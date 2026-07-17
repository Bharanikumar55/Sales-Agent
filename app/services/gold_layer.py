"""
Gold Layer — Business-Driven Aggregated Data Marts

These are NOT raw entities. They are pre-computed business answers.
Each table answers a specific business question a manager would ask.

Design: Top-Down. Manager defines the question → Data Engineer writes SQL → stored in .sql files.

Gold queries live in: app/sql/gold/
- revenue_summary.sql           → "What is our total revenue by account?"
- top_customers.sql             → "Who are our top 10 customers by deal value?"
- pipeline_health.sql           → "What does our pipeline look like by stage?"
- account_360.sql               → "Give me a 360 view of each account"
- activity_summary.sql          → "How active are we with each account?"
- deals_closing_soon.sql        → "Which deals are closing soon?"
- at_risk_accounts.sql          → "Which accounts have gone cold?"
- salesperson_performance.sql   → "How is each salesperson performing?"
- vertical_revenue.sql          → "Revenue breakdown by TF vertical"
- ai_influence_summary.sql      → "How much revenue is AI-influenced?"
- win_loss_analysis.sql         → "What is our win rate by vertical/salesperson?"
- deal_velocity.sql             → "How fast do deals move through stages?"
- geography_mix.sql             → "Onshore vs offshore revenue split"
- lead_source_effectiveness.sql → "Which lead sources produce the most revenue?"
- stale_deals.sql               → "Which open deals haven't been updated recently?"

HUMAN OWNS GOLD:
- Data Engineers / Analysts write and review SQL
- SQL files are version controlled
- Business logic is explicit and testable
- AI only READS Gold, never modifies it
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
import json
from app.sql import get_query


# Gold table definitions moved to app/sql/gold/__init__.sql
# All SQL now lives in .sql files - no hardcoded SQL in Python


class GoldLayerBuilder:
    """
    Builds and refreshes Gold aggregation tables from Semantic (dim_/fact_) tables.
    
    GOLD LAYER PHILOSOPHY:
    - SQL queries are written by humans and stored in app/sql/gold/*.sql
    - AI never modifies Gold - it only reads from it
    - Business logic is explicit, testable, and version controlled
    - Gold answers specific business questions defined by stakeholders
    
    Called after every ingestion — keeps Gold always current.
    """

    def __init__(self, db: Session):
        self.db = db

    def initialize(self):
        """Create gold schema and all gold tables from SQL file."""
        try:
            sql = get_query("gold", "__init__")
            if sql:
                self.db.execute(text(sql))
                self.db.commit()
                print("  ✅ Gold schema initialized from SQL file")
            else:
                print("  ⚠️ Gold init SQL not found")
        except Exception as e:
            print(f"  ⚠️ Gold schema init error: {e}")
            self.db.rollback()

    def refresh_all(self) -> dict:
        """
        Refresh every Gold mart from current Semantic layer data.
        Called after each ingestion so Gold is always up to date.
        
        Returns:
            dict with row counts for each refreshed mart
        """
        results = {}
        results["revenue_summary"]          = self._refresh_revenue_summary()
        results["top_customers"]            = self._refresh_top_customers()
        results["pipeline_health"]          = self._refresh_pipeline_health()
        results["account_360"]              = self._refresh_account_360()
        results["activity_summary"]         = self._refresh_activity_summary()
        results["deals_closing_soon"]       = self._refresh_deals_closing_soon()
        results["at_risk_accounts"]         = self._refresh_at_risk_accounts()
        results["salesperson_performance"]  = self._refresh_salesperson_performance()
        results["vertical_revenue"]         = self._refresh_vertical_revenue()
        results["ai_influence_summary"]     = self._refresh_ai_influence_summary()
        results["win_loss_analysis"]        = self._refresh_win_loss_analysis()
        results["deal_velocity"]            = self._refresh_deal_velocity()
        results["geography_mix"]            = self._refresh_geography_mix()
        results["lead_source_effectiveness"]= self._refresh_lead_source_effectiveness()
        results["stale_deals"]              = self._refresh_stale_deals()
        print(f"  🥇 Gold layer refreshed: {results}")
        return results

    def _execute_sql_file(self, query_name: str) -> int:
        """
        Execute a SQL query from an external .sql file.
        
        Args:
            query_name: Name of the SQL file (without .sql extension)
            
        Returns:
            Row count after execution, or 0 on error
        """
        try:
            sql = get_query("gold", query_name)
            if not sql:
                print(f"  ⚠️ SQL file not found: gold/{query_name}.sql")
                return 0
            
            self.db.execute(text(sql))
            self.db.commit()
            
            # Get row count
            count_sql = f"SELECT COUNT(*) FROM gold.{query_name}"
            result = self.db.execute(text(count_sql))
            return result.scalar()
            
        except Exception as e:
            print(f"  ⚠️ {query_name} refresh error: {e}")
            self.db.rollback()
            return 0

    # -------------------------------------------------------------------------
    # Gold Mart Refresh Methods
    # Each method loads and executes SQL from app/sql/gold/
    # -------------------------------------------------------------------------

    def _refresh_revenue_summary(self) -> int:
        """Refresh revenue summary from silver.fact_deals."""
        return self._execute_sql_file("revenue_summary")

    def _refresh_top_customers(self) -> int:
        """Refresh top customers from gold.revenue_summary."""
        return self._execute_sql_file("top_customers")

    def _refresh_pipeline_health(self) -> int:
        """Refresh pipeline health from silver.fact_deals."""
        return self._execute_sql_file("pipeline_health")

    def _refresh_account_360(self) -> int:
        """Refresh account 360 from silver dimension and fact tables."""
        return self._execute_sql_file("account_360")

    def _refresh_activity_summary(self) -> int:
        """Refresh activity summary from silver.fact_interactions."""
        return self._execute_sql_file("activity_summary")

    def _refresh_deals_closing_soon(self) -> int:
        """Refresh deals closing soon from silver.fact_deals."""
        return self._execute_sql_file("deals_closing_soon")

    def _refresh_at_risk_accounts(self) -> int:
        """Refresh at-risk accounts from silver dimension and fact tables."""
        return self._execute_sql_file("at_risk_accounts")

    def _refresh_salesperson_performance(self) -> int:
        """Refresh salesperson performance from silver.fact_deals."""
        return self._execute_sql_file("salesperson_performance")

    def _refresh_vertical_revenue(self) -> int:
        """Refresh vertical revenue breakdown from silver.fact_deals."""
        return self._execute_sql_file("vertical_revenue")

    def _refresh_ai_influence_summary(self) -> int:
        """Refresh AI influence summary from silver.fact_deals."""
        return self._execute_sql_file("ai_influence_summary")

    def _refresh_win_loss_analysis(self) -> int:
        """Refresh win/loss analysis from silver.fact_deals."""
        return self._execute_sql_file("win_loss_analysis")

    def _refresh_deal_velocity(self) -> int:
        """Refresh deal velocity metrics from silver.fact_deals."""
        return self._execute_sql_file("deal_velocity")

    def _refresh_geography_mix(self) -> int:
        """Refresh geography mix from silver.fact_deals."""
        return self._execute_sql_file("geography_mix")

    def _refresh_lead_source_effectiveness(self) -> int:
        """Refresh lead source effectiveness from silver.fact_deals."""
        return self._execute_sql_file("lead_source_effectiveness")

    def _refresh_stale_deals(self) -> int:
        """Refresh stale deals from silver.fact_deals."""
        return self._execute_sql_file("stale_deals")

    def get_gold_stats(self) -> dict:
        """Quick row counts for all gold tables — used by health check endpoint."""
        tables = [
            "gold.revenue_summary",
            "gold.top_customers",
            "gold.pipeline_health",
            "gold.account_360",
            "gold.activity_summary",
            "gold.deals_closing_soon",
            "gold.at_risk_accounts",
            "gold.salesperson_performance",
            "gold.vertical_revenue",
            "gold.ai_influence_summary",
            "gold.win_loss_analysis",
            "gold.deal_velocity",
            "gold.geography_mix",
            "gold.lead_source_effectiveness",
            "gold.stale_deals",
        ]
        stats = {}
        for t in tables:
            try:
                stats[t] = self.db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            except Exception:
                stats[t] = 0
        return stats
