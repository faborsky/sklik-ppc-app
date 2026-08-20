"""Campaign commands."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from sklik.api import _api_call, _fail, _fail_msg, _fetch_all, _is_sem_blocked
from sklik.formatting import (
    _czk_to_halere, _halere_to_czk, _format_money, _format_share,
    _format_stat_date, _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, stat_columns



# ---------------------------------------------------------------------------
# Targeting helpers (campaign regions / device bids / schedule)
# ---------------------------------------------------------------------------

# Sentinel: --schedule-json not used at all (None means "clear the schedule").
_SCHEDULE_UNSET = object()

def _parse_regions(value: str | None) -> list[dict] | None:
    """Parse a comma-separated list of region IDs into the API's struct form.

    The API takes `regions` as an array of structs `[{"predefinedId": id}, …]`
    — bare ints are rejected with `400 … regions[0] must be struct, not int`.
    It also refuses an empty array AND nil, so geo targeting cannot be cleared
    through the API at all (web UI only) — we fail loudly instead of sending a
    payload that always 400s.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        _fail_msg("--regions cannot be empty: the API rejects both an empty array "
                  "and nil, so geo targeting can't be cleared via the API "
                  "(remove it in the Sklik web UI). Pass region IDs to change it.")
    try:
        ids = [int(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError:
        _fail_msg("--regions must be comma-separated integers (region IDs, see the `regions` command).")
    if not ids:
        _fail_msg("--regions contains no region IDs.")
    return [{"predefinedId": i} for i in ids]


def _parse_device_bids(value: str | None) -> dict | None:
    """Parse 'desktop:mobile:tablet:other' percentage modifiers into a struct.

    Values MUST be whole percents — the API rejects floats
    (`400 … devicesPriceRatio.desktop must be int, not double`).
    """
    if value is None:
        return None
    parts = value.split(":")
    if len(parts) != 4:
        _fail_msg("--device-bids must be 'desktop:mobile:tablet:other' "
                  "(e.g. 0:-30:-30:-100).")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        _fail_msg("--device-bids values must be numbers (percent modifiers).")
    if any(n != int(n) for n in nums):
        _fail_msg("--device-bids values must be whole percents — the API rejects "
                  "decimals (e.g. use -30, not -30.5).")
    desktop, mobile, tablet, other = (int(n) for n in nums)
    return {"desktop": desktop, "mobile": mobile, "tablet": tablet, "other": other}


def _parse_schedule(value: str | None) -> object:
    """Parse --schedule-json into the API's shape: 7 arrays of 24 hourly ints.

    The API takes `schedule` as an array of 7 day-arrays (week starts Monday),
    each with 24 values, or nil to clear it. The legacy
    `{"daySchedule":[{"value":[…]}, …]}` form (which the API rejects) is
    accepted here and normalised, since older docs advertised it.

    Returns `_SCHEDULE_UNSET` when the flag wasn't used, `None` for an explicit
    clear (JSON `null`), otherwise the normalised 7×24 array.
    """
    if value is None:
        return _SCHEDULE_UNSET
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        _fail_msg(f"Invalid --schedule-json: {e}")

    if parsed is None:
        return None  # explicit clear — the API accepts nil for schedule

    # Legacy/read shape: {"daySchedule": [{"value": [...]}, ...]}
    if isinstance(parsed, dict):
        days = parsed.get("daySchedule")
        if not isinstance(days, list):
            _fail_msg("--schedule-json must be an array of 7 day-arrays "
                      "(24 hourly values each), or null to clear.")
        parsed = [d.get("value") if isinstance(d, dict) else d for d in days]

    if not isinstance(parsed, list) or len(parsed) != 7:
        _fail_msg("--schedule-json must contain exactly 7 days (week starts Monday); "
                  "e.g. [[100,100,…×24], …×7]. Use null to clear the schedule.")

    normalised = []
    for i, day in enumerate(parsed):
        if isinstance(day, dict):  # {"value": [...]} per day
            day = day.get("value")
        if not isinstance(day, list) or len(day) != 24:
            _fail_msg(f"--schedule-json: day {i + 1} must be an array of 24 hourly values (0-100).")
        try:
            hours = [int(h) for h in day]
        except (TypeError, ValueError):
            _fail_msg(f"--schedule-json: day {i + 1} contains a non-numeric hourly value.")
        if any(h < 0 or h > 100 for h in hours):
            _fail_msg(f"--schedule-json: day {i + 1} has values outside the 0-100 range.")
        normalised.append(hours)
    return normalised


def _format_schedule(schedule: object) -> list[str]:
    """Summarise a campaign schedule (7×24 hourly %) into per-day active windows.

    The API returns `schedule` as an array of 7 day-arrays (empty array = no
    schedule); the legacy `{"daySchedule": …}` struct is still tolerated.
    """
    if isinstance(schedule, dict):
        days = schedule.get("daySchedule", [])
    elif isinstance(schedule, list):
        days = schedule
    else:
        days = []
    if not days:
        return ["(none — runs all the time)"]
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    lines = []
    for i, day in enumerate(days[:7]):
        if isinstance(day, dict):
            hours = day.get("value", [])
        elif isinstance(day, list):
            hours = day
        else:
            hours = []
        active = [h for h, v in enumerate(hours) if v and v > 0]
        if not active:
            summary = "off"
        elif len(active) == 24:
            summary = "24h"
        else:
            summary = ", ".join(f"{h}:00" for h in active)
        lines.append(f"  {names[i] if i < 7 else i}: {summary}")
    return lines or ["(none — runs all the time)"]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _lookup_campaign_type(campaign_id: int, user_id: int | None = None) -> str | None:
    """Campaign type by ID, or None if the campaign doesn't exist.

    Asks for the ONE campaign (`ids` restriction) — never a whole-account
    listing, which would both waste rows and miss campaigns beyond the page.
    """
    # _soft: an ID from another account comes back as 403 Access Denied, which
    # for the caller means the same thing as "not here" — a clean message beats
    # a raw API status.
    data = _api_call("campaigns.list", [
        {"ids": [campaign_id]},
        {"limit": 1, "offset": 0, "displayColumns": ["id", "type"]},
    ], user_id, _soft=True)
    if data.get("status") not in (200, 206):
        return None
    campaigns = data.get("campaigns", [])
    return campaigns[0].get("type", "fulltext") if campaigns else None


def _get_campaign_type(campaign_id: int, user_id: int | None = None) -> str:
    """Campaign type (needed for campaigns.update), defaulting to fulltext."""
    return _lookup_campaign_type(campaign_id, user_id) or "fulltext"


# ---------------------------------------------------------------------------
# Commands — Campaigns
# ---------------------------------------------------------------------------

def cmd_campaigns(args: argparse.Namespace) -> None:
    """List campaigns."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "status", "budget.dayBudget", "type",
            "adSelection", "createDate", "startDate", "endDate"]

    campaigns = _fetch_all("campaigns.list", restriction, cols, "campaigns",
                           getattr(args, "user_id", None))

    # Client-side status filter (API doesn't support it in restriction)
    if args.status:
        campaigns = [c for c in campaigns if c.get("status") == args.status]

    if args.json:
        out = []
        for c in campaigns:
            budget = c.get("budget", {}) if isinstance(c.get("budget"), dict) else {}
            out.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "type": c.get("type"),
                "dayBudget": _halere_to_czk(budget.get("dayBudget")),
                "adSelection": c.get("adSelection"),
                "createDate": c.get("createDate"),
                "startDate": c.get("startDate"),
                "endDate": c.get("endDate"),
            })
        _output_json(out)
    else:
        if not campaigns:
            print("No campaigns found.")
            return
        print(f"{'ID':<12} {'Name':<35} {'Status':<10} {'Type':<10} "
              f"{'Day Budget':<12} {'Rotation':<10}")
        print("-" * 96)
        for c in campaigns:
            budget = c.get("budget", {}) if isinstance(c.get("budget"), dict) else {}
            print(f"{c.get('id', ''):<12} {c.get('name', ''):<35} "
                  f"{c.get('status', ''):<10} {c.get('type', ''):<10} "
                  f"{_format_money(budget.get('dayBudget')):<12} "
                  f"{c.get('adSelection') or '—':<10}")


def cmd_campaign_create(args: argparse.Namespace) -> None:
    """Create a campaign."""
    campaign: dict = {
        "name": args.name,
        "dayBudget": _czk_to_halere(args.day_budget),
        "type": args.type,
    }
    if args.status:
        campaign["status"] = args.status
    regions = _parse_regions(getattr(args, "regions", None))
    if regions is not None:
        campaign["regions"] = regions
    device_bids = _parse_device_bids(getattr(args, "device_bids", None))
    if device_bids is not None:
        campaign["devicesPriceRatio"] = device_bids
    if getattr(args, "ad_selection", None):
        campaign["adSelection"] = args.ad_selection

    data = _api_call("campaigns.create", [[campaign]], getattr(args, "user_id", None))
    campaign_ids = data.get("campaignIds", [])

    if args.json:
        _output_json({"campaignIds": campaign_ids})
    else:
        print(f"Campaign created: ID {campaign_ids[0] if campaign_ids else '?'}")


def cmd_campaign_update(args: argparse.Namespace) -> None:
    """Update a campaign."""
    # campaigns.update always needs the 'type' field — fetch just this campaign
    # (a whole-account listing used to be paged and silently missed campaign
    # #101 onwards, failing the update with a bogus "not found").
    user_id = getattr(args, "user_id", None)
    campaign_type = _lookup_campaign_type(args.campaign_id, user_id)
    if not campaign_type:
        _fail_msg(f"Campaign {args.campaign_id} not found.", campaignId=args.campaign_id)

    update: dict = {"id": args.campaign_id, "type": campaign_type}
    if args.name:
        update["name"] = args.name
    if args.day_budget is not None:
        update["dayBudget"] = _czk_to_halere(args.day_budget)
    if args.status:
        update["status"] = args.status
    regions = _parse_regions(getattr(args, "regions", None))
    if regions is not None:
        update["regions"] = regions
    device_bids = _parse_device_bids(getattr(args, "device_bids", None))
    if device_bids is not None:
        update["devicesPriceRatio"] = device_bids
    schedule = _parse_schedule(getattr(args, "schedule_json", None))
    if schedule is not _SCHEDULE_UNSET:
        update["schedule"] = schedule  # None = explicit clear (API accepts nil)
    if getattr(args, "ad_selection", None):
        update["adSelection"] = args.ad_selection

    if len(update) == 2:  # only id + type, no actual changes
        _fail_msg("No fields to update.")

    data = _api_call("campaigns.update", [[update]], user_id)
    if args.json:
        _output_json({"updated": True, "campaignId": args.campaign_id})
    else:
        print(f"Campaign {args.campaign_id} updated.")


def cmd_campaign_remove(args: argparse.Namespace) -> None:
    """Remove a campaign."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("campaigns.remove", [[args.campaign_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "campaignId": args.campaign_id})
    else:
        print(f"Campaign {args.campaign_id} removed.")


def cmd_campaign_stats(args: argparse.Namespace) -> None:
    """Show campaign statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    gran = getattr(args, "granularity", "total")
    restriction: dict = {}
    if args.campaign_id:
        restriction["ids"] = [args.campaign_id]

    cols = ["id", "name"] + stat_columns("campaigns")
    report = _fetch_report("campaigns", restriction, date_from, date_to,
                           cols, granularity=gran,
                           user_id=getattr(args, "user_id", None))

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No data.")
            return
        print(f"Campaign stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  {r.get('name', '?')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    {_format_stat_date(s, gran)}"
                      f"Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {_format_share(s.get('ctr'))}  Avg CPC: {_format_money(s.get('avgCpc'))}  "
                      f"Cost: {_format_money(s.get('totalMoney'))}  "
                      f"Conv: {s.get('conversions', 0)}")


def cmd_campaign_targeting(args: argparse.Namespace) -> None:
    """Show geo / device / schedule targeting for a campaign."""
    cols = ["id", "name", "regions.id", "regions.name",
            "devicesPriceRatio", "schedule"]
    data = _api_call("campaigns.list", [
        {"ids": [args.campaign_id]},
        {"limit": 1, "offset": 0, "displayColumns": cols},
    ], getattr(args, "user_id", None))
    campaigns = data.get("campaigns", [])
    if not campaigns:
        print(f"ERROR: Campaign {args.campaign_id} not found.", file=sys.stderr)
        sys.exit(1)
    c = campaigns[0]
    regions = c.get("regions", []) or []
    devices = c.get("devicesPriceRatio", {}) or {}
    schedule = c.get("schedule")

    if args.json:
        _output_json({
            "id": c.get("id"),
            "name": c.get("name"),
            "regions": regions,
            "devicesPriceRatio": devices,
            "schedule": schedule,
        })
    else:
        print(f"Targeting for: {c.get('name', '?')} (ID: {c.get('id')})\n")
        print("Regions (geo):")
        if regions:
            for r in regions:
                print(f"  {r.get('id')}: {r.get('name', '?')}")
        else:
            print("  (all regions)")
        print("\nDevice bid modifiers (%):")
        if devices:
            print(f"  desktop: {devices.get('desktop', 0)}  mobile: {devices.get('mobile', 0)}  "
                  f"tablet: {devices.get('tablet', 0)}  other: {devices.get('other', 0)}")
        else:
            print("  (none)")
        print("\nSchedule (active hours per day):")
        for line in _format_schedule(schedule):
            print(line)


def cmd_campaign_restore(args: argparse.Namespace) -> None:
    """Restore (undelete) a removed campaign."""
    _api_call("campaigns.restore", [[args.campaign_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"restored": True, "campaignId": args.campaign_id})
    else:
        print(f"Campaign {args.campaign_id} restored.")
