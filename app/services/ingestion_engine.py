import json
import concurrent.futures
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.services.data_mapper import DataMapper
from app.services.schema_evolution import SchemaEvolutionEngine
from app.services.schema_manager import SchemaManager
from app.services.ai_analyzer import AIDataClassifier
from app.services.gold_layer import GoldLayerBuilder
from app.services.vector_store import VectorStoreService

class IngestionEngine:
    """
    Orchestrates the entire ingestion pipeline:
    1. Deterministic Classification (DataMapper)
    2. Optional AI fallback (AIClassifier)
    3. Schema Evolution (EvolutionEngine)
    4. Data Enrichment (Merging unmapped fields)
    5. Storage (SchemaManager)
    """

    def __init__(self, db: Session):
        self.db = db
        self.data_mapper = DataMapper()
        self.ai_classifier = AIDataClassifier()
        self.schema_manager = SchemaManager(db)
        self.evolution_engine = SchemaEvolutionEngine(db)
        self.vector_store = VectorStoreService()

    def process(self, data: List[Dict[str, Any]], source: str, data_type: Optional[str] = None, pre_classification: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process a batch of records through the pipeline.
        If pre_classification is provided (e.g. from transcript NLP), it is used
        directly instead of re-classifying the data.
        """
        # Step 1: Detect Source
        source_type = self.data_mapper.detect_source_type(source)
        if not data_type:
            data_type = self.ai_classifier.detect_data_type(data)
        
        # Step 2: Use pre-built classification or run deterministic mapping
        unmapped_fields = []
        if pre_classification and pre_classification.get("classifications"):
            classification = pre_classification
            method = pre_classification.get("method", "deterministic")
        else:
            classification, unmapped_fields = self.data_mapper.classify(data, source, db=self.db)
            method = "deterministic"

            # Step 3: AI Fallback if deterministic failed completely
            if not classification or not classification.get("classifications"):
                print(f"⚠️ Deterministic mapping failed, using AI fallback for {source}")
                classification = self.ai_classifier.classify_data(data, source)
                unmapped_fields = []
                method = "ai_fallback"

        # Step 4: Handle Unmapped Fields (Evolution)
        # POLICY: We ONLY evolve the schema for structured data (CSVs/CRM/ERP).
        # Unstructured transcripts often have too much AI-extracted 'noise' to evolve safely.
        evolution_report = {"columns_added": [], "fields_ignored": [], "new_mappings": {}}
        if unmapped_fields and data_type != "raw_transcript":
            print(f"🔍 Found {len(unmapped_fields)} unmapped field(s), checking with Evolution Engine...")
            evolution_report = self.evolution_engine.handle_unmapped_fields(unmapped_fields)
            
            # Step 5: High-Performance Data Enrichment
            if evolution_report["new_mappings"]:
                self._enrich_classification(classification, evolution_report["new_mappings"], data, source_type)

        # Step 6: Save to Silver Layer (JSON Audit Trail)
        silver_id = self.schema_manager.save_to_silver(source, method, classification)
        
        # Step 7: Populate entity tables (dim_ / fact_) from Silver Layer
        # This takes the cleaned, normalized data from the Silver JSON audit trail
        # and upserts/inserts it into the final entity tables.
        silver_payload = self.schema_manager.get_from_silver(silver_id)
        records_processed, tables_updated = self.schema_manager.build_gold_from_silver(silver_payload)
        print(f"  🏁 Entity tables updated: {records_processed} records into {tables_updated}")

        # Step 7b: Vector indexing — parallel with Gold refresh, only for unstructured docs
        # CSV/XLSX go purely through the Silver SQL path, no vector needed.
        vector_future = None
        if data_type == "raw_transcript" and self.vector_store.is_available():
            raw_text_records = self._extract_raw_texts(data)
            fallback_account = self._extract_account_name(data, classification)
            if raw_text_records:
                # Fill in any missing account_name with the GPT-resolved one
                for r in raw_text_records:
                    if not r["account_name"] and fallback_account:
                        r["account_name"] = fallback_account
                    if not r["filename"]:
                        r["filename"] = source
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                vector_future = executor.submit(
                    self._index_texts_in_vector_store,
                    raw_text_records, source
                )

        # Step 8: Build Gold from Silver
        gold = GoldLayerBuilder(self.db)
        gold.refresh_all()

        # Step 9: Invalidate schema cache so NL queries see latest columns
        from app.services.schema_introspector import invalidate_schema_cache
        invalidate_schema_cache()

        # Wait for vector indexing to finish (non-blocking to Gold, but we log the result)
        if vector_future is not None:
            try:
                chunks_indexed = vector_future.result(timeout=60)
                print(f"  📌 Vector store: {chunks_indexed} chunk(s) indexed")
            except Exception as e:
                print(f"  ⚠️ Vector indexing failed (non-fatal): {e}")

        return {
            "silver_id": silver_id,
            "method": method,
            "report": evolution_report,
            "table_count": len(tables_updated),
            "record_count": records_processed
        }

    def _extract_raw_texts(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Pull raw transcript strings and their associated metadata from data records.
        Returns list of dicts with keys: text, filename, account_name.
        """
        results = []
        for rec in data:
            text = rec.get("_raw_text") or rec.get("raw_transcript") or rec.get("transcript") or rec.get("content_text")
            if text and isinstance(text, str) and len(text.strip()) >= 50:
                results.append({
                    "text": text.strip(),
                    "filename": rec.get("_filename") or "",
                    "account_name": rec.get("_account_context") or rec.get("account_name") or "",
                })
        return results

    def _extract_account_name(self, data: List[Dict[str, Any]], classification: Dict) -> Optional[str]:
        """Best-effort account name extraction for vector metadata."""
        # Try the classification output first (most reliable — GPT-extracted)
        for item in classification.get("classifications", []):
            for rec in item.get("records", []):
                name = rec.get("account_name")
                if name and isinstance(name, str) and len(name.strip()) > 1:
                    return name.strip()
        # Fall back to raw data
        for rec in data:
            name = rec.get("account_name") or rec.get("company")
            if name and isinstance(name, str) and len(name.strip()) > 1:
                return name.strip()
        return None

    def _index_texts_in_vector_store(
        self, text_records: List[Dict[str, Any]], source: str
    ) -> int:
        """Embed and upsert all raw text records into Pinecone. Returns total chunks indexed."""
        total = 0
        for rec in text_records:
            count = self.vector_store.index_document(
                raw_text=rec["text"],
                filename=rec["filename"] or source,
                account_name=rec["account_name"] or None,
                source=source,
            )
            total += count
        return total

    def _enrich_classification(self, classification: Dict, new_mappings: Dict, raw_data: List[Dict], source_type: str):
        """
        Merges AI-discovered fields into existing classification entries.
        Ensures identity consistency across merges.
        """
        for table_name, field_map in new_mappings.items():
            bare_table = table_name.split(".")[-1]
            
            # Find destination entry
            entry = None
            for item in classification.get("classifications", []):
                if item["table"] in [bare_table, table_name]:
                    entry = item
                    break
            
            if entry:
                # MERGE into existing records
                print(f"  🎨 Enrichment: Merging newly discovered fields into existing {bare_table} records")
                for i, record in enumerate(entry["records"]):
                    source_record = raw_data[min(i, len(raw_data) - 1)]
                    for can_col, src_fld in field_map.items():
                        if src_fld in source_record:
                            record[can_col] = str(source_record[src_fld])
                    
                    # SAFETY: Don't let identity be lost
                    if bare_table == "dim_contact":
                        self._ensure_contact_identity(record, source_record, source_type)
            else:
                # CREATE new entry
                print(f"  🎨 Enrichment: Creating new entry for {bare_table}")
                new_records = []
                known_map = self.data_mapper.mappings.get(source_type, {}).get(bare_table, {}) if source_type else {}
                
                for source_record in raw_data:
                    mapped = {}
                    # Pull contextual identifiers (account_name, contact_name)
                    for can_col, src_fld in known_map.items():
                        if src_fld in source_record:
                            mapped[can_col] = str(source_record[src_fld])
                    
                    # Fallback robust identity
                    if bare_table == "dim_contact":
                        self._ensure_contact_identity(mapped, source_record, source_type)
                    
                    # Ensure account_name context is preserved for fact tables
                    if not mapped.get("account_name"):
                        # Try to find an account name from other records in this batch
                        for c in classification.get("classifications", []):
                            for r in c.get("records", []):
                                if r.get("account_name"):
                                    mapped["account_name"] = r["account_name"]
                                    break
                            if mapped.get("account_name"): break
                    
                    # Add discovered fields
                    for can_col, src_fld in field_map.items():
                        if src_fld in source_record:
                            mapped[can_col] = str(source_record[src_fld])
                    
                    if mapped:
                        new_records.append(mapped)
                
                if new_records:
                    classification.setdefault("classifications", []).append({
                        "table": bare_table,
                        "records": new_records
                    })

    def _ensure_contact_identity(self, record: Dict, source_record: Dict, source_type: str):
        """Ensures dim_contact records have an identity field."""
        if not record.get("contact_name"):
            for alt in ["contact_name", "name", "person_name", "employee_name", "contact"]:
                if alt in source_record:
                    record["contact_name"] = str(source_record[alt])
                    return
            
            # Final fallback: Use account_name if available so it doesn't drop
            if record.get("account_name"):
                record["contact_name"] = f"{record['account_name']} (General)"
