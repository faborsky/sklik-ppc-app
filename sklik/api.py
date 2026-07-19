"""Engine: config, accounts, auth/session, rate limiting, API calls, errors."""
from __future__ import annotations

import json
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv


# Set once in main() from the active command's --json flag. When True, fatal
# errors are emitted as a parseable {"error": {...}} object on STDOUT (for an
# orchestrating caller such as Claude Code) instead of only human text on stderr.
_JSON_OUTPUT = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

def check_config() -> None:
    token = _get_token()
    if not token or token.startswith("your-"):
        env_var = _token_env_var(ACTIVE_ACCOUNT)
        msg = (f"{env_var} not set for account '{ACTIVE_ACCOUNT}'. "
               f"Add it to .env (see .env.example).")
        available = _available_accounts()
        if available:
            msg += f" Configured accounts: {', '.join(available)}."
        _fail_msg(msg, account=ACTIVE_ACCOUNT, configuredAccounts=_available_accounts())


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
        _fail("client.loginByToken", data)
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
        _fail_msg(
            f"daily request budget reached for account '{ACTIVE_ACCOUNT}' "
            f"({len(reqs)}/{limits['day']} incl. {int(RATE_LIMIT_SAFETY*100)}% safety "
            f"margin). Resets in ~{wait_h:.1f}h. Aborting to protect the account.",
            account=ACTIVE_ACCOUNT, resetsInHours=round(wait_h, 1),
        )

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


def _extract_diagnostics(data: dict) -> list[str]:
    """Flatten Sklik diagnostics (dict {problems:[…]} OR list) into readable lines."""
    diag = data.get("diagnostics")
    out: list[str] = []
    if isinstance(diag, dict):
        for p in diag.get("problems", []):
            if isinstance(p, dict):
                out.append(f"{p.get('field', '')}: {p.get('problemMessage', p.get('id', ''))}".strip(": ").strip())
            else:
                out.append(str(p))
    elif isinstance(diag, list):
        for d in diag:
            if isinstance(d, dict):
                parts = [str(d.get("id", "")).strip()]
                if d.get("field"):
                    parts.append(f"field={d.get('field')}")
                if d.get("type"):
                    parts.append(f"type={d.get('type')}")
                if d.get("problemMessage"):
                    parts.append(str(d.get("problemMessage")))
                out.append(" ".join(p for p in parts if p))
            else:
                out.append(str(d))
    return [o for o in out if o]


def _fail(method: str, data: dict) -> None:
    """Emit a Sklik API error and exit non-zero.

    In --json mode the error is written as a parseable {"error": {...}} object on
    STDOUT so an orchestrating caller (e.g. Claude Code) can read it; otherwise a
    human-readable message goes to stderr. Either way the real diagnostics
    (e.g. ad_duplicate_in_db) are surfaced, never swallowed by a warning.
    """
    status = data.get("status")
    message = data.get("statusMessage")
    problems = _extract_diagnostics(data)
    if method.startswith("conversions.") and _is_sem_blocked(data):
        problems.append("This account has SEM (Seznam Event Measurement) activated, "
                        "which disables the conversions.* API methods. Manage "
                        "conversions in the Sklik web interface instead.")
    if _JSON_OUTPUT:
        print(json.dumps({"error": {
            "method": method,
            "status": status,
            "message": message,
            "diagnostics": problems,
        }}, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"ERROR: {method} returned {status}: {message}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
    sys.exit(1)


def _fail_msg(message: str, **extra: object) -> None:
    """Emit a non-API fatal error (bad args, local budget, not-found) and exit.

    Structured on stdout in --json mode, plain on stderr otherwise — same
    contract as _fail so callers get a consistent, parseable failure shape.
    """
    if _JSON_OUTPUT:
        print(json.dumps({"error": {"message": message, **extra}},
                         indent=2, ensure_ascii=False, default=str))
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def _api_call(method: str, params: list | None = None, user_id: int | None = None,
              _throttle: bool = True, _retries: int = 0, _soft: bool = False) -> dict:
    """Make a Sklik DRAK API call with session management.

    First param is always the user struct with session.
    Handles 401 by re-authenticating once.

    Respects the account's per-minute / per-day request budget (tracked locally
    across sessions); `_throttle=False` skips the pre-check (used only for the
    api.limits fetch itself, which is still counted).

    `_soft=True` returns the raw response dict on a non-2xx status instead of
    printing an error and exiting — used for dry-run validation (ads.check) where
    the caller inspects the diagnostics and decides what to do.
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
    try:
        data = resp.json()
    except ValueError:
        _fail_msg(f"{method} returned non-JSON response (HTTP {resp.status_code}) — "
                  f"likely an unknown method name or an API outage.",
                  method=method, httpStatus=resp.status_code)

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
            _fail_msg(f"{method} still rate-limited (429) after {_retries} retries — "
                      f"giving up to protect account '{ACTIVE_ACCOUNT}'.",
                      method=method, status=429)
        wait = 5 * (_retries + 1)  # 5s, 10s, 15s
        print(f"Rate limited (429), waiting {wait}s… (retry {_retries + 1}/3)", file=sys.stderr)
        time.sleep(wait)
        return _api_call(method, params, user_id, _throttle=_throttle,
                         _retries=_retries + 1, _soft=_soft)

    # Handle errors
    if data.get("status") not in (200, 206):
        if _soft:
            return data  # caller inspects diagnostics (dry-run validation)
        _fail(method, data)

    # Show warnings from 206
    if data.get("status") == 206:
        diag = data.get("diagnostics")
        if isinstance(diag, list):
            for d in diag:
                if isinstance(d, dict) and d.get("type") == "warning":
                    print(f"WARNING: {d.get('id')}: {d.get('field', '')}", file=sys.stderr)

    return data


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


def set_json_output(value: bool) -> None:
    """Enable structured-error-to-stdout mode from the command's --json flag."""
    global _JSON_OUTPUT
    _JSON_OUTPUT = bool(value)
