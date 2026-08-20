"""Two-step report helper (createReport -> readReport)."""
from __future__ import annotations

from sklik.api import _api_call, _list_page_size



# ---------------------------------------------------------------------------
# Report helper (two-step: createReport → readReport)
# ---------------------------------------------------------------------------

BASE_STAT_COLUMNS = [
    "clicks", "impressions", "ctr", "avgCpc", "avgPos",
    "totalMoney", "conversions", "conversionValue",
    "transactions", "pno",
    "missImpressions", "underLowerThreshold", "exhaustedBudget",
    "ish", "ishContext", "ishSum",
]

# Columns the API accepts only for SOME report entities. Asking for one where
# it isn't allowed fails the whole readReport with 400, so they can't live in
# the shared base. Verified live 2026-08-11 by sending an invalid column and
# reading the whitelist the API returns in the error (see docs/api-notes.md).
_ENTITY_EXTRA_STAT_COLUMNS = {
    "campaigns": ["impressionMoney", "clickMoney", "avgCpt",
                  "exhaustedBudgetShare", "underForestThreshold", "stoppedBySchedule"],
    "groups": ["impressionMoney", "clickMoney", "avgCpt",
               "exhaustedBudgetShare", "underForestThreshold", "stoppedBySchedule",
               "winRate"],
    "keywords": ["impressionMoney", "clickMoney",
                 "exhaustedBudgetShare", "underForestThreshold", "stoppedBySchedule"],
    "ads": ["impressionMoney", "clickMoney", "avgCpt",
            "exhaustedBudgetShare", "underForestThreshold", "stoppedBySchedule"],
}

# Kept for backwards compatibility with anything importing the old name.
STAT_COLUMNS = list(BASE_STAT_COLUMNS)

# Granularity values the API's displayOptions.statGranularity accepts.
STAT_GRANULARITIES = ["total", "daily", "weekly", "monthly", "quarterly", "yearly"]


def stat_columns(entity: str) -> list[str]:
    """Stat columns valid for `entity`: the shared base plus its extras.

    `winRate` (share of auctions won) exists ONLY on groups — the campaign
    report has no equivalent, and campaign-level frequency capping isn't
    exposed by the API at all.
    """
    return BASE_STAT_COLUMNS + _ENTITY_EXTRA_STAT_COLUMNS.get(entity, [])


def _read_report_rows(
    entity: str,
    report_id: object,
    total_count: int,
    read_opts: dict,
    limit: int | None,
    user_id: int | None,
) -> list[dict]:
    """Read a prepared report, walking offsets to the end of `total_count`.

    One readReport call returns at most the account's `statsDataLimit` (5000) —
    asking for more is a `406`, and asking for exactly the cap on a bigger
    report silently drops the rest.

    **`offset`/`limit`/`totalCount` count ENTITIES, not returned rows.** On the
    entity reports (campaigns/groups/keywords/ads) that's the same thing, but
    the `queries` report returns all search queries of the keywords in the
    window — asking for 5 keywords can hand back 6 rows, and 138 keywords
    yield 127 query rows (verified live 2026-08-20). So the offset advances by
    the page size, NEVER by len(rows) — that would re-read and duplicate.

    `limit` (when given) is the caller's own cap on ROWS, e.g. `--limit`.
    """
    page_size = _list_page_size(user_id)
    rows: list[dict] = []
    offset = 0
    while offset < total_count:
        page_limit = min(page_size, total_count - offset)
        opts = dict(read_opts)
        opts["offset"] = offset
        opts["limit"] = page_limit
        data = _api_call(f"{entity}.readReport", [report_id, opts], user_id)
        rows.extend(data.get("report", []) or [])
        offset += page_limit
        if limit is not None and len(rows) >= limit:
            break
    return rows[:limit] if limit is not None else rows


def _fetch_report(
    entity: str,
    restriction: dict,
    date_from: str,
    date_to: str,
    display_columns: list[str] | None = None,
    granularity: str = "total",
    limit: int | None = None,
    user_id: int | None = None,
) -> list[dict]:
    """Create and read a report in one step (all rows unless `limit` says less)."""
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
    return _read_report_rows(entity, report_id, total_count, {
        "allowEmptyStatistics": True,
        "displayColumns": cols,
    }, limit, user_id)


def _fetch_listing_report(
    entity: str,
    restriction: dict,
    display_columns: list[str],
    limit: int | None = None,
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

    return _read_report_rows(entity, report_id, total_count,
                             {"displayColumns": display_columns}, limit, user_id)
