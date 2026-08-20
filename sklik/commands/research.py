"""Keyword research & search query commands."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from sklik.api import _api_call, _fail, _fail_msg, _is_sem_blocked
from sklik.formatting import (
    _czk_to_halere, _halere_to_czk, _format_money, _format_share,
    _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, STAT_COLUMNS



# ---------------------------------------------------------------------------
# Commands — Keyword Research
# ---------------------------------------------------------------------------

def cmd_suggest(args: argparse.Namespace) -> None:
    """Get keyword suggestions."""
    opts: dict = {
        "offset": 0,
        "limit": args.limit,
        "related": args.related,
        "orderBy": args.order_by,
        "orderDirection": "desc",
    }

    # suggest doesn't support managed accounts (userId)
    data = _api_call("keywords.suggest", [args.query, opts])
    suggestions = data.get("suggestions", [])

    if args.json:
        out = []
        for s in suggestions:
            out.append({
                "query": s.get("query"),
                "avgSearchCount": s.get("avgSearchCount"),
                "cpc": _halere_to_czk(s.get("cpc")),
            })
        _output_json(out)
    else:
        if not suggestions:
            print("No suggestions found.")
            return
        print(f"{'Keyword':<40} {'Avg Searches':<15} {'CPC'}")
        print("-" * 65)
        for s in suggestions:
            print(f"{s.get('query', ''):<40} {s.get('avgSearchCount', 0):<15} "
                  f"{_format_money(s.get('cpc'))}")
        print(f"\nTotal: {data.get('total', len(suggestions))} suggestions")


def cmd_suggest_stats(args: argparse.Namespace) -> None:
    """Get search volume stats for keywords."""
    queries = [q.strip() for q in args.queries.split(",")]
    opts: dict = {"granularity": args.granularity}

    # suggest.stats doesn't support managed accounts (userId)
    data = _api_call("keywords.suggest.stats", [queries, opts])
    stats = data.get("stats", [])

    if args.json:
        out = []
        for s in stats:
            out.append({
                "query": s.get("query"),
                "avgSearchCount": s.get("avgSearchCount"),
                "avgCpc": _halere_to_czk(s.get("avgCpc")),
                "searchCountInTime": s.get("searchCountInTime", []),
            })
        _output_json(out)
    else:
        if not stats:
            print("No stats found.")
            return
        for s in stats:
            print(f"\n{s.get('query', '?')}:")
            print(f"  Avg searches: {s.get('avgSearchCount', 0)}  Avg CPC: {_format_money(s.get('avgCpc'))}")
            timeline = s.get("searchCountInTime", [])
            if timeline:
                print(f"  Timeline:")
                for t in timeline[-12:]:  # Last 12 periods
                    print(f"    {t.get('timePeriod', '?')}: {t.get('searchCount', 0)}")


# ---------------------------------------------------------------------------
# Commands — Search queries
# ---------------------------------------------------------------------------

def cmd_search_queries(args: argparse.Namespace) -> None:
    """Show search query report."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}

    cols = ["query", "clicks", "impressions", "avgCpc", "totalMoney",
            "conversions", "conversionValue", "keyword.id", "keyword.name", "keyword.matchType",
            "group.id", "group.name", "campaign.id"]
    # The campaign/group filter runs client-side, so with one set we must read
    # the WHOLE report first — capping the fetch would filter a truncated head
    # and quietly under-report the campaign. --limit then caps what's shown.
    filtered = bool(args.campaign_id or args.group_id)
    report = _fetch_report("queries", restriction, date_from, date_to,
                           cols, limit=None if filtered else args.limit,
                           user_id=getattr(args, "user_id", None))

    if args.campaign_id:
        report = [r for r in report
                  if (r.get("campaign", {}).get("id") if isinstance(r.get("campaign"), dict) else r.get("campaign.id")) == args.campaign_id]
    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    matched = len(report)
    if args.limit and matched > args.limit:
        report = report[:args.limit]

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No search queries found.")
            return
        if matched > len(report):
            shown = f" — showing first {len(report)} of {matched}"
        elif args.limit and len(report) >= args.limit:
            # Unfiltered read stops at --limit rows, so this may not be all.
            shown = f" — capped at --limit {args.limit}, there may be more"
        else:
            shown = ""
        print(f"Search queries ({date_from} — {date_to}){shown}:\n")
        print(f"{'Query':<40} {'Clicks':<8} {'Impr':<8} {'CTR':<8} {'Cost'}")
        print("-" * 80)
        for r in report:
            query = r.get("query", "?")
            if len(query) > 38:
                query = query[:36] + ".."
            stats = r.get("stats", [{}])
            s = stats[0] if stats else {}
            print(f"{query:<40} {s.get('clicks', 0):<8} {s.get('impressions', 0):<8} "
                  f"{_format_share(s.get('ctr')):<9} {_format_money(s.get('totalMoney'))}")
