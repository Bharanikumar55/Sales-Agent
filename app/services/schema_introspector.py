"""
Schema Introspector - Dynamically fetches database schema for AI prompts.

Instead of hardcoding schema definitions, this module queries the database
catalog to get real-time table and column information.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, List, Any, Optional
import json
import time

_schema_cache: Dict[str, Any] = {"text": None, "timestamp": 0}
SCHEMA_CACHE_TTL = 120  # seconds


def get_schema_names(db: Session) -> List[str]:
    """Get all schema names in the database (excluding system schemas)."""
    query = text("""
        SELECT schema_name 
        FROM information_schema.schemata 
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND schema_name NOT LIKE 'pg_temp_%'
          AND schema_name NOT LIKE 'pg_toast_temp_%'
        ORDER BY schema_name
    """)
    result = db.execute(query)
    return [row[0] for row in result.fetchall()]


def get_tables_in_schema(db: Session, schema_name: str) -> List[str]:
    """Get all table names in a specific schema."""
    query = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = :schema 
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    result = db.execute(query, {"schema": schema_name})
    return [row[0] for row in result.fetchall()]


def get_table_columns(db: Session, schema_name: str, table_name: str) -> List[Dict[str, Any]]:
    """Get column details for a specific table."""
    query = text("""
        SELECT 
            column_name,
            data_type,
            character_maximum_length,
            numeric_precision,
            is_nullable,
            column_default
        FROM information_schema.columns 
        WHERE table_schema = :schema 
          AND table_name = :table
        ORDER BY ordinal_position
    """)
    result = db.execute(query, {"schema": schema_name, "table": table_name})
    
    columns = []
    for row in result.fetchall():
        col_info = {
            "name": row[0],
            "type": row[1],
            "nullable": row[4] == "YES",
        }
        if row[2]:  # character max length
            col_info["max_length"] = row[2]
        if row[3]:  # numeric precision
            col_info["precision"] = row[3]
        if row[5]:  # default value
            col_info["default"] = str(row[5])
        columns.append(col_info)
    
    return columns


def get_table_comment(db: Session, schema_name: str, table_name: str) -> Optional[str]:
    """Get the comment/description for a table if available."""
    query = text("""
        SELECT obj_description(
            (quote_ident(:schema) || '.' || quote_ident(:table))::regclass, 
            'pg_class'
        )
    """)
    result = db.execute(query, {"schema": schema_name, "table": table_name})
    row = result.fetchone()
    return row[0] if row and row[0] else None


def get_column_comments(db: Session, schema_name: str, table_name: str) -> Dict[str, str]:
    """Get comments for all columns in a table."""
    query = text("""
        SELECT 
            a.attname as column_name,
            pg_catalog.col_description(a.attrelid, a.attnum) as comment
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = :schema 
          AND c.relname = :table
          AND a.attnum > 0 
          AND NOT a.attisdropped
          AND pg_catalog.col_description(a.attrelid, a.attnum) IS NOT NULL
    """)
    result = db.execute(query, {"schema": schema_name, "table": table_name})
    return {row[0]: row[1] for row in result.fetchall()}


def get_sample_data(db: Session, schema_name: str, table_name: str, limit: int = 3) -> List[Dict]:
    """Get sample rows from a table to help AI understand the data."""
    try:
        query = text(f"""
            SELECT * FROM {schema_name}.{table_name} 
            LIMIT {limit}
        """)
        result = db.execute(query)
        columns = result.keys()
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"  ⚠️ Could not get sample data for {schema_name}.{table_name}: {e}")
        return []


def get_row_counts(db: Session, schema_name: str, table_name: str) -> int:
    """Get approximate row count for a table."""
    try:
        query = text(f"""
            SELECT reltuples::BIGINT as estimate 
            FROM pg_class 
            WHERE oid = '{schema_name}.{table_name}'::regclass
        """)
        result = db.execute(query)
        row = result.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def get_foreign_keys(db: Session, schema_name: str, table_name: str) -> List[Dict[str, str]]:
    """Get foreign key relationships for a table."""
    query = text("""
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = :schema
            AND tc.table_name = :table
    """)
    result = db.execute(query, {"schema": schema_name, "table": table_name})
    return [
        {
            "column": row[0],
            "references_table": f"{row[1]}.{row[2]}",
            "references_column": row[3]
        }
        for row in result.fetchall()
    ]


def introspect_schema(db: Session, target_schemas: List[str] = None) -> Dict[str, Any]:
    """
    Full schema introspection. Returns structured schema information.
    
    Args:
        db: Database session
        target_schemas: List of schema names to introspect. If None, introspects all non-system schemas.
    
    Returns:
        Dictionary with schema → tables → columns structure
    """
    if target_schemas is None:
        target_schemas = get_schema_names(db)
    
    schema_info = {}
    
    for schema_name in target_schemas:
        tables = get_tables_in_schema(db, schema_name)
        schema_info[schema_name] = {}
        
        for table_name in tables:
            columns = get_table_columns(db, schema_name, table_name)
            table_comment = get_table_comment(db, schema_name, table_name)
            column_comments = get_column_comments(db, schema_name, table_name)
            row_count = get_row_counts(db, schema_name, table_name)
            foreign_keys = get_foreign_keys(db, schema_name, table_name)
            
            # Add column comments to column info
            for col in columns:
                col["description"] = column_comments.get(col["name"])
            
            schema_info[schema_name][table_name] = {
                "description": table_comment,
                "columns": columns,
                "row_count": row_count,
                "foreign_keys": foreign_keys,
            }
    
    return schema_info


def invalidate_schema_cache():
    """Call after data ingestion or schema changes to force a fresh introspection."""
    _schema_cache["text"] = None
    _schema_cache["timestamp"] = 0


def format_schema_for_prompt(db: Session, target_schemas: List[str] = None, include_samples: bool = False) -> str:
    """
    Format schema information into a text summary suitable for AI prompts.
    Uses a TTL cache to avoid hitting the DB catalog on every query.
    """
    if target_schemas is None:
        target_schemas = ["gold", "silver"]

    cache_key = ",".join(sorted(target_schemas))
    now = time.time()
    if (
        _schema_cache["text"] is not None
        and (now - _schema_cache["timestamp"]) < SCHEMA_CACHE_TTL
        and _schema_cache.get("key") == cache_key
    ):
        return _schema_cache["text"]

    schema_info = introspect_schema(db, target_schemas)
    
    lines = []
    
    for schema_name in sorted(schema_info.keys()):
        tables = schema_info[schema_name]
        if not tables:
            continue
            
        lines.append(f"\n{'='*60}")
        lines.append(f"SCHEMA: {schema_name.upper()}")
        lines.append(f"{'='*60}")
        
        # Sort tables: prioritize specific naming patterns
        table_names = sorted(tables.keys())
        
        for table_name in table_names:
            table_info = tables[table_name]
            
            # Table header
            desc = table_info.get("description")
            row_count = table_info.get("row_count", 0)
            lines.append(f"\n📋 {schema_name}.{table_name}")
            if desc:
                lines.append(f"   Description: {desc}")
            if row_count:
                lines.append(f"   Rows: ~{row_count:,}")
            
            # Columns
            lines.append("   Columns:")
            for col in table_info["columns"]:
                col_type = col["type"]
                if col.get("max_length"):
                    col_type += f"({col['max_length']})"
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                col_desc = f" - {col['name']}: {col_type} [{nullable}]"
                if col.get("description"):
                    col_desc += f" -- {col['description']}"
                lines.append(col_desc)
            
            # Foreign keys
            if table_info.get("foreign_keys"):
                lines.append("   Relationships:")
                for fk in table_info["foreign_keys"]:
                    lines.append(f"     - {fk['column']} → {fk['references_table']}.{fk['references_column']}")
            
            # Sample data (optional)
            if include_samples:
                samples = get_sample_data(db, schema_name, table_name, limit=2)
                if samples:
                    lines.append("   Sample Data:")
                    for i, sample in enumerate(samples, 1):
                        truncated = {k: str(v)[:50] + "..." if len(str(v)) > 50 else v 
                                   for k, v in sample.items()}
                        lines.append(f"     Row {i}: {json.dumps(truncated, default=str)}")
    
    result_text = "\n".join(lines)
    _schema_cache["text"] = result_text
    _schema_cache["timestamp"] = time.time()
    _schema_cache["key"] = cache_key
    return result_text


def get_gold_layer_guidance() -> str:
    """
    Returns guidance text for when to use Gold vs Silver tables.
    This is kept separate from the dynamic schema since it's business logic.
    """
    return """
GOLD LAYER GUIDANCE (Pre-aggregated business marts - PREFER THESE FIRST):
- gold.top_customers              → Use for: Top customers, best accounts, account rankings
- gold.revenue_summary            → Use for: Revenue by account, deal value summaries, vertical/horizontal breakdown
- gold.pipeline_health            → Use for: Pipeline stages, win rates, funnel analysis, P0-P10 opportunity stages
- gold.account_360                → Use for: Account overviews, 360-degree views, AI-influenced deal counts
- gold.deals_closing_soon         → Use for: Upcoming closes, deals by close date, salesperson info
- gold.at_risk_accounts           → Use for: At-risk accounts, silent accounts, churn risk
- gold.activity_summary           → Use for: Interaction counts, activity summaries per account
- gold.salesperson_performance    → Use for: Salesperson metrics, rep performance, individual sales stats
- gold.vertical_revenue           → Use for: Revenue by vertical (Mortgage, Banking, Capital Market, etc.), horizontal, geography
- gold.ai_influence_summary       → Use for: AI-influenced deals, AI impact on revenue, AI vs non-AI pipeline
- gold.win_loss_analysis          → Use for: Win rates, loss analysis, conversion rates by vertical/salesperson
- gold.deal_velocity              → Use for: Deal speed, time in stage, sales cycle length
- gold.geography_mix              → Use for: Onshore vs offshore revenue split, geography breakdown
- gold.lead_source_effectiveness  → Use for: Lead source ROI, which sources produce most wins/revenue
- gold.stale_deals                → Use for: Stale/stuck deals, deals needing attention, pipeline hygiene

THOUGHTFOCUS BUSINESS DIMENSIONS (available in most gold tables):
- vertical:          Mortgage & Lending, Banking & Insurance, Capital Market, Higher Education, Technology, Payments
- horizontal:        AI & Data, Application Engineering, Digital Operations
- engagement_model:  T&M, Fixed, Retainers, Outcome-based
- opportunity_stage: P0 (won) through P10 (cold prospect)
- ai_influenced:     yes / no
- business_type:     New Business, Existing Customer, Renewal
- geography:         Onshore, Offshore, Both
- salesperson:       Sales rep name

SILVER LAYER GUIDANCE (Raw entity data - Use for specific details):
- silver.dim_*             → Dimension tables: accounts, contacts
- silver.fact_*            → Fact tables: interactions, deals, insights
- Use Silver when question needs: specific meeting summaries, contact details, 
  individual deal details, budget/buying intent from insights
"""


def build_dynamic_prompt(db: Session, question: str, limit: int, conversation_context: str = "") -> str:
    """
    Build a complete SQL generation prompt with dynamic schema introspection.

    This replaces the hardcoded prompt in nl_query_engine.py.
    """
    # Get dynamic schema
    schema_text = format_schema_for_prompt(db, target_schemas=["gold", "silver"])

    # Get business logic guidance
    guidance_text = get_gold_layer_guidance()

    # Build conversation context section if available
    context_section = ""
    if conversation_context:
        context_section = f"""
CONVERSATION CONTEXT (Previous messages for reference):
{conversation_context}

IMPORTANT: Use the conversation context to understand references like:
- "this account" → refers to the account mentioned in previous messages
- "them" → refers to people/companies mentioned above
- "tell me more" → expand on previous topic
- "who else" → related to previous query context
"""

    prompt = f"""You are a SQL expert for a business semantic layer. Convert this question to PostgreSQL queries.

{schema_text}

{guidance_text}
{context_section}

QUESTION: {question}

CRITICAL RULES:
1. PREFER gold.* tables for summary, ranking, pipeline, risk questions. Use silver.* for specific row-level detail.
2. Generate the SINGLE most relevant query to answer the question elegantly. Only generate multiple queries if the information requested spans across completely unrelated entities that cannot be joined.
3. If you do generate multiple queries, ensure they are compatible for tabular display if they represent similar entities.
4. Use ILIKE '%keyword%' for ALL text searches — NEVER use = for text columns
5. sentiment values are stored lowercase — use sentiment ILIKE 'negative' (or 'positive'/'neutral')
6. account_name is stored lowercase — always use ILIKE for account name filters
7. For deal_stage: use ILIKE 'closed won' / ILIKE 'closed lost' (exact values: 'Closed Won', 'Closed Lost', 'Negotiation', 'Proposal', 'Discovery')
8. deal_value is TEXT — always cast: CASE WHEN deal_value ~ '^[0-9.]+$' THEN CAST(deal_value AS NUMERIC) ELSE 0 END
9. Always ORDER BY date DESC (insight_date, interaction_date, etc.)
10. Use LIMIT {limit}
11. TF dimension filters: vertical ILIKE '%mortgage%', opportunity_stage ILIKE 'p0', ai_influenced ILIKE 'yes' (these are TEXT columns, always use ILIKE)

Return JSON:
{{
    "sql_queries": [
        "SELECT * FROM silver.fact_interactions WHERE account_name ILIKE '%example%' ORDER BY interaction_date DESC LIMIT {limit}"
    ],
    "reasoning": "Brief explanation of table choice"
}}

IMPORTANT: Return ONLY valid JSON."""
    
    return prompt
