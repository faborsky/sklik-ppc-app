"""Keyword & negative keyword commands."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from sklik.api import _api_call, _fail, _fail_msg, _is_sem_blocked
from sklik.commands.campaigns import _get_campaign_type
from sklik.formatting import (
    _czk_to_halere, _halere_to_czk, _format_money,
    _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, STAT_COLUMNS



# ---------------------------------------------------------------------------
# Commands — Keywords
# ---------------------------------------------------------------------------

def cmd_keywords(args: argparse.Namespace) -> None:
    """List keywords."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "cpc", "matchType", "status", "url",
            "group.id", "group.name", "campaign.id"]

    data = _api_call("keywords.list", [restriction, {
        "limit": 5000, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    keywords = data.get("keywords", [])

    # Client-side group/campaign filter
    if args.group_id:
        keywords = [k for k in keywords
                    if (k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id")) == args.group_id]
    if args.campaign_id:
        keywords = [k for k in keywords
                    if (k.get("campaign", {}).get("id") if isinstance(k.get("campaign"), dict) else k.get("campaign.id")) == args.campaign_id]

    if args.json:
        out = []
        for k in keywords:
            out.append({
                "id": k.get("id"),
                "name": k.get("name"),
                "matchType": k.get("matchType"),
                "status": k.get("status"),
                "cpc": _halere_to_czk(k.get("cpc")),
                "url": k.get("url"),
                "groupId": k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id"),
                "groupName": k.get("group", {}).get("name") if isinstance(k.get("group"), dict) else k.get("group.name"),
            })
        _output_json(out)
    else:
        if not keywords:
            print("No keywords found.")
            return
        print(f"{'ID':<12} {'Keyword':<30} {'Match':<10} {'Status':<10} {'CPC':<10} {'Group'}")
        print("-" * 95)
        for k in keywords:
            g_name = k.get("group", {}).get("name", "") if isinstance(k.get("group"), dict) else k.get("group.name", "")
            cpc = k.get("cpc")
            cpc_str = _format_money(cpc) if cpc else "group"
            print(f"{k.get('id', ''):<12} {k.get('name', ''):<30} "
                  f"{k.get('matchType', ''):<10} {k.get('status', ''):<10} "
                  f"{cpc_str:<10} {g_name}")


def cmd_keyword_create(args: argparse.Namespace) -> None:
    """Create a keyword."""
    kw: dict = {
        "name": args.name,
        "groupId": args.group_id,
        "matchType": args.match_type,
    }
    if args.cpc is not None:
        kw["cpc"] = _czk_to_halere(args.cpc)
    if args.url:
        kw["url"] = args.url

    data = _api_call("keywords.create", [[kw]], getattr(args, "user_id", None))
    kw_ids = data.get("positiveKeywordIds", [])

    if args.json:
        _output_json({"keywordIds": kw_ids})
    else:
        print(f"Keyword created: ID {kw_ids[0] if kw_ids else '?'}")


def cmd_keyword_create_batch(args: argparse.Namespace) -> None:
    """Batch create keywords from JSON array."""
    try:
        keywords_data = json.loads(args.keywords_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    batch = []
    for kw in keywords_data:
        item: dict = {
            "name": kw["name"],
            "groupId": args.group_id,
            "matchType": kw.get("matchType", "broad"),
        }
        if "cpc" in kw and kw["cpc"] is not None:
            item["cpc"] = _czk_to_halere(kw["cpc"])
        if "url" in kw:
            item["url"] = kw["url"]
        batch.append(item)

    data = _api_call("keywords.create", [batch], getattr(args, "user_id", None))
    kw_ids = data.get("positiveKeywordIds", [])

    if args.json:
        _output_json({"keywordIds": kw_ids, "count": len(kw_ids)})
    else:
        print(f"Created {len(kw_ids)} keywords: {kw_ids}")


def cmd_keyword_update(args: argparse.Namespace) -> None:
    """Update a keyword."""
    update: dict = {"id": args.keyword_id}
    if args.cpc is not None:
        update["cpc"] = _czk_to_halere(args.cpc)
    if args.status:
        update["status"] = args.status
    if args.url:
        update["url"] = args.url

    if len(update) == 1:
        print("ERROR: No fields to update. Use --cpc, --status, or --url.", file=sys.stderr)
        sys.exit(1)

    _api_call("keywords.update", [[update]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "keywordId": args.keyword_id})
    else:
        print(f"Keyword {args.keyword_id} updated.")


def cmd_keyword_remove(args: argparse.Namespace) -> None:
    """Remove a keyword."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("keywords.remove", [[args.keyword_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "keywordId": args.keyword_id})
    else:
        print(f"Keyword {args.keyword_id} removed.")


def cmd_keyword_stats(args: argparse.Namespace) -> None:
    """Show keyword statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}

    cols = ["id", "name", "matchType", "group.id", "group.name", "campaign.id"] + STAT_COLUMNS
    report = _fetch_report("keywords", restriction, date_from, date_to,
                           cols, user_id=getattr(args, "user_id", None))

    # Client-side group/campaign filter
    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]
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
        print(f"Keyword stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  [{r.get('matchType', '?')}] {r.get('name', '?')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {s.get('ctr', 0):.2f}%  Avg CPC: {_format_money(s.get('avgCpc'))}  "
                      f"Cost: {_format_money(s.get('totalMoney'))}  "
                      f"Conv: {s.get('conversions', 0)}")


# ---------------------------------------------------------------------------
# Commands — Negative keywords
# ---------------------------------------------------------------------------

def cmd_negatives(args: argparse.Namespace) -> None:
    """List negative keywords."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "matchType", "group.id", "group.name"]

    data = _api_call("keywords.negative.list", [restriction, {
        "limit": 5000, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    keywords = data.get("keywords", [])

    # Client-side group/campaign filter. keywords.negative.list returns only
    # group-level negatives (campaign-level ones are write-only in the API),
    # so --campaign-id filters via the campaign's groups.
    if args.group_id:
        keywords = [k for k in keywords
                    if (k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id")) == args.group_id]
    elif args.campaign_id:
        gdata = _api_call("groups.list", [{"isDeleted": False}, {
            "limit": 5000, "offset": 0, "displayColumns": ["id", "campaign.id"],
        }], getattr(args, "user_id", None))
        allowed = {g.get("id") for g in gdata.get("groups", [])
                   if (g.get("campaign", {}).get("id") if isinstance(g.get("campaign"), dict) else g.get("campaign.id")) == args.campaign_id}
        keywords = [k for k in keywords
                    if (k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id")) in allowed]

    if args.json:
        out = []
        for k in keywords:
            out.append({
                "id": k.get("id"),
                "name": k.get("name"),
                "matchType": k.get("matchType"),
                "groupId": k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id"),
            })
        _output_json(out)
    else:
        if not keywords:
            print("No negative keywords found.")
            return
        print(f"{'ID':<12} {'Keyword':<30} {'Match Type':<20} {'Group'}")
        print("-" * 75)
        for k in keywords:
            g_name = k.get("group", {}).get("name", "") if isinstance(k.get("group"), dict) else k.get("group.name", "")
            print(f"{k.get('id', ''):<12} {k.get('name', ''):<30} "
                  f"{k.get('matchType', ''):<20} {g_name}")


def cmd_negative_add(args: argparse.Namespace) -> None:
    """Add a negative keyword (group-level or campaign-level)."""
    # Campaign-level negatives go through campaigns.update (requires type field)
    if args.campaign_id and not args.group_id:
        camp_type = _get_campaign_type(args.campaign_id, getattr(args, "user_id", None))
        neg = {"name": args.name, "matchType": args.match_type}
        data = _api_call("campaigns.update", [[{
            "id": args.campaign_id,
            "type": camp_type,
            "negativeKeywords": [neg],
        }]], getattr(args, "user_id", None))
        if args.json:
            _output_json({"campaignId": args.campaign_id, "added": 1, "level": "campaign"})
        else:
            print(f"Campaign-level negative added to campaign {args.campaign_id}.")
        return

    if not args.group_id:
        print("ERROR: --group-id or --campaign-id is required.", file=sys.stderr)
        sys.exit(1)

    neg: dict = {
        "name": args.name,
        "matchType": args.match_type,
        "groupId": args.group_id,
    }

    data = _api_call("keywords.negative.create", [[neg]], getattr(args, "user_id", None))
    neg_ids = data.get("negativeKeywordIds", [])

    if args.json:
        _output_json({"negativeKeywordIds": neg_ids})
    else:
        print(f"Negative keyword added: ID {neg_ids[0] if neg_ids else '?'}")


def cmd_negative_add_batch(args: argparse.Namespace) -> None:
    """Batch add negative keywords (group-level or campaign-level)."""
    try:
        keywords_data = json.loads(args.keywords_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    negs = []
    for kw in keywords_data:
        negs.append({
            "name": kw["name"] if isinstance(kw, dict) else kw,
            "matchType": kw.get("matchType", "negativeBroad") if isinstance(kw, dict) else "negativeBroad",
        })

    # Campaign-level negatives go through campaigns.update (requires type field)
    if args.campaign_id and not args.group_id:
        camp_type = _get_campaign_type(args.campaign_id, getattr(args, "user_id", None))
        data = _api_call("campaigns.update", [[{
            "id": args.campaign_id,
            "type": camp_type,
            "negativeKeywords": negs,
        }]], getattr(args, "user_id", None))
        if args.json:
            _output_json({"campaignId": args.campaign_id, "added": len(negs), "level": "campaign"})
        else:
            print(f"Added {len(negs)} campaign-level negatives to campaign {args.campaign_id}.")
        return

    if not args.group_id:
        print("ERROR: --group-id or --campaign-id is required.", file=sys.stderr)
        sys.exit(1)

    # Group-level negatives via keywords.negative.create
    batch = []
    for neg in negs:
        neg["groupId"] = args.group_id
        batch.append(neg)

    data = _api_call("keywords.negative.create", [batch], getattr(args, "user_id", None))
    neg_ids = data.get("negativeKeywordIds", [])

    if args.json:
        _output_json({"negativeKeywordIds": neg_ids, "count": len(neg_ids)})
    else:
        print(f"Added {len(neg_ids)} group-level negative keywords.")


def cmd_negative_remove(args: argparse.Namespace) -> None:
    """Remove a negative keyword."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("keywords.negative.remove", [[args.keyword_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "keywordId": args.keyword_id})
    else:
        print(f"Negative keyword {args.keyword_id} removed.")


def cmd_keyword_restore(args: argparse.Namespace) -> None:
    """Restore (undelete) a removed keyword."""
    _api_call("keywords.restore", [[args.keyword_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"restored": True, "keywordId": args.keyword_id})
    else:
        print(f"Keyword {args.keyword_id} restored.")


def cmd_keyword_set(args: argparse.Namespace) -> None:
    """Declaratively set a group's keywords (upsert; --remove-others syncs).

    keywords.set adds missing keywords, updates cpc/url of existing ones and
    restores previously removed ones. With --remove-others it also deletes
    every keyword NOT in the payload — a full sync of the group.
    """
    try:
        keywords_data = json.loads(args.keywords_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    kws = []
    for kw in keywords_data:
        if isinstance(kw, str):
            kws.append({"name": kw, "matchType": "broad"})
            continue
        item: dict = {"name": kw["name"], "matchType": kw.get("matchType", "broad")}
        if kw.get("cpc") is not None:
            item["cpc"] = _czk_to_halere(kw["cpc"])
        if kw.get("url"):
            item["url"] = kw["url"]
        kws.append(item)

    data = _api_call("keywords.set",
                     [args.group_id, kws, bool(args.remove_others)],
                     getattr(args, "user_id", None))
    ids = data.get("keywordIds", [])

    if args.json:
        _output_json({"keywordIds": ids, "groupId": args.group_id,
                      "removedOthers": bool(args.remove_others)})
    else:
        print(f"Group {args.group_id}: set {len(kws)} keywords "
              f"({'removed others' if args.remove_others else 'others kept'}); "
              f"affected IDs: {len(ids)}")
