# Sklik Display & Banner Campaign Rules

Reference for managing display (content network) and remarketing campaigns with banner ads on Sklik.

## Campaign Types

### Content Network (`type: context`)
- Banners shown on Seznam partner sites (content network)
- Bidding: **CPT** (cost per thousand impressions) or CPC
- Good for: brand awareness, broad reach, product visibility
- Typical daily budget: 50–300 Kč
- Group `maxCpt` sets the CPT bid (in haléře via API, CZK in CLI)

### Remarketing
- Target users who already visited your site
- Requires a remarketing audience set up in Sklik admin
- Higher CTR expected (0.3%+) due to a warmer audience
- Typical daily budget: 30–150 Kč
- Usually CPC bidding

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
3. **Create/Replace**: Must be done via the Sklik web interface
4. **Remove**: HTML5 banner IDs are not available via API; removal is also via the web interface
5. **Stats**: HTML5 banner stats are only visible in the Sklik web interface

### Restriction Filters
Unlike `ads.*`, `banners.list` and `banners.createReport` DO support:
- `campaign.ids` — filter by campaign
- `group.ids` — filter by group
- `banner.dimensions` — filter by WxH

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

- **Image banners** (JPG/PNG/GIF): upload with `banner-create --image <path|url>` (loop per file; replace = `banner-remove` + `banner-create`).
- **HTML5 banners** (ZIP): generate with whatever tool you prefer (a banner builder, a design tool, an HTML/CSS export), keep each ZIP ≤150 KB, then **upload via the Sklik web UI** — the API cannot create HTML5 banners.

Follow the naming convention above so the review/replace scenarios can group them by theme.
