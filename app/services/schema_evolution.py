"""Schema Evolution Engine - Enterprise-level deterministic schema management.

Handles ONLY truly new/unknown fields that aren't in any source mapping.
Uses AI ONLY to decide which table an unknown field belongs to.
"""
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from openai import OpenAI
from app.config import settings


class SchemaEvolutionEngine:
    """
    When unmapped fields appear in data, this engine:
    1. Uses AI to decide which canonical table the field belongs to
    2. Adds the column with ALTER TABLE
    3. Returns the mapping so data can be inserted
    """

    def __init__(self, db: Session):
        self.db = db
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=60.0,
            max_retries=2,
        )

    def handle_unmapped_fields(self, unmapped_fields: List[Dict]) -> Dict[str, Any]:
        """
        Process fields that weren't in any source mapping.

        Args:
            unmapped_fields: [{"field": "region", "sample_value": "North America", "source_type": "crm"}]

        Returns:
            Report of what happened + new mappings to use for insertion
        """
        report = {
            "columns_added": [],
            "fields_ignored": [],
            "new_mappings": {},  # table_name → {canonical_col: source_field}
        }

        if not unmapped_fields:
            return report

        print(f"\n🔍 Found {len(unmapped_fields)} unmapped field(s)")

        for field_info in unmapped_fields:
            field_name = field_info["field"]
            sample_value = field_info.get("sample_value", "")

            # Use AI to classify this unknown field
            print(f"  🤖 Unknown field '{field_name}' (value: '{sample_value[:50]}') → asking AI...")

            suggested_table = self._classify_field_with_ai(field_name, sample_value)

            if suggested_table:
                # Add column to the suggested table
                if self._add_column(suggested_table, field_name):
                    report["columns_added"].append({
                        "table": suggested_table,
                        "column": field_name,
                    })
                    # Store new mapping so ingest can use it
                    report["new_mappings"].setdefault(suggested_table, {})[field_name] = field_name
                    print(f"  ✅ Added '{field_name}' to {suggested_table}")
            else:
                report["fields_ignored"].append(field_name)
                print(f"  ⏭️ Ignored '{field_name}' (AI says not relevant)")

        return report

    def _classify_field_with_ai(self, field_name: str, sample_value: str) -> Optional[str]:
        """
        AI decides: which canonical table does this unknown field belong to?
        Returns table name or None if field should be ignored.
        """
        prompt = f"""A new field appeared in business data that isn't in our standard mapping.

FIELD NAME: {field_name}
SAMPLE VALUE: {sample_value}

AVAILABLE TABLES:
- dim_account: Companies, organizations (columns: account_name, industry, geography, annual_revenue, employee_count, website)
- dim_contact: People, employees (columns: name, email, phone, title, role, department, account_name)
- dim_product: Products, services (columns: name, category, price, sku, description)
- dim_department: Departments, teams (columns: name, function, head, location)
- dim_location: Geographic locations (columns: city, state, country, region)
- fact_deals: Sales opportunities (columns: deal_name, deal_value, deal_stage, account_name)
- fact_transactions: Financial events (columns: transaction_type, amount, status, account_name)
- fact_hr_records: Employee events (columns: record_type, employee_name, department, salary)
- fact_insights: AI-extracted insights (columns: insight_type, content, account_name)

Which table should this field be added to? Or should it be ignored?

Return JSON only:
{{"table": "dim_account", "reasoning": "brief reason"}}

If the field is internal metadata, technical, or not business-relevant, return:
{{"table": "ignore", "reasoning": "brief reason"}}"""

        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a database schema expert. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            result = json.loads(content.strip())
            table = result.get("table", "ignore")
            reasoning = result.get("reasoning", "")
            print(f"     AI reasoning: {reasoning}")

            if table == "ignore":
                return None
            return table

        except Exception as e:
            print(f"  ⚠️ AI classification failed: {e}")
            return None

    def _add_column(self, table_name: str, column_name: str) -> bool:
        """Add a new TEXT column to an existing table."""
        try:
            safe_name = column_name.lower().replace(" ", "_").replace("-", "_")

            # Ensure we are working with silver schema
            from app.services.canonical_schema import SILVER_SCHEMA
            
            # Check if already exists in silver schema
            inspector = inspect(self.db.bind)
            try:
                existing = [col["name"] for col in inspector.get_columns(table_name, schema=SILVER_SCHEMA)]
            except Exception:
                # If table doesn't exist yet, we can't add a column
                return False
                
            if safe_name in existing:
                return True

            sql = f'ALTER TABLE silver."{table_name}" ADD COLUMN "{safe_name}" TEXT'
            self.db.execute(text(sql))
            self.db.commit()
            return True

        except Exception as e:
            print(f"  ❌ Error adding column: {e}")
            self.db.rollback()
            return False
