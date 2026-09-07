# Sklik Search App — CLI for Sklik DRAK API

Python CLI for managing PPC search & display campaigns on Seznam Sklik via the DRAK JSON API. Built to be driven by a human **and** by Claude Code: structured `--json` I/O, parseable errors, and a self-enforcing per-account request budget.

## Setup

```bash
source venv/bin/activate && python sklik_cli.py <command> [flags]
# or: ./run.sh <command> [flags]
```

## Code structure

The implementation is a package under `sklik/`; `sklik_cli.py` is a thin entrypoint.

- `sklik/api.py` — **engine**: config, account/token discovery, auth + session cache, the cross-session **request budget** (rate limiting), `_api_call`, paging of list methods (`_fetch_all`, `_list_page_size`), and structured errors (`_fail` / `_fail_msg`).
- `sklik/fenix.py` — **engine for the Fénix REST API** (`api.sklik.cz/v1`, Seznam Nákupy): separate auth (`SKLIK_FENIX_REFRESH_TOKEN` → 1h access token cached per account+managed user in `.fenix_cache_<account>.json`), `fenix.call()`, cursor paging (`fenix.fetch_all()`), `poll_report()` for async stats. Reuses `api._fail_msg`. Needs a `premiseId` (shop) via `fenix.resolve_premise()`.
- `sklik/formatting.py` — CZK⇄haléře conversion + `_output_json`.
- `sklik/reports.py` — two-step report helper (`createReport` → `readReport`).
- `sklik/images.py` — image loading/base64 shared by combined ads and banners.
- `sklik/commands/*.py` — one module per domain (`account`, `campaigns`, `groups`, `keywords`, `ads`, `research`, `sitelinks`, `conversions`, `retargeting`, `banners`, `placements`, `nakupy`).
- `sklik/cli.py` — argparse wiring + dispatch.

Shared mutable state (`ACTIVE_ACCOUNT`, `_JSON_OUTPUT`, session) lives in `api.py` and changes only through `api.set_account()` / `api.set_json_output()`. Fénix keeps its own `ACTIVE_USER_ID` in `fenix.py` (`fenix.set_user_id()`), because there the managed account is chosen when the token is minted, not per call. Command modules read it via the `api` module — never `from sklik.api import ACTIVE_ACCOUNT`, which would copy a stale value. `BASE_DIR` in `api.py` resolves to the project root, so `.env` and the `.session_cache_*` / `.rate_limit_*` files stay where they were.

## Authentication & accounts

- Tokens in `.env`, one env var per login: `SKLIK_API_TOKEN` = the `default` account (used when `--account` is omitted); `SKLIK_API_TOKEN_<NAME>` = a named account (`--account <name>`, uppercased). Accounts are discovered at runtime — no names hardcoded.
- Session cached per account in `.session_cache_<account>.json` (25 min TTL); auto-reconnects on 401.
- **`--account <name>`** and **`--user-id <id>`** are independent global flags (before the subcommand). `--account` picks the login/token; `--user-id` acts on a MANAGED account under the active login (agency → client).
- **Fénix commands** (`feed-*`, `nakupy-*`, `shop-items`) use a **separate API and token**: `SKLIK_FENIX_REFRESH_TOKEN` / `_<NAME>` (a refresh token from the Sklik web UI, exchanged for a 1h access token). They also need a `premiseId` (shop, not campaign): `--premise-id` or `SKLIK_FENIX_PREMISE` / `_<NAME>`. `cli.py` calls `fenix.check_config()` for these, never `api.check_config()`.
- A token-less/unknown `--account` fails with an error listing the configured accounts. `suggest`/`suggest-stats` silently ignore `--user-id` (the API methods take no managed-user param) — call them without it.

## Price convention

CLI accepts/displays **CZK**; the API uses haléře (100 = 1 Kč). Conversion is automatic both ways.

**Fénix (Nákupy) is the exception**: it sends plain CZK floats, so the `sklik/formatting.py` helpers must NOT touch those values. One field bucks even that — the campaign's `exhaustedDayBudget` is in haléře while its `budget.dayBudget` is in CZK.

## Commands (93, grouped)

**Full flag reference + examples: [README.md](README.md).** Index:

- **Overview:** `account`, `api-limits`, `pulse` (warns when the window's stats aren't complete yet), `credit`, `regions`, `autotagging`, `autotagging-update`
- **Campaigns:** `campaigns`, `campaign-create/update/remove/restore/stats/targeting` — targeting: `--regions` (replaces the whole set; **cannot be cleared via the API**), `--device-bids` (whole percents only), `--schedule-json` (7×24 array, `null` clears), `--ad-selection {weighted,random,cpa,cos}`
- **Groups:** `groups`, `group-create/update/remove/restore/stats` — `--max-daily-impression` = frequency cap (the campaign-level cap in the web UI is invisible to the API, and the group cap wins where both are set); `group-stats` is the only entity returning `winRate`
- **Keywords:** `keywords`, `keyword-create`, `keyword-create-batch`, `keyword-update/remove/restore/stats`, **`keyword-set`** (declarative upsert; `--remove-others` = full sync)
- **Ads:** `ads`, `ad-create`, `combined-create`, `ad-update` (status only), **`ad-replace`** (safe atomic text change), `ad-remove`, `ad-restore`, `ad-stats`
- **Negatives:** `negatives`, `negative-add`, `negative-add-batch`, `negative-remove`
- **Research:** `suggest`, `suggest-stats`, `search-queries`
- **Sitelinks:** `sitelinks`, `sitelink-create/update/remove`, `sitelink-assign` (campaign/group; REPLACES the whole set), `sitelinks-assigned`
- **Conversions:** `conversions`, `conversion-types`, `conversion-create/update/remove`
- **Retargeting:** `retargeting`, `retargeting-create/update/remove`, **`retargeting-attach/detach`** (audience ↔ group), `retargeting-attached`, **`retargeting-exclude`** (+`-remove`) — negative retargeting at campaign OR group level, `retargeting-excluded`
- **Banners:** `banner-formats`, `banners`, `banner-create`, `banner-download`, `banner-update`, `banner-remove`, `banner-restore`
- **Placements:** `placements`, `placement-create/remove`, `placements-excluded`, `placement-exclude` (+`-remove`/`-restore`) — negative placements
- **Display targeting:** `targeting-categories`, `targeting`, `targeting-add`, `targeting-exclude`, `targeting-remove`, `targeting-restore` — unified `--type interest/theme/intend`
- **Shared budgets:** `budgets`, `budget-create/update/remove` — campaign assignment lives on the budget; amounts in plain CZK
- **Nákupy / feed (Fénix API, separate token):** `feed-status`, `feed-diagnostics` (offer health), `nakupy-campaigns` (web/device/auction-type **bid multipliers**, unreadable via DRAK), `nakupy-stats` (`--split webType,deviceType,productType,conversionId` or `--by-category`; async report), `shop-items` (`--all`, `--unpaired`, `--product-detail` = auction position + CPC-to-win)

## Safety

- Destructive ops (`*-remove`) require `--confirm`.
- Parse programmatic output with `--json`; on failure the error comes back as `{"error": …}` on **stdout** (human text on stderr otherwise).
- The CLI self-enforces the account's request budget — don't fan out hundreds of parallel write calls or tight-retry loops.
- Default stats window = last 30 days; `--granularity {total,daily,weekly,monthly,quarterly,yearly}` splits it by period.
- **Stat columns differ per report entity** — request them via `stat_columns(entity)` from `sklik/reports.py`, never a shared list; an unsupported column fails the whole `readReport` with 400.
- Report ratios (`ctr`, `winRate`, `exhaustedBudgetShare`) are fractions 0–1 in `--json`; only the human output renders them as %.

## ⚠️ Critical for automation (read before scripting writes)

- **Change ad text with `ad-replace`, NEVER `ad-remove` + `ad-create` by hand.** `ads.update` does an atomic delete-old + create-new server-side, so a failed validation keeps the original ad; a manual remove+create silently drops the ad when the create fails (this caused a real production incident). Combined/banner "replace" = create-first, then remove.
- **Filtering is client-side.** The API ignores parent-entity filters (`campaign.ids`/`group.ids`/`status`) in restrictions; `--campaign-id`/`--group-id`/`--status` filter locally after fetch — over the **complete** set since v1.9.0 (before that the filter ran on a truncated first page).
- **Listings and reports are fully paged — never add a hardcoded `limit`.** `*.list` returns no total count and silently gives you the first page only, so a fixed limit truncates every account bigger than that number (`campaigns` was capped at 100, `ads`/`groups`/`banners` at 500 until v1.9.0 — Jindra's own account already had 521 ads and showed 500). Read through **`api._fetch_all()`** (list methods) and **`_fetch_report`/`_fetch_listing_report`** (reports); both walk offsets to the end. Single-entity lookups (`{"ids": [x]}`, `limit: 1`) are the one legitimate fixed limit — never scan a whole listing to find one row.
- **Audiences attach to groups via `retargeting-attach`/`retargeting-detach`/`retargeting-attached`** (v1.6.0; `retargeting.group.lists.*`). Attaching a **deleted** list fails with a bare `406 Bad values` — check `deleted` in `retargeting --json` first.
- **Soft-delete quirks**: re-adding a removed display-targeting category → `409 entity_already_exists` (use `targeting-restore`); re-excluding a removed negative placement → `group_pattern_duplicity` (use `placement-exclude-restore`). `placements-excluded` cannot show the pattern text (API never returns it).
- **Batch writes are all-or-nothing**; split payloads over the per-method cap (typically ≤100 for create/update/remove). Check caps with `api-limits`.
- **Fénix `maxCpcMultiplier` is a multiplier, DRAK `devicesPriceRatio` is a modifier.** Fénix: 100 = no change, 120 = +20 %. DRAK: 0 = no change, 20 = +20 %. Copying a number from `nakupy-campaigns` into `campaign-update --device-bids` without subtracting 100 sets a wildly wrong bid. Only device multipliers are writable at all — web and auction-type ones are web-UI only, in both APIs.
- **The API is strict about payload shapes and scalar types** — a struct where it wants a struct, an `int` where it wants an `int`. A bare int in an array of structs (`regions`) or a float in an int field (`devicesPriceRatio`) is a hard `400`, not a coercion. When adding or changing a write payload, verify the shape against [docs/api-notes.md](docs/api-notes.md) / the DRAK docs — and for campaigns use **`campaigns.check`** (and `ads.check` for ads): same payload, no writes, one request. This class of bug shipped undetected in `--regions` / `--device-bids` / `--schedule-json` until v1.8.1.

Full API behaviour, quirks, rate-limit internals and status codes: **[docs/api-notes.md](docs/api-notes.md)**.

## Release checklist

Bump `__version__` in `sklik/__init__.py` → update README (version line + command tables), CLAUDE.md (command count/index), CHANGELOG.md (new `## [x.y.z] — YYYY-MM-DD` entry), bundled skill → run `python scripts/check_docs_consistency.py` (must pass) → commit → tag `vX.Y.Z` → **GitHub Release from the tag** (`gh release create vX.Y.Z --latest --title "vX.Y.Z — <changelog headline>"`, notes = the CHANGELOG entry). A pushed tag alone does NOT show on /releases and subscribers get no notification — the release step is mandatory, not optional.

## Documentation map

- **[README.md](README.md)** — full command reference, flags, worked examples.
- **[docs/api-notes.md](docs/api-notes.md)** — how the DRAK API actually behaves (endpoints, report quirks, ad/banner/conversion/retargeting specifics, rate limits, status codes).
- **[CHANGELOG.md](CHANGELOG.md)** — version history.
- **`skill/sklik-ppc/`** — the bundled Claude Code skill (`/sklik-ppc`): strategy, campaign structure, display rules.
