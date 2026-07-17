-- Gold Mart: Vertical Revenue
-- Business Question: "What is our revenue breakdown by vertical?"
-- Source: silver.fact_deals + silver.dim_account

DELETE FROM gold.vertical_revenue;

INSERT INTO gold.vertical_revenue (
    vertical, horizontal, geography, engagement_model,
    total_deal_value, won_value, pipeline_value, ai_influenced_value,
    deal_count, won_count, avg_deal_size, refreshed_at
)
SELECT
    COALESCE(da.vertical, fd.vertical, 'Unassigned') AS vertical,
    fd.horizontal,
    COALESCE(da.geography, fd.geography) AS geography,
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
GROUP BY COALESCE(da.vertical, fd.vertical, 'Unassigned'),
         fd.horizontal,
         COALESCE(da.geography, fd.geography),
         fd.engagement_model;
