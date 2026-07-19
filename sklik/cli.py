"""CLI: argument parsing and command dispatch."""
from __future__ import annotations

import argparse

import sklik.api as api
from sklik import __version__
from sklik.commands.account import (
    cmd_account, cmd_api_limits, cmd_pulse,
    cmd_credit, cmd_regions, cmd_autotagging, cmd_autotagging_update,
)
from sklik.commands.campaigns import (
    cmd_campaigns, cmd_campaign_create, cmd_campaign_update,
    cmd_campaign_remove, cmd_campaign_stats, cmd_campaign_targeting,
    cmd_campaign_restore,
)
from sklik.commands.groups import (
    cmd_groups, cmd_group_create, cmd_group_update, cmd_group_remove, cmd_group_stats,
    cmd_group_restore,
)
from sklik.commands.keywords import (
    cmd_keywords, cmd_keyword_create, cmd_keyword_create_batch, cmd_keyword_update,
    cmd_keyword_remove, cmd_keyword_stats, cmd_keyword_restore, cmd_keyword_set,
    cmd_negatives, cmd_negative_add, cmd_negative_add_batch, cmd_negative_remove,
)
from sklik.commands.ads import (
    cmd_ads, cmd_ad_create, cmd_combined_create, cmd_ad_update,
    cmd_ad_replace, cmd_ad_remove, cmd_ad_stats, cmd_ad_restore,
)
from sklik.commands.research import cmd_suggest, cmd_suggest_stats, cmd_search_queries
from sklik.commands.sitelinks import (
    cmd_sitelinks, cmd_sitelink_create, cmd_sitelink_remove,
    cmd_sitelink_update, cmd_sitelink_assign, cmd_sitelinks_assigned,
)
from sklik.commands.conversions import (
    cmd_conversions, cmd_conversion_types, cmd_conversion_create,
    cmd_conversion_update, cmd_conversion_remove,
)
from sklik.commands.retargeting import (
    cmd_retargeting, cmd_retargeting_create, cmd_retargeting_update, cmd_retargeting_remove,
    cmd_retargeting_attach, cmd_retargeting_detach, cmd_retargeting_attached,
    cmd_retargeting_exclude, cmd_retargeting_exclude_remove, cmd_retargeting_excluded,
)
from sklik.commands.banners import (
    cmd_banner_formats, cmd_banners, cmd_banner_create, cmd_banner_download, cmd_banner_remove,
    cmd_banner_update, cmd_banner_restore,
)
from sklik.commands.placements import (
    cmd_placements, cmd_placement_create, cmd_placement_remove,
    cmd_placements_excluded, cmd_placement_exclude, cmd_placement_exclude_remove,
    cmd_placement_exclude_restore,
)
from sklik.commands.display_targeting import (
    cmd_targeting_categories, cmd_targeting, cmd_targeting_add,
    cmd_targeting_exclude, cmd_targeting_remove, cmd_targeting_restore,
)
from sklik.commands.budgets import (
    cmd_budgets, cmd_budget_create, cmd_budget_update, cmd_budget_remove,
)



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
        default=api.DEFAULT_ACCOUNT,
        metavar="NAME",
        help="Sklik login to use: 'default' uses SKLIK_API_TOKEN, '<name>' uses "
             f"SKLIK_API_TOKEN_<NAME>. Default: {api.DEFAULT_ACCOUNT}",
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
    p.add_argument("--ad-selection", dest="ad_selection",
                   choices=["weighted", "random", "cpa", "cos"],
                   help="Ad rotation: weighted=prefer higher CTR (default), "
                        "random=even split (clean creative A/B test), "
                        "cpa=prefer lower CPA, cos=prefer lower CTR")
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
    p.add_argument("--ad-selection", dest="ad_selection",
                   choices=["weighted", "random", "cpa", "cos"],
                   help="Ad rotation: weighted=prefer higher CTR (default), "
                        "random=even split (clean creative A/B test), "
                        "cpa=prefer lower CPA, cos=prefer lower CTR")
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

    # --- campaign-restore ---
    p = subparsers.add_parser("campaign-restore", help="Restore (undelete) a removed campaign")
    p.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")
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
    p.add_argument("--max-daily-impression", type=int, dest="max_daily_impression",
                   help="Frequency cap: max impressions per user per day")
    p.add_argument("--json", **json_kwargs)

    # --- group-update ---
    p = subparsers.add_parser("group-update", help="Update ad group")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--cpc", type=float, help="New max CPC in CZK")
    p.add_argument("--status", choices=["active", "suspend"], help="New status")
    p.add_argument("--max-daily-impression", type=int, dest="max_daily_impression",
                   help="Frequency cap: max impressions per user per day")
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

    # --- group-restore ---
    p = subparsers.add_parser("group-restore", help="Restore (undelete) a removed ad group")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
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

    # --- keyword-restore ---
    p = subparsers.add_parser("keyword-restore", help="Restore (undelete) a removed keyword")
    p.add_argument("--keyword-id", type=int, required=True, help="Keyword ID")
    p.add_argument("--json", **json_kwargs)

    # --- keyword-set ---
    p = subparsers.add_parser(
        "keyword-set",
        help="Declaratively set a group's keywords (upsert; --remove-others = full sync)")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--keywords-json", required=True,
                   help='JSON array: [{"name":"kw","matchType":"broad","cpc":5.0,"url":"…"}] or ["kw1","kw2"]')
    p.add_argument("--remove-others", action="store_true",
                   help="Also DELETE every keyword not present in the payload")
    p.add_argument("--json", **json_kwargs)

    # --- ads ---
    p = subparsers.add_parser("ads", help="List ads")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--campaign-id", type=int, help="Filter by campaign ID")
    p.add_argument("--json", **json_kwargs)

    # --- ad-create ---
    p = subparsers.add_parser("ad-create", help="Create ETA ad")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--headline1", required=True, help="Headline 1 (max 30 chars)")
    p.add_argument("--headline2", required=True, help="Headline 2 (max 30 chars)")
    p.add_argument("--headline3", help="Headline 3 (max 30 chars)")
    # --description is an alias for --description1 (the list output field is
    # `description`, so both spellings are accepted to avoid confusion).
    p.add_argument("--description1", "--description", dest="description1", required=True,
                   help="Description 1 / description (max 90 chars)")
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
    p = subparsers.add_parser("ad-update", help="Update ad status (in place, no new ID)")
    p.add_argument("--ad-id", type=int, required=True, help="Ad ID")
    p.add_argument("--status", choices=["active", "suspend"], help="New status")
    p.add_argument("--json", **json_kwargs)

    # --- ad-replace ---
    p = subparsers.add_parser(
        "ad-replace",
        help="Safely change a text ad's creative (atomic swap; original kept if the new ad fails validation)")
    p.add_argument("--ad-id", type=int, required=True, help="Ad ID to replace")
    p.add_argument("--headline1", help="New headline 1")
    p.add_argument("--headline2", help="New headline 2")
    p.add_argument("--headline3", help="New headline 3")
    p.add_argument("--description1", "--description", dest="description1", help="New description 1")
    p.add_argument("--description2", help="New description 2")
    p.add_argument("--final-url", help="New final URL")
    p.add_argument("--path1", help="New display path 1")
    p.add_argument("--path2", help="New display path 2")
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

    # --- ad-restore ---
    p = subparsers.add_parser("ad-restore", help="Restore (undelete) a removed ad")
    p.add_argument("--ad-id", type=int, required=True, help="Ad ID")
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

    # --- sitelink-update ---
    p = subparsers.add_parser(
        "sitelink-update",
        help="Update sitelink (NOTE: renaming creates a NEW sitelink ID)")
    p.add_argument("--sitelink-id", type=int, required=True, help="Sitelink ID")
    p.add_argument("--name", help="New name (creates a new ID server-side)")
    p.add_argument("--url", help="New URL")
    p.add_argument("--json", **json_kwargs)

    # --- sitelink-assign ---
    p = subparsers.add_parser(
        "sitelink-assign",
        help="Assign sitelinks to a campaign or group — REPLACES the whole set")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--sitelink-ids", required=True,
                   help='Comma-separated sitelink IDs; "" clears the assignment')
    p.add_argument("--json", **json_kwargs)

    # --- sitelinks-assigned ---
    p = subparsers.add_parser(
        "sitelinks-assigned", help="Show sitelinks assigned to a campaign or group")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--group-id", type=int, help="Group ID")
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

    # --- retargeting-attach ---
    p = subparsers.add_parser(
        "retargeting-attach", help="Attach an audience list to an ad group as targeting")
    p.add_argument("--list-id", type=int, required=True, help="Retargeting list ID")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-detach ---
    p = subparsers.add_parser(
        "retargeting-detach", help="Detach an audience list from an ad group")
    p.add_argument("--list-id", type=int, required=True, help="Retargeting list ID")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--confirm", action="store_true", help="Required for detaching")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-attached ---
    p = subparsers.add_parser(
        "retargeting-attached",
        help="List audience lists attached to a group (all groups if omitted)")
    p.add_argument("--group-id", type=int, help="Group ID (all groups if omitted)")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-exclude ---
    p = subparsers.add_parser(
        "retargeting-exclude",
        help="Exclude an audience from a campaign or group (negative retargeting)")
    p.add_argument("--list-id", type=int, required=True, help="Retargeting list ID")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-exclude-remove ---
    p = subparsers.add_parser(
        "retargeting-exclude-remove",
        help="Stop excluding an audience from a campaign or group")
    p.add_argument("--list-id", type=int, required=True, help="Retargeting list ID")
    p.add_argument("--campaign-id", type=int, help="Campaign ID")
    p.add_argument("--group-id", type=int, help="Group ID")
    p.add_argument("--confirm", action="store_true", help="Required for removal")
    p.add_argument("--json", **json_kwargs)

    # --- retargeting-excluded ---
    p = subparsers.add_parser(
        "retargeting-excluded",
        help="List excluded audiences (campaign- and group-level)")
    p.add_argument("--campaign-id", type=int, help="Filter by campaign ID")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
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

    # --- banner-download ---
    p = subparsers.add_parser("banner-download", help="Download a group's banner images to a directory")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--out", required=True, help="Output directory (created if missing)")
    p.add_argument("--json", **json_kwargs)

    # --- banner-remove ---
    p = subparsers.add_parser("banner-remove", help="Remove image banner")
    p.add_argument("--banner-id", type=int, required=True, help="Banner ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- banner-update ---
    p = subparsers.add_parser(
        "banner-update",
        help="Update banner status/name/clickthru URL (image change = create-first replace)")
    p.add_argument("--banner-id", type=int, required=True, help="Banner ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--clickthru-url", dest="clickthru_url", help="New click-through URL")
    p.add_argument("--status", choices=["active", "suspend"], help="New status")
    p.add_argument("--json", **json_kwargs)

    # --- banner-restore ---
    p = subparsers.add_parser("banner-restore", help="Restore (undelete) a removed banner")
    p.add_argument("--banner-id", type=int, required=True, help="Banner ID")
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

    # --- placements-excluded ---
    p = subparsers.add_parser(
        "placements-excluded", help="List excluded websites (negative placements)")
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--json", **json_kwargs)

    # --- placement-exclude ---
    p = subparsers.add_parser(
        "placement-exclude", help="Exclude a website from a display group")
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--pattern", required=True,
                   help='URL pattern to exclude, e.g. "spamweb.cz"')
    p.add_argument("--json", **json_kwargs)

    # --- placement-exclude-remove ---
    p = subparsers.add_parser(
        "placement-exclude-remove",
        help="Remove a negative placement (stop excluding the website)")
    p.add_argument("--pattern-id", type=int, required=True, help="Negative pattern ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- placement-exclude-restore ---
    p = subparsers.add_parser(
        "placement-exclude-restore",
        help="Restore a removed negative placement (re-exclude the website)")
    p.add_argument("--pattern-id", type=int, required=True, help="Negative pattern ID")
    p.add_argument("--json", **json_kwargs)

    # --- display targeting: interests / themes / intends ---
    type_kwargs: dict = {
        "choices": ["interest", "theme", "intend"], "required": True,
        "help": "Targeting dimension: interest (zájmy), theme (témata), intend (úmysly)",
    }

    p = subparsers.add_parser(
        "targeting-categories",
        help="List available categories of a display-targeting dimension")
    p.add_argument("--type", **type_kwargs)
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser(
        "targeting",
        help="List display-targeting entries (interests/themes/intends) on groups")
    p.add_argument("--type", **type_kwargs)
    p.add_argument("--group-id", type=int, help="Filter by group ID")
    p.add_argument("--negative", action="store_true", help="Show exclusions instead")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser(
        "targeting-add", help="Add a category targeting to a display group")
    p.add_argument("--type", **type_kwargs)
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--category-id", type=int, required=True,
                   help="Category ID (see targeting-categories)")
    p.add_argument("--cpc", type=float, help="Max CPC in CZK (default: group CPC)")
    p.add_argument("--cpt", type=float, help="Max CPT in CZK (default: group setting)")
    p.add_argument("--status", choices=["active", "suspend"], help="Initial status")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser(
        "targeting-exclude", help="Exclude a category from a display group")
    p.add_argument("--type", **type_kwargs)
    p.add_argument("--group-id", type=int, required=True, help="Group ID")
    p.add_argument("--category-id", type=int, required=True,
                   help="Category ID (see targeting-categories)")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser(
        "targeting-remove",
        help="Remove a targeting entry (or an exclusion with --negative)")
    p.add_argument("--type", **type_kwargs)
    p.add_argument("--id", type=int, required=True, help="Targeting entry ID")
    p.add_argument("--negative", action="store_true", help="The ID is an exclusion")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser(
        "targeting-restore",
        help="Restore a removed targeting entry (re-add same category = 409; restore instead)")
    p.add_argument("--type", **type_kwargs)
    p.add_argument("--id", type=int, required=True, help="Targeting entry ID")
    p.add_argument("--negative", action="store_true", help="The ID is an exclusion")
    p.add_argument("--json", **json_kwargs)

    # --- shared budgets ---
    p = subparsers.add_parser("budgets", help="List shared budgets (amounts in CZK)")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser("budget-create", help="Create shared budget")
    p.add_argument("--name", required=True, help="Budget name")
    p.add_argument("--day-budget", type=float, required=True, help="Daily budget in CZK")
    p.add_argument("--campaign-ids", help="Comma-separated campaign IDs to assign")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser(
        "budget-update", help="Update shared budget / its campaign assignment")
    p.add_argument("--budget-id", type=int, required=True, help="Shared budget ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--day-budget", type=float, help="New daily budget in CZK")
    p.add_argument("--add-campaign-ids", help="Comma-separated campaign IDs to assign")
    p.add_argument("--remove-campaign-ids", help="Comma-separated campaign IDs to unassign")
    p.add_argument("--remove-all-campaigns", action="store_true",
                   help="Unassign ALL campaigns (excludes the add/remove flags)")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser("budget-remove", help="Remove shared budget")
    p.add_argument("--budget-id", type=int, required=True, help="Shared budget ID")
    p.add_argument("--confirm", action="store_true", help="Required for deletion")
    p.add_argument("--json", **json_kwargs)

    # --- credit ---
    p = subparsers.add_parser("credit", help="Show wallet credit (CZK)")
    p.add_argument("--json", **json_kwargs)

    # --- regions ---
    p = subparsers.add_parser(
        "regions", help="List predefined region IDs for --regions targeting")
    p.add_argument("--json", **json_kwargs)

    # --- autotagging ---
    p = subparsers.add_parser("autotagging", help="Show autotagging (UTM) config")
    p.add_argument("--json", **json_kwargs)

    p = subparsers.add_parser(
        "autotagging-update",
        help="Update autotagging config (merged over the current settings)")
    p.add_argument("--enabled", choices=["on", "off"], help="Enable/disable autotagging")
    p.add_argument("--config-json", help="Partial config as JSON, merged over current")
    p.add_argument("--json", **json_kwargs)

    args = parser.parse_args()
    api.set_json_output(getattr(args, "json", False))
    api.set_account(getattr(args, "account", api.DEFAULT_ACCOUNT))
    api.check_config()

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
        "ad-replace": cmd_ad_replace,
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
        "banner-download": cmd_banner_download,
        "banner-remove": cmd_banner_remove,
        "placements": cmd_placements,
        "placement-create": cmd_placement_create,
        "placement-remove": cmd_placement_remove,
        "campaign-restore": cmd_campaign_restore,
        "group-restore": cmd_group_restore,
        "keyword-restore": cmd_keyword_restore,
        "keyword-set": cmd_keyword_set,
        "ad-restore": cmd_ad_restore,
        "sitelink-update": cmd_sitelink_update,
        "sitelink-assign": cmd_sitelink_assign,
        "sitelinks-assigned": cmd_sitelinks_assigned,
        "retargeting-attach": cmd_retargeting_attach,
        "retargeting-detach": cmd_retargeting_detach,
        "retargeting-attached": cmd_retargeting_attached,
        "retargeting-exclude": cmd_retargeting_exclude,
        "retargeting-exclude-remove": cmd_retargeting_exclude_remove,
        "retargeting-excluded": cmd_retargeting_excluded,
        "banner-update": cmd_banner_update,
        "banner-restore": cmd_banner_restore,
        "placements-excluded": cmd_placements_excluded,
        "placement-exclude": cmd_placement_exclude,
        "placement-exclude-remove": cmd_placement_exclude_remove,
        "placement-exclude-restore": cmd_placement_exclude_restore,
        "targeting-categories": cmd_targeting_categories,
        "targeting": cmd_targeting,
        "targeting-add": cmd_targeting_add,
        "targeting-exclude": cmd_targeting_exclude,
        "targeting-remove": cmd_targeting_remove,
        "targeting-restore": cmd_targeting_restore,
        "budgets": cmd_budgets,
        "budget-create": cmd_budget_create,
        "budget-update": cmd_budget_update,
        "budget-remove": cmd_budget_remove,
        "credit": cmd_credit,
        "regions": cmd_regions,
        "autotagging": cmd_autotagging,
        "autotagging-update": cmd_autotagging_update,
    }

    commands[args.command](args)
