-- Gold Mart: Geography Mix
-- Business Question: "What is our onshore vs offshore revenue split?"
-- Source: silver.fact_deals + silver.dim_account

DELETE FROM gold.geography_mix;

INSERT INTO gold.geography_mix (
    geography, vertical,
    total_deal_value, won_value, pipeline_value,
    deal_count, won_count, account_count,
    refreshed_at
)
SELECT
    COALESCE(COALESCE(da.geography, fd.geography), 'Unknown') AS geography,
    COALESCE(da.vertical, fd.vertical) AS vertical,
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
    COUNT(DISTINCT COALESCE(fd.account_id::TEXT, fd.account_name)) AS account_count,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
LEFT JOIN silver.dim_account da
    ON da.id = fd.account_id
WHERE fd.account_name IS NOT NULL
  AND fd.account_name != ''
GROUP BY COALESCE(COALESCE(da.geography, fd.geography), 'Unknown'),
         COALESCE(da.vertical, fd.vertical);
