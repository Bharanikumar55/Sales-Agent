-- Gold Mart: Lead Source Effectiveness
-- Business Question: "Which lead sources produce the most revenue and wins?"
-- Source: silver.fact_deals

DELETE FROM gold.lead_source_effectiveness;

INSERT INTO gold.lead_source_effectiveness (
    lead_source, vertical,
    total_deal_value, won_value,
    deal_count, won_count, win_rate, avg_deal_size,
    refreshed_at
)
SELECT
    COALESCE(fd.lead_source, 'Unknown') AS lead_source,
    fd.vertical,
    COALESCE(SUM(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS total_deal_value,
    COALESCE(SUM(
        CASE WHEN fd.deal_stage ILIKE 'closed won'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS won_value,
    COUNT(fd.id) AS deal_count,
    COUNT(CASE WHEN fd.deal_stage ILIKE 'closed won' THEN 1 END) AS won_count,
    CASE
        WHEN COUNT(CASE WHEN fd.deal_stage ILIKE 'closed%' THEN 1 END) > 0
        THEN ROUND(
            COUNT(CASE WHEN fd.deal_stage ILIKE 'closed won' THEN 1 END)::NUMERIC
            / COUNT(CASE WHEN fd.deal_stage ILIKE 'closed%' THEN 1 END)::NUMERIC * 100, 1
        )
        ELSE 0
    END AS win_rate,
    COALESCE(AVG(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_deal_size,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
WHERE fd.account_name IS NOT NULL
  AND fd.account_name != ''
GROUP BY COALESCE(fd.lead_source, 'Unknown'), fd.vertical;
