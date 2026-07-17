-- Gold Mart: Top Customers
-- Business Question: "Who are our top 10 accounts by total deal value?"
-- Source: gold.revenue_summary + silver.dim_account + silver.dim_contact + silver.fact_interactions

DELETE FROM gold.top_customers;

INSERT INTO gold.top_customers (
    rank, 
    account_name, 
    industry, 
    geography,
    vertical,
    total_deal_value, 
    won_value, 
    open_deals,
    contacts_count, 
    last_interaction, 
    refreshed_at
)
SELECT
    ROW_NUMBER() OVER (ORDER BY rs.total_deal_value DESC) AS rank,
    rs.account_name,
    rs.industry,
    rs.geography,
    rs.vertical,
    rs.total_deal_value,
    rs.won_value,
    rs.deal_count - rs.won_count AS open_deals,
    COALESCE(cc.contact_count, 0) AS contacts_count,
    li.last_interaction,
    CURRENT_TIMESTAMP
FROM gold.revenue_summary rs
LEFT JOIN silver.dim_account da
    ON LOWER(TRIM(da.account_name)) = LOWER(TRIM(rs.account_name))
LEFT JOIN (
    SELECT account_name, COUNT(*) AS contact_count
    FROM silver.dim_contact
    GROUP BY account_name
) cc ON LOWER(TRIM(cc.account_name)) = LOWER(TRIM(rs.account_name))
LEFT JOIN (
    SELECT account_id, MAX(interaction_date) AS last_interaction
    FROM silver.fact_interactions
    WHERE account_id IS NOT NULL
    GROUP BY account_id
) li ON li.account_id = da.id
WHERE rs.account_name IS NOT NULL AND rs.account_name != ''
ORDER BY rs.total_deal_value DESC;
