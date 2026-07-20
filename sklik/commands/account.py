"""Account, api-limits and pulse commands."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta

import sklik.api as api
from sklik.api import _api_call, _fail_msg, _load_rate_state, RATE_LIMIT_SAFETY
from sklik.formatting import (
    _halere_to_czk, _format_money, _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, STAT_COLUMNS



# ---------------------------------------------------------------------------
# Commands — Account
# ---------------------------------------------------------------------------

def cmd_account(args: argparse.Namespace) -> None:
    """Show account info."""
    data = _api_call("client.get", [], getattr(args, "user_id", None))
    # client.get nests the account fields under a "user" struct; fall back to the
    # top level for forward/backward compatibility.
    acct = data.get("user", data)

    if args.json:
        info = {
            "userId": acct.get("userId"),
            "username": acct.get("username"),
            "walletCredit": _halere_to_czk(acct.get("walletCredit")),
            "walletCreditWithVat": _halere_to_czk(acct.get("walletCreditWithVat")),
            "walletVerified": acct.get("walletVerified"),
            "dayBudgetSum": _halere_to_czk(acct.get("dayBudgetSum")),
            "accountLimit": _halere_to_czk(acct.get("accountLimit")),
            "agencyStatus": acct.get("agencyStatus"),
        }
        foreign = data.get("foreignAccounts", [])
        if foreign:
            info["foreignAccounts"] = [{
                "userId": a.get("userId"),
                "username": a.get("username"),
                "access": a.get("access"),
                "walletCredit": _halere_to_czk(a.get("walletCredit")),
            } for a in foreign]
        _output_json(info)
    else:
        print(f"Account:        {acct.get('username', '?')} (ID: {acct.get('userId', '?')})")
        print(f"Wallet:         {_format_money(acct.get('walletCredit'))}")
        print(f"Wallet (VAT):   {_format_money(acct.get('walletCreditWithVat'))}")
        print(f"Verified:       {acct.get('walletVerified', '?')}")
        print(f"Day budget sum: {_format_money(acct.get('dayBudgetSum'))}")
        limit = acct.get("accountLimit")
        print(f"Account limit:  {_format_money(limit) if limit else '—'}")
        print(f"Agency status:  {acct.get('agencyStatus', '?')}")

        foreign = data.get("foreignAccounts", [])
        if foreign:
            print(f"\nManaged accounts ({len(foreign)}):")
            for a in foreign:
                print(f"  {a.get('username', '?')} (ID: {a.get('userId')}) "
                      f"[{a.get('access')}] credit: {_format_money(a.get('walletCredit'))}")


def cmd_api_limits(args: argparse.Namespace) -> None:
    """Show the account's API limits (rate limits, batch caps, value ranges)
    plus the local request-budget usage tracked across sessions."""
    data = _api_call("api.limits", user_id=getattr(args, "user_id", None), _throttle=False)
    limits = data.get("limits", {}) or {}
    batch = data.get("batchCallLimits", []) or []

    # Local rolling usage from our own budget file.
    state = _load_rate_state()
    now = time.time()
    reqs = [t for t in state.get("requests", []) if now - t < 86400]
    minute_used = len([t for t in reqs if now - t < 60])
    day_used = len(reqs)

    def _range(lo: object, hi: object) -> str:
        lo_c = _halere_to_czk(lo) if lo is not None else None
        hi_c = _halere_to_czk(hi) if hi is not None else None
        return f"{lo_c if lo_c is not None else '—'} – {hi_c if hi_c is not None else '—'} Kč"

    if args.json:
        _output_json({
            "account": api.ACTIVE_ACCOUNT,
            "limits": limits,
            "batchCallLimits": batch,
            "localUsage": {
                "requestsLastMinute": minute_used,
                "requestsLast24h": day_used,
                "safetyFactor": RATE_LIMIT_SAFETY,
            },
        })
        return

    print(f"=== API limits — account '{api.ACTIVE_ACCOUNT}' ===")
    print(f"Requests/minute:   {limits.get('minuteRequestLimit', '—')}  "
          f"(local usage last 60s: {minute_used})")
    print(f"Requests/day:      {limits.get('dayRequestLimit', '—')}  "
          f"(local usage last 24h: {day_used})")
    print(f"Stats rows/report: {limits.get('statsDataLimit', '—')}")
    print(f"Safety margin:     CLI throttles at {int(RATE_LIMIT_SAFETY * 100)}% of these")
    print()
    print("Value ranges:")
    print(f"  CPC:        {_range(limits.get('CpcMin'), limits.get('CpcMax'))}")
    print(f"  CPM:        {_range(limits.get('CpmMin'), limits.get('CpmMax'))}")
    print(f"  Day budget: {_range(limits.get('dayBudgetMin'), limits.get('dayBudgetMax'))}")
    vat = limits.get("valueAddedTax")
    if vat is not None:
        print(f"  VAT:        {round(vat * 100)}%")
    print(f"  Banner max: {limits.get('bannerSizeKBMax', '—')} KB")
    if batch:
        print()
        print(f"Batch limits — max items per call ({len(batch)} entries):")
        for b in batch:
            print(f"  {str(b.get('name')):30} {b.get('limit')}")


def _first_stats(row: dict) -> dict:
    """Return the single 'total'-granularity stats dict from a report row."""
    stats = row.get("stats") or []
    return stats[0] if stats else {}


def _pct_delta(cur: float, prev: float | None) -> str:
    """Human-readable percent change of cur vs a previous value."""
    if prev is None or prev == 0:
        return "new" if cur else "—"
    pct = (cur - prev) / prev * 100
    arrow = "↑" if pct > 0 else ("↓" if pct < 0 else "→")
    return f"{arrow}{abs(pct):.0f}%"


def cmd_pulse(args: argparse.Namespace) -> None:
    """Account-wide PPC pulse — ONE compact digest instead of many calls.

    Fetches campaign-level stats for the window (and, unless --no-compare, the
    previous equal-length window), pre-computes totals + per-campaign deltas +
    top movers, and prints a small digest. The point is token economy: a caller
    (e.g. an analytics agent) gets an aggregated summary instead of dumping raw
    rows from account + campaigns + campaign-stats into its context.
    """
    if bool(args.date_from) != bool(args.date_to):
        print("ERROR: --date-from a --date-to musí být zadané spolu.", file=sys.stderr)
        sys.exit(1)

    today = datetime.now()
    if args.date_from and args.date_to:
        date_from, date_to = args.date_from, args.date_to
        d_from = datetime.strptime(date_from, "%Y-%m-%d")
        d_to = datetime.strptime(date_to, "%Y-%m-%d")
        window = (d_to - d_from).days + 1
    else:
        window = args.days
        d_to = today
        d_from = today - timedelta(days=window - 1)
        date_from = d_from.strftime("%Y-%m-%d")
        date_to = d_to.strftime("%Y-%m-%d")

    user_id = getattr(args, "user_id", None)
    cols = ["id", "name"] + STAT_COLUMNS
    cur_report = _fetch_report("campaigns", {}, date_from, date_to, cols, user_id=user_id)

    compare = not args.no_compare
    prev_map: dict = {}
    prev_from = prev_to = None
    if compare:
        prev_to_dt = d_from - timedelta(days=1)
        prev_from_dt = prev_to_dt - timedelta(days=window - 1)
        prev_from = prev_from_dt.strftime("%Y-%m-%d")
        prev_to = prev_to_dt.strftime("%Y-%m-%d")
        prev_report = _fetch_report("campaigns", {}, prev_from, prev_to, cols, user_id=user_id)
        prev_map = {r.get("id"): _first_stats(r) for r in prev_report}

    # Per-campaign rows (cost stays in haléře until display; conversionValue
    # arrives from the API already in CZK — see docs/api-notes.md); accumulate totals.
    rows = []
    tot = {"clicks": 0, "impressions": 0, "totalMoney": 0, "conversions": 0.0, "conversionValue": 0}
    for r in cur_report:
        s = _first_stats(r)
        cid = r.get("id")
        clicks = s.get("clicks", 0) or 0
        impr = s.get("impressions", 0) or 0
        cost = s.get("totalMoney", 0) or 0
        conv = s.get("conversions", 0) or 0
        val = s.get("conversionValue", 0) or 0
        p = prev_map.get(cid, {})
        rows.append({
            "id": cid,
            "name": r.get("name", "?"),
            "clicks": clicks,
            "impressions": impr,
            "ctr": (clicks / impr * 100) if impr else 0.0,
            "avgCpc_czk": (cost / clicks / 100) if clicks else 0.0,
            "cost_czk": cost / 100,
            "conversions": conv,
            "convValue_czk": val,
            "pno": (cost / 100 / val * 100) if val else None,
            "d_cost": _pct_delta(cost, p.get("totalMoney")) if compare else None,
            "d_clicks": _pct_delta(clicks, p.get("clicks")) if compare else None,
            "d_conv": _pct_delta(conv, p.get("conversions")) if compare else None,
            "_cost": cost, "_prev_cost": p.get("totalMoney") or 0,
            "_conv": conv, "_prev_conv": p.get("conversions") or 0,
        })
        tot["clicks"] += clicks
        tot["impressions"] += impr
        tot["totalMoney"] += cost
        tot["conversions"] += conv
        tot["conversionValue"] += val

    ptot = {"clicks": 0, "impressions": 0, "totalMoney": 0, "conversions": 0.0, "conversionValue": 0}
    for s in prev_map.values():
        ptot["clicks"] += s.get("clicks", 0) or 0
        ptot["impressions"] += s.get("impressions", 0) or 0
        ptot["totalMoney"] += s.get("totalMoney", 0) or 0
        ptot["conversions"] += s.get("conversions", 0) or 0
        ptot["conversionValue"] += s.get("conversionValue", 0) or 0

    active = sorted((r for r in rows if r["impressions"] > 0), key=lambda r: r["_cost"], reverse=True)
    hidden = len(rows) - len(active)

    totals = {
        "cost_czk": tot["totalMoney"] / 100,
        "clicks": tot["clicks"],
        "impressions": tot["impressions"],
        "ctr": (tot["clicks"] / tot["impressions"] * 100) if tot["impressions"] else 0.0,
        "avgCpc_czk": (tot["totalMoney"] / tot["clicks"] / 100) if tot["clicks"] else 0.0,
        "conversions": tot["conversions"],
        "convValue_czk": tot["conversionValue"],
        "pno": (tot["totalMoney"] / 100 / tot["conversionValue"] * 100) if tot["conversionValue"] else None,
    }
    if compare:
        totals["d_cost"] = _pct_delta(tot["totalMoney"], ptot["totalMoney"])
        totals["d_clicks"] = _pct_delta(tot["clicks"], ptot["clicks"])
        totals["d_impr"] = _pct_delta(tot["impressions"], ptot["impressions"])
        totals["d_conv"] = _pct_delta(tot["conversions"], ptot["conversions"])

    # Movers: biggest absolute cost & conversion swings vs previous period.
    movers = []
    if compare:
        for r in sorted(active, key=lambda r: abs(r["_cost"] - r["_prev_cost"]), reverse=True)[:3]:
            if r["_cost"] != r["_prev_cost"]:
                movers.append(f"{r['name']}: cost {r['d_cost']}")
        for r in sorted(active, key=lambda r: abs(r["_conv"] - r["_prev_conv"]), reverse=True)[:2]:
            if r["_conv"] != r["_prev_conv"]:
                movers.append(f"{r['name']}: conv {r['d_conv']}")

    # Data-readiness check (stats.status): warn when any day in the window is
    # still "preparing"/"error" — totals and deltas would be computed from
    # partial data. Soft call: a failure here must never break the pulse.
    stats_warning = None
    sdata = _api_call("stats.status", [{"dateFrom": date_from, "dateTo": date_to}],
                      user_id, _soft=True)
    if isinstance(sdata, dict) and sdata.get("status") in (200, 206):
        day_rows = next((v for k, v in sdata.items()
                         if k != "diagnostics" and isinstance(v, list)), [])
        bad = [d for d in day_rows
               if isinstance(d, dict) and d.get("status") not in ("complete", None)]
        if bad:
            def _fmt_day(raw: object) -> str:
                s = str(raw).split("T")[0].replace("-", "")
                return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s.isdigit() else str(raw)
            detail = ", ".join(f"{_fmt_day(d.get('date'))}: {d.get('status')}" for d in bad[:5])
            more = " …" if len(bad) > 5 else ""
            stats_warning = (f"Statistiky za {len(bad)} dní okna ještě nejsou kompletní "
                             f"({detail}{more}) — čísla a delty ber s rezervou.")

    if args.json:
        _output_json({
            "account": args.account,
            "period": {"from": date_from, "to": date_to, "days": window},
            "comparePeriod": ({"from": prev_from, "to": prev_to} if compare else None),
            "statsWarning": stats_warning,
            "totals": totals,
            "campaigns": [{k: v for k, v in r.items() if not k.startswith("_")} for r in active],
            "hiddenZeroImpressionCampaigns": hidden,
            "movers": movers,
        })
        return

    # --- compact text digest ---
    print(f"Sklik pulse — {args.account}  ({date_from} → {date_to}, {window}d)")
    if compare:
        print(f"vs předchozích {window} dní ({prev_from} → {prev_to})")
    if stats_warning:
        print(f"⚠️  {stats_warning}")
    print()

    def dd(key: str) -> str:
        return f" ({totals[key]})" if compare else ""

    pno_str = f"{totals['pno']:.0f}%" if totals["pno"] is not None else "—"
    print(
        f"TOTAL  cost {totals['cost_czk']:.0f} Kč{dd('d_cost')}  "
        f"clicks {totals['clicks']}{dd('d_clicks')}  "
        f"impr {totals['impressions']}{dd('d_impr')}  "
        f"CTR {totals['ctr']:.2f}%  CPC {totals['avgCpc_czk']:.2f} Kč  "
        f"conv {totals['conversions']:.0f}{dd('d_conv')}  "
        f"val {totals['convValue_czk']:.0f} Kč  PNO {pno_str}"
    )
    print()

    if not active:
        print("Žádná kampaň se zobrazeními v období.")
        return

    print("Kampaně (aktivní v období, dle nákladů):")
    for r in active:
        name = r["name"][:30]
        pno_c = f"{r['pno']:.0f}%" if r["pno"] is not None else "—"
        dcost = r["d_cost"] if compare else ""
        dconv = r["d_conv"] if compare else ""
        print(
            f"  {name:<30} {r['cost_czk']:>6.0f} Kč {dcost:<6} "
            f"clk {r['clicks']:>4} CTR {r['ctr']:>5.2f}% "
            f"conv {r['conversions']:>3.0f} {dconv:<6} PNO {pno_c}"
        )
    if hidden:
        print(f"  (+{hidden} kampaní bez zobrazení skryto)")

    if movers:
        print()
        print("Hlavní pohyby: " + "; ".join(movers))


# ---------------------------------------------------------------------------
# Commands — credit, regions catalog, autotagging (account-level utilities)
# ---------------------------------------------------------------------------

def cmd_credit(args: argparse.Namespace) -> None:
    """Show wallet credit (client.getCredit). Amounts are plain CZK."""
    data = _api_call("client.getCredit", [], getattr(args, "user_id", None))
    clients = data.get("clients", [])

    rows = [{
        "userId": c.get("userId"),
        "credit": c.get("credit"),
        "creditWithVat": c.get("creditWithVat"),
        "agencyStatus": c.get("agencyStatus"),
        "agencyLimit": c.get("agencyLimit"),
    } for c in clients]

    if args.json:
        _output_json(rows)
    else:
        if not rows:
            print("No credit info returned.")
            return
        for r in rows:
            print(f"User {r['userId']}: kredit {r['credit']} Kč "
                  f"(s DPH {r['creditWithVat']} Kč)"
                  + (f", typ: {r['agencyStatus']}" if r.get("agencyStatus") else ""))


def cmd_regions(args: argparse.Namespace) -> None:
    """List predefined region IDs for --regions targeting."""
    data = _api_call("listPredefinedRegions", [],
                     getattr(args, "user_id", None))
    regions = data.get("predefinedRegions", [])

    if args.json:
        _output_json([{"id": r.get("id"), "name": r.get("name")} for r in regions])
    else:
        if not regions:
            print("No regions returned.")
            return
        print(f"{'ID':<8} Name")
        print("-" * 40)
        for r in regions:
            print(f"{r.get('id', ''):<8} {r.get('name', '')}")


def cmd_autotagging(args: argparse.Namespace) -> None:
    """Show the account's autotagging (UTM) configuration."""
    data = _api_call("autotagging.get", [], getattr(args, "user_id", None))
    cfg = data.get("autotagging") or {
        k: v for k, v in data.items()
        if k not in ("status", "statusMessage", "session", "diagnostics")
    }
    if args.json:
        _output_json(cfg)
    else:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))


def cmd_autotagging_update(args: argparse.Namespace) -> None:
    """Update autotagging config: current settings merged with the overrides."""
    uid = getattr(args, "user_id", None)
    data = _api_call("autotagging.get", [], uid)
    cfg = data.get("autotagging") or {
        k: v for k, v in data.items()
        if k not in ("status", "statusMessage", "session", "diagnostics")
    }

    overrides: dict = {}
    if args.config_json:
        try:
            overrides = json.loads(args.config_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid --config-json: {e}", file=sys.stderr)
            sys.exit(1)
    if args.enabled is not None:
        overrides["enabled"] = args.enabled == "on"

    if not overrides:
        print("ERROR: Nothing to update. Use --enabled on/off or --config-json.",
              file=sys.stderr)
        sys.exit(1)

    # autotagging.get returns read-only fields (e.g. separatorChar) that
    # autotagging.update rejects — whitelist the updatable ones.
    updatable = {"enabled", "paramChar", "removeAccents",
                 "utmSource", "utmMedium", "utmCampaign", "utmContent",
                 "utmKeyword", "utmId", "utmOptional1", "utmOptional2", "utmOptional3"}
    merged = {k: v for k, v in {**cfg, **overrides}.items() if k in updatable}
    _api_call("autotagging.update", [merged], uid)

    if args.json:
        _output_json({"updated": True, "autotagging": merged})
    else:
        print("Autotagging updated.")
