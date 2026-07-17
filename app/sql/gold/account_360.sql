-- Gold Mart: Account 360
-- Business Question: "Give me a 360 view of each account"
-- Source: silver.dim_account + fact tables (joined via account_id)

DELETE FROM gold.account_360;

INSERT INTO gold.account_360 (
    account_name, industry, geography, vertical, employee_count, annual_revenue, website,
    total_deal_value, open_deal_count, won_deal_count, ai_influenced_count, contact_count,
    interaction_count, insight_count, primary_contact, latest_deal_stage,
    latest_sentiment, refreshed_at
)
SELECT
    da.account_name AS account_name,
    da.industry,
    da.geography,
    da.vertical,
    da.employee_count,
    da.annual_revenue,
    da.website,
    COALESCE(deal_stats.total_deal_value, 0) AS total_deal_value,
    COALESCE(deal_stats.open_deal_count, 0) AS open_deal_count,
    COALESCE(deal_stats.won_deal_count, 0) AS won_deal_count,
    COALESCE(deal_stats.ai_influenced_count, 0) AS ai_influenced_count,
    COALESCE(contact_stats.contact_count, 0) AS contact_count,
    COALESCE(interaction_stats.interaction_count, 0) AS interaction_count,
    COALESCE(insight_stats.insight_count, 0) AS insight_count,
    contact_stats.primary_contact,
    deal_stats.latest_deal_stage,
    interaction_stats.latest_sentiment,
    CURRENT_TIMESTAMP
FROM silver.dim_account da
LEFT JOIN (
    SELECT 
        account_id,
        SUM(CASE WHEN deal_value ~ '^[0-9.]+$' 
            THEN CAST(deal_value AS NUMERIC) ELSE 0 END) AS total_deal_value,
        COUNT(CASE WHEN deal_stage NOT ILIKE 'closed%' THEN 1 END) AS open_deal_count,
        COUNT(CASE WHEN deal_stage ILIKE 'closed won' THEN 1 END) AS won_deal_count,
        COUNT(CASE WHEN ai_influenced ILIKE 'yes' THEN 1 END) AS ai_influenced_count,
        MAX(deal_stage) AS latest_deal_stage
    FROM silver.fact_deals
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) deal_stats ON deal_stats.account_id = da.id
LEFT JOIN (
    SELECT 
        account_name,
        COUNT(*) AS contact_count,
        MAX(CASE WHEN role ILIKE '%primary%' OR role ILIKE '%decision%' 
            THEN contact_name END) AS primary_contact
    FROM silver.dim_contact
    GROUP BY account_name
) contact_stats ON LOWER(TRIM(contact_stats.account_name)) = LOWER(TRIM(da.account_name))
LEFT JOIN (
    SELECT 
        account_id,
        COUNT(*) AS interaction_count,
        MAX(sentiment) AS latest_sentiment
    FROM silver.fact_interactions
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) interaction_stats ON interaction_stats.account_id = da.id
LEFT JOIN (
    SELECT account_id, COUNT(*) AS insight_count
    FROM silver.fact_insights
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) insight_stats ON insight_stats.account_id = da.id
WHERE da.account_name IS NOT NULL AND da.account_name != '';
