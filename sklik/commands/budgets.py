"""Shared budget commands (sharedbudgets.*).

A shared budget pools the daily spend limit of several campaigns. Campaign
assignment is managed HERE (addCids/removeCids on the budget), not via
campaigns.update.

QUIRK: unlike the rest of the API, sharedbudgets amounts are in plain CZK
(create takes int Kč, list returns double Kč) — no haléře conversion.
"""
from __future__ import annotations

import argparse
import sys

from sklik.api import _api_call
from sklik.formatting import _output_json


def _parse_ids(csv: str | None) -> list[int]:
    return [int(x) for x in csv.split(",") if x.strip()] if csv else []


def cmd_budgets(args: argparse.Namespace) -> None:
    """List shared budgets with their assigned campaigns."""
    data = _api_call("sharedbudgets.list", [], getattr(args, "user_id", None))
    budgets = data.get("budgets", [])

    rows = [{
        "id": b.get("id"),
        "name": b.get("name"),
        "dayBudget": b.get("dayBudget"),
        "exhaustedMoney": b.get("exhaustedMoney"),
        "campaigns": [{"id": c.get("id"), "name": c.get("name")}
                      for c in b.get("campaigns", []) if not c.get("deleted")],
    } for b in budgets]

    if args.json:
        _output_json(rows)
    else:
        if not rows:
            print("No shared budgets found.")
            return
        for b in rows:
            camps = ", ".join(c["name"] or str(c["id"]) for c in b["campaigns"]) or "—"
            print(f"[{b['id']}] {b['name']}: {b['dayBudget']} Kč/den "
                  f"(vyčerpáno {b['exhaustedMoney']} Kč) — kampaně: {camps}")


def cmd_budget_create(args: argparse.Namespace) -> None:
    """Create a shared budget, optionally assigning campaigns right away."""
    attributes: dict = {
        "name": args.name,
        "dayBudget": int(round(args.day_budget)),  # plain Kč (sharedbudgets quirk)
    }
    cids = _parse_ids(args.campaign_ids)
    if cids:
        attributes["addCids"] = cids

    data = _api_call("sharedbudgets.create", [[{"attributes": attributes}]],
                     getattr(args, "user_id", None))
    ids = data.get("ids", [])

    if args.json:
        _output_json({"budgetIds": ids})
    else:
        print(f"Shared budget created: ID {ids[0] if ids else '?'}")


def cmd_budget_update(args: argparse.Namespace) -> None:
    """Update a shared budget (name, amount, campaign assignment)."""
    attributes: dict = {}
    if args.name:
        attributes["name"] = args.name
    if args.day_budget is not None:
        attributes["dayBudget"] = int(round(args.day_budget))
    if args.remove_all_campaigns:
        if args.add_campaign_ids or args.remove_campaign_ids:
            print("ERROR: --remove-all-campaigns cannot be combined with "
                  "--add-campaign-ids/--remove-campaign-ids.", file=sys.stderr)
            sys.exit(1)
        attributes["removeAllCids"] = True
    else:
        add_ids = _parse_ids(args.add_campaign_ids)
        rem_ids = _parse_ids(args.remove_campaign_ids)
        if add_ids:
            attributes["addCids"] = add_ids
        if rem_ids:
            attributes["removeCids"] = rem_ids

    if not attributes:
        print("ERROR: No fields to update. Use --name, --day-budget, "
              "--add-campaign-ids, --remove-campaign-ids, or --remove-all-campaigns.",
              file=sys.stderr)
        sys.exit(1)

    _api_call("sharedbudgets.update", [[{
        "id": args.budget_id,
        "attributes": attributes,
    }]], getattr(args, "user_id", None))

    if args.json:
        _output_json({"updated": True, "budgetId": args.budget_id})
    else:
        print(f"Shared budget {args.budget_id} updated.")


def cmd_budget_remove(args: argparse.Namespace) -> None:
    """Remove a shared budget."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("sharedbudgets.remove", [[args.budget_id]],
              getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "budgetId": args.budget_id})
    else:
        print(f"Shared budget {args.budget_id} removed.")
