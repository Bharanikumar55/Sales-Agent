"""EvoBI Semantic Catalog Data Models

Provides clean, vendor-agnostic abstractions for entities, dimensions,
measures, relationships, and the overall semantic catalog.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SemanticEntity(BaseModel):
    """Represents a logical table/entity in the semantic layer."""
    name: str = Field(..., description="Logical entity name (e.g., 'fact_deals', 'dim_account')")
    physical_table: str = Field(..., description="Fully qualified physical table name (e.g., 'silver.fact_deals')")
    schema_name: str = Field(..., description="Database schema/layer ('silver' or 'gold')")
    primary_key: Optional[str] = Field(default="id", description="Primary key column identifier")
    description: Optional[str] = Field(default=None, description="Human-readable business description of the entity")


class SemanticDimension(BaseModel):
    """Represents a categorical, textual, or temporal attribute of an entity."""
    name: str = Field(..., description="Logical dimension name")
    physical_column: str = Field(..., description="Physical column name in the database table")
    entity: str = Field(..., description="Logical entity name this dimension belongs to")
    data_type: str = Field(default="TEXT", description="Physical data type (TEXT, VARCHAR, DATE, etc.)")
    description: Optional[str] = Field(default=None, description="Business description of the dimension")
    time_grains: Optional[List[str]] = Field(
        default=None,
        description="Available time grains if this is a temporal dimension (e.g. ['day', 'week', 'month', 'quarter', 'year'])"
    )
    allowed_values: Optional[List[str]] = Field(
        default=None,
        description="Explicit allowed values/categories for constrained dimensions"
    )


class SemanticMeasure(BaseModel):
    """Represents a quantitative, aggregatable metric."""
    name: str = Field(..., description="Logical measure / metric name")
    physical_column: str = Field(..., description="Physical column or SQL expression for aggregation")
    entity: str = Field(..., description="Logical entity name this measure belongs to")
    data_type: str = Field(default="NUMERIC", description="Data type (NUMERIC, INTEGER, etc.)")
    default_aggregation: str = Field(
        default="SUM",
        description="Default aggregation function: SUM, AVG, COUNT, MIN, MAX, COUNT_DISTINCT"
    )
    description: Optional[str] = Field(default=None, description="Business description of the metric")


class SemanticRelationship(BaseModel):
    """Represents a join relationship between two semantic entities."""
    from_entity: str = Field(..., description="Source entity name (e.g. 'fact_deals')")
    to_entity: str = Field(..., description="Target entity name (e.g. 'dim_account')")
    from_column: str = Field(..., description="Join key column on source entity (e.g. 'account_id')")
    to_column: str = Field(..., description="Join key column on target entity (e.g. 'id')")
    cardinality: Optional[str] = Field(
        default="N:1",
        description="Relationship cardinality (e.g., 'N:1', '1:N', '1:1', 'N:M')"
    )


class EvoBICatalog(BaseModel):
    """The central EvoBI Semantic Catalog containing entities, dimensions, measures, and relationships."""
    entities: Dict[str, SemanticEntity] = Field(default_factory=dict)
    dimensions: Dict[str, SemanticDimension] = Field(default_factory=dict)
    measures: Dict[str, SemanticMeasure] = Field(default_factory=dict)
    relationships: List[SemanticRelationship] = Field(default_factory=list)

    def get_entity(self, name: str) -> Optional[SemanticEntity]:
        """Retrieve an entity by name."""
        return self.entities.get(name)

    def get_dimensions_for_entity(self, entity_name: str) -> List[SemanticDimension]:
        """Return all dimensions belonging to a given entity."""
        return [d for d in self.dimensions.values() if d.entity == entity_name]

    def get_measures_for_entity(self, entity_name: str) -> List[SemanticMeasure]:
        """Return all measures belonging to a given entity."""
        return [m for m in self.measures.values() if m.entity == entity_name]

    def get_relationships_for_entity(self, entity_name: str) -> List[SemanticRelationship]:
        """Return all relationships involving the given entity."""
        return [
            r for r in self.relationships
            if r.from_entity == entity_name or r.to_entity == entity_name
        ]

    def find_dimension(self, dim_name: str, entity_name: Optional[str] = None) -> Optional[SemanticDimension]:
        """Find a dimension by name, optionally scoped to a specific entity."""
        if entity_name:
            key = f"{entity_name}.{dim_name}"
            if key in self.dimensions:
                return self.dimensions[key]
        for d in self.dimensions.values():
            if d.name == dim_name and (entity_name is None or d.entity == entity_name):
                return d
        return None

    def find_measure(self, measure_name: str, entity_name: Optional[str] = None) -> Optional[SemanticMeasure]:
        """Find a measure by name, optionally scoped to a specific entity."""
        if entity_name:
            key = f"{entity_name}.{measure_name}"
            if key in self.measures:
                return self.measures[key]
        for m in self.measures.values():
            if m.name == measure_name and (entity_name is None or m.entity == entity_name):
                return m
        return None

    def to_summary_dict(self) -> Dict[str, Any]:
        """Produce a clean, human-readable summary of the catalog."""
        return {
            "total_entities": len(self.entities),
            "total_dimensions": len(self.dimensions),
            "total_measures": len(self.measures),
            "total_relationships": len(self.relationships),
            "entities": {
                name: {
                    "physical_table": ent.physical_table,
                    "layer": ent.schema_name,
                    "primary_key": ent.primary_key,
                    "dimensions": [d.name for d in self.get_dimensions_for_entity(name)],
                    "measures": [f"{m.name} ({m.default_aggregation})" for m in self.get_measures_for_entity(name)],
                }
                for name, ent in self.entities.items()
            },
            "relationships": [
                f"{r.from_entity}.{r.from_column} -> {r.to_entity}.{r.to_column} ({r.cardinality})"
                for r in self.relationships
            ]
        }
