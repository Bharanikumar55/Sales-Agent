-- Gold Mart: Deals Closing Soon
-- Business Question: "Which deals are closing soon?"
-- Source: silver.fact_deals + silver.dim_account + silver.dim_contact (joined via account_id)

DELETE FROM gold.deals_closing_soon;

INSERT INTO gold.deals_closing_soon (
    deal_name, account_name, deal_value, deal_stage,
    opportunity_stage, vertical, horizontal, engagement_model,
    ai_influenced, salesperson,
    close_date, probability, contact_name, days_until_close, refreshed_at
)
SELECT
    fd.deal_name,
    COALESCE(da.account_name, fd.account_name) AS account_name,
    fd.deal_value,
    fd.deal_stage,
    fd.opportunity_stage,
    COALESCE(da.vertical, fd.vertical) AS vertical,
    fd.horizontal,
    fd.engagement_model,
    fd.ai_influenced,
    fd.salesperson,
    fd.close_date,
    fd.probability,
    COALESCE(dc.contact_name, fd.contact_name) AS contact_name,
    CASE 
        WHEN fd.close_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' 
        THEN (CAST(fd.close_date AS DATE) - CURRENT_DATE)
        ELSE NULL 
    END AS days_until_close,
    CURRENT_TIMESTAMP
FROM silver.fact_deals fd
LEFT JOIN silver.dim_account da
    ON da.id = fd.account_id
LEFT JOIN silver.dim_contact dc 
    ON LOWER(TRIM(dc.account_name)) = LOWER(TRIM(COALESCE(da.account_name, fd.account_name)))
    AND (dc.role ILIKE '%primary%' OR dc.role ILIKE '%decision%')
WHERE fd.deal_stage NOT ILIKE 'closed%'
  AND fd.close_date IS NOT NULL
  AND fd.deal_name IS NOT NULL AND fd.deal_name != ''
  AND fd.account_name IS NOT NULL AND fd.account_name != ''
ORDER BY fd.close_date ASC;
