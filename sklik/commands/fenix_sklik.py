"""Sklik campaign commands on the Fénix REST API (`fenix-*`): the authorized
user, campaigns, groups, ads and negative keywords.

Same engine and token as the Nákupy commands (`sklik/fenix.py`,
`SKLIK_FENIX_REFRESH_TOKEN`), but these endpoints (`/user/*`, `/sklik/*`) take
no `premiseId`. They do not replace the DRAK commands: Fénix (spec 1.30.0) has
no endpoints for positive keywords, keyword suggestions or search-query
reports. What it adds is `dryRun` validation of creates and — the one thing
DRAK cannot do at all — LISTING campaign-level negative keywords.

Written against the OpenAPI spec (v1.30.0). What a live account confirmed on
2026-10-02 and 2026-10-11 and what is still spec-only (details in
`docs/api-notes.md`):

* **verified live** — every read; the server-side dry run and the real create
  of a campaign, a group and an ETA ad (a valid payload answers 2xx, an invalid
  one 422 naming the field); `fenix-negative-add` / `fenix-negative-remove` at
  both levels with all three match types.
* **NOT run live** — `fenix-campaign-create --status active`, the `context` and
  `product` campaign types, `--user-id`, and a 429.

Money, per field:

* **haléře** — `budget.dayBudget` (campaigns) and `cpc` (groups): verified
  live, a 30 Kč budget reads `3000` and a 3 Kč bid reads `300`.
  `exhaustedDayBudget` and `cpm` are haléře per the spec (not seen live). The
  CLI takes CZK on the flags and converts; the human output converts back.
  `--json` passes the raw API payload through untouched (haléře), like the
  Nákupy commands do.
* **CZK** — `credit` / `creditWithVat` of `/user/me/credit`: verified live
  (same number as DRAK's `credit` command).
* **not stated** — `agencyLimit` of `/user/me/credit` ("Limit assigned by
  agency", an integer with no unit). Printed raw, never converted.

`devices.maxCpcMultiplier` is deliberately NOT requested: the spec words it
exactly like the Nákupy field of the same name ("multiplier in percent"), which
live data showed to be a signed modifier instead — showing it here would mean
guessing which of the two it is.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import sklik.fenix as fenix
from sklik.api import _fail_msg
from sklik.formatting import _czk_to_halere, _format_money, _output_json

# The listings return only the attributes named in the `a` query parameter, and
# the spec does not say what comes back when it is omitted — so every listing
# asks for its columns explicitly. `isDeleted` rides along so the deleted-filter
# can be re-applied client-side (see `_live`).
_CAMPAIGN_ATTRS = ("id", "name", "type", "status", "isDeleted", "adSelection",
                   "paymentMethod", "createDate", "exhaustedDayBudget",
                   "budget.id", "budget.name", "budget.dayBudget",
                   "startDate", "endDate",
                   # `capping` as a whole is a 422 — only its dotted fields work
                   "capping.maxImpressions", "capping.maxImpressionsPeriod")
_GROUP_ATTRS = ("id", "name", "status", "isDeleted", "createDate", "cpc", "cpm")
_AD_ATTRS = ("id", "type", "status", "adStatus", "isDeleted", "createDate",
             "startDate", "endDate",
             # ETA
             "headline1", "headline2", "headline3", "description", "description2",
             "path1", "path2", "finalUrl", "mobileFinalUrl", "trackingTemplate",
             # banner / combined naming, so non-ETA rows are not blank
             "name", "shortLine", "longLine", "companyName")
_NEGATIVE_ATTRS = ("name", "matchType")
_ACCOUNT_ATTRS = ("id", "username", "access", "agencyStatus", "relationStatus")

# Fénix calls the broad negative match plain `negative` (DRAK: `negativeBroad`).
# The DRAK spelling is accepted too, so both command families take the same value.
_MATCH_ALIASES = {"negativeBroad": "negative"}


def _s(value: object, default: str = "") -> str:
    """A table cell: a listing only carries the attributes it has a value for,
    and a null in a padded column would crash the f-string format spec."""
    return default if value is None else str(value)


def _live(items: list[dict]) -> list[dict]:
    """Drop deleted rows. `isDeleted=false` is sent as a query filter as well;
    this repeats it locally so a filter the API ignored cannot pass unnoticed
    (DRAK ignores most of its filters — same belt and braces as `shop-items`)."""
    return [i for i in items if not i.get("isDeleted")]


def _negatives_path(campaign_id: int, group_id: int | None) -> str:
    """Negative-keyword collection of a campaign, or of one of its groups."""
    base = f"/sklik/campaigns/{campaign_id}"
    if group_id:
        base += f"/groups/{group_id}"
    return f"{base}/negative-keywords/"


def _negative_item(args: argparse.Namespace) -> dict:
    return {"name": args.name,
            "matchType": _MATCH_ALIASES.get(args.match_type, args.match_type)}


def _created_ids(data: dict) -> list:
    return [i.get("id") for i in data.get("items") or [] if isinstance(i, dict)]


def _report_create(args: argparse.Namespace, label: str, key: str, data: dict,
                   **extra: object) -> None:
    """Shared output of the create commands (real create and server dry run).

    `extra` (e.g. the status a campaign was created with) is added to the JSON
    and shown in brackets in the human output."""
    if args.dry_run:
        # dryRun=true: the API validated the payload and persisted nothing. The
        # spec gives the dry-run answer no shape of its own (seen live for a
        # campaign: `{"items": []}`), so it is passed on as-is.
        if args.json:
            _output_json({"dryRun": True, "valid": True, "response": data})
        else:
            print(f"Dry run OK — {label.lower()} payload is valid; nothing was created.")
            if data:
                print(f"API response: {json.dumps(data, ensure_ascii=False)}")
        return
    ids = _created_ids(data)
    if args.json:
        _output_json({key: ids, **extra})
    else:
        note = ", ".join(f"{k}: {v}" for k, v in extra.items())
        print(f"{label} created: ID {ids[0] if ids else '?'}"
              + (f" ({note})" if note else ""))


def _local_dry_run(args: argparse.Namespace, method: str, path: str, body: dict) -> None:
    """`--dry-run` for the negative-keyword writes, which have NO `dryRun`
    parameter in the spec. Sending one would risk the API ignoring it and
    performing the write, so nothing is sent at all: the request is only shown.
    That makes it a preview, not a validation — and the output says so."""
    if args.json:
        _output_json({"dryRun": "local", "validated": False,
                      "wouldSend": {"method": method, "path": path, "body": body}})
    else:
        print(f"Dry run (local only — this endpoint has no server-side dryRun, "
              f"so nothing was validated or sent):\n  {method} {path}\n"
              f"  body: {json.dumps(body, ensure_ascii=False)}")


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def cmd_fenix_me(args: argparse.Namespace) -> None:
    """Who the Fénix token acts as, and which scopes it carries."""
    d = fenix.call("GET", "/user/me")

    if args.json:
        _output_json(d)
        return
    print(f"User:    {d.get('userName', '—')} (ID {d.get('userId', '—')})")
    actor = d.get("actor")
    if actor:
        print(f"Actor:   {actor.get('userName', '—')} (ID {actor.get('userId', '—')}) "
              "— acting on the user's behalf")
    print(f"Scopes:  {', '.join(d.get('scope') or []) or '—'}")


def cmd_fenix_credit(args: argparse.Namespace) -> None:
    """Credit of the authorized user (CZK), or the agency limit of a client."""
    d = fenix.call("GET", "/user/me/credit")

    if args.json:
        _output_json(d)
        return
    print(f"Agency status:       {d.get('agencyStatus', '—')}")
    print(f"Verified in wallet:  {d.get('verifiedInWallet', '—')}")
    if "credit" in d:
        # Plain CZK per the spec — not haléře, do NOT use _format_money.
        print(f"Credit:              {d.get('credit')} Kč "
              f"(with VAT {d.get('creditWithVat')} Kč)")
    else:
        # Agency clients get `agencyLimit` instead of a credit. The spec gives
        # it no unit, so it is printed as-is rather than labelled Kč or haléře.
        print(f"Agency limit:        {_s(d.get('agencyLimit'), '—')} (unit not documented)")


def cmd_fenix_accounts(args: argparse.Namespace) -> None:
    """Accounts (own and managed) the token can access — IDs for --user-id."""
    data = fenix.call("GET", "/user/linked-accounts", {"a": list(_ACCOUNT_ATTRS)})
    accounts = data.get("items") or []

    if args.json:
        _output_json(accounts)
        return
    if not accounts:
        print("No accessible accounts.")
        return
    print(f"{'ID':<12} {'Username':<40} {'Access':<7} {'Relation':<9} {'Agency'}")
    print("-" * 86)
    for a in accounts:
        print(f"{_s(a.get('id')):<12} {_s(a.get('username')):<40} "
              f"{_s(a.get('access')):<7} {_s(a.get('relationStatus')):<9} "
              f"{a.get('agencyStatus') or '—'}")


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def cmd_fenix_campaigns(args: argparse.Namespace) -> None:
    """List campaigns."""
    params: dict = {"a": list(_CAMPAIGN_ATTRS), "isDeleted": "false",
                    "order": "id:ASC"}
    if args.status:
        params["status"] = args.status
    campaigns = _live(fenix.fetch_all_offset("/sklik/campaigns/", params))
    if args.status:
        campaigns = [c for c in campaigns if c.get("status") == args.status]

    if args.json:
        _output_json(campaigns)
        return
    if not campaigns:
        print("No campaigns found.")
        return
    print(f"{'ID':<12} {'Name':<35} {'Status':<10} {'Type':<10} "
          f"{'Day Budget':<12} {'Rotation':<10} {'Start':<11} {'End':<11} {'Cap'}")
    print("-" * 124)
    for c in campaigns:
        budget = c.get("budget") or {}
        cap = c.get("capping") or {}
        cap_txt = (f"{cap['maxImpressions']}/{cap.get('maxImpressionsPeriod') or '?'}"
                   if cap.get("maxImpressions") else "—")
        # budget.dayBudget is haléře (spec: `BudgetResponse`).
        print(f"{_s(c.get('id')):<12} {_s(c.get('name')):<35} "
              f"{_s(c.get('status')):<10} {_s(c.get('type')):<10} "
              f"{_format_money(budget.get('dayBudget')):<12} "
              f"{c.get('adSelection') or '—':<10} "
              f"{(c.get('startDate') or '—')[:10]:<11} "
              f"{(c.get('endDate') or '—')[:10]:<11} {cap_txt}")


def cmd_fenix_groups(args: argparse.Namespace) -> None:
    """List the ad groups of one campaign."""
    groups = _live(fenix.fetch_all_offset(
        f"/sklik/campaigns/{args.campaign_id}/groups/",
        {"a": list(_GROUP_ATTRS), "isDeleted": "false", "order": "id:ASC"}))

    if args.json:
        _output_json(groups)
        return
    if not groups:
        print("No groups found.")
        return
    print(f"{'ID':<12} {'Name':<35} {'Status':<10} {'Max CPC':<12} {'Max CPM'}")
    print("-" * 84)
    for g in groups:
        # cpc / cpm are haléře (spec: "Max CPC in hellers").
        print(f"{_s(g.get('id')):<12} {_s(g.get('name')):<35} "
              f"{_s(g.get('status')):<10} {_format_money(g.get('cpc')):<12} "
              f"{_format_money(g.get('cpm'))}")


def cmd_fenix_ads(args: argparse.Namespace) -> None:
    """List the ads of one group."""
    ads = _live(fenix.fetch_all_offset(
        f"/sklik/campaigns/{args.campaign_id}/groups/{args.group_id}/ads/",
        {"a": list(_AD_ATTRS), "isDeleted": "false", "order": "id:ASC"}))

    if args.json:
        _output_json(ads)
        return
    if not ads:
        print("No ads found.")
        return
    for a in ads:
        dates = ""
        if a.get("startDate") or a.get("endDate"):
            dates = (f"  {(a.get('startDate') or '…')[:10]} → "
                     f"{(a.get('endDate') or '…')[:10]}")
        print(f"[{a.get('id')}] {_s(a.get('type'), '?')}  "
              f"status={_s(a.get('status'), '—')}  approval={_s(a.get('adStatus'), '—')}"
              f"{dates}")
        if a.get("type") == "eta":
            heads = [a.get(k) for k in ("headline1", "headline2", "headline3")]
            print(f"    {' | '.join(h for h in heads if h)}")
            descs = [a.get(k) for k in ("description", "description2")]
            print(f"    {' '.join(d for d in descs if d)}")
        else:
            title = a.get("shortLine") or a.get("name")
            if title:
                print(f"    {title}")
        if a.get("finalUrl"):
            print(f"    → {a['finalUrl']}")


def cmd_fenix_negatives(args: argparse.Namespace) -> None:
    """List negative keywords of a campaign (campaign level) or of one group."""
    negatives = fenix.fetch_all_offset(
        _negatives_path(args.campaign_id, args.group_id),
        {"a": list(_NEGATIVE_ATTRS)})

    if args.json:
        _output_json(negatives)
        return
    level = (f"group {args.group_id}" if args.group_id
             else f"campaign {args.campaign_id} (campaign level)")
    if not negatives:
        print(f"No negative keywords on {level}.")
        return
    print(f"Negative keywords on {level}: {len(negatives)}\n")
    print(f"{'Keyword':<40} {'Match Type'}")
    print("-" * 56)
    for n in negatives:
        print(f"{_s(n.get('name')):<40} {_s(n.get('matchType'))}")


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def cmd_fenix_campaign_create(args: argparse.Namespace) -> None:
    """Create a campaign — paused unless --status active is passed."""
    # `suspend` is the paused value of the spec's Status enum (active|suspend).
    # A campaign created by a script should never start spending by default.
    status = args.status or "suspend"
    campaign: dict = {
        "type": args.type,
        "name": args.name,
        "budget": {"dayBudget": _czk_to_halere(args.day_budget)},  # haléře
        "status": status,
    }
    if args.ad_selection:
        campaign["adSelection"] = args.ad_selection

    data = fenix.call("POST", "/sklik/campaigns/",
                      {"dryRun": "true"} if args.dry_run else None, body=campaign)
    _report_create(args, "Campaign", "campaignIds", data, status=status)


def cmd_fenix_group_create(args: argparse.Namespace) -> None:
    """Create an ad group in a campaign."""
    if args.cpc is None and args.cpm is None:
        # The spec requires only `name`, and does not say what bid a group gets
        # without one. A CLI rule, not an API one: never leave a bid to an
        # undocumented server default.
        _fail_msg("--cpc or --cpm is required. The API itself accepts a group "
                  "without a bid, but the spec does not say what bid it then gets.")
    group: dict = {"name": args.name}
    if args.cpc is not None:
        group["cpc"] = _czk_to_halere(args.cpc)   # haléře
    if args.cpm is not None:
        group["cpm"] = _czk_to_halere(args.cpm)   # haléře
    if args.status:
        group["status"] = args.status

    data = fenix.call("POST", f"/sklik/campaigns/{args.campaign_id}/groups/",
                      {"dryRun": "true"} if args.dry_run else None, body=group)
    _report_create(args, "Group", "groupIds", data)


def cmd_fenix_ad_create(args: argparse.Namespace) -> None:
    """Create an ETA ad in a group.

    No `status`: the spec allows it, the live API answers 422 "status: Invalid
    field value" for both values (2026-10-11). The ad is always created active.
    """
    ad: dict = {
        "type": "eta",
        "headline1": args.headline1,
        "headline2": args.headline2,
        "description": args.description1,
        "finalUrl": args.final_url,
    }
    for key, value in (("headline3", args.headline3),
                       ("description2", args.description2),
                       ("path1", args.path1), ("path2", args.path2),
                       ("mobileFinalUrl", args.mobile_final_url),
                       ("trackingTemplate", args.tracking_template)):
        if value:
            ad[key] = value

    data = fenix.call(
        "POST", f"/sklik/campaigns/{args.campaign_id}/groups/{args.group_id}/ads/",
        {"dryRun": "true"} if args.dry_run else None, body=ad)
    _report_create(args, "Ad", "adIds", data)


def cmd_fenix_negative_add(args: argparse.Namespace) -> None:
    """Add a negative keyword at campaign level, or to one group."""
    path = _negatives_path(args.campaign_id, args.group_id)
    item = _negative_item(args)
    body = {"negativeKeywords": [item]}
    if args.dry_run:
        _local_dry_run(args, "POST", path, body)
        return

    fenix.call("POST", path, body=body)   # 201, no body
    level = "group" if args.group_id else "campaign"
    if args.json:
        _output_json({"added": 1, "level": level, "campaignId": args.campaign_id,
                      "groupId": args.group_id, "negativeKeyword": item})
    else:
        print(f"Negative keyword added ({level} level): "
              f"{item['name']} [{item['matchType']}]")


def cmd_fenix_negative_remove(args: argparse.Namespace) -> None:
    """Permanently delete a negative keyword (matched by text + match type)."""
    # Negative keywords have no IDs in Fénix — the delete names them by
    # name + matchType, in the request body of a POST to `…/delete`.
    path = _negatives_path(args.campaign_id, args.group_id) + "delete"
    item = _negative_item(args)
    body = {"negativeKeywords": [item]}
    if args.dry_run:
        _local_dry_run(args, "POST", path, body)
        return
    if not args.confirm:
        _fail_msg("Requires --confirm flag.")

    fenix.call("POST", path, body=body)   # 204, no body
    level = "group" if args.group_id else "campaign"
    if args.json:
        _output_json({"removed": True, "level": level,
                      "campaignId": args.campaign_id, "groupId": args.group_id,
                      "negativeKeyword": item})
    else:
        print(f"Negative keyword removed ({level} level): "
              f"{item['name']} [{item['matchType']}]")


# ---------------------------------------------------------------------------
# Updates (PATCH) — spec 1.34.0
# ---------------------------------------------------------------------------

# A date flag takes YYYY-MM-DD, or `none` to clear the date (the API takes
# null). The spec types the dates as date-time; a bare date was accepted live
# (2026-10-22) and is stored as midnight local time (`…T00:00:00+01:00`).
_CLEAR = "none"

# Ad types whose PATCH schema has a `name` (UpdateAdBanner, UpdateAdBranding).
_NAMED_AD_TYPES = ("banner", "branding")


def _date_value(value: str | None, flag: str) -> str | None:
    """`YYYY-MM-DD` → the same string (validated); `none` → None (= clear)."""
    if value is None or value.lower() == _CLEAR:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        _fail_msg(f"{flag} must be YYYY-MM-DD or '{_CLEAR}' (got {value!r}).")
    return value


def _put_dates(body: dict, args: argparse.Namespace) -> None:
    """Add --start-date / --end-date to a PATCH body when given."""
    for key, attr, flag in (("startDate", "start_date", "--start-date"),
                            ("endDate", "end_date", "--end-date")):
        raw = getattr(args, attr, None)
        if raw is not None:
            body[key] = _date_value(raw, flag)


def _campaign_type(campaign_id: int) -> str:
    """The PATCH body needs the campaign's `type` (it selects the schema and
    cannot be changed), so look it up. The spec names the filter `id`; the
    live API validates `ids` as a list and filters by it (2026-10-22)."""
    data = fenix.call("GET", "/sklik/campaigns/",
                      {"ids": [campaign_id], "a": ["id", "type"]})
    for c in data.get("items") or []:
        if c.get("id") == campaign_id and c.get("type"):
            return c["type"]
    _fail_msg(f"Campaign {campaign_id} not found.", campaignId=campaign_id)
    return ""  # unreachable, _fail_msg exits


def _report_update(args: argparse.Namespace, label: str, sent: dict,
                   **ids: object) -> None:
    """Shared output of the update commands (real PATCH and server dry run)."""
    if args.json:
        _output_json({"updated": not args.dry_run, "dryRun": args.dry_run,
                      **ids, "sent": sent})
        return
    changed = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}"
                        for k, v in sent.items() if k != "type")
    if args.dry_run:
        print(f"Dry run OK — {label} update is valid; nothing was changed.\n  {changed}")
    else:
        print(f"{label} updated: {changed}")


def cmd_fenix_campaign_update(args: argparse.Namespace) -> None:
    """Update a campaign: status, budgets, dates, frequency cap, excluded URLs."""
    body: dict = {}
    if args.name:
        body["name"] = args.name
    if args.status:
        body["status"] = args.status
    if args.day_budget is not None:
        body["budget"] = {"dayBudget": _czk_to_halere(args.day_budget)}   # haléře
    if args.total_budget is not None:
        # null = no total budget limit
        body["totalBudget"] = (None if args.total_budget.lower() == _CLEAR
                               else _czk_to_halere(_czk(args.total_budget, "--total-budget")))
    _put_dates(body, args)

    if args.no_capping:
        if any(v is not None for v in (args.capping_max, args.capping_period,
                                       args.capping_min_delay, args.capping_min_delay_period)):
            _fail_msg("--no-capping cannot be combined with other --capping-* flags.")
        body["capping"] = None
    else:
        capping: dict = {}
        if args.capping_max is not None:
            capping["maxImpressions"] = args.capping_max
        if args.capping_period:
            capping["maxImpressionsPeriod"] = args.capping_period
        if args.capping_min_delay is not None:
            capping["minDelay"] = args.capping_min_delay
        if args.capping_min_delay_period:
            capping["minDelayPeriod"] = args.capping_min_delay_period
        # Pairs go together: the spec does not say whether a PATCH merges the
        # nested object or replaces it, and a lone period could wipe the count.
        for a, b in (("maxImpressions", "maxImpressionsPeriod"),
                     ("minDelay", "minDelayPeriod")):
            if (a in capping) != (b in capping):
                _fail_msg("--capping-max needs --capping-period and "
                          "--capping-min-delay needs --capping-min-delay-period "
                          "(and vice versa).")
        if capping:
            body["capping"] = capping

    if args.no_excluded_urls:
        if args.excluded_urls:
            _fail_msg("--no-excluded-urls cannot be combined with --excluded-urls.")
        body["excludedUrls"] = []
    elif args.excluded_urls:
        body["excludedUrls"] = args.excluded_urls   # replaces the whole list

    if not body:
        _fail_msg("No fields to update.")

    campaign_type = args.type or _campaign_type(args.campaign_id)
    if "capping" in body and campaign_type == "simple":
        _fail_msg("Campaigns of type 'simple' have no frequency cap in the API.")
    if "excludedUrls" in body and campaign_type == "social":
        _fail_msg("Campaigns of type 'social' have no excluded URLs in the API.")
    body = {"type": campaign_type, **body}
    fenix.call("PATCH", f"/sklik/campaigns/{args.campaign_id}/",
               {"dryRun": "true"} if args.dry_run else None, body=body)
    _report_update(args, f"Campaign {args.campaign_id}", body,
                   campaignId=args.campaign_id)


def _czk(value: str, flag: str) -> float:
    try:
        return float(value)
    except ValueError:
        _fail_msg(f"{flag} must be an amount in CZK or '{_CLEAR}' (got {value!r}).")
        return 0.0  # unreachable


def _ad_types(campaign_id: int, group_id: int, ad_ids: list[int]) -> dict[int, str]:
    """`type` of each ad (the PATCH body needs it), read from the group's
    listing — one walk of the group instead of one call per ad."""
    ads = fenix.fetch_all_offset(
        f"/sklik/campaigns/{campaign_id}/groups/{group_id}/ads/",
        {"a": ["id", "type"], "isDeleted": "false", "order": "id:ASC"})
    types = {a.get("id"): a.get("type") for a in _live(ads)}
    missing = [i for i in ad_ids if not types.get(i)]
    if missing:
        _fail_msg(f"Ads not found in group {group_id}: "
                  f"{', '.join(map(str, missing))}.", adIds=missing)
    return {i: types[i] for i in ad_ids}


def cmd_fenix_ad_update(args: argparse.Namespace) -> None:
    """Update ads of one group (any type, banners included): status, dates, name.

    Only fields the API changes IN PLACE are offered. Changing a creative field
    (text, image) makes the API delete the ad and create a successor with a new
    ID — for ETA text use `ad-replace`; that path is not wrapped here."""
    fields: dict = {}
    if args.status:
        fields["status"] = args.status
    _put_dates(fields, args)
    if args.name:
        fields["name"] = args.name
    if not fields:
        _fail_msg("No fields to update.")

    ad_ids = list(dict.fromkeys(args.ad_id))
    types = ({i: args.type for i in ad_ids} if args.type
             else _ad_types(args.campaign_id, args.group_id, ad_ids))
    if "name" in fields:
        unnamed = [i for i, t in types.items() if t not in _NAMED_AD_TYPES]
        if unnamed:
            _fail_msg(f"--name exists only for {', '.join(_NAMED_AD_TYPES)} ads; "
                      f"not for {', '.join(map(str, unnamed))}.", adIds=unnamed)

    base = f"/sklik/campaigns/{args.campaign_id}/groups/{args.group_id}/ads"
    params = {"dryRun": "true"} if args.dry_run else None
    replaced: dict = {}
    done: list[int] = []
    for ad_id in ad_ids:
        try:
            data = fenix.call("PATCH", f"{base}/{ad_id}/", params,
                              body={"type": types[ad_id], **fields})
        except SystemExit:
            # The error itself is already out; say which ads did change.
            if done and not args.dry_run:
                print(f"Already updated before the failure: "
                      f"{', '.join(map(str, done))}", file=sys.stderr)
            raise
        done.append(ad_id)
        # 204 = changed in place; 200 with an `id` = the API replaced the ad.
        new_id = data.get("id") if isinstance(data, dict) else None
        if new_id and new_id != ad_id:
            replaced[ad_id] = new_id

    if args.json:
        _output_json({"updated": [] if args.dry_run else ad_ids,
                      "dryRun": args.dry_run, "replaced": replaced,
                      "campaignId": args.campaign_id, "groupId": args.group_id,
                      "sent": fields})
        return
    changed = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in fields.items())
    verb = "Dry run OK — valid, nothing changed for" if args.dry_run else "Updated"
    print(f"{verb} {len(ad_ids)} ad(s) in group {args.group_id}: {changed}")
    for old, new in replaced.items():
        print(f"  ad {old} was replaced by the API with a new ad {new}")
