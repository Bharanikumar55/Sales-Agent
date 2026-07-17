"""
Canonical Schema - Pre-defined business tables that cover all enterprise data sources.

Instead of AI inventing new tables each time, data gets classified into these 
pre-defined tables. This ensures consistency, predictability, and queryability.

Covers: CRM, ERP, HRMS, Meeting Transcripts, Support Tickets, Marketing, Finance
"""

# All columns are TEXT for maximum flexibility.
# source_data stores the full original record as JSON (never lose data).
# extra_data stores any fields that don't map to named columns.

CANONICAL_SCHEMA = {
    "dimensions": {
        "dim_account": {
            "description": "Companies, organizations, clients",
            "columns": {
                "account_name": "TEXT NOT NULL", # Primary identifier
                "industry": "TEXT",             # Used in: revenue_summary, account_360, at_risk
                "geography": "TEXT",            # Onshore / Offshore / Both
                "vertical": "TEXT",             # TF vertical: Mortgage & Lending, Banking & Insurance, Capital Market, Higher Education, Technology, Payments
                "annual_revenue": "TEXT",       # Used in: account_360
                "employee_count": "TEXT",       # Used in: account_360
                "website": "TEXT",              # Used in: account_360
                "source_data": "TEXT",          # Full original record as JSON
            },
            "examples": ["Reliance Industries", "Microsoft"]
        },
        "dim_contact": {
            "description": "People - contacts, decision makers",
            "columns": {
                "contact_name": "TEXT NOT NULL",      # Primary identifier
                "account_name": "TEXT",         # FK to dim_account - Used in ALL queries
                "role": "TEXT",                 # Used in: account_360, deals_closing_soon
                "source_data": "TEXT",          # Full original record (includes email, phone, title, dept)
            },
            "examples": ["Rajesh Kumar - Head of Digital at Reliance"]
        },
        # Note: Additional dimension tables (product, department, location)
        # can be added when needed for future Gold marts
    },
    "facts": {
        "fact_interactions": {
            "description": "Meetings, calls, emails - communication events",
            "columns": {
                "account_id": "INTEGER",        # FK to dim_account.id (identity layer)
                "account_name": "TEXT",         # Kept for backward compatibility
                "interaction_date": "TEXT",     # Used in: top_customers, at_risk_accounts
                "sentiment": "TEXT",            # Used in: activity_summary, at_risk, account_360
                "source_data": "TEXT",          # Full original record (includes type, summary, attendees, etc)
            },
            "examples": ["Meeting with Reliance - Positive sentiment"]
        },
        "fact_deals": {
            "description": "Sales opportunities, pipeline",
            "columns": {
                "account_id": "INTEGER",        # FK to dim_account.id (identity layer)
                "deal_name": "TEXT",            # Used in: deals_closing_soon
                "account_name": "TEXT",         # Kept for backward compatibility
                "deal_value": "TEXT",           # Used in: revenue_summary, pipeline_health, at_risk
                "deal_stage": "TEXT",           # Used in: ALL queries (closed_won, closed_lost, etc)
                "probability": "TEXT",          # Used in: deals_closing_soon
                "close_date": "TEXT",           # Used in: deals_closing_soon, at_risk
                "contact_name": "TEXT",         # Used in: deals_closing_soon
                "vertical": "TEXT",             # TF vertical: Mortgage & Lending, Banking & Insurance, Capital Market, Higher Education, Technology, Payments
                "horizontal": "TEXT",           # TF horizontal/service line: AI & Data, Application Engineering, Digital Operations
                "engagement_model": "TEXT",     # T&M, Fixed, Retainers, Outcome-based
                "opportunity_stage": "TEXT",    # P0 (won) through P10 (cold prospect)
                "ai_influenced": "TEXT",        # yes / no — is this deal AI-influenced?
                "business_type": "TEXT",        # New Business, Existing Customer, Renewal
                "lead_source": "TEXT",          # How the lead was sourced
                "salesperson": "TEXT",          # Owner / sales rep assigned
                "source_data": "TEXT",          # Full original record (includes currency, product, pipeline)
            },
            "examples": ["$2.5M Cloud Deal with Reliance"]
        },
        "fact_insights": {
            "description": "AI-extracted insights, competitive intel",
            "columns": {
                "account_id": "INTEGER",        # FK to dim_account.id (identity layer)
                "account_name": "TEXT",         # Kept for backward compatibility
                "insight_type": "TEXT",         # Used in: activity_summary (competitive check)
                "content": "TEXT",              # Human-readable insight description with reasoning
                "confidence": "TEXT",           # Confidence score (0.0 - 1.0)
                "insight_date": "TEXT",         # Date the insight was observed
                "source_data": "TEXT",          # Full original record as JSON
            },
            "examples": ["Competitor AWS mentioned in Reliance meeting"]
        },
    }
}


SILVER_SCHEMA = "silver"


def get_all_table_names(prefixed=False):
    """Get list of all canonical table names.
    prefixed=True  → ['silver.dim_account', ...]
    prefixed=False → ['dim_account', ...]  (bare names, used for metadata reflection)
    """
    tables = []
    for dim_name in CANONICAL_SCHEMA["dimensions"]:
        tables.append(f"{SILVER_SCHEMA}.{dim_name}" if prefixed else dim_name)
    for fact_name in CANONICAL_SCHEMA["facts"]:
        tables.append(f"{SILVER_SCHEMA}.{fact_name}" if prefixed else fact_name)
    return tables


def prefixed(table_name: str) -> str:
    """Return silver-schema-prefixed table name, e.g. 'dim_account' → 'silver.dim_account'.
    Idempotent — safe to call on already-prefixed names."""
    if table_name.startswith(f"{SILVER_SCHEMA}."):
        return table_name
    return f"{SILVER_SCHEMA}.{table_name}"


def get_table_info(table_name):
    """Get info for a specific table"""
    if table_name in CANONICAL_SCHEMA["dimensions"]:
        return CANONICAL_SCHEMA["dimensions"][table_name]
    if table_name in CANONICAL_SCHEMA["facts"]:
        return CANONICAL_SCHEMA["facts"][table_name]
    return None


def get_schema_summary():
    """Get a text summary of the schema for AI prompts"""
    lines = []
    lines.append("SILVER LAYER — DIMENSION TABLES (entities):")
    for name, info in CANONICAL_SCHEMA["dimensions"].items():
        cols = ", ".join(info["columns"].keys())
        lines.append(f"  silver.{name}: {info['description']}")
        lines.append(f"    Columns: {cols}")

    lines.append("\nSILVER LAYER — FACT TABLES (events/transactions):")
    for name, info in CANONICAL_SCHEMA["facts"].items():
        cols = ", ".join(info["columns"].keys())
        lines.append(f"  silver.{name}: {info['description']}")
        lines.append(f"    Columns: {cols}")

    return "\n".join(lines)
