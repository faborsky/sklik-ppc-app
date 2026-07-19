# Sklik Display & Banner Campaign Rules

Reference for managing display (content network) and remarketing campaigns with banner ads on Sklik.

## Campaign Types

### Content Network (`type: context`)
- Banners shown on Seznam partner sites (content network)
- Bidding: **CPT** (cost per thousand impressions) or CPC
- Good for: brand awareness, broad reach, product visibility
- Typical daily budget: 50–300 Kč
- CPT bidding (`maxCpt`) is set in the **Sklik web UI only** — the CLI exposes just `--cpc` on groups

### Remarketing
- Target users who already visited your site
- Full flow is CLI-only: `retargeting-create` (audience) → `retargeting-attach --list-id L --group-id X` → verify with `retargeting-attached`
- Higher CTR expected (0.3%+) due to a warmer audience
- Typical daily budget: 30–150 Kč
- Usually CPC bidding

### Other display targeting (all attach to the GROUP)
- **Placements**: `placement-create` (target specific websites) / `placement-exclude` (ban websites — the API won't list excluded pattern texts back, note them down)
- **Interests / themes / intents**: `targeting-add` / `targeting-exclude` with `--type interest/theme/intend`; category catalog via `targeting-categories`
- Combine: e.g. theme targeting + excluded placements + frequency cap (`group-update --max-daily-impression`)

## Placement Targeting (Umístění) — patterns.* API

Targeting specific websites in the content network is FULLY supported via API (the `patterns.*` namespace; CLI: `placements`, `placement-create`, `placement-remove`).

- A placement pattern is a URL string attached to a **group**: `"forbes.cz"`, `"mediar.cz"`, or with a path `"www.e15.cz/byznys"` (section-level targeting).
- Optional per-placement `--cpc` overrides the group CPC.
- There is no `patterns.list` — the CLI lists placements via the report API (`patterns.createReport`/`readReport`).
- Negative placements (excluded sites) exist in the API (`patterns.negative.*`) but are not wrapped in the CLI yet.
- **A new display group has NO placements = serves network-wide.** Add placements before activating when per-web targeting is intended.
- One campaign per web (with its own `--day-budget`) is the cleanest structure when each placement needs its own budget.

## Combined (Native) Ads — Kombinovaná reklama

The display-network ad type that also serves as **native advertising inside articles** on Seznam content sites. Sklik automatically composes the rendering (native in-article, responsive banner slots, branding strips) from the supplied assets — you don't pick the placement format.

### Why use it alongside banners
- Reaches native in-article placements that fixed-size banners can never fill
- One ad covers all responsive slots — no need for 7 sizes
- Typically cheaper inventory than premium banner positions

### API support (full, via `ads.*`)
- `ads.create` with `adType: combined` — CLI command `combined-create`
- Listed by `ads.list` (CLI `ads`), stats via the ads report (CLI `ad-stats`, `adType: combined`)
- No content-update command for combined ads. To change one: **create the new ad first (`combined-create`), verify, then `ad-remove` the old** — create-first ordering so a failed create never drops the ad. (Text-only eta ads have a safe one-shot `ad-replace`; combined does not, because of the images.)

### Required assets
| Field | Limit |
|-------|-------|
| Short headline (`shortLine`) | max 25 chars |
| Long headline (`longLine`) | max 90 chars |
| Description | max 90 chars |
| Company name | max 25 chars |
| Landscape image | 1.91:1, min 600×314 px, recommended 1200×628, max 1 MB |
| Square image | 1:1, min 300×300 px, recommended 1200×1200, max 1 MB |

Optional: square logo (1:1, min 128×128), landscape logo (4:1, min 512×128), main/accent color (hex), mobile final URL, tracking template.

### Gotchas
- **Forbidden characters are stripped silently** — e.g. em dash "—" disappears from headlines without any warning. Always verify final texts with `ads --json` after creation.
- Logos: either the square or the landscape logo is shown, never both; display is not guaranteed.
- Texts must read naturally in native context (the ad looks like an article teaser) — avoid hard banner-style "CLICK NOW" copy.

## Banner API Specifics

### Namespace
Banners use `banners.*` API methods (separate from `ads.*` for text ads):
- `banners.list`, `banners.create`, `banners.update`, `banners.remove`, `banners.restore`
- `banners.createReport` / `banners.readReport` for stats
- `banners.check` for validation before upload

### CRITICAL: HTML5 vs Image Banners

**The Sklik `banners.*` API only works with IMAGE banners (JPG, PNG, GIF).**

HTML5 banners (ZIP files with HTML/CSS/JS):
- **Cannot** be created, updated, or listed via API
- **Must** be uploaded/managed via the Sklik web interface (sklik.cz)
- Are invisible to `banners.list` and `banners.createReport`
- The Sklik documentation explicitly states: "HTML5 reklamy nelze vytvářet ani upravovat přes API."

Image banners (JPG, PNG, GIF):
- Full API support via the `banners.*` namespace
- Files are **base64-encoded** in the `file` parameter
- When `banners.update` receives a new `file`, it creates a **new banner** (returns `newIds`)

### HTML5 Banner Format
- ZIP archive containing one HTML page + inline resources (CSS, base64 images, JS)
- Max ZIP size: 150 KB (Sklik limit)
- Required: `<meta name="ad.size" content="width=W,height=H">`
- No `<a>` tags, forms, iframes, or external URLs
- No transparent backgrounds, no interactivity
- Dimensions auto-detected from the HTML meta tag or ZIP filename
- Upload: via Sklik web UI → "Vytvořit reklamu" → "HTML5 banner"
- Bulk upload: multiple ZIPs at once, or one ZIP with folders (each = one banner)

### Workflow for HTML5 Banner Management
1. **Analyze**: Use the API (`banners` list for image banners + `ad-stats --group-id` for performance — the ads report includes both `adType: banner` and `adType: html5_banner`). HTML5 banners are visible in stats but cannot be created/edited via API.
2. **Plan**: Use the CLI to understand campaign/group structure, then plan HTML5 uploads
3. **Create/Replace/Remove**: Must be done via the Sklik web interface (the API cannot create, edit, or remove HTML5 banners)
4. **Stats**: via `ad-stats` (rows with `adType: html5_banner`) — see step 1

### Filtering banner lists
Like the rest of the API, `banners.list` ignores parent-entity restrictions — the CLI filters **client-side**: use `banners --group-id X --json`. To filter by size/campaign, parse the `--json` output yourself (each banner row carries its dimensions and group).

## Creative Theme Concept

Banners come in "creative sets" — multiple sizes of the same visual message.

### Naming Convention
A consistent filename pattern makes it easy to group and audit banners. One workable scheme:
```
{project}_{YYYYMMDD}_{THEME}_{WxH}.zip
```
Examples:
- `eshop_20260311_jarni-sleva_300x250.zip`
- `eshop_20260311_doprava-zdarma_970x310.zip`

**Theme** = a short creative-concept identifier (everything between the project prefix and the dimension suffix), e.g. `jarni-sleva`, `doprava-zdarma`, `novinka`. Use whatever scheme you like — the point is that it's parseable and consistent.

### Theme Grouping Logic
When analyzing banners from the API:
1. Parse the banner name to extract the theme (everything between the project prefix and the dimension suffix)
2. Group by theme across all groups/campaigns
3. Aggregate stats per theme to compare creative performance
4. Identify missing sizes (compare against your core set)

## Core Banner Sizes (Priority Order)

| Size | Format | Where It Shows |
|------|--------|----------------|
| 300×250 | Medium Rectangle | Most common, highest fill rate |
| 300×600 | Half Page | Premium sidebar placement |
| 480×300 | Large Rectangle | Content inline |
| 970×310 | Large Leaderboard | Top of page, high visibility |
| 728×90 | Leaderboard | Header/footer |
| 320×100 | Mobile Banner | Mobile devices |
| 300×300 | Square | Social/mobile |

Extended: 160×600, 480×480, 970×210, 500×200, 720×1280 (interscroller), 2000×1400 (branding)

## Campaign Structure for Display

```
Campaign: "{project} - Remarketing" (type: context)
  Budget: 50–150 Kč/day

  Group: "{theme}" — CPT: 15 Kč
    Banners: all sizes of that theme
    Click URL: theme-appropriate landing page

  Group: "{theme2}" — CPT: 15 Kč
    Banners: ...
```

- One group per creative theme (all sizes in one group)
- Or one group per targeting strategy (all themes for one audience)
- Never mix themes AND targeting in the same group — pick one grouping axis

## Producing the banners

This skill **uploads** image banners and reports on all banners (image + HTML5), but it does not design them.

- **Image banners** (JPG/PNG/GIF): upload with `banner-create --image <path|url>` (loop per file; replace = `banner-create` new **then** `banner-remove` old — create-first; download live creatives first with `banner-download --group-id X --out DIR`).
- **HTML5 banners** (ZIP): generate with whatever tool you prefer (a banner builder, a design tool, an HTML/CSS export), keep each ZIP ≤150 KB, then **upload via the Sklik web UI** — the API cannot create HTML5 banners.

Follow the naming convention above so the review/replace scenarios can group them by theme.
