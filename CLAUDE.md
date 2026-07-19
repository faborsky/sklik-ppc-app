# Sklik Search App — CLI for Sklik DRAK API

Python CLI for managing PPC search & display campaigns on Seznam Sklik via the DRAK JSON API. Built to be driven by a human **and** by Claude Code: structured `--json` I/O, parseable errors, and a self-enforcing per-account request budget.

## Setup

```bash
source venv/bin/activate && python sklik_cli.py <command> [flags]
# or: ./run.sh <command> [flags]
```

## Code structure

The implementation is a package under `sklik/`; `sklik_cli.py` is a thin entrypoint.

- `sklik/api.py` — **engine**: config, account/token discovery, auth + session cache, the cross-session **request budget** (rate limiting), `_api_call`, and structured errors (`_fail` / `_fail_msg`).
- `sklik/formatting.py` — CZK⇄haléře conversion + `_output_json`.
- `sklik/reports.py` — two-step report helper (`createReport` → `readReport`).
- `sklik/images.py` — image loading/base64 shared by combined ads and banners.
- `sklik/commands/*.py` — one module per domain (`account`, `campaigns`, `groups`, `keywords`, `ads`, `research`, `sitelinks`, `conversions`, `retargeting`, `banners`, `placements`).
- `sklik/cli.py` — argparse wiring + dispatch.

Shared mutable state (`ACTIVE_ACCOUNT`, `_JSON_OUTPUT`, session) lives in `api.py` and changes only through `api.set_account()` / `api.set_json_output()`. Command modules read it via the `api` module — never `from sklik.api import ACTIVE_ACCOUNT`, which would copy a stale value. `BASE_DIR` in `api.py` resolves to the project root, so `.env` and the `.session_cache_*` / `.rate_limit_*` files stay where they were.

## Authentication & accounts

- Tokens in `.env`, one env var per login: `SKLIK_API_TOKEN` = the `default` account (used when `--account` is omitted); `SKLIK_API_TOKEN_<NAME>` = a named account (`--account <name>`, uppercased). Accounts are discovered at runtime — no names hardcoded.
- Session cached per account in `.session_cache_<account>.json` (25 min TTL); auto-reconnects on 401.
- **`--account <name>`** and **`--user-id <id>`** are independent global flags (before the subcommand). `--account` picks the login/token; `--user-id` acts on a MANAGED account under the active login (agency → client).
- A token-less/unknown `--account` fails with an error listing the configured accounts. `suggest`/`suggest-stats` silently ignore `--user-id` (the API methods take no managed-user param) — call them without it.

## Price convention

CLI accepts/displays **CZK**; the API uses haléře (100 = 1 Kč). Conversion is automatic both ways.

## Commands (88, grouped)

**Full flag reference + examples: [README.md](README.md).** Index:

- **Overview:** `account`, `api-limits`, `pulse` (warns when the window's stats aren't complete yet), `credit`, `regions`, `autotagging`, `autotagging-update`
- **Campaigns:** `campaigns`, `campaign-create/update/remove/restore/stats/targeting` — targeting: `--regions`, `--device-bids`, `--schedule-json`, `--ad-selection {weighted,random,cpa,cos}`
- **Groups:** `groups`, `group-create/update/remove/restore/stats` — `--max-daily-impression` = frequency cap
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

## Safety

- Destructive ops (`*-remove`) require `--confirm`.
- Parse programmatic output with `--json`; on failure the error comes back as `{"error": …}` on **stdout** (human text on stderr otherwise).
- The CLI self-enforces the account's request budget — don't fan out hundreds of parallel write calls or tight-retry loops.
- Default stats window = last 30 days.

## ⚠️ Critical for automation (read before scripting writes)

- **Change ad text with `ad-replace`, NEVER `ad-remove` + `ad-create` by hand.** `ads.update` does an atomic delete-old + create-new server-side, so a failed validation keeps the original ad; a manual remove+create silently drops the ad when the create fails (this caused a real production incident). Combined/banner "replace" = create-first, then remove.
- **Filtering is client-side.** The API ignores parent-entity filters (`campaign.ids`/`group.ids`/`status`) in restrictions; `--campaign-id`/`--group-id`/`--status` filter locally after fetch.
- **Audiences attach to groups via `retargeting-attach`/`retargeting-detach`/`retargeting-attached`** (v1.6.0; `retargeting.group.lists.*`). Attaching a **deleted** list fails with a bare `406 Bad values` — check `deleted` in `retargeting --json` first.
- **Soft-delete quirks**: re-adding a removed display-targeting category → `409 entity_already_exists` (use `targeting-restore`); re-excluding a removed negative placement → `group_pattern_duplicity` (use `placement-exclude-restore`). `placements-excluded` cannot show the pattern text (API never returns it).
- **Batch writes are all-or-nothing**; split payloads over the per-method cap (typically ≤100 for create/update/remove). Check caps with `api-limits`.

Full API behaviour, quirks, rate-limit internals and status codes: **[docs/api-notes.md](docs/api-notes.md)**.

## Release checklist

Bump `__version__` in `sklik/__init__.py` → update README (version line + command tables), CLAUDE.md (command count/index), CHANGELOG.md (new `## [x.y.z] — YYYY-MM-DD` entry), bundled skill → run `python scripts/check_docs_consistency.py` (must pass) → commit → tag `vX.Y.Z`.

## Documentation map

- **[README.md](README.md)** — full command reference, flags, worked examples.
- **[docs/api-notes.md](docs/api-notes.md)** — how the DRAK API actually behaves (endpoints, report quirks, ad/banner/conversion/retargeting specifics, rate limits, status codes).
- **[CHANGELOG.md](CHANGELOG.md)** — version history.
- **`skill/sklik-ppc/`** — the bundled Claude Code skill (`/sklik-ppc`): strategy, campaign structure, display rules.
