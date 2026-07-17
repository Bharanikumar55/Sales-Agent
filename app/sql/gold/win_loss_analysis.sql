-- Gold Mart: Win/Loss Analysis
-- Business Question: "What is our win rate by vertical, horizontal, and salesperson?"
-- Source: silver.fact_deals (closed deals only)

DELETE FROM gold.win_loss_analysis;

INSERT INTO gold.win_loss_analysis (
    vertical, horizontal, salesperson,
    total_closed, won_count, lost_count, win_rate,
    won_value, lost_value, avg_won_deal_size, avg_lost_deal_size,
    refreshed_at
)
SELECT
    fd.vertical,
    fd.horizontal,
    fd.salesperson,
    COUNT(*) AS total_closed,
    COUNT(CASE WHEN fd.deal_stage ILIKE 'closed won' THEN 1 END) AS won_count,
    COUNT(CASE WHEN fd.deal_stage ILIKE 'closed lost' THEN 1 END) AS lost_count,
    CASE
        WHEN COUNT(*) > 0
        THEN ROUND(
            COUNT(CASE WHEN fd.deal_stage ILIKE 'closed won' THEN 1 END)::NUMERIC
            / COUNT(*)::NUMERIC * 100, 1
        )
        ELSE 0
    END AS win_rate,
    COALESCE(SUM(
        CASE WHEN fd.deal_stage ILIKE 'closed won'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS won_value,
    COALESCE(SUM(
        CASE WHEN fd.deal_stage ILIKE 'closed lost'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) ELSE 0 END
    ), 0) AS lost_value,
    COALESCE(AVG(
        CASE WHEN fd.deal_stage ILIKE 'closed won'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_won_deal_size,
    COALESCE(AVG(
        CASE WHEN fd.deal_stage ILIKE 'closed lost'
             AND fd.deal_value ~ '^[0-9.]+$'
        THEN CAST(fd.deal_value AS NUMERIC) END
    ), 0) AS avg_lost_deal_size,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
WHERE fd.deal_stage ILIKE 'closed%'
GROUP BY fd.vertical, fd.horizontal, fd.salesperson;
