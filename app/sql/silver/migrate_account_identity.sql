-- Account Identity Layer Migration
-- Adds account_id FK to fact tables and creates account_source_map for multi-source identity tracking.
-- dim_account.id (existing SERIAL PK) serves as the canonical account_id.

-- 1. Create account_source_map table
CREATE TABLE IF NOT EXISTS silver.account_source_map (
    id              SERIAL PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES silver.dim_account(id) ON DELETE CASCADE,
    source          VARCHAR(50) NOT NULL,
    source_name     TEXT NOT NULL,
    source_id       TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_id, source, source_name)
);

-- 2. Add account_id to fact_deals
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'fact_deals' AND column_name = 'account_id'
    ) THEN
        ALTER TABLE silver.fact_deals ADD COLUMN account_id INTEGER REFERENCES silver.dim_account(id);
    END IF;
END $$;

-- 3. Add account_id to fact_interactions
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'fact_interactions' AND column_name = 'account_id'
    ) THEN
        ALTER TABLE silver.fact_interactions ADD COLUMN account_id INTEGER REFERENCES silver.dim_account(id);
    END IF;
END $$;

-- 4. Add account_id to fact_insights
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'fact_insights' AND column_name = 'account_id'
    ) THEN
        ALTER TABLE silver.fact_insights ADD COLUMN account_id INTEGER REFERENCES silver.dim_account(id);
    END IF;
END $$;

-- 5. Backfill account_id from existing account_name data
UPDATE silver.fact_deals fd
SET account_id = da.id
FROM silver.dim_account da
WHERE LOWER(TRIM(da.account_name)) = LOWER(TRIM(fd.account_name))
  AND fd.account_id IS NULL;

UPDATE silver.fact_interactions fi
SET account_id = da.id
FROM silver.dim_account da
WHERE LOWER(TRIM(da.account_name)) = LOWER(TRIM(fi.account_name))
  AND fi.account_id IS NULL;

UPDATE silver.fact_insights fins
SET account_id = da.id
FROM silver.dim_account da
WHERE LOWER(TRIM(da.account_name)) = LOWER(TRIM(fins.account_name))
  AND fins.account_id IS NULL;

-- 6. Seed account_source_map from existing dim_account records
INSERT INTO silver.account_source_map (account_id, source, source_name)
SELECT id, 'legacy', account_name
FROM silver.dim_account
WHERE account_name IS NOT NULL AND account_name != ''
ON CONFLICT (account_id, source, source_name) DO NOTHING;

-- 7. Create index for faster identity resolution lookups
CREATE INDEX IF NOT EXISTS idx_dim_account_name_lower
    ON silver.dim_account (LOWER(TRIM(account_name)));

CREATE INDEX IF NOT EXISTS idx_fact_deals_account_id
    ON silver.fact_deals (account_id);

CREATE INDEX IF NOT EXISTS idx_fact_interactions_account_id
    ON silver.fact_interactions (account_id);

CREATE INDEX IF NOT EXISTS idx_fact_insights_account_id
    ON silver.fact_insights (account_id);

CREATE INDEX IF NOT EXISTS idx_account_source_map_account_id
    ON silver.account_source_map (account_id);
