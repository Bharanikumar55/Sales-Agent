# Semantic Layer Service — Architecture & Implementation

> **Single source of truth.** This document covers the architecture, data flow, and design principles of the Semantic Layer Service.

---

## Table of Contents

1. [What This Service Does](#1-what-this-service-does)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Data Layer Design](#3-data-layer-design)
4. [How Ingestion Works](#4-how-ingestion-works)
5. [Engineer's Journey](#5-engineers-journey-from-business-question-to-schema)
6. [How Querying Works](#6-how-querying-works)
7. [Gold Schema Agent](#7-gold-schema-agent)
8. [AI Usage](#8-ai-usage)
9. [Does the Service Ask Clarifying Questions?](#9-does-the-service-ask-clarifying-questions)
10. [How Data Persists and Is Recalled After Days](#10-how-data-persists-and-is-recalled-after-days)
11. [How Multi-Account Comparison Works](#11-how-multi-account-comparison-works-eg-google-vs-microsoft)
12. [API Endpoints](#12-api-endpoints)
13. [Setup](#13-setup)
14. [Design Philosophy](#14-design-philosophy-human-defined-gold-vs-ai-enriched-silver)

---

## 1. What This Service Does

A FastAPI backend that ingests business data from multiple sources, normalises it into a three-layer medallion database, and lets users ask questions in plain English. A background AI agent continuously proposes improvements to the Gold layer so the system gets smarter over time without any manual schema work.

---

## 2. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                              │
│   CRM (Salesforce, HubSpot)       ERP (SAP, Oracle, Xero)         │
│   HRMS (Workday, BambooHR)        Meetings (Zoom, Teams)          │
└───────────────────────────┬────────────────────────────────────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │    FastAPI Layer     │
                 │  POST /data/ingest  │
                 └──────────┬──────────┘
                            │
            ┌───────────────┴────────────────┐
            │                                │
     Structured Data                  Raw Transcript
     Rule-based mapping               AI extracts entities
     (zero AI for known sources)      from raw text
            │                                │
            └───────────────┬────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────┐
         │             BRONZE LAYER             │
         │   Raw payload stored as-is           │
         │   Append-only — immutable baseline   │
         └──────────────────┬───────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────┐
         │             SILVER LAYER             │
         │   Normalised canonical entities      │
         │   dim_* tables (UPSERT)              │
         │   fact_* tables (INSERT)             │
         └──────────────────┬───────────────────┘
                            │
                            │  Gold rebuilt from Silver
                            │  after every ingest ↓
                            ▼
         ┌──────────────────────────────────────┐
         │              GOLD LAYER              │
         │   Pre-aggregated business marts      │
         │   One table per business question    │
         │   Always rebuilt fresh after ingest  │
         └──────────────────┬───────────────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │    FastAPI Layer     │
                 │  POST /query/ask    │
                 │  Plain English in   │
                 └──────────┬──────────┘
                            │
               ┌────────────┴─────────────┐
               │  Try Gold first          │
               │  Gold has answer?        │
               │                          │
               │  YES ──────────────────► Plain English answer
               │                          returned immediately
               │  NO (fallback)           │
               │   │                      │
               │   ▼                      │
               │  Query Silver instead    │
               │  Answer synthesised      │
               │  from Silver data        │
               │   │                      │
               │   ▼                      │
               │  Gold Schema Agent  ───► Proposes new Gold table
               │  fires in background     or new columns
               │  (non-blocking)          logged to schema_proposals
               └──────────────────────────┘
```

---

## 3. Data Layer Design

| Layer | Purpose | Write behaviour |
|---|---|---|
| **Bronze** | Raw payload stored exactly as received | Append-only, never modified |
| **Silver** | Normalised entities (`dim_*`, `fact_*`), identity map (`account_source_map`), quality log (`data_quality_issues`) | `dim_*` UPSERT, `fact_*` INSERT, fact tables link to accounts via `account_id` FK |
| **Gold** | Pre-aggregated business marts, one table per business question | Fully rebuilt from Silver after every ingest |

---

## 4. How Ingestion Works

- Structured data (CRM, ERP, HRMS) → deterministic field mapping, zero AI for known sources
- Raw transcript (Zoom, Teams) → GPT-4 extracts entities from text, then same mapping pipeline
- New unknown field → AI classifies it once, `ALTER TABLE` adds the column, deterministic forever after
- Account identity resolution: incoming account names matched to canonical `account_id` via exact, case-insensitive, and substring matching — tracked in `account_source_map`
- Data validation: every record checked before Silver insert; invalid records skipped and logged to `data_quality_issues`
- Domain relevance: uploaded files are checked for sales keywords/entities before processing; non-sales files saved to Bronze only (user can force-process)
- After every ingest: Bronze saved → Silver entity tables written → all Gold marts rebuilt
- Query-time enrichment: if a query finds no data in Gold or Silver, the system searches Bronze for relevant raw records, extracts structured data via LLM, inserts into Silver, refreshes Gold, and re-runs the query (once per query, never loops)

---

## 5. Engineer's Journey: From Business Question to Schema

This is the end-to-end workflow for building and evolving the semantic layer:

### Phase 1: Logic Definition (The Goal)
1. **Business Question**: Hear the new business question (e.g., "Who are our top customers?").
2. **Logic Design**: Instead of just mapping raw data, we first **decide on the business logic** needed to answer that question (e.g., "We will rank customers by descending sum of all deal values").

### Phase 2: Silver Selection (The Foundation)
1. **Canonical Column Identification**: Based on the logic above, we decide **what data to extract from raw data into Silver**. We define the specific columns that will internally help us build the Gold mart (e.g., `deal_value`, `account_name`).
2. **Schema Definition**: Ensure these canonical columns exist in the Silver schema.

### Phase 3: Data Extraction & Evolution
*   **Structured Data (CSV/CRM)**: Each time raw data comes in, we extract and map the necessary columns into Silver. 
    *   **Evolution**: If a CSV contains additional information not yet in our mapping, the **Schema Evolution Engine** loops in AI to decide if it's relevant and automatically places it in the best Silver table.
*   **Unstructured Data (Transcripts)**: We are **strictly selective**. AI only extracts the specific columns we've already defined for Silver. This ensures that the Silver layer remains 100% focused on business logic and isn't polluted by AI "noise" from raw text.

### Phase 4: Build Gold (The Answer)
Now that we have the clear business logic and the needed canonical columns populated in Silver, we **build the Gold Mart**. This table provides the 100% accurate, pre-aggregated answer that the UI displays.

### Phase 5: Continuous Optimization (The Bonus Point)
When a new business question comes tomorrow that our current Gold/Silver columns can't answer:
1. The system falls back to a deep-search of Silver tables.
2. **The Suggestion Engine**: In the background, the **Gold Schema Agent** identifies the missing answer. It analyzes the Silver fallback and **proposes a new Gold mapping** (SQL and DDL) in the `gold.schema_proposals` table.
3. This acts as an automated "suggestion table" for engineers, showing exactly which Silver columns are needed to answer the new question and build the next Gold mart.

---

## 6. How Querying Works

- User question sent to `POST /api/v1/query/ask`
- GPT-4 generates SQL preferring Gold tables → SQL runs → GPT-4 synthesises plain English answer
- If Gold returns zero rows → SQL regenerated against Silver → answer synthesised from Silver data
- On every Silver fallback → Gold Schema Agent fires in a background thread (non-blocking)
- Response always includes: `answer`, `sql_queries`, `data`, `fallback_used`, `execution_time_ms`

---

## 7. Gold Schema Agent

Fires in a background thread on every Silver fallback — never blocks the query response.

Reads the live Gold schema from the DB, looks at what Silver returned, asks GPT-4 to propose either a new Gold table or new columns on an existing one. Proposal is saved to `gold.schema_proposals` with status `pending_approval`. Nothing is auto-applied — an engineer reviews and implements approved proposals. Over time this progressively eliminates Silver fallbacks.

---

## 8. AI Usage

| Where | AI used | Frequency |
|---|---|---|
| CRM / ERP / HRMS ingestion | No | Never |
| Transcript ingestion | Yes — entity extraction | Once per transcript |
| Unknown source type | Yes — record classification | Once per unknown source |
| New unmapped field | Yes — table assignment | Once per field, ever |
| NL query → SQL | Yes | Once per query |
| SQL results → English answer | Yes | Once per query |
| Bronze enrichment | Yes — extract from raw docs when query has no data | At most once per query |
| Gold Schema Agent | Yes — background thread | Once per Silver fallback |

---

## 9. Clarifying Questions

**Not implemented.** The service does not ask the user follow-up questions. It always attempts an answer immediately. If the question is vague, GPT-4 generates its best-guess SQL. If nothing matches, the response returns empty data with `fallback_used: true`. The user rephrases and asks again. A conversational clarification loop is a future feature — not present today.

---

## 10. Data Persistence and Memory

All data is stored in PostgreSQL permanently — no expiry, no session cache. Data ingested today is queryable in two days or two years.

**Conversation memory is not implemented.** GPT-4 is stateless — every query is a fresh API call with no knowledge of previous questions. What persists is the data in the database, not any AI context. The database is the only memory.

> Adding conversation memory (e.g. storing past Q&A turns and passing them as context to GPT-4) is a planned enhancement. It would allow follow-up questions like "what about their deals?" without repeating the account name, and could reduce redundant SQL calls.

---

## 11. Multi-Account Comparison (e.g. Google vs Microsoft)

User asks: *"Compare Google and Microsoft"* via `POST /api/v1/query/ask`

1. **SQL generation (AI)** — GPT-4 generates SQL against Gold first (`gold.account_360`, `gold.revenue_summary`) filtering both accounts with `ILIKE`. If Gold is insufficient, falls back to Silver (`silver.fact_deals`, `silver.fact_interactions`, `silver.dim_account`)
2. **Execution (no AI)** — SQL runs against PostgreSQL, rows for both accounts returned
3. **Answer synthesis (AI)** — GPT-4 formats a side-by-side Markdown comparison from the returned rows

The answer quality depends entirely on what data was ingested. No data for an account = nothing to compare.

---

## 12. API Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/api/v1/data/ingest` | Ingest data from any source |
| `POST` | `/api/v1/data/upload` | Upload a CSV file |
| `POST` | `/api/v1/query/ask` | Ask a question in plain English |
| `POST` | `/api/v1/query` | Direct structured SQL query |
| `POST` | `/api/v1/schema/analyze` | Preview how data will map (no insert) |
| `GET` | `/api/v1/schema/info` | View current schema and row counts |
| `GET` | `/health` | Health check |

---

## 13. Setup

**Prerequisites:** Python 3.11+, PostgreSQL 13+, OpenAI API key

```bash
pip install -r requirements.txt
```

```env
# .env
DATABASE_URL=postgresql://postgres:password@localhost:5433/semantic_layer
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4
```

```bash
uvicorn app.main:app --reload --port 9000
```

Swagger UI at `http://localhost:9000/docs`

---

## 14. Design Philosophy: Human-Defined Gold vs. AI-Enriched Silver

A common question is: **"If AI can evolve the Silver layer, why can't it also auto-build the Gold layer?"**

### AI-Enriched Silver (The "What")
Silver is a direct 1-to-1 mapping from Raw data. It is "Self-Healing."
*   **Dynamic Mapper**: We use a mapper that reflects the current Silver schema. If a Silver table has a column and a raw file has that same column name, the mapper **automatically extracts it** without needing AI. 
*   **Simple Logic**: Silver asks: *"Does this name exist in the raw file?"* If yes → Extract. This is easy for AI to "evolve" once and then let the code take over.

### Human-Defined Gold (The "Why")
Gold is **Derived Logic**, which is much harder to automate reliably.
*   **Lost Context**: Even if AI builds a great Gold table today, there is no way for it to "store" that query in the project permanently. A human must "fix" the logic to ensure it doesn't change tomorrow.
*   **Derived Complexity**: Silver just looks for column names (direct). Gold creates "Derived Columns" (aggregates like `SUM`). You can't just look at a raw file and "know" how to build a Gold table; it requires knowing the **business intent** which AI cannot yet persist without human verification.
*   **The "Bonus" Middle Ground**: This is why we created the **Gold Schema Agent**. It **proposes** the logic to a human, who then approves and saves it.

**Conclusion**: We use AI to handle the *breadth* of data (Silver), but we rely on Humans to define the *meaning* of data (Gold). This ensures the Semantic Layer remains 100% reliable for executive reporting.

### Identity Layer & Data Quality

Two additional layers protect data integrity:

- **Account Identity**: Fact tables use `account_id` (FK to `dim_account.id`) instead of raw name strings. `resolve_account_id()` matches incoming names via exact → case-insensitive → substring containment, then records the mapping in `silver.account_source_map`. This means "HCC Corp" from a CRM export and "HCC" from a transcript resolve to the same canonical account without fuzzy matching libraries.

- **Data Validation**: Before any Silver insert, `validate_record()` checks required fields (e.g., `account_id` on all fact tables, `deal_name` on deals, numeric `deal_value`). Invalid records are skipped — not crashed on — and logged to `silver.data_quality_issues` with the full record and error list for review.
