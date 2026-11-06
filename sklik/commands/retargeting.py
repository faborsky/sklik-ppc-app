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
# Commands — E-mail audiences (retargeting.emails.* / retargeting.email.*)
# ---------------------------------------------------------------------------
# An e-mail list is created empty, then filled with addresses. Unlike URL lists:
#   - create/update take flat items ({name, description} / {retargetingListId, …}),
#     not the {attributes: …} wrapper;
#   - addEmail / removeEmail / removeAll take ONE struct {retargetingListId, emails, …},
#     not an array of items;
#   - the account must have accepted the e-mail retargeting terms in the web UI,
#     otherwise writes fail with email_retargeting_terms_and_conditions_not_granted
#     (check with retargeting.email.contractCondition.check).
# The API docs neither say whether addresses must be hashed nor give a per-call cap,
# so addresses are sent normalised (trimmed, lower-cased, de-duplicated) in chunks.
# Addresses are personal data: they are never echoed back, only counted.

_EMAIL_CHUNK = 1000


def _read_emails(args: argparse.Namespace) -> tuple[list[str], int]:
    """Addresses from --emails and/or --file (one per line; for CSV the first column).
    Returns (valid unique normalised addresses, number of rejected entries)."""
    raw: list[str] = []
    if args.emails:
        raw.extend(args.emails.split(","))
    if args.file:
        try:
            with open(args.file, encoding="utf-8-sig") as fh:
                for line in fh:
                    raw.append(line.replace(";", ",").split(",")[0])
        except OSError as e:
            _fail_msg(f"Cannot read --file: {e}")
    if not raw:
        _fail_msg("Give addresses with --emails a@b.cz,c@d.cz and/or --file path.")

    seen: set[str] = set()
    valid: list[str] = []
    rejected = 0
    for item in raw:
        addr = item.strip().strip('"').lower()
        if not addr:
            continue
        if "@" not in addr or "." not in addr.split("@")[-1] or " " in addr:
            rejected += 1  # header row, stray values, typos
            continue
        if addr not in seen:
            seen.add(addr)
            valid.append(addr)
    if not valid:
        _fail_msg(f"No valid e-mail addresses found ({rejected} rejected).")
    return valid, rejected


def _email_terms_accepted(uid: int | None) -> bool | None:
    data = _api_call("retargeting.email.contractCondition.check", [], uid)
    return data.get("contractAccepted")


def _require_email_terms(uid: int | None) -> None:
    if _email_terms_accepted(uid) is False:
        _fail_msg("E-mail retargeting terms are not accepted on this account. Accept them in the "
                  "Sklik web UI (Nástroje → Retargeting → e-mailové seznamy) and retry.")


def cmd_retargeting_email_terms(args: argparse.Namespace) -> None:
    """Has the account accepted the e-mail retargeting terms?"""
    accepted = _email_terms_accepted(getattr(args, "user_id", None))
    if args.json:
        _output_json({"contractAccepted": accepted})
    else:
        print("E-mail retargeting terms: " + ("accepted" if accepted else "NOT accepted — accept them "
                                              "in the Sklik web UI before creating e-mail lists"))


def cmd_retargeting_emails(args: argparse.Namespace) -> None:
    """List e-mail audiences; --detail adds membership and user counts."""
    uid = getattr(args, "user_id", None)
    data = _api_call("retargeting.emails.list", [], uid)
    lists = [e for e in data.get("emails", []) if args.include_deleted or not e.get("deleted")]
    rows = [{"listId": e.get("emailId"), "name": e.get("name"),
             "status": e.get("status"), "deleted": e.get("deleted")} for e in lists]

    if args.detail and rows:
        got = _api_call("retargeting.emails.get", [[r["listId"] for r in rows]], uid)
        by_id = {e.get("emailId"): (e.get("attributes") or {}) for e in got.get("emails", [])}
        for r in rows:
            a = by_id.get(r["listId"], {})
            r["users"] = a.get("users")
            r["membership"] = a.get("membership")

    if args.json:
        _output_json(rows)
        return
    if not rows:
        print("No e-mail audiences found.")
        return
    print(f"{'List ID':<12} {'Name':<40} {'Status':<8}" + (f" {'Users':>9} {'Days':>5}" if args.detail else ""))
    print("-" * (62 + (16 if args.detail else 0)))
    for r in rows:
        line = f"{r['listId'] or '':<12} {(r['name'] or ''):<40} {(r['status'] or ''):<8}"
        if args.detail:
            line += f" {r.get('users') if r.get('users') is not None else '?':>9} {r.get('membership') or '':>5}"
        print(line)


def cmd_retargeting_email_create(args: argparse.Namespace) -> None:
    """Create an empty e-mail audience (fill it with retargeting-email-add)."""
    uid = getattr(args, "user_id", None)
    _require_email_terms(uid)
    item: dict = {"name": args.name}
    if args.description:
        item["description"] = args.description
    data = _api_call("retargeting.emails.create", [[item]], uid)
    ids = data.get("listIds", [])
    if args.json:
        _output_json({"listIds": ids})
    else:
        print(f"E-mail audience created: ID {ids[0] if ids else '?'} — add addresses with retargeting-email-add")


def cmd_retargeting_email_update(args: argparse.Namespace) -> None:
    """Rename / re-describe / pause / resume an e-mail audience."""
    item: dict = {"retargetingListId": args.list_id}
    if args.name:
        item["name"] = args.name
    if args.description is not None:
        item["description"] = args.description
    if args.status:
        item["status"] = args.status
    if len(item) == 1:
        _fail_msg("No fields to update. Use --name, --description or --status.")
    _api_call("retargeting.emails.update", [[item]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "listId": args.list_id})
    else:
        print(f"E-mail audience {args.list_id} updated.")


def _send_emails(method: str, args: argparse.Namespace) -> tuple[int, int]:
    uid = getattr(args, "user_id", None)
    _require_email_terms(uid)
    emails, rejected = _read_emails(args)
    for i in range(0, len(emails), _EMAIL_CHUNK):
        _api_call(method, [{"retargetingListId": args.list_id,
                            "emails": emails[i:i + _EMAIL_CHUNK]}], uid)
    return len(emails), rejected


def cmd_retargeting_email_add(args: argparse.Namespace) -> None:
    """Add addresses to an e-mail audience."""
    sent, rejected = _send_emails("retargeting.emails.addEmail", args)
    if args.json:
        _output_json({"listId": args.list_id, "sent": sent, "rejected": rejected})
    else:
        print(f"Sent {sent} unique addresses to e-mail audience {args.list_id}"
              + (f" ({rejected} invalid entries skipped)" if rejected else "")
              + ". Sklik matches them to users in the background; the user count updates later.")


def cmd_retargeting_email_remove_emails(args: argparse.Namespace) -> None:
    """Remove specific addresses from an e-mail audience."""
    if not args.confirm:
        _fail_msg("Requires --confirm flag.")
    sent, rejected = _send_emails("retargeting.emails.removeEmail", args)
    if args.json:
        _output_json({"listId": args.list_id, "removed": sent, "rejected": rejected})
    else:
        print(f"Requested removal of {sent} addresses from e-mail audience {args.list_id}.")


def cmd_retargeting_email_clear(args: argparse.Namespace) -> None:
    """Remove ALL addresses from an e-mail audience (the list itself stays)."""
    if not args.confirm:
        _fail_msg("Requires --confirm flag.")
    _api_call("retargeting.emails.removeAll", [{"retargetingListId": args.list_id}],
              getattr(args, "user_id", None))
    if args.json:
        _output_json({"cleared": True, "listId": args.list_id})
    else:
        print(f"All addresses removed from e-mail audience {args.list_id}.")


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


def cmd_retargeting_attached(args: argparse.Namespace) -> None:
    """List audience lists attached to a group (or to all groups)."""
    uid = getattr(args, "user_id", None)
    if args.group_id:
        gids = [args.group_id]
    else:
        gids = [g["id"] for g in _fetch_all("groups.list", {"isDeleted": False},
                                            ["id"], "groups", uid)]

    # The method takes the group IDs as one array — on a big account that array
    # would blow the per-call item cap (413), so ask in chunks.
    chunk = _list_page_size(uid)
    rows = []
    for i in range(0, len(gids), chunk):
        data = _api_call("retargeting.group.lists.list", [gids[i:i + chunk]], uid)
        rows.extend(r for r in data.get("lists", []) if not r.get("deleted"))

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
