"""Comprehensive Verification Test for EvoBI Enterprise Intermediate Representation (IR)

Tests construction, Pydantic validation, serialization, and structural consistency
across the 5 required analytical query patterns + validation edge cases.

Can be run via:
    python tests/test_semantic_ir.py
"""
import sys
from pathlib import Path
import json

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.services.semantic_ir.models import (
    SemanticQueryIR,
    IRMeasure,
    IRFilter,
    IROrderBy,
    IRTimeGrain,
)
from pydantic import ValidationError


def test_1_simple_aggregation():
    """Test 1: Simple aggregation
    User question: 'What is the total deal value?'
    """
    print("\n------------------------------------------------------------------")
    print("Test 1: Simple Aggregation")
    print("User Question: 'What is the total deal value?'")
    print("------------------------------------------------------------------")

    ir = SemanticQueryIR(
        entities=["fact_deals"],
        measures=[
            IRMeasure(name="deal_value", aggregation="SUM", alias="total_deal_value")
        ],
        dimensions=[],
        filters=[],
        group_by=[],
        order_by=[],
        limit=None,
    )

    # Validate with Pydantic
    assert ir.entities == ["fact_deals"]
    assert len(ir.measures) == 1
    assert ir.measures[0].name == "deal_value"
    assert ir.measures[0].aggregation == "SUM"
    assert ir.measures[0].alias == "total_deal_value"

    # Print JSON output
    print(ir.to_json())
    return ir


def test_2_grouped_query():
    """Test 2: Grouped query
    User question: 'What is the total deal value by salesperson?'
    """
    print("\n------------------------------------------------------------------")
    print("Test 2: Grouped Query")
    print("User Question: 'What is the total deal value by salesperson?'")
    print("------------------------------------------------------------------")

    ir = SemanticQueryIR(
        entities=["fact_deals"],
        dimensions=["salesperson"],
        measures=[
            IRMeasure(name="deal_value", aggregation="SUM", alias="total_deal_value")
        ],
        filters=[],
        group_by=["salesperson"],
        order_by=[],
        limit=None,
    )

    assert ir.dimensions == ["salesperson"]
    assert ir.group_by == ["salesperson"]
    assert ir.measures[0].aggregation == "SUM"

    print(ir.to_json())
    return ir


def test_3_filtered_query():
    """Test 3: Filtered query
    User question: 'What is the total deal value for Banking & Insurance?'
    """
    print("\n------------------------------------------------------------------")
    print("Test 3: Filtered Query")
    print("User Question: 'What is the total deal value for Banking & Insurance?'")
    print("------------------------------------------------------------------")

    ir = SemanticQueryIR(
        entities=["fact_deals"],
        dimensions=[],
        measures=[
            IRMeasure(name="deal_value", aggregation="SUM", alias="total_deal_value")
        ],
        filters=[
            IRFilter(field="vertical", operator="=", value="Banking & Insurance")
        ],
        group_by=[],
        order_by=[],
        limit=None,
    )

    assert len(ir.filters) == 1
    assert ir.filters[0].field == "vertical"
    assert ir.filters[0].operator == "="
    assert ir.filters[0].value == "Banking & Insurance"

    print(ir.to_json())
    return ir


def test_4_grouped_and_filtered_query():
    """Test 4: Grouped + filtered query
    User question: 'What is the total deal value for each salesperson in Banking & Insurance?'
    """
    print("\n------------------------------------------------------------------")
    print("Test 4: Grouped + Filtered Query")
    print("User Question: 'What is the total deal value for each salesperson in Banking & Insurance?'")
    print("------------------------------------------------------------------")

    ir = SemanticQueryIR(
        entities=["fact_deals"],
        dimensions=["salesperson"],
        measures=[
            IRMeasure(name="deal_value", aggregation="SUM", alias="total_deal_value")
        ],
        filters=[
            IRFilter(field="vertical", operator="=", value="Banking & Insurance")
        ],
        group_by=["salesperson"],
        order_by=[],
        limit=None,
    )

    assert ir.dimensions == ["salesperson"]
    assert ir.group_by == ["salesperson"]
    assert len(ir.filters) == 1
    assert ir.filters[0].value == "Banking & Insurance"

    print(ir.to_json())
    return ir


def test_5_ordered_query():
    """Test 5: Ordered query
    User question: 'Show the top 5 salespeople by total deal value.'
    """
    print("\n------------------------------------------------------------------")
    print("Test 5: Ordered Query (Top 5 Ranking)")
    print("User Question: 'Show the top 5 salespeople by total deal value.'")
    print("------------------------------------------------------------------")

    ir = SemanticQueryIR(
        entities=["fact_deals"],
        dimensions=["salesperson"],
        measures=[
            IRMeasure(name="deal_value", aggregation="SUM", alias="total_deal_value")
        ],
        filters=[],
        group_by=["salesperson"],
        order_by=[
            IROrderBy(field="total_deal_value", direction="DESC")
        ],
        limit=5,
    )

    assert ir.limit == 5
    assert len(ir.order_by) == 1
    assert ir.order_by[0].field == "total_deal_value"
    assert ir.order_by[0].direction == "DESC"

    print(ir.to_json())
    return ir


def test_6_temporal_grain_query():
    """Test 6: Query with optional temporal grain support
    User question: 'What is the monthly pipeline trend by close date?'
    """
    print("\n------------------------------------------------------------------")
    print("Test 6: Temporal Grain Support (Time-Series Analysis)")
    print("User Question: 'What is the monthly pipeline trend by close date?'")
    print("------------------------------------------------------------------")

    ir = SemanticQueryIR(
        entities=["fact_deals"],
        dimensions=["close_date"],
        measures=[
            IRMeasure(name="deal_value", aggregation="SUM", alias="monthly_deal_value")
        ],
        group_by=["close_date"],
        time_grain=IRTimeGrain(field="close_date", grain="month"),
        order_by=[IROrderBy(field="close_date", direction="ASC")],
        limit=12,
    )

    assert ir.time_grain is not None
    assert ir.time_grain.field == "close_date"
    assert ir.time_grain.grain == "month"

    print(ir.to_json())
    return ir


def test_7_validation_edge_cases():
    """Test 7: Verification of Pydantic validation rules."""
    print("\n------------------------------------------------------------------")
    print("Test 7: Pydantic Validation Edge Cases")
    print("------------------------------------------------------------------")

    # 1. Invalid aggregation
    try:
        IRMeasure(name="deal_value", aggregation="MEDIAN")
        assert False, "Should have failed on invalid aggregation"
    except ValidationError as e:
        print(" Caught invalid aggregation error as expected: 'MEDIAN' rejected")

    # 2. Invalid sort direction
    try:
        IROrderBy(field="deal_value", direction="SIDEWAYS")
        assert False, "Should have failed on invalid direction"
    except ValidationError as e:
        print(" Caught invalid sort direction error as expected: 'SIDEWAYS' rejected")

    # 3. Invalid limit (non-positive)
    try:
        SemanticQueryIR(
            entities=["fact_deals"],
            measures=[IRMeasure(name="deal_value", aggregation="SUM")],
            limit=-10,
        )
        assert False, "Should have failed on negative limit"
    except ValidationError as e:
        print(" Caught non-positive limit error as expected: limit=-10 rejected")

    # 4. Empty query (no entities, dimensions, or measures)
    try:
        SemanticQueryIR(entities=[], dimensions=[], measures=[])
        assert False, "Should have failed on empty query"
    except ValidationError as e:
        print(" Caught empty query consistency error as expected")

    # 5. Roundtrip JSON serialization and deserialization
    original = SemanticQueryIR(
        entities=["fact_deals"],
        dimensions=["vertical"],
        measures=[IRMeasure(name="deal_value", aggregation="SUM", alias="rev")],
        filters=[IRFilter(field="deal_stage", operator="=", value="Closed Won")],
        limit=10,
    )
    serialized = original.to_json()
    deserialized = SemanticQueryIR.from_json(serialized)
    assert deserialized == original
    print(" JSON round-trip serialization/deserialization confirmed 100% equivalent")


def main():
    print("==================================================================")
    print("Running EvoBI Enterprise SemanticQueryIR Suite...")
    print("==================================================================")

    test_1_simple_aggregation()
    test_2_grouped_query()
    test_3_filtered_query()
    test_4_grouped_and_filtered_query()
    test_5_ordered_query()
    test_6_temporal_grain_query()
    test_7_validation_edge_cases()

    print("\n==================================================================")
    print("All 7 IR validation and example tests passed successfully!")
    print("==================================================================")


if __name__ == "__main__":
    main()
