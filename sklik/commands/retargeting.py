"""Retargeting (audience list) commands."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from sklik.api import (_api_call, _fail, _fail_msg, _fetch_all,
                       _is_sem_blocked, _list_page_size)
from sklik.formatting import (
    _czk_to_halere, _halere_to_czk, _format_money,
    _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, STAT_COLUMNS



# ---------------------------------------------------------------------------
# Commands — Retargeting (audience lists for remarketing)
# ---------------------------------------------------------------------------
# A retargeting list defines an audience based on site-visit behaviour (URL
# conditions). Used to target/exclude past visitors in context campaigns.
# Note: list objects use `listId` (not `id`); the create payload nests the
# editable fields under `attributes`.

def cmd_retargeting(args: argparse.Namespace) -> None:
    """List retargeting (audience) lists."""
    # retargeting.lists.list takes only the user struct.
    data = _api_call("retargeting.lists.list", [], getattr(args, "user_id", None))
    lists = data.get("lists", [])

    if args.json:
        out = [{
            "listId": lst.get("listId"),
            "name": lst.get("name"),
            "status": lst.get("status"),
            "deleted": lst.get("deleted"),
        } for lst in lists]
        _output_json(out)
    else:
        if not lists:
            print("No retargeting lists found.")
            return
        print(f"{'List ID':<12} {'Name':<40} {'Status'}")
        print("-" * 65)
        for lst in lists:
            print(f"{lst.get('listId', ''):<12} {lst.get('name', ''):<40} {lst.get('status', '')}")


def cmd_retargeting_create(args: argparse.Namespace) -> None:
    """Create a retargeting list."""
    if args.conditions_json and args.take_all_users:
        print("ERROR: --take-all-users cannot be combined with --conditions-json "
              "(a take-all-users list has no URL conditions).", file=sys.stderr)
        sys.exit(1)

    attributes: dict = {
        "name": args.name,
        "membership": args.membership,
        "useHistoricData": args.use_historic,
        # If explicit URL conditions are given, the list is condition-based,
        # otherwise it captures all visitors of the retargeting code.
        "takeAllUsers": args.take_all_users if args.take_all_users is not None
        else (args.conditions_json is None),
    }
    if args.description:
        attributes["description"] = args.description

    lst: dict = {"attributes": attributes}
    if args.conditions_json:
        try:
            lst["conditionGroups"] = json.loads(args.conditions_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid --conditions-json: {e}", file=sys.stderr)
            sys.exit(1)

    data = _api_call("retargeting.lists.create", [[lst]], getattr(args, "user_id", None))
    ids = data.get("listIds", [])

    if args.json:
        _output_json({"listIds": ids})
    else:
        print(f"Retargeting list created: ID {ids[0] if ids else '?'}")


def cmd_retargeting_update(args: argparse.Namespace) -> None:
    """Update a retargeting list (name / membership / description)."""
    attributes: dict = {}
    if args.name:
        attributes["name"] = args.name
    if args.membership is not None:
        attributes["membership"] = args.membership
    if args.description is not None:
        attributes["description"] = args.description

    if not attributes:
        print("ERROR: No fields to update. Use --name, --membership, or --description.", file=sys.stderr)
        sys.exit(1)

    _api_call("retargeting.lists.update", [[{
        "listId": args.list_id,
        "attributes": attributes,
    }]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "listId": args.list_id})
    else:
        print(f"Retargeting list {args.list_id} updated.")


def cmd_retargeting_remove(args: argparse.Namespace) -> None:
    """Remove a retargeting list."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("retargeting.lists.remove", [[args.list_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "listId": args.list_id})
    else:
        print(f"Retargeting list {args.list_id} removed.")


# ---------------------------------------------------------------------------
# Commands — Attaching audiences to ad groups (retargeting.group.lists.*)
# ---------------------------------------------------------------------------
# The attachment lives in its own namespace, not on the group object:
# add/remove take [{listId, groupId}, …]; list takes a plain array of group IDs.

def cmd_retargeting_attach(args: argparse.Namespace) -> None:
    """Attach a retargeting (audience) list to an ad group as targeting."""
    data = _api_call("retargeting.group.lists.add", [[{
        "listId": args.list_id,
        "groupId": args.group_id,
    }]], getattr(args, "user_id", None))

    if args.json:
        _output_json({"attached": True, "listId": args.list_id,
                      "groupId": args.group_id, "count": data.get("count")})
    else:
        print(f"Retargeting list {args.list_id} attached to group {args.group_id}.")


def cmd_retargeting_detach(args: argparse.Namespace) -> None:
    """Detach a retargeting list from an ad group."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    data = _api_call("retargeting.group.lists.remove", [[{
        "listId": args.list_id,
        "groupId": args.group_id,
    }]], getattr(args, "user_id", None))

    if args.json:
        _output_json({"detached": True, "listId": args.list_id,
                      "groupId": args.group_id, "count": data.get("count")})
    else:
        print(f"Retargeting list {args.list_id} detached from group {args.group_id}.")


def cmd_retargeting_exclude(args: argparse.Namespace) -> None:
    """Exclude an audience from a campaign or group (negative retargeting).

    Typical use: exclude existing customers from an acquisition display
    campaign. Works at campaign OR group level (retargeting.*.negative.add).
    """
    if bool(args.campaign_id) == bool(args.group_id):
        print("ERROR: Use exactly one of --campaign-id or --group-id.", file=sys.stderr)
        sys.exit(1)

    uid = getattr(args, "user_id", None)
    if args.campaign_id:
        _api_call("retargeting.campaign.negative.add", [[{
            "entityId": args.list_id, "campaignId": args.campaign_id,
        }]], uid)
        target = f"campaign {args.campaign_id}"
    else:
        _api_call("retargeting.group.negative.add", [[{
            "entityId": args.list_id, "groupId": args.group_id,
        }]], uid)
        target = f"group {args.group_id}"

    if args.json:
        _output_json({"excluded": True, "listId": args.list_id,
                      "campaignId": args.campaign_id, "groupId": args.group_id})
    else:
        print(f"Audience {args.list_id} excluded from {target}.")


def cmd_retargeting_exclude_remove(args: argparse.Namespace) -> None:
    """Stop excluding an audience from a campaign or group."""
    if bool(args.campaign_id) == bool(args.group_id):
        print("ERROR: Use exactly one of --campaign-id or --group-id.", file=sys.stderr)
        sys.exit(1)
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    uid = getattr(args, "user_id", None)
    if args.campaign_id:
        _api_call("retargeting.campaign.negative.remove", [[{
            "entityId": args.list_id, "campaignId": args.campaign_id,
        }]], uid)
        target = f"campaign {args.campaign_id}"
    else:
        _api_call("retargeting.group.negative.remove", [[{
            "entityId": args.list_id, "groupId": args.group_id,
        }]], uid)
        target = f"group {args.group_id}"

    if args.json:
        _output_json({"exclusionRemoved": True, "listId": args.list_id,
                      "campaignId": args.campaign_id, "groupId": args.group_id})
    else:
        print(f"Audience {args.list_id} no longer excluded from {target}.")


def cmd_retargeting_excluded(args: argparse.Namespace) -> None:
    """List excluded audiences (campaign- and group-level negative retargeting)."""
    from sklik.reports import _fetch_listing_report

    uid = getattr(args, "user_id", None)
    rows = []

    def _collect(entity: str, level: str, parent_key: str) -> None:
        report = _fetch_listing_report(
            entity, {"isDeleted": False},
            ["id", "name", f"{parent_key}.id", f"{parent_key}.name"], user_id=uid)
        for r in report:
            parent = r.get(parent_key, {}) if isinstance(r.get(parent_key), dict) else {}
            rows.append({
                "entityId": r.get("id"),
                "name": r.get("name"),
                "level": level,
                "campaignId": parent.get("id") if level == "campaign" else None,
                "groupId": parent.get("id") if level == "group" else None,
                "parentName": parent.get("name"),
            })

    if not args.group_id:
        _collect("retargeting.campaign.negative", "campaign", "campaign")
    if not args.campaign_id:
        _collect("retargeting.group.negative", "group", "group")

    if args.campaign_id:
        rows = [r for r in rows if r["campaignId"] == args.campaign_id]
    if args.group_id:
        rows = [r for r in rows if r["groupId"] == args.group_id]

    if args.json:
        _output_json(rows)
    else:
        if not rows:
            print("No excluded audiences.")
            return
        print(f"{'Entity ID':<12} {'Audience':<35} {'Level':<10} {'Campaign/Group'}")
        print("-" * 85)
        for r in rows:
            print(f"{r['entityId'] or '':<12} {(r['name'] or ''):<35} "
                  f"{r['level']:<10} {r['parentName'] or ''}")


def _group_ids(group_id: int | None, uid: int | None) -> list[int]:
    """[group_id] if given, otherwise every non-deleted group of the account."""
    if group_id:
        return [group_id]
    return [g["id"] for g in _fetch_all("groups.list", {"isDeleted": False},
                                        ["id"], "groups", uid)]


def _list_by_groups(method: str, key: str, gids: list[int], uid: int | None) -> list[dict]:
    """Call a `retargeting.group.*.list` method in chunks (one big array hits 413)."""
    chunk = _list_page_size(uid)
    rows: list[dict] = []
    for i in range(0, len(gids), chunk):
        data = _api_call(method, [gids[i:i + chunk]], uid)
        rows.extend(r for r in data.get(key, []) if not r.get("deleted"))
    return rows


def cmd_retargeting_attached(args: argparse.Namespace) -> None:
    """List audience lists attached to a group (or to all groups)."""
    uid = getattr(args, "user_id", None)
    rows = _list_by_groups("retargeting.group.lists.list", "lists",
                           _group_ids(args.group_id, uid), uid)

    if args.json:
        _output_json([{
            "listId": r.get("listId"),
            "groupId": r.get("groupId"),
            "name": r.get("name"),
            "status": r.get("status"),
        } for r in rows])
    else:
        if not rows:
            print("No audiences attached.")
            return
        print(f"{'List ID':<12} {'Group ID':<12} {'Name':<40} {'Status'}")
        print("-" * 78)
        for r in rows:
            print(f"{r.get('listId', ''):<12} {r.get('groupId', ''):<12} "
                  f"{r.get('name', ''):<40} {r.get('status', '')}")


# ---------------------------------------------------------------------------
# Commands — Combinations (retargeting.combinations.* / retargeting.group.combinations.*)
# ---------------------------------------------------------------------------
# A combination joins existing lists with set logic: each `listGroup` has an
# operator (and = in every list of the group, or = in at least one, not = in none)
# and the groups are ANDed together. A combination made only of `not` groups is
# rejected (retargeting_combination_list_groups_only_not). Combinations are NOT
# returned by retargeting.lists.list — they live in their own namespace — and
# they attach to groups via retargeting.group.combinations.*. Excluding one works
# through the existing negative retargeting (entityId = combination ID).

_COMBINATION_OPERATORS = ("and", "or", "not")


def _parse_id_csv(value: str, flag: str) -> list[int]:
    try:
        ids = [int(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError:
        _fail_msg(f"{flag} must be comma-separated list IDs, got '{value}'.")
    if not ids:
        _fail_msg(f"{flag} is empty.")
    return ids


def _combination_groups(args: argparse.Namespace) -> list[dict]:
    """listGroups from --and/--or/--not (each occurrence = one group) or --groups-json."""
    groups: list[dict] = []
    for op in _COMBINATION_OPERATORS:
        for value in getattr(args, f"op_{op}") or []:
            groups.append({"operator": op, "listIds": _parse_id_csv(value, f"--{op}")})
    if args.groups_json:
        if groups:
            _fail_msg("Use either --and/--or/--not or --groups-json, not both.")
        try:
            groups = json.loads(args.groups_json)
        except json.JSONDecodeError as e:
            _fail_msg(f"Invalid --groups-json: {e}")
        for g in groups:
            if g.get("operator") not in _COMBINATION_OPERATORS:
                _fail_msg(f"Each group needs operator and/or/not, got {g.get('operator')!r}.")
    if not groups:
        _fail_msg("Give at least one list group: --or 1,2 / --and 3 / --not 4 (or --groups-json).")
    if all(g["operator"] == "not" for g in groups):
        _fail_msg("A combination of only --not groups is rejected by Sklik; add an --and/--or group.")
    return groups


def cmd_retargeting_combinations(args: argparse.Namespace) -> None:
    """List retargeting combinations; --detail adds list groups and user counts."""
    uid = getattr(args, "user_id", None)
    data = _api_call("retargeting.combinations.list", [], uid)
    combos = [c for c in data.get("combinations", []) if args.include_deleted or not c.get("deleted")]

    rows = [{
        "combinationId": c.get("combinationId"),
        "name": c.get("name"),
        "status": c.get("status"),
        "deleted": c.get("deleted"),
    } for c in combos]

    if args.detail and rows:
        details: dict = {}
        ids = [r["combinationId"] for r in rows]
        for i in range(0, len(ids), 100):
            got = _api_call("retargeting.combinations.get", [ids[i:i + 100]], uid)
            for c in got.get("combinations", []):
                details[c.get("combinationId")] = c
        for r in rows:
            d = details.get(r["combinationId"], {})
            r["users"] = (d.get("attributes") or {}).get("users")
            r["listGroups"] = [{"operator": g.get("operator"), "listIds": g.get("listIds", [])}
                               for g in d.get("listGroups", [])]

    if args.json:
        _output_json(rows)
        return
    if not rows:
        print("No retargeting combinations found.")
        return
    print(f"{'Comb. ID':<12} {'Name':<40} {'Status':<8}" + (f" {'Users':>9}  Groups" if args.detail else ""))
    print("-" * (62 + (40 if args.detail else 0)))
    for r in rows:
        line = f"{r['combinationId'] or '':<12} {(r['name'] or ''):<40} {(r['status'] or ''):<8}"
        if args.detail:
            groups = " AND ".join(f"{g['operator']}({','.join(map(str, g['listIds']))})"
                                  for g in r.get("listGroups", []))
            line += f" {r.get('users') if r.get('users') is not None else '?':>9}  {groups}"
        print(line)


def cmd_retargeting_combination_create(args: argparse.Namespace) -> None:
    """Create a retargeting combination from existing lists."""
    attributes: dict = {"name": args.name}
    if args.description:
        attributes["description"] = args.description
    combo = {"attributes": attributes, "listGroups": _combination_groups(args)}

    data = _api_call("retargeting.combinations.create", [[combo]], getattr(args, "user_id", None))
    ids = data.get("combinationIds", [])
    if args.json:
        _output_json({"combinationIds": ids, "listGroups": combo["listGroups"]})
    else:
        print(f"Retargeting combination created: ID {ids[0] if ids else '?'}")


def cmd_retargeting_combination_update(args: argparse.Namespace) -> None:
    """Rename / re-describe / pause / resume a combination (list groups are left as they are)."""
    attributes: dict = {}
    if args.name:
        attributes["name"] = args.name
    if args.description is not None:
        attributes["description"] = args.description
    if args.status:
        attributes["status"] = args.status
    if not attributes:
        _fail_msg("No fields to update. Use --name, --description or --status.")

    _api_call("retargeting.combinations.update", [[{
        "combinationId": args.combination_id, "attributes": attributes,
    }]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "combinationId": args.combination_id})
    else:
        print(f"Retargeting combination {args.combination_id} updated.")


def cmd_retargeting_combination_remove(args: argparse.Namespace) -> None:
    """Remove a retargeting combination."""
    if not args.confirm:
        _fail_msg("Requires --confirm flag.")
    _api_call("retargeting.combinations.remove", [[args.combination_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "combinationId": args.combination_id})
    else:
        print(f"Retargeting combination {args.combination_id} removed.")


def cmd_retargeting_combination_attach(args: argparse.Namespace) -> None:
    """Attach a combination to an ad group as targeting."""
    data = _api_call("retargeting.group.combinations.add", [[{
        "combinationId": args.combination_id, "groupId": args.group_id,
    }]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"attached": True, "combinationId": args.combination_id,
                      "groupId": args.group_id, "count": data.get("count")})
    else:
        print(f"Retargeting combination {args.combination_id} attached to group {args.group_id}.")


def cmd_retargeting_combination_detach(args: argparse.Namespace) -> None:
    """Detach a combination from an ad group."""
    if not args.confirm:
        _fail_msg("Requires --confirm flag.")
    data = _api_call("retargeting.group.combinations.remove", [[{
        "combinationId": args.combination_id, "groupId": args.group_id,
    }]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"detached": True, "combinationId": args.combination_id,
                      "groupId": args.group_id, "count": data.get("count")})
    else:
        print(f"Retargeting combination {args.combination_id} detached from group {args.group_id}.")


def cmd_retargeting_combinations_attached(args: argparse.Namespace) -> None:
    """List combinations attached to a group (or to all groups)."""
    uid = getattr(args, "user_id", None)
    attached = _list_by_groups("retargeting.group.combinations.list", "combinations",
                               _group_ids(args.group_id, uid), uid)
    rows = [{
        "combinationId": r.get("combinationId"),
        "groupId": r.get("groupId"),
        "name": r.get("name"),
        "status": r.get("status"),
    } for r in attached]

    if args.json:
        _output_json(rows)
        return
    if not rows:
        print("No combinations attached.")
        return
    print(f"{'Comb. ID':<12} {'Group ID':<12} {'Name':<40} {'Status'}")
    print("-" * 78)
    for r in rows:
        print(f"{r['combinationId'] or '':<12} {r['groupId'] or '':<12} "
              f"{(r['name'] or ''):<40} {r['status'] or ''}")
