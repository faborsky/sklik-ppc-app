"""Two-step report helper (createReport -> readReport)."""
from __future__ import annotations

from sklik.api import _api_call



# ---------------------------------------------------------------------------
# Report helper (two-step: createReport → readReport)
# ---------------------------------------------------------------------------

STAT_COLUMNS = [
    "clicks", "impressions", "ctr", "avgCpc", "avgPos",
    "totalMoney", "conversions", "conversionValue",
    "transactions", "pno",
    "missImpressions", "underLowerThreshold", "exhaustedBudget",
    "ish", "ishContext", "ishSum",
]


def _fetch_report(
    entity: str,
    restriction: dict,
    date_from: str,
    date_to: str,
    display_columns: list[str] | None = None,
    granularity: str = "total",
    limit: int = 5000,
    user_id: int | None = None,
) -> list[dict]:
    """Create and read a report in one step."""
    # Dates go in restrictionFilter, granularity in displayOptions
    restriction_with_dates = dict(restriction)
    restriction_with_dates["dateFrom"] = date_from
    restriction_with_dates["dateTo"] = date_to

    display_opts: dict = {
        "statGranularity": granularity,
    }

    create_data = _api_call(f"{entity}.createReport", [restriction_with_dates, display_opts], user_id)
    report_id = create_data["reportId"]
    total_count = create_data.get("totalCount", 0)

    if total_count == 0:
        return []

    cols = display_columns or ["id", "name"] + STAT_COLUMNS
    read_opts = {
        "offset": 0,
        "limit": min(limit, total_count),
        "allowEmptyStatistics": True,
        "displayColumns": cols,
    }

    read_data = _api_call(f"{entity}.readReport", [report_id, read_opts], user_id)
    return read_data.get("report", [])


def _fetch_listing_report(
    entity: str,
    restriction: dict,
    display_columns: list[str],
    limit: int = 5000,
    user_id: int | None = None,
) -> list[dict]:
    """createReport → readReport for pure LISTING entities.

    Some namespaces (e.g. patterns.negative) have no .list method and their
    report is a plain listing: the restrictionFilter must NOT contain
    dateFrom/dateTo and there is no displayOptions struct on create.
    """
    create_data = _api_call(f"{entity}.createReport", [dict(restriction)], user_id)
    report_id = create_data["reportId"]
    total_count = create_data.get("totalCount", 0)

    if total_count == 0:
        return []

    read_opts = {
        "offset": 0,
        "limit": min(limit, total_count),
        "displayColumns": display_columns,
    }
    read_data = _api_call(f"{entity}.readReport", [report_id, read_opts], user_id)
    return read_data.get("report", [])
