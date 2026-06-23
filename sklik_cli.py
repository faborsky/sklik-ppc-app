#!/usr/bin/env python3
"""Sklik DRAK CLI — manage PPC search campaigns on Seznam Sklik.

SAFETY: Destructive operations require --confirm flag.
Prices: CLI accepts CZK, internally converts to halere (×100).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

__version__ = "1.4.0"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Pinned to v5 (current stable). Using the unpinned ".../drak/json" endpoint
# would silently follow the newest version and could break on a major bump.
API_BASE = "https://api.sklik.cz/drak/json/v5"

# ---------------------------------------------------------------------------
# Multi-account support
# ---------------------------------------------------------------------------
# Each account is a SEPARATE Sklik login with its OWN API token (and therefore
# its own session). Select with the global `--account` flag.
# `--user-id` is different: it acts on a MANAGED account UNDER the active login.
#
# Tokens come from environment variables (in .env):
#   SKLIK_API_TOKEN          -> the "default" account (used when --account omitted)
#   SKLIK_API_TOKEN_<NAME>   -> a named account, selected with --account <name>
# Accounts are discovered from the environment at runtime — no names are
# hardcoded, so any number of logins can be configured.
DEFAULT_ACCOUNT = "default"

# Set by set_account() (called from main() once args are parsed).
ACTIVE_ACCOUNT = DEFAULT_ACCOUNT


def _token_env_var(account: str) -> str:
    """Environment variable holding the API token for a given account name."""
    if account == DEFAULT_ACCOUNT:
        return "SKLIK_API_TOKEN"
    return f"SKLIK_API_TOKEN_{account.upper()}"


def _available_accounts() -> list[str]:
    """Account names that have a token configured in the environment."""
    accounts = []
    if os.getenv("SKLIK_API_TOKEN"):
        accounts.append(DEFAULT_ACCOUNT)
    prefix = "SKLIK_API_TOKEN_"
    for key in os.environ:
        if key.startswith(prefix) and os.getenv(key):
            accounts.append(key[len(prefix):].lower())
    return accounts


def set_account(account: str) -> None:
    """Select the active Sklik login for this invocation."""
    global ACTIVE_ACCOUNT, _current_session
    ACTIVE_ACCOUNT = account
    _current_session = None  # different account => different session


def _get_token() -> str:
    """API token for the active account."""
    return os.getenv(_token_env_var(ACTIVE_ACCOUNT), "")


def _session_cache_path() -> str:
    """Per-account session cache file (sessions are not shared across logins)."""
    return os.path.join(BASE_DIR, f".session_cache_{ACTIVE_ACCOUNT}.json")


# ---------------------------------------------------------------------------
# Auth & Session helpers
# ---------------------------------------------------------------------------

def _check_config() -> None:
    token = _get_token()
    if not token or token.startswith("your-"):
        env_var = _token_env_var(ACTIVE_ACCOUNT)
        msg = (f"ERROR: {env_var} not set for account '{ACTIVE_ACCOUNT}'. "
               f"Add it to .env (see .env.example).")
        available = _available_accounts()
        if available:
            msg += f" Configured accounts: {', '.join(available)}."
        print(msg, file=sys.stderr)
        sys.exit(1)


def _load_session() -> str | None:
    """Load cached session for the active account if still valid."""
    path = _session_cache_path()
    if os.path.exists(path):
        with open(path, "r") as f:
            cache = json.load(f)
        if cache.get("expires_at", 0) > time.time():
            return cache["session"]
    return None


def _save_session(session: str) -> None:
    """Cache session for 25 minutes (per active account)."""
    with open(_session_cache_path(), "w") as f:
        json.dump({
            "session": session,
            "expires_at": time.time() + 1500,  # 25 min
        }, f)


def _login() -> str:
    """Authenticate via the active account's token, return session string."""
    resp = requests.post(
        f"{API_BASE}/client.loginByToken",
        json=[_get_token()],
        timeout=30,
    )
    data = resp.json()
    if data.get("status") != 200:
        print(f"ERROR: Login failed ({data.get('status')}): {data.get('statusMessage')}", file=sys.stderr)
        if data.get("diagnostics"):
            for d in data["diagnostics"]:
                print(f"  - {d.get('id')}: {d.get('field', '')} {d.get('type', '')}", file=sys.stderr)
        sys.exit(1)
    session = data["session"]
    _save_session(session)
    return session


def _get_session() -> str:
    """Get valid session (from cache or fresh login)."""
    session = _load_session()
    if session:
        return session
    return _login()


# ---------------------------------------------------------------------------
# Rate limiting — local, cross-session request budget per account
# ---------------------------------------------------------------------------
# Sklik enforces a per-account minuteRequestLimit / dayRequestLimit (queryable
# at runtime via the api.limits method — the numbers are NOT published and are
# account-specific). Exceeding them returns status 429 and, if abused, can get
# an account throttled or blocked. To respect the budget even across separate
# CLI runs and parallel sessions, we keep a rolling log of our own request
# timestamps in a per-account file (sibling to the session cache) and check it
# BEFORE every call — proactively, not just reactively after a 429.
#
# Behaviour: minute ceiling -> wait out the rolling 60s window, then proceed;
# day ceiling -> refuse the call (never loop), so a runaway job can't keep
# hammering an account that is already at its daily limit.

RATE_LIMIT_SAFETY = 0.9        # use at most 90% of the account's stated limits
RATE_LIMIT_REFRESH = 86400     # re-fetch api.limits at most once a day (seconds)
RATE_LIMIT_MAX_WAIT = 180      # max seconds to wait out a full minute window
# Conservative fallbacks if api.limits can't be fetched (real values are usually
# higher — better to throttle a little early than risk a block).
RATE_LIMIT_FALLBACK_MINUTE = 250
RATE_LIMIT_FALLBACK_DAY = 100000


def _rate_limit_path() -> str:
    """Per-account rolling request-budget file (not shared across logins)."""
    return os.path.join(BASE_DIR, f".rate_limit_{ACTIVE_ACCOUNT}.json")


def _load_rate_state() -> dict:
    path = _rate_limit_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"requests": [], "limits": None, "limits_fetched": 0}


def _save_rate_state(state: dict) -> None:
    try:
        with open(_rate_limit_path(), "w") as f:
            json.dump(state, f)
    except OSError:
        pass  # bookkeeping must never break a real operation


def _ensure_limits(user_id: int | None) -> dict:
    """Return cached {minute, day} request limits, refreshing via api.limits
    at most once a day. Falls back to conservative defaults if unavailable."""
    state = _load_rate_state()
    cached = state.get("limits")
    if cached and (time.time() - state.get("limits_fetched", 0)) < RATE_LIMIT_REFRESH:
        return cached

    minute, day = RATE_LIMIT_FALLBACK_MINUTE, RATE_LIMIT_FALLBACK_DAY
    try:
        # _throttle=False: avoids recursing back into the throttle (this call is
        # itself counted by _record_request, just not pre-checked).
        data = _api_call("api.limits", user_id=user_id, _throttle=False)
        lim = data.get("limits", {}) or {}
        minute = int(lim.get("minuteRequestLimit") or minute)
        day = int(lim.get("dayRequestLimit") or day)
    except SystemExit:
        pass  # transient api.limits failure — keep fallbacks, retry next day

    result = {"minute": minute, "day": day}
    # Re-load: the api.limits call above just recorded a request timestamp.
    state = _load_rate_state()
    state["limits"] = result
    state["limits_fetched"] = time.time()
    _save_rate_state(state)
    return result


def _throttle_request(user_id: int | None) -> None:
    """Enforce the local per-account request budget before an API call."""
    limits = _ensure_limits(user_id)
    minute_cap = max(1, int(limits["minute"] * RATE_LIMIT_SAFETY))
    day_cap = max(1, int(limits["day"] * RATE_LIMIT_SAFETY))

    state = _load_rate_state()
    now = time.time()
    reqs = [t for t in state.get("requests", []) if now - t < 86400]

    # Day ceiling — hard stop, never loop.
    if len(reqs) >= day_cap:
        wait_h = (86400 - (now - min(reqs))) / 3600
        state["requests"] = reqs
        _save_rate_state(state)
        print(
            f"ERROR: daily request budget reached for account '{ACTIVE_ACCOUNT}' "
            f"({len(reqs)}/{limits['day']} incl. {int(RATE_LIMIT_SAFETY*100)}% safety "
            f"margin). Resets in ~{wait_h:.1f}h. Aborting to protect the account.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Minute ceiling — wait out the rolling 60s window.
    waited = 0.0
    while True:
        minute_reqs = [t for t in reqs if now - t < 60]
        if len(minute_reqs) < minute_cap:
            break
        sleep_for = max(1.0, 60 - (now - min(minute_reqs)) + 0.5)
        if waited + sleep_for > RATE_LIMIT_MAX_WAIT:
            print(
                f"WARNING: minute request budget for '{ACTIVE_ACCOUNT}' still full "
                f"after {int(waited)}s — proceeding; Sklik may return 429.",
                file=sys.stderr,
            )
            break
        print(
            f"Rate budget: {len(minute_reqs)}/{limits['minute']} req/min for "
            f"'{ACTIVE_ACCOUNT}', waiting {sleep_for:.0f}s…",
            file=sys.stderr,
        )
        time.sleep(sleep_for)
        now = time.time()
        reqs = [t for t in reqs if now - t < 86400]
        waited += sleep_for

    state["requests"] = reqs
    _save_rate_state(state)


def _record_request() -> None:
    """Append the current request's timestamp to the rolling local budget."""
    state = _load_rate_state()
    now = time.time()
    reqs = [t for t in state.get("requests", []) if now - t < 86400]
    reqs.append(now)
    state["requests"] = reqs
    _save_rate_state(state)


# ---------------------------------------------------------------------------
# API call helper
# ---------------------------------------------------------------------------

_current_session: str | None = None


def _api_call(method: str, params: list | None = None, user_id: int | None = None,
              _throttle: bool = True, _retries: int = 0) -> dict:
    """Make a Sklik DRAK API call with session management.

    First param is always the user struct with session.
    Handles 401 by re-authenticating once.

    Respects the account's per-minute / per-day request budget (tracked locally
    across sessions); `_throttle=False` skips the pre-check (used only for the
    api.limits fetch itself, which is still counted).
    """
    global _current_session

    if _current_session is None:
        _current_session = _get_session()

    # Stay inside the account's request budget before spending a request.
    if _throttle:
        _throttle_request(user_id)
    _record_request()

    user_struct: dict[str, str | int] = {"session": _current_session}
    if user_id:
        user_struct["userId"] = user_id

    all_params = [user_struct] + (params or [])

    resp = requests.post(
        f"{API_BASE}/{method}",
        json=all_params,
        timeout=60,
    )
    data = resp.json()

    # Handle expired session — re-auth once
    if data.get("status") == 401:
        _current_session = _login()
        all_params[0] = {"session": _current_session}
        if user_id:
            all_params[0]["userId"] = user_id
        resp = requests.post(
            f"{API_BASE}/{method}",
            json=all_params,
            timeout=60,
        )
        data = resp.json()

    # Update cached session from response
    if "session" in data and data["session"]:
        _current_session = data["session"]
        _save_session(_current_session)

    # Handle rate limiting (429) — capped, backing-off retry so a throttled
    # account is never hammered in an infinite loop.
    if data.get("status") == 429:
        if _retries >= 3:
            print(f"ERROR: {method} still rate-limited (429) after {_retries} retries — "
                  f"giving up to protect account '{ACTIVE_ACCOUNT}'.", file=sys.stderr)
            sys.exit(1)
        wait = 5 * (_retries + 1)  # 5s, 10s, 15s
        print(f"Rate limited (429), waiting {wait}s… (retry {_retries + 1}/3)", file=sys.stderr)
        time.sleep(wait)
        return _api_call(method, params, user_id, _throttle=_throttle, _retries=_retries + 1)

    # Handle errors
    if data.get("status") not in (200, 206):
        print(f"ERROR: {method} returned {data.get('status')}: {data.get('statusMessage')}", file=sys.stderr)
        if method.startswith("conversions.") and _is_sem_blocked(data):
            print("  Hint: this account has SEM (Seznam Event Measurement) activated, "
                  "which disables the conversions.* API methods. Manage conversions in "
                  "the Sklik web interface instead.", file=sys.stderr)
        diag = data.get("diagnostics")
        if diag:
            if isinstance(diag, dict):
                # Nested format: {"operation": {...}, "problems": [...]}
                for p in diag.get("problems", []):
                    print(f"  - {p.get('field', '')}: {p.get('problemMessage', p.get('id', ''))}", file=sys.stderr)
            elif isinstance(diag, list):
                for d in diag:
                    if isinstance(d, dict):
                        print(f"  - [{d.get('type')}] {d.get('id')}: {d.get('field', '')}", file=sys.stderr)
                    else:
                        print(f"  - {d}", file=sys.stderr)
        sys.exit(1)

    # Show warnings from 206
    if data.get("status") == 206:
        diag = data.get("diagnostics")
        if isinstance(diag, list):
            for d in diag:
                if isinstance(d, dict) and d.get("type") == "warning":
                    print(f"WARNING: {d.get('id')}: {d.get('field', '')}", file=sys.stderr)

    return data


# ---------------------------------------------------------------------------
# Report helper (two-step: createReport → readReport)
# ---------------------------------------------------------------------------

STAT_COLUMNS = [
    "clicks", "impressions", "ctr", "avgCpc", "avgPos",
    "totalMoney", "conversions", "conversionValue",
    "transactions", "pno",
    "missImpressions", "underLowerThreshold", "exhaustedBudget",
    "ish", "ishContext", "ishSum",
]


def _fetch_report(
    entity: str,
    restriction: dict,
    date_from: str,
    date_to: str,
    display_columns: list[str] | None = None,
    granularity: str = "total",
    limit: int = 5000,
    user_id: int | None = None,
) -> list[dict]:
    """Create and read a report in one step."""
    # Dates go in restrictionFilter, granularity in displayOptions
    restriction_with_dates = dict(restriction)
    restriction_with_dates["dateFrom"] = date_from
    restriction_with_dates["dateTo"] = date_to

    display_opts: dict = {
        "statGranularity": granularity,
    }

    create_data = _api_call(f"{entity}.createReport", [restriction_with_dates, display_opts], user_id)
    report_id = create_data["reportId"]
    total_count = create_data.get("totalCount", 0)

    if total_count == 0:
        return []

    cols = display_columns or ["id", "name"] + STAT_COLUMNS
    read_opts = {
        "offset": 0,
        "limit": min(limit, total_count),
        "allowEmptyStatistics": True,
        "displayColumns": cols,
    }

    read_data = _api_call(f"{entity}.readReport", [report_id, read_opts], user_id)
    return read_data.get("report", [])


# ---------------------------------------------------------------------------
# Price conversion helpers
# ---------------------------------------------------------------------------

def _czk_to_halere(czk: float) -> int:
    """Convert CZK to halere."""
    return int(round(czk * 100))


def _halere_to_czk(halere: int | None) -> float | None:
    """Convert halere to CZK."""
    if halere is None:
        return None
    return halere / 100.0


def _format_money(halere: int | None) -> str:
    """Format halere as CZK string."""
    if halere is None:
        return "—"
    return f"{halere / 100:.2f} Kč"


# ---------------------------------------------------------------------------
# Targeting helpers (campaign regions / device bids / schedule)
# ---------------------------------------------------------------------------

def _parse_regions(value: str | None) -> list[int] | None:
    """Parse a comma-separated list of region IDs (empty string clears them)."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return []  # explicit clear
    try:
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError:
        print("ERROR: --regions must be comma-separated integers (region IDs).", file=sys.stderr)
        sys.exit(1)


def _parse_device_bids(value: str | None) -> dict | None:
    """Parse 'desktop:mobile:tablet:other' percentage modifiers into a struct."""
    if value is None:
        return None
    parts = value.split(":")
    if len(parts) != 4:
        print("ERROR: --device-bids must be 'desktop:mobile:tablet:other' "
              "(e.g. 0:-30:-30:-100).", file=sys.stderr)
        sys.exit(1)
    try:
        desktop, mobile, tablet, other = (float(p) for p in parts)
    except ValueError:
        print("ERROR: --device-bids values must be numbers (percent modifiers).", file=sys.stderr)
        sys.exit(1)
    return {"desktop": desktop, "mobile": mobile, "tablet": tablet, "other": other}


def _format_schedule(schedule: object) -> list[str]:
    """Summarise a campaign schedule (7×24 hourly %) into per-day active windows."""
    if not isinstance(schedule, dict):
        return ["(none — runs all the time)"]
    days = schedule.get("daySchedule", [])
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    lines = []
    for i, day in enumerate(days[:7]):
        hours = day.get("value", []) if isinstance(day, dict) else []
        active = [h for h, v in enumerate(hours) if v and v > 0]
        if not active:
            summary = "off"
        elif len(active) == 24:
            summary = "24h"
        else:
            summary = ", ".join(f"{h}:00" for h in active)
        lines.append(f"  {names[i] if i < 7 else i}: {summary}")
    return lines or ["(none — runs all the time)"]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _get_campaign_type(campaign_id: int, user_id: int | None = None) -> str:
    """Fetch campaign type (needed for campaigns.update with negativeKeywords)."""
    data = _api_call("campaigns.list", [
        {"ids": [campaign_id]},
        {"limit": 1, "offset": 0, "displayColumns": ["id", "type"]},
    ], user_id)
    campaigns = data.get("campaigns", [])
    if campaigns:
        return campaigns[0].get("type", "fulltext")
    return "fulltext"


def _output_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _convert_stats_to_czk(stats: list[dict]) -> list[dict]:
    """Convert money fields in stats from halere to CZK."""
    money_fields = ["avgCpc", "totalMoney", "conversionPrice", "conversionValue",
                    "clickMoney", "impressionMoney"]
    result = []
    for s in stats:
        s2 = dict(s)
        for f in money_fields:
            if f in s2 and s2[f] is not None:
                s2[f] = round(s2[f] / 100, 2)
        result.append(s2)
    return result


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
            "account": ACTIVE_ACCOUNT,
            "limits": limits,
            "batchCallLimits": batch,
            "localUsage": {
                "requestsLastMinute": minute_used,
                "requestsLast24h": day_used,
                "safetyFactor": RATE_LIMIT_SAFETY,
            },
        })
        return

    print(f"=== API limits — account '{ACTIVE_ACCOUNT}' ===")
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


# ---------------------------------------------------------------------------
# Commands — Campaigns
# ---------------------------------------------------------------------------

def cmd_campaigns(args: argparse.Namespace) -> None:
    """List campaigns."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "status", "budget.dayBudget", "type",
            "createDate", "startDate", "endDate"]

    data = _api_call("campaigns.list", [restriction, {
        "limit": 100, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    campaigns = data.get("campaigns", [])

    # Client-side status filter (API doesn't support it in restriction)
    if args.status:
        campaigns = [c for c in campaigns if c.get("status") == args.status]

    if args.json:
        out = []
        for c in campaigns:
            budget = c.get("budget", {}) if isinstance(c.get("budget"), dict) else {}
            out.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "type": c.get("type"),
                "dayBudget": _halere_to_czk(budget.get("dayBudget")),
                "createDate": c.get("createDate"),
                "startDate": c.get("startDate"),
                "endDate": c.get("endDate"),
            })
        _output_json(out)
    else:
        if not campaigns:
            print("No campaigns found.")
            return
        print(f"{'ID':<12} {'Name':<35} {'Status':<10} {'Type':<10} {'Day Budget':<12}")
        print("-" * 85)
        for c in campaigns:
            budget = c.get("budget", {}) if isinstance(c.get("budget"), dict) else {}
            print(f"{c.get('id', ''):<12} {c.get('name', ''):<35} "
                  f"{c.get('status', ''):<10} {c.get('type', ''):<10} "
                  f"{_format_money(budget.get('dayBudget')):<12}")


def cmd_campaign_create(args: argparse.Namespace) -> None:
    """Create a campaign."""
    campaign: dict = {
        "name": args.name,
        "dayBudget": _czk_to_halere(args.day_budget),
        "type": args.type,
    }
    if args.status:
        campaign["status"] = args.status
    regions = _parse_regions(getattr(args, "regions", None))
    if regions is not None:
        campaign["regions"] = regions
    device_bids = _parse_device_bids(getattr(args, "device_bids", None))
    if device_bids is not None:
        campaign["devicesPriceRatio"] = device_bids

    data = _api_call("campaigns.create", [[campaign]], getattr(args, "user_id", None))
    campaign_ids = data.get("campaignIds", [])

    if args.json:
        _output_json({"campaignIds": campaign_ids})
    else:
        print(f"Campaign created: ID {campaign_ids[0] if campaign_ids else '?'}")


def cmd_campaign_update(args: argparse.Namespace) -> None:
    """Update a campaign."""
    # Fetch current campaign to get required 'type' field
    user_id = getattr(args, "user_id", None)
    data = _api_call("campaigns.list", [
        {"isDeleted": False},
        {"limit": 100, "offset": 0, "displayColumns": ["id", "type"]}
    ], user_id)
    campaign_type = None
    for c in data.get("campaigns", []):
        if c.get("id") == args.campaign_id:
            campaign_type = c.get("type")
            break
    if not campaign_type:
        print(f"ERROR: Campaign {args.campaign_id} not found.", file=sys.stderr)
        sys.exit(1)

    update: dict = {"id": args.campaign_id, "type": campaign_type}
    if args.name:
        update["name"] = args.name
    if args.day_budget is not None:
        update["dayBudget"] = _czk_to_halere(args.day_budget)
    if args.status:
        update["status"] = args.status
    regions = _parse_regions(getattr(args, "regions", None))
    if regions is not None:
        update["regions"] = regions
    device_bids = _parse_device_bids(getattr(args, "device_bids", None))
    if device_bids is not None:
        update["devicesPriceRatio"] = device_bids
    if getattr(args, "schedule_json", None):
        try:
            update["schedule"] = json.loads(args.schedule_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid --schedule-json: {e}", file=sys.stderr)
            sys.exit(1)

    if len(update) == 2:  # only id + type, no actual changes
        print("ERROR: No fields to update.", file=sys.stderr)
        sys.exit(1)

    data = _api_call("campaigns.update", [[update]], user_id)
    if args.json:
        _output_json({"updated": True, "campaignId": args.campaign_id})
    else:
        print(f"Campaign {args.campaign_id} updated.")


def cmd_campaign_remove(args: argparse.Namespace) -> None:
    """Remove a campaign."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("campaigns.remove", [[args.campaign_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "campaignId": args.campaign_id})
    else:
        print(f"Campaign {args.campaign_id} removed.")


def cmd_campaign_stats(args: argparse.Namespace) -> None:
    """Show campaign statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}
    if args.campaign_id:
        restriction["ids"] = [args.campaign_id]

    cols = ["id", "name"] + STAT_COLUMNS
    report = _fetch_report("campaigns", restriction, date_from, date_to,
                           cols, user_id=getattr(args, "user_id", None))

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No data.")
            return
        print(f"Campaign stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  {r.get('name', '?')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {s.get('ctr', 0):.2f}%  Avg CPC: {_format_money(s.get('avgCpc'))}  "
                      f"Cost: {_format_money(s.get('totalMoney'))}  "
                      f"Conv: {s.get('conversions', 0)}")


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

    # Per-campaign rows (money stays in haléře until display); accumulate totals.
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
            "convValue_czk": val / 100,
            "pno": (cost / val * 100) if val else None,
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
        "convValue_czk": tot["conversionValue"] / 100,
        "pno": (tot["totalMoney"] / tot["conversionValue"] * 100) if tot["conversionValue"] else None,
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

    if args.json:
        _output_json({
            "account": args.account,
            "period": {"from": date_from, "to": date_to, "days": window},
            "comparePeriod": ({"from": prev_from, "to": prev_to} if compare else None),
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


def cmd_campaign_targeting(args: argparse.Namespace) -> None:
    """Show geo / device / schedule targeting for a campaign."""
    cols = ["id", "name", "regions.id", "regions.name",
            "devicesPriceRatio", "schedule"]
    data = _api_call("campaigns.list", [
        {"ids": [args.campaign_id]},
        {"limit": 1, "offset": 0, "displayColumns": cols},
    ], getattr(args, "user_id", None))
    campaigns = data.get("campaigns", [])
    if not campaigns:
        print(f"ERROR: Campaign {args.campaign_id} not found.", file=sys.stderr)
        sys.exit(1)
    c = campaigns[0]
    regions = c.get("regions", []) or []
    devices = c.get("devicesPriceRatio", {}) or {}
    schedule = c.get("schedule")

    if args.json:
        _output_json({
            "id": c.get("id"),
            "name": c.get("name"),
            "regions": regions,
            "devicesPriceRatio": devices,
            "schedule": schedule,
        })
    else:
        print(f"Targeting for: {c.get('name', '?')} (ID: {c.get('id')})\n")
        print("Regions (geo):")
        if regions:
            for r in regions:
                print(f"  {r.get('id')}: {r.get('name', '?')}")
        else:
            print("  (all regions)")
        print("\nDevice bid modifiers (%):")
        if devices:
            print(f"  desktop: {devices.get('desktop', 0)}  mobile: {devices.get('mobile', 0)}  "
                  f"tablet: {devices.get('tablet', 0)}  other: {devices.get('other', 0)}")
        else:
            print("  (none)")
        print("\nSchedule (active hours per day):")
        for line in _format_schedule(schedule):
            print(line)


# ---------------------------------------------------------------------------
# Commands — Groups (ad groups)
# ---------------------------------------------------------------------------

def cmd_groups(args: argparse.Namespace) -> None:
    """List ad groups."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "maxCpc", "status", "campaign.id", "campaign.name"]

    data = _api_call("groups.list", [restriction, {
        "limit": 500, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    groups = data.get("groups", [])

    # Client-side campaign filter
    if args.campaign_id:
        groups = [g for g in groups
                  if (g.get("campaign", {}).get("id") if isinstance(g.get("campaign"), dict) else g.get("campaign.id")) == args.campaign_id]

    if args.json:
        out = []
        for g in groups:
            out.append({
                "id": g.get("id"),
                "name": g.get("name"),
                "status": g.get("status"),
                "maxCpc": _halere_to_czk(g.get("maxCpc")),
                "campaignId": g.get("campaign", {}).get("id") if isinstance(g.get("campaign"), dict) else g.get("campaign.id"),
                "campaignName": g.get("campaign", {}).get("name") if isinstance(g.get("campaign"), dict) else g.get("campaign.name"),
            })
        _output_json(out)
    else:
        if not groups:
            print("No groups found.")
            return
        print(f"{'ID':<12} {'Name':<30} {'Status':<10} {'Max CPC':<12} {'Campaign'}")
        print("-" * 90)
        for g in groups:
            c_name = g.get("campaign", {}).get("name", "?") if isinstance(g.get("campaign"), dict) else g.get("campaign.name", "?")
            print(f"{g.get('id', ''):<12} {g.get('name', ''):<30} "
                  f"{g.get('status', ''):<10} {_format_money(g.get('maxCpc')):<12} {c_name}")


def cmd_group_create(args: argparse.Namespace) -> None:
    """Create an ad group."""
    group: dict = {
        "campaignId": args.campaign_id,
        "name": args.name,
        "cpc": _czk_to_halere(args.cpc),
    }

    data = _api_call("groups.create", [[group]], getattr(args, "user_id", None))
    group_ids = data.get("groupIds", [])

    if args.json:
        _output_json({"groupIds": group_ids})
    else:
        print(f"Group created: ID {group_ids[0] if group_ids else '?'}")


def cmd_group_update(args: argparse.Namespace) -> None:
    """Update an ad group."""
    update: dict = {"id": args.group_id}
    if args.name:
        update["name"] = args.name
    if args.cpc is not None:
        update["cpc"] = _czk_to_halere(args.cpc)
    if args.status:
        update["status"] = args.status

    if len(update) == 1:
        print("ERROR: No fields to update.", file=sys.stderr)
        sys.exit(1)

    _api_call("groups.update", [[update]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "groupId": args.group_id})
    else:
        print(f"Group {args.group_id} updated.")


def cmd_group_remove(args: argparse.Namespace) -> None:
    """Remove an ad group."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("groups.remove", [[args.group_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "groupId": args.group_id})
    else:
        print(f"Group {args.group_id} removed.")


def cmd_group_stats(args: argparse.Namespace) -> None:
    """Show group statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}
    if args.group_id:
        restriction["ids"] = [args.group_id]

    cols = ["id", "name", "campaign.id", "campaign.name"] + STAT_COLUMNS
    report = _fetch_report("groups", restriction, date_from, date_to,
                           cols, user_id=getattr(args, "user_id", None))

    # Client-side campaign filter (API doesn't support campaign.ids in report restriction)
    if args.campaign_id:
        report = [r for r in report
                  if (r.get("campaign", {}).get("id") if isinstance(r.get("campaign"), dict) else r.get("campaign.id")) == args.campaign_id]

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No data.")
            return
        print(f"Group stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  {r.get('name', '?')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {s.get('ctr', 0):.2f}%  Avg CPC: {_format_money(s.get('avgCpc'))}  "
                      f"Cost: {_format_money(s.get('totalMoney'))}  "
                      f"Conv: {s.get('conversions', 0)}")


# ---------------------------------------------------------------------------
# Commands — Keywords
# ---------------------------------------------------------------------------

def cmd_keywords(args: argparse.Namespace) -> None:
    """List keywords."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "cpc", "matchType", "status", "url",
            "group.id", "group.name", "campaign.id"]

    data = _api_call("keywords.list", [restriction, {
        "limit": 5000, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    keywords = data.get("keywords", [])

    # Client-side group/campaign filter
    if args.group_id:
        keywords = [k for k in keywords
                    if (k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id")) == args.group_id]
    if args.campaign_id:
        keywords = [k for k in keywords
                    if (k.get("campaign", {}).get("id") if isinstance(k.get("campaign"), dict) else k.get("campaign.id")) == args.campaign_id]

    if args.json:
        out = []
        for k in keywords:
            out.append({
                "id": k.get("id"),
                "name": k.get("name"),
                "matchType": k.get("matchType"),
                "status": k.get("status"),
                "cpc": _halere_to_czk(k.get("cpc")),
                "url": k.get("url"),
                "groupId": k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id"),
                "groupName": k.get("group", {}).get("name") if isinstance(k.get("group"), dict) else k.get("group.name"),
            })
        _output_json(out)
    else:
        if not keywords:
            print("No keywords found.")
            return
        print(f"{'ID':<12} {'Keyword':<30} {'Match':<10} {'Status':<10} {'CPC':<10} {'Group'}")
        print("-" * 95)
        for k in keywords:
            g_name = k.get("group", {}).get("name", "") if isinstance(k.get("group"), dict) else k.get("group.name", "")
            cpc = k.get("cpc")
            cpc_str = _format_money(cpc) if cpc else "group"
            print(f"{k.get('id', ''):<12} {k.get('name', ''):<30} "
                  f"{k.get('matchType', ''):<10} {k.get('status', ''):<10} "
                  f"{cpc_str:<10} {g_name}")


def cmd_keyword_create(args: argparse.Namespace) -> None:
    """Create a keyword."""
    kw: dict = {
        "name": args.name,
        "groupId": args.group_id,
        "matchType": args.match_type,
    }
    if args.cpc is not None:
        kw["cpc"] = _czk_to_halere(args.cpc)
    if args.url:
        kw["url"] = args.url

    data = _api_call("keywords.create", [[kw]], getattr(args, "user_id", None))
    kw_ids = data.get("positiveKeywordIds", [])

    if args.json:
        _output_json({"keywordIds": kw_ids})
    else:
        print(f"Keyword created: ID {kw_ids[0] if kw_ids else '?'}")


def cmd_keyword_create_batch(args: argparse.Namespace) -> None:
    """Batch create keywords from JSON array."""
    try:
        keywords_data = json.loads(args.keywords_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    batch = []
    for kw in keywords_data:
        item: dict = {
            "name": kw["name"],
            "groupId": args.group_id,
            "matchType": kw.get("matchType", "broad"),
        }
        if "cpc" in kw and kw["cpc"] is not None:
            item["cpc"] = _czk_to_halere(kw["cpc"])
        if "url" in kw:
            item["url"] = kw["url"]
        batch.append(item)

    data = _api_call("keywords.create", [batch], getattr(args, "user_id", None))
    kw_ids = data.get("positiveKeywordIds", [])

    if args.json:
        _output_json({"keywordIds": kw_ids, "count": len(kw_ids)})
    else:
        print(f"Created {len(kw_ids)} keywords: {kw_ids}")


def cmd_keyword_update(args: argparse.Namespace) -> None:
    """Update a keyword."""
    update: dict = {"id": args.keyword_id}
    if args.cpc is not None:
        update["cpc"] = _czk_to_halere(args.cpc)
    if args.status:
        update["status"] = args.status
    if args.url:
        update["url"] = args.url

    if len(update) == 1:
        print("ERROR: No fields to update. Use --cpc, --status, or --url.", file=sys.stderr)
        sys.exit(1)

    _api_call("keywords.update", [[update]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "keywordId": args.keyword_id})
    else:
        print(f"Keyword {args.keyword_id} updated.")


def cmd_keyword_remove(args: argparse.Namespace) -> None:
    """Remove a keyword."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("keywords.remove", [[args.keyword_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "keywordId": args.keyword_id})
    else:
        print(f"Keyword {args.keyword_id} removed.")


def cmd_keyword_stats(args: argparse.Namespace) -> None:
    """Show keyword statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}

    cols = ["id", "name", "matchType", "group.id", "group.name", "campaign.id"] + STAT_COLUMNS
    report = _fetch_report("keywords", restriction, date_from, date_to,
                           cols, user_id=getattr(args, "user_id", None))

    # Client-side group/campaign filter
    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]
    if args.campaign_id:
        report = [r for r in report
                  if (r.get("campaign", {}).get("id") if isinstance(r.get("campaign"), dict) else r.get("campaign.id")) == args.campaign_id]

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No data.")
            return
        print(f"Keyword stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  [{r.get('matchType', '?')}] {r.get('name', '?')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {s.get('ctr', 0):.2f}%  Avg CPC: {_format_money(s.get('avgCpc'))}  "
                      f"Cost: {_format_money(s.get('totalMoney'))}  "
                      f"Conv: {s.get('conversions', 0)}")


# ---------------------------------------------------------------------------
# Commands — Ads
# ---------------------------------------------------------------------------

def cmd_ads(args: argparse.Namespace) -> None:
    """List ads."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "adType", "headline1", "headline2", "headline3",
            "description", "description2", "finalUrl", "path1", "path2",
            "shortLine", "longLine", "companyName",
            "status", "group.id", "group.name"]

    data = _api_call("ads.list", [restriction, {
        "limit": 500, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    ads = data.get("ads", [])

    # Client-side group filter
    if args.group_id:
        ads = [a for a in ads
               if (a.get("group", {}).get("id") if isinstance(a.get("group"), dict) else a.get("group.id")) == args.group_id]

    if args.json:
        out = []
        for a in ads:
            item = {
                "id": a.get("id"),
                "adType": a.get("adType"),
                "status": a.get("status"),
                "headline1": a.get("headline1"),
                "headline2": a.get("headline2"),
                "headline3": a.get("headline3"),
                "description": a.get("description"),
                "description2": a.get("description2"),
                "finalUrl": a.get("finalUrl"),
                "path1": a.get("path1"),
                "path2": a.get("path2"),
                "groupId": a.get("group", {}).get("id") if isinstance(a.get("group"), dict) else a.get("group.id"),
            }
            if a.get("adType") == "combined":
                item.update({
                    "shortLine": a.get("shortLine"),
                    "longLine": a.get("longLine"),
                    "companyName": a.get("companyName"),
                })
            out.append(item)
        _output_json(out)
    else:
        if not ads:
            print("No ads found.")
            return
        for a in ads:
            print(f"ID: {a.get('id')}  Type: {a.get('adType')}  Status: {a.get('status')}")
            if a.get("adType") == "combined":
                print(f"  Short: {a.get('shortLine', '')}  |  Long: {a.get('longLine', '')}")
                print(f"  Desc: {a.get('description', '')}  |  Brand: {a.get('companyName', '')}")
                print(f"  URL: {a.get('finalUrl', '')}")
            else:
                print(f"  H1: {a.get('headline1', '')}  |  H2: {a.get('headline2', '')}  |  H3: {a.get('headline3', '')}")
                print(f"  D1: {a.get('description', '')}")
                print(f"  D2: {a.get('description2', '')}")
                print(f"  URL: {a.get('finalUrl', '')}  Path: /{a.get('path1', '')}/{a.get('path2', '')}")
            print()


def cmd_ad_create(args: argparse.Namespace) -> None:
    """Create an ETA ad."""
    ad: dict = {
        "groupId": args.group_id,
        "adType": "eta",
        "headline1": args.headline1,
        "headline2": args.headline2,
        "description": args.description1,
        "finalUrl": args.final_url,
    }
    if args.headline3:
        ad["headline3"] = args.headline3
    if args.description2:
        ad["description2"] = args.description2
    if args.path1:
        ad["path1"] = args.path1
    if args.path2:
        ad["path2"] = args.path2

    data = _api_call("ads.create", [[ad]], getattr(args, "user_id", None))
    ad_ids = data.get("adIds", [])

    if args.json:
        _output_json({"adIds": ad_ids})
    else:
        print(f"Ad created: ID {ad_ids[0] if ad_ids else '?'}")


def cmd_combined_create(args: argparse.Namespace) -> None:
    """Create a combined (native) ad for the display network.

    Sklik composes the final look from the texts and images — including the
    native in-article format. Landscape image (1.91:1, min 600×314) and square
    image (1:1, min 300×300) are both required by the API.
    """
    ad: dict = {
        "groupId": args.group_id,
        "adType": "combined",
        "shortLine": args.short_line,
        "longLine": args.long_line,
        "description": args.description,
        "companyName": args.company_name,
        "finalUrl": args.final_url,
        "image": _load_image_b64(args.image_landscape),
        "imageSquare": _load_image_b64(args.image_square),
    }
    if args.image_logo:
        ad["imageLogo"] = _load_image_b64(args.image_logo)
    if args.image_landscape_logo:
        ad["imageLandscapeLogo"] = _load_image_b64(args.image_landscape_logo)
    if args.color_main:
        ad["colorMain"] = args.color_main.lstrip("#")
    if args.color_accent:
        ad["colorAccent"] = args.color_accent.lstrip("#")
    if args.mobile_final_url:
        ad["mobileFinalUrl"] = args.mobile_final_url
    if args.tracking_template:
        ad["trackingTemplate"] = args.tracking_template
    if args.status:
        ad["status"] = args.status

    data = _api_call("ads.create", [[ad]], getattr(args, "user_id", None))
    ad_ids = data.get("adIds", [])

    if args.json:
        _output_json({"adIds": ad_ids})
    else:
        print(f"Combined ad created: ID {ad_ids[0] if ad_ids else '?'}")


def cmd_ad_update(args: argparse.Namespace) -> None:
    """Update an ad."""
    update: dict = {"id": args.ad_id}
    if args.status:
        update["status"] = args.status

    if len(update) == 1:
        print("ERROR: No fields to update.", file=sys.stderr)
        sys.exit(1)

    data = _api_call("ads.update", [[update]], getattr(args, "user_id", None))
    new_ids = data.get("newAdIds", [])
    if args.json:
        _output_json({"updated": True, "adId": args.ad_id, "newAdIds": new_ids})
    else:
        if new_ids:
            print(f"Ad {args.ad_id} updated → new ID: {new_ids[0]}")
        else:
            print(f"Ad {args.ad_id} updated.")


def cmd_ad_remove(args: argparse.Namespace) -> None:
    """Remove an ad."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("ads.remove", [[args.ad_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "adId": args.ad_id})
    else:
        print(f"Ad {args.ad_id} removed.")


def cmd_ad_stats(args: argparse.Namespace) -> None:
    """Show ad statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}

    cols = ["id", "adType", "headline1", "headline2", "status", "group.id"] + STAT_COLUMNS
    report = _fetch_report("ads", restriction, date_from, date_to,
                           cols, user_id=getattr(args, "user_id", None))

    # Client-side group filter
    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No data.")
            return
        print(f"Ad stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  {r.get('headline1', '')} | {r.get('headline2', '')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {s.get('ctr', 0):.2f}%  Cost: {_format_money(s.get('totalMoney'))}")


# ---------------------------------------------------------------------------
# Commands — Negative keywords
# ---------------------------------------------------------------------------

def cmd_negatives(args: argparse.Namespace) -> None:
    """List negative keywords."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "name", "matchType", "group.id", "group.name"]

    data = _api_call("keywords.negative.list", [restriction, {
        "limit": 5000, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))

    keywords = data.get("keywords", [])

    # Client-side group/campaign filter
    if args.group_id:
        keywords = [k for k in keywords
                    if (k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id")) == args.group_id]

    if args.json:
        out = []
        for k in keywords:
            out.append({
                "id": k.get("id"),
                "name": k.get("name"),
                "matchType": k.get("matchType"),
                "groupId": k.get("group", {}).get("id") if isinstance(k.get("group"), dict) else k.get("group.id"),
            })
        _output_json(out)
    else:
        if not keywords:
            print("No negative keywords found.")
            return
        print(f"{'ID':<12} {'Keyword':<30} {'Match Type':<20} {'Group'}")
        print("-" * 75)
        for k in keywords:
            g_name = k.get("group", {}).get("name", "") if isinstance(k.get("group"), dict) else k.get("group.name", "")
            print(f"{k.get('id', ''):<12} {k.get('name', ''):<30} "
                  f"{k.get('matchType', ''):<20} {g_name}")


def cmd_negative_add(args: argparse.Namespace) -> None:
    """Add a negative keyword (group-level or campaign-level)."""
    # Campaign-level negatives go through campaigns.update (requires type field)
    if args.campaign_id and not args.group_id:
        camp_type = _get_campaign_type(args.campaign_id, getattr(args, "user_id", None))
        neg = {"name": args.name, "matchType": args.match_type}
        data = _api_call("campaigns.update", [[{
            "id": args.campaign_id,
            "type": camp_type,
            "negativeKeywords": [neg],
        }]], getattr(args, "user_id", None))
        if args.json:
            _output_json({"campaignId": args.campaign_id, "added": 1, "level": "campaign"})
        else:
            print(f"Campaign-level negative added to campaign {args.campaign_id}.")
        return

    if not args.group_id:
        print("ERROR: --group-id or --campaign-id is required.", file=sys.stderr)
        sys.exit(1)

    neg: dict = {
        "name": args.name,
        "matchType": args.match_type,
        "groupId": args.group_id,
    }

    data = _api_call("keywords.negative.create", [[neg]], getattr(args, "user_id", None))
    neg_ids = data.get("negativeKeywordIds", [])

    if args.json:
        _output_json({"negativeKeywordIds": neg_ids})
    else:
        print(f"Negative keyword added: ID {neg_ids[0] if neg_ids else '?'}")


def cmd_negative_add_batch(args: argparse.Namespace) -> None:
    """Batch add negative keywords (group-level or campaign-level)."""
    try:
        keywords_data = json.loads(args.keywords_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    negs = []
    for kw in keywords_data:
        negs.append({
            "name": kw["name"] if isinstance(kw, dict) else kw,
            "matchType": kw.get("matchType", "negativeBroad") if isinstance(kw, dict) else "negativeBroad",
        })

    # Campaign-level negatives go through campaigns.update (requires type field)
    if args.campaign_id and not args.group_id:
        camp_type = _get_campaign_type(args.campaign_id, getattr(args, "user_id", None))
        data = _api_call("campaigns.update", [[{
            "id": args.campaign_id,
            "type": camp_type,
            "negativeKeywords": negs,
        }]], getattr(args, "user_id", None))
        if args.json:
            _output_json({"campaignId": args.campaign_id, "added": len(negs), "level": "campaign"})
        else:
            print(f"Added {len(negs)} campaign-level negatives to campaign {args.campaign_id}.")
        return

    if not args.group_id:
        print("ERROR: --group-id or --campaign-id is required.", file=sys.stderr)
        sys.exit(1)

    # Group-level negatives via keywords.negative.create
    batch = []
    for neg in negs:
        neg["groupId"] = args.group_id
        batch.append(neg)

    data = _api_call("keywords.negative.create", [batch], getattr(args, "user_id", None))
    neg_ids = data.get("negativeKeywordIds", [])

    if args.json:
        _output_json({"negativeKeywordIds": neg_ids, "count": len(neg_ids)})
    else:
        print(f"Added {len(neg_ids)} group-level negative keywords.")


def cmd_negative_remove(args: argparse.Namespace) -> None:
    """Remove a negative keyword."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("keywords.negative.remove", [[args.keyword_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "keywordId": args.keyword_id})
    else:
        print(f"Negative keyword {args.keyword_id} removed.")


# ---------------------------------------------------------------------------
# Commands — Keyword Research
# ---------------------------------------------------------------------------

def cmd_suggest(args: argparse.Namespace) -> None:
    """Get keyword suggestions."""
    opts: dict = {
        "offset": 0,
        "limit": args.limit,
        "related": args.related,
        "orderBy": args.order_by,
        "orderDirection": "desc",
    }

    # suggest doesn't support managed accounts (userId)
    data = _api_call("keywords.suggest", [args.query, opts])
    suggestions = data.get("suggestions", [])

    if args.json:
        out = []
        for s in suggestions:
            out.append({
                "query": s.get("query"),
                "avgSearchCount": s.get("avgSearchCount"),
                "cpc": _halere_to_czk(s.get("cpc")),
            })
        _output_json(out)
    else:
        if not suggestions:
            print("No suggestions found.")
            return
        print(f"{'Keyword':<40} {'Avg Searches':<15} {'CPC'}")
        print("-" * 65)
        for s in suggestions:
            print(f"{s.get('query', ''):<40} {s.get('avgSearchCount', 0):<15} "
                  f"{_format_money(s.get('cpc'))}")
        print(f"\nTotal: {data.get('total', len(suggestions))} suggestions")


def cmd_suggest_stats(args: argparse.Namespace) -> None:
    """Get search volume stats for keywords."""
    queries = [q.strip() for q in args.queries.split(",")]
    opts: dict = {"granularity": args.granularity}

    # suggest.stats doesn't support managed accounts (userId)
    data = _api_call("keywords.suggest.stats", [queries, opts])
    stats = data.get("stats", [])

    if args.json:
        out = []
        for s in stats:
            out.append({
                "query": s.get("query"),
                "avgSearchCount": s.get("avgSearchCount"),
                "avgCpc": _halere_to_czk(s.get("avgCpc")),
                "searchCountInTime": s.get("searchCountInTime", []),
            })
        _output_json(out)
    else:
        if not stats:
            print("No stats found.")
            return
        for s in stats:
            print(f"\n{s.get('query', '?')}:")
            print(f"  Avg searches: {s.get('avgSearchCount', 0)}  Avg CPC: {_format_money(s.get('avgCpc'))}")
            timeline = s.get("searchCountInTime", [])
            if timeline:
                print(f"  Timeline:")
                for t in timeline[-12:]:  # Last 12 periods
                    print(f"    {t.get('timePeriod', '?')}: {t.get('searchCount', 0)}")


# ---------------------------------------------------------------------------
# Commands — Search queries
# ---------------------------------------------------------------------------

def cmd_search_queries(args: argparse.Namespace) -> None:
    """Show search query report."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    restriction: dict = {}

    cols = ["query", "clicks", "impressions", "avgCpc", "totalMoney",
            "conversions", "conversionValue", "keyword.id", "keyword.name", "keyword.matchType",
            "group.id", "group.name", "campaign.id"]
    report = _fetch_report("queries", restriction, date_from, date_to,
                           cols, limit=args.limit,
                           user_id=getattr(args, "user_id", None))

    # Client-side campaign/group filter
    if args.campaign_id:
        report = [r for r in report
                  if (r.get("campaign", {}).get("id") if isinstance(r.get("campaign"), dict) else r.get("campaign.id")) == args.campaign_id]
    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No search queries found.")
            return
        print(f"Search queries ({date_from} — {date_to}):\n")
        print(f"{'Query':<40} {'Clicks':<8} {'Impr':<8} {'CTR':<8} {'Cost'}")
        print("-" * 80)
        for r in report:
            query = r.get("query", "?")
            if len(query) > 38:
                query = query[:36] + ".."
            stats = r.get("stats", [{}])
            s = stats[0] if stats else {}
            print(f"{query:<40} {s.get('clicks', 0):<8} {s.get('impressions', 0):<8} "
                  f"{s.get('ctr', 0):.1f}%{'':<3} {_format_money(s.get('totalMoney'))}")


# ---------------------------------------------------------------------------
# Commands — Sitelinks
# ---------------------------------------------------------------------------

def cmd_sitelinks(args: argparse.Namespace) -> None:
    """List sitelinks."""
    data = _api_call("sitelinks.list", [], getattr(args, "user_id", None))
    sitelinks = data.get("sitelinks", [])

    if args.json:
        out = []
        for s in sitelinks:
            out.append({
                "id": s.get("id"),
                "name": s.get("name"),
                "url": s.get("url"),
                "status": s.get("status"),
            })
        _output_json(out)
    else:
        if not sitelinks:
            print("No sitelinks found.")
            return
        print(f"{'ID':<12} {'Name':<30} {'URL':<40} {'Status'}")
        print("-" * 95)
        for s in sitelinks:
            print(f"{s.get('id', ''):<12} {s.get('name', ''):<30} "
                  f"{s.get('url', ''):<40} {s.get('status', '')}")


def cmd_sitelink_create(args: argparse.Namespace) -> None:
    """Create a sitelink."""
    sitelink: dict = {
        "name": args.name,
        "url": args.url,
    }

    data = _api_call("sitelinks.create", [[sitelink]], getattr(args, "user_id", None))
    ids = data.get("ids", [])

    if args.json:
        _output_json({"sitelinkIds": ids})
    else:
        print(f"Sitelink created: ID {ids[0] if ids else '?'}")


def cmd_sitelink_remove(args: argparse.Namespace) -> None:
    """Remove a sitelink."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("sitelinks.remove", [[args.sitelink_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "sitelinkId": args.sitelink_id})
    else:
        print(f"Sitelink {args.sitelink_id} removed.")


# ---------------------------------------------------------------------------
# Commands — Conversions (conversion tracking definitions)
# ---------------------------------------------------------------------------
# A "conversion" here is a DEFINITION of a desired action (purchase, signup, …)
# and its value — not the measurement itself. The CLI manages these definitions.
# Note: accounts with SEM (Seznam Event Measurement) activated cannot use the
# conversions.* methods; we surface a friendly message instead of a stacktrace.

def _is_sem_blocked(data: dict) -> bool:
    """Heuristic: detect the SEM-activated restriction on conversions.* methods."""
    msg = (data.get("statusMessage") or "").lower()
    if "event measurement" in msg or "měření událostí" in msg:
        return True
    # Match SEM as a standalone word, not a substring (e.g. "assessment").
    return bool(re.search(r"\bsem\b", msg))


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
# Commands — Image banners (context/display network)
# ---------------------------------------------------------------------------
# banners.create takes the image bytes directly in `file` (base64 over JSON),
# so the CLI accepts either a local path or a public URL and encodes it. Allowed
# formats/sizes come from images.constraints.list (e.g. 300×300, 728×90; ≤250 KB).

def _load_image_b64(src: str) -> str:
    """Read an image from a local path or http(s) URL and return base64 bytes."""
    try:
        if src.startswith(("http://", "https://")):
            resp = requests.get(src, timeout=30)
            resp.raise_for_status()
            raw = resp.content
        else:
            with open(src, "rb") as f:
                raw = f.read()
    except (OSError, requests.RequestException) as e:
        print(f"ERROR: Could not load image '{src}': {e}", file=sys.stderr)
        sys.exit(1)
    return base64.b64encode(raw).decode("ascii")


def cmd_banner_formats(args: argparse.Namespace) -> None:
    """List allowed banner formats (dimensions + size limits)."""
    data = _api_call("images.constraints.list", [], getattr(args, "user_id", None))
    # Structure: {"banner": {"banner": [ {minWidth,maxWidth,...,maxSize,ruleName}, ... ]}}
    rules = []
    constraints = data.get("constraints") or data
    banner = constraints.get("banner", {}) if isinstance(constraints, dict) else {}
    rules = banner.get("banner", []) if isinstance(banner, dict) else []

    if args.json:
        _output_json(rules)
    else:
        if not rules:
            print("No banner format constraints returned.")
            return
        print(f"{'Format':<16} {'Max size':<12} {'External ad'}")
        print("-" * 45)
        for r in rules:
            w = r.get("recommendedWidth") or r.get("maxWidth")
            h = r.get("recommendedHeight") or r.get("maxHeight")
            dims = f"{w}×{h}" if w and h else (r.get("ruleName") or "?")
            size = r.get("maxSize")
            size_str = f"{size // 1024} KB" if size else "—"
            print(f"{dims:<16} {size_str:<12} {r.get('externalAdSupport', False)}")


def cmd_banners(args: argparse.Namespace) -> None:
    """List image banners."""
    cols = ["id", "bannerName", "adStatus", "clickthruUrl",
            "height", "group.id", "group.name"]
    data = _api_call("banners.list", [{"isDeleted": False}, {
        "limit": 500, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))
    banners = data.get("banners", [])

    # Client-side group filter
    if args.group_id:
        banners = [b for b in banners
                   if (b.get("group", {}).get("id") if isinstance(b.get("group"), dict) else b.get("group.id")) == args.group_id]

    if args.json:
        out = [{
            "id": b.get("id"),
            "name": b.get("bannerName"),
            "status": b.get("adStatus"),
            "clickthruUrl": b.get("clickthruUrl"),
            "groupId": b.get("group", {}).get("id") if isinstance(b.get("group"), dict) else b.get("group.id"),
            "groupName": b.get("group", {}).get("name") if isinstance(b.get("group"), dict) else b.get("group.name"),
        } for b in banners]
        _output_json(out)
    else:
        if not banners:
            print("No banners found.")
            return
        print(f"{'ID':<12} {'Name':<35} {'Status':<10} {'Group'}")
        print("-" * 80)
        for b in banners:
            g_name = b.get("group", {}).get("name", "") if isinstance(b.get("group"), dict) else b.get("group.name", "")
            print(f"{b.get('id', ''):<12} {(b.get('bannerName') or ''):<35} "
                  f"{(b.get('adStatus') or ''):<10} {g_name}")


def cmd_banner_create(args: argparse.Namespace) -> None:
    """Create an image banner (image from local path or URL)."""
    banner: dict = {
        "groupId": args.group_id,
        "name": args.name,
        "clickthruUrl": args.clickthru_url,
        "file": _load_image_b64(args.image),
    }
    if args.status:
        banner["status"] = args.status

    data = _api_call("banners.create", [[banner]], getattr(args, "user_id", None))
    # banners.create returns bannerIds as [{"id": ..., "requestId": ...}]; normalise to ints.
    raw_ids = data.get("bannerIds") or data.get("ids") or []
    ids = [i.get("id") if isinstance(i, dict) else i for i in raw_ids]

    if args.json:
        _output_json({"bannerIds": ids})
    else:
        print(f"Banner created: ID {ids[0] if ids else '?'}")


def cmd_banner_remove(args: argparse.Namespace) -> None:
    """Remove an image banner."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("banners.remove", [[args.banner_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "bannerId": args.banner_id})
    else:
        print(f"Banner {args.banner_id} removed.")


# ---------------------------------------------------------------------------
# Commands — Placements (content network "umístění" = patterns.* namespace)
# ---------------------------------------------------------------------------
# Placement targeting of display groups lives in the patterns.* namespace:
# a pattern is a URL string like "forbes.cz" or "www.e15.cz/byznys" attached
# to a group. There is no patterns.list — listing goes through the report API.

def cmd_placements(args: argparse.Namespace) -> None:
    """List placement patterns (content network targeting)."""
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    report = _fetch_report(
        "patterns", {}, date_from, date_to,
        ["id", "pattern", "status", "cpc", "group.id", "group.name"],
        user_id=getattr(args, "user_id", None))

    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    if args.json:
        out = [{
            "id": r.get("id"),
            "pattern": r.get("pattern"),
            "status": r.get("status"),
            "cpc": _halere_to_czk(r.get("cpc")),
            "groupId": r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id"),
            "groupName": r.get("group", {}).get("name") if isinstance(r.get("group"), dict) else r.get("group.name"),
        } for r in report]
        _output_json(out)
    else:
        if not report:
            print("No placements found.")
            return
        print(f"{'ID':<12} {'Pattern':<35} {'Status':<10} {'Group'}")
        print("-" * 80)
        for r in report:
            g_name = r.get("group", {}).get("name", "") if isinstance(r.get("group"), dict) else r.get("group.name", "")
            print(f"{r.get('id', ''):<12} {(r.get('pattern') or ''):<35} "
                  f"{(r.get('status') or ''):<10} {g_name}")


def cmd_placement_create(args: argparse.Namespace) -> None:
    """Add a placement pattern (target website) to a display group."""
    pattern: dict = {
        "groupId": args.group_id,
        "pattern": args.pattern,
    }
    if args.cpc is not None:
        pattern["cpc"] = _czk_to_halere(args.cpc)
    if args.status:
        pattern["status"] = args.status

    data = _api_call("patterns.create", [[pattern]], getattr(args, "user_id", None))
    raw_ids = data.get("ids") or data.get("patternIds") or []
    ids = [i.get("id") if isinstance(i, dict) else i for i in raw_ids]

    if args.json:
        _output_json({"patternIds": ids})
    else:
        print(f"Placement created: ID {ids[0] if ids else '?'}")


def cmd_placement_remove(args: argparse.Namespace) -> None:
    """Remove a placement pattern."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("patterns.remove", [[args.pattern_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "patternId": args.pattern_id})
    else:
        print(f"Placement {args.pattern_id} removed.")


# ---------------------------------------------------------------------------
# CLI setup
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sklik DRAK CLI — manage PPC search campaigns.",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--account",
        default=DEFAULT_ACCOUNT,
        metavar="NAME",
        help="Sklik login to use: 'default' uses SKLIK_API_TOKEN, '<name>' uses "
             f"SKLIK_API_TOKEN_<NAME>. Default: {DEFAULT_ACCOUNT}",
    )
    parser.add_argument("--user-id", type=int, default=None, help="Managed account user ID")
    subparsers = parser.add_subparsers(dest="command", required=True)

    json_kwargs: dict = {"action": "store_true", "help": "Output as JSON"}

    # --- account ---
    p = subparsers.add_parser("account", help="Account info")
    p.add_argument("--json", **json_kwargs)

    # --- api-limits ---
    p = subparsers.add_parser(
        "api-limits",
        help="Show account API limits (rate/batch/value ranges) + local request-budget usage",
    )
    p.add_argument("--json", **json_kwargs)

    # --- pulse (account-wide compact digest) ---
    p = subparsers.add_parser(
        "pulse",
        help="Account-wide PPC pulse: one compact digest (totals + per-campaign + deltas)",
    )
    p.add_argument("--days", type=int, default=7, help="Window length in days (default 7)")
    p.add_argument("--date-from", help="Start date YYYY-MM-DD (use with --date-to; overrides --days)")
    p.add_argument("--date-to", help="End date YYYY-MM-DD (use with --date-from; overrides --days)")
    p.add_argument("--no-compare", action="store_true",
                   help="Skip vs-previous-period deltas (one fewer API call)")
    p.add_argument("--json", **json_kwargs)

    # --- campaigns ---
    p = subparsers.add_parser("campaigns", help="List campaigns")
    p.add_argument("--status", choices=["active", "suspend"], help="Filter by status")
    p.add_argument("--json", **json_kwargs)

    # --- campaign-create ---
    p = subparsers.add_parser("campaign-create", help="Create campaign")
    p.add_argument("--name", required=True, help="Campaign name")
    p.add_argument("--day-budget", type=float, required=True, help="Day budget in CZK")
    p.add_argument("--type", default="fulltext", choices=["fulltext", "context", "product"], help="Campaign type")
    p.add_argument("--status", choices=["active", "suspend"], help="Initial status")
    p.add_argument("--regions", help="Comma-separated region IDs for geo targeting")
    p.add_argument("--device-bids", dest="device_bids",
                   help="Device bid modifiers 'desktop:mobile:tablet:other' in %% (e.g. 0:-30:-30:-100)")
    p.add_argument("--json", **json_kwargs)

    # --- campaign-update ---
    p = subparsers.add_parser("campaign-update", help="Update campaign")
    p.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--day-budget", type=float, help="New day budget in CZK")
    p.add_argument("--status", choices=["active", "suspend"], help="New status")
    p.add_argument("--regions", help="Comma-separated region IDs (empty string clears geo targeting)")
    p.add_argument("--device-bids", dest="device_bids",
                   help="Device bid modifiers 'desktop:mobile:tablet:other' in %% (e.g. 0:-30:-30:-100)")
    p.add_argument("--schedule-json", dest="schedule_json",
                   help="Schedule as JSON: {\"daySchedule\":[{\"value\":[24 hourly 0-100]}, ...×7]}")
    p.add_argument("--json", **json_kwargs)

    # --- campaign-targeting ---
    p = subparsers.add_parser("campaign-targeting", help="Show geo/device/schedule targeting")
    p.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")
    p.add_argument("--json", **json_kwargs)

    # --- campaign-remove ---
    p = subparsers.add_parser("campaign-remove", help="Remove campaign")
    p.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- campaign-stats ---
    p = subparsers.add_parser("campaign-stats", help="Campaign statistics")
    p.add_argument("--campaign-id", type=int, help="Campaign ID (all if omitted)")
    p.add_argument("--date-from", help="Start date YYYY-MM-DD")
    p.add_argument("--date-to", help="End date YYYY-MM-DD")
    p.add_argument("--json", **json_kwargs)

    # --- groups ---
    p = subparsers.add_parser("groups", help="List ad groups")
    p.add_argument("--campaign-id", type=int, help="Filter by campaign ID")
    p.add_argument("--json", **json_kwargs)

    # --- group-create ---
    p = subparsers.add_parser("group-create", help="Create ad group")
    p.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")
    p.add_argument("--name", required=True, help="Group name")
    p.add_argument("--cpc", type=float, required=True, help="Default max CPC in CZK")
    p.add_argument("--json", **json_kwargs)

    # --- group-update ---
    p = subparsers.add_parser("group-update", help="Update ad group")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--cpc", type=float, help="New max CPC in CZK")
    p.add_argument("--status", choices=["active", "suspend"], help="New status")
    p.add_argument("--json", **json_kwargs)

    # --- group-remove ---
    p = subparsers.add_parser("group-remove", help="Remove ad group")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- group-stats ---
    p = subparsers.add_parser("group-stats", help="Group statistics")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--date-from", help="Start date YYYY-MM-DD")
    p.add_argument("--date-to", help="End date YYYY-MM-DD")
    p.add_argument("--json", **json_kwargs)

    # --- keywords ---
    p = subparsers.add_parser("keywords", help="List keywords")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--campaign-id", type=int, help="Filter by campaign ID")
    p.add_argument("--json", **json_kwargs)

    # --- keyword-create ---
    p = subparsers.add_parser("keyword-create", help="Create keyword")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--name", required=True, help="Keyword text")
    p.add_argument("--match-type", default="broad", choices=["broad", "phrase", "exact"], help="Match type")
    p.add_argument("--cpc", type=float, help="Max CPC in CZK (default: group CPC)")
    p.add_argument("--url", help="Landing page URL")
    p.add_argument("--json", **json_kwargs)

    # --- keyword-create-batch ---
    p = subparsers.add_parser("keyword-create-batch", help="Batch create keywords")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--keywords-json", required=True, help='JSON array: [{"name":"kw","matchType":"broad","cpc":5.0}]')
    p.add_argument("--json", **json_kwargs)

    # --- keyword-update ---
    p = subparsers.add_parser("keyword-update", help="Update keyword")
    p.add_argument("--keyword-id", type=int, required=True, help="Keyword ID")
    p.add_argument("--cpc", type=float, help="New CPC in CZK")
    p.add_argument("--status", choices=["active", "suspend"], help="New status")
    p.add_argument("--url", help="New URL")
    p.add_argument("--json", **json_kwargs)

    # --- keyword-remove ---
    p = subparsers.add_parser("keyword-remove", help="Remove keyword")
    p.add_argument("--keyword-id", type=int, required=True, help="Keyword ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- keyword-stats ---
    p = subparsers.add_parser("keyword-stats", help="Keyword statistics")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--date-from", help="Start date YYYY-MM-DD")
    p.add_argument("--date-to", help="End date YYYY-MM-DD")
    p.add_argument("--json", **json_kwargs)

    # --- ads ---
    p = subparsers.add_parser("ads", help="List ads")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--json", **json_kwargs)

    # --- ad-create ---
    p = subparsers.add_parser("ad-create", help="Create ETA ad")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--headline1", required=True, help="Headline 1 (max 30 chars)")
    p.add_argument("--headline2", required=True, help="Headline 2 (max 30 chars)")
    p.add_argument("--headline3", help="Headline 3 (max 30 chars)")
    p.add_argument("--description1", required=True, help="Description 1 (max 90 chars)")
    p.add_argument("--description2", help="Description 2 (max 90 chars)")
    p.add_argument("--final-url", required=True, help="Final URL")
    p.add_argument("--path1", help="Display path 1 (max 15 chars)")
    p.add_argument("--path2", help="Display path 2 (max 15 chars)")
    p.add_argument("--json", **json_kwargs)

    # --- combined-create ---
    p = subparsers.add_parser(
        "combined-create",
        help="Create combined (native) ad for the display network")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--short-line", required=True, help="Short headline (max 25 chars)")
    p.add_argument("--long-line", required=True, help="Long headline (max 90 chars)")
    p.add_argument("--description", required=True, help="Description (max 90 chars)")
    p.add_argument("--company-name", dest="company_name", required=True,
                   help="Company or brand name (max 25 chars)")
    p.add_argument("--final-url", required=True, help="Final URL")
    p.add_argument("--image-landscape", required=True,
                   help="Landscape image 1.91:1, min 600x314 px (local path or URL)")
    p.add_argument("--image-square", required=True,
                   help="Square image 1:1, min 300x300 px (local path or URL)")
    p.add_argument("--image-logo", help="Square logo 1:1, min 128x128 px (optional)")
    p.add_argument("--image-landscape-logo",
                   help="Landscape logo 4:1, min 512x128 px (optional)")
    p.add_argument("--color-main", help="Main color in HEX (with or without #)")
    p.add_argument("--color-accent", help="Accent color in HEX (with or without #)")
    p.add_argument("--mobile-final-url", help="Mobile final URL")
    p.add_argument("--tracking-template", help="Tracking template")
    p.add_argument("--status", choices=["active", "suspend"], help="Initial status")
    p.add_argument("--json", **json_kwargs)

    # --- ad-update ---
    p = subparsers.add_parser("ad-update", help="Update ad")
    p.add_argument("--ad-id", type=int, required=True, help="Ad ID")
    p.add_argument("--status", choices=["active", "suspend"], help="New status")
    p.add_argument("--json", **json_kwargs)

    # --- ad-remove ---
    p = subparsers.add_parser("ad-remove", help="Remove ad")
    p.add_argument("--ad-id", type=int, required=True, help="Ad ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- ad-stats ---
    p = subparsers.add_parser("ad-stats", help="Ad statistics")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--date-from", help="Start date YYYY-MM-DD")
    p.add_argument("--date-to", help="End date YYYY-MM-DD")
    p.add_argument("--json", **json_kwargs)

    # --- negatives ---
    p = subparsers.add_parser("negatives", help="List negative keywords")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--campaign-id", type=int, help="Filter by campaign ID")
    p.add_argument("--json", **json_kwargs)

    # --- negative-add ---
    p = subparsers.add_parser("negative-add", help="Add negative keyword")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--name", required=True, help="Negative keyword text")
    p.add_argument("--match-type", default="negativeBroad",
                   choices=["negativeBroad", "negativePhrase", "negativeExact"], help="Match type")
    p.add_argument("--json", **json_kwargs)

    # --- negative-add-batch ---
    p = subparsers.add_parser("negative-add-batch", help="Batch add negatives")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--keywords-json", required=True, help='JSON array: [{"name":"kw","matchType":"negativeBroad"}] or ["kw1","kw2"]')
    p.add_argument("--json", **json_kwargs)

    # --- negative-remove ---
    p = subparsers.add_parser("negative-remove", help="Remove negative keyword")
    p.add_argument("--keyword-id", type=int, required=True, help="Negative keyword ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- suggest ---
    p = subparsers.add_parser("suggest", help="Keyword suggestions")
    p.add_argument("--query", required=True, help="Seed query")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--related", action="store_true", help="Include related keywords")
    p.add_argument("--order-by", default="avgSearchCount",
                   choices=["avgSearchCount", "cpc", "score"], help="Sort order")
    p.add_argument("--json", **json_kwargs)

    # --- suggest-stats ---
    p = subparsers.add_parser("suggest-stats", help="Search volume for keywords")
    p.add_argument("--queries", required=True, help="Comma-separated keywords")
    p.add_argument("--granularity", default="monthly", choices=["monthly", "daily"], help="Granularity")
    p.add_argument("--json", **json_kwargs)

    # --- search-queries ---
    p = subparsers.add_parser("search-queries", help="Search query report")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--date-from", help="Start date YYYY-MM-DD")
    p.add_argument("--date-to", help="End date YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=100, help="Max results (default: 100)")
    p.add_argument("--json", **json_kwargs)

    # --- sitelinks ---
    p = subparsers.add_parser("sitelinks", help="List sitelinks")
    p.add_argument("--json", **json_kwargs)

    # --- sitelink-create ---
    p = subparsers.add_parser("sitelink-create", help="Create sitelink")
    p.add_argument("--name", required=True, help="Sitelink text")
    p.add_argument("--url", required=True, help="Sitelink URL")
    p.add_argument("--json", **json_kwargs)

    # --- sitelink-remove ---
    p = subparsers.add_parser("sitelink-remove", help="Remove sitelink")
    p.add_argument("--sitelink-id", type=int, required=True, help="Sitelink ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- conversions ---
    p = subparsers.add_parser("conversions", help="List conversion definitions")
    p.add_argument("--json", **json_kwargs)

    # --- conversion-types ---
    p = subparsers.add_parser("conversion-types", help="List conversion type IDs (for conversion-create)")
    p.add_argument("--json", **json_kwargs)

    # --- conversion-create ---
    p = subparsers.add_parser("conversion-create", help="Create conversion definition")
    p.add_argument("--name", required=True, help="Conversion name")
    p.add_argument("--type-id", type=int, required=True, help="Conversion type ID (see conversion-types)")
    p.add_argument("--value", type=float, help="Conversion value in CZK")
    p.add_argument("--color", help="Hex color (e.g. #ff0000)")
    p.add_argument("--json", **json_kwargs)

    # --- conversion-update ---
    p = subparsers.add_parser("conversion-update", help="Update conversion definition")
    p.add_argument("--conversion-id", type=int, required=True, help="Conversion ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--value", type=float, help="New value in CZK")
    p.add_argument("--color", help="New hex color")
    p.add_argument("--json", **json_kwargs)

    # --- conversion-remove ---
    p = subparsers.add_parser("conversion-remove", help="Remove conversion definition")
    p.add_argument("--conversion-id", type=int, required=True, help="Conversion ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting ---
    p = subparsers.add_parser("retargeting", help="List retargeting (audience) lists")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-create ---
    p = subparsers.add_parser("retargeting-create", help="Create retargeting list")
    p.add_argument("--name", required=True, help="List name")
    p.add_argument("--membership", type=int, required=True, help="Membership duration in days")
    p.add_argument("--description", help="Optional description")
    p.add_argument("--use-historic", action="store_true", help="Include historic URL requests")
    p.add_argument("--take-all-users", dest="take_all_users", action="store_const", const=True,
                   default=None, help="Capture all visitors (default unless --conditions-json given)")
    p.add_argument("--conditions-json", help='URL condition groups as JSON (advanced)')
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-update ---
    p = subparsers.add_parser("retargeting-update", help="Update retargeting list")
    p.add_argument("--list-id", type=int, required=True, help="Retargeting list ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--membership", type=int, help="New membership duration in days")
    p.add_argument("--description", help="New description")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-remove ---
    p = subparsers.add_parser("retargeting-remove", help="Remove retargeting list")
    p.add_argument("--list-id", type=int, required=True, help="Retargeting list ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- banner-formats ---
    p = subparsers.add_parser("banner-formats", help="List allowed banner formats")
    p.add_argument("--json", **json_kwargs)

    # --- banners ---
    p = subparsers.add_parser("banners", help="List image banners")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--json", **json_kwargs)

    # --- banner-create ---
    p = subparsers.add_parser("banner-create", help="Create image banner")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--name", required=True, help="Banner name")
    p.add_argument("--clickthru-url", dest="clickthru_url", required=True, help="Click-through URL")
    p.add_argument("--image", required=True, help="Image: local path or http(s) URL (jpg/png/gif)")
    p.add_argument("--status", choices=["active", "suspend"], help="Initial status")
    p.add_argument("--json", **json_kwargs)

    # --- banner-remove ---
    p = subparsers.add_parser("banner-remove", help="Remove image banner")
    p.add_argument("--banner-id", type=int, required=True, help="Banner ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- placements ---
    p = subparsers.add_parser("placements", help="List placement patterns (content network targeting)")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--json", **json_kwargs)

    # --- placement-create ---
    p = subparsers.add_parser("placement-create", help="Add placement (target website) to a display group")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--pattern", required=True,
                   help='URL pattern, e.g. "forbes.cz" or "www.e15.cz/byznys"')
    p.add_argument("--cpc", type=float, help="Placement max CPC in CZK (default: group CPC)")
    p.add_argument("--status", choices=["active", "suspend"], help="Initial status")
    p.add_argument("--json", **json_kwargs)

    # --- placement-remove ---
    p = subparsers.add_parser("placement-remove", help="Remove placement pattern")
    p.add_argument("--pattern-id", type=int, required=True, help="Pattern ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    args = parser.parse_args()
    set_account(getattr(args, "account", DEFAULT_ACCOUNT))
    _check_config()

    commands = {
        "account": cmd_account,
        "api-limits": cmd_api_limits,
        "pulse": cmd_pulse,
        "campaigns": cmd_campaigns,
        "campaign-create": cmd_campaign_create,
        "campaign-update": cmd_campaign_update,
        "campaign-remove": cmd_campaign_remove,
        "campaign-stats": cmd_campaign_stats,
        "campaign-targeting": cmd_campaign_targeting,
        "groups": cmd_groups,
        "group-create": cmd_group_create,
        "group-update": cmd_group_update,
        "group-remove": cmd_group_remove,
        "group-stats": cmd_group_stats,
        "keywords": cmd_keywords,
        "keyword-create": cmd_keyword_create,
        "keyword-create-batch": cmd_keyword_create_batch,
        "keyword-update": cmd_keyword_update,
        "keyword-remove": cmd_keyword_remove,
        "keyword-stats": cmd_keyword_stats,
        "ads": cmd_ads,
        "ad-create": cmd_ad_create,
        "combined-create": cmd_combined_create,
        "ad-update": cmd_ad_update,
        "ad-remove": cmd_ad_remove,
        "ad-stats": cmd_ad_stats,
        "negatives": cmd_negatives,
        "negative-add": cmd_negative_add,
        "negative-add-batch": cmd_negative_add_batch,
        "negative-remove": cmd_negative_remove,
        "suggest": cmd_suggest,
        "suggest-stats": cmd_suggest_stats,
        "search-queries": cmd_search_queries,
        "sitelinks": cmd_sitelinks,
        "sitelink-create": cmd_sitelink_create,
        "sitelink-remove": cmd_sitelink_remove,
        "conversions": cmd_conversions,
        "conversion-types": cmd_conversion_types,
        "conversion-create": cmd_conversion_create,
        "conversion-update": cmd_conversion_update,
        "conversion-remove": cmd_conversion_remove,
        "retargeting": cmd_retargeting,
        "retargeting-create": cmd_retargeting_create,
        "retargeting-update": cmd_retargeting_update,
        "retargeting-remove": cmd_retargeting_remove,
        "banner-formats": cmd_banner_formats,
        "banners": cmd_banners,
        "banner-create": cmd_banner_create,
        "banner-remove": cmd_banner_remove,
        "placements": cmd_placements,
        "placement-create": cmd_placement_create,
        "placement-remove": cmd_placement_remove,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
