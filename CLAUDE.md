# Sklik Search App — CLI for Sklik DRAK API

Python CLI for managing PPC search & display campaigns on Seznam Sklik via the DRAK JSON API. Built to be driven by a human **and** by Claude Code: structured `--json` I/O, parseable errors, and a self-enforcing per-account request budget.

## Setup

```bash
source venv/bin/activate && python sklik_cli.py <command> [flags]
# or: ./run.sh <command> [flags]   (also on Windows/Git Bash: it picks venv/bin or venv/Scripts)
# opt-in, only when .env holds 1Password op:// references instead of tokens:
#     ./run-op.sh <command> [flags]     (= op run --env-file=.env -- ./run.sh …)
```

## Code structure

The implementation is a package under `sklik/`; `sklik_cli.py` is a thin entrypoint.

- `sklik/api.py` — **engine**: config, account/token discovery, auth + session cache, the cross-session **request budget** (rate limiting), `_api_call`, paging of list methods (`_fetch_all`, `_list_page_size`), and structured errors (`_fail` / `_fail_msg`).
- `sklik/fenix.py` — **engine for the Fénix REST API** (`api.sklik.cz/v1`; Seznam Nákupy + the `fenix-*` campaign commands): separate auth (`SKLIK_FENIX_REFRESH_TOKEN` → 1h access token cached per account+managed user in `.fenix_cache_<account>.json`), `fenix.call()` (honours `Retry-After` on 429), cursor paging (`fenix.fetch_all()`, Nákupy shop items) and offset paging (`fenix.fetch_all_offset()`, the `/sklik/*` listings), `poll_report()` for async stats. Reuses `api._fail_msg`. Only the `/nakupy/*` calls need a `premiseId` (shop) via `fenix.resolve_premise()`.
- `sklik/formatting.py` — CZK⇄haléře conversion + `_output_json`.
- `sklik/reports.py` — two-step report helper (`createReport` → `readReport`).
- `sklik/images.py` — image loading/base64 shared by combined ads and banners.
- `sklik/commands/*.py` — one module per domain (`account`, `campaigns`, `groups`, `keywords`, `ads`, `research`, `sitelinks`, `conversions`, `retargeting`, `banners`, `placements`, `nakupy`, `fenix_sklik`).
- `sklik/cli.py` — argparse wiring + dispatch.

Shared mutable state (`ACTIVE_ACCOUNT`, `_JSON_OUTPUT`, session) lives in `api.py` and changes only through `api.set_account()` / `api.set_json_output()`. Fénix keeps its own `ACTIVE_USER_ID` in `fenix.py` (`fenix.set_user_id()`), because there the managed account is chosen when the token is minted, not per call. Command modules read it via the `api` module — never `from sklik.api import ACTIVE_ACCOUNT`, which would copy a stale value. `BASE_DIR` in `api.py` resolves to the project root, so `.env` and the `.session_cache_*` / `.rate_limit_*` files stay where they were.

## Authentication & accounts

- Tokens in `.env`, one env var per login: `SKLIK_API_TOKEN` = the `default` account (used when `--account` is omitted); `SKLIK_API_TOKEN_<NAME>` = a named account (`--account <name>`, uppercased). Accounts are discovered at runtime — no names hardcoded.
- Session cached per account in `.session_cache_<account>.json` (25 min TTL); auto-reconnects on 401.
- **`--account <name>`** and **`--user-id <id>`** are independent global flags (before the subcommand). `--account` picks the login/token; `--user-id` acts on a MANAGED account under the active login (agency → client).
- **Fénix commands** (`feed-*`, `nakupy-*`, `shop-items`, `fenix-*`) use a **separate API and token**: `SKLIK_FENIX_REFRESH_TOKEN` / `_<NAME>` (a refresh token from the Sklik web UI, exchanged for a 1h access token). The Nákupy ones also need a `premiseId` (shop, not campaign): `--premise-id` or `SKLIK_FENIX_PREMISE` / `_<NAME>`; the `fenix-*` ones do not. The refresh token carries an access level (`r` / `rw` / `rwa`) — the `fenix-*` writes need `rw`; `fenix-me` shows the scopes actually granted. `cli.py` calls `fenix.check_config()` for these, never `api.check_config()`.
- **Password managers are opt-in and live outside the Python code.** The app only reads the environment, and `load_dotenv()` does not override variables that are already set — so anything that injects the token variables works. `./run-op.sh` is the worked example (1Password CLI: `.env` holds `op://vault/item/field` references, `op run` resolves them for one process); it hardcodes no account, set `OP_ACCOUNT` yourself when several are signed in. Started through plain `./run.sh`, an unresolved `op://…` value is caught by `api.check_config()` / `fenix.check_config()` (`_fail_if_secret_reference`) before any request. The short-lived session / access tokens still land in `.session_cache_*.json` / `.fenix_cache_*.json`. Never add a hard dependency on `op` — `./run.sh` with plain tokens must keep working unchanged.
- A token-less/unknown `--account` fails with an error listing the configured accounts. `suggest`/`suggest-stats` silently ignore `--user-id` (the API methods take no managed-user param) — call them without it.

## Price convention

CLI accepts/displays **CZK**; the API uses haléře (100 = 1 Kč). Conversion is automatic both ways.

**Fénix (Nákupy) is mostly the exception**: stats and shop-item CPCs are plain CZK floats, so the `sklik/formatting.py` helpers must NOT touch them. But `/nakupy/campaigns/` proxies DRAK, so **both** `budget.dayBudget` and `exhaustedDayBudget` there are haléře — the OpenAPI spec claims CZK for `dayBudget` and is wrong (verified against a live account through both APIs).

**`fenix-*` commands**: flags take CZK like everywhere else (`--day-budget`, `--cpc`, `--cpm`) and the human output prints Kč, but **`--json` is the raw API payload — `budget.dayBudget`, `exhaustedDayBudget`, `cpc`, `cpm` are haléře there**, unlike `campaigns --json` / `groups --json`, which convert to CZK. `fenix-credit` is plain CZK (`credit`, `creditWithVat`); its `agencyLimit` has no unit in the spec and is passed through unlabelled. Verified against a live account on 2026-10-02: `budget.dayBudget` and `cpc` are haléře, `credit` is CZK; `exhaustedDayBudget`, `cpm` and `agencyLimit` are still the spec's word only.

## Commands (114, grouped)

**Full flag reference + examples: [README.md](README.md).** Index:

- **Overview:** `account`, `api-limits`, `pulse` (warns when the window's stats aren't complete yet), `credit`, `regions`, `autotagging`, `autotagging-update`
- **Campaigns:** `campaigns`, `campaign-create/update/remove/restore/stats/targeting` — targeting: `--regions` (replaces the whole set; **cannot be cleared via the API**), `--device-bids` (whole percents only), `--schedule-json` (7×24 array, `null` clears), `--ad-selection {weighted,random,cpa,cos}`, `--start-date` / `--end-date` (`YYYY-MM-DD`; `none` clears on update)
- **Groups:** `groups`, `group-create/update/remove/restore/stats` — `--max-daily-impression` = frequency cap (the campaign-level cap is invisible to DRAK — read it with `fenix-campaigns`, write it with `fenix-campaign-update --capping-*`; the group cap wins where both are set); `group-stats` is the only entity returning `winRate`
- **Keywords:** `keywords`, `keyword-create`, `keyword-create-batch`, `keyword-update/remove/restore/stats`, **`keyword-set`** (declarative upsert; `--remove-others` = full sync)
- **Ads:** `ads`, `ad-create`, `combined-create`, `ad-update` (status only), **`ad-replace`** (safe atomic text change), `ad-remove`, `ad-restore`, `ad-stats`
- **Negatives:** `negatives`, `negative-add`, `negative-add-batch`, `negative-remove` — since DRAK 11.27.0 the remove takes `groupId` + `[{name, matchType}]` and hard-deletes (no IDs, no restore; `--keyword-id` is looked up first), and the create returns no IDs. `negatives` reports `broad/phrase/exact`, writes want `negativeBroad/…`
- **Research:** `suggest`, `suggest-stats` (chunked: the API takes ≤100 queries per call), `search-queries`
- **Sitelinks:** `sitelinks`, `sitelink-create/update/remove`, `sitelink-assign` (campaign/group; replaces the sitelinks, re-sends the assigned callouts — one shared set in the API), `sitelinks-assigned`
- **Callouts (popisky):** `callouts`, `callout-create/remove`, `callout-assign` (replaces the callouts, keeps the sitelinks; `--dry-run`), `callouts-assigned`. A callout is a `sitelinks.*` record without a URL; the CLI keeps the two apart.
- **Conversions:** `conversions`, `conversion-types`, `conversion-create/update/remove`
- **Lookalike audiences:** `lookalike-create` (`--source-list-id`, `--accuracy low|medium|high`) — modelling only runs while the source and the lookalike list are both attached to an active group
- **Retargeting:** `retargeting`, `retargeting-create/update/remove`, **`retargeting-attach/detach`** (audience ↔ group), `retargeting-attached`, **`retargeting-exclude`** (+`-remove`) — negative retargeting at campaign OR group level, `retargeting-excluded`
- **Banners:** `banner-formats`, `banners`, `banner-create`, `banner-download`, `banner-update`, `banner-remove`, `banner-restore`
- **Placements:** `placements`, `placement-create/remove`, `placements-excluded`, `placement-exclude` (+`-remove`/`-restore`) — negative placements
- **Display targeting:** `targeting-categories`, `targeting`, `targeting-add`, `targeting-exclude`, `targeting-remove`, `targeting-restore` — unified `--type interest/theme/intend`
- **Shared budgets:** `budgets`, `budget-create/update/remove` — campaign assignment lives on the budget; amounts in plain CZK
- **Nákupy / feed (Fénix API, separate token):** `feed-status`, `feed-diagnostics` (offer health), `nakupy-campaigns` (web/device/auction-type **bid multipliers**, unreadable via DRAK), `nakupy-stats` (`--split webType,deviceType,productType,conversionId` or `--by-category`; async report), `shop-items` (`--all`, `--unpaired`, `--product-detail` = auction position + CPC-to-win), `nakupy-item-stats` (per-product cost/conversions/PNO, `--no-conversion-cost`)
- **Campaigns via Fénix (same Fénix token, no premiseId; DRAK stays the default for everything it can do):** `fenix-me` (who the token acts as + scopes), `fenix-credit`, `fenix-accounts` (IDs for `--user-id`), `fenix-campaigns`, `fenix-groups --campaign-id`, `fenix-ads --campaign-id --group-id`, **`fenix-negatives --campaign-id [--group-id]`** (lists CAMPAIGN-level negatives — DRAK cannot), `fenix-campaign-create` (created **paused** unless `--status active`), `fenix-group-create`, `fenix-ad-create` (ETA) — all three with `--dry-run` = API `dryRun=true` — and `fenix-negative-add` / `fenix-negative-remove` (by text + match type, `--confirm`; their `--dry-run` is a local preview only); **`fenix-campaign-update`** (status, day/total budget, start/end date, campaign-level `capping`, `excludedUrls`) and **`fenix-ad-update`** (status, start/end date, banner/branding name; any ad type incl. banners, several `--ad-id` of one group) — PATCH with `--dry-run` = API `dryRun=true`. The PATCH body needs the entity's `type`: looked up unless `--type` is given (campaign lookup sends `ids`, not the spec's `id` — the live API validates `ids`)

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
- **Fénix `maxCpcMultiplier` is a signed modifier, exactly like DRAK `devicesPriceRatio`** — 0 = no change, `+20` = +20 %, `-100` = off; the value copies from `nakupy-campaigns` into `campaign-update --device-bids` unconverted. The name and the OpenAPI spec say "multiplier, 100 = no change" and are wrong (live values are small signed deltas, and a multiplier cannot be `-100`). **Placements without a modifier are omitted from the response entirely** — absence means "no change", so never test for a neutral `100`. Only device modifiers are writable at all — web and auction-type ones are web-UI only, in both APIs.
- **`fenix-*`: the reads are verified live, the writes are not** (Fénix OpenAPI 1.30.0, live run 2026-10-02). Verified: `fenix-me`, `fenix-credit`, `fenix-accounts`, `fenix-campaigns`, `fenix-groups`, `fenix-negatives --campaign-id`, and `fenix-campaign-create --dry-run` (valid payload → 2xx, nothing persisted; invalid → 422 naming the field). **Never run live:** any create without `--dry-run`, the group/ad dry run, `fenix-negative-add` / `-remove`, `fenix-ads`. Treat the first real write as a test: `fenix-me` first, then a `--dry-run`. Entity IDs are the same in both APIs. Three things differ from the DRAK commands: (1) **`--dry-run` on `fenix-campaign-create` / `-group-create` / `-ad-create` is a real server-side validation** (`dryRun=true`, nothing persisted), but on **`fenix-negative-add` / `-remove` it only prints the request and sends nothing** — those endpoints have no `dryRun` in the spec, so nothing is validated; (2) **negative keywords have no IDs in Fénix** — remove takes `--name` + `--match-type` and is permanent; the broad match type is `negative` (DRAK's `negativeBroad` is accepted as an alias; confirmed live — DRAK-written `negativeBroad` reads back as `negative`); (3) **`--json` money is haléře** (see Price convention). Fénix has no positive keywords, keyword suggestions or search-query reports — keep using the DRAK commands for those, and for anything DRAK already does reliably.
- **The API is strict about payload shapes and scalar types** — a struct where it wants a struct, an `int` where it wants an `int`. A bare int in an array of structs (`regions`) or a float in an int field (`devicesPriceRatio`) is a hard `400`, not a coercion. When adding or changing a write payload, verify the shape against [docs/api-notes.md](docs/api-notes.md) / the DRAK docs — and for campaigns use **`campaigns.check`** (and `ads.check` for ads): same payload, no writes, one request. This class of bug shipped undetected in `--regions` / `--device-bids` / `--schedule-json` until v1.8.1.

Full API behaviour, quirks, rate-limit internals and status codes: **[docs/api-notes.md](docs/api-notes.md)**.

## Release checklist

Bump `__version__` in `sklik/__init__.py` → update README (version line + command tables), CLAUDE.md (command count/index), CHANGELOG.md (new `## [x.y.z] — YYYY-MM-DD` entry), bundled skill → run `python scripts/check_docs_consistency.py` and `python -m unittest discover -s tests` (both must pass) → commit → tag `vX.Y.Z` → **GitHub Release from the tag** (`gh release create vX.Y.Z --latest --title "vX.Y.Z — <changelog headline>"`, notes = the CHANGELOG entry). A pushed tag alone does NOT show on /releases and subscribers get no notification — the release step is mandatory, not optional.

## Documentation map

- **[README.md](README.md)** — full command reference, flags, worked examples.
- **[docs/api-notes.md](docs/api-notes.md)** — how the DRAK API actually behaves (endpoints, report quirks, ad/banner/conversion/retargeting specifics, rate limits, status codes), plus the Fénix API section (spec 1.30.0: what is verified live vs. spec-only, rate limits, open ambiguities).
- **[CHANGELOG.md](CHANGELOG.md)** — version history.
- **`skill/sklik-ppc/`** — the bundled Claude Code skill (`/sklik-ppc`): strategy, campaign structure, display rules.

## README language

README.md is Czech only on purpose: Sklik is a Czech-only platform. Author links: faborsky.cz + aifirst.cz.
