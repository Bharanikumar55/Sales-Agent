# Sales Agent — Detailed Architecture (Aligned to Avinash's Agent Framework)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          SALES AGENT — FULL ARCHITECTURE                     │
│                    (Aligned to Avinash's Agent Framework)                     │
└──────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
 DATA SOURCES (External Systems)
═══════════════════════════════════════════════════════════════════════════════

  File Upload               API Ingest              CRM/ERP/HRMS
  (.pdf .csv .xlsx           (JSON payload)          Salesforce, NetSuite,
   .txt .docx)                                       Keka, etc.
       │                         │                        │
       └─────────────┬───────────┘────────────────────────┘
                     │
                     ▼
═══════════════════════════════════════════════════════════════════════════════
 FEEDER AGENT (IngestionEngine + DataMapper + TranscriptProcessor)
 "Feeds data from sources → Bronze → Silver → Gold"
 - Dumb for structured data (deterministic JSON field mapping)
 - Intelligent for unstructured data (GPT-4 extraction)
═══════════════════════════════════════════════════════════════════════════════
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
  Unstructured                Structured
  (transcripts,               (CSV, XLSX,
   meeting notes)              CRM exports)
        │                         │
        ▼                         ▼
  TranscriptProcessor         DataMapper
  (GPT-4 → 22 fields)        (crm.json / erp.json / hrms.json)
  (regex fallback)            (deterministic, zero AI)
        │                         │
        └────────────┬────────────┘
                     │
              is_sales_relevant()  ← domain gate (keyword + entity heuristic)
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  🥉 BRONZE LAYER — Immutable Raw Archive                           │
  │                                                                     │
  │  bronze.raw_ingestion                                               │
  │  ├── source       (user_upload / crm / erp)                         │
  │  ├── data_type    (raw_transcript / structured_data)                │
  │  ├── raw_payload  (JSONB — full original record, never touched)     │
  │  └── created_at                                                     │
  │                                                                     │
  │  POLICY: Every payload saved BEFORE any processing.                 │
  │          If AI makes a mistake, originals are always recoverable.   │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
                     ┌───────────┘
                     │
              ┌──────▼──────────────────────────────────────┐
              │  DQ AGENT (DataValidator)                    │
              │  Validates BEFORE Silver insertion:           │
              │  • Required field checks (NOT NULL)          │
              │  • Numeric format validation                 │
              │  • TF enum validation (verticals, stages)    │
              │  • Date format checks                        │
              │  • Completeness scoring per record & batch   │
              │  • Rejects → silver.data_quality_issues      │
              │  POLICY: validate → warn → log, never block  │
              └──────┬──────────────────────────────────────┘
                     │
              Identity Resolution (resolve_account_id)
              exact match → case-insensitive → substring
              Maps "HCC", "HCC Corp", "hcc" → same account_id
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  🥈 SILVER LAYER — Normalized Entity Tables (Star Schema)          │
  │                                                                     │
  │  DIMENSIONS:                                                        │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  silver.dim_account     Companies & profiles                │    │
  │  │    account_name, industry, geography, vertical,             │    │
  │  │    annual_revenue, employee_count, website                  │    │
  │  │                                                             │    │
  │  │  silver.dim_contact     People & roles                      │    │
  │  │    contact_name, account_name (FK), role                    │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                     │
  │  FACTS:                                                             │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  silver.fact_deals      Sales pipeline + TF dimensions      │    │
  │  │    account_id (FK), deal_name, deal_value, deal_stage,      │    │
  │  │    probability, close_date, contact_name,                   │    │
  │  │    ★ vertical, horizontal, engagement_model,                │    │
  │  │    ★ opportunity_stage (P0-P10), ai_influenced,             │    │
  │  │    ★ business_type, lead_source, salesperson                │    │
  │  │                                                             │    │
  │  │  silver.fact_interactions  Meetings, calls, emails          │    │
  │  │    account_id (FK), interaction_date, sentiment             │    │
  │  │                                                             │    │
  │  │  silver.fact_insights     AI-extracted signals              │    │
  │  │    account_id (FK), insight_type, content, confidence       │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                     │
  │  QUALITY & IDENTITY:                                                │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  silver.account_source_map    Multi-source identity layer   │    │
  │  │  silver.data_quality_issues   Validation rejects + audit    │    │
  │  │  silver.processed_data        JSON audit trail              │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
                   GoldLayerBuilder.refresh_all()
                   (DELETE + INSERT FROM silver SQL)
                   Runs after EVERY ingestion
                                 │
                                 ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  🥇 GOLD LAYER — 15 Pre-Aggregated Business Marts                 │
  │  All enriched with ThoughtFocus dimensions                          │
  │                                                                     │
  │  CORE METRICS (7):                                                  │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  revenue_summary         Revenue per account + TF dims      │    │
  │  │  top_customers           Ranked by deal value               │    │
  │  │  pipeline_health         Stage distribution + P0-P10        │    │
  │  │  account_360             Full profile per account           │    │
  │  │  activity_summary        Engagement per account             │    │
  │  │  deals_closing_soon      Upcoming close dates + salesperson │    │
  │  │  at_risk_accounts        Cold accounts needing attention    │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                     │
  │  TF-SPECIFIC ANALYTICS (5):                                         │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  salesperson_performance  Rep-level metrics                 │    │
  │  │  vertical_revenue         Revenue by Mortgage, Banking...   │    │
  │  │  ai_influence_summary     AI-influenced vs non-AI deals     │    │
  │  │  win_loss_analysis        Win rate by vertical/salesperson  │    │
  │  │  geography_mix            Onshore vs Offshore split         │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                     │
  │  OPERATIONAL INTELLIGENCE (3):                                      │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  deal_velocity            Avg days in stage / bottlenecks   │    │
  │  │  lead_source_effectiveness Which channels produce wins      │    │
  │  │  stale_deals              Stuck deals needing attention     │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                     │
  │  SCHEMA EVOLUTION:                                                  │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  gold.schema_proposals    AI-proposed improvements          │    │
  │  │  (GoldSchemaAgent stores executable DDL + refresh SQL)      │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
═══════════════════════════════════════════════════════════════════════════════
 SEEKER AGENT (NLQueryEngine + SchemaIntrospector)
 "Sits between chat-with-data and Gold layer"
 Builds semantic model from live DB schema → understands question intent
 → generates SQL → gets data → synthesizes readable answer
═══════════════════════════════════════════════════════════════════════════════
                                 │
        ┌────────────────────────┼───────────────────────┐
        ▼                        ▼                       ▼
  ┌──────────┐           ┌──────────────┐         ┌──────────────┐
  │ GOLD     │           │ SILVER       │         │ BRONZE       │
  │ (fast,   │  0 rows → │ (detailed,   │ 0 rows→ │ (enrichment, │
  │ pre-agg) │  fallback │ entity-level)│ fallback│ AI extract → │
  │          │           │              │         │ Silver → Gold │
  │          │           │              │         │ → re-query)   │
  └──────────┘           └──────────────┘         └──────────────┘
                                 │
        ┌────────────────────────┤
        ▼                        ▼
  Intent: METRIC            Intent: NARRATIVE
  (SQL → Gold/Silver)       (Vector search → Pinecone)
        │                        │
        ▼                        ▼
  GPT synthesizes            GPT synthesizes from
  from SQL rows              document chunks
        │                        │
        └───────────┬────────────┘
                    ▼
  ┌────────────────────────────────────────────┐
  │  GoldSchemaAgent (BUILDER concept)          │
  │  Fires in BACKGROUND when Silver fallback:  │
  │  • Reads current Gold SQL files from disk   │
  │  • Introspects live Silver schemas          │
  │  • Generates executable ALTER TABLE + SQL   │
  │  • Stores in gold.schema_proposals          │
  │  • Human approves → engineer deploys        │
  │  GOAL: Progressively eliminate fallbacks    │
  └────────────────────────────────────────────┘
                    │
                    ▼
═══════════════════════════════════════════════════════════════════════════════
 FRONTEND (Next.js)
═══════════════════════════════════════════════════════════════════════════════

  Dashboard        Accounts        Pipeline        Chat (AI Assistant)
  (KPIs, gold      (company        (deal           (NL questions,
   stats, health)   profiles,       tracker,        file upload,
                    scoped chat)    stages)         conversation)
```
