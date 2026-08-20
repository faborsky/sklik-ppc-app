"""Ad commands: text (eta), combined (native), safe replace, stats."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from sklik.api import _api_call, _fail, _fail_msg, _fetch_all
from sklik.formatting import (
    _halere_to_czk, _format_money, _format_share,
    _format_stat_date, _output_json, _convert_stats_to_czk,
)
from sklik.reports import _fetch_report, stat_columns
from sklik.images import _load_image_b64



# ---------------------------------------------------------------------------
# Commands — Ads
# ---------------------------------------------------------------------------

def cmd_ads(args: argparse.Namespace) -> None:
    """List ads."""
    restriction: dict = {"isDeleted": False}

    cols = ["id", "adType", "headline1", "headline2", "headline3",
            "description", "description2", "finalUrl", "path1", "path2",
            "shortLine", "longLine", "companyName",
            "status", "group.id", "group.name", "campaign.id", "campaign.name"]

    ads = _fetch_all("ads.list", restriction, cols, "ads",
                     getattr(args, "user_id", None))

    # Client-side group/campaign filter (API doesn't filter on parent ids)
    if args.group_id:
        ads = [a for a in ads
               if (a.get("group", {}).get("id") if isinstance(a.get("group"), dict) else a.get("group.id")) == args.group_id]
    if getattr(args, "campaign_id", None):
        ads = [a for a in ads
               if (a.get("campaign", {}).get("id") if isinstance(a.get("campaign"), dict) else a.get("campaign.id")) == args.campaign_id]

    if args.json:
        out = []
        for a in ads:
            item = {
                "id": a.get("id"),
                "adType": a.get("adType"),
                "status": a.get("status"),
                "headline1": a.get("headline1"),
                "headline2": a.get("headline2"),
                "headline3": a.get("headline3"),
                "description": a.get("description"),
                "description2": a.get("description2"),
                "finalUrl": a.get("finalUrl"),
                "path1": a.get("path1"),
                "path2": a.get("path2"),
                "groupId": a.get("group", {}).get("id") if isinstance(a.get("group"), dict) else a.get("group.id"),
                "campaignId": a.get("campaign", {}).get("id") if isinstance(a.get("campaign"), dict) else a.get("campaign.id"),
            }
            if a.get("adType") == "combined":
                item.update({
                    "shortLine": a.get("shortLine"),
                    "longLine": a.get("longLine"),
                    "companyName": a.get("companyName"),
                })
            out.append(item)
        _output_json(out)
    else:
        if not ads:
            print("No ads found.")
            return
        for a in ads:
            print(f"ID: {a.get('id')}  Type: {a.get('adType')}  Status: {a.get('status')}")
            if a.get("adType") == "combined":
                print(f"  Short: {a.get('shortLine', '')}  |  Long: {a.get('longLine', '')}")
                print(f"  Desc: {a.get('description', '')}  |  Brand: {a.get('companyName', '')}")
                print(f"  URL: {a.get('finalUrl', '')}")
            else:
                print(f"  H1: {a.get('headline1', '')}  |  H2: {a.get('headline2', '')}  |  H3: {a.get('headline3', '')}")
                print(f"  D1: {a.get('description', '')}")
                print(f"  D2: {a.get('description2', '')}")
                print(f"  URL: {a.get('finalUrl', '')}  Path: /{a.get('path1', '')}/{a.get('path2', '')}")
            print()


def cmd_ad_create(args: argparse.Namespace) -> None:
    """Create an ETA ad."""
    ad: dict = {
        "groupId": args.group_id,
        "adType": "eta",
        "headline1": args.headline1,
        "headline2": args.headline2,
        "description": args.description1,
        "finalUrl": args.final_url,
    }
    if args.headline3:
        ad["headline3"] = args.headline3
    if args.description2:
        ad["description2"] = args.description2
    if args.path1:
        ad["path1"] = args.path1
    if args.path2:
        ad["path2"] = args.path2

    data = _api_call("ads.create", [[ad]], getattr(args, "user_id", None))
    ad_ids = data.get("adIds", [])

    if args.json:
        _output_json({"adIds": ad_ids})
    else:
        print(f"Ad created: ID {ad_ids[0] if ad_ids else '?'}")


def cmd_combined_create(args: argparse.Namespace) -> None:
    """Create a combined (native) ad for the display network.

    Sklik composes the final look from the texts and images — including the
    native in-article format. Landscape image (1.91:1, min 600×314) and square
    image (1:1, min 300×300) are both required by the API.
    """
    ad: dict = {
        "groupId": args.group_id,
        "adType": "combined",
        "shortLine": args.short_line,
        "longLine": args.long_line,
        "description": args.description,
        "companyName": args.company_name,
        "finalUrl": args.final_url,
        "image": _load_image_b64(args.image_landscape),
        "imageSquare": _load_image_b64(args.image_square),
    }
    if args.image_logo:
        ad["imageLogo"] = _load_image_b64(args.image_logo)
    if args.image_landscape_logo:
        ad["imageLandscapeLogo"] = _load_image_b64(args.image_landscape_logo)
    if args.color_main:
        ad["colorMain"] = args.color_main.lstrip("#")
    if args.color_accent:
        ad["colorAccent"] = args.color_accent.lstrip("#")
    if args.mobile_final_url:
        ad["mobileFinalUrl"] = args.mobile_final_url
    if args.tracking_template:
        ad["trackingTemplate"] = args.tracking_template
    if args.status:
        ad["status"] = args.status

    data = _api_call("ads.create", [[ad]], getattr(args, "user_id", None))
    ad_ids = data.get("adIds", [])

    if args.json:
        _output_json({"adIds": ad_ids})
    else:
        print(f"Combined ad created: ID {ad_ids[0] if ad_ids else '?'}")


def cmd_ad_update(args: argparse.Namespace) -> None:
    """Update an ad."""
    update: dict = {"id": args.ad_id}
    if args.status:
        update["status"] = args.status

    if len(update) == 1:
        print("ERROR: No fields to update.", file=sys.stderr)
        sys.exit(1)

    data = _api_call("ads.update", [[update]], getattr(args, "user_id", None))
    new_ids = data.get("newAdIds", [])
    if args.json:
        _output_json({"updated": True, "adId": args.ad_id, "newAdIds": new_ids})
    else:
        if new_ids:
            print(f"Ad {args.ad_id} updated → new ID: {new_ids[0]}")
        else:
            print(f"Ad {args.ad_id} updated.")


def cmd_ad_replace(args: argparse.Namespace) -> None:
    """Safely change a text (eta) ad's creative.

    Sklik can't edit an existing ad's text in place: any creative change makes
    ads.update ATOMICALLY delete the old ad and create the new one (returned as
    newAdIds) in ONE server-side operation. So — unlike a manual ad-remove +
    ad-create, where a failed create leaves the group with the ad gone — a
    validation failure here leaves the ORIGINAL ad untouched. That manual
    remove+create is exactly what silently dropped ads in production; use this
    command instead of doing it by hand.

    Flow: fetch the current ad → apply only the fields you pass → pre-validate
    with ads.check (a non-mutating dry-run; catches bad length / forbidden chars
    / missing fields cleanly) → atomic ads.update. The whole current creative is
    resubmitted, so partial edits (e.g. fixing one number) keep the rest intact.
    """
    user_id = getattr(args, "user_id", None)

    cols = ["id", "adType", "headline1", "headline2", "headline3",
            "description", "description2", "finalUrl", "path1", "path2", "group.id"]
    data = _api_call("ads.list", [{"ids": [args.ad_id], "isDeleted": False},
                                  {"limit": 1, "offset": 0, "displayColumns": cols}], user_id)
    ads = data.get("ads", [])
    if not ads:
        _fail_msg(f"Ad {args.ad_id} not found.", adId=args.ad_id)
    ad = ads[0]
    ad_type = ad.get("adType")
    if ad_type != "eta":
        _fail_msg(f"ad-replace supports text (eta) ads only; ad {args.ad_id} is "
                  f"'{ad_type}'. For combined/banner ads, remove and recreate with images.",
                  adId=args.ad_id, adType=ad_type)
    group_id = (ad.get("group", {}).get("id") if isinstance(ad.get("group"), dict)
                else ad.get("group.id"))

    # Start from the current creative so unspecified fields are preserved.
    creative: dict = {
        "adType": "eta",
        "headline1": ad.get("headline1"),
        "headline2": ad.get("headline2"),
        "description": ad.get("description"),
        "finalUrl": ad.get("finalUrl"),
    }
    for f in ("headline3", "description2", "path1", "path2"):
        if ad.get(f) is not None:
            creative[f] = ad.get(f)

    overrides = {
        "headline1": args.headline1, "headline2": args.headline2,
        "headline3": args.headline3, "description": args.description1,
        "description2": args.description2, "finalUrl": args.final_url,
        "path1": args.path1, "path2": args.path2,
    }
    changed = False
    for field, value in overrides.items():
        if value is not None:
            if creative.get(field) != value:
                changed = True
            creative[field] = value
    if not changed:
        _fail_msg("Nothing to change — pass at least one field that differs from the "
                  "current ad (--headline1/2/3, --description/--description2, "
                  "--final-url, --path1/2).", adId=args.ad_id)

    # Pre-flight validation, WITHOUT the duplicity check: the new creative would
    # otherwise flag as a near-duplicate of the very ad we're about to replace.
    # Real duplicates against OTHER ads are still caught safely by ads.update
    # below (atomic → the original ad survives a failed swap).
    check_struct = dict(creative)
    check_struct["groupId"] = group_id
    check = _api_call("ads.check", [[check_struct],
                                    {"checkDuplicity": False, "checkRules": True,
                                     "checkRequired": True}], user_id, _soft=True)
    cstatus = check.get("status")
    if cstatus not in (200, 206):
        if cstatus == 406:
            _fail("ads.check", check)  # genuine creative errors — stop, ad untouched
        # Check couldn't run (bad args / transient) — not a creative problem, and
        # the atomic ads.update is still safe, so proceed with a note.
        print(f"NOTE: ads.check pre-validation unavailable (status {cstatus}); relying "
              f"on atomic ads.update (original ad is preserved if the swap fails).",
              file=sys.stderr)

    update_struct = dict(creative)
    update_struct["id"] = args.ad_id
    result = _api_call("ads.update", [[update_struct]], user_id)
    new_ids = result.get("newAdIds", [])

    if args.json:
        _output_json({
            "replaced": True,
            "oldAdId": args.ad_id,
            "newAdIds": new_ids,
            "newAdId": new_ids[0] if new_ids else None,
        })
    else:
        if new_ids:
            print(f"Ad {args.ad_id} replaced → new ID: {new_ids[0]} (original preserved on any failure).")
        else:
            print(f"Ad {args.ad_id} updated (no new ID returned).")


def cmd_ad_remove(args: argparse.Namespace) -> None:
    """Remove an ad."""
    if not args.confirm:
        print("ERROR: Requires --confirm flag.", file=sys.stderr)
        sys.exit(1)

    _api_call("ads.remove", [[args.ad_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "adId": args.ad_id})
    else:
        print(f"Ad {args.ad_id} removed.")


def cmd_ad_stats(args: argparse.Namespace) -> None:
    """Show ad statistics."""
    date_from = args.date_from or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = args.date_to or datetime.now().strftime("%Y-%m-%d")

    gran = getattr(args, "granularity", "total")
    restriction: dict = {}

    cols = ["id", "adType", "headline1", "headline2", "status", "group.id"] + stat_columns("ads")
    report = _fetch_report("ads", restriction, date_from, date_to,
                           cols, granularity=gran,
                           user_id=getattr(args, "user_id", None))

    # Client-side group filter
    if args.group_id:
        report = [r for r in report
                  if (r.get("group", {}).get("id") if isinstance(r.get("group"), dict) else r.get("group.id")) == args.group_id]

    if args.json:
        for r in report:
            if "stats" in r:
                r["stats"] = _convert_stats_to_czk(r["stats"])
        _output_json(report)
    else:
        if not report:
            print("No data.")
            return
        print(f"Ad stats ({date_from} — {date_to}):\n")
        for r in report:
            print(f"  {r.get('headline1', '')} | {r.get('headline2', '')} (ID: {r.get('id')})")
            for s in r.get("stats", []):
                print(f"    {_format_stat_date(s, gran)}"
                      f"Clicks: {s.get('clicks', 0)}  Impr: {s.get('impressions', 0)}  "
                      f"CTR: {_format_share(s.get('ctr'))}  Cost: {_format_money(s.get('totalMoney'))}")


def cmd_ad_restore(args: argparse.Namespace) -> None:
    """Restore (undelete) a removed ad."""
    _api_call("ads.restore", [[args.ad_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"restored": True, "adId": args.ad_id})
    else:
        print(f"Ad {args.ad_id} restored.")
