-- Add content, confidence, and insight_date columns to silver.fact_insights
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'fact_insights' AND column_name = 'content'
    ) THEN
        ALTER TABLE silver.fact_insights ADD COLUMN content TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'fact_insights' AND column_name = 'confidence'
    ) THEN
        ALTER TABLE silver.fact_insights ADD COLUMN confidence TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'fact_insights' AND column_name = 'insight_date'
    ) THEN
        ALTER TABLE silver.fact_insights ADD COLUMN insight_date TEXT;
    END IF;
END $$;
