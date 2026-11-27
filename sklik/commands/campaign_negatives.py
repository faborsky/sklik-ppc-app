"""Campaign-level negative keywords — via API Fénix (sklik/fenix.py).

DRAK can WRITE campaign negatives (campaigns.update negativeKeywords) but never read them
back, and it is unclear whether such a write appends or replaces. Fénix has explicit
operations: GET lists, POST adds (append), POST …/delete removes given items, PUT replaces
the whole set (not wrapped — too easy to wipe a list by accident).

Match types: Fénix calls broad negative `negative`; DRAK calls it `negativeBroad`. Both
spellings are accepted and shown as DRAK's names for consistency with the rest of the CLI.

Networks (Fénix spec 1.40.0, 2026-11-13): every negative belongs to a network —
`fulltext` (search) or `context` (content). `network` is one value for the WHOLE request
body, not per keyword. Omitted on add → the server picks a default from the campaign
type; omitted on delete → the keyword is deleted from BOTH networks. The same text can
therefore exist twice (once per network), so duplicates are judged per network.
"""
from __future__ import annotations

import argparse
import json
import sys

from sklik.api import _fail_msg
from sklik import fenix
from sklik.formatting import _output_json

_TO_FENIX = {"negativeBroad": "negative", "negative": "negative",
             "negativePhrase": "negativePhrase", "negativeExact": "negativeExact"}
_FROM_FENIX = {"negative": "negativeBroad", "negativePhrase": "negativePhrase",
               "negativeExact": "negativeExact"}
NETWORKS = ("fulltext", "context")


def _path(campaign_id: int) -> str:
    return f"/sklik/campaigns/{campaign_id}/negative-keywords/"


def _list(campaign_id: int, uid: int | None, network: str | None = None) -> list[dict]:
    items: list[dict] = []
    offset, limit = 0, 1000
    params: dict = {"a": ["name", "matchType", "network"]}
    if network:
        params["network"] = network
    while True:
        body = fenix.call("GET", _path(campaign_id), {**params, "offset": offset, "limit": limit})
        page = (body or {}).get("items", [])
        items.extend({"name": k.get("name"),
                      "matchType": _FROM_FENIX.get(k.get("matchType"), k.get("matchType")),
                      "network": k.get("network")}
                     for k in page)
        if len(page) < limit:
            return items
        offset += limit


def _key(item: dict) -> tuple[str, str]:
    return (item["name"].lower(), item["matchType"])


def _body(items: list[dict], network: str | None) -> dict:
    body: dict = {"negativeKeywords": [{"name": i["name"], "matchType": _TO_FENIX[i["matchType"]]}
                                       for i in items]}
    if network:
        body["network"] = network
    return body


def _items(args: argparse.Namespace) -> list[dict]:
    if args.keywords_json:
        try:
            raw = json.loads(args.keywords_json)
        except json.JSONDecodeError as e:
            _fail_msg(f"Invalid --keywords-json: {e}")
        items = [{"name": k["name"], "matchType": k.get("matchType", args.match_type)}
                 if isinstance(k, dict) else {"name": k, "matchType": args.match_type} for k in raw]
    elif args.name:
        items = [{"name": args.name, "matchType": args.match_type}]
    else:
        _fail_msg("Give --name (with --match-type) or --keywords-json.")
    for i in items:
        if i.get("matchType") not in _TO_FENIX:
            _fail_msg(f"Bad or missing match type for '{i.get('name')}': use negativeBroad, "
                      f"negativePhrase or negativeExact.")
    return items


def cmd_negatives_campaign(args: argparse.Namespace) -> None:
    """List campaign-level negative keywords (impossible through DRAK)."""
    items = _list(args.campaign_id, getattr(args, "user_id", None), getattr(args, "network", None))
    if args.json:
        _output_json(items)
        return
    if not items:
        print(f"No campaign-level negatives on campaign {args.campaign_id}.")
        return
    print(f"{'Keyword':<45} {'Match type':<16} Network")
    print("-" * 72)
    for k in items:
        print(f"{(k['name'] or '')[:44]:<45} {k['matchType']:<16} {k.get('network') or '-'}")
    print(f"\n{len(items)} campaign-level negatives.")


def cmd_negative_campaign_add(args: argparse.Namespace) -> None:
    """Append campaign-level negatives (existing ones stay)."""
    uid = getattr(args, "user_id", None)
    network = getattr(args, "network", None)
    items = _items(args)
    existing = _list(args.campaign_id, uid)
    if network:
        # Exact duplicate = same text + match type IN THAT network.
        have = {_key(k) for k in existing if k.get("network") in (network, None)}
        partial: list[dict] = []
    else:
        # Target network unknown (server default by campaign type): treat anything already
        # present in some network as present, but say when it is only in one of them.
        have = {_key(k) for k in existing}
        nets: dict[tuple[str, str], set] = {}
        for k in existing:
            nets.setdefault(_key(k), set()).add(k.get("network"))
        # Only worth a note where the campaign evidently uses BOTH networks: a
        # campaign of one type accepts only its own network (live 2026-11-22: a
        # context campaign answers fulltext with 403 network_not_allowed_for_campaign_type).
        campaign_nets = {k.get("network") for k in existing if k.get("network")}
        partial = [{**i, "onlyIn": sorted(n for n in nets[_key(i)] if n)} for i in items
                   if len(campaign_nets) > 1 and _key(i) in nets
                   and len({n for n in nets[_key(i)] if n}) == 1]
    new = [i for i in items if _key(i) not in have]
    skipped = [i for i in items if i not in new]
    if new:
        fenix.call("POST", _path(args.campaign_id), None, _body(new, network))
    if args.json:
        out: dict = {"campaignId": args.campaign_id, "network": network,
                     "added": new, "alreadyPresent": skipped}
        if partial:
            out["presentInOneNetworkOnly"] = partial
        _output_json(out)
        return
    print(f"Added {len(new)} campaign-level negatives to campaign {args.campaign_id}"
          + (f" (network {network})" if network else "")
          + (f"; {len(skipped)} already present" if skipped else "") + ".")
    if partial:
        print("NOTE: skipped as present, but only in one network — re-run with --network "
              "to add them to the other one: "
              + ", ".join(f"{p['name']} [{'/'.join(p['onlyIn'])}]" for p in partial),
              file=sys.stderr)


def cmd_negative_campaign_remove(args: argparse.Namespace) -> None:
    """Remove given campaign-level negatives; reports the ones that were not there."""
    if not args.confirm:
        _fail_msg("Requires --confirm flag.")
    uid = getattr(args, "user_id", None)
    network = getattr(args, "network", None)
    items = _items(args)
    have = {_key(k) for k in _list(args.campaign_id, uid)
            if not network or k.get("network") in (network, None)}
    found = [i for i in items if _key(i) in have]
    missing = [i for i in items if i not in found]
    if not found:
        _fail_msg(f"None of the given negatives are on campaign {args.campaign_id}"
                  + (f" in network {network}" if network else "") + " — nothing removed.",
                  notFound=missing)
    fenix.call("POST", _path(args.campaign_id) + "delete", None, _body(found, network))
    if args.json:
        _output_json({"campaignId": args.campaign_id, "network": network or "both",
                      "removed": found, "notFound": missing})
        return
    print(f"Removed {len(found)} campaign-level negatives from campaign {args.campaign_id}"
          + (f" (network {network})" if network else " (both networks)")
          + (f"; not found: {', '.join(i['name'] for i in missing)}" if missing else "") + ".")
