-- Gold Mart: Deal Velocity
-- Business Question: "How fast do deals move through stages?"
-- Source: silver.fact_deals

DELETE FROM gold.deal_velocity;

INSERT INTO gold.deal_velocity (
    deal_stage, vertical, engagement_model,
    deal_count, avg_days_in_stage, avg_deal_value, total_value,
    refreshed_at
)
SELECT
    fd.deal_stage,
    fd.vertical,
    fd.engagement_model,
    COUNT(*) AS deal_count,
    AVG(
        CASE
            WHEN fd.close_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                 AND fd.created_at IS NOT NULL
            THEN CAST(fd.close_date AS DATE) - fd.created_at::DATE
            WHEN fd.created_at IS NOT NULL
            THEN CURRENT_DATE - fd.created_at::DATE
            ELSE NULL
        END
    ) AS avg_days_in_stage,
    COALESCE(AVG(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_deal_value,
    COALESCE(SUM(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS total_value,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
WHERE fd.deal_stage IS NOT NULL
  AND fd.deal_stage != ''
GROUP BY fd.deal_stage, fd.vertical, fd.engagement_model;
