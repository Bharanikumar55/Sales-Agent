"""EvoBI Live Catalog Builder

Transforms raw database introspection from `schema_introspector.py` into
a rich, structured `EvoBICatalog` containing entities, dimensions, measures,
and join relationships.
"""
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.services.schema_introspector import (
    introspect_schema,
    invalidate_schema_cache,
)
from app.services.semantic.models import (
    SemanticEntity,
    SemanticDimension,
    SemanticMeasure,
    SemanticRelationship,
    EvoBICatalog,
)

# -----------------------------------------------------------------------------
# Enterprise & ThoughtFocus Business Semantic Overrides
# Known business metrics, dimensions, constraints, and descriptions
# -----------------------------------------------------------------------------

BUSINESS_ENTITY_DESCRIPTIONS = {
    # Silver layer entities
    "dim_account": "Client companies, organizations, and accounts profile catalog.",
    "dim_contact": "Key stakeholder contacts, buyers, and executives.",
    "fact_deals": "Sales deals, opportunity pipeline, and ThoughtFocus commercial transactions.",
    "fact_interactions": "Client touchpoints, meetings, call transcripts, and communication logs.",
    "fact_insights": "AI-extracted signals, competitive intelligence, and buying indicators.",
    "account_source_map": "Identity mapping for multi-source account reconciliation.",
    "data_quality_issues": "Rejected or malformed records log for data quality audit.",
    # Gold layer marts
    "revenue_summary": "Pre-aggregated revenue, won value, and pipeline value segmented by account and TF dimensions.",
    "top_customers": "Ranked accounts by total commercial deal value and active engagement.",
    "pipeline_health": "Pipeline stage distribution and velocity across ThoughtFocus P0-P10 stages.",
    "account_360": "Unified 360-degree overview of account revenue, contacts, meetings, and sentiment.",
    "activity_summary": "Summary of meetings, calls, and recent interaction touchpoints per account.",
    "deals_closing_soon": "Upcoming deal closures with target close dates and assigned sales reps.",
    "at_risk_accounts": "Accounts with open deals but no recent contact, highlighting churn/slippage risk.",
    "salesperson_performance": "Commercial quota attainment and deal generation per sales representative.",
    "vertical_revenue": "Revenue and deal pipeline broken down by industry vertical.",
    "ai_influence_summary": "Comparative analytics for AI-influenced deals vs standard commercial deals.",
    "win_loss_analysis": "Win rate and conversion rates by vertical, salesperson, and market segment.",
    "deal_velocity": "Average days in stage and cycle speed through the opportunity funnel.",
    "geography_mix": "Revenue distribution across Onshore vs Offshore delivery models.",
    "lead_source_effectiveness": "ROI and win conversion rates across referral, inbound, and outbound channels.",
    "stale_deals": "Opportunities stuck in current stage without recent activity.",
}

# Explicit business definitions for known metrics (measures)
BUSINESS_MEASURES = {
    # fact_deals
    ("fact_deals", "deal_value"): {
        "name": "deal_value",
        "default_aggregation": "SUM",
        "description": "Total monetary deal value in USD.",
        "data_type": "NUMERIC",
    },
    ("fact_deals", "probability"): {
        "name": "probability",
        "default_aggregation": "AVG",
        "description": "Deal win probability percentage (0-100%).",
        "data_type": "NUMERIC",
    },
    # dim_account
    ("dim_account", "annual_revenue"): {
        "name": "annual_revenue",
        "default_aggregation": "SUM",
        "description": "Annual reported revenue of the client company in USD.",
        "data_type": "NUMERIC",
    },
    ("dim_account", "employee_count"): {
        "name": "employee_count",
        "default_aggregation": "SUM",
        "description": "Total headcount of the account organization.",
        "data_type": "INTEGER",
    },
    # Gold marts - revenue_summary
    ("revenue_summary", "total_deal_value"): {
        "name": "total_deal_value",
        "default_aggregation": "SUM",
        "description": "Total deal value across all recorded stages.",
        "data_type": "NUMERIC",
    },
    ("revenue_summary", "won_value"): {
        "name": "won_value",
        "default_aggregation": "SUM",
        "description": "Total value of Closed Won contracts.",
        "data_type": "NUMERIC",
    },
    ("revenue_summary", "pipeline_value"): {
        "name": "pipeline_value",
        "default_aggregation": "SUM",
        "description": "Active unclosed opportunity pipeline value.",
        "data_type": "NUMERIC",
    },
    ("revenue_summary", "ai_influenced_value"): {
        "name": "ai_influenced_value",
        "default_aggregation": "SUM",
        "description": "Total value of deals driven or influenced by AI capabilities.",
        "data_type": "NUMERIC",
    },
    ("revenue_summary", "deal_count"): {
        "name": "deal_count",
        "default_aggregation": "SUM",
        "description": "Count of total deals.",
        "data_type": "INTEGER",
    },
    ("revenue_summary", "won_count"): {
        "name": "won_count",
        "default_aggregation": "SUM",
        "description": "Count of Closed Won deals.",
        "data_type": "INTEGER",
    },
    ("revenue_summary", "avg_deal_size"): {
        "name": "avg_deal_size",
        "default_aggregation": "AVG",
        "description": "Average deal size across relevant opportunities.",
        "data_type": "NUMERIC",
    },
}

# Explicit business definitions for known dimensions
BUSINESS_DIMENSIONS = {
    ("fact_deals", "vertical"): {
        "description": "ThoughtFocus industry vertical domain.",
        "allowed_values": [
            "Mortgage & Lending",
            "Banking & Insurance",
            "Capital Market",
            "Higher Education",
            "Technology",
            "Payments",
        ],
    },
    ("fact_deals", "horizontal"): {
        "description": "ThoughtFocus service line / delivery capability.",
        "allowed_values": [
            "AI & Data",
            "Application Engineering",
            "Digital Operations",
        ],
    },
    ("fact_deals", "engagement_model"): {
        "description": "Contractual commercial delivery model.",
        "allowed_values": ["T&M", "Fixed", "Retainers", "Outcome-based"],
    },
    ("fact_deals", "opportunity_stage"): {
        "description": "Granular pipeline opportunity stage code.",
        "allowed_values": [
            "P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"
        ],
    },
    ("fact_deals", "deal_stage"): {
        "description": "High-level sales qualification stage.",
        "allowed_values": [
            "Discovery",
            "Proposal",
            "Negotiation",
            "Closed Won",
            "Closed Lost",
        ],
    },
    ("fact_deals", "ai_influenced"): {
        "description": "Flag indicating if AI capability is incorporated.",
        "allowed_values": ["yes", "no"],
    },
    ("fact_deals", "business_type"): {
        "description": "Customer commercial relationship classification.",
        "allowed_values": ["New Business", "Existing Customer", "Renewal"],
    },
    ("fact_deals", "salesperson"): {
        "description": "Account executive or sales representative assigned to the deal.",
    },
    ("fact_deals", "close_date"): {
        "description": "Projected or actual closing date of the opportunity.",
        "time_grains": ["day", "week", "month", "quarter", "year"],
    },
    ("dim_account", "geography"): {
        "description": "Delivery model geography classification.",
        "allowed_values": ["Onshore", "Offshore", "Both"],
    },
    ("dim_account", "account_name"): {
        "description": "Canonical legal name of the client organization.",
    },
    ("dim_account", "industry"): {
        "description": "Industry sector of the account.",
    },
    ("fact_interactions", "interaction_date"): {
        "description": "Date when client interaction occurred.",
        "time_grains": ["day", "week", "month", "quarter", "year"],
    },
    ("fact_interactions", "sentiment"): {
        "description": "Client interaction sentiment assessment.",
        "allowed_values": ["positive", "neutral", "negative"],
    },
}

# Standard time grains for date/timestamp fields
DEFAULT_TIME_GRAINS = ["day", "week", "month", "quarter", "year"]


class LiveCatalogBuilder:
    """Builds and maintains the live EvoBI Semantic Catalog.

    Reuses runtime schema information from `schema_introspector.py` and enriches
    it with enterprise semantic definitions (measures, dimensions, grains,
    and relationships).
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def build_catalog(
        self,
        target_schemas: List[str] = None,
        force_refresh: bool = False,
        raw_introspection_override: Optional[Dict[str, Any]] = None,
    ) -> EvoBICatalog:
        """Construct an EvoBICatalog instance from live PostgreSQL catalog or provided introspection.

        Args:
            target_schemas: Schemas to introspect (default: ['silver', 'gold'])
            force_refresh: If True, invalidates any existing schema cache first
            raw_introspection_override: Optional pre-computed introspection dict (for offline testing)

        Returns:
            EvoBICatalog instance with registered entities, dimensions, measures, and relationships
        """
        if target_schemas is None:
            target_schemas = ["silver", "gold"]

        if force_refresh:
            invalidate_schema_cache()

        # Step 1: Introspect physical schema
        if raw_introspection_override is not None:
            raw_schema = raw_introspection_override
        elif self.db is not None:
            raw_schema = introspect_schema(self.db, target_schemas=target_schemas)
        else:
            raise ValueError("LiveCatalogBuilder requires an active DB session or raw_introspection_override.")

        catalog = EvoBICatalog()

        # Step 2: Convert physical tables to SemanticEntities & inspect attributes
        for schema_name, tables in raw_schema.items():
            for table_name, table_info in tables.items():
                entity_name = table_name  # e.g., 'fact_deals', 'dim_account', 'revenue_summary'
                physical_table = f"{schema_name}.{table_name}"

                # Determine primary key (convention: 'id' column if present)
                column_list = table_info.get("columns", [])
                col_names = [c["name"] for c in column_list]
                pk_col = "id" if "id" in col_names else (col_names[0] if col_names else None)

                # Entity description
                description = (
                    BUSINESS_ENTITY_DESCRIPTIONS.get(table_name)
                    or table_info.get("description")
                    or f"{schema_name.capitalize()} layer entity for {table_name}"
                )

                entity = SemanticEntity(
                    name=entity_name,
                    physical_table=physical_table,
                    schema_name=schema_name,
                    primary_key=pk_col,
                    description=description,
                )
                catalog.entities[entity_name] = entity

                # Step 3: Classify columns into Measures or Dimensions
                self._process_columns(entity_name, column_list, catalog)

                # Step 4: Extract physical foreign keys into SemanticRelationships
                for fk in table_info.get("foreign_keys", []):
                    ref_table_full = fk.get("references_table", "")  # e.g. 'silver.dim_account'
                    ref_entity = ref_table_full.split(".")[-1]
                    rel = SemanticRelationship(
                        from_entity=entity_name,
                        to_entity=ref_entity,
                        from_column=fk.get("column"),
                        to_column=fk.get("references_column"),
                        cardinality="N:1",
                    )
                    # Deduplicate before appending
                    if not any(
                        r.from_entity == rel.from_entity
                        and r.to_entity == rel.to_entity
                        and r.from_column == rel.from_column
                        for r in catalog.relationships
                    ):
                        catalog.relationships.append(rel)

        # Step 5: Add logical relationships where physical FK may not exist in database DDL
        self._inject_logical_relationships(catalog)

        return catalog

    def _process_columns(
        self,
        entity_name: str,
        column_list: List[Dict[str, Any]],
        catalog: EvoBICatalog,
    ) -> None:
        """Classify columns of an entity into SemanticMeasure or SemanticDimension."""
        for col in column_list:
            col_name = col["name"]
            data_type = col.get("type", "TEXT").upper()
            description = col.get("description")

            # Check explicit business measure definitions first
            override_key = (entity_name, col_name)
            if override_key in BUSINESS_MEASURES:
                m_conf = BUSINESS_MEASURES[override_key]
                measure = SemanticMeasure(
                    name=m_conf.get("name", col_name),
                    physical_column=col_name,
                    entity=entity_name,
                    data_type=m_conf.get("data_type", data_type),
                    default_aggregation=m_conf.get("default_aggregation", "SUM"),
                    description=m_conf.get("description", description),
                )
                catalog.measures[f"{entity_name}.{measure.name}"] = measure
                continue

            # Check explicit business dimension definitions
            if override_key in BUSINESS_DIMENSIONS:
                d_conf = BUSINESS_DIMENSIONS[override_key]
                dimension = SemanticDimension(
                    name=col_name,
                    physical_column=col_name,
                    entity=entity_name,
                    data_type=data_type,
                    description=d_conf.get("description", description),
                    time_grains=d_conf.get("time_grains"),
                    allowed_values=d_conf.get("allowed_values"),
                )
                catalog.dimensions[f"{entity_name}.{dimension.name}"] = dimension
                continue

            # Dynamic Heuristic Classification for un-overridden columns:
            if self._is_measure_candidate(col_name, data_type):
                agg = self._infer_default_aggregation(col_name)
                measure = SemanticMeasure(
                    name=col_name,
                    physical_column=col_name,
                    entity=entity_name,
                    data_type=data_type,
                    default_aggregation=agg,
                    description=description or f"Quantitative metric for {col_name}",
                )
                catalog.measures[f"{entity_name}.{measure.name}"] = measure
            else:
                time_grains = DEFAULT_TIME_GRAINS if self._is_temporal(col_name, data_type) else None
                dimension = SemanticDimension(
                    name=col_name,
                    physical_column=col_name,
                    entity=entity_name,
                    data_type=data_type,
                    description=description or f"Categorical attribute {col_name}",
                    time_grains=time_grains,
                )
                catalog.dimensions[f"{entity_name}.{dimension.name}"] = dimension

    def _is_measure_candidate(self, col_name: str, data_type: str) -> bool:
        """Determine if a column should be treated as a quantitative measure."""
        # Exclude IDs, keys, timestamps, metadata
        col_lower = col_name.lower()
        if col_lower == "id" or col_lower.endswith("_id"):
            return False
        if col_lower in ("created_at", "updated_at", "refreshed_at", "source_data", "source", "rank"):
            return False

        # Positive indicator: metric name patterns
        measure_suffixes = (
            "_value", "_count", "_size", "_amount", "_total", "_pct",
            "_rate", "_revenue", "_score", "_cost", "_price", "_margin", "_quantity"
        )
        if any(col_lower.endswith(sfx) for sfx in measure_suffixes) or col_lower.startswith(("total_", "avg_", "sum_")):
            return True

        # Numeric SQL data types (unless clearly an ID or code)
        numeric_types = ("NUMERIC", "INTEGER", "BIGINT", "DECIMAL", "REAL", "DOUBLE PRECISION", "FLOAT")
        if any(nt in data_type for nt in numeric_types):
            return True

        return False

    def _infer_default_aggregation(self, col_name: str) -> str:
        """Infer default aggregation (SUM vs AVG) from column name."""
        col_lower = col_name.lower()
        if col_lower.startswith("avg_") or any(s in col_lower for s in ("_rate", "_pct", "_ratio", "_score", "_average")):
            return "AVG"
        return "SUM"

    def _is_temporal(self, col_name: str, data_type: str) -> bool:
        """Determine if a column is a date or timestamp dimension."""
        col_lower = col_name.lower()
        if any(t in data_type for t in ("DATE", "TIMESTAMP", "TIME")):
            return True
        if col_lower.endswith(("_date", "_at", "_time")) and not col_lower.endswith("_count"):
            return True
        return False

    def _inject_logical_relationships(self, catalog: EvoBICatalog) -> None:
        """Ensure core Star Schema logical joins exist even if not declared as physical DB foreign keys."""
        # Canonical silver relationships
        logical_pairs = [
            ("fact_deals", "dim_account", "account_id", "id", "N:1"),
            ("fact_interactions", "dim_account", "account_id", "id", "N:1"),
            ("fact_insights", "dim_account", "account_id", "id", "N:1"),
            ("dim_contact", "dim_account", "account_name", "account_name", "N:1"),
        ]
        for src, tgt, src_col, tgt_col, card in logical_pairs:
            if src in catalog.entities and tgt in catalog.entities:
                # Add if not already present
                exists = any(
                    r.from_entity == src and r.to_entity == tgt and r.from_column == src_col
                    for r in catalog.relationships
                )
                if not exists:
                    catalog.relationships.append(
                        SemanticRelationship(
                            from_entity=src,
                            to_entity=tgt,
                            from_column=src_col,
                            to_column=tgt_col,
                            cardinality=card,
                        )
                    )
