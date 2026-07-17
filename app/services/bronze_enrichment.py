"""Bronze Enrichment Service - Extracts data from Bronze when Silver/Gold have no answer.

When a user query returns no results from Gold or Silver, this service:
  1. Searches bronze.raw_ingestion for relevant raw documents
  2. Sends the raw text through LLM extraction (TranscriptProcessor)
  3. Classifies the extracted data into Silver table records (AIDataClassifier)
  4. Inserts into Silver via SchemaManager (with full validation)
  5. Refreshes Gold so subsequent queries can use pre-aggregated data
"""
import json
import re
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.transcript_processor import TranscriptProcessor
from app.services.ai_analyzer import AIDataClassifier
from app.services.schema_manager import SchemaManager
from app.services.gold_layer import GoldLayerBuilder

logger = logging.getLogger(__name__)


class BronzeEnrichmentService:
    """
    Bridge between Bronze (raw) and Silver (normalised) layers.
    Triggered only when a query cannot be answered from existing Silver/Gold data.
    """

    def __init__(self, db: Session):
        self.db = db
        self.transcript_processor = TranscriptProcessor()
        self.ai_classifier = AIDataClassifier()
        self.schema_manager = SchemaManager(db)

    def enrich(self, question: str, account_context: str = None) -> int:
        """
        Find relevant Bronze records, extract structured data, and insert into Silver.

        Args:
            question:        The original user question (used for keyword extraction)
            account_context: Optional account name to focus the search

        Returns:
            Number of records successfully inserted into Silver
        """
        bronze_records = self._fetch_relevant_bronze(question, account_context)
        if not bronze_records:
            logger.info("Bronze enrichment: no relevant Bronze records found")
            return 0

        print(f"  🔍 Bronze enrichment: found {len(bronze_records)} candidate record(s)")

        total_enriched = 0
        for record in bronze_records:
            try:
                count = self._process_bronze_record(record)
                total_enriched += count
            except Exception as e:
                logger.warning("Bronze enrichment failed for record %s: %s", record.get("id"), e)

        if total_enriched > 0:
            print(f"  🔄 Bronze enrichment: inserted {total_enriched} record(s) into Silver, refreshing Gold...")
            try:
                GoldLayerBuilder(self.db).refresh_all()
            except Exception as e:
                logger.warning("Gold refresh after enrichment failed: %s", e)

        return total_enriched

    # ------------------------------------------------------------------
    # Bronze search
    # ------------------------------------------------------------------

    def _fetch_relevant_bronze(
        self, question: str, account_context: str = None
    ) -> List[Dict[str, Any]]:
        """Search bronze.raw_ingestion for records matching the query context."""
        keywords = self._extract_keywords(question, account_context)
        records: List[Dict[str, Any]] = []

        if keywords:
            for kw in keywords:
                try:
                    result = self.db.execute(
                        text("""
                            SELECT id, source, data_type, raw_payload, created_at
                            FROM bronze.raw_ingestion
                            WHERE raw_payload::text ILIKE :pattern
                            ORDER BY created_at DESC
                            LIMIT 3
                        """),
                        {"pattern": f"%{kw}%"},
                    )
                    for row in result.mappings():
                        records.append(dict(row))
                except Exception as e:
                    logger.warning("Bronze keyword search failed for '%s': %s", kw, e)

        if not records:
            try:
                result = self.db.execute(
                    text("""
                        SELECT id, source, data_type, raw_payload, created_at
                        FROM bronze.raw_ingestion
                        ORDER BY created_at DESC
                        LIMIT 2
                    """)
                )
                for row in result.mappings():
                    records.append(dict(row))
            except Exception as e:
                logger.warning("Bronze recent-records fetch failed: %s", e)

        seen_ids: set = set()
        unique: List[Dict[str, Any]] = []
        for rec in records:
            rid = rec.get("id")
            if rid not in seen_ids:
                seen_ids.add(rid)
                unique.append(rec)

        return unique[:3]

    @staticmethod
    def _extract_keywords(question: str, account_context: str = None) -> List[str]:
        """Pull likely entity names from the question and account context."""
        keywords: List[str] = []

        if account_context:
            keywords.append(account_context)

        stop_words = {
            "What", "When", "Where", "Who", "How", "Which",
            "Show", "Tell", "Give", "List", "Find", "Get",
            "The", "And", "For", "Are", "Can", "Does", "Did",
            "Have", "Has", "Will", "Any", "All", "Our", "Their",
            "About", "From", "With", "This", "That", "Some",
        }
        words = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", question)
        for w in words:
            if w not in stop_words and len(w) >= 3 and w not in keywords:
                keywords.append(w)

        return keywords

    # ------------------------------------------------------------------
    # Per-record processing
    # ------------------------------------------------------------------

    def _process_bronze_record(self, record: Dict[str, Any]) -> int:
        """Extract, classify, and insert one Bronze record into Silver."""
        payload = record.get("raw_payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return 0

        source = record.get("source", "bronze_enrichment")

        raw_text = (
            payload.get("raw_transcript")
            or payload.get("transcript")
            or payload.get("content_text")
            or ""
        )
        if not raw_text and isinstance(payload, dict):
            raw_text = json.dumps(payload)

        if not raw_text or len(raw_text.strip()) < 50:
            return 0

        processed = self.transcript_processor.process_raw_transcript(raw_text)

        classification = self.ai_classifier.classify_transcript_data(
            [processed], source_name=f"{source}_enriched"
        )

        if not classification or not classification.get("classifications"):
            return 0

        entity_to_table = {
            "dim_account": "silver.dim_account",
            "dim_contact": "silver.dim_contact",
            "fact_deals": "silver.fact_deals",
            "fact_interactions": "silver.fact_interactions",
            "fact_insights": "silver.fact_insights",
        }

        total = 0
        dim_items = [
            c for c in classification["classifications"]
            if c.get("table", "").startswith("dim_")
        ]
        fact_items = [
            c for c in classification["classifications"]
            if not c.get("table", "").startswith("dim_")
        ]

        for item in dim_items + fact_items:
            table = item.get("table", "")
            recs = item.get("records", [])
            full_table = entity_to_table.get(table, f"silver.{table}")
            if recs:
                count = self.schema_manager.insert_classified_data(
                    full_table, recs, source=f"{source}_enriched"
                )
                total += count

        if total > 0:
            print(f"  ✅ Bronze enrichment: {total} record(s) written to Silver from Bronze #{record.get('id')}")

        return total
