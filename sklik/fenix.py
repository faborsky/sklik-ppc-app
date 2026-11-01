"""Engine for the Sklik **Fénix** REST API (Seznam Nákupy + Sklik campaigns).

Fénix (`api.sklik.cz/v1`) is Seznam's newer REST interface. Its `/nakupy/*`
half serves **Seznam Nákupy** (formerly Zboží.cz) and covers the shopping blind
spot of DRAK (`sklik/api.py`): the feed, per-offer diagnostics, per-product
bids/auction positions and the placement breakdown of shopping statistics —
none of which DRAK exposes, where a product campaign is only ever an aggregate.
Its `/sklik/*` and `/user/*` half (campaigns, groups, ads, negative keywords,
the authorized user) backs the `fenix-*` commands in
`sklik/commands/fenix_sklik.py`.

It is a **separate API with separate auth**: a long-lived *refresh token*
(generated in the Sklik web UI) is exchanged at `POST /user/token` for a 1-hour
access token, cached per account in `.fenix_cache_<account>.json`.

Config in `.env`, mirroring the DRAK per-account scheme:

    SKLIK_FENIX_REFRESH_TOKEN          -> the "default" account
    SKLIK_FENIX_REFRESH_TOKEN_<NAME>   -> a named account (--account <name>)
    SKLIK_FENIX_PREMISE                -> default premiseId (shop)
    SKLIK_FENIX_PREMISE_<NAME>         -> per-account default premiseId

`premiseId` identifies the **shop** and is required by every `/nakupy/*` call;
`--premise-id` overrides the configured default. It is not a campaign ID. The
`/sklik/*` and `/user/*` endpoints do not take it.

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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

import sklik.api as api
from sklik.api import BASE_DIR, _fail_msg

# The OpenAPI spec's server is `/v1`; the `/fenix/` path only serves the docs UI.
FENIX_BASE = "https://api.sklik.cz/v1"

# Access tokens live 1 h; refresh early so a call can never race the expiry.
_TOKEN_SLACK = 120

# Minimum spacing between Fénix calls. The spec (1.30.0) publishes a default
# budget of 5 requests/second across all endpoints and answers bursts with 429
# + `Retry-After`; there is no runtime query for it like DRAK's `api.limits`.
# We stay well under it — the pacing is per process, so parallel CLI runs add up.
_MIN_INTERVAL = 0.6
_last_call_at = 0.0

# Endpoints whose own `x-rate-limit` in the spec is TIGHTER than `_MIN_INTERVAL`
# and that one CLI run calls repeatedly (paging). The other per-endpoint limits
# (`/nakupy/feeds/` and `/nakupy/diagnostics/item` 2/min, `/nakupy/statistics/*`
# 5/30 s) are hit once per run, so in-process pacing cannot help there — those
# rely on honouring `Retry-After` below.
_ENDPOINT_MIN_INTERVAL = {
    "/nakupy/shop-items/": 1.1,   # spec: 1 request per second
}

# Longest server-requested wait (`Retry-After`) we sit out before giving up.
_RETRY_AFTER_MAX = 120

# Runaway guard for cursor/offset paging — a hit is reported, never silent.
LIST_MAX_ITEMS = 200000

# Page size of the offset-paged `/sklik/*` listings (the spec's `limit` maximum).
SKLIK_PAGE_LIMIT = 1000

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
    env_var = f"SKLIK_FENIX_REFRESH_TOKEN{_env_suffix()}"
    api._fail_if_secret_reference(token, env_var)
    if not token or token.startswith("your-"):
        _fail_msg(
            f"{env_var} not set for account '{api.ACTIVE_ACCOUNT}'. The Nákupy "
            "and fenix-* commands use the Fénix API, which has its OWN token — "
            "generate a refresh token in the Sklik web UI and add it to .env "
            "(see .env.example). The DRAK API token does not work here.",
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
        detail: object = data or resp.text[:400]
        # Defensive: a validation error that echoes the submitted form back
        # would carry the refresh token into the error output (and from there
        # into an agent's transcript). Not observed — but never worth the risk.
        secret = form["refresh_token"]
        if secret and secret in json.dumps(detail, ensure_ascii=False, default=str):
            detail = "(response omitted: it echoed the refresh token)"
        _fail_msg(f"Fénix authentication failed (HTTP {resp.status_code}). {hint}",
                  account=api.ACTIVE_ACCOUNT, userId=ACTIVE_USER_ID,
                  httpStatus=resp.status_code, detail=detail)

    _save_token(data["access_token"], int(data.get("expires_in", 3600)))
    return data["access_token"]


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def _throttle(path: str) -> None:
    """Keep at least `_MIN_INTERVAL` between calls (Fénix 429s on bursts), or
    the endpoint's own longer interval where the spec sets a tighter limit."""
    global _last_call_at
    interval = max(_MIN_INTERVAL, _ENDPOINT_MIN_INTERVAL.get(path, 0.0))
    gap = time.time() - _last_call_at
    if gap < interval:
        time.sleep(interval - gap)
    _last_call_at = time.time()


def _retry_after(resp: requests.Response) -> float | None:
    """Seconds a 429 asks us to wait (`Retry-After`), or None if it doesn't say.

    The spec promises the header on every 429. Both RFC 9110 forms are read:
    delta-seconds and an HTTP-date.
    """
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None  # unparseable header — fall back to our own back-off


def _error_lines(data: object) -> list[str]:
    """Flatten a Fénix error body (`{"detail": [{loc, msg, type}, …]}`) into
    readable lines, so the human (stderr) error names the offending field too —
    `_fail_msg` prints only its message outside --json mode."""
    detail = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detail, str):
        return [detail]
    out: list[str] = []
    for d in detail if isinstance(detail, list) else []:
        if not isinstance(d, dict):
            out.append(str(d))
            continue
        loc = ".".join(str(x) for x in d.get("loc") or [])
        msg = str(d.get("msg") or d.get("type") or "").strip()
        out.append(f"{loc}: {msg}" if loc and msg else (loc or msg))
    return [o for o in out if o]


def _request(method: str, path: str, params: dict | None = None,
             body: object | None = None) -> requests.Response:
    _throttle(path)
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

    Returns the parsed JSON body (`{}` for the body-less 201/204 answers of
    the write endpoints). A 401 re-authenticates once, a 429 waits as long as
    `Retry-After` says (our own linear back-off if the header is missing) and
    retries; every other non-2xx exits through the CLI's structured error.
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
        wait = _retry_after(resp)
        if wait is None:
            wait = 3 * (_retries + 1)
        elif wait > _RETRY_AFTER_MAX:
            _fail_msg(f"Fénix {method} {path} is rate-limited (429) and asks to "
                      f"wait {wait:.0f}s — try again after that.",
                      method=f"{method} {path}", httpStatus=429,
                      retryAfter=round(wait))
        print(f"Fénix rate limit (429), waiting {wait:.0f}s… "
              f"(retry {_retries + 1}/3)", file=sys.stderr)
        time.sleep(wait)
        return call(method, path, params, body, _retries=_retries + 1)

    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.status_code not in (200, 201, 202, 204, 206):
        lines = _error_lines(data)
        _fail_msg(f"Fénix {method} {path} returned HTTP {resp.status_code}"
                  + (": " + "; ".join(lines) if lines else "."),
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


def fetch_all_offset(path: str, params: dict,
                     page_limit: int = SKLIK_PAGE_LIMIT) -> list[dict]:
    """Read EVERY row of an offset-paged Fénix listing (the `/sklik/*` ones).

    Unlike `/nakupy/shop-items/` these page with plain `offset`/`limit` (max
    1000) and the response is just `{"items": […]}` — no cursor and no total
    count, exactly like DRAK's `*.list`. So the only complete read is to walk
    offsets until a short page comes back; same contract as `api._fetch_all`.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        data = call("GET", path, dict(params, limit=page_limit, offset=offset))
        page = data.get("items") or []
        rows.extend(page)
        if len(page) < page_limit:
            return rows
        offset += page_limit
        if len(rows) >= LIST_MAX_ITEMS:
            print(f"WARNING: {path} returned more than {LIST_MAX_ITEMS} rows; "
                  "the list is truncated. Narrow the query.", file=sys.stderr)
            return rows


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
        # A 429 names its own wait; 425 (still generating) keeps our cadence.
        wait = _retry_after(resp) if resp.status_code == 429 else None
        time.sleep(min(wait, _RETRY_AFTER_MAX) if wait is not None else delay)
        delay = min(delay + 2, 10)
