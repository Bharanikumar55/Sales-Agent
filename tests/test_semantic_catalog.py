"""Unit and Verification Test for EvoBI Semantic Catalog & LiveCatalogBuilder

Can be run via:
    python tests/test_semantic_catalog.py
"""
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.services.semantic.models import (
    SemanticEntity,
    SemanticDimension,
    SemanticMeasure,
    SemanticRelationship,
    EvoBICatalog,
)
from app.services.semantic.catalog_builder import LiveCatalogBuilder


def get_mock_introspection_data():
    """Provides a realistic snapshot of Silver and Gold schemas based on the repository DDLs."""
    return {
        "silver": {
            "dim_account": {
                "description": "Companies and client profiles",
                "row_count": 42,
                "columns": [
                    {"name": "id", "type": "INTEGER", "description": "Primary key"},
                    {"name": "account_name", "type": "TEXT", "description": "Company name"},
                    {"name": "industry", "type": "TEXT", "description": "Industry sector"},
                    {"name": "geography", "type": "TEXT", "description": "Onshore/Offshore"},
                    {"name": "annual_revenue", "type": "TEXT", "description": "Revenue"},
                    {"name": "employee_count", "type": "TEXT", "description": "Headcount"},
                    {"name": "website", "type": "TEXT", "description": "Website URL"},
                ],
                "foreign_keys": [],
            },
            "fact_deals": {
                "description": "Sales opportunities and commercial pipeline",
                "row_count": 150,
                "columns": [
                    {"name": "id", "type": "INTEGER", "description": "Primary key"},
                    {"name": "account_id", "type": "INTEGER", "description": "FK to dim_account"},
                    {"name": "deal_name", "type": "TEXT", "description": "Opportunity name"},
                    {"name": "account_name", "type": "TEXT", "description": "Account name"},
                    {"name": "deal_value", "type": "TEXT", "description": "Deal value in USD"},
                    {"name": "deal_stage", "type": "TEXT", "description": "Sales stage"},
                    {"name": "probability", "type": "TEXT", "description": "Win probability"},
                    {"name": "close_date", "type": "TEXT", "description": "Close date"},
                    {"name": "vertical", "type": "TEXT", "description": "Industry vertical"},
                    {"name": "horizontal", "type": "TEXT", "description": "Service horizontal"},
                    {"name": "engagement_model", "type": "TEXT", "description": "Contract model"},
                    {"name": "opportunity_stage", "type": "TEXT", "description": "P0-P10 stage"},
                    {"name": "ai_influenced", "type": "TEXT", "description": "AI flag"},
                    {"name": "salesperson", "type": "TEXT", "description": "Sales rep"},
                    {"name": "business_type", "type": "TEXT", "description": "New/Existing"},
                    {"name": "lead_source", "type": "TEXT", "description": "Lead channel"},
                ],
                "foreign_keys": [
                    {
                        "column": "account_id",
                        "references_table": "silver.dim_account",
                        "references_column": "id",
                    }
                ],
            },
        },
        "gold": {
            "revenue_summary": {
                "description": "Pre-aggregated revenue by account and vertical",
                "row_count": 35,
                "columns": [
                    {"name": "id", "type": "INTEGER", "description": "Primary key"},
                    {"name": "account_name", "type": "TEXT", "description": "Account"},
                    {"name": "vertical", "type": "TEXT", "description": "Vertical"},
                    {"name": "total_deal_value", "type": "NUMERIC", "description": "Total value"},
                    {"name": "won_value", "type": "NUMERIC", "description": "Won value"},
                    {"name": "pipeline_value", "type": "NUMERIC", "description": "Pipeline value"},
                    {"name": "deal_count", "type": "INTEGER", "description": "Deal count"},
                    {"name": "avg_deal_size", "type": "NUMERIC", "description": "Avg size"},
                ],
                "foreign_keys": [],
            }
        },
    }


def test_catalog_builder():
    print("==================================================================")
    print("Testing EvoBI LiveCatalogBuilder & Semantic Catalog Abstraction...")
    print("==================================================================")

    # Attempt to connect to live DB; if DB is offline, fallback to mock introspection
    db_session = None
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        db_session = SessionLocal()
        # Verify if connection is live
        db_session.execute(text("SELECT 1"))
        print(" Connected to live PostgreSQL database. Introspecting live catalog...")
        builder = LiveCatalogBuilder(db_session)
        catalog = builder.build_catalog(target_schemas=["silver", "gold"])
    except Exception as e:
        print(f" Live DB offline or unreachable ({e}). Using schema introspection snapshot...")
        builder = LiveCatalogBuilder()
        catalog = builder.build_catalog(
            raw_introspection_override=get_mock_introspection_data()
        )
    finally:
        if db_session:
            db_session.close()

    # 1. Assert Entities
    assert "fact_deals" in catalog.entities, "Entity fact_deals must exist"
    assert "dim_account" in catalog.entities, "Entity dim_account must exist"

    deals_entity = catalog.entities["fact_deals"]
    print(f"\n[Entity] {deals_entity.name}")
    print(f"  Physical Table: {deals_entity.physical_table}")
    print(f"  Layer: {deals_entity.schema_name}")
    print(f"  Primary Key: {deals_entity.primary_key}")
    print(f"  Description: {deals_entity.description}")

    # 2. Assert Measure: deal_value
    deal_value = catalog.find_measure("deal_value", "fact_deals")
    assert deal_value is not None, "deal_value must be recognized as a measure on fact_deals"
    assert deal_value.default_aggregation == "SUM", "deal_value default aggregation must be SUM"
    print(f"\n[Measure] {deal_value.entity}.{deal_value.name}")
    print(f"  Physical Column: {deal_value.physical_column}")
    print(f"  Default Aggregation: {deal_value.default_aggregation}")
    print(f"  Data Type: {deal_value.data_type}")
    print(f"  Description: {deal_value.description}")

    # 3. Assert Measure: probability
    prob = catalog.find_measure("probability", "fact_deals")
    assert prob is not None, "probability must be recognized as a measure on fact_deals"
    assert prob.default_aggregation == "AVG", "probability default aggregation must be AVG"
    print(f"\n[Measure] {prob.entity}.{prob.name}")
    print(f"  Default Aggregation: {prob.default_aggregation}")

    # 4. Assert Dimension: vertical
    vertical = catalog.find_dimension("vertical", "fact_deals")
    assert vertical is not None, "vertical must be recognized as a dimension on fact_deals"
    assert vertical.allowed_values is not None and len(vertical.allowed_values) > 0, "vertical should have allowed_values"
    print(f"\n[Dimension] {vertical.entity}.{vertical.name}")
    print(f"  Allowed Values: {vertical.allowed_values}")
    print(f"  Description: {vertical.description}")

    # 5. Assert Dimension: salesperson
    salesperson = catalog.find_dimension("salesperson", "fact_deals")
    assert salesperson is not None, "salesperson must be recognized as a dimension on fact_deals"
    print(f"\n[Dimension] {salesperson.entity}.{salesperson.name}")
    print(f"  Description: {salesperson.description}")

    # 6. Assert Dimension: close_date (temporal)
    close_date = catalog.find_dimension("close_date", "fact_deals")
    assert close_date is not None, "close_date must be recognized as a dimension on fact_deals"
    assert close_date.time_grains is not None and "quarter" in close_date.time_grains, "close_date should have time grains"
    print(f"\n[Temporal Dimension] {close_date.entity}.{close_date.name}")
    print(f"  Time Grains: {close_date.time_grains}")

    # 7. Assert Relationship: fact_deals -> dim_account
    relationships = catalog.get_relationships_for_entity("fact_deals")
    deals_to_account = [
        r for r in relationships
        if r.from_entity == "fact_deals" and r.to_entity == "dim_account"
    ]
    assert len(deals_to_account) > 0, "Relationship fact_deals -> dim_account must exist"
    rel = deals_to_account[0]
    print(f"\n[Relationship] {rel.from_entity}.{rel.from_column} -> {rel.to_entity}.{rel.to_column}")
    print(f"  Cardinality: {rel.cardinality}")

    # 8. Summary statistics
    summary = catalog.to_summary_dict()
    print("\n==================================================================")
    print("Catalog Summary Statistics:")
    print(f"  Total Entities:      {summary['total_entities']}")
    print(f"  Total Dimensions:    {summary['total_dimensions']}")
    print(f"  Total Measures:      {summary['total_measures']}")
    print(f"  Total Relationships: {summary['total_relationships']}")
    print("==================================================================")
    print("All tests passed successfully!")


if __name__ == "__main__":
    test_catalog_builder()
