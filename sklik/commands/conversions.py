"""Conversion definition commands."""
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



def cmd_conversions(args: argparse.Namespace) -> None:
    """List conversion definitions."""
    # conversions.list takes only the user struct (no restriction/displayColumns).
    data = _api_call("conversions.list", [], getattr(args, "user_id", None))
    conversions = data.get("conversions", [])

    if args.json:
        out = [{
            "id": c.get("id"),
            "name": c.get("name"),
            "conversionTypeId": c.get("conversionTypeId"),
            "conversionTypeName": c.get("conversionTypeName"),
            "value": _halere_to_czk(c.get("value")),
            "color": c.get("color"),
            "removed": c.get("removed"),
        } for c in conversions]
        _output_json(out)
    else:
        if not conversions:
            print("No conversions found.")
            return
        print(f"{'ID':<12} {'Name':<30} {'Type':<28} {'Value':<12}")
        print("-" * 85)
        for c in conversions:
            print(f"{c.get('id', ''):<12} {c.get('name', ''):<30} "
                  f"{(c.get('conversionTypeName') or '?'):<28} "
                  f"{_format_money(c.get('value')):<12}")


def cmd_conversion_types(args: argparse.Namespace) -> None:
    """List conversion type IDs (for conversion-create).

    The listConversionTypes API method is currently broken server-side (HTTP 500),
    so we fall back to deriving the distinct types already used on the account.
    """
    user_id = getattr(args, "user_id", None)
    data = _api_call("conversions.list", [], user_id)
    seen: dict[int, str] = {}
    for c in data.get("conversions", []):
        tid = c.get("conversionTypeId")
        if tid is not None and tid not in seen:
            seen[tid] = c.get("conversionTypeName") or "?"
    types = [{"conversionTypeId": k, "name": v} for k, v in sorted(seen.items())]

    if args.json:
        _output_json(types)
    else:
        if not types:
            print("No conversion types in use yet. Use --type-id with a known "
                  "Sklik conversion type ID when creating a conversion.")
            return
        print("Conversion types currently in use on this account:")
        print(f"{'Type ID':<10} {'Name'}")
        print("-" * 40)
        for t in types:
            print(f"{t['conversionTypeId']:<10} {t['name']}")


def cmd_conversion_create(args: argparse.Namespace) -> None:
    """Create a conversion definition."""
    conv: dict = {
        "name": args.name,
        "conversionTypeId": args.type_id,
    }
    if args.value is not None:
        conv["value"] = _czk_to_halere(args.value)
    if args.color:
        conv["color"] = args.color

    data = _api_call("conversions.create", [[conv]], getattr(args, "user_id", None))
    ids = data.get("conversionIds", [])

    if args.json:
        _output_json({"conversionIds": ids})
    else:
        print(f"Conversion created: ID {ids[0] if ids else '?'}")


def cmd_conversion_update(args: argparse.Namespace) -> None:
    """Update a conversion definition."""
    update: dict = {"id": args.conversion_id}
    if args.name:
        update["name"] = args.name
    if args.value is not None:
        update["value"] = _czk_to_halere(args.value)
    if args.color:
        update["color"] = args.color

    if len(update) == 1:
        print("ERROR: No fields to update. Use --name, --value, or --color.", file=sys.stderr)
        sys.exit(1)

    _api_call("conversions.update", [[update]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "conversionId": args.conversion_id})
    else:
        print(f"Conversion {args.conversion_id} updated.")


def cmd_conversion_remove(args: argparse.Namespace) -> None:
    """Remove a conversion definition."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("conversions.remove", [[args.conversion_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "conversionId": args.conversion_id})
    else:
        print(f"Conversion {args.conversion_id} removed.")
