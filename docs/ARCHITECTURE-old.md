# Sales Agent — Architecture

## Overview

Sales Agent is an AI-powered semantic layer for sales teams. It ingests data from multiple sources (CRM exports, meeting transcripts, file uploads), normalizes it into a queryable structure, and lets users ask natural language questions about their accounts, deals, contacts, and meetings.

Built with **FastAPI** (Python) + **Next.js** (React) + **PostgreSQL**, following a **Medallion Architecture** (Bronze → Silver → Gold).

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                       DATA SOURCES                          │
│                                                             │
│  File Upload              API Ingest            CRM/ERP    │
│  (.pdf .csv .xlsx         (JSON payload)        Webhooks   │
│   .txt .docx)                                              │
└──────────┬────────────────────┬─────────────────────┬──────┘
           │                    │                     │
           ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER                         │
│                                                             │
│  FileParser ─────► detect_data_type ─────► IngestionEngine  │
│  (PDF/CSV/XLSX/         │                       │           │
│   TXT/DOCX)             │                       │           │
│                  ┌──────┴──────┐                │           │
│                  ▼             ▼                │           │
│          Unstructured    Structured             │           │
│          (transcript)    (CRM/ERP)              │           │
│               │              │                  │           │
│               ▼              ▼                  │           │
│      TranscriptProcessor  DataMapper            │           │
│      (GPT-4 or regex)    (JSON field maps)      │           │
│               │              │                  │           │
│               ▼              ▼                  │           │
│      classify_transcript  Deterministic         │           │
│      _data               Classification         │           │
│               │              │                  │           │
│               └──────┬───────┘                  │           │
│                      ▼                          │           │
│              SchemaEvolution                    │           │
│              (new fields → ALTER TABLE)          │           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  MEDALLION STORAGE                           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  BRONZE  —  bronze.raw_ingestion                      │  │
│  │  Immutable raw capture. Every payload saved as JSONB. │  │
│  └───────────────────────────┬───────────────────────────┘  │
│                              │                              │
│  ┌───────────────────────────▼───────────────────────────┐  │
│  │  SILVER  —  Normalized Entity Tables                  │  │
│  │                                                       │  │
│  │  silver.processed_data      (JSON audit trail)        │  │
│  │  silver.dim_account         (companies)               │  │
│  │  silver.dim_contact         (people)                  │  │
│  │  silver.fact_deals          (pipeline / opportunities)│  │
│  │  silver.fact_interactions   (meetings, calls, emails) │  │
│  │  silver.fact_insights       (deal signals, comp intel)│  │
│  │  silver.account_source_map  (identity → multi-source) │  │
│  │  silver.data_quality_issues (validation rejects)      │  │
│  └───────────────────────────┬───────────────────────────┘  │
│                              │                              │
│                   GoldLayerBuilder.refresh_all()             │
│                   (DELETE + INSERT from Silver SQL)          │
│                              │                              │
│  ┌───────────────────────────▼───────────────────────────┐  │
│  │  GOLD  —  Pre-aggregated Business Marts               │  │
│  │                                                       │  │
│  │  gold.revenue_summary      gold.top_customers         │  │
│  │  gold.pipeline_health      gold.account_360           │  │
│  │  gold.activity_summary     gold.deals_closing_soon    │  │
│  │  gold.at_risk_accounts     gold.schema_proposals      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     QUERY LAYER                             │
│                                                             │
│  NLQueryEngine                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  1. User asks natural language question                │ │
│  │  2. schema_introspector reads live DB catalog          │ │
│  │  3. GPT generates SQL (tries Gold tables first)       │ │
│  │  4. Execute SQL, collect results                       │ │
│  │  5. If Gold = 0 rows → fallback to Silver tables      │ │
│  │  6. If Silver = 0 rows → Bronze enrichment:           │ │
│  │     search bronze.raw_ingestion → LLM extract →       │ │
│  │     insert into Silver → refresh Gold → re-query      │ │
│  │  7. GPT synthesizes markdown answer from data          │ │
│  │  8. If no DB data but conversation history exists      │ │
│  │     → answer from conversation context                 │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  GoldSchemaAgent (background)                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  When Silver fallback occurs, proposes new Gold        │ │
│  │  tables/columns → gold.schema_proposals                │ │
│  │  (approve/reject/implement via API)                    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js)                      │
│                                                             │
│  SalesAssistant.js (App Shell)                              │
│  ├── OverviewPage     — Dashboard KPIs, gold-layer stats    │
│  ├── AccountsPage     — Account list + detail + scoped chat │
│  │                      (includes insights per account)     │
│  ├── PipelinePage     — Deal pipeline visualization         │
│  └── ChatPage         — Conversational AI + file upload     │
│                                                             │
│  lib/api.js           — All fetch() calls to backend        │
└─────────────────────────────────────────────────────────────┘
```

---

## Ingestion Pipeline (detailed)

### Unstructured Data (PDF, TXT, DOCX — meeting transcripts, notes)

```
File Upload
  → FileParser.parse()          extract text from binary format
  → is_sales_relevant()         keyword + entity check (skip if not sales data)
     ↳ NOT relevant:            save to Bronze only, return is_relevant: false
     ↳ force_process=true:      bypass check, proceed normally
  → detect_data_type()          identifies "raw_transcript" (has raw_transcript field)
  → save to Bronze              immutable raw capture
  → TranscriptProcessor         GPT-4 extracts 22 structured fields:
      ._extract_with_ai()         account_name, deal_name, deal_value, deal_stage,
                                   attendees, contacts, topics, sentiment, key_points,
                                   action_items, competitive_intel, deal_signals, etc.
      ._extract_with_fallback()   regex/heuristic backup if GPT fails (token limit, API down)
  → classify_transcript_data()  deterministic mapping of NLP output → 5 entity tables
  → IngestionEngine.process()   uses pre-built classification (no re-classification)
  → resolve_account_id()        identity layer: exact → lowercase → substring match
  → validate_record()           data validation: skip + log invalid records
  → Silver entity tables        dim_account, dim_contact, fact_deals,
                                 fact_interactions, fact_insights
  → GoldLayerBuilder.refresh()  rebuild all 7 gold marts
```

### Structured Data (CSV, XLSX — CRM exports, ERP data)

```
File Upload or API Ingest
  → FileParser.parse()          CSV → rows, Excel → rows
  → is_sales_relevant()         keyword + entity check (skip if not sales data)
     ↳ NOT relevant:            save to Bronze only, return is_relevant: false
     ↳ force_process=true:      bypass check, proceed normally
  → detect_data_type()          identifies "structured_data"
  → save to Bronze              immutable raw capture
  → DataMapper.classify()       deterministic field mapping via JSON configs:
                                   mappings/crm.json   (Salesforce, HubSpot, etc.)
                                   mappings/erp.json   (SAP, Oracle, NetSuite)
                                   mappings/hrms.json  (Workday, BambooHR)
  → SchemaEvolutionEngine       if unmapped fields found:
                                   AI decides target table → ALTER TABLE ADD COLUMN
  → resolve_account_id()        identity layer: match account_name → internal account_id
  → validate_record()           data validation: skip + log invalid records
  → IngestionEngine.process()   save audit trail → populate entity tables → refresh gold
```

---

## Query Flow (detailed)

```
User Question
  → NLQueryEngine.query()
  → Greeting check                skip DB if "hi" / "hello"
  → _query_with_fallback()
      Attempt 1 — Gold:           GPT generates SQL preferring gold.* tables
        → if rows returned        ✓ answer from Gold
      Attempt 2 — Silver:         force silver.dim_*/fact_* tables
        → if rows returned        ✓ answer from Silver (fallback_used = True)
      Attempt 3 — Bronze enrichment (only if both Gold & Silver returned 0 rows):
        → BronzeEnrichmentService.enrich()
            _fetch_relevant_bronze()   search bronze.raw_ingestion by keywords / recent
            _process_bronze_record()   TranscriptProcessor → classify → insert Silver
            GoldLayerBuilder.refresh_all()
        → _query_with_fallback()       re-run Gold/Silver query
  → _synthesize_answer()           GPT formats data as markdown
  → GoldSchemaAgent (if Silver fallback occurred with data)
  → Return answer + metadata
```

---

## Services Reference

| Service | Responsibility |
|---|---|
| `file_parser.py` | Converts uploaded bytes to `List[Dict]` (PDF, CSV, XLSX, TXT, DOCX) |
| `file_overview_service.py` | AI-generated summary of uploaded file shown in chat |
| `transcript_processor.py` | Raw text → 22 structured fields (GPT-4 with regex fallback) |
| `data_mapper.py` | Deterministic field→column mapping using per-source JSON configs |
| `ai_analyzer.py` | AI classification for unknown sources + transcript→table mapping |
| `ingestion_engine.py` | Orchestrates: classify → evolve schema → store → refresh gold |
| `schema_manager.py` | DDL, migrations, bronze/silver CRUD, entity table inserts/upserts, account identity resolution |
| `schema_evolution.py` | Detects unmapped fields, AI picks target table, ALTER TABLE |
| `data_validator.py` | Validates records before Silver insert; rejects go to `data_quality_issues`. Also provides `is_sales_relevant()` domain check for uploads |
| `canonical_schema.py` | Defines the 5 entity tables and their columns (the schema contract) |
| `schema_introspector.py` | Reads live DB catalog to build dynamic prompts for SQL generation |
| `nl_query_engine.py` | Natural language → SQL → execute → human-readable answer; triggers Bronze enrichment when no data found |
| `bronze_enrichment.py` | Searches Bronze for relevant raw records, extracts structured data via LLM, inserts into Silver |
| `gold_layer.py` | Creates and refreshes the 7 gold aggregation marts |
| `gold_schema_agent.py` | Proposes new gold tables/columns when silver fallback occurs |

---

## Database Schema

### Bronze (raw capture)
```
bronze.raw_ingestion
  ├── id            SERIAL PRIMARY KEY
  ├── source        VARCHAR(255)        -- "user_upload", "crm", "erp"
  ├── data_type     VARCHAR(50)         -- "raw_transcript" or "structured_data"
  ├── raw_payload   JSONB               -- full original record, untouched
  └── created_at    TIMESTAMP
```

### Silver (normalized entities)

**Dimensions:**
```
silver.dim_account
  ├── id             SERIAL PRIMARY KEY   ← canonical account_id used by all fact tables
  ├── account_name   TEXT NOT NULL (UNIQUE)
  ├── industry, geography, annual_revenue, employee_count, website
  └── source_data    TEXT (full original record as JSON)

silver.dim_contact
  ├── contact_name   TEXT NOT NULL
  ├── account_name   TEXT (FK)
  ├── role
  └── source_data    TEXT
  UNIQUE(contact_name, account_name)
```

**Facts:**
```
silver.fact_deals
  ├── account_id     INTEGER (FK → dim_account.id)   ← identity layer
  ├── deal_name, account_name, deal_value, deal_stage
  ├── probability, close_date, contact_name
  └── source_data    TEXT

silver.fact_interactions
  ├── account_id     INTEGER (FK → dim_account.id)   ← identity layer
  ├── account_name, interaction_date, sentiment
  └── source_data    TEXT

silver.fact_insights
  ├── account_id     INTEGER (FK → dim_account.id)   ← identity layer
  ├── account_name, insight_type
  ├── content        TEXT    -- human-readable insight with reasoning
  ├── confidence     TEXT    -- 0.0 to 1.0
  ├── insight_date   TEXT
  └── source_data    TEXT
```

**Identity & Quality:**
```
silver.account_source_map
  ├── account_id     INTEGER (FK → dim_account.id)
  ├── source         VARCHAR(50)    -- "user_upload", "crm", "legacy"
  ├── source_name    TEXT           -- the account name as it appeared in the source
  ├── source_id      TEXT           -- optional external ID
  UNIQUE(account_id, source, source_name)

silver.data_quality_issues
  ├── table_name     TEXT           -- which table the record was headed to
  ├── error_messages  TEXT[]        -- what failed validation
  ├── raw_record     JSONB          -- the full rejected record
  └── created_at     TIMESTAMP
```

### Gold (aggregated marts)
```
gold.revenue_summary        -- total revenue exposure per account (won + pipeline + avg deal size)
gold.top_customers          -- all accounts ranked by total deal value
gold.pipeline_health        -- open deal stage distribution + values
gold.account_360            -- full account profile (deals + contacts + interactions + insights)
gold.activity_summary       -- interaction frequency + sentiment + competitive flags per account
gold.deals_closing_soon     -- all open deals with a close date, ordered soonest first
gold.at_risk_accounts       -- accounts with open deals and no recent contact (30d/60d thresholds)
gold.schema_proposals       -- AI-suggested gold schema improvements

See GOLD_DEFINITIONS.md for detailed business definitions of each table.
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy, OpenAI GPT-4 |
| **Frontend** | Next.js 16, React, Tailwind CSS, Lucide Icons |
| **Database** | PostgreSQL (bronze/silver/gold schemas) |
| **AI** | OpenAI GPT-4 (transcript extraction, SQL generation, answer synthesis) |
| **File Parsing** | PyPDF2, openpyxl, python-docx |

---

## Design Principles

1. **Deterministic first, AI second** — Field mapping uses exact JSON configs. AI only kicks in when deterministic mapping fails or for transcript extraction.

2. **Never lose data** — Bronze layer captures every raw payload. Silver `source_data` columns preserve the full original record as JSON. Schema evolution adds columns rather than dropping fields. Invalid records are logged to `data_quality_issues`, not silently dropped.

3. **Gold → Silver → Bronze enrichment** — The NL query engine tries pre-aggregated Gold marts first for fast answers, falls back to Silver entity tables, and if still empty, extracts data from Bronze raw records into Silver (one-time enrichment per query) before re-running the query.

4. **Schema evolves, not breaks** — When new fields appear in uploaded data, `SchemaEvolutionEngine` adds columns to existing tables rather than creating new ones.

5. **Conversation-aware** — The query engine uses conversation history to answer follow-up questions, including answering from file overviews when database queries return no results.

6. **Identity over strings** — Fact tables reference accounts via `account_id` (FK to `dim_account.id`) instead of raw name strings. The identity layer resolves names through exact match, case-insensitive match, and substring containment — so "HCC Corp" and "HCC" map to the same account without fuzzy matching libraries.

7. **Validate before Silver, never crash** — Every record is validated before insertion. Invalid records (missing required fields, non-numeric deal values) are skipped and logged to `silver.data_quality_issues` with full error details. Ingestion continues for all other records.

8. **Sales-domain gate** — Uploaded files are checked for sales relevance (keywords, roles, monetary values) before Silver processing. Irrelevant files are saved to Bronze only — the user is notified and can force-process if needed. No data is deleted or blocked from uploading.
