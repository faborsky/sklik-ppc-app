"""Seznam Nákupy commands (Fénix REST API): feed, offer diagnostics, campaign
bid multipliers, shopping statistics and per-item auction data.

These go through `sklik/fenix.py` — a different API and a different token from
every other command here. Each call needs a `premiseId` (shop): `--premise-id`
or `SKLIK_FENIX_PREMISE` in .env.

Two conventions differ from the DRAK commands and are easy to get wrong:

* **Money is plain CZK, not haléře** — never run these values through
  `_format_money` / `_convert_stats_to_czk`, which would divide by 100.
* **`maxCpcMultiplier` is a multiplier in percent, not a signed modifier** —
  100 means "no change", 120 means +20 %. DRAK's `--device-bids` uses the
  opposite convention (0 = no change), so the two are 100 points apart.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

import sklik.fenix as fenix
from sklik.api import _fail_msg
from sklik.formatting import _output_json

_SPLIT_CHOICES = ("deviceType", "webType", "productType", "conversionId")

# Numeric columns of a statistics row; everything else in the row is a
# dimension the report was split by (webType, offerCategory, itemId, …).
# Kept as a set of METRICS so an undocumented new dimension shows up in the
# output instead of silently disappearing.
_STAT_METRICS = frozenset({
    "impressions", "clicks", "conversions", "conversionPrice", "conversionRatio",
    "conversionValue", "directConversions", "avgCpc", "ctr", "pno",
    "totalMoney", "itemsSold",
})

# Per-request caps from the OpenAPI spec: loading extra per-item data makes the
# call much slower, so the API lowers the page size for it.
_SHOP_ITEM_LIMITS = {"plain": 3000, "search_info": 300, "product_detail": 50}


def _czk(value: float | None) -> str:
    """Format a Fénix money value. Fénix sends CZK — do NOT use _format_money."""
    if value is None:
        return "—"
    return f"{value:,.2f} Kč".replace(",", " ")


def _ratio(numerator: float | None, denominator: float | None) -> str:
    """Percentage derived from two raw counters, '—' when undefined.

    Ratios are computed rather than read from the report's own `ctr` / `pno`
    columns: the API does not document whether those are fractions or percents,
    and a wrong guess understates or overstates them 100× (the exact bug that
    hit `ctr` and `conversionValue` in earlier versions). `--json` still passes
    the API's own columns through untouched.
    """
    if not denominator:
        return "—"
    return f"{(numerator or 0) / denominator * 100:.2f}%"


def _multiplier(value: int | None) -> str:
    """Render a Fénix `maxCpcMultiplier`: 100 % = no change, 120 % = +20 %."""
    if value is None:
        return "—"
    delta = value - 100
    return f"{value} %" + (f" ({delta:+d} %)" if delta else " (beze změny)")


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------

def cmd_feed_status(args: argparse.Namespace) -> None:
    """Feed URL, last successful import and how often it may be downloaded."""
    premise = fenix.resolve_premise(args.premise_id)
    data = fenix.call("GET", "/nakupy/feeds/", {"premiseId": premise})
    feeds = data.get("items") or []

    if args.json:
        _output_json(feeds)
        return
    if not feeds:
        print("No feed configured for this shop.")
        return
    for f in feeds:
        print(f"Feed URL:            {f.get('feedUrl', '—')}")
        print(f"Last import (OK):    {f.get('lastSuccessfulImport', '—')}")
        print(f"Downloads per day:   {f.get('maxFeedDownloadsPerDay', '—')}")


def cmd_feed_diagnostics(args: argparse.Namespace) -> None:
    """Offer health: OK / error / not visible / improvable / without category."""
    premise = fenix.resolve_premise(args.premise_id)
    d = fenix.call("GET", "/nakupy/diagnostics/item", {"premiseId": premise})

    if args.json:
        _output_json(d)
        return
    print(f"Offers total:         {d.get('total', 0)}")
    for label, key in (("OK", "ok"), ("Error", "error"),
                       ("Not visible", "notVisible"),
                       ("Can be improved", "canBeImproved"),
                       ("Without category", "withoutCategory")):
        print(f"  {label + ':':<20}{d.get(key, 0)} ({d.get(key + 'Percentage', 0)} %)")
    print(f"  {'Assignable to cat.:':<20}{d.get('assignableToCategory', 0)}")
    print("\nOnly 'error' and 'not visible' stop an offer from serving; "
          "'can be improved' just means missing optional data (EAN, params, images).")


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

def cmd_nakupy_campaigns(args: argparse.Namespace) -> None:
    """Shopping campaigns with the bid multipliers DRAK cannot show."""
    premise = fenix.resolve_premise(args.premise_id)
    data = fenix.call("GET", "/nakupy/campaigns/", {"premiseId": premise})
    camps = data.get("items") or []

    if args.json:
        _output_json(camps)
        return
    if not camps:
        print("No Nákupy campaigns for this shop.")
        return
    for c in camps:
        budget = (c.get("budget") or {}).get("dayBudget")
        # dayBudget is CZK here; the campaign's `exhaustedDayBudget` is haléře.
        print(f"Campaign {c.get('id')}  status={c.get('status')}  "
              f"dayBudget={budget if budget is not None else '—'} Kč  "
              f"bidding={c.get('zboziBiddingType', '—')}")
        for label, rows, key in (("web ", c.get("websites"), "webType"),
                                 ("dev ", c.get("devices"), "deviceType"),
                                 ("type", c.get("products"), "productType")):
            for r in rows or []:
                print(f"  {label} {str(r.get(key)):10} "
                      f"{_multiplier(r.get('maxCpcMultiplier'))}")
    print("\nMultiplier 100 % = no change. Only DEVICE multipliers are writable "
          "via API (campaign-update --device-bids, where 0 = no change); "
          "web and auction-type multipliers are web-UI only.")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _print_stat_row(head: str, r: dict) -> None:
    print(f"  {head}")
    print(f"      Impr: {r.get('impressions', 0)}  Clicks: {r.get('clicks', 0)}  "
          f"CTR: {_ratio(r.get('clicks'), r.get('impressions'))}  "
          f"Avg CPC: {_czk(r.get('avgCpc'))}  Cost: {_czk(r.get('totalMoney'))}")
    print(f"      Conv: {r.get('conversions', 0)}  Value: {_czk(r.get('conversionValue'))}  "
          f"PNO: {_ratio(r.get('totalMoney'), r.get('conversionValue'))}  "
          f"Sold: {r.get('itemsSold', 0)}")


def cmd_nakupy_stats(args: argparse.Namespace) -> None:
    """Shopping statistics, split by placement/device/auction type or category."""
    premise = fenix.resolve_premise(args.premise_id)
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    body: dict = {
        "from": f"{date_from}T00:00:00Z",
        "to": f"{date_to}T23:59:59Z",
        "format": ["json"],
        "granularity": args.granularity,
    }
    if args.by_category:
        endpoint = "/nakupy/statistics/category"
        if args.split:
            _fail_msg("--split and --by-category are different reports — use one.")
    else:
        endpoint = "/nakupy/statistics/aggregated"
        if args.split:
            splits = [s.strip() for s in args.split.split(",") if s.strip()]
            bad = [s for s in splits if s not in _SPLIT_CHOICES]
            if bad:
                _fail_msg(f"invalid --split value(s): {', '.join(bad)}. "
                          f"Allowed: {', '.join(_SPLIT_CHOICES)}.")
            body["splitStats"] = splits

    created = fenix.call("POST", endpoint, {"premiseId": premise}, body=body)
    report_id = created.get("id")
    if report_id is None:
        _fail_msg("Fénix accepted the statistics request but returned no report id.",
                  detail=created)

    report = fenix.poll_report(report_id)
    rows = report.get("stats") or []
    sums = report.get("sums") or {}

    if args.json:
        _output_json({"from": date_from, "to": date_to,
                      "granularity": args.granularity,
                      "sums": sums, "stats": rows})
        return

    label = "by category" if args.by_category else (args.split or "no split")
    print(f"Nákupy stats ({date_from} — {date_to}, {label}):\n")
    if not rows and not sums:
        print("No data for this period.")
        return
    for r in rows:
        dims = [f"{k}={v}" for k, v in r.items()
                if k not in _STAT_METRICS and v is not None]
        _print_stat_row("  ".join(dims) if dims else "—", r)
    if sums:
        _print_stat_row("TOTAL", sums)


# ---------------------------------------------------------------------------
# Shop items
# ---------------------------------------------------------------------------

def _shop_item_limit(args: argparse.Namespace) -> int:
    """Page size allowed for the requested detail level (API-enforced caps)."""
    cap = _SHOP_ITEM_LIMITS["plain"]
    if args.search_info:
        cap = min(cap, _SHOP_ITEM_LIMITS["search_info"])
    if args.product_detail:
        cap = min(cap, _SHOP_ITEM_LIMITS["product_detail"])
    if args.limit is None:
        return cap
    if args.limit > cap:
        _fail_msg(f"--limit {args.limit} exceeds the API cap of {cap} for this "
                  "call (3000 plain, 300 with --search-info, 50 with "
                  "--product-detail).")
    return args.limit


def cmd_shop_items(args: argparse.Namespace) -> None:
    """Feed items: pairing, per-item CPC and (with --product-detail) the auction
    position plus the CPC needed to win it."""
    premise = fenix.resolve_premise(args.premise_id)
    limit = _shop_item_limit(args)

    params: dict = {"premiseId": premise}
    if args.unpaired:
        params["paired"] = "false"
    elif args.paired:
        params["paired"] = "true"
    if args.product_detail:
        params["loadProductDetail"] = "true"
    if args.search_info:
        params["loadSearchInfo"] = "true"
    if args.item_id:
        ids = [s.strip() for s in args.item_id.split(",") if s.strip()]
        cap = 50 if args.product_detail else 100
        if len(ids) > cap:
            _fail_msg(f"--item-id takes at most {cap} IDs per call"
                      f"{' with --product-detail' if args.product_detail else ''}; "
                      f"got {len(ids)}.")
        params["itemId"] = ids

    if args.all:
        items, total = fenix.fetch_all("/nakupy/shop-items/", params, limit)
    else:
        data = fenix.call("GET", "/nakupy/shop-items/", dict(params, limit=limit))
        items = data.get("items") or []
        total = (data.get("meta") or {}).get("totalCount")

    # The `paired` query filter is also applied client-side on the per-item
    # `product` field, which is what the pairing actually is. Belt and braces:
    # a filter silently ignored by the API would otherwise pass unnoticed.
    if args.unpaired:
        items = [it for it in items if not it.get("product")]
    elif args.paired:
        items = [it for it in items if it.get("product")]

    if args.json:
        _output_json({"totalCount": total, "complete": bool(args.all),
                      "items": items})
    else:
        print(f"Shop items: {len(items)} shown / {total if total is not None else '?'} total")
        for it in items:
            prod = it.get("product") or {}
            detail = prod.get("productDetailInfo") or {}
            line = (f"  {str(it.get('itemId')):24} "
                    f"{'paired' if prod else 'UNPAIRED':9} "
                    f"maxCpcSearch={_czk(it.get('maxCpcSearch'))} "
                    f"minCpc={_czk(it.get('minCpc'))}")
            if detail:
                line += (f"  pos={detail.get('fromCheapestPosition', '—')} "
                         f"top={detail.get('topPosition', '—')} "
                         f"cpcToWin={_czk(detail.get('maxCpc'))}")
            print(f"{line}  {(it.get('name') or '')[:40]}")

    # Never let a truncated list look complete — the v1.9.0 lesson, restated
    # for Fénix's cursor paging. stderr keeps --json output parseable.
    if not args.all and total is not None and total > len(items):
        print(f"NOTE: showing {len(items)} of {total} items — add --all to page "
              "through the whole feed.", file=sys.stderr)
