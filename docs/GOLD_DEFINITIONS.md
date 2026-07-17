# Gold Table Definitions

This file is the single source of truth for what each Gold table means, how it is calculated, and where its data comes from. All definitions are derived from the actual SQL in `app/sql/gold/`.

Auto-rebuilt after every data upload. No manual refresh needed.

## ThoughtFocus Business Dimensions

All Gold tables are enriched with the following TF-specific dimensions where applicable:

| Dimension | Values | Source |
|-----------|--------|--------|
| **Vertical** | Mortgage & Lending, Banking & Insurance, Capital Market, Higher Education, Technology, Payments | dim_account.vertical / fact_deals.vertical |
| **Horizontal** | AI & Data, Application Engineering, Digital Operations | fact_deals.horizontal |
| **Geography** | Onshore, Offshore, Both | dim_account.geography |
| **Engagement Model** | T&M, Fixed, Retainers, Outcome-based | fact_deals.engagement_model |
| **Opportunity Stage** | P0 (won) → P10 (cold prospect) | fact_deals.opportunity_stage |
| **AI Influenced** | Yes / No | fact_deals.ai_influenced |
| **Business Type** | New Business, Existing Customer, Renewal | fact_deals.business_type |
| **Salesperson** | Owner / rep assigned | fact_deals.salesperson |

---

## Table: gold.revenue_summary

**Business Question:**
What is our total revenue exposure per account?

**Definition:**
One row per account. Sums up all deal values from the deals table and breaks them into three buckets: total value (all deals), won value (deals marked "closed won"), and pipeline value (deals not yet closed). Also tracks AI-influenced deal value and count. Enriched with vertical, horizontal, engagement model, industry and geography.

**Source Tables:**
silver.fact_deals, silver.dim_account

---

## Table: gold.top_customers

**Business Question:**
Who are our biggest accounts by total deal value?

**Definition:**
Ranks all accounts from highest to lowest total deal value using the revenue summary. For each account, also pulls in the vertical, number of known contacts and the date of the most recent interaction. Accounts with no deals are excluded.

**Source Tables:**
gold.revenue_summary, silver.dim_account, silver.dim_contact, silver.fact_interactions

---

## Table: gold.pipeline_health

**Business Question:**
What does our active deal pipeline look like by stage?

**Definition:**
Groups all open (non-closed) deals by their current stage, opportunity stage (P0-P10), vertical, and horizontal. For each group, shows the number of deals, total value, average deal size, and how many distinct accounts have deals in that stage. Closed deals are excluded entirely.

**Source Tables:**
silver.fact_deals

---

## Table: gold.account_360

**Business Question:**
Give me the full picture on a single account.

**Definition:**
One row per account with everything in one place: company profile (industry, geography, vertical, size, revenue, website), deal totals (total value, open count, won count, AI-influenced count, latest stage), contact count plus the primary or decision-maker contact, interaction count with the most recent sentiment, and total insight count. Only accounts with a name are included.

**Source Tables:**
silver.dim_account, silver.fact_deals, silver.dim_contact, silver.fact_interactions, silver.fact_insights

---

## Table: gold.activity_summary

**Business Question:**
How active are we with each account?

**Definition:**
One row per account that has at least one interaction or one insight. Includes vertical. Breaks interactions into positive, negative, and neutral counts based on recorded sentiment. Calculates an average sentiment score (positive = +1, negative = -1, neutral = 0). Also counts total AI-extracted insights and flags how many are competitive intelligence.

**Source Tables:**
silver.dim_account, silver.fact_interactions, silver.fact_insights

---

## Table: gold.deals_closing_soon

**Business Question:**
Which open deals have a close date coming up?

**Definition:**
Lists every open (non-closed) deal that has a close date set. Shows the deal name, account, value, stage, opportunity stage (P0-P10), vertical, horizontal, engagement model, AI-influenced flag, salesperson, probability, and the primary or decision-maker contact. Calculates how many days remain until the close date. Ordered by close date ascending (soonest first).

**Source Tables:**
silver.fact_deals, silver.dim_account, silver.dim_contact

---

## Table: gold.at_risk_accounts

**Business Question:**
Which accounts with open deals have gone cold?

**Definition:**
Only includes accounts that have at least one open (non-closed) deal. Includes vertical. For each, looks at the most recent interaction date and assigns a risk level:

- **High** — No interaction on record, or last interaction was more than 60 days ago
- **Medium** — Last interaction was 30 to 60 days ago
- **Low** — Last interaction was within 30 days
- **None** — No open deals (excluded from results)

Also shows the open deal count, open deal value, last interaction date, and last recorded sentiment.

**Source Tables:**
silver.dim_account, silver.fact_deals, silver.fact_interactions

---

## Table: gold.salesperson_performance

**Business Question:**
How is each salesperson performing?

**Definition:**
One row per salesperson, broken down by vertical and horizontal. Shows total deal value, won value, pipeline value, deal count, won count, AI-influenced deal count, average deal size, and average days to close (for won deals). Only deals with a named salesperson are included.

**Source Tables:**
silver.fact_deals

---

## Table: gold.vertical_revenue

**Business Question:**
What is our revenue breakdown by TF vertical?

**Definition:**
Revenue aggregated by vertical, then further broken down by horizontal, geography, and engagement model. Shows total value, won value, pipeline value, AI-influenced value, deal count, won count, and average deal size. Deals without a vertical are grouped as "Unassigned".

**Source Tables:**
silver.fact_deals, silver.dim_account

---

## Table: gold.ai_influence_summary

**Business Question:**
How much of our revenue is AI-influenced?

**Definition:**
Groups all deals by AI-influenced flag (yes/no/unknown), then further by vertical, horizontal, and business type. Shows total value, won value, pipeline value, deal count, won count, and average deal size. Answers the question "what % of pipeline/revenue is AI-influenced?"

**Source Tables:**
silver.fact_deals

---

## Table: gold.win_loss_analysis

**Business Question:**
What is our win rate by vertical, horizontal, and salesperson?

**Definition:**
Only includes closed deals (won + lost). Groups by vertical, horizontal, and salesperson. Calculates total closed count, won count, lost count, win rate (%), won value, lost value, and average deal size for both wins and losses. Enables win rate comparisons across any dimension.

**Source Tables:**
silver.fact_deals

---

## Table: gold.deal_velocity

**Business Question:**
How fast do deals move through stages?

**Definition:**
Groups deals by stage, vertical, and engagement model. Calculates the average number of days deals have spent in each stage (using close_date or current date vs created_at). Also includes deal count, average deal value, and total value per group. Helps identify bottleneck stages.

**Source Tables:**
silver.fact_deals

---

## Table: gold.geography_mix

**Business Question:**
What is our onshore vs offshore revenue split?

**Definition:**
Revenue aggregated by geography (Onshore/Offshore/Both) and vertical. Shows total deal value, won value, pipeline value, deal count, won count, and number of distinct accounts. Deals without geography are grouped as "Unknown".

**Source Tables:**
silver.fact_deals, silver.dim_account

---

## Table: gold.lead_source_effectiveness

**Business Question:**
Which lead sources produce the most revenue and wins?

**Definition:**
Groups all deals by lead_source and vertical. Shows total deal value, won value, deal count, won count, win rate (among closed deals), and average deal size. Helps answer which acquisition channels (Referral, Inbound, Conference, Cold Outreach, Account Mining) are most effective.

**Source Tables:**
silver.fact_deals

---

## Table: gold.stale_deals

**Business Question:**
Which open deals haven't been updated recently?

**Definition:**
Lists all open (non-closed) deals with a staleness assessment. Calculates days since last update and assigns a staleness level:

- **Critical** — No update for 60+ days
- **Warning** — No update for 30-60 days
- **Monitor** — No update for 14-30 days
- **Active** — Updated within 14 days

Includes deal name, account, value, stage, opportunity stage, vertical, salesperson, and close date. Ordered by most stale first.

**Source Tables:**
silver.fact_deals
