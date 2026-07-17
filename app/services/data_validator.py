"""Data Validation Layer — enterprise-grade checks before Silver table insertion.

Policy: validate → warn → log.  Never blocks the full ingestion pipeline.

Capabilities:
  - Required field checks (NOT NULL)
  - Numeric format validation
  - TF-specific enum validation (verticals, horizontals, stages, engagement models)
  - Completeness scoring per record and per batch
  - Cross-table referential integrity checks (via DataQualityAgent)
"""

import re
from typing import Dict, Any, Tuple, List, Optional


# ── TF Business Dimension Enums ─────────────────────────────────
# These are the valid values per Avinash's specifications.
# Validation is case-insensitive with fuzzy matching.

VALID_VERTICALS = {
    "mortgage & lending", "banking & insurance", "capital market",
    "higher education", "technology", "payments",
}

VALID_HORIZONTALS = {
    "ai & data", "application engineering", "digital operations",
}

VALID_ENGAGEMENT_MODELS = {
    "t&m", "time and material", "fixed", "retainers",
    "outcome-based", "transactional",
}

VALID_OPPORTUNITY_STAGES = {
    "p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10",
}

VALID_AI_INFLUENCED = {"yes", "no"}

VALID_BUSINESS_TYPES = {
    "new business", "existing customer", "renewal",
}

VALID_GEOGRAPHIES = {"onshore", "offshore", "both"}


def validate_record(table_name: str, record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a single record before it is written to a Silver entity table.

    Args:
        table_name: Silver table name (may include "silver." prefix).
        record: The filtered column→value dict about to be inserted.

    Returns:
        (is_valid, error_messages)  — empty list when valid.
    """
    errors: List[str] = []
    warnings: List[str] = []
    bare = table_name.split(".")[-1]

    if bare == "dim_account":
        _require(record, "account_name", errors)
        _enum_if_present(record, "vertical", VALID_VERTICALS, warnings)
        _enum_if_present(record, "geography", VALID_GEOGRAPHIES, warnings)

    elif bare == "dim_contact":
        _require(record, "contact_name", errors)

    elif bare == "fact_deals":
        _require_any(record, ["account_id", "account_name"], errors)
        _require(record, "deal_name", errors)
        _numeric_if_present(record, "deal_value", errors)
        _enum_if_present(record, "vertical", VALID_VERTICALS, warnings)
        _enum_if_present(record, "horizontal", VALID_HORIZONTALS, warnings)
        _enum_if_present(record, "engagement_model", VALID_ENGAGEMENT_MODELS, warnings)
        _enum_if_present(record, "opportunity_stage", VALID_OPPORTUNITY_STAGES, warnings)
        _enum_if_present(record, "ai_influenced", VALID_AI_INFLUENCED, warnings)
        _enum_if_present(record, "business_type", VALID_BUSINESS_TYPES, warnings)
        _date_if_present(record, "close_date", warnings)

    elif bare == "fact_interactions":
        _require_any(record, ["account_id", "account_name"], errors)
        _date_if_present(record, "interaction_date", warnings)

    elif bare == "fact_insights":
        _require_any(record, ["account_id", "account_name"], errors)

    # Warnings don't block insertion but are logged
    if warnings:
        for w in warnings:
            print(f"  ⚠️ DQ warning ({bare}): {w}")

    return (len(errors) == 0, errors)


def completeness_score(record: Dict[str, Any], required_fields: List[str], all_fields: List[str]) -> float:
    """
    Calculate completeness score for a record (0.0 to 1.0).
    
    Required fields count double. Missing required = 0 for that field.
    Optional fields that are filled add to the score.
    """
    if not all_fields:
        return 1.0
    
    total_weight = len(required_fields) * 2 + (len(all_fields) - len(required_fields))
    score = 0.0
    
    for field in all_fields:
        val = record.get(field)
        is_filled = val is not None and str(val).strip() != ""
        if field in required_fields:
            score += 2.0 if is_filled else 0.0
        else:
            score += 1.0 if is_filled else 0.0
    
    return round(score / total_weight, 3) if total_weight > 0 else 1.0


def batch_dq_report(table_name: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate a data quality report for a batch of records.
    
    Returns:
        {
            "table": "fact_deals",
            "total_records": 50,
            "valid_records": 45,
            "invalid_records": 5,
            "validation_rate": 0.90,
            "avg_completeness": 0.78,
            "field_fill_rates": {"deal_name": 1.0, "vertical": 0.6, ...},
            "common_errors": ["deal_value must be numeric (3 records)"],
            "enum_distribution": {"vertical": {"Technology": 12, "Banking & Insurance": 8, ...}}
        }
    """
    bare = table_name.split(".")[-1]
    
    valid_count = 0
    all_errors: List[str] = []
    error_counts: Dict[str, int] = {}
    field_fill: Dict[str, int] = {}
    field_total: Dict[str, int] = {}
    enum_dist: Dict[str, Dict[str, int]] = {}
    
    # Identify all fields across records
    all_field_names = set()
    for rec in records:
        all_field_names.update(rec.keys())
    
    # Track enum fields
    enum_fields = {
        "vertical": VALID_VERTICALS,
        "horizontal": VALID_HORIZONTALS,
        "engagement_model": VALID_ENGAGEMENT_MODELS,
        "opportunity_stage": VALID_OPPORTUNITY_STAGES,
        "ai_influenced": VALID_AI_INFLUENCED,
        "business_type": VALID_BUSINESS_TYPES,
        "geography": VALID_GEOGRAPHIES,
    }
    
    for rec in records:
        is_valid, errors = validate_record(table_name, rec)
        if is_valid:
            valid_count += 1
        for err in errors:
            error_counts[err] = error_counts.get(err, 0) + 1
        
        # Field fill rates
        for field in all_field_names:
            field_total[field] = field_total.get(field, 0) + 1
            val = rec.get(field)
            if val is not None and str(val).strip() != "":
                field_fill[field] = field_fill.get(field, 0) + 1
        
        # Enum distribution
        for enum_field in enum_fields:
            if enum_field in rec:
                val = rec.get(enum_field)
                if val and str(val).strip():
                    val_str = str(val).strip()
                    if enum_field not in enum_dist:
                        enum_dist[enum_field] = {}
                    enum_dist[enum_field][val_str] = enum_dist[enum_field].get(val_str, 0) + 1
    
    total = len(records)
    fill_rates = {}
    for field in sorted(all_field_names):
        if field in field_total and field_total[field] > 0:
            fill_rates[field] = round(field_fill.get(field, 0) / field_total[field], 3)
    
    common_errors = [
        f"{err} ({count} record{'s' if count > 1 else ''})"
        for err, count in sorted(error_counts.items(), key=lambda x: -x[1])[:10]
    ]
    
    return {
        "table": bare,
        "total_records": total,
        "valid_records": valid_count,
        "invalid_records": total - valid_count,
        "validation_rate": round(valid_count / total, 3) if total > 0 else 1.0,
        "field_fill_rates": fill_rates,
        "common_errors": common_errors,
        "enum_distribution": enum_dist,
    }


# ── helpers ──────────────────────────────────────────────────────

def _require(record: Dict[str, Any], field: str, errors: List[str]):
    """Field must be present and non-blank."""
    val = record.get(field)
    if val is None or str(val).strip() == "":
        errors.append(f"{field} is required and cannot be empty")


def _require_any(record: Dict[str, Any], fields: List[str], errors: List[str]):
    """At least one of the listed fields must be present and non-blank."""
    for f in fields:
        val = record.get(f)
        if val is not None and str(val).strip() != "":
            return  # at least one field is present
    errors.append(f"At least one of {', '.join(fields)} is required")


def _numeric_if_present(record: Dict[str, Any], field: str, errors: List[str]):
    """If the field exists, its value must be interpretable as a number."""
    val = record.get(field)
    if val is None or str(val).strip() == "":
        return
    cleaned = str(val).replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()
    try:
        float(cleaned)
    except (ValueError, TypeError):
        errors.append(f"{field} must be numeric, got: '{val}'")


def _enum_if_present(record: Dict[str, Any], field: str, valid_values: set, warnings: List[str]):
    """If the field exists, warn if its value is not in the known enum set."""
    val = record.get(field)
    if val is None or str(val).strip() == "":
        return
    if str(val).strip().lower() not in valid_values:
        warnings.append(
            f"{field} value '{val}' is not a recognized value. "
            f"Expected one of: {', '.join(sorted(valid_values))}"
        )


def _date_if_present(record: Dict[str, Any], field: str, warnings: List[str]):
    """If the field exists, warn if it doesn't look like a date."""
    val = record.get(field)
    if val is None or str(val).strip() == "":
        return
    val_str = str(val).strip()
    # Accept YYYY-MM-DD, YYYY/MM/DD, MM/DD/YYYY
    date_patterns = [
        r'^\d{4}-\d{2}-\d{2}$',
        r'^\d{4}/\d{2}/\d{2}$',
        r'^\d{2}/\d{2}/\d{4}$',
        r'^\d{2}-\d{2}-\d{4}$',
    ]
    if not any(re.match(p, val_str) for p in date_patterns):
        warnings.append(f"{field} value '{val_str}' does not look like a date (expected YYYY-MM-DD)")


# ── domain relevance check ───────────────────────────────────────

_SALES_KEYWORDS = {
    "account", "client", "deal", "meeting", "revenue", "opportunity",
    "contact", "pipeline", "proposal", "negotiation", "contract",
    "prospect", "customer", "sales", "crm", "lead", "close", "quote",
    "pricing", "budget", "forecast", "renewal", "churn", "upsell",
    "onboarding", "demo", "sow", "rfp", "rfi",
}

_SALES_COLUMN_HINTS = {
    "account_name", "deal_name", "deal_value", "deal_stage", "close_date",
    "contact_name", "contact_email", "opportunity", "revenue", "pipeline",
    "lead_source", "account", "client", "company", "stage",
}

_ROLE_PATTERN = re.compile(
    r"\b(?:CEO|CFO|CTO|COO|CIO|CMO|VP|Director|Manager|Head of|"
    r"President|Partner|Account Executive|Sales Rep|BDR|SDR|"
    r"Account Manager|Sales Manager|Regional Director)\b",
    re.IGNORECASE,
)

_MONEY_PATTERN = re.compile(
    r"\$\s?[\d,.]+|\d+(?:,\d{3})+(?:\.\d+)?\s*(?:USD|dollars?|M|K|B)\b",
    re.IGNORECASE,
)

_MIN_KEYWORD_HITS = 2


def is_sales_relevant(data: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Determine whether parsed file data is related to the sales domain.

    Uses simple keyword + entity heuristics — no ML, no API calls.

    Args:
        data: Output of FileParser.parse() — a list of record dicts.

    Returns:
        (is_relevant, reason) — reason explains why it was flagged as irrelevant.
    """
    if not data:
        return False, "File produced no extractable records."

    hits: int = 0

    column_names = {k.lower() for rec in data for k in rec.keys()}
    col_overlap = column_names & _SALES_COLUMN_HINTS
    if col_overlap:
        hits += len(col_overlap)

    text_blob = _build_text_blob(data)
    text_lower = text_blob.lower()

    for kw in _SALES_KEYWORDS:
        if kw in text_lower:
            hits += 1

    if _ROLE_PATTERN.search(text_blob):
        hits += 2

    if _MONEY_PATTERN.search(text_blob):
        hits += 1

    if hits >= _MIN_KEYWORD_HITS:
        return True, ""

    return (
        False,
        "This file does not appear to contain sales-related information. "
        "No sales keywords (account, deal, revenue, contact, etc.), "
        "business roles, or monetary values were detected.",
    )


def _build_text_blob(data: List[Dict[str, Any]], max_chars: int = 50_000) -> str:
    """Flatten all record values into a single searchable string."""
    parts: List[str] = []
    total = 0
    for rec in data:
        for k, v in rec.items():
            chunk = f"{k} {v}" if v else k
            parts.append(str(chunk))
            total += len(chunk)
            if total >= max_chars:
                return " ".join(parts)
    return " ".join(parts)
