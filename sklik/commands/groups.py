"""Ad group commands."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from sklik.api import _api_call, _fail, _fail_msg, _is_sem_blocked
from sklik.formatting import (
    _czk_to_halere, _halere_to_czk, _format_money,
    _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, STAT_COLUMNS



# ---------------------------------------------------------------------------
# Commands — Groups (ad groups)
# ---------------------------------------------------------------------------

def cmd_groups(args: argparse.Namespace) -> None:
    """List ad groups."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "maxCpc", "status", "campaign.id", "campaign.name"]

    data = _api_call("groups.list", [restriction, {
        "limit": 500, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    groups = data.get("groups", [])

    # Client-side campaign filter
    if args.campaign_id:
        groups = [g for g in groups
                  if (g.get("campaign", {}).get("id") if isinstance(g.get("campaign"), dict) else g.get("campaign.id")) == args.campaign_id]

    if args.json:
        out = []
        for g in groups:
            out.append({
                "id": g.get("id"),
                "name": g.get("name"),
                "status": g.get("status"),
                "maxCpc": _halere_to_czk(g.get("maxCpc")),
                "campaignId": g.get("campaign", {}).get("id") if isinstance(g.get("campaign"), dict) else g.get("campaign.id"),
                "campaignName": g.get("campaign", {}).get("name") if isinstance(g.get("campaign"), dict) else g.get("campaign.name"),
            })
        _output_json(out)
    else:
        if not groups:
            print("No groups found.")
            return
        print(f"{'ID':<12} {'Name':<30} {'Status':<10} {'Max CPC':<12} {'Campaign'}")
        print("-" * 90)
        for g in groups:
            c_name = g.get("campaign", {}).get("name", "?") if isinstance(g.get("campaign"), dict) else g.get("campaign.name", "?")
            print(f"{g.get('id', ''):<12} {g.get('name', ''):<30} "
                  f"{g.get('status', ''):<10} {_format_money(g.get('maxCpc')):<12} {c_name}")


def cmd_group_create(args: argparse.Namespace) -> None:
    """Create an ad group."""
    group: dict = {
        "campaignId": args.campaign_id,
        "name": args.name,
        "cpc": _czk_to_halere(args.cpc),
    }
    if getattr(args, "max_daily_impression", None) is not None:
        group["maxUserDailyImpression"] = args.max_daily_impression

    data = _api_call("groups.create", [[group]], getattr(args, "user_id", None))
    group_ids = data.get("groupIds", [])

    if args.json:
        _output_json({"groupIds": group_ids})
    else:
        print(f"Group created: ID {group_ids[0] if group_ids else '?'}")


def cmd_group_update(args: argparse.Namespace) -> None:
    """Update an ad group."""
    update: dict = {"id": args.group_id}
    if args.name:
        update["name"] = args.name
    if args.cpc is not None:
        update["cpc"] = _czk_to_halere(args.cpc)
    if args.status:
        update["status"] = args.status
    if getattr(args, "max_daily_impression", None) is not None:
        update["maxUserDailyImpression"] = args.max_daily_impression

    if len(update) == 1:
        _fail_msg("No fields to update. Use --name, --cpc, --status, or --max-daily-impression.")

    _api_call("groups.update", [[update]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "groupId": args.group_id})
    else:
        print(f"Group {args.group_id} updated.")


def cmd_group_remove(args: argparse.Namespace) -> None:
    """Remove an ad group."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("groups.remove", [[args.group_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "groupId": args.group_id})
    else:
        print(f"Group {args.group_id} removed.")


def cmd_group_stats(args: argparse.Namespace) -> None:
    """Show group statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}
    if args.group_id:
        restriction["ids"] = [args.group_id]

    cols = ["id", "name", "campaign.id", "campaign.name"] + STAT_COLUMNS
    report = _fetch_report("groups", restriction, date_from, date_to,
                           cols, user_id=getattr(args, "user_id", None))

    # Client-side campaign filter (API doesn't support campaign.ids in report restriction)
    if args.campaign_id:
        report = [r for r in report
                  if (r.get("campaign", {}).get("id") if isinstance(r.get("campaign"), dict) else r.get("campaign.id")) == args.campaign_id]

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No data.")
            return
        print(f"Group stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  {r.get('name', '?')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {s.get('ctr', 0):.2f}%  Avg CPC: {_format_money(s.get('avgCpc'))}  "
                      f"Cost: {_format_money(s.get('totalMoney'))}  "
                      f"Conv: {s.get('conversions', 0)}")


def cmd_group_restore(args: argparse.Namespace) -> None:
    """Restore (undelete) a removed ad group."""
    _api_call("groups.restore", [[args.group_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"restored": True, "groupId": args.group_id})
    else:
        print(f"Group {args.group_id} restored.")
