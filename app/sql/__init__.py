"""
SQL Query Repository

This module contains SQL queries organized by layer:
- silver/: Data ingestion and transformation queries
- gold/: Business aggregation and mart queries

Gold queries are written by humans based on business requirements.
Silver queries extract and cleanse raw data.
"""

from pathlib import Path
from typing import Dict, List, Optional
import os


# Define paths
SQL_DIR = Path(__file__).parent
GOLD_DIR = SQL_DIR / "gold"
SILVER_DIR = SQL_DIR / "silver"


def get_gold_queries() -> Dict[str, str]:
    """Load all Gold mart queries from .sql files."""
    queries = {}
    if GOLD_DIR.exists():
        for sql_file in sorted(GOLD_DIR.glob("*.sql")):
            query_name = sql_file.stem
            queries[query_name] = sql_file.read_text(encoding="utf-8")
    return queries


def get_silver_queries() -> Dict[str, str]:
    """Load all Silver transformation queries from .sql files."""
    queries = {}
    if SILVER_DIR.exists():
        for sql_file in sorted(SILVER_DIR.glob("*.sql")):
            query_name = sql_file.stem
            queries[query_name] = sql_file.read_text(encoding="utf-8")
    return queries


def get_query(layer: str, name: str) -> Optional[str]:
    """Get a specific query by layer and name."""
    query_dir = GOLD_DIR if layer == "gold" else SILVER_DIR
    query_file = query_dir / f"{name}.sql"
    if query_file.exists():
        return query_file.read_text(encoding="utf-8")
    return None


def list_available_queries() -> Dict[str, List[str]]:
    """List all available queries by layer."""
    return {
        "gold": list(get_gold_queries().keys()),
        "silver": list(get_silver_queries().keys())
    }
