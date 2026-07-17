-- Gold Mart: Stale Deals
-- Business Question: "Which open deals haven't been updated recently?"
-- Source: silver.fact_deals

DELETE FROM gold.stale_deals;

INSERT INTO gold.stale_deals (
    deal_name, account_name, deal_value, deal_stage,
    opportunity_stage, vertical, salesperson, close_date,
    days_since_update, staleness_level, refreshed_at
)
SELECT
    fd.deal_name,
    fd.account_name,
    fd.deal_value,
    fd.deal_stage,
    fd.opportunity_stage,
    fd.vertical,
    fd.salesperson,
    fd.close_date,
    CASE
        WHEN fd.updated_at IS NOT NULL
        THEN (CURRENT_DATE - fd.updated_at::DATE)
        WHEN fd.created_at IS NOT NULL
        THEN (CURRENT_DATE - fd.created_at::DATE)
        ELSE NULL
    END AS days_since_update,
    CASE
        WHEN fd.updated_at IS NOT NULL AND (CURRENT_DATE - fd.updated_at::DATE) > 60
        THEN 'Critical'
        WHEN fd.updated_at IS NOT NULL AND (CURRENT_DATE - fd.updated_at::DATE) > 30
        THEN 'Warning'
        WHEN fd.created_at IS NOT NULL AND fd.updated_at IS NULL
             AND (CURRENT_DATE - fd.created_at::DATE) > 30
        THEN 'Warning'
        WHEN fd.updated_at IS NOT NULL AND (CURRENT_DATE - fd.updated_at::DATE) > 14
        THEN 'Monitor'
        ELSE 'Active'
    END AS staleness_level,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
WHERE fd.deal_stage IS NOT NULL
  AND fd.deal_stage NOT ILIKE 'closed%'
  AND fd.deal_name IS NOT NULL
ORDER BY days_since_update DESC NULLS LAST;
