-- Gold Layer Schema Initialization
-- Run this once to create all Gold mart tables
-- Dimensions aligned to ThoughtFocus business model:
--   Verticals:        Mortgage & Lending, Banking & Insurance, Capital Market,
--                     Higher Education, Technology, Payments
--   Horizontals:      AI & Data, Application Engineering, Digital Operations
--   Geography:        Onshore / Offshore / Both
--   Engagement Model: T&M, Fixed, Retainers, Outcome-based
--   Opportunity Stage: P0 (won) → P10 (cold prospect)

CREATE SCHEMA IF NOT EXISTS gold;

-- ── Fix stale UNIQUE constraints from earlier schema versions ──
-- These single-column constraints conflict with multi-dimension GROUP BY.
-- Safe: IF EXISTS means no error on fresh DBs.
DO $$ BEGIN
    ALTER TABLE gold.revenue_summary DROP CONSTRAINT IF EXISTS revenue_summary_account_name_key;
    ALTER TABLE gold.pipeline_health DROP CONSTRAINT IF EXISTS pipeline_health_stage_key;
    ALTER TABLE gold.salesperson_performance DROP CONSTRAINT IF EXISTS salesperson_performance_salesperson_key;
    ALTER TABLE gold.vertical_revenue DROP CONSTRAINT IF EXISTS vertical_revenue_vertical_key;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- 1. Revenue Summary — total deal value per account, segmented by stage and TF dimensions
CREATE TABLE IF NOT EXISTS gold.revenue_summary (
    id                   SERIAL PRIMARY KEY,
    account_name         TEXT NOT NULL,
    industry             TEXT,
    geography            TEXT,
    vertical             TEXT,
    horizontal           TEXT,
    engagement_model     TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    pipeline_value       NUMERIC DEFAULT 0,
    ai_influenced_value  NUMERIC DEFAULT 0,
    deal_count           INTEGER DEFAULT 0,
    won_count            INTEGER DEFAULT 0,
    ai_influenced_count  INTEGER DEFAULT 0,
    avg_deal_size        NUMERIC DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_name, vertical, horizontal, engagement_model)
);

-- 2. Top Customers — ranked by total deal value (KPI mart)
CREATE TABLE IF NOT EXISTS gold.top_customers (
    id                   SERIAL PRIMARY KEY,
    rank                 INTEGER,
    account_name         TEXT NOT NULL,
    industry             TEXT,
    geography            TEXT,
    vertical             TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    open_deals           INTEGER DEFAULT 0,
    contacts_count       INTEGER DEFAULT 0,
    last_interaction     TEXT,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_name)
);

-- 3. Pipeline Health — deals grouped by stage with TF dimensions
CREATE TABLE IF NOT EXISTS gold.pipeline_health (
    id                   SERIAL PRIMARY KEY,
    stage                TEXT NOT NULL,
    opportunity_stage    TEXT,
    vertical             TEXT,
    horizontal           TEXT,
    deal_count           INTEGER DEFAULT 0,
    total_value          NUMERIC DEFAULT 0,
    avg_deal_size        NUMERIC DEFAULT 0,
    accounts_in_stage    INTEGER DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (stage, opportunity_stage, vertical, horizontal)
);

-- 4. Account 360 — one row per account, everything in one place
CREATE TABLE IF NOT EXISTS gold.account_360 (
    id                   SERIAL PRIMARY KEY,
    account_name         TEXT NOT NULL,
    industry             TEXT,
    geography            TEXT,
    vertical             TEXT,
    employee_count       TEXT,
    annual_revenue       TEXT,
    website              TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    open_deal_count      INTEGER DEFAULT 0,
    won_deal_count       INTEGER DEFAULT 0,
    ai_influenced_count  INTEGER DEFAULT 0,
    contact_count        INTEGER DEFAULT 0,
    interaction_count    INTEGER DEFAULT 0,
    insight_count        INTEGER DEFAULT 0,
    primary_contact      TEXT,
    latest_deal_stage    TEXT,
    latest_sentiment     TEXT,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_name)
);

-- 5. Activity Summary — how engaged are we with each account?
CREATE TABLE IF NOT EXISTS gold.activity_summary (
    id                   SERIAL PRIMARY KEY,
    account_name         TEXT NOT NULL,
    vertical             TEXT,
    total_interactions   INTEGER DEFAULT 0,
    positive_interactions INTEGER DEFAULT 0,
    negative_interactions INTEGER DEFAULT 0,
    neutral_interactions  INTEGER DEFAULT 0,
    total_insights        INTEGER DEFAULT 0,
    competitive_flags     INTEGER DEFAULT 0,
    avg_sentiment_score   TEXT,
    refreshed_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_name)
);

-- 6. Deals Closing Soon — pipeline urgency view with TF dimensions
CREATE TABLE IF NOT EXISTS gold.deals_closing_soon (
    id                   SERIAL PRIMARY KEY,
    deal_name            TEXT,
    account_name         TEXT,
    deal_value           TEXT,
    deal_stage           TEXT,
    opportunity_stage    TEXT,
    vertical             TEXT,
    horizontal           TEXT,
    engagement_model     TEXT,
    ai_influenced        TEXT,
    salesperson          TEXT,
    close_date           TEXT,
    probability          TEXT,
    contact_name         TEXT,
    days_until_close     INTEGER,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. At-Risk Accounts — accounts with no recent activity
CREATE TABLE IF NOT EXISTS gold.at_risk_accounts (
    id                        SERIAL PRIMARY KEY,
    account_name              TEXT NOT NULL,
    industry                  TEXT,
    geography                 TEXT,
    vertical                  TEXT,
    open_deal_count           INTEGER DEFAULT 0,
    open_deal_value           NUMERIC DEFAULT 0,
    last_interaction_date     TEXT,
    days_since_last_contact   INTEGER,
    last_sentiment            TEXT,
    risk_level                TEXT,
    refreshed_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_name)
);

-- 8. Salesperson Performance — deals and revenue per salesperson
CREATE TABLE IF NOT EXISTS gold.salesperson_performance (
    id                   SERIAL PRIMARY KEY,
    salesperson          TEXT NOT NULL,
    vertical             TEXT,
    horizontal           TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    pipeline_value       NUMERIC DEFAULT 0,
    deal_count           INTEGER DEFAULT 0,
    won_count            INTEGER DEFAULT 0,
    ai_influenced_count  INTEGER DEFAULT 0,
    avg_deal_size        NUMERIC DEFAULT 0,
    avg_close_days       NUMERIC,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (salesperson, vertical, horizontal)
);

-- 9. Vertical Revenue — revenue breakdown by TF vertical
CREATE TABLE IF NOT EXISTS gold.vertical_revenue (
    id                   SERIAL PRIMARY KEY,
    vertical             TEXT NOT NULL,
    horizontal           TEXT,
    geography            TEXT,
    engagement_model     TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    pipeline_value       NUMERIC DEFAULT 0,
    ai_influenced_value  NUMERIC DEFAULT 0,
    deal_count           INTEGER DEFAULT 0,
    won_count            INTEGER DEFAULT 0,
    avg_deal_size        NUMERIC DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (vertical, horizontal, geography, engagement_model)
);

-- 10. AI Influence Summary — AI-influenced vs non-AI deal breakdown
CREATE TABLE IF NOT EXISTS gold.ai_influence_summary (
    id                   SERIAL PRIMARY KEY,
    ai_influenced        TEXT NOT NULL,
    vertical             TEXT,
    horizontal           TEXT,
    business_type        TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    pipeline_value       NUMERIC DEFAULT 0,
    deal_count           INTEGER DEFAULT 0,
    won_count            INTEGER DEFAULT 0,
    avg_deal_size        NUMERIC DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. Win/Loss Analysis — win rates and loss analysis by dimension
CREATE TABLE IF NOT EXISTS gold.win_loss_analysis (
    id                   SERIAL PRIMARY KEY,
    vertical             TEXT,
    horizontal           TEXT,
    salesperson          TEXT,
    total_closed         INTEGER DEFAULT 0,
    won_count            INTEGER DEFAULT 0,
    lost_count           INTEGER DEFAULT 0,
    win_rate             NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    lost_value           NUMERIC DEFAULT 0,
    avg_won_deal_size    NUMERIC DEFAULT 0,
    avg_lost_deal_size   NUMERIC DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Deal Velocity — avg days deals spend in the pipeline
CREATE TABLE IF NOT EXISTS gold.deal_velocity (
    id                   SERIAL PRIMARY KEY,
    deal_stage           TEXT,
    vertical             TEXT,
    engagement_model     TEXT,
    deal_count           INTEGER DEFAULT 0,
    avg_days_in_stage    NUMERIC,
    avg_deal_value       NUMERIC DEFAULT 0,
    total_value          NUMERIC DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 13. Geography Mix — revenue split by onshore / offshore
CREATE TABLE IF NOT EXISTS gold.geography_mix (
    id                   SERIAL PRIMARY KEY,
    geography            TEXT NOT NULL,
    vertical             TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    pipeline_value       NUMERIC DEFAULT 0,
    deal_count           INTEGER DEFAULT 0,
    won_count            INTEGER DEFAULT 0,
    account_count        INTEGER DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 14. Lead Source Effectiveness — which lead sources produce most value
CREATE TABLE IF NOT EXISTS gold.lead_source_effectiveness (
    id                   SERIAL PRIMARY KEY,
    lead_source          TEXT NOT NULL,
    vertical             TEXT,
    total_deal_value     NUMERIC DEFAULT 0,
    won_value            NUMERIC DEFAULT 0,
    deal_count           INTEGER DEFAULT 0,
    won_count            INTEGER DEFAULT 0,
    win_rate             NUMERIC DEFAULT 0,
    avg_deal_size        NUMERIC DEFAULT 0,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. Stale Deals — open deals with no recent updates
CREATE TABLE IF NOT EXISTS gold.stale_deals (
    id                   SERIAL PRIMARY KEY,
    deal_name            TEXT,
    account_name         TEXT,
    deal_value           TEXT,
    deal_stage           TEXT,
    opportunity_stage    TEXT,
    vertical             TEXT,
    salesperson          TEXT,
    close_date           TEXT,
    days_since_update    INTEGER,
    staleness_level      TEXT,
    refreshed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
