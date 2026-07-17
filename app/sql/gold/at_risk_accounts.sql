-- Gold Mart: At-Risk Accounts
-- Business Question: "Which accounts have gone cold?"
-- Source: silver.dim_account + silver.fact_deals + silver.fact_interactions (joined via account_id)

DELETE FROM gold.at_risk_accounts;

INSERT INTO gold.at_risk_accounts (
    account_name, industry, geography, vertical, open_deal_count, open_deal_value,
    last_interaction_date, days_since_last_contact, last_sentiment, risk_level, refreshed_at
)
SELECT
    da.account_name AS account_name,
    da.industry,
    da.geography,
    da.vertical,
    COALESCE(deal_stats.open_deal_count, 0) AS open_deal_count,
    COALESCE(deal_stats.open_deal_value, 0) AS open_deal_value,
    interaction_stats.last_interaction_date,
    CASE 
        WHEN interaction_stats.last_interaction_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' 
        THEN (CURRENT_DATE - CAST(interaction_stats.last_interaction_date AS DATE))
        ELSE NULL 
    END AS days_since_last_contact,
    interaction_stats.last_sentiment,
    CASE 
        WHEN interaction_stats.last_interaction_date IS NULL 
            AND COALESCE(deal_stats.open_deal_count, 0) > 0 THEN 'High'
        WHEN interaction_stats.last_interaction_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' 
            AND (CURRENT_DATE - CAST(interaction_stats.last_interaction_date AS DATE)) > 60 
            AND COALESCE(deal_stats.open_deal_count, 0) > 0 THEN 'High'
        WHEN interaction_stats.last_interaction_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' 
            AND (CURRENT_DATE - CAST(interaction_stats.last_interaction_date AS DATE)) > 30 
            AND COALESCE(deal_stats.open_deal_count, 0) > 0 THEN 'Medium'
        WHEN COALESCE(deal_stats.open_deal_count, 0) > 0 THEN 'Low'
        ELSE 'None'
    END AS risk_level,
    CURRENT_TIMESTAMP
FROM silver.dim_account da
LEFT JOIN (
    SELECT 
        account_id,
        COUNT(CASE WHEN deal_stage NOT ILIKE 'closed%' THEN 1 END) AS open_deal_count,
        SUM(CASE WHEN deal_stage NOT ILIKE 'closed%' 
                 AND deal_value ~ '^[0-9.]+$' 
            THEN CAST(deal_value AS NUMERIC) ELSE 0 END) AS open_deal_value
    FROM silver.fact_deals
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) deal_stats ON deal_stats.account_id = da.id
LEFT JOIN (
    SELECT 
        account_id,
        MAX(interaction_date) AS last_interaction_date,
        MAX(sentiment) AS last_sentiment
    FROM silver.fact_interactions
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) interaction_stats ON interaction_stats.account_id = da.id
WHERE COALESCE(deal_stats.open_deal_count, 0) > 0
  AND da.account_name IS NOT NULL AND da.account_name != '';
