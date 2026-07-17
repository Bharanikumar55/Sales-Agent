"""Main FastAPI Application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.config import settings
from app.database import engine, Base

app = FastAPI(
    title=settings.SERVICE_NAME,
    description="AI-powered semantic layer service for intelligent data modeling",
    version=settings.VERSION
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    print(f"Starting {settings.SERVICE_NAME} v{settings.VERSION}")
    print(f"Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
    print(f"AI Model: {settings.OPENAI_MODEL} (fast: {settings.OPENAI_MODEL_FAST})")
    
    # Create base tables if needed
    try:
        Base.metadata.create_all(bind=engine)
        print("Database connection established")
    except Exception as e:
        print(f"Database connection warning: {e}")
    
    # -- Bronze + Silver schemas (raw_ingestion, processed_data)
    # -- Silver entity tables (dim_* / fact_* in public schema)
    try:
        from app.database import SessionLocal
        from app.services.schema_manager import SchemaManager

        db = SessionLocal()
        schema_manager = SchemaManager(db)
        result = schema_manager.initialize_canonical_schema()
        db.close()

        if result["created"]:
            print(f"Silver: Created {len(result['created'])} entity table(s): {', '.join(result['created'])}")
        if result["existing"]:
            print(f"Silver: {len(result['existing'])} entity table(s) already exist")
    except Exception as e:
        print(f"Silver schema warning: {e}")

    # -- Gold aggregation marts (pre-computed business answers)
    try:
        from app.database import SessionLocal
        from app.services.gold_layer import GoldLayerBuilder

        db = SessionLocal()
        gold = GoldLayerBuilder(db)
        gold.initialize()
        db.close()
        print("Gold: 15 aggregation marts ready (revenue_summary, top_customers, pipeline_health, account_360, activity_summary, deals_closing_soon, at_risk_accounts, salesperson_performance, vertical_revenue, ai_influence_summary, win_loss_analysis, deal_velocity, geography_mix, lead_source_effectiveness, stale_deals)")
    except Exception as e:
        print(f"Gold layer init warning: {e}")

    # -- Normalize existing data (idempotent — safe to run every startup)
    try:
        from app.database import SessionLocal
        from sqlalchemy import text as sa_text
        db = SessionLocal()
        db.execute(sa_text("UPDATE silver.fact_interactions SET sentiment = LOWER(sentiment) WHERE sentiment ~ '[A-Z]'"))
        db.execute(sa_text("UPDATE silver.fact_deals SET deal_stage = INITCAP(deal_stage) WHERE deal_stage !~ '^[A-Z]'"))
        db.commit()
        db.close()
        print("Data normalization: sentiment lowercased, deal_stage title-cased")
    except Exception as e:
        print(f"Normalization warning (non-fatal): {e}")

    print(f"{settings.SERVICE_NAME} is ready on port {settings.SERVICE_PORT}!")

@app.get("/")
def root():
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "status": "running",
        "description": "AI-powered semantic layer service",
        "endpoints": {
            "analyze": "POST /api/v1/schema/analyze",
            "create": "POST /api/v1/schema/create",
            "ingest": "POST /api/v1/data/ingest",
            "upload": "POST /api/v1/data/upload",
            "query": "POST /api/v1/query",
            "ask": "POST /api/v1/query/ask",
            "info": "GET /api/v1/schema/info"
        }
    }

@app.get("/health")
def health():
    return {"status": "healthy", "service": settings.SERVICE_NAME}
