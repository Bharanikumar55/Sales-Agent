-- Gold Mart: Revenue Summary
-- Business Question: "What is our total revenue exposure per account?"
-- Source: silver.fact_deals + silver.dim_account (joined via account_id)

DELETE FROM gold.revenue_summary;

INSERT INTO gold.revenue_summary (
    account_name, 
    industry, 
    geography,
    vertical,
    horizontal,
    engagement_model,
    total_deal_value, 
    won_value, 
    pipeline_value,
    ai_influenced_value,
    deal_count, 
    won_count, 
    ai_influenced_count,
    avg_deal_size, 
    refreshed_at
)
SELECT
    COALESCE(da.account_name, fd.account_name) AS account_name,
    da.industry,
    COALESCE(da.geography, fd.geography) AS geography,
    COALESCE(da.vertical, fd.vertical) AS vertical,
    fd.horizontal,
    fd.engagement_model,
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
    COALESCE(SUM(
        CASE WHEN fd.ai_influenced ILIKE 'yes'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS ai_influenced_value,
    COUNT(fd.id) AS deal_count,
    COUNT(CASE WHEN fd.deal_stage ILIKE 'closed won' THEN 1 END) AS won_count,
    COUNT(CASE WHEN fd.ai_influenced ILIKE 'yes' THEN 1 END) AS ai_influenced_count,
    COALESCE(AVG(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_deal_size,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
LEFT JOIN silver.dim_account da
    ON da.id = fd.account_id
WHERE fd.account_name IS NOT NULL 
  AND fd.account_name != ''
GROUP BY COALESCE(da.account_name, fd.account_name), da.industry,
         COALESCE(da.geography, fd.geography), COALESCE(da.vertical, fd.vertical),
         fd.horizontal, fd.engagement_model;
