"""Sitelink commands."""
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
# Commands — Sitelinks
# ---------------------------------------------------------------------------

def cmd_sitelinks(args: argparse.Namespace) -> None:
    """List sitelinks (sitelinks.list returns soft-deleted rows too — filter them)."""
    data = _api_call("sitelinks.list", [], getattr(args, "user_id", None))
    sitelinks = [s for s in data.get("sitelinks", []) if not s.get("deleted")]

    if args.json:
        out = []
        for s in sitelinks:
            out.append({
                "id": s.get("id"),
                "name": s.get("name"),
                "url": s.get("url"),
                "status": s.get("status"),
            })
        _output_json(out)
    else:
        if not sitelinks:
            print("No sitelinks found.")
            return
        print(f"{'ID':<12} {'Name':<30} {'URL':<40} {'Status'}")
        print("-" * 95)
        for s in sitelinks:
            print(f"{s.get('id', ''):<12} {s.get('name', ''):<30} "
                  f"{s.get('url', ''):<40} {s.get('status', '')}")


def cmd_sitelink_create(args: argparse.Namespace) -> None:
    """Create a sitelink."""
    sitelink: dict = {
        "name": args.name,
        "url": args.url,
    }

    data = _api_call("sitelinks.create", [[sitelink]], getattr(args, "user_id", None))
    ids = data.get("ids", [])

    if args.json:
        _output_json({"sitelinkIds": ids})
    else:
        print(f"Sitelink created: ID {ids[0] if ids else '?'}")


def cmd_sitelink_remove(args: argparse.Namespace) -> None:
    """Remove a sitelink."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("sitelinks.remove", [[args.sitelink_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "sitelinkId": args.sitelink_id})
    else:
        print(f"Sitelink {args.sitelink_id} removed.")


def cmd_sitelink_update(args: argparse.Namespace) -> None:
    """Update a sitelink. NOTE: renaming creates a NEW sitelink ID server-side."""
    if not args.name and not args.url:
        print("ERROR: No fields to update. Use --name or --url.", file=sys.stderr)
        sys.exit(1)

    # The API requires `name` in every update payload — merge over current values.
    current = None
    if not args.name or not args.url:
        data = _api_call("sitelinks.list", [], getattr(args, "user_id", None))
        current = next((s for s in data.get("sitelinks", [])
                        if s.get("id") == args.sitelink_id), None)
        if current is None:
            print(f"ERROR: Sitelink {args.sitelink_id} not found.", file=sys.stderr)
            sys.exit(1)

    sitelink: dict = {
        "id": args.sitelink_id,
        "name": args.name or current.get("name"),
        "url": args.url or current.get("url"),
    }

    data = _api_call("sitelinks.update", [[sitelink]], getattr(args, "user_id", None))
    ids = data.get("ids", [])
    new_id = ids[0] if ids else args.sitelink_id

    if args.json:
        _output_json({"updated": True, "sitelinkId": new_id,
                      "idChanged": new_id != args.sitelink_id})
    else:
        if new_id != args.sitelink_id:
            print(f"Sitelink updated — renaming created a NEW ID: {new_id} "
                  f"(old {args.sitelink_id} was removed). Use the new ID from now on.")
        else:
            print(f"Sitelink {args.sitelink_id} updated.")


# ---------------------------------------------------------------------------
# Assigning sitelinks to campaigns / groups (sitelinks.campaign|group.set/list)
# ---------------------------------------------------------------------------
# set REPLACES the entire assignment of the campaign/group; empty list clears it.

def cmd_sitelink_assign(args: argparse.Namespace) -> None:
    """Assign sitelinks to a campaign or group. REPLACES the whole set."""
    if bool(args.campaign_id) == bool(args.group_id):
        print("ERROR: Use exactly one of --campaign-id or --group-id.", file=sys.stderr)
        sys.exit(1)

    ids = [int(x) for x in args.sitelink_ids.split(",") if x.strip()]
    uid = getattr(args, "user_id", None)

    if args.campaign_id:
        _api_call("sitelinks.campaign.set",
                  [[{"id": args.campaign_id, "sitelinkIds": ids}]], uid)
        target = f"campaign {args.campaign_id}"
    else:
        _api_call("sitelinks.group.set",
                  [[{"id": args.group_id, "sitelinkIds": ids}]], uid)
        target = f"group {args.group_id}"

    if args.json:
        _output_json({"assigned": ids, "campaignId": args.campaign_id,
                      "groupId": args.group_id})
    else:
        if ids:
            print(f"Sitelinks {ids} assigned to {target} (previous assignment replaced).")
        else:
            print(f"All sitelinks cleared from {target}.")


def cmd_sitelinks_assigned(args: argparse.Namespace) -> None:
    """Show sitelinks assigned to a campaign or group."""
    if bool(args.campaign_id) == bool(args.group_id):
        print("ERROR: Use exactly one of --campaign-id or --group-id.", file=sys.stderr)
        sys.exit(1)

    uid = getattr(args, "user_id", None)
    if args.campaign_id:
        data = _api_call("sitelinks.campaign.list", [[args.campaign_id]], uid)
        rows = data.get("campaigns", [])
    else:
        data = _api_call("sitelinks.group.list", [[args.group_id]], uid)
        rows = data.get("groups", [])

    out = []
    for row in rows:
        for s in row.get("sitelinks", []):
            out.append({
                "entityId": row.get("id"),
                "sitelinkId": s.get("id"),
                "name": s.get("name"),
                "url": s.get("url"),
                "status": s.get("status"),
            })

    if args.json:
        _output_json(out)
    else:
        if not out:
            print("No sitelinks assigned.")
            return
        print(f"{'Sitelink ID':<12} {'Name':<30} {'URL':<40} {'Status'}")
        print("-" * 95)
        for s in out:
            print(f"{s['sitelinkId'] or '':<12} {s['name'] or '':<30} "
                  f"{s['url'] or '':<40} {s['status'] or ''}")
