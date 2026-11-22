"""Placement (patterns) commands."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from sklik.api import _api_call, _fail, _fail_msg, _is_sem_blocked
from sklik.formatting import (
    _czk_to_halere, _halere_to_czk, _format_money, _format_share,
    _format_stat_date, _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, _fetch_listing_report, STAT_COLUMNS, stat_columns



# ---------------------------------------------------------------------------
# Commands — Placements (content network "umístění" = patterns.* namespace)
# ---------------------------------------------------------------------------
# Placement targeting of display groups lives in the patterns.* namespace:
# a pattern is a URL string like "forbes.cz" or "www.e15.cz/byznys" attached
# to a group. There is no patterns.list — listing goes through the report API.

def cmd_placements(args: argparse.Namespace) -> None:
    """List placement patterns (content network targeting)."""
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    report = _fetch_report(
        "patterns", {}, date_from, date_to,
        ["id", "pattern", "status", "cpc", "group.id", "group.name"],
        user_id=getattr(args, "user_id", None))

    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    if args.json:
        out = [{
            "id": r.get("id"),
            "pattern": r.get("pattern"),
            "status": r.get("status"),
            "cpc": _halere_to_czk(r.get("cpc")),
            "groupId": r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id"),
            "groupName": r.get("group", {}).get("name") if isinstance(r.get("group"), dict) else r.get("group.name"),
        } for r in report]
        _output_json(out)
    else:
        if not report:
            print("No placements found.")
            return
        print(f"{'ID':<12} {'Pattern':<35} {'Status':<10} {'Group'}")
        print("-" * 80)
        for r in report:
            g_name = r.get("group", {}).get("name", "") if isinstance(r.get("group"), dict) else r.get("group.name", "")
            print(f"{r.get('id', ''):<12} {(r.get('pattern') or ''):<35} "
                  f"{(r.get('status') or ''):<10} {g_name}")


def _group_of(r: dict, key: str):
    g = r.get("group")
    return g.get(key) if isinstance(g, dict) else r.get(f"group.{key}")


def cmd_placement_stats(args: argparse.Namespace) -> None:
    """Statistics per placement pattern (cost, clicks, conversions …).

    `placements` lists the patterns only; the same `patterns` report carries
    the stat columns too (whitelist in reports._ENTITY_STAT_COLUMNS)."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")
    gran = getattr(args, "granularity", "total")
    cols = ["id", "pattern", "status", "cpc", "group.id", "group.name",
            "campaign.id", "campaign.name"] + stat_columns("patterns")
    report = _fetch_report("patterns", {}, date_from, date_to, cols, granularity=gran,
                           user_id=getattr(args, "user_id", None))
    if args.group_id:
        report = [r for r in report if _group_of(r, "id") == args.group_id]
    if args.campaign_id:
        report = [r for r in report
                  if (r.get("campaign", {}).get("id") if isinstance(r.get("campaign"), dict)
                      else r.get("campaign.id")) == args.campaign_id]

    if args.json:
        for r in report:
            if "cpc" in r:
                r["cpc"] = _halere_to_czk(r.get("cpc"))
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
        return
    if not report:
        print("No placement data.")
        return
    print(f"Placement stats ({date_from} — {date_to}):\n")
    for r in report:
        print(f"  {r.get('pattern', '')} (ID: {r.get('id')}, group: {_group_of(r, 'name') or ''})")
        for s in r.get("stats", []):
            print(f"    {_format_stat_date(s, gran)}"
                  f"Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                  f"CTR: {_format_share(s.get('ctr'))}  Cost: {_format_money(s.get('totalMoney'))}  "
                  f"Conv: {s.get('conversions', 0)}  Value: {s.get('conversionValue') or 0} Kč")


def cmd_placement_create(args: argparse.Namespace) -> None:
    """Add a placement pattern (target website) to a display group."""
    pattern: dict = {
        "groupId": args.group_id,
        "pattern": args.pattern,
    }
    if args.cpc is not None:
        pattern["cpc"] = _czk_to_halere(args.cpc)
    if args.status:
        pattern["status"] = args.status

    data = _api_call("patterns.create", [[pattern]], getattr(args, "user_id", None))
    raw_ids = data.get("ids") or data.get("patternIds") or []
    ids = [i.get("id") if isinstance(i, dict) else i for i in raw_ids]

    if args.json:
        _output_json({"patternIds": ids})
    else:
        print(f"Placement created: ID {ids[0] if ids else '?'}")


def cmd_placement_remove(args: argparse.Namespace) -> None:
    """Remove a placement pattern."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("patterns.remove", [[args.pattern_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "patternId": args.pattern_id})
    else:
        print(f"Placement {args.pattern_id} removed.")


# ---------------------------------------------------------------------------
# Negative placements (patterns.negative.*) — exclude websites from a group
# ---------------------------------------------------------------------------
# Like positive patterns there is no .list — listing goes through the report API.

def cmd_placements_excluded(args: argparse.Namespace) -> None:
    """List negative (excluded) placement patterns.

    QUIRK (verified live 2026-07): the report accepts the `pattern` display
    column but never returns its value, so the excluded URL text is not
    available via the API — only in the Sklik web UI. Keep track of what you
    exclude (IDs are returned by placement-exclude).
    """
    report = _fetch_listing_report(
        "patterns.negative", {"isDeleted": False},
        ["id", "pattern", "createDate", "group.id", "group.name"],
        user_id=getattr(args, "user_id", None))

    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    if args.json:
        _output_json([{
            "id": r.get("id"),
            "pattern": r.get("pattern"),  # currently always null (API quirk)
            "createDate": r.get("createDate"),
            "groupId": r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id"),
            "groupName": r.get("group", {}).get("name") if isinstance(r.get("group"), dict) else r.get("group.name"),
        } for r in report])
    else:
        if not report:
            print("No excluded placements found.")
            return
        print(f"{'ID':<12} {'Created':<22} {'Group'}")
        print("-" * 70)
        for r in report:
            g_name = r.get("group", {}).get("name", "") if isinstance(r.get("group"), dict) else r.get("group.name", "")
            print(f"{r.get('id', ''):<12} {(r.get('createDate') or ''):<22} {g_name}")
        print("\n(Pozn.: API nevrací text vzoru — je vidět jen ve webovém rozhraní.)")


def cmd_placement_exclude(args: argparse.Namespace) -> None:
    """Exclude a website (negative placement pattern) from a display group."""
    data = _api_call("patterns.negative.create", [[{
        "groupId": args.group_id,
        "pattern": args.pattern,
    }]], getattr(args, "user_id", None))
    raw_ids = data.get("ids") or []
    ids = [i.get("id") if isinstance(i, dict) else i for i in raw_ids]

    if args.json:
        _output_json({"patternIds": ids})
    else:
        print(f"Placement excluded: ID {ids[0] if ids else '?'}")


def cmd_placement_exclude_remove(args: argparse.Namespace) -> None:
    """Remove a negative placement pattern (stop excluding the website)."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("patterns.negative.remove", [[args.pattern_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "patternId": args.pattern_id})
    else:
        print(f"Excluded placement {args.pattern_id} removed (website no longer excluded).")


def cmd_placement_exclude_restore(args: argparse.Namespace) -> None:
    """Restore a removed negative placement.

    Needed because re-creating the same excluded pattern after a remove fails
    with group_pattern_duplicity — the soft-deleted entry blocks it; restoring
    the old ID is the way to re-exclude the same website.
    """
    _api_call("patterns.negative.restore", [[args.pattern_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"restored": True, "patternId": args.pattern_id})
    else:
        print(f"Excluded placement {args.pattern_id} restored (website excluded again).")
