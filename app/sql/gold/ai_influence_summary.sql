-- Gold Mart: AI Influence Summary
-- Business Question: "How much of our revenue is AI-influenced?"
-- Source: silver.fact_deals

DELETE FROM gold.ai_influence_summary;

INSERT INTO gold.ai_influence_summary (
    ai_influenced, vertical, horizontal, business_type,
    total_deal_value, won_value, pipeline_value,
    deal_count, won_count, avg_deal_size, refreshed_at
)
SELECT
    COALESCE(fd.ai_influenced, 'Unknown') AS ai_influenced,
    fd.vertical,
    fd.horizontal,
    fd.business_type,
    COALESCE(SUM(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS total_deal_value,
    COALESCE(SUM(
        CASE WHEN fd.deal_stage ILIKE 'closed won'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS won_value,
    COALESCE(SUM(
        CASE WHEN fd.deal_stage NOT ILIKE 'closed%'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS pipeline_value,
    COUNT(fd.id) AS deal_count,
    COUNT(CASE WHEN fd.deal_stage ILIKE 'closed won' THEN 1 END) AS won_count,
    COALESCE(AVG(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_deal_size,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
WHERE fd.account_name IS NOT NULL 
  AND fd.account_name != ''
GROUP BY COALESCE(fd.ai_influenced, 'Unknown'),
         fd.vertical, fd.horizontal, fd.business_type;
