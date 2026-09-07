"""Engine for the Sklik **Fénix** REST API (Seznam Nákupy).

Fénix (`api.sklik.cz/v1`) is Seznam's newer REST interface for **Seznam Nákupy**
(formerly Zboží.cz). It covers the shopping blind spot of DRAK (`sklik/api.py`):
the feed, per-offer diagnostics, per-product bids/auction positions and the
placement breakdown of shopping statistics — none of which DRAK exposes, where a
product campaign is only ever an aggregate.

It is a **separate API with separate auth**: a long-lived *refresh token*
(generated in the Sklik web UI) is exchanged at `POST /user/token` for a 1-hour
access token, cached per account in `.fenix_cache_<account>.json`.

Config in `.env`, mirroring the DRAK per-account scheme:

    SKLIK_FENIX_REFRESH_TOKEN          -> the "default" account
    SKLIK_FENIX_REFRESH_TOKEN_<NAME>   -> a named account (--account <name>)
    SKLIK_FENIX_PREMISE                -> default premiseId (shop)
    SKLIK_FENIX_PREMISE_<NAME>         -> per-account default premiseId

`premiseId` identifies the **shop** and is required by every `/nakupy/*` call;
`--premise-id` overrides the configured default. It is not a campaign ID.

`--user-id` works here too, but at a different layer than in DRAK: Fénix takes
the managed account at **token mint time** (`user_id` in the token request), so
each managed account gets its own cached access token.

Money conventions differ from DRAK and are NOT uniform inside Fénix itself —
see `docs/api-notes.md`. Nothing in this module converts amounts; the callers
pass through what the API sends.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

import requests

import sklik.api as api
from sklik.api import BASE_DIR, _fail_msg

# The OpenAPI spec's server is `/v1`; the `/fenix/` path only serves the docs UI.
FENIX_BASE = "https://api.sklik.cz/v1"

# Access tokens live 1 h; refresh early so a call can never race the expiry.
_TOKEN_SLACK = 120

# Minimum spacing between Fénix calls. Fénix has no published request budget
# (unlike DRAK's `api.limits`) and answers bursts with 429, so we self-pace.
_MIN_INTERVAL = 0.6
_last_call_at = 0.0

# Runaway guard for cursor paging — a hit is reported, never silent.
LIST_MAX_ITEMS = 200000

# Managed account for this invocation; set once from `--user-id` in main().
ACTIVE_USER_ID: int | None = None


def set_user_id(user_id: int | None) -> None:
    """Select the managed account Fénix tokens are minted for."""
    global ACTIVE_USER_ID
    ACTIVE_USER_ID = user_id


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _env_suffix() -> str:
    """`_<NAME>` suffix of the active account's env vars ('' for default)."""
    if api.ACTIVE_ACCOUNT == api.DEFAULT_ACCOUNT:
        return ""
    return f"_{api.ACTIVE_ACCOUNT.upper()}"


def _refresh_token() -> str:
    return os.getenv(f"SKLIK_FENIX_REFRESH_TOKEN{_env_suffix()}", "")


def check_config() -> None:
    """Fail early (before any request) if no Fénix refresh token is configured."""
    token = _refresh_token()
    if not token or token.startswith("your-"):
        env_var = f"SKLIK_FENIX_REFRESH_TOKEN{_env_suffix()}"
        _fail_msg(
            f"{env_var} not set for account '{api.ACTIVE_ACCOUNT}'. The Nákupy "
            "commands use the Fénix API, which has its OWN token — generate a "
            "refresh token in the Sklik web UI and add it to .env (see "
            ".env.example). The DRAK API token does not work here.",
            account=api.ACTIVE_ACCOUNT,
        )


def resolve_premise(cli_value: int | None) -> int:
    """The shop to act on: `--premise-id`, else the configured default."""
    if cli_value:
        return cli_value
    raw = os.getenv(f"SKLIK_FENIX_PREMISE{_env_suffix()}", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    _fail_msg(
        "no Fénix premiseId. Pass --premise-id <id> or set "
        f"SKLIK_FENIX_PREMISE{_env_suffix()} in .env. It is the SHOP "
        "(provozovna) ID from Sklik Nákupy, not a campaign ID."
        + (f" Ignoring unusable configured value {raw!r}." if raw else ""),
        account=api.ACTIVE_ACCOUNT,
    )


# ---------------------------------------------------------------------------
# Auth — refresh token -> access token (cached per account and managed user)
# ---------------------------------------------------------------------------

def _cache_path() -> str:
    return os.path.join(BASE_DIR, f".fenix_cache_{api.ACTIVE_ACCOUNT}.json")


def _cache_key() -> str:
    """Cache slot: one access token per managed account under this login."""
    return str(ACTIVE_USER_ID) if ACTIVE_USER_ID else "self"


def _load_token() -> str | None:
    """Cached access token for the active account+user, if still valid."""
    try:
        with open(_cache_path()) as f:
            cache = json.load(f)
        entry = cache.get(_cache_key()) or {}
        if entry.get("expires_at", 0) > time.time():
            return entry["access_token"]
    except (OSError, ValueError, AttributeError):
        pass  # missing/corrupt cache is never fatal — just re-authenticate
    return None


def _save_token(access_token: str, expires_in: int) -> None:
    """Cache the access token, preserving the other managed accounts' slots."""
    try:
        with open(_cache_path()) as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    cache[_cache_key()] = {
        "access_token": access_token,
        "expires_at": time.time() + max(60, expires_in - _TOKEN_SLACK),
    }
    try:
        with open(_cache_path(), "w") as f:
            json.dump(cache, f)
    except OSError:
        pass  # an uncacheable token still works, it just costs a mint per call


def _authenticate() -> str:
    """Exchange the refresh token for an access token (and cache it)."""
    form = {"grant_type": "refresh_token", "refresh_token": _refresh_token()}
    if ACTIVE_USER_ID:
        form["user_id"] = str(ACTIVE_USER_ID)

    resp = requests.post(
        f"{FENIX_BASE}/user/token", data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30,
    )
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code != 200 or "access_token" not in data:
        hint = ("Check that --user-id names an account you have been granted "
                "access to." if ACTIVE_USER_ID else
                "The refresh token may be expired or revoked — regenerate it "
                "in the Sklik web UI.")
        _fail_msg(f"Fénix authentication failed (HTTP {resp.status_code}). {hint}",
                  account=api.ACTIVE_ACCOUNT, userId=ACTIVE_USER_ID,
                  httpStatus=resp.status_code, detail=data or resp.text[:400])

    _save_token(data["access_token"], int(data.get("expires_in", 3600)))
    return data["access_token"]


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def _throttle() -> None:
    """Keep at least `_MIN_INTERVAL` between calls (Fénix 429s on bursts)."""
    global _last_call_at
    gap = time.time() - _last_call_at
    if gap < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - gap)
    _last_call_at = time.time()


def _request(method: str, path: str, params: dict | None = None,
             body: object | None = None) -> requests.Response:
    _throttle()
    url = f"{FENIX_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    return requests.request(
        method, url,
        headers={"Authorization": f"Bearer {_load_token() or _authenticate()}",
                 "Accept": "application/json"},
        json=body if body is not None else None,
        timeout=90,
    )


def call(method: str, path: str, params: dict | None = None,
         body: object | None = None, _retries: int = 0) -> dict:
    """One Fénix REST call; `path` is relative to `/v1` (e.g. `/nakupy/feeds/`).

    Returns the parsed JSON body. A 401 re-authenticates once, a 429 backs off
    and retries; every other non-2xx exits through the CLI's structured error.
    """
    resp = _request(method, path, params, body)

    if resp.status_code == 401 and _retries == 0:
        _authenticate()
        return call(method, path, params, body, _retries=_retries + 1)

    if resp.status_code == 429:
        if _retries >= 3:
            _fail_msg(f"Fénix {method} {path} still rate-limited (429) after "
                      f"{_retries} retries — wait a minute and try again.",
                      method=f"{method} {path}", httpStatus=429)
        time.sleep(3 * (_retries + 1))
        return call(method, path, params, body, _retries=_retries + 1)

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code not in (200, 201, 202, 206):
        _fail_msg(f"Fénix {method} {path} returned HTTP {resp.status_code}.",
                  method=f"{method} {path}", httpStatus=resp.status_code,
                  detail=data or resp.text[:400])
    return data if isinstance(data, dict) else {"data": data}


def fetch_all(path: str, params: dict, page_limit: int) -> tuple[list[dict], int | None]:
    """Read EVERY row of a cursor-paged Fénix listing.

    Fénix pages with an **opaque cursor**: `meta.offset` from one response is
    passed as `offset` to the next, and comes back `null` on the last page.
    `meta.totalCount` is only sent on the initial (cursor-less) request.

    Returns `(rows, total_count)`. Same contract as `api._fetch_all`: complete
    or loudly truncated, never a short list passed off as the whole set.
    """
    rows: list[dict] = []
    total: int | None = None
    cursor: int | None = None

    while True:
        page_params = dict(params, limit=page_limit)
        if cursor is not None:
            page_params["offset"] = cursor
        data = call("GET", path, page_params)

        rows.extend(data.get("items") or [])
        meta = data.get("meta") or {}
        if total is None:
            total = meta.get("totalCount")

        next_cursor = meta.get("offset")
        if not next_cursor:
            return rows, total
        if next_cursor == cursor:
            # A cursor that doesn't advance would page forever; stop and say so
            # rather than spin. (Belt and braces — not observed in practice.)
            print(f"WARNING: {path} returned a repeating pagination cursor; "
                  f"stopping after {len(rows)} rows.", file=sys.stderr)
            return rows, total
        cursor = next_cursor
        if len(rows) >= LIST_MAX_ITEMS:
            print(f"WARNING: {path} returned more than {LIST_MAX_ITEMS} rows; "
                  "the list is truncated. Narrow the query.", file=sys.stderr)
            return rows, total


def poll_report(report_id: int, timeout: int = 120) -> dict:
    """Poll `GET /sklik/reports/{id}` until the async statistics report is ready.

    The Nákupy statistics endpoints only queue the work (`202` + a report id);
    the data is then read from the shared `/sklik/reports` endpoint, which
    answers **425 Too Early** while the report is still being generated. 425 is
    not in the OpenAPI spec — it was observed live, so anything else non-200 is
    treated as a real failure rather than silently retried until the timeout.
    """
    deadline = time.time() + timeout
    delay = 3
    while True:
        resp = _request("GET", f"/sklik/reports/{report_id}", {"format": "json"})
        if resp.status_code == 401:
            _authenticate()
            resp = _request("GET", f"/sklik/reports/{report_id}", {"format": "json"})

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                _fail_msg(f"Fénix report {report_id} returned non-JSON content.",
                          detail=resp.text[:400])
        if resp.status_code not in (425, 429):
            _fail_msg(f"Fénix report {report_id} failed (HTTP {resp.status_code}).",
                      httpStatus=resp.status_code, detail=resp.text[:400])
        if time.time() > deadline:
            _fail_msg(f"Fénix report {report_id} was not ready within {timeout}s. "
                      "Large windows take longer — retry, or narrow the period.",
                      httpStatus=resp.status_code)
        time.sleep(delay)
        delay = min(delay + 2, 10)
