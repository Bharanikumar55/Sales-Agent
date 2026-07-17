"""API Routes - Canonical Schema with AI Classification"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any, Optional
import time
import json
import csv
import io

from app.database import get_db
from app.api.models import (
    AnalyzeDataRequest, AnalyzeDataResponse,
    CreateSchemaRequest, CreateSchemaResponse,
    IngestDataRequest, IngestDataResponse,
    QueryRequest, QueryResponse,
    NaturalLanguageQueryRequest, NaturalLanguageQueryResponse,
    SchemaInfoResponse
)
from app.services.ai_analyzer import AIDataClassifier
from app.services.schema_manager import SchemaManager
from app.services.canonical_schema import get_schema_summary, get_all_table_names, prefixed as silver_prefixed
from app.services.nl_query_engine import NLQueryEngine
from app.services.data_mapper import DataMapper
from app.services.schema_evolution import SchemaEvolutionEngine
from app.services.gold_layer import GoldLayerBuilder
from app.services.file_overview_service import FileOverviewService
from app.services.data_validator import is_sales_relevant
from app.services.schema_introspector import invalidate_schema_cache

router = APIRouter(prefix="/api/v1", tags=["semantic-layer"])


@router.post("/schema/analyze", response_model=AnalyzeDataResponse)
async def analyze_data(request: AnalyzeDataRequest, db: Session = Depends(get_db)):
    """
    Preview how data will be classified into canonical tables.
    Does NOT insert data - just shows the mapping.
    Handles: Raw transcripts, CRM, ERP, HRMS, or any structured data.
    """
    try:
        from app.services.transcript_processor import TranscriptProcessor
        
        classifier = AIDataClassifier()
        
        # Step 1: Detect data type
        data_type = classifier.detect_data_type(request.sample_data)
        print(f"📊 Detected data type: {data_type}")
        
        # Step 2: Process raw transcripts if needed
        processed_data = request.sample_data
        if data_type == "raw_transcript":
            print("🎤 Processing raw transcript with NLP...")
            processor = TranscriptProcessor()
            processed_data = []
            for record in request.sample_data:
                raw_text = record.get("transcript") or record.get("raw_transcript")
                metadata = {k: v for k, v in record.items() if k not in ["transcript", "raw_transcript"]}
                processed = processor.process_raw_transcript(raw_text, metadata)
                processed_data.append(processed)
                print(f"✅ Extracted: {processed.get('account_name', 'Unknown')} - {processed.get('sentiment', 'N/A')}")
        
        # Step 3: Classify into canonical tables
        if data_type == "raw_transcript":
            # Deterministic classification for transcripts (no AI call needed)
            result = classifier.classify_transcript_data(processed_data, request.source_name)
        else:
            # AI-powered classification for structured data
            print("🤖 AI classifying data into canonical tables...")
            result = classifier.classify_data(processed_data, request.source_name)
        
        # Build response
        tables_used = [c["table"] for c in result.get("classifications", [])]
        total_records = sum(len(c["records"]) for c in result.get("classifications", []))
        
        return AnalyzeDataResponse(
            status="success",
            suggested_schema=result,
            confidence=0.9,
            source=request.source_name,
            data_type=data_type,
            message=f"Classified {len(request.sample_data)} record(s) into {len(tables_used)} table(s) ({total_records} rows). Tables: {', '.join(tables_used)}"
        )
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/ingest", response_model=IngestDataResponse)
async def ingest_data(request: IngestDataRequest, db: Session = Depends(get_db)):
    """
    Ingest data into canonical tables.
    
    ENTERPRISE DETERMINISTIC APPROACH:
    1. Raw transcripts → NLP extraction → deterministic mapping
    2. Structured data (CRM/ERP/HRMS) → exact field mapping (NO AI)
    3. Unknown fields → AI decides which table (ONLY AI usage)
    """
    try:
        from app.services.transcript_processor import TranscriptProcessor
        
        schema_manager = SchemaManager(db)
        data_mapper = DataMapper()
        ai_classifier = AIDataClassifier()
        
        # Step 1: Detect data type (deterministic - checks for transcript field)
        data_type = ai_classifier.detect_data_type(request.data)
        print(f"📊 Ingest - Data type: {data_type}, Source: {request.source}")
        
        # Step 1b: Save to Bronze Layer (Postgres)
        schema_manager.save_to_bronze(request.source, data_type, request.data)
        
        # Step 2: Process raw transcripts if needed
        processed_data = request.data
        if data_type == "raw_transcript":
            print("🎤 Processing raw transcript with NLP...")
            processor = TranscriptProcessor()
            processed_data = []
            for record in request.data:
                raw_text = record.get("transcript") or record.get("raw_transcript")
                metadata = {k: v for k, v in record.items() if k not in ["transcript", "raw_transcript"]}
                processed = processor.process_raw_transcript(raw_text, metadata)
                # Preserve raw text so ingestion_engine can index it in the vector store
                if raw_text:
                    processed["_raw_text"] = raw_text
                processed_data.append(processed)
                print(f"  ✅ Extracted: {processed.get('account_name', 'Unknown')} - {processed.get('sentiment', 'N/A')}")
            
            # Transcripts use deterministic classification (structure is known after NLP)
            classification = ai_classifier.classify_transcript_data(processed_data, request.source)
            classification["method"] = "deterministic"
            print("🔧 Classification: deterministic (transcript)")
        else:
            classification = None

        # --- MODULAR INGESTION ENGINE ---
        from app.services.ingestion_engine import IngestionEngine
        engine = IngestionEngine(db)
        result = engine.process(processed_data, request.source, data_type=data_type, pre_classification=classification)
        
        # Extract account names and data types from the ingested data
        accounts_found = set()
        for rec in processed_data:
            name = rec.get("account_name") or rec.get("company") or rec.get("account")
            if name and isinstance(name, str) and len(name.strip()) > 1:
                accounts_found.add(name.strip())

        tables_touched = set()
        if classification and classification.get("classifications"):
            for c in classification["classifications"]:
                tbl = c.get("table", "")
                count = len(c.get("records", []))
                if count > 0:
                    label = tbl.replace("dim_", "").replace("fact_", "").replace("_", " ").title()
                    tables_touched.add(label)

        # Build a human-friendly message
        parts = []
        rc = result['record_count']
        if rc > 0:
            parts.append(f"Successfully added **{rc} record(s)**")
            if tables_touched:
                parts[-1] += f" to {', '.join(sorted(tables_touched))}"
            if accounts_found:
                acct_list = ", ".join(f"**{a}**" for a in sorted(accounts_found))
                parts.append(f"Accounts detected: {acct_list}")
        else:
            parts.append("File was saved but no new records were added to the database")
            if accounts_found:
                acct_list = ", ".join(f"**{a}**" for a in sorted(accounts_found))
                parts.append(f"Accounts mentioned in file: {acct_list}")

        msg = ". ".join(parts) + "."

        invalidate_schema_cache()

        return IngestDataResponse(
            status="success",
            action="ingested",
            records_processed=result['record_count'],
            tables_updated=list(tables_touched),
            message=msg
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/query", response_model=QueryResponse)
async def query_semantic_layer(request: QueryRequest, db: Session = Depends(get_db)):
    """
    Query the semantic layer. Specify a table name or let it query all.
    """
    try:
        start_time = time.time()
        schema_manager = SchemaManager(db)
        
        # Determine which table to query
        table_name = None
        if request.dimensions:
            # Use first dimension as table hint
            dim = request.dimensions[0].lower()
            for t in get_all_table_names(prefixed=True):
                if dim in t:
                    table_name = t
                    break

        if not table_name:
            table_name = "silver.fact_interactions"
        
        limit = request.limit or 100
        sql = f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT {limit}"
        
        result = db.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()
        data = [dict(zip(columns, row)) for row in rows]
        
        execution_time = (time.time() - start_time) * 1000
        
        return QueryResponse(
            status="success",
            data=data,
            sql=sql,
            execution_time_ms=execution_time,
            row_count=len(data)
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/ask", response_model=NaturalLanguageQueryResponse)
async def ask_natural_language(request: NaturalLanguageQueryRequest, db: Session = Depends(get_db)):
    """
    Query the semantic layer using natural language.
    AI converts your question to SQL, executes it, and synthesizes an answer.
    Supports conversation history for context-aware responses.
    
    Examples:
    - "What is the budget for Reliance Industries?"
    - "Show me all meetings with Aether Tech"
    - "What deals are in the pipeline?"
    - "Who are the contacts at Reliance?"
    """
    try:
        engine = NLQueryEngine(db)
        result = engine.query(
            question=request.query,
            limit=request.limit,
            account_context=request.account_context,
            conversation_history=request.conversation_history
        )
        
        return NaturalLanguageQueryResponse(**result)
    
    except Exception as e:
        print(f"❌ NL Query Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/upload")
async def upload_file(
    file: UploadFile = File(...),
    source: str = Form(default="user_upload"),
    force_process: bool = Form(default=False),
    db: Session = Depends(get_db)
):
    """
    Upload a file (PDF, CSV, TXT, XLSX, DOCX) and ingest it into the semantic layer.
    - PDF/TXT/DOCX: Treated as transcript → AI extraction
    - CSV/XLSX: Treated as structured data → deterministic mapping
    - Returns AI-generated overview along with ingestion results
    - If file is not sales-relevant, skips Silver processing (saved to Bronze only)
    - Pass force_process=true to bypass relevance check
    """
    try:
        content = await file.read()
        filename = file.filename.lower()
        file_extension = filename.rsplit(".", 1)[-1]
        print(f"📁 File upload: {file.filename} ({len(content)} bytes), source: {source}")

        # --- MODULAR FILE PARSER ---
        from app.services.file_parser import FileParser
        data = FileParser.parse(file.filename, content)

        if not data:
            raise HTTPException(status_code=400, detail="No data extracted from file")

        # --- DOMAIN RELEVANCE CHECK ---
        relevant, relevance_msg = True, ""
        if not force_process:
            relevant, relevance_msg = is_sales_relevant(data)

        if not relevant:
            print(f"  ⚠️ File not sales-relevant: {file.filename}")
            schema_manager = SchemaManager(db)
            ai_classifier = AIDataClassifier()
            data_type = ai_classifier.detect_data_type(data)
            schema_manager.save_to_bronze(source, data_type, data)

            return {
                "status": "skipped",
                "filename": file.filename,
                "file_type": file_extension,
                "records_extracted": len(data),
                "is_relevant": False,
                "relevance_message": relevance_msg,
                "file_overview": None,
                "ingest_result": {
                    "records_processed": 0,
                    "tables_updated": [],
                    "message": "File saved to Bronze (raw archive) only — not processed into Silver."
                }
            }

        # Extract account names from data for the response
        accounts_in_file = set()
        for rec in data:
            name = rec.get("account_name") or rec.get("company") or rec.get("account")
            if name and isinstance(name, str) and len(name.strip()) > 1:
                accounts_in_file.add(name.strip())

        # --- PARALLEL: Generate AI Overview (non-blocking) ---
        overview_service = FileOverviewService()
        file_overview = overview_service.generate_overview(
            filename=file.filename,
            data=data,
            file_type=file_extension
        )

        # Attach real filename so vector store uses it as the doc identity key
        for record in data:
            if "raw_transcript" in record:
                record["_filename"] = file.filename

        # Route through existing ingest logic
        ingest_request = IngestDataRequest(source=source, data=data)
        result = await ingest_data(ingest_request, db)

        return {
            "status": "success",
            "filename": file.filename,
            "file_type": file_extension,
            "records_extracted": len(data),
            "accounts_found": list(accounts_in_file),
            "is_relevant": True,
            "relevance_message": "",
            "file_overview": file_overview,
            "ingest_result": {
                "records_processed": result.records_processed,
                "tables_updated": result.tables_updated,
                "message": result.message
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Upload Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/upload/{account_name}")
async def upload_file_for_account(
    account_name: str,
    file: UploadFile = File(...),
    source: str = Form(default="account_upload"),
    force_process: bool = Form(default=False),
    db: Session = Depends(get_db)
):
    """
    Upload a file scoped to a specific account (for account-specific chat).
    Same as /data/upload but tags all data with the account name.
    Returns AI-generated overview along with ingestion results.
    If file is not sales-relevant, skips Silver processing (saved to Bronze only).
    """
    try:
        content = await file.read()
        filename = file.filename.lower()
        file_extension = filename.rsplit(".", 1)[-1]
        print(f"📁 Account upload for '{account_name}': {file.filename} ({len(content)} bytes)")

        # --- MODULAR FILE PARSER ---
        from app.services.file_parser import FileParser
        data = FileParser.parse(file.filename, content)

        # Inject account context into all records
        for record in data:
            record["account_name"] = account_name

        if not data:
            raise HTTPException(status_code=400, detail="No data extracted from file")

        print(f"  ✅ Parsed: {len(data)} records tagged to {account_name}")

        # Detect other account names mentioned in the file (before overwriting)
        other_accounts = set()
        for rec in data:
            original_name = rec.get("_original_account") or rec.get("company") or ""
            if original_name and isinstance(original_name, str) and len(original_name.strip()) > 1:
                if original_name.strip().lower() != account_name.strip().lower():
                    other_accounts.add(original_name.strip())

        account_mismatch = len(other_accounts) > 0

        # --- DOMAIN RELEVANCE CHECK ---
        relevant, relevance_msg = True, ""
        if not force_process:
            relevant, relevance_msg = is_sales_relevant(data)

        if not relevant:
            print(f"  ⚠️ File not sales-relevant: {file.filename} (account: {account_name})")
            schema_manager = SchemaManager(db)
            ai_classifier = AIDataClassifier()
            data_type = ai_classifier.detect_data_type(data)
            schema_manager.save_to_bronze(source, data_type, data)

            return {
                "status": "skipped",
                "account": account_name,
                "filename": file.filename,
                "file_type": file_extension,
                "records_extracted": len(data),
                "is_relevant": False,
                "account_mismatch": False,
                "other_accounts": [],
                "relevance_message": relevance_msg,
                "file_overview": None,
                "ingest_result": {
                    "records_processed": 0,
                    "tables_updated": [],
                    "message": f"This file doesn't appear to contain sales-related data. It has been saved to the archive."
                }
            }

        # --- PARALLEL: Generate AI Overview (non-blocking) ---
        overview_service = FileOverviewService()
        file_overview = overview_service.generate_overview(
            filename=file.filename,
            data=data,
            file_type=file_extension
        )

        # Attach real filename + account context so vector store uses correct doc identity
        for record in data:
            if "raw_transcript" in record:
                record["_filename"] = file.filename
                record["_account_context"] = account_name

        # Route through existing ingest logic
        ingest_request = IngestDataRequest(source=source, data=data)
        result = await ingest_data(ingest_request, db)

        return {
            "status": "success",
            "account": account_name,
            "filename": file.filename,
            "file_type": file_extension,
            "records_extracted": len(data),
            "is_relevant": True,
            "account_mismatch": account_mismatch,
            "other_accounts": list(other_accounts),
            "relevance_message": "",
            "file_overview": file_overview,
            "ingest_result": {
                "records_processed": result.records_processed,
                "tables_updated": result.tables_updated,
                "message": result.message
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Account Upload Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema/info", response_model=SchemaInfoResponse)
async def get_schema_info(db: Session = Depends(get_db)):
    """
    Get current semantic layer schema with row counts.
    """
    try:
        schema_manager = SchemaManager(db)
        info = schema_manager.get_schema_info()
        
        return SchemaInfoResponse(
            dimensions=info["dimensions"],
            fact_tables=info["fact_tables"],
            total_tables=info["total_tables"],
            version="2.0.0"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Dashboard Endpoints
# =========================================================================

@router.get("/dashboard/accounts")
async def get_accounts(db: Session = Depends(get_db)):
    """Get all accounts with summary info"""
    try:
        result = db.execute(text("SELECT * FROM silver.dim_account ORDER BY id DESC"))
        rows = result.fetchall()
        columns = result.keys()
        accounts = [dict(zip(columns, row)) for row in rows]

        enriched = []
        for acc in accounts:
            name = acc.get("account_name", "")
            
            contacts_r = db.execute(text(
                "SELECT COUNT(*) FROM silver.dim_contact WHERE account_name ILIKE :name"
            ), {"name": f"%{name}%"})
            contact_count = contacts_r.scalar() or 0

            deals_r = db.execute(text(
                "SELECT COUNT(*), COALESCE(SUM(CASE WHEN deal_value ~ '^[0-9.]+$' THEN CAST(deal_value AS NUMERIC) ELSE 0 END), 0) FROM silver.fact_deals WHERE account_name ILIKE :name"
            ), {"name": f"%{name}%"})
            deal_row = deals_r.fetchone()
            deal_count = deal_row[0] if deal_row else 0
            deal_total = float(deal_row[1]) if deal_row else 0

            interaction_r = db.execute(text(
                "SELECT COUNT(*) FROM silver.fact_interactions WHERE account_name ILIKE :name"
            ), {"name": f"%{name}%"})
            interaction_count = interaction_r.scalar() or 0

            enriched.append({
                **acc,
                "contact_count": contact_count,
                "deal_count": deal_count,
                "deal_total_value": deal_total,
                "interaction_count": interaction_count,
            })

        return {"status": "success", "accounts": enriched, "total": len(enriched)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/accounts/{account_id}")
async def get_account_detail(account_id: int, db: Session = Depends(get_db)):
    """Get full detail for a single account"""
    try:
        acc_r = db.execute(text("SELECT * FROM silver.dim_account WHERE id = :id"), {"id": account_id})
        acc_row = acc_r.fetchone()
        if not acc_row:
            raise HTTPException(status_code=404, detail="Account not found")
        acc = dict(zip(acc_r.keys(), acc_row))
        name = acc.get("account_name", "")

        contacts_r = db.execute(text(
            "SELECT * FROM silver.dim_contact WHERE account_name ILIKE :name ORDER BY id DESC"
        ), {"name": f"%{name}%"})
        contacts = [dict(zip(contacts_r.keys(), r)) for r in contacts_r.fetchall()]

        deals_r = db.execute(text(
            "SELECT * FROM silver.fact_deals WHERE account_name ILIKE :name ORDER BY id DESC"
        ), {"name": f"%{name}%"})
        deals = [dict(zip(deals_r.keys(), r)) for r in deals_r.fetchall()]

        interactions_r = db.execute(text(
            "SELECT * FROM silver.fact_interactions WHERE account_name ILIKE :name ORDER BY id DESC LIMIT 20"
        ), {"name": f"%{name}%"})
        interactions = [dict(zip(interactions_r.keys(), r)) for r in interactions_r.fetchall()]

        insights_r = db.execute(text(
            "SELECT * FROM silver.fact_insights WHERE account_name ILIKE :name ORDER BY id DESC LIMIT 20"
        ), {"name": f"%{name}%"})
        insights = [dict(zip(insights_r.keys(), r)) for r in insights_r.fetchall()]

        return {
            "status": "success",
            "account": acc,
            "contacts": contacts,
            "deals": deals,
            "interactions": interactions,
            "insights": insights,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/pipeline")
async def get_pipeline(db: Session = Depends(get_db)):
    """Get all deals grouped by stage for pipeline view"""
    try:
        result = db.execute(text("SELECT * FROM silver.fact_deals ORDER BY id DESC"))
        rows = result.fetchall()
        columns = result.keys()
        deals = [dict(zip(columns, row)) for row in rows]

        stages = {}
        for deal in deals:
            stage = deal.get("deal_stage") or "Unknown"
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(deal)

        return {"status": "success", "stages": stages, "total_deals": len(deals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/insights")
async def get_insights(db: Session = Depends(get_db)):
    """Get recent insights feed"""
    try:
        result = db.execute(text("SELECT * FROM silver.fact_insights ORDER BY id DESC LIMIT 50"))
        rows = result.fetchall()
        columns = result.keys()
        insights = [dict(zip(columns, row)) for row in rows]

        return {"status": "success", "insights": insights, "total": len(insights)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get overview statistics for the dashboard"""
    try:
        accounts = db.execute(text("SELECT COUNT(*) FROM silver.dim_account")).scalar() or 0
        contacts = db.execute(text("SELECT COUNT(*) FROM silver.dim_contact")).scalar() or 0
        deals = db.execute(text("SELECT COUNT(*) FROM silver.fact_deals")).scalar() or 0
        interactions = db.execute(text("SELECT COUNT(*) FROM silver.fact_interactions")).scalar() or 0
        insights = db.execute(text("SELECT COUNT(*) FROM silver.fact_insights")).scalar() or 0

        deal_value_r = db.execute(text(
            "SELECT COALESCE(SUM(CASE WHEN deal_value ~ '^[0-9.]+$' THEN CAST(deal_value AS NUMERIC) ELSE 0 END), 0) FROM silver.fact_deals"
        ))
        total_deal_value = float(deal_value_r.scalar() or 0)

        return {
            "status": "success",
            "stats": {
                "accounts": accounts,
                "contacts": contacts,
                "deals": deals,
                "interactions": interactions,
                "insights": insights,
                "total_deal_value": total_deal_value,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Gold Layer Endpoints — Pre-aggregated Business Marts
# These answer specific business questions directly from Gold tables.
# =========================================================================

@router.get("/dashboard/gold/revenue-summary")
async def get_gold_revenue_summary(db: Session = Depends(get_db)):
    """Gold: Total revenue, won value, pipeline value per account"""
    try:
        result = db.execute(text("""
            SELECT account_name, industry, geography,
                   total_deal_value, won_value, pipeline_value,
                   deal_count, won_count, avg_deal_size, refreshed_at
            FROM gold.revenue_summary
            ORDER BY total_deal_value DESC
        """))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
        return {"status": "success", "data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/gold/top-customers")
async def get_gold_top_customers(db: Session = Depends(get_db)):
    """Gold: Top customers ranked by deal value — the KPI mart"""
    try:
        result = db.execute(text("""
            SELECT rank, account_name, industry, geography,
                   total_deal_value, won_value, open_deals,
                   contacts_count, last_interaction, refreshed_at
            FROM gold.top_customers
            ORDER BY rank ASC
        """))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
        return {"status": "success", "data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/gold/pipeline-health")
async def get_gold_pipeline_health(db: Session = Depends(get_db)):
    """Gold: Pipeline funnel — deals and value by stage"""
    try:
        result = db.execute(text("""
            SELECT stage, deal_count, total_value, avg_deal_size,
                   accounts_in_stage, refreshed_at
            FROM gold.pipeline_health
            ORDER BY total_value DESC
        """))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
        return {"status": "success", "data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/gold/account-360")
async def get_gold_account_360(db: Session = Depends(get_db)):
    """Gold: Full 360 view per account — everything in one row"""
    try:
        result = db.execute(text("""
            SELECT account_name, industry, geography, employee_count,
                   annual_revenue, website, total_deal_value,
                   open_deal_count, won_deal_count, contact_count,
                   interaction_count, insight_count, primary_contact,
                   latest_deal_stage, latest_sentiment, refreshed_at
            FROM gold.account_360
            ORDER BY total_deal_value DESC
        """))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
        return {"status": "success", "data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/gold/activity-summary")
async def get_gold_activity_summary(db: Session = Depends(get_db)):
    """Gold: Engagement activity per account — interactions and sentiment"""
    try:
        result = db.execute(text("""
            SELECT account_name, total_interactions,
                   positive_interactions, negative_interactions,
                   neutral_interactions, total_insights,
                   competitive_flags, refreshed_at
            FROM gold.activity_summary
            ORDER BY total_interactions DESC
        """))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
        return {"status": "success", "data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/gold/deals-closing-soon")
async def get_gold_deals_closing_soon(db: Session = Depends(get_db)):
    """Gold: Deals with upcoming close dates — sorted by urgency"""
    try:
        result = db.execute(text("""
            SELECT deal_name, account_name, deal_value, deal_stage,
                   close_date, probability, contact_name,
                   days_until_close, refreshed_at
            FROM gold.deals_closing_soon
            ORDER BY days_until_close ASC NULLS LAST
        """))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
        return {"status": "success", "data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/gold/at-risk-accounts")
async def get_gold_at_risk_accounts(db: Session = Depends(get_db)):
    """Gold: Accounts with no recent activity — sorted by risk level"""
    try:
        result = db.execute(text("""
            SELECT account_name, industry, geography,
                   open_deal_count, open_deal_value,
                   last_interaction_date, days_since_last_contact,
                   last_sentiment, risk_level, refreshed_at
            FROM gold.at_risk_accounts
            ORDER BY
                CASE risk_level
                    WHEN 'No Contact'  THEN 1
                    WHEN 'High Risk'   THEN 2
                    WHEN 'Medium Risk' THEN 3
                    ELSE 4
                END,
                days_since_last_contact DESC NULLS FIRST
        """))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
        return {"status": "success", "data": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/gold/refresh")
async def refresh_gold_layer(db: Session = Depends(get_db)):
    """Manually trigger Gold layer refresh — rebuilds all 7 aggregation marts"""
    try:
        gold = GoldLayerBuilder(db)
        results = gold.refresh_all()
        stats = gold.get_gold_stats()
        return {"status": "success", "refreshed": results, "row_counts": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Gold Schema Agent - Proposal Management Endpoints
# =============================================================================

@router.get("/gold/proposals/pending")
async def get_pending_proposals(limit: int = 10, db: Session = Depends(get_db)):
    """
    Get pending Gold schema proposals for human review.
    These are AI-generated suggestions for new Gold tables or columns.
    """
    try:
        from app.services.gold_schema_agent import GoldSchemaAgent
        agent = GoldSchemaAgent(db)
        proposals = agent.get_pending_proposals(limit=limit)
        return {
            "status": "success",
            "count": len(proposals),
            "proposals": proposals
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gold/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    reviewer: str = Form(..., description="Name of reviewer"),
    notes: str = Form(default="", description="Review notes"),
    db: Session = Depends(get_db)
):
    """
    Approve a Gold schema proposal.
    After approval, engineer implements the DDL/SQL manually.
    """
    try:
        from app.services.gold_schema_agent import GoldSchemaAgent
        agent = GoldSchemaAgent(db)
        success = agent.approve_proposal(proposal_id, reviewer, notes)
        if success:
            return {
                "status": "success",
                "message": f"Proposal {proposal_id} approved by {reviewer}"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to approve proposal")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gold/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: int,
    reviewer: str = Form(..., description="Name of reviewer"),
    notes: str = Form(..., description="Reason for rejection"),
    db: Session = Depends(get_db)
):
    """
    Reject a Gold schema proposal.
    Provide notes explaining why it's not needed.
    """
    try:
        from app.services.gold_schema_agent import GoldSchemaAgent
        agent = GoldSchemaAgent(db)
        success = agent.reject_proposal(proposal_id, reviewer, notes)
        if success:
            return {
                "status": "success",
                "message": f"Proposal {proposal_id} rejected by {reviewer}"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to reject proposal")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Vector Store Endpoints — Semantic search over unstructured documents
# =============================================================================

@router.post("/vector/search")
async def vector_search(
    query: str = Form(..., description="Natural language question to search documents"),
    account_name: Optional[str] = Form(default=None, description="Filter to a specific account"),
    top_k: int = Form(default=5, description="Number of document chunks to return"),
):
    """
    Semantic search over Pinecone-indexed documents (PDFs, TXT, DOCX).
    Returns the most relevant document excerpts for a given question.
    """
    try:
        from app.services.vector_store import VectorStoreService
        svc = VectorStoreService()
        if not svc.is_available():
            return {
                "status": "unavailable",
                "message": "Pinecone is not configured. Set PINECONE_API_KEY in your .env file.",
                "results": [],
            }
        results = svc.search(query=query, account_name=account_name, top_k=top_k)
        return {
            "status": "success",
            "query": query,
            "account_filter": account_name,
            "total": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector/stats")
async def vector_stats():
    """
    Return Pinecone index statistics: total vectors indexed, dimension, etc.
    """
    try:
        from app.services.vector_store import VectorStoreService
        svc = VectorStoreService()
        stats = svc.get_stats()
        return {"status": "success", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gold/proposals/{proposal_id}/implement")
async def mark_proposal_implemented(proposal_id: int, db: Session = Depends(get_db)):
    """
    Mark a proposal as implemented (after DDL is manually applied).
    This updates the proposal status and records implementation time.
    """
    try:
        from app.services.gold_schema_agent import GoldSchemaAgent
        agent = GoldSchemaAgent(db)
        success = agent.mark_implemented(proposal_id)
        if success:
            return {
                "status": "success",
                "message": f"Proposal {proposal_id} marked as implemented"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to mark proposal implemented")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
