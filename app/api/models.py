"""API Request/Response Models"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Request Models
class AnalyzeDataRequest(BaseModel):
    """Request to analyze data and suggest schema"""
    source_name: str = Field(..., description="Name of data source (e.g., 'crm', 'erp')")
    sample_data: List[Dict[str, Any]] = Field(..., description="Sample data records")
    auto_create: bool = Field(default=False, description="Automatically create schema if true")

class CreateSchemaRequest(BaseModel):
    """Request to create semantic layer schema"""
    schema: Dict[str, Any] = Field(..., description="Schema structure from analyze endpoint")
    approval: str = Field(default="approved", description="Approval status")

class IngestDataRequest(BaseModel):
    """Request to ingest data"""
    source: str = Field(..., description="Data source name")
    data: List[Dict[str, Any]] = Field(..., description="Data records to ingest")
    auto_enrich: bool = Field(default=True, description="Automatically enrich existing dimensions")

class QueryRequest(BaseModel):
    """Request to query semantic layer"""
    dimensions: List[str] = Field(..., description="Dimensions to include")
    metrics: Optional[List[str]] = Field(default=None, description="Metrics to aggregate")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Filter conditions")
    group_by: Optional[List[str]] = Field(default=None, description="Group by dimensions")
    limit: Optional[int] = Field(default=100, description="Result limit")

class ConversationMessage(BaseModel):
    """A single message in the conversation history"""
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")

class NaturalLanguageQueryRequest(BaseModel):
    """Request to query using natural language"""
    query: str = Field(..., description="Natural language question (e.g., 'What is the budget for Reliance?')")
    limit: Optional[int] = Field(default=10, description="Maximum results to return")
    account_context: Optional[str] = Field(default=None, description="Scope query to a specific account name")
    conversation_history: Optional[List[ConversationMessage]] = Field(default=None, description="Previous messages for context (last 3 recommended)")

# Response Models
class AnalyzeDataResponse(BaseModel):
    """Response from analyze endpoint"""
    status: str
    suggested_schema: Dict[str, Any]
    confidence: float
    source: str
    data_type: str = "structured_data"  # Type detected: raw_transcript, structured_meeting, structured_data
    message: str

class CreateSchemaResponse(BaseModel):
    """Response from create schema endpoint"""
    status: str
    tables_created: List[str]
    message: str

class IngestDataResponse(BaseModel):
    """Response from ingest endpoint"""
    status: str
    action: str  # "enriched", "new_dimension_detected", "created"
    records_processed: int
    tables_updated: List[str]
    new_dimensions: Optional[List[Dict[str, Any]]] = None
    message: str

class QueryResponse(BaseModel):
    """Response from query endpoint"""
    status: str
    data: List[Dict[str, Any]]
    sql: Optional[str] = None
    execution_time_ms: Optional[float] = None
    row_count: int

class NaturalLanguageQueryResponse(BaseModel):
    """Response from natural language query endpoint"""
    status: str
    answer: str
    sql_queries: List[str]
    data: List[Dict[str, Any]]
    explanation: str
    row_count: int
    execution_time_ms: float
    fallback_used: Optional[bool] = False
    enrichment_triggered: Optional[bool] = False
    vector_used: Optional[bool] = False
    account_context: Optional[str] = None

class SchemaInfoResponse(BaseModel):
    """Response from schema info endpoint"""
    dimensions: List[Dict[str, Any]]
    fact_tables: List[Dict[str, Any]]
    total_tables: int
    version: str
