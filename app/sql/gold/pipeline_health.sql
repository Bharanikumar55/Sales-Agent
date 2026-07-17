-- Gold Mart: Pipeline Health
-- Business Question: "What does our pipeline look like by stage?"
-- Source: silver.fact_deals

DELETE FROM gold.pipeline_health;

INSERT INTO gold.pipeline_health (
    stage, 
    opportunity_stage,
    vertical,
    horizontal,
    deal_count, 
    total_value, 
    avg_deal_size,
    accounts_in_stage, 
    refreshed_at
)
SELECT
    fd.deal_stage AS stage,
    fd.opportunity_stage,
    fd.vertical,
    fd.horizontal,
    COUNT(*) AS deal_count,
    COALESCE(SUM(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS total_value,
    COALESCE(AVG(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_deal_size,
    COUNT(DISTINCT COALESCE(fd.account_id::TEXT, fd.account_name)) AS accounts_in_stage,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
WHERE fd.deal_stage IS NOT NULL 
  AND fd.deal_stage != ''
  AND fd.deal_stage NOT ILIKE 'closed%'
GROUP BY fd.deal_stage, fd.opportunity_stage, fd.vertical, fd.horizontal;
