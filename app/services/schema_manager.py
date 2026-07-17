"""Schema Manager - Creates canonical tables and manages data insertion"""
from typing import List, Dict, Any, Optional
from sqlalchemy import MetaData, text
from sqlalchemy.orm import Session
import json

from app.services.canonical_schema import CANONICAL_SCHEMA, get_all_table_names, SILVER_SCHEMA, prefixed as silver_prefixed
from app.services.data_validator import validate_record
from app.sql import get_query

class SchemaManager:
    """
    Manages the Silver layer entity tables (dim_* / fact_*).

    Medallion Architecture roles:
      bronze.raw_ingestion      = Bronze  (raw, as-is)
      silver.processed_data     = Silver  (cleaned JSON audit trail)
      silver.dim_* / silver.fact_* = Silver  (normalised entity tables)
      gold.*                    = Gold    (pre-aggregated business marts)
      NL Query Engine           = Semantic Layer (translation service, not storage)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.metadata = MetaData()
        self.metadata.reflect(bind=db.bind, schema=SILVER_SCHEMA)
    
    def initialize_canonical_schema(self) -> Dict[str, Any]:
        """
        Create all canonical tables if they don't exist.
        Called on application startup.
        
        Returns:
            Dict with created and existing table counts
        """
        # Initialize Bronze and Silver schemas
        self._initialize_bronze_silver_schemas()

        created = []
        existing = []
        
        # Migrate existing public-schema dim_*/fact_* tables into silver schema
        self._migrate_public_tables_to_silver()

        # Create dimension tables in silver schema
        for table_name, table_def in CANONICAL_SCHEMA["dimensions"].items():
            if self._create_table(table_name, table_def["columns"], is_dimension=True):
                created.append(table_name)
            else:
                existing.append(table_name)

        # Create fact tables in silver schema
        for table_name, table_def in CANONICAL_SCHEMA["facts"].items():
            if self._create_table(table_name, table_def["columns"], is_dimension=False):
                created.append(table_name)
            else:
                existing.append(table_name)

        # Migrate dim_contact constraint if it still has old UNIQUE(name) only
        self._migrate_dim_contact_constraint()

        # Add content/confidence/insight_date columns to fact_insights if missing
        self._migrate_fact_insights_columns()

        # Account identity layer: account_source_map + account_id FK on fact tables
        self._migrate_account_identity()

        # Data quality issues table for validation rejects
        self._migrate_data_quality_table()

        # ThoughtFocus dimension columns (vertical, horizontal, etc.)
        self._migrate_tf_columns()

        # Refresh metadata after all tables created
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.db.bind, schema=SILVER_SCHEMA)
        
        return {"created": created, "existing": existing}

    def _migrate_public_tables_to_silver(self):
        """
        One-time migration: move any dim_*/fact_* tables still in the public
        schema into the silver schema where they belong.
        Safe to call repeatedly — checks before acting.
        """
        try:
            pub_meta = MetaData()
            pub_meta.reflect(bind=self.db.bind)  # reflects public schema
            for bare_name in get_all_table_names(prefixed=False):
                if bare_name in pub_meta.tables:
                    self.db.execute(text(
                        f'ALTER TABLE public."{bare_name}" SET SCHEMA silver'
                    ))
                    print(f"  🔀 Moved public.{bare_name} → silver.{bare_name}")
            self.db.commit()
        except Exception as e:
            print(f"  ⚠️ Public→Silver migration: {e}")
            self.db.rollback()

    def _migrate_dim_contact_constraint(self):
        """
        Ensure silver.dim_contact uses composite UNIQUE(name, account_name).
        Drops the old single-column UNIQUE(name) constraint if it exists.
        Safe to call repeatedly — uses external SQL file.
        """
        try:
            sql = get_query("silver", "migrate_constraints")
            if sql:
                # SQLAlchemy text() execute split by semicolons if needed or execute as one block
                # Postgres allows multiple statements in one block if using plain text
                self.db.execute(text(sql))
                self.db.commit()
                print("  ✅ Applied Silver constraint migrations")
            else:
                print("  ⚠️ migrate_constraints.sql not found")
        except Exception as e:
            print(f"  ⚠️ dim_contact constraint migration: {e}")
            self.db.rollback()
    
    def _migrate_fact_insights_columns(self):
        """Add content, confidence, insight_date columns to fact_insights if they don't exist."""
        try:
            sql = get_query("silver", "migrate_fact_insights")
            if sql:
                self.db.execute(text(sql))
                self.db.commit()
            else:
                print("  ⚠️ migrate_fact_insights.sql not found")
        except Exception as e:
            print(f"  ⚠️ fact_insights column migration: {e}")
            self.db.rollback()

    def _migrate_account_identity(self):
        """Add account_id FK to fact tables and create account_source_map."""
        try:
            sql = get_query("silver", "migrate_account_identity")
            if sql:
                self.db.execute(text(sql))
                self.db.commit()
                print("  ✅ Applied account identity migration")
            else:
                print("  ⚠️ migrate_account_identity.sql not found")
        except Exception as e:
            print(f"  ⚠️ Account identity migration: {e}")
            self.db.rollback()

    def _migrate_data_quality_table(self):
        """Create silver.data_quality_issues table for validation rejects."""
        try:
            sql = get_query("silver", "migrate_data_quality")
            if sql:
                self.db.execute(text(sql))
                self.db.commit()
            else:
                print("  ⚠️ migrate_data_quality.sql not found")
        except Exception as e:
            print(f"  ⚠️ Data quality table migration: {e}")
            self.db.rollback()

    def _migrate_tf_columns(self):
        """Add ThoughtFocus-specific dimension columns to existing silver tables."""
        try:
            sql = get_query("silver", "migrate_tf_columns")
            if sql:
                self.db.execute(text(sql))
                self.db.commit()
                print("  ✅ Applied TF dimension column migration")
            else:
                print("  ⚠️ migrate_tf_columns.sql not found")
        except Exception as e:
            print(f"  ⚠️ TF column migration: {e}")
            self.db.rollback()

    def _log_quality_issue(self, table_name: str, errors: List[str], record: Dict[str, Any]):
        """Insert a rejected record into silver.data_quality_issues."""
        try:
            self.db.execute(
                text("""
                    INSERT INTO silver.data_quality_issues (table_name, error_messages, raw_record)
                    VALUES (:tbl, :errs, :rec)
                """),
                {
                    "tbl": table_name,
                    "errs": errors,
                    "rec": json.dumps(record, default=str),
                }
            )
        except Exception as e:
            print(f"  ⚠️ Could not log quality issue: {e}")

    def resolve_account_id(self, account_name: str, source: str = None) -> Optional[int]:
        """
        Resolve an account_name to an internal account_id (dim_account.id).

        Matching strategy (in order):
          1. Exact match
          2. Case-insensitive match
          3. Substring containment (min 3 chars to avoid false positives)
          4. No match → auto-create dim_account row

        Populates account_source_map on every successful resolution.
        """
        if not account_name or not account_name.strip():
            return None

        name = account_name.strip()

        # 1. Exact match
        row = self.db.execute(
            text("SELECT id FROM silver.dim_account WHERE account_name = :name LIMIT 1"),
            {"name": name}
        ).fetchone()
        if row:
            self._upsert_account_source_map(row[0], source, name)
            return row[0]

        # 2. Case-insensitive match
        row = self.db.execute(
            text("SELECT id FROM silver.dim_account WHERE LOWER(TRIM(account_name)) = LOWER(TRIM(:name)) LIMIT 1"),
            {"name": name}
        ).fetchone()
        if row:
            self._upsert_account_source_map(row[0], source, name)
            return row[0]

        # 3. Substring containment (both directions, skip very short names)
        if len(name) >= 3:
            row = self.db.execute(
                text("""
                    SELECT id FROM silver.dim_account
                    WHERE LOWER(account_name) LIKE '%%' || LOWER(:name) || '%%'
                       OR LOWER(:name) LIKE '%%' || LOWER(account_name) || '%%'
                    ORDER BY LENGTH(account_name) ASC
                    LIMIT 1
                """),
                {"name": name}
            ).fetchone()
            if row:
                self._upsert_account_source_map(row[0], source, name)
                return row[0]

        # 4. No match → auto-create a minimal dim_account row
        row = self.db.execute(
            text('INSERT INTO silver.dim_account ("account_name") VALUES (:name) RETURNING id'),
            {"name": name}
        ).fetchone()
        if row:
            self._upsert_account_source_map(row[0], source, name)
            return row[0]

        return None

    def _upsert_account_source_map(self, account_id: int, source: str, source_name: str, source_id: str = None):
        """Track which source provided which name for a given account."""
        if not account_id or not source_name:
            return
        try:
            self.db.execute(
                text("""
                    INSERT INTO silver.account_source_map (account_id, source, source_name, source_id)
                    VALUES (:aid, :src, :sname, :sid)
                    ON CONFLICT (account_id, source, source_name) DO UPDATE
                    SET source_id = COALESCE(EXCLUDED.source_id, silver.account_source_map.source_id),
                        updated_at = CURRENT_TIMESTAMP
                """),
                {"aid": account_id, "src": source or "unknown", "sname": source_name, "sid": source_id}
            )
        except Exception as e:
            print(f"  ⚠️ account_source_map upsert: {e}")

    def _initialize_bronze_silver_schemas(self):
        """Create bronze and silver schemas and base tables using external SQL."""
        try:
            sql = get_query("silver", "init_schemas")
            if sql:
                self.db.execute(text(sql))
                self.db.commit()
                print("  ✅ Initialized bronze and silver schemas from SQL file")
            else:
                print("  ⚠️ init_schemas.sql not found")
        except Exception as e:
            print(f"  ⚠️ Error initializing bronze/silver schemas: {e}")
            self.db.rollback()

    def save_to_bronze(self, source: str, data_type: str, records: List[Dict[str, Any]]):
        """Save raw data payload to the Bronze layer in Postgres"""
        if not records:
            return
        try:
            for record in records:
                self.db.execute(
                    text("INSERT INTO bronze.raw_ingestion (source, data_type, raw_payload) VALUES (:source, :dtype, :payload)"),
                    {"source": source, "dtype": data_type, "payload": json.dumps(record)}
                )
            self.db.commit()
            print(f"  💾 Saved {len(records)} record(s) to Bronze layer")
        except Exception as e:
            print(f"  ⚠️ Error saving to Bronze layer: {e}")
            self.db.rollback()

    def save_to_silver(self, source: str, classification_method: str, payload: Dict[str, Any]):
        """Save processed extraction to the Silver layer in Postgres"""
        if not payload:
            return
            
        # Transform destination-centric to source-centric and clean data
        entities = {}
        table_to_entity = {
            "dim_account": "accounts",
            "dim_contact": "contacts",
            "fact_deals": "deals",
            "fact_interactions": "interactions",
            "fact_insights": "insights"
        }
        
        for item in payload.get("classifications", []):
            table = item.get("table", "")
            entity_name = table_to_entity.get(table, table)
            records = item.get("records", [])
            cleaned_records = []
            
            for rec in records:
                clean_rec = {}
                for k, v in rec.items():
                    # 6. Remove overloaded source_data
                    if k == "source_data":
                        continue
                        
                    if isinstance(v, str):
                        # 3. Fix Nested JSON Strings
                        try:
                            if v.startswith('[') or v.startswith('{'):
                                parsed_v = json.loads(v)
                                clean_rec[k] = parsed_v
                                continue
                        except json.JSONDecodeError:
                            pass
                            
                        # 2. Fix dirty data types (strings -> numbers)
                        # Remove whitespace and normalize
                        v_stripped = v.strip()
                        try:
                            if '.' in v_stripped:
                                fv = float(v_stripped)
                                # Only convert to int if it's perfectly whole
                                if fv.is_integer() and not k.endswith("rate") and not k.endswith("multiplier"):
                                    clean_rec[k] = int(fv)
                                else:
                                    clean_rec[k] = fv
                                continue
                            elif v_stripped.lstrip('-').isdigit():
                                clean_rec[k] = int(v_stripped)
                                continue
                        except ValueError:
                            pass
                            
                        # 4. Normalization for specific fields
                        if k in ("account_name", "contact_name") and table in ("dim_account", "fact_deals", "fact_interactions", "fact_insights", "dim_contact"):
                            clean_rec[k] = v_stripped
                        elif k == "sentiment":
                            clean_rec[k] = v_stripped.lower()
                        else:
                            clean_rec[k] = v_stripped
                    else:
                        clean_rec[k] = v
                cleaned_records.append(clean_rec)
                
            entities[entity_name] = cleaned_records
            
        # 5. Separate Metadata from Entities
        silver_payload = {
            "metadata": {
                "summary": payload.get("summary", ""),
                "source": payload.get("source", source),
                "records_analyzed": payload.get("records_analyzed", 0),
                "classification_method": classification_method
            },
            "entities": entities
        }

        try:
            result = self.db.execute(
                text("INSERT INTO silver.processed_data (source, classification_method, processed_payload) VALUES (:source, :method, :payload) RETURNING id"),
                {"source": source, "method": classification_method, "payload": json.dumps(silver_payload)}
            )
            silver_id = result.scalar()
            self.db.commit()
            print(f"  💾 Saved processed mapping to Silver layer (ID: {silver_id})")
            return silver_id
        except Exception as e:
            print(f"  ⚠️ Error saving to Silver layer: {e}")
            self.db.rollback()
            return None

    def get_from_silver(self, silver_id: int) -> Dict[str, Any]:
        """Read a payload out of the Silver layer"""
        result = self.db.execute(
            text("SELECT processed_payload FROM silver.processed_data WHERE id = :id"),
            {"id": silver_id}
        )
        row = result.fetchone()
        if row:
            return row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return None

    def build_gold_from_silver(self, silver_payload: Dict[str, Any]) -> tuple:
        """Insert data into Silver entity tables (dim_*/fact_*) by reading from Silver processed JSON payload."""
        if not silver_payload or "entities" not in silver_payload:
            return 0, []
            
        entities = silver_payload["entities"]
        metadata = silver_payload.get("metadata", {})
        source = metadata.get("source", "unknown")
        
        entity_to_table = {
            "accounts": "silver.dim_account",
            "contacts": "silver.dim_contact",
            "deals": "silver.fact_deals",
            "interactions": "silver.fact_interactions",
            "insights": "silver.fact_insights"
        }
        
        records_processed = 0
        tables_updated = []

        # Process dimensions first so account_ids exist before fact inserts need them
        dim_keys = [k for k in entities if entity_to_table.get(k, "").split(".")[-1].startswith("dim_")]
        fact_keys = [k for k in entities if k not in dim_keys]
        
        for entity_name in dim_keys + fact_keys:
            records = entities[entity_name]
            if not records:
                continue
                
            table_name = entity_to_table.get(entity_name, entity_name)
            
            count = self.insert_classified_data(table_name, records, source=source)
            if count > 0:
                records_processed += count
                if table_name not in tables_updated:
                    tables_updated.append(table_name)
                    
        return records_processed, tables_updated

    def _create_table(self, table_name: str, columns_def: Dict[str, str], is_dimension: bool) -> bool:
        """
        Create a single table from canonical schema definition.
        
        Returns:
            True if created, False if already exists
        """
        # Check if already exists in silver schema
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.db.bind, schema=SILVER_SCHEMA)
        full_name = f"{SILVER_SCHEMA}.{table_name}"
        if full_name in self.metadata.tables:
            return False

        columns = []
        columns.append("id SERIAL PRIMARY KEY")

        for col_name, col_type in columns_def.items():
            if is_dimension and col_name in ("name", "account_name") and table_name != "dim_contact":
                columns.append(f'"{col_name}" {col_type} UNIQUE')
            else:
                columns.append(f'"{col_name}" {col_type}')

        columns.append("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        columns.append("updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        if table_name == "dim_contact":
            columns.append('UNIQUE ("contact_name", "account_name")')

        sql = f"""
        CREATE TABLE IF NOT EXISTS silver.{table_name} (
            {', '.join(columns)}
        )
        """

        try:
            self.db.execute(text(sql))
            self.db.commit()
            print(f"  ✅ Created: silver.{table_name}")
            return True
        except Exception as e:
            print(f"  ❌ Error creating silver.{table_name}: {e}")
            self.db.rollback()
            return False
    
    def insert_classified_data(self, table_name: str, records: List[Dict[str, Any]], source: str = None) -> int:
        """
        Insert AI-classified data into a canonical table.
        
        SMART LOGIC:
        - Dimensions (dim_*): UPSERT on 'name' field (deduplicates)
        - Facts (fact_*): Always INSERT (each event is unique)
        
        Args:
            table_name: Name of the target table
            records: List of records (field names must match table columns)
            source: Data source identifier
        
        Returns:
            Number of records inserted/updated
        """
        if not records:
            return 0
        
        # Ensure table_name is silver-prefixed
        full_table = silver_prefixed(table_name)
        bare_name = full_table.split(".", 1)[-1]  # dim_account, fact_deals, etc.

        # Refresh metadata for silver schema
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.db.bind, schema=SILVER_SCHEMA)

        if full_table not in self.metadata.tables:
            print(f"❌ Table {full_table} does not exist")
            return 0

        table = self.metadata.tables[full_table]
        excluded_cols = ['id', 'created_at', 'updated_at']
        column_names = [col.name for col in table.columns if col.name not in excluded_cols]

        is_dimension = bare_name.startswith('dim_')
        processed = 0
        
        for record in records:
            # Add source if provided
            if source and "source" in column_names and "source" not in record:
                record["source"] = source
            
            # Filter to valid columns, convert values to strings
            filtered = {}
            for k, v in record.items():
                if k in column_names:
                    # Robust preservation: skip None and empty strings so they don't overwrite via COALESCE
                    if v is None or v == "":
                        continue
                        
                    if isinstance(v, (list, dict)):
                        filtered[k] = json.dumps(v)
                    elif isinstance(v, bool):
                        filtered[k] = str(v).lower()
                    else:
                        str_v = str(v).strip()
                        if k == "sentiment":
                            filtered[k] = str_v.lower()
                        else:
                            filtered[k] = str_v            
            if not filtered:
                print(f"⚠️ No matching columns for {full_table}. Expected: {column_names}, Got: {list(record.keys())}")
                continue

            # Clean deal_value: strip currency symbols and commas so gold SQL casts work
            if "deal_value" in filtered and filtered["deal_value"]:
                dv = str(filtered["deal_value"]).replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()
                filtered["deal_value"] = dv

            # --- Identity resolution: resolve account_id for fact tables ---
            if not is_dimension and "account_name" in filtered:
                acct_id = self.resolve_account_id(filtered["account_name"], source=source)
                if acct_id and "account_id" in column_names:
                    filtered["account_id"] = str(acct_id)

            # --- dim_contact fallback: generate a name before validation runs ---
            if bare_name == "dim_contact" and not filtered.get("contact_name"):
                if filtered.get("account_name"):
                    print(f"  ℹ️ Mapping to general contact for account: {filtered['account_name']}")
                    filtered["contact_name"] = f"{filtered['account_name']} (General)"

            # --- Data validation: skip and log invalid records ---
            is_valid, val_errors = validate_record(full_table, filtered)
            if not is_valid:
                print(f"  ⚠️ Validation failed for {full_table}: {val_errors}")
                self._log_quality_issue(full_table, val_errors, record)
                continue

            try:
                if is_dimension:
                    id_col = "account_name" if bare_name == "dim_account" else "contact_name"
                    
                    if id_col not in filtered or not filtered[id_col]:
                        print(f"  ⚠️ Skipping record for {full_table}: Missing primary identifier '{id_col}'")
                        continue

                    col_str = ', '.join([f'"{k}"' for k in filtered.keys()])
                    placeholders = ', '.join([f":{k}" for k in filtered.keys()])
                    update_fields = [k for k in filtered.keys() if k != id_col]
                    update_str = ', '.join([f'"{k}" = EXCLUDED."{k}"' for k in update_fields])

                    if bare_name == "dim_contact":
                        conflict_target = '("contact_name", "account_name")'
                    else:
                        conflict_target = f'("{id_col}")'

                    # If no fields to update (only name was provided), just do a "NOTHING" or update timestamp
                    if not update_str:
                        sql = f"""
                        INSERT INTO {full_table} ({col_str})
                        VALUES ({placeholders})
                        ON CONFLICT {conflict_target}
                        DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                        """
                    else:
                        # IDENTITY-BASED MERGING: Use COALESCE to preserve existing values if new ones are NULL
                        safe_update_str = ', '.join([f'"{k}" = COALESCE(EXCLUDED.""{k}"", {full_table}.""{k}"")' for k in update_fields])
                        sql = f"""
                        INSERT INTO {full_table} ({col_str})
                        VALUES ({placeholders})
                        ON CONFLICT {conflict_target}
                        DO UPDATE SET {safe_update_str}, updated_at = CURRENT_TIMESTAMP
                        """
                    sql = sql.replace('""', '"')
                    self.db.execute(text(sql), filtered)
                    processed += 1

                    # Populate source map for dim_account upserts
                    if bare_name == "dim_account" and source:
                        acct_name = filtered.get("account_name")
                        if acct_name:
                            row = self.db.execute(
                                text("SELECT id FROM silver.dim_account WHERE account_name = :name LIMIT 1"),
                                {"name": acct_name}
                            ).fetchone()
                            if row:
                                self._upsert_account_source_map(row[0], source, acct_name)

                elif bare_name == "fact_deals":
                    deal_name = filtered.get("deal_name", "")
                    account_name = filtered.get("account_name", "")
                    if deal_name and account_name:
                        exists_r = self.db.execute(text(
                            "SELECT id FROM silver.fact_deals WHERE deal_name = :dn AND account_name = :an LIMIT 1"
                        ), {"dn": deal_name, "an": account_name})
                        if exists_r.fetchone():
                            update_fields = [k for k in filtered.keys() if k not in ("deal_name", "account_name")]
                            if update_fields:
                                update_str = ', '.join([f'"{k}" = COALESCE(:{k}, "{k}")' for k in update_fields])
                                self.db.execute(text(
                                    f'UPDATE silver.fact_deals SET {update_str}, updated_at = CURRENT_TIMESTAMP '
                                    f'WHERE deal_name = :deal_name AND account_name = :account_name'
                                ), filtered)
                            processed += 1
                            continue
                    col_str = ', '.join([f'"{k}"' for k in filtered.keys()])
                    placeholders = ', '.join([f":{k}" for k in filtered.keys()])
                    sql = f'INSERT INTO {full_table} ({col_str}) VALUES ({placeholders})'
                    self.db.execute(text(sql), filtered)
                    processed += 1

                else:
                    col_str = ', '.join([f'"{k}"' for k in filtered.keys()])
                    placeholders = ', '.join([f":{k}" for k in filtered.keys()])
                    sql = f'INSERT INTO {full_table} ({col_str}) VALUES ({placeholders})'
                    self.db.execute(text(sql), filtered)
                    processed += 1

            except Exception as e:
                print(f"⚠️ Error upserting into {full_table}: {e}")
                self.db.rollback()

        self.db.commit()
        if processed > 0:
            action = "upserted" if is_dimension else "inserted"
            print(f"  ✅ {full_table}: {processed} record(s) {action}")
        return processed
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get current schema information"""
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.db.bind, schema=SILVER_SCHEMA)

        dimensions = []
        fact_tables = []

        for full_name, table in self.metadata.tables.items():
            # full_name is 'silver.dim_account' etc.
            bare_name = full_name.split(".", 1)[-1]
            table_info = {
                "name": full_name,
                "columns": [col.name for col in table.columns],
                "row_count": self._get_row_count(full_name)
            }

            if bare_name.startswith('dim_'):
                if bare_name in CANONICAL_SCHEMA.get("dimensions", {}):
                    table_info["description"] = CANONICAL_SCHEMA["dimensions"][bare_name]["description"]
                dimensions.append(table_info)
            elif bare_name.startswith('fact_'):
                if bare_name in CANONICAL_SCHEMA.get("facts", {}):
                    table_info["description"] = CANONICAL_SCHEMA["facts"][bare_name]["description"]
                fact_tables.append(table_info)

        return {
            "dimensions": dimensions,
            "fact_tables": fact_tables,
            "total_tables": len(dimensions) + len(fact_tables)
        }
    
    def _get_row_count(self, table_name: str) -> int:
        """Get row count for a table"""
        try:
            result = self.db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            return result.scalar()
        except Exception:
            return 0
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists in silver schema"""
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.db.bind, schema=SILVER_SCHEMA)
        return silver_prefixed(table_name) in self.metadata.tables
