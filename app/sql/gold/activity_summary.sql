-- Gold Mart: Activity Summary
-- Business Question: "How active are we with each account?"
-- Source: silver.fact_interactions + silver.fact_insights (joined via account_id)

DELETE FROM gold.activity_summary;

INSERT INTO gold.activity_summary (
    account_name, vertical, total_interactions, positive_interactions,
    negative_interactions, neutral_interactions, total_insights,
    competitive_flags, avg_sentiment_score, refreshed_at
)
SELECT
    da.account_name,
    da.vertical,
    COALESCE(i.total_interactions, 0) AS total_interactions,
    COALESCE(i.positive_count, 0) AS positive_interactions,
    COALESCE(i.negative_count, 0) AS negative_interactions,
    COALESCE(i.neutral_count, 0) AS neutral_interactions,
    COALESCE(ins.total_insights, 0) AS total_insights,
    COALESCE(ins.competitive_count, 0) AS competitive_flags,
    i.avg_sentiment,
    CURRENT_TIMESTAMP
FROM silver.dim_account da
LEFT JOIN (
    SELECT 
        account_id,
        COUNT(*) AS total_interactions,
        COUNT(CASE WHEN sentiment ILIKE '%positive%' THEN 1 END) AS positive_count,
        COUNT(CASE WHEN sentiment ILIKE '%negative%' THEN 1 END) AS negative_count,
        COUNT(CASE WHEN sentiment ILIKE '%neutral%' OR sentiment IS NULL THEN 1 END) AS neutral_count,
        AVG(CASE 
            WHEN sentiment ILIKE '%positive%' THEN 1
            WHEN sentiment ILIKE '%negative%' THEN -1
            ELSE 0 
        END) AS avg_sentiment
    FROM silver.fact_interactions
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) i ON i.account_id = da.id
LEFT JOIN (
    SELECT 
        account_id,
        COUNT(*) AS total_insights,
        COUNT(CASE WHEN insight_type ILIKE '%competitive%' THEN 1 END) AS competitive_count
    FROM silver.fact_insights
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) ins ON ins.account_id = da.id
WHERE da.account_name IS NOT NULL AND da.account_name != ''
  AND (i.total_interactions > 0 OR ins.total_insights > 0);
