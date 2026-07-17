-- Gold Mart: Salesperson Performance
-- Business Question: "How is each salesperson performing?"
-- Source: silver.fact_deals

DELETE FROM gold.salesperson_performance;

INSERT INTO gold.salesperson_performance (
    salesperson, vertical, horizontal,
    total_deal_value, won_value, pipeline_value,
    deal_count, won_count, ai_influenced_count,
    avg_deal_size, avg_close_days, refreshed_at
)
SELECT
    fd.salesperson,
    fd.vertical,
    fd.horizontal,
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
    COUNT(CASE WHEN fd.ai_influenced ILIKE 'yes' THEN 1 END) AS ai_influenced_count,
    COALESCE(AVG(
        CASE WHEN fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_deal_size,
    AVG(
        CASE WHEN fd.deal_stage ILIKE 'closed won'
             AND fd.close_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
             AND fd.created_at IS NOT NULL
        THEN CAST(fd.close_date AS DATE) - fd.created_at::DATE
        ELSE NULL END
    ) AS avg_close_days,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
WHERE fd.salesperson IS NOT NULL
  AND fd.salesperson != ''
GROUP BY fd.salesperson, fd.vertical, fd.horizontal;
