-- Migration: Add ThoughtFocus-specific dimension columns to existing silver tables
-- Safe to run repeatedly — uses ADD COLUMN IF NOT EXISTS pattern via DO blocks.

-- ═══ dim_account: add vertical ═══
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'dim_account' AND column_name = 'vertical'
    ) THEN
        ALTER TABLE silver.dim_account ADD COLUMN vertical TEXT;
        RAISE NOTICE 'Added vertical to silver.dim_account';
    END IF;
END $$;

-- ═══ fact_deals: add TF dimensions ═══
DO $$
DECLARE
    cols TEXT[] := ARRAY[
        'vertical', 'horizontal', 'engagement_model', 'opportunity_stage',
        'ai_influenced', 'business_type', 'lead_source', 'salesperson', 'geography'
    ];
    col TEXT;
BEGIN
    FOREACH col IN ARRAY cols
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'silver' AND table_name = 'fact_deals' AND column_name = col
        ) THEN
            EXECUTE format('ALTER TABLE silver.fact_deals ADD COLUMN %I TEXT', col);
            RAISE NOTICE 'Added % to silver.fact_deals', col;
        END IF;
    END LOOP;
END $$;
