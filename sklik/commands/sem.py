"""SEM (Seznam Event Measurement) commands — via the Fénix REST API (`sklik/fenix.py`).

DRAK blocks `conversions.*` on accounts with SEM activated; Fénix is the only API that
reads and writes SEM conversions. Each conversion is built on one SEM event
(Purchase, AddToCart, …) and may carry condition groups on the event's dimensions
(value, url, content_category, item_id, …). Creating a conversion ALSO creates a
"Seznam z konverze" retargeting list — that is how event/value audiences such as
"purchase over 1 500 Kč" are made, which DRAK's URL-only lists cannot express.

Same engine and token as the other Fénix commands (`SKLIK_FENIX_REFRESH_TOKEN`, no
`premiseId`). Written against the OpenAPI spec (read at 1.36.4, 2026-11-06): GET lists
with offset paging (`fetch_all_offset`), POST/PATCH take `dryRun=true` for a server-side
validation that persists nothing.

Caveat: a conversion counts in Sklik conversion reports. A conditional conversion on
an event already measured by another conversion (e.g. high-value Purchase next to the
main Purchase) counts the same order twice in "Konverze". The convention to follow:
name it "… (vedlejší)", value 0, and never use it as a bidding goal.
"""
from __future__ import annotations

import argparse
import json

from sklik import fenix
from sklik.api import _fail_msg
from sklik.formatting import _output_json

_CONVERSIONS = "/sklik/event-measurement/conversions/"

SEM_EVENTS = ["Search", "ViewContent", "AddToWishlist", "AddToCart", "InitiateCheckout",
              "AddPaymentInfo", "CompleteRegistration", "Contact", "CustomizeProduct", "Donate",
              "FindLocation", "Lead", "Purchase", "Schedule", "StartTrial", "SubmitApplication",
              "Subscribe", "PageView"]
CONDITION_KEYS = ["url", "user_ge", "user_ct", "event_source", "value", "content_type",
                  "content_name", "content_category", "item_id", "user_region"]
CONDITION_TYPES = ["contains", "not_contains", "equals", "not_equals", "starts", "not_starts",
                   "ends", "not_ends", "less_than", "greater_than"]
_CONVERSION_ATTRS = ("id", "name", "description", "value", "semEventName", "isDeleted",
                     "conditionGroups")


def _parse_condition(spec: str) -> dict:
    """KEY:TYPE:VALUE → condition. For key `value` the amount is given in CZK and sent
    in haléře (the API expects hellers there)."""
    parts = spec.split(":", 2)
    if len(parts) != 3:
        _fail_msg(f"--condition must be KEY:TYPE:VALUE, got '{spec}'.")
    key, ctype, value = (p.strip() for p in parts)
    if key not in CONDITION_KEYS:
        _fail_msg(f"Unknown condition key '{key}'. Allowed: {', '.join(CONDITION_KEYS)}.")
    if ctype not in CONDITION_TYPES:
        _fail_msg(f"Unknown condition type '{ctype}'. Allowed: {', '.join(CONDITION_TYPES)}.")
    if not value:
        _fail_msg(f"--condition '{spec}' has an empty value.")
    if key == "value":
        try:
            value = str(round(float(value.replace(",", ".")) * 100))
        except ValueError:
            _fail_msg(f"Condition on `value` needs an amount in CZK, got '{value}'.")
    return {"key": key, "type": ctype, "value": value}


def _condition_groups(args: argparse.Namespace) -> list | None:
    if args.conditions_json:
        if args.condition:
            _fail_msg("Use either --condition or --conditions-json, not both.")
        try:
            return json.loads(args.conditions_json)
        except json.JSONDecodeError as e:
            _fail_msg(f"Invalid --conditions-json: {e}")
    if args.condition:
        # All --condition flags go into ONE group. The spec describes the conditions of
        # a group only as "combined within the group" without saying AND or OR; with
        # several conditions verify the resulting audience size before relying on it.
        return [{"conditions": [_parse_condition(c) for c in args.condition]}]
    return None


def _fmt_conditions(groups: list | None) -> str:
    if not groups:
        return "—"
    out = []
    for g in groups:
        parts = []
        for c in g.get("conditions", []):
            val = c.get("value")
            if c.get("key") == "value":
                try:
                    val = f"{int(val) / 100:g} Kč"
                except (TypeError, ValueError):
                    pass
            parts.append(f"{c.get('key')} {c.get('type')} {val}")
        out.append("(" + " · ".join(parts) + ")")
    return " AND ".join(out)


def cmd_sem_status(args: argparse.Namespace) -> None:
    """Is SEM activated on the account?"""
    body = fenix.call("GET", "/sklik/event-measurement/activate/")
    if args.json:
        _output_json(body)
    else:
        if body.get("semActivated"):
            print(f"SEM activated since {body.get('semActivatedTimestamp')}.")
        else:
            print("SEM is NOT activated on this account.")


def cmd_sem_conversions(args: argparse.Namespace) -> None:
    """List SEM conversions with their event and conditions."""
    params: dict = {"a": list(_CONVERSION_ATTRS), "order": "id:ASC"}
    if not args.include_deleted:
        params["isDeleted"] = "false"
    items = fenix.fetch_all_offset(_CONVERSIONS, params)
    if args.json:
        _output_json(items)
        return
    if not items:
        print("No SEM conversions.")
        return
    print(f"{'ID':<11} {'Name':<38} {'Event':<20} {'Value':>7}  Conditions")
    print("-" * 110)
    for c in items:
        value = "—" if c.get("value") is None else f"{c['value']} Kč"
        print(f"{c.get('id', ''):<11} {(c.get('name') or '')[:37]:<38} {c.get('semEventName') or '':<20} "
              f"{value:>7}  {_fmt_conditions(c.get('conditionGroups'))}"
              + ("  [deleted]" if c.get("isDeleted") else ""))


def cmd_sem_conversion_create(args: argparse.Namespace) -> None:
    """Create a SEM conversion (and with it a retargeting list). --dry-run only validates."""
    body: dict = {"name": args.name, "semEventName": args.event, "value": args.value}
    if args.description:
        body["description"] = args.description
    groups = _condition_groups(args)
    if groups:
        body["conditionGroups"] = groups

    resp = fenix.call("POST", _CONVERSIONS, {"dryRun": "true"} if args.dry_run else None, body)
    out = {"dryRun": args.dry_run, "request": body}
    if not args.dry_run:
        out["conversionIds"] = (resp or {}).get("conversionIds", [])
        out["retargetingListIds"] = (resp or {}).get("retargetingListIds", [])
    if args.json:
        _output_json(out)
        return
    if args.dry_run:
        print(f"Dry run OK — '{args.name}' on {args.event}, value {args.value} Kč, "
              f"conditions {_fmt_conditions(groups)}. Nothing was created.")
        return
    print(f"SEM conversion created: ID {out['conversionIds'][0] if out['conversionIds'] else '?'}")
    if out["retargetingListIds"]:
        # The spec says the list ids are not positionally aligned with the conversion ids.
        print(f"Retargeting list created with it: ID {out['retargetingListIds'][0]}")
    else:
        print("WARNING: no retargeting list ID returned — Sklik may have failed to create it; "
              "check the SEM → Retargeting tab.")


def cmd_sem_conversion_update(args: argparse.Namespace) -> None:
    """Update a SEM conversion's name / description / value / conditions."""
    body: dict = {}
    if args.name:
        body["name"] = args.name
    if args.description is not None:
        body["description"] = args.description
    if args.value is not None:
        body["value"] = args.value
    groups = _condition_groups(args)
    if groups is not None:
        body["conditionGroups"] = groups
    if not body:
        _fail_msg("No fields to update. Use --name, --description, --value or --condition.")
    fenix.call("PATCH", f"{_CONVERSIONS}{args.conversion_id}/",
               {"dryRun": "true"} if args.dry_run else None, body)
    if args.json:
        _output_json({"updated": not args.dry_run, "dryRun": args.dry_run,
                      "conversionId": args.conversion_id, "request": body})
    else:
        print(("Dry run OK — nothing changed" if args.dry_run else "Updated")
              + f": SEM conversion {args.conversion_id}.")


def cmd_sem_conversion_remove(args: argparse.Namespace) -> None:
    """Remove (soft-delete) a SEM conversion; --restore brings it back."""
    if not args.confirm and not args.restore:
        _fail_msg("Requires --confirm flag.")
    fenix.call("PATCH", f"{_CONVERSIONS}{args.conversion_id}/",
               None, {"deleted": not args.restore})
    verb = "restored" if args.restore else "removed"
    if args.json:
        _output_json({verb: True, "conversionId": args.conversion_id})
    else:
        print(f"SEM conversion {args.conversion_id} {verb}.")
