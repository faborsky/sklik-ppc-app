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
from datetime import datetime, timedelta

from sklik.api import _api_call, _fetch_all
from sklik.formatting import _output_json
from sklik.reports import _fetch_report


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


def _day_key(stat: dict) -> str:
    """Stats `date` (int 20261031) -> '2026-10-31'."""
    d = str(stat.get("date") or "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d


def cmd_budget_check(args: argparse.Namespace) -> None:
    """Flag campaigns whose daily spend keeps hitting the daily budget.

    The API has no "low budget" flag (the web UI's "Nízký rozpočet" is not
    exposed) and exhaustedBudgetShare / missImpressions can read 0 on campaigns
    that do hit the cap (seen live on a managed account), so the cap is detected from spend:
    a budget is binding when spend >= --threshold of it on >= --min-days of the
    window. Campaigns sharing one budget are pooled (the cap applies to the
    sum). The CURRENT budget is compared with past spend — the API gives no
    budget history, so a recently changed budget shows up as days far above
    100 %.
    """
    if args.days < 1:
        print("ERROR: --days must be >= 1.", file=sys.stderr)
        sys.exit(1)
    if not 0 < args.threshold <= 200:
        print("ERROR: --threshold is a percentage of the daily budget (1-200).",
              file=sys.stderr)
        sys.exit(1)

    uid = getattr(args, "user_id", None)
    # Today is incomplete (the cap isn't reached yet) -> end at yesterday.
    d_to = datetime.now() if args.include_today else datetime.now() - timedelta(days=1)
    d_from = d_to - timedelta(days=args.days - 1)
    date_from, date_to = d_from.strftime("%Y-%m-%d"), d_to.strftime("%Y-%m-%d")
    days = [(d_from + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(args.days)]

    campaigns = _fetch_all(
        "campaigns.list", {"isDeleted": False},
        ["id", "name", "status", "type", "budget.id", "budget.dayBudget"],
        "campaigns", uid)

    # Group campaigns by the budget that caps them (shared budget = pooled spend).
    groups: dict = {}
    for c in campaigns:
        b = c.get("budget") if isinstance(c.get("budget"), dict) else {}
        key = b.get("id") or f"c{c.get('id')}"
        g = groups.setdefault(key, {"budgetId": b.get("id"),
                                    "dayBudget": (b.get("dayBudget") or 0) / 100,
                                    "campaigns": []})
        g["campaigns"].append(c)

    report = _fetch_report(
        "campaigns", {}, date_from, date_to,
        ["id", "name", "totalMoney", "exhaustedBudgetShare", "missImpressions"],
        granularity="daily", user_id=uid)
    spend: dict = {}
    api_flag: dict = {}
    for r in report:
        per_day = spend.setdefault(r.get("id"), {})
        for s in r.get("stats") or []:
            k = _day_key(s)
            per_day[k] = per_day.get(k, 0) + (s.get("totalMoney") or 0) / 100
            api_flag[r.get("id")] = max(api_flag.get(r.get("id"), 0),
                                        s.get("exhaustedBudgetShare") or 0,
                                        s.get("missImpressions") or 0)

    rows = []
    skipped_no_budget = 0
    for g in groups.values():
        active = [c for c in g["campaigns"] if c.get("status") == "active"]
        if not active:
            continue
        if g["dayBudget"] <= 0:
            skipped_no_budget += 1  # e.g. fixed-price (CPT) placements
            continue
        daily = [sum(spend.get(c["id"], {}).get(d, 0) for c in g["campaigns"]) for d in days]
        pct = [round(x / g["dayBudget"] * 100) for x in daily]
        at_cap = sum(1 for p in pct if p >= args.threshold)
        shared = len(g["campaigns"]) > 1
        rows.append({
            "scope": "shared" if shared else "campaign",
            "id": None if shared else active[0]["id"],
            "budgetId": g["budgetId"],
            "name": (f"Sdílený rozpočet {g['budgetId']}: "
                     + ", ".join(c["name"] for c in active)) if shared else active[0]["name"],
            "campaigns": [{"id": c["id"], "name": c["name"]} for c in active],
            "dayBudget_czk": g["dayBudget"],
            "daysAtCap": at_cap,
            "daysInWindow": len(days),
            "limited": at_cap >= args.min_days,
            "maxPct": max(pct) if pct else 0,
            "avgPct": round(sum(pct) / len(pct)) if pct else 0,
            "dailyPct": dict(zip(days, pct)),
            "budgetChangedSuspected": any(p > 130 for p in pct),
            "apiFlagMax": max((api_flag.get(c["id"], 0) for c in g["campaigns"]), default=0),
        })
    rows.sort(key=lambda r: (-r["daysAtCap"], -r["maxPct"]))
    shown = rows if args.all else [r for r in rows if r["limited"]]
    limited_count = sum(1 for r in rows if r["limited"])

    if args.json:
        _output_json({
            "window": {"from": date_from, "to": date_to, "days": len(days)},
            "thresholdPct": args.threshold, "minDays": args.min_days,
            "limitedCount": limited_count, "checkedCount": len(rows),
            "skippedNoDayBudget": skipped_no_budget,
            "campaigns": shown,
        })
        return

    print(f"Budget check — {date_from} → {date_to} ({len(days)} d), "
          f"výdej ≥ {args.threshold:g} % denního rozpočtu aspoň {args.min_days}× "
          f"= omezeno rozpočtem")
    if not shown:
        print("Žádná aktivní kampaň nenarážela na denní rozpočet." if not args.all
              else "Žádné aktivní kampaně s denním rozpočtem.")
    for r in shown:
        mark = "OMEZENO" if r["limited"] else "ok"
        print(f"\n[{mark}] {r['name']}" + (f"  (id {r['id']})" if r["id"] else ""))
        print(f"  rozpočet {r['dayBudget_czk']:.0f} Kč/den · na stropu "
              f"{r['daysAtCap']}/{r['daysInWindow']} dní "
              f"· max {r['maxPct']} %, průměr {r['avgPct']} %")
        print("  po dnech: " + " ".join(f"{p}%" for p in r["dailyPct"].values()))
        if r["budgetChangedSuspected"]:
            print("  pozor: dny nad 130 % — rozpočet se v okně nejspíš změnil "
                  "(API nezná jeho historii), ověř v UI")
        if r["limited"] and r["apiFlagMax"] == 0:
            print("  API pole exhaustedBudgetShare/missImpressions hlásí 0 — u této kampaně nespolehlivé")
    print(f"\nZkontrolováno {len(rows)} aktivních rozpočtů, omezeno {limited_count}."
          + (f" {skipped_no_budget}× bez denního rozpočtu (přeskočeno)." if skipped_no_budget else ""))
