"""Data Mapper - Enterprise-level deterministic field mapping.

This is the CORE of the semantic layer.
Each data source has an EXACT mapping: source_field → table.column.
No AI. No fuzzy matching. No guessing.

When a new field appears that's not in any mapping → AI decides where it goes.
"""
import json
from typing import Dict, Any, List, Tuple, Optional


import os
from pathlib import Path

# Source name aliases → which mapping to use
SOURCE_ALIASES = {
    "salesforce_crm": "crm",
    "salesforce": "crm",
    "hubspot": "crm",
    "hubspot_crm": "crm",
    "pipedrive": "crm",
    "zoho_crm": "crm",
    "dynamics_crm": "crm",
    "crm": "crm",
    "crm_export": "crm",
    "user_upload": "crm",

    "sap_erp": "erp",
    "sap": "erp",
    "oracle_erp": "erp",
    "oracle": "erp",
    "netsuite": "erp",
    "quickbooks": "erp",
    "xero": "erp",
    "erp": "erp",

    "workday": "hrms",
    "workday_hrms": "hrms",
    "bamboohr": "hrms",
    "adp": "hrms",
    "gusto": "hrms",
    "hrms": "hrms",
}


class DataMapper:
    """
    Maps source data to canonical tables using exact field mappings.
    Zero AI. Zero guessing. 100% deterministic.
    """

    def __init__(self):
        self.mappings = self._load_mappings()
        self.aliases = SOURCE_ALIASES

    def _load_mappings(self) -> Dict[str, Any]:
        """Load all mapping JSON files from the mappings directory."""
        mappings = {}
        mapping_dir = Path(__file__).parent / "mappings"
        
        if not mapping_dir.exists():
            return {}

        for mapping_file in mapping_dir.glob("*.json"):
            try:
                with open(mapping_file, 'r') as f:
                    mappings[mapping_file.stem] = json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading mapping {mapping_file}: {e}")
        
        return mappings

    def detect_source_type(self, source_name: str) -> Optional[str]:
        """
        Resolve source name to mapping type.
        Returns: "crm", "erp", "hrms", or None if unknown
        """
        source_lower = source_name.lower().strip()
        return self.aliases.get(source_lower)

    def _normalize_value(self, value: Any) -> Optional[str]:
        """Convert any value to a string for canonical storage."""
        if value is None:
            return None
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    def classify(self, data: List[Dict[str, Any]], source_name: str, db: Optional[Any] = None) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Classify data into canonical tables using exact mappings.
        If db session is provided, also checks existing database columns to avoid
        re-detecting already-evolved fields as "unmapped".
        """
        source_type = self.detect_source_type(source_name)

        if not source_type:
            return None, []

        mapping = self.mappings.get(source_type, {})
        
        # DYNAMIC SCHEMA AWARENESS:
        # If we have a DB session, fetch actually existing columns in the Silver schema.
        # This allows the mapper to "know" about fields added via AI evolution.
        known_db_columns = {} # table_name -> set of columns
        if db:
            try:
                from sqlalchemy import inspect
                inspector = inspect(db.bind)
                for table_name in inspector.get_table_names(schema="silver"):
                    cols = {col["name"] for col in inspector.get_columns(table_name, schema="silver")}
                    known_db_columns[table_name] = cols
            except Exception as e:
                print(f"  ⚠️ Schema reflection failed: {e}")

        classifications = {}
        all_unmapped = []

        # Build a global set of ALL mapped fields for this source
        all_mapped_source_fields = set()
        for table_name, field_map in mapping.items():
            for canonical_col, source_field in field_map.items():
                all_mapped_source_fields.add(source_field)

        for record in data:
            # Track which source fields we've mapped in this record
            mapped_source_fields = set()

            # Tables to check: those in mapping + those in DB
            target_tables = set(mapping.keys()) | set(known_db_columns.keys())

            for table_name in target_tables:
                mapped_record = {}
                field_map = mapping.get(table_name, {})
                db_cols = known_db_columns.get(table_name, set())

                # 1. Map via hardcoded deterministic mapping
                for canonical_col, source_field in field_map.items():
                    if source_field in record:
                        value = record[source_field]
                        mapped_record[canonical_col] = self._normalize_value(value)
                        mapped_source_fields.add(source_field)

                # 2. Map via dynamic DB schema awareness (if not already mapped)
                # If a field in the record exactly matches a column in the DB, map it!
                for field_name in record:
                    if field_name not in mapped_source_fields and field_name in db_cols:
                        mapped_record[field_name] = self._normalize_value(record[field_name])
                        # We don't necessarily add to mapped_source_fields here yet 
                        # because multiple tables might have the same column (like account_name)

                # Post-process the record
                if not mapped_record:
                    continue

                # Dimension records are meaningful if they have their primary identifier
                is_dimension = table_name.startswith("dim_")
                primary_id = "account_name" if table_name == "dim_account" else ("contact_name" if table_name == "dim_contact" else None)
                has_id = primary_id in mapped_record if primary_id else False
                
                # Other fields that aren't metadata
                meaningful_fields = [k for k in mapped_record if k not in ("account_name", "contact_name", "source", "source_data")]
                
                if meaningful_fields or (is_dimension and has_id):
                    # Add source_data for fact tables
                    if table_name.startswith("fact_"):
                        mapped_record["source_data"] = json.dumps(record, default=str)
                    classifications.setdefault(table_name, []).append(mapped_record)
                    
                    # Mark all fields used in this table as mapped for the "unmapped" check later
                    for k in mapped_record:
                        if k in record:
                            mapped_source_fields.add(k)

            # Find unmapped fields (fields in source data not in any mapping and not in DB)
            for field_name, value in record.items():
                # A field is unmapped only if it wasn't used in any table (hardcoded or dynamic)
                if field_name not in mapped_source_fields and field_name not in all_mapped_source_fields:
                    all_unmapped.append({
                        "field": field_name,
                        "sample_value": str(value)[:100] if value else "",
                        "source_type": source_type,
                    })

        # Build result
        result = {
            "classifications": [
                {"table": table_name, "records": records}
                for table_name, records in classifications.items()
            ],
            "summary": f"Mapped {len(data)} record(s) as {source_type} into {len(classifications)} table(s)",
            "method": "deterministic",
        }

        # Deduplicate unmapped fields
        seen = set()
        unique_unmapped = []
        for item in all_unmapped:
            if item["field"] not in seen:
                seen.add(item["field"])
                unique_unmapped.append(item)

        return result, unique_unmapped

    def get_known_source_types(self) -> List[str]:
        """Return list of supported source types"""
        return list(self.mappings.keys())

    def get_mapping_for_source(self, source_name: str) -> Optional[Dict]:
        """Return the field mapping for a specific source"""
        source_type = self.detect_source_type(source_name)
        if source_type:
            return self.mappings[source_type]
        return None
