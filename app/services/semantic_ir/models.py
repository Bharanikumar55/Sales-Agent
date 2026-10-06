"""EvoBI Enterprise Intermediate Representation (IR) Data Models

A strongly typed, vendor-agnostic representation of user analytical queries.
Expresses WHAT data and calculations are desired without containing raw SQL.
"""
from enum import Enum
from typing import List, Any, Optional, Union
import json
from pydantic import BaseModel, Field, field_validator, model_validator


class AggregationType(str, Enum):
    """Allowed metric aggregation operations in the Semantic IR."""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    MIN = "MIN"
    MAX = "MAX"


class OrderDirection(str, Enum):
    """Sort direction options."""
    ASC = "ASC"
    DESC = "DESC"


class IRMeasure(BaseModel):
    """Quantitative metric specification in the IR."""
    name: str = Field(..., description="Name of the measure / metric attribute")
    aggregation: str = Field(default="SUM", description="Aggregation function (SUM, AVG, COUNT, MIN, MAX, COUNT_DISTINCT)")
    alias: Optional[str] = Field(default=None, description="Optional output column alias for the aggregated metric")

    @field_validator("aggregation")
    @classmethod
    def validate_aggregation(cls, v: str) -> str:
        v_upper = v.upper().strip()
        allowed = {a.value for a in AggregationType}
        if v_upper not in allowed:
            raise ValueError(f"Invalid aggregation '{v}'. Allowed aggregations: {sorted(allowed)}")
        return v_upper


class IRFilter(BaseModel):
    """Filter / predicate specification in the IR."""
    field: str = Field(..., description="Field/attribute name to filter on")
    operator: str = Field(default="=", description="Comparison operator (=, !=, >, >=, <, <=, IN, NOT IN, LIKE, ILIKE, IS NULL, IS NOT NULL, BETWEEN)")
    value: Optional[Any] = Field(default=None, description="Filter operand value(s)")

    @field_validator("operator")
    @classmethod
    def normalize_operator(cls, v: str) -> str:
        op = v.strip().upper()
        # Accept standard mathematical and SQL comparison operators
        allowed_ops = {"=", "==", "!=", "<>", ">", ">=", "<", "<=", "IN", "NOT IN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL", "BETWEEN"}
        if op == "==":
            return "="
        if op == "<>":
            return "!="
        if op not in allowed_ops:
            raise ValueError(f"Unsupported filter operator '{v}'. Allowed: {sorted(allowed_ops)}")
        return op


class IROrderBy(BaseModel):
    """Ordering specification in the IR."""
    field: str = Field(..., description="Field or alias name to sort by")
    direction: str = Field(default="ASC", description="Sort direction (ASC or DESC)")

    @field_validator("direction")
    @classmethod
    def normalize_direction(cls, v: str) -> str:
        d = v.strip().upper()
        if d not in ("ASC", "DESC"):
            raise ValueError(f"Invalid sort direction '{v}'. Must be 'ASC' or 'DESC'")
        return d


class IRTimeGrain(BaseModel):
    """Optional temporal grain specification for time-series analysis."""
    field: str = Field(..., description="Date or timestamp dimension field name")
    grain: str = Field(default="month", description="Time granularity: day, week, month, quarter, year")

    @field_validator("grain")
    @classmethod
    def normalize_grain(cls, v: str) -> str:
        g = v.strip().lower()
        allowed = {"day", "week", "month", "quarter", "year"}
        if g not in allowed:
            raise ValueError(f"Invalid time grain '{v}'. Allowed: {sorted(allowed)}")
        return g


class SemanticQueryIR(BaseModel):
    """Central EvoBI Intermediate Representation (IR).

    Decouples natural language query understanding from physical SQL generation.
    Describes WHAT analytical results are requested, independent of dialect syntax.
    """
    entities: List[str] = Field(default_factory=list, description="Target entities / models (e.g. ['fact_deals'])")
    dimensions: List[str] = Field(default_factory=list, description="Grouping / projection dimension attributes")
    measures: List[IRMeasure] = Field(default_factory=list, description="Quantitative aggregated metrics")
    filters: List[IRFilter] = Field(default_factory=list, description="Query filter predicates")
    group_by: List[str] = Field(default_factory=list, description="Grouping dimensions (usually identical to dimensions)")
    order_by: List[IROrderBy] = Field(default_factory=list, description="Sorting rules")
    limit: Optional[int] = Field(default=None, description="Maximum number of records to return")
    time_grain: Optional[IRTimeGrain] = Field(default=None, description="Optional time granularity specification")

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("Limit must be a positive integer greater than zero.")
        return v

    @model_validator(mode="after")
    def validate_query_consistency(self) -> "SemanticQueryIR":
        """Basic structural validation for the query."""
        if not self.entities and not self.dimensions and not self.measures:
            raise ValueError("Query IR must specify at least one entity, dimension, or measure.")
        return self

    def to_json(self, indent: int = 2) -> str:
        """Serialize the IR into formatted JSON string."""
        return json.dumps(self.model_dump(), indent=indent, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "SemanticQueryIR":
        """Deserialize and validate from JSON string."""
        data = json.loads(json_str)
        return cls(**data)
