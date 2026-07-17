"""
Gold Schema Agent - Proposes new Gold tables/columns on Silver fallback

Fires in background thread (non-blocking) whenever query falls back to Silver.
Analyzes what Silver returned and proposes Gold schema improvements.
Stores proposals in gold.schema_proposals for human review.

KEY CAPABILITY (v2):
  - Reads ACTUAL gold SQL files from app/sql/gold/ to understand current refresh logic
  - Introspects LIVE silver table schemas (columns + types) from the database
  - Produces EXECUTABLE SQL: ALTER TABLE DDL + complete updated refresh query
  - Proposals are copy-paste-ready — no manual SQL writing needed

Nothing is auto-applied - engineers review and implement approved proposals.
Over time, this progressively eliminates Silver fallbacks.
"""

import json
import re
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from app.config import settings
from app.sql import get_query, get_gold_queries, GOLD_DIR


class GoldSchemaAgent:
    """
    Analyzes Silver fallback queries and proposes Gold schema improvements.
    
    DESIGN PRINCIPLES:
    - Runs in background thread (never blocks user query)
    - Stores proposals, never auto-applies
    - Human engineers review and implement
    - Progressive improvement over time
    - Proposals include EXECUTABLE SQL (ALTER + refresh query)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=45.0,
            max_retries=1,
        )
    
    def analyze_fallback(
        self,
        question: str,
        silver_data: List[Dict],
        silver_sql: List[str],
        execution_time_ms: float
    ) -> None:
        """
        Fire-and-forget analysis of Silver fallback.
        Runs in background thread so it never blocks the response.
        """
        # Skip if Silver returned nothing useful
        if not silver_data or len(silver_data) == 0:
            return
        
        # Spawn background thread
        thread = threading.Thread(
            target=self._analyze_and_propose,
            args=(question, silver_data, silver_sql, execution_time_ms),
            daemon=True
        )
        thread.start()
        print(f"  🤖 GoldSchemaAgent: Background analysis started for: {question[:50]}...")
    
    def _analyze_and_propose(
        self,
        question: str,
        silver_data: List[Dict],
        silver_sql: List[str],
        execution_time_ms: float
    ) -> None:
        """
        Internal method that runs in background thread.
        Analyzes the fallback and creates a proposal.
        """
        try:
            # Ensure proposals table exists
            self._ensure_proposals_table()
            
            # Extract which Silver tables were queried
            silver_tables = self._extract_silver_tables(silver_sql)
            
            # Check if similar proposal already exists
            if self._similar_proposal_exists(question, silver_tables):
                print(f"  🤖 GoldSchemaAgent: Similar proposal already exists, skipping")
                return
            
            # Gather rich context for the proposal
            gold_context = self._get_gold_context()
            silver_context = self._get_silver_schema_details(silver_tables)
            
            # Ask GPT-4 to propose Gold improvement with full context
            proposal = self._generate_proposal(
                question=question,
                silver_tables=silver_tables,
                silver_data_sample=silver_data[:5],
                gold_context=gold_context,
                silver_context=silver_context,
                execution_time_ms=execution_time_ms
            )
            
            if proposal:
                # Store proposal in database
                self._store_proposal(proposal, question, silver_tables, silver_data[:3])
                print(f"  ✅ GoldSchemaAgent: Proposal created - {proposal.get('proposal_type')} for {proposal.get('target_table')}")
            
        except Exception as e:
            print(f"  ⚠️ GoldSchemaAgent error: {e}")
            # Never fail the original request
    
    def _ensure_proposals_table(self) -> None:
        """Create schema_proposals table if it doesn't exist."""
        try:
            sql = get_query("gold", "schema_proposals")
            if sql:
                self.db.execute(text(sql))
                self.db.commit()
        except Exception as e:
            print(f"  ⚠️ Could not create proposals table: {e}")
            self.db.rollback()
    
    def _extract_silver_tables(self, sql_queries: List[str]) -> List[str]:
        """Extract silver table names from SQL queries."""
        tables = set()
        pattern = re.compile(r'silver\.(\w+)', re.IGNORECASE)
        for sql in sql_queries:
            for match in pattern.finditer(sql):
                table_name = match.group(1).lower()
                if table_name not in ("where", "from", "join", "on", "and", "or"):
                    tables.add(f"silver.{table_name}")
        return sorted(tables)
    
    # ------------------------------------------------------------------
    # Context gathering — reads actual SQL files + live DB schemas
    # ------------------------------------------------------------------

    def _get_gold_context(self) -> str:
        """
        Build rich Gold layer context:
        1. List of gold tables with their columns (from DB)
        2. The actual SQL refresh query for each table (from .sql files)
        """
        parts = []

        # 1. Gold table schemas from live DB
        gold_tables = self._get_gold_table_schemas()
        if gold_tables:
            parts.append("=== CURRENT GOLD TABLE SCHEMAS ===")
            for table_name, columns in gold_tables.items():
                col_list = ", ".join(f"{c['name']} {c['type']}" for c in columns)
                parts.append(f"gold.{table_name} ({col_list})")

        # 2. Actual SQL refresh queries from disk
        gold_queries = get_gold_queries()
        if gold_queries:
            parts.append("\n=== GOLD REFRESH SQL (from app/sql/gold/) ===")
            for name, sql in sorted(gold_queries.items()):
                if name in ("__init__", "schema_proposals"):
                    continue
                # Truncate very long SQL to fit context window
                sql_trimmed = sql.strip()[:2000]
                parts.append(f"\n--- gold/{name}.sql ---\n{sql_trimmed}")

        return "\n".join(parts) if parts else "(no gold tables found)"

    def _get_gold_table_schemas(self) -> Dict[str, List[Dict]]:
        """Get column names and types for all gold tables from DB."""
        try:
            inspector = inspect(self.db.bind)
            tables = inspector.get_table_names(schema="gold")
            result = {}
            for t in tables:
                if t == "schema_proposals":
                    continue
                cols = inspector.get_columns(t, schema="gold")
                result[t] = [{"name": c["name"], "type": str(c["type"])} for c in cols]
            return result
        except Exception as e:
            print(f"  ⚠️ Could not introspect gold schema: {e}")
            return {}

    def _get_silver_schema_details(self, silver_tables: List[str]) -> str:
        """
        Get actual column names and types for the silver tables that were queried.
        Also includes ALL silver tables for completeness.
        """
        try:
            inspector = inspect(self.db.bind)
            all_silver = inspector.get_table_names(schema="silver")
            parts = ["=== SILVER TABLE SCHEMAS ==="]
            for t in sorted(all_silver):
                cols = inspector.get_columns(t, schema="silver")
                col_list = ", ".join(f"{c['name']} {str(c['type'])}" for c in cols)
                marker = " ← QUERIED" if f"silver.{t}" in silver_tables else ""
                parts.append(f"silver.{t}{marker} ({col_list})")
            return "\n".join(parts)
        except Exception as e:
            print(f"  ⚠️ Could not introspect silver schema: {e}")
            return f"Silver tables queried: {', '.join(silver_tables)}"
    
    def _similar_proposal_exists(self, question: str, silver_tables: List[str]) -> bool:
        """Check if a similar proposal already exists."""
        try:
            tables_json = json.dumps(silver_tables)
            result = self.db.execute(text("""
                SELECT COUNT(*) 
                FROM gold.schema_proposals 
                WHERE status = 'pending_approval'
                AND (
                    business_question ILIKE :question_pattern
                    OR silver_tables_queried::text = :tables_json
                )
            """), {
                "question_pattern": f"%{question[:30]}%",
                "tables_json": tables_json
            })
            return result.scalar() > 0
        except Exception:
            return False
    
    def _generate_proposal(
        self,
        question: str,
        silver_tables: List[str],
        silver_data_sample: List[Dict],
        gold_context: str,
        silver_context: str,
        execution_time_ms: float
    ) -> Optional[Dict[str, Any]]:
        """
        Ask GPT-4 to propose a Gold schema improvement with EXECUTABLE SQL.
        
        The prompt includes:
        - The actual Gold table DDLs and refresh SQL from disk
        - The actual Silver table schemas from DB
        - Sample data that Silver returned
        
        The output includes:
        - For new_columns: ALTER TABLE statement + FULL updated refresh SQL
        - For new_table: CREATE TABLE DDL + refresh SQL + gold_layer.py snippet
        """
        prompt = f"""You are a senior data warehouse architect. A business question fell back to Silver 
because Gold couldn't answer it. Propose a PRODUCTION-READY Gold schema change.

═══ BUSINESS QUESTION ═══
{question}

═══ SILVER TABLES QUERIED ═══
{', '.join(silver_tables)}

═══ SAMPLE DATA FROM SILVER (first 5 rows) ═══
{json.dumps(silver_data_sample, indent=2, default=str)[:1500]}

═══ EXECUTION TIME (Silver) ═══
{execution_time_ms:.0f}ms — Gold pre-aggregation would be faster.

{gold_context}

{silver_context}

═══ YOUR TASK ═══

Decide ONE of:
A) **new_columns** — Add columns to an EXISTING Gold table
B) **new_table** — Create an entirely new Gold table

Then produce EXECUTABLE SQL that an engineer can copy-paste and deploy.

Return JSON with these fields:

{{
    "proposal_type": "new_table" or "new_columns",
    "target_table": "gold.table_name",
    "rationale": "1-2 sentence business justification",

    "ddl_statements": [
        "ALTER TABLE gold.revenue_summary ADD COLUMN new_col TEXT;",
        "-- or CREATE TABLE gold.new_table (...);  for new_table proposals"
    ],

    "refresh_sql": "-- The COMPLETE refresh SQL (DELETE + INSERT INTO ... SELECT FROM silver...)\n-- For new_columns: provide the FULL UPDATED version of the existing refresh SQL\n-- For new_table: provide the new refresh SQL\n-- This must be a working query that populates the gold table from silver tables.",

    "silver_to_gold_mapping": {{
        "description": "What this Gold table/columns answer",
        "source_tables": ["silver.fact_deals"],
        "column_mappings": [
            {{"gold_column": "col_name", "silver_source": "expression", "transformation": "description"}}
        ]
    }},

    "proposed_columns": [
        {{"name": "col_name", "type": "NUMERIC", "description": "what it measures"}}
    ]
}}

═══ RULES ═══
1. The refresh_sql must be a COMPLETE, RUNNABLE SQL query (DELETE + INSERT + SELECT).
2. For "new_columns" on an existing table: look at the CURRENT refresh SQL shown above 
   and produce a FULL UPDATED VERSION that includes the new columns.
3. Follow the exact SQL patterns used in the existing gold/*.sql files (COALESCE, CASE WHEN, etc.).
4. Column types: use NUMERIC for values, INTEGER for counts, TEXT for labels/names.
5. All deal_value comparisons must use: deal_value ~ '^[0-9.]+$' before CAST.
6. If no useful Gold change can be proposed (question is too unique), return: {{"proposal_type": "none"}}
"""
        
        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior data warehouse architect. "
                            "Produce production-ready SQL that follows the exact patterns "
                            "used in the existing codebase. Return valid JSON only."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                max_tokens=3000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean markdown if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content.strip())
            
            if result.get("proposal_type") == "none":
                return None
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ GPT proposal generation failed: {e}")
            return None
    
    def _store_proposal(
        self,
        proposal: Dict[str, Any],
        question: str,
        silver_tables: List[str],
        sample_data: List[Dict]
    ) -> None:
        """Store the proposal in gold.schema_proposals."""
        try:
            # ddl_statements is a list — join into single string for storage
            ddl = proposal.get("ddl_statements") or proposal.get("proposed_ddl")
            if isinstance(ddl, list):
                ddl = "\n".join(ddl)

            # refresh_sql takes priority over generic proposed_sql
            refresh_sql = proposal.get("refresh_sql") or proposal.get("proposed_sql") or ""

            self.db.execute(text("""
                INSERT INTO gold.schema_proposals (
                    proposal_type,
                    target_table,
                    proposed_ddl,
                    proposed_columns,
                    silver_to_gold_mapping,
                    business_question,
                    silver_tables_queried,
                    sample_data_returned,
                    rationale,
                    proposed_sql,
                    status,
                    created_at
                ) VALUES (
                    :proposal_type,
                    :target_table,
                    :proposed_ddl,
                    :proposed_columns,
                    :silver_to_gold_mapping,
                    :business_question,
                    :silver_tables,
                    :sample_data,
                    :rationale,
                    :proposed_sql,
                    'pending_approval',
                    CURRENT_TIMESTAMP
                )
            """), {
                "proposal_type": proposal.get("proposal_type"),
                "target_table": proposal.get("target_table"),
                "proposed_ddl": ddl,
                "proposed_columns": json.dumps(proposal.get("proposed_columns", [])),
                "silver_to_gold_mapping": json.dumps(proposal.get("silver_to_gold_mapping", {})),
                "business_question": question,
                "silver_tables": json.dumps(silver_tables),
                "sample_data": json.dumps(sample_data, default=str),
                "rationale": proposal.get("rationale"),
                "proposed_sql": refresh_sql
            })
            self.db.commit()
            
        except Exception as e:
            print(f"  ⚠️ Failed to store proposal: {e}")
            self.db.rollback()
    
    def get_pending_proposals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pending proposals for human review."""
        try:
            result = self.db.execute(text("""
                SELECT 
                    id,
                    proposal_type,
                    target_table,
                    proposed_ddl,
                    proposed_columns,
                    silver_to_gold_mapping,
                    business_question,
                    silver_tables_queried,
                    rationale,
                    proposed_sql,
                    created_at
                FROM gold.schema_proposals
                WHERE status = 'pending_approval'
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"limit": limit})
            
            proposals = []
            for row in result.fetchall():
                proposals.append({
                    "id": row[0],
                    "proposal_type": row[1],
                    "target_table": row[2],
                    "proposed_ddl": row[3],
                    "proposed_columns": json.loads(row[4]) if row[4] else [],
                    "silver_to_gold_mapping": json.loads(row[5]) if row[5] else {},
                    "business_question": row[6],
                    "silver_tables_queried": json.loads(row[7]) if row[7] else [],
                    "rationale": row[8],
                    "proposed_sql": row[9],
                    "created_at": row[10].isoformat() if row[10] else None
                })
            return proposals
            
        except Exception as e:
            print(f"  ⚠️ Failed to get proposals: {e}")
            return []
    
    def approve_proposal(self, proposal_id: int, reviewer: str, notes: str = "") -> bool:
        """Mark a proposal as approved (human reviewer)."""
        try:
            self.db.execute(text("""
                UPDATE gold.schema_proposals
                SET status = 'approved',
                    reviewed_by = :reviewer,
                    review_notes = :notes,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = :proposal_id
            """), {
                "proposal_id": proposal_id,
                "reviewer": reviewer,
                "notes": notes
            })
            self.db.commit()
            return True
        except Exception as e:
            print(f"  ⚠️ Failed to approve proposal: {e}")
            self.db.rollback()
            return False
    
    def reject_proposal(self, proposal_id: int, reviewer: str, notes: str) -> bool:
        """Mark a proposal as rejected (human reviewer)."""
        try:
            self.db.execute(text("""
                UPDATE gold.schema_proposals
                SET status = 'rejected',
                    reviewed_by = :reviewer,
                    review_notes = :notes,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = :proposal_id
            """), {
                "proposal_id": proposal_id,
                "reviewer": reviewer,
                "notes": notes
            })
            self.db.commit()
            return True
        except Exception as e:
            print(f"  ⚠️ Failed to reject proposal: {e}")
            self.db.rollback()
            return False
    
    def mark_implemented(self, proposal_id: int) -> bool:
        """Mark a proposal as implemented (after DDL is applied)."""
        try:
            self.db.execute(text("""
                UPDATE gold.schema_proposals
                SET status = 'implemented',
                    implemented_at = CURRENT_TIMESTAMP
                WHERE id = :proposal_id
            """), {"proposal_id": proposal_id})
            self.db.commit()
            return True
        except Exception as e:
            print(f"  ⚠️ Failed to mark proposal implemented: {e}")
            self.db.rollback()
            return False
