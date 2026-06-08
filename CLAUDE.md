# Sklik Search App — CLI for Sklik DRAK API

Python CLI for managing PPC search campaigns on Seznam Sklik via the DRAK JSON API.

## Setup

```bash
source venv/bin/activate && python sklik_cli.py <command> [flags]
# or: ./run.sh <command> [flags]
```

## Authentication

- Tokens in `.env`, one env var per login:
  - `SKLIK_API_TOKEN` — the `default` account (used when `--account` is omitted)
  - `SKLIK_API_TOKEN_<NAME>` — a named account, selected with `--account <name>`
- Accounts are discovered from the environment at runtime — no names are hardcoded.
- Session cached per account in `.session_cache_<account>.json` (25 min TTL)
- Auto-reconnects on 401 (expired session)

## Accounts

Each account is a SEPARATE Sklik login with its own token. Two independent global flags (before the subcommand):

- **`--account <name>`** — which token/login to use. Omitted = `default` (`SKLIK_API_TOKEN`); `--account <name>` reads `SKLIK_API_TOKEN_<NAME>` (uppercased).
- **`--user-id <id>`** — a MANAGED account under the active login (e.g. agency → client account).

A token-less or unknown `--account` fails with an error listing the configured accounts.

The `suggest` and `suggest-stats` commands don't support `--user-id` (but do accept `--account`).

## Price Convention

- **CLI accepts/displays prices in CZK** (Kč)
- API uses haléře internally (100 haléřů = 1 Kč)
- CLI converts automatically in both directions

## Commands Reference

### Account
| Command | Description |
|---------|-------------|
| `account` | Account info, wallet balance, managed accounts |

### Campaigns
| Command | Key Flags |
|---------|-----------|
| `campaigns` | `--status active/suspend`, `--json` |
| `campaign-create` | `--name`, `--day-budget` (CZK), `--type fulltext`, `--json` |
| `campaign-update` | `--campaign-id`, `--name`, `--day-budget`, `--status`, `--json` |
| `campaign-remove` | `--campaign-id`, `--confirm`, `--json` |
| `campaign-stats` | `--campaign-id`, `--date-from`, `--date-to`, `--json` |
| `campaign-targeting` | `--campaign-id`, `--json` (shows geo/device/schedule) |

**Campaign targeting** (`campaign-create` / `campaign-update`):
- `--regions` — comma-separated region IDs for geo targeting (empty string on update clears them)
- `--device-bids` — `desktop:mobile:tablet:other` % modifiers, e.g. `0:-30:-30:-100`
- `--schedule-json` (update only) — `{"daySchedule":[{"value":[24 hourly 0-100]}, …×7]}`

### Groups (ad groups)
| Command | Key Flags |
|---------|-----------|
| `groups` | `--campaign-id`, `--json` |
| `group-create` | `--campaign-id`, `--name`, `--cpc` (CZK), `--json` |
| `group-update` | `--group-id`, `--name`, `--cpc`, `--status`, `--json` |
| `group-remove` | `--group-id`, `--confirm`, `--json` |
| `group-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--json` |

### Keywords
| Command | Key Flags |
|---------|-----------|
| `keywords` | `--group-id`, `--campaign-id`, `--json` |
| `keyword-create` | `--group-id`, `--name`, `--match-type broad/phrase/exact`, `--cpc` (CZK), `--json` |
| `keyword-create-batch` | `--group-id`, `--keywords-json` (JSON array), `--json` |
| `keyword-update` | `--keyword-id`, `--cpc`, `--status`, `--url`, `--json` |
| `keyword-remove` | `--keyword-id`, `--confirm`, `--json` |
| `keyword-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--json` |

### Ads
| Command | Key Flags |
|---------|-----------|
| `ads` | `--group-id`, `--json` |
| `ad-create` | `--group-id`, `--headline1`, `--headline2`, `--headline3`, `--description1`, `--description2`, `--final-url`, `--path1`, `--path2`, `--json` |
| `ad-update` | `--ad-id`, `--status`, `--json` |
| `ad-remove` | `--ad-id`, `--confirm`, `--json` |
| `ad-stats` | `--group-id`, `--date-from`, `--date-to`, `--json` |

### Negative Keywords
| Command | Key Flags |
|---------|-----------|
| `negatives` | `--group-id`, `--campaign-id`, `--json` |
| `negative-add` | `--group-id`, `--name`, `--match-type negativeBroad/negativePhrase/negativeExact`, `--json` |
| `negative-add-batch` | `--group-id`, `--keywords-json`, `--json` |
| `negative-remove` | `--keyword-id`, `--confirm`, `--json` |

### Keyword Research
| Command | Key Flags |
|---------|-----------|
| `suggest` | `--query`, `--limit`, `--related`, `--order-by avgSearchCount/cpc/score`, `--json` |
| `suggest-stats` | `--queries` (comma-separated), `--granularity monthly/daily`, `--json` |

### Search Queries
| Command | Key Flags |
|---------|-----------|
| `search-queries` | `--campaign-id`, `--group-id`, `--date-from`, `--date-to`, `--limit`, `--json` |

### Sitelinks
| Command | Key Flags |
|---------|-----------|
| `sitelinks` | `--json` |
| `sitelink-create` | `--name`, `--url`, `--json` |
| `sitelink-remove` | `--sitelink-id`, `--confirm`, `--json` |

### Conversions (conversion-tracking definitions)
A conversion = a named definition of a desired action (purchase, signup…) and its value. The CLI manages the definitions; measurement (pixel/SEM) lives on the website.
| Command | Key Flags |
|---------|-----------|
| `conversions` | `--json` |
| `conversion-types` | `--json` (type IDs in use; see SEM note) |
| `conversion-create` | `--name`, `--type-id`, `--value` (CZK), `--color`, `--json` |
| `conversion-update` | `--conversion-id`, `--name`, `--value`, `--color`, `--json` |
| `conversion-remove` | `--conversion-id`, `--confirm`, `--json` |

### Retargeting (audience lists)
| Command | Key Flags |
|---------|-----------|
| `retargeting` | `--json` |
| `retargeting-create` | `--name`, `--membership` (days), `--description`, `--use-historic`, `--take-all-users`, `--conditions-json`, `--json` |
| `retargeting-update` | `--list-id`, `--name`, `--membership`, `--description`, `--json` |
| `retargeting-remove` | `--list-id`, `--confirm`, `--json` |

### Image Banners (context/display network — static jpg/png/gif, not HTML5)
| Command | Key Flags |
|---------|-----------|
| `banner-formats` | `--json` (allowed dimensions + size limits) |
| `banners` | `--group-id`, `--json` |
| `banner-create` | `--group-id`, `--name`, `--clickthru-url`, `--image` (local path OR http URL), `--status`, `--json` |
| `banner-remove` | `--banner-id`, `--confirm`, `--json` |

## Safety Rules

- All destructive operations (`*-remove`) require `--confirm` flag
- Always use `--json` flag when parsing output programmatically
- Default date range for stats is last 30 days

## Batch Format Examples

**keyword-create-batch:**
```json
[{"name": "kurz ai", "matchType": "phrase", "cpc": 15.0}, {"name": "ai školení", "matchType": "broad"}]
```

**negative-add-batch:**
```json
[{"name": "zdarma", "matchType": "negativeBroad"}, {"name": "free", "matchType": "negativeBroad"}]
```
Or simple array: `["zdarma", "free", "zadarmo"]` (defaults to negativeBroad).

## API Notes

- **Endpoint pinned to v5**: `https://api.sklik.cz/drak/json/v5` (not the unpinned `.../drak/json`, which silently follows the newest version and could break on a major bump).
- Protocol: JSON-RPC POST to `https://api.sklik.cz/drak/json/v5/{method}`
- Params sent as JSON array: `[userStruct, ...params]`
- Reports are two-step: `createReport` (dates in restriction) → `readReport` (pagination + columns)
- Campaign budget is nested as `budget.dayBudget` in list responses but flat `dayBudget` in create
- Ad updates that change creative fields create a new ad (returns `newAdIds`)
- Keyword `name` and `matchType` cannot be updated — must remove and recreate
- **Filtering**: API does NOT support parent-entity filters (`campaign.ids`, `group.ids`, `status`) in `restrictionFilter`. Only `ids` (own entity IDs), `isDeleted`, and `dateFrom`/`dateTo` (for reports) work. All `--campaign-id`, `--group-id`, `--status` filters are applied client-side.
- **Diagnostics**: Can be a dict `{"operation": {...}, "problems": [...]}` or a list of dicts — handle both formats
- **Negative keywords**: Group-level via `keywords.negative.create` (requires `groupId`). Campaign-level via `campaigns.update` with `negativeKeywords` array (requires `type` field). CLI handles both via `--group-id` or `--campaign-id`.
- **campaigns.update quirk**: `type` field is ALWAYS required in the update payload (for any field change, not just negativeKeywords). CLI auto-fetches it before updating.
- **Targeting fields** (on campaign objects): `regions` (array of `{id,name}`), `devicesPriceRatio` (`{desktop,mobile,tablet,other}` as % modifiers), `schedule` (`{daySchedule:[{value:[24 hourly 0-100]}, …×7]}`, week starts Monday). Settable via `campaigns.create`/`update`.
- **Conversions**: `conversions.list` takes ONLY the user struct (no restriction/displayColumns). Value in haléře. **SEM caveat**: accounts with Seznam Event Measurement activated cannot use `conversions.*` — CLI prints a friendly hint instead of crashing. `listConversionTypes` is currently broken server-side (HTTP 500), so `conversion-types` derives types from existing conversions instead.
- **Retargeting**: list objects use `listId` (not `id`); create/update nest editable fields under `attributes` (`name`, `membership`, `useHistoricData`, `takeAllUsers`, `description`). `retargeting.lists.list` takes only the user struct.
- **Banners**: `banners.create` takes the image bytes directly in `file` (base64 over JSON) — NOT an image-id; CLI base64-encodes a local path or downloads a URL. Required fields: `groupId`, `name`, `clickthruUrl`, `file`. List/return quirks: list columns use `bannerName`/`adStatus` (not `name`/`status`); `banners.create` returns `bannerIds` as `[{"id":…,"requestId":…}]` (CLI normalises to ints). Allowed formats via `images.constraints.list` (fixed sizes, ≤250 KB). The separate `images.*` namespace (URL + metadata, Sklik downloads) is NOT used.
