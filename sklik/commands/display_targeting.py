"""Display-network targeting dimensions: interests, themes, intends (customer intents).

All three dimensions share the same shape in the DRAK API: a flat category
catalog (read-only), positive targeting entries attached to a GROUP (with
optional cpc/cpt override in haléře), and negative (exclusion) entries also
attached to a group. There is no .list — listing goes through the report API.

The CLI unifies them behind a required --type {interest,theme,intend} flag so
the command surface stays small.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

from sklik.api import _api_call
from sklik.formatting import _czk_to_halere, _halere_to_czk, _output_json
from sklik.reports import _fetch_report, _fetch_listing_report


_DIMENSIONS: dict[str, dict[str, str]] = {
    "interest": {
        "ns": "interests",
        "category_method": "interests.listCategories",
        "category_field": "interestCategoryId",
        "created_ids_field": "interestIds",
    },
    "theme": {
        "ns": "themes",
        "category_method": "themes.listCategories",
        "category_field": "categoryId",
        "created_ids_field": "themeIds",
    },
    "intend": {
        "ns": "intends",
        "category_method": "intends.getCategoryList",
        "category_field": "intendCategoryId",
        "created_ids_field": "intendIds",
    },
}


def _dim(args: argparse.Namespace) -> dict[str, str]:
    return _DIMENSIONS[args.type]


def _first_list_value(data: dict) -> list:
    """Pick the payload array out of a response regardless of its key name."""
    for key, value in data.items():
        if key in ("diagnostics",):
            continue
        if isinstance(value, list):
            return value
    return []


def cmd_targeting_categories(args: argparse.Namespace) -> None:
    """List the available categories for a display-targeting dimension."""
    dim = _dim(args)
    data = _api_call(dim["category_method"], [], getattr(args, "user_id", None))
    categories = _first_list_value(data)

    rows = []
    for c in categories:
        cat_id = c.get(dim["category_field"]) or c.get("categoryId") or c.get("id")
        rows.append({"categoryId": cat_id, "name": c.get("name")})

    if args.json:
        _output_json(rows)
    else:
        if not rows:
            print("No categories found.")
            return
        print(f"{'Category ID':<14} Name")
        print("-" * 60)
        for r in rows:
            print(f"{r['categoryId'] or '':<14} {r['name'] or ''}")


def _category_names(dim: dict, user_id: int | None) -> dict[int, str]:
    """categoryId → name map from the dimension's catalog (one extra call)."""
    data = _api_call(dim["category_method"], [], user_id)
    names: dict[int, str] = {}
    for c in _first_list_value(data):
        cat_id = c.get(dim["category_field"]) or c.get("categoryId") or c.get("id")
        if cat_id is not None:
            names[cat_id] = c.get("name")
    return names


def cmd_targeting(args: argparse.Namespace) -> None:
    """List targeting entries (or exclusions with --negative) of a dimension.

    The report returns categoryId only; the CLI joins the human-readable
    category name from the catalog. Negative reports take no dates.
    """
    dim = _dim(args)
    uid = getattr(args, "user_id", None)

    if args.negative:
        report = _fetch_listing_report(
            dim["ns"] + ".negative", {"isDeleted": False},
            ["id", "categoryId", "group.id", "group.name"], user_id=uid)
    else:
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        report = _fetch_report(
            dim["ns"], {"isDeleted": False}, date_from, date_to,
            ["id", "categoryId", "group.id", "group.name", "status", "cpc", "cpt"],
            user_id=uid)

    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    names = _category_names(dim, uid) if report else {}

    rows = []
    for r in report:
        cat_id = r.get("categoryId")
        rows.append({
            "id": r.get("id"),
            "categoryId": cat_id,
            "categoryName": names.get(cat_id),
            "groupId": r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id"),
            "groupName": r.get("group", {}).get("name") if isinstance(r.get("group"), dict) else r.get("group.name"),
            "status": r.get("status"),
            "cpc": _halere_to_czk(r.get("cpc")) if r.get("cpc") is not None else None,
            "cpt": _halere_to_czk(r.get("cpt")) if r.get("cpt") is not None else None,
        })

    if args.json:
        _output_json(rows)
    else:
        if not rows:
            print("No targeting entries found.")
            return
        label = "exclusion" if args.negative else "targeting"
        print(f"{args.type} {label} entries:")
        print(f"{'ID':<12} {'Category':<40} {'Status':<10} {'Group'}")
        print("-" * 85)
        for r in rows:
            cat = r["categoryName"] or str(r["categoryId"] or "")
            print(f"{r['id'] or '':<12} {cat:<40} "
                  f"{(r['status'] or ''):<10} {r['groupName'] or ''}")


def cmd_targeting_add(args: argparse.Namespace) -> None:
    """Add a positive targeting entry (category) to a display group."""
    dim = _dim(args)
    entry: dict = {
        "groupId": args.group_id,
        dim["category_field"]: args.category_id,
    }
    if args.cpc is not None:
        entry["cpc"] = _czk_to_halere(args.cpc)
    if args.cpt is not None:
        entry["cpt"] = _czk_to_halere(args.cpt)
    if args.status:
        entry["status"] = args.status

    data = _api_call(dim["ns"] + ".create", [[entry]], getattr(args, "user_id", None))
    ids = data.get(dim["created_ids_field"]) or _first_list_value(data)

    if args.json:
        _output_json({"ids": ids, "groupId": args.group_id,
                      "categoryId": args.category_id})
    else:
        print(f"{args.type} targeting added to group {args.group_id}: "
              f"ID {ids[0] if ids else '?'}")


def cmd_targeting_exclude(args: argparse.Namespace) -> None:
    """Exclude a category from a display group (negative targeting entry)."""
    dim = _dim(args)
    data = _api_call(dim["ns"] + ".negative.create", [[{
        "groupId": args.group_id,
        dim["category_field"]: args.category_id,
    }]], getattr(args, "user_id", None))
    ids = data.get(dim["created_ids_field"]) or _first_list_value(data)

    if args.json:
        _output_json({"ids": ids, "groupId": args.group_id,
                      "categoryId": args.category_id})
    else:
        print(f"{args.type} category {args.category_id} excluded from group "
              f"{args.group_id}: ID {ids[0] if ids else '?'}")


def cmd_targeting_remove(args: argparse.Namespace) -> None:
    """Remove a targeting entry (or an exclusion with --negative).

    Removal is a soft delete: re-adding the same category later fails with 409
    entity_already_exists — use targeting-restore with the old ID instead.
    """
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    dim = _dim(args)
    method = dim["ns"] + (".negative.remove" if args.negative else ".remove")
    _api_call(method, [[args.id]], getattr(args, "user_id", None))

    if args.json:
        _output_json({"removed": True, "id": args.id, "negative": bool(args.negative)})
    else:
        kind = "exclusion" if args.negative else "targeting entry"
        print(f"{args.type} {kind} {args.id} removed.")


def cmd_targeting_restore(args: argparse.Namespace) -> None:
    """Restore a removed targeting entry (or exclusion with --negative)."""
    dim = _dim(args)
    method = dim["ns"] + (".negative.restore" if args.negative else ".restore")
    _api_call(method, [[args.id]], getattr(args, "user_id", None))

    if args.json:
        _output_json({"restored": True, "id": args.id, "negative": bool(args.negative)})
    else:
        kind = "exclusion" if args.negative else "targeting entry"
        print(f"{args.type} {kind} {args.id} restored.")
