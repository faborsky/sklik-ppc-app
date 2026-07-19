"""Image banner commands (context/display network)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import requests

from sklik.api import _api_call, _fail, _fail_msg
from sklik.formatting import _halere_to_czk, _format_money, _output_json
from sklik.images import _load_image_b64, _image_ext



def cmd_banner_formats(args: argparse.Namespace) -> None:
    """List allowed banner formats (dimensions + size limits)."""
    data = _api_call("images.constraints.list", [], getattr(args, "user_id", None))
    # Structure: {"banner": {"banner": [ {minWidth,maxWidth,...,maxSize,ruleName}, ... ]}}
    rules = []
    constraints = data.get("constraints") or data
    banner = constraints.get("banner", {}) if isinstance(constraints, dict) else {}
    rules = banner.get("banner", []) if isinstance(banner, dict) else []

    if args.json:
        _output_json(rules)
    else:
        if not rules:
            print("No banner format constraints returned.")
            return
        print(f"{'Format':<16} {'Max size':<12} {'External ad'}")
        print("-" * 45)
        for r in rules:
            w = r.get("recommendedWidth") or r.get("maxWidth")
            h = r.get("recommendedHeight") or r.get("maxHeight")
            dims = f"{w}×{h}" if w and h else (r.get("ruleName") or "?")
            size = r.get("maxSize")
            size_str = f"{size // 1024} KB" if size else "—"
            print(f"{dims:<16} {size_str:<12} {r.get('externalAdSupport', False)}")


def cmd_banners(args: argparse.Namespace) -> None:
    """List image banners."""
    cols = ["id", "bannerName", "adStatus", "clickthruUrl",
            "height", "group.id", "group.name"]
    data = _api_call("banners.list", [{"isDeleted": False}, {
        "limit": 500, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))
    banners = data.get("banners", [])

    # Client-side group filter
    if args.group_id:
        banners = [b for b in banners
                   if (b.get("group", {}).get("id") if isinstance(b.get("group"), dict) else b.get("group.id")) == args.group_id]

    if args.json:
        out = [{
            "id": b.get("id"),
            "name": b.get("bannerName"),
            "status": b.get("adStatus"),
            "clickthruUrl": b.get("clickthruUrl"),
            "groupId": b.get("group", {}).get("id") if isinstance(b.get("group"), dict) else b.get("group.id"),
            "groupName": b.get("group", {}).get("name") if isinstance(b.get("group"), dict) else b.get("group.name"),
        } for b in banners]
        _output_json(out)
    else:
        if not banners:
            print("No banners found.")
            return
        print(f"{'ID':<12} {'Name':<35} {'Status':<10} {'Group'}")
        print("-" * 80)
        for b in banners:
            g_name = b.get("group", {}).get("name", "") if isinstance(b.get("group"), dict) else b.get("group.name", "")
            print(f"{b.get('id', ''):<12} {(b.get('bannerName') or ''):<35} "
                  f"{(b.get('adStatus') or ''):<10} {g_name}")


def cmd_banner_create(args: argparse.Namespace) -> None:
    """Create an image banner (image from local path or URL)."""
    banner: dict = {
        "groupId": args.group_id,
        "name": args.name,
        "clickthruUrl": args.clickthru_url,
        "file": _load_image_b64(args.image),
    }
    if args.status:
        banner["status"] = args.status

    data = _api_call("banners.create", [[banner]], getattr(args, "user_id", None))
    # banners.create returns bannerIds as [{"id": ..., "requestId": ...}]; normalise to ints.
    raw_ids = data.get("bannerIds") or data.get("ids") or []
    ids = [i.get("id") if isinstance(i, dict) else i for i in raw_ids]

    if args.json:
        _output_json({"bannerIds": ids})
    else:
        print(f"Banner created: ID {ids[0] if ids else '?'}")


def cmd_banner_download(args: argparse.Namespace) -> None:
    """Download a group's banner images to a local directory.

    Reads image.url via banners.list (the old imageURL column is deprecated and
    always returns empty). Useful for versioning display creatives back into a
    repo — the Sklik UI has no bulk creative export.
    """
    cols = ["id", "bannerName", "adStatus", "image.url",
            "image.width", "image.height", "group.id", "group.name"]
    data = _api_call("banners.list", [{"isDeleted": False}, {
        "limit": 500, "offset": 0, "displayColumns": cols,
    }], getattr(args, "user_id", None))
    banners = [b for b in data.get("banners", [])
               if (b.get("group", {}).get("id") if isinstance(b.get("group"), dict)
                   else b.get("group.id")) == args.group_id]

    if not banners:
        if args.json:
            _output_json({"downloaded": [], "groupId": args.group_id})
        else:
            print("No banners found for this group.")
        return

    os.makedirs(args.out, exist_ok=True)
    results = []
    for b in banners:
        img = b.get("image", {}) if isinstance(b.get("image"), dict) else {}
        url = img.get("url") or b.get("image.url")
        bid = b.get("id")
        name = b.get("bannerName") or "banner"
        if not url:
            results.append({"id": bid, "name": name, "error": "no image.url returned"})
            continue
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            results.append({"id": bid, "name": name, "error": str(e)})
            continue
        w = img.get("width") or b.get("image.width")
        h = img.get("height") or b.get("image.height")
        dims = f"_{w}x{h}" if w and h else ""
        safe = re.sub(r"[^\w.-]+", "_", str(name)).strip("_") or "banner"
        ext = _image_ext(url, resp.headers.get("Content-Type"))
        path = os.path.join(args.out, f"{safe}{dims}_{bid}.{ext}")
        with open(path, "wb") as f:
            f.write(resp.content)
        results.append({"id": bid, "name": name, "file": path,
                        "url": url, "bytes": len(resp.content)})

    if args.json:
        _output_json({"downloaded": results, "groupId": args.group_id, "out": args.out})
    else:
        ok = sum(1 for r in results if r.get("file"))
        for r in results:
            if r.get("file"):
                print(f"✓ {r['file']} ({r['bytes']} B)")
            else:
                print(f"✗ banner {r['id']} ({r['name']}): {r['error']}")
        print(f"\nDownloaded {ok}/{len(results)} banner(s) to {args.out}")


def cmd_banner_remove(args: argparse.Namespace) -> None:
    """Remove an image banner."""
    if not args.confirm:
        _fail_msg("Requires --confirm flag.")

    _api_call("banners.remove", [[args.banner_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"removed": True, "bannerId": args.banner_id})
    else:
        print(f"Banner {args.banner_id} removed.")


def cmd_banner_update(args: argparse.Namespace) -> None:
    """Update a banner's status/name/clickthru URL in place.

    Deliberately does NOT take an image: changing the creative (`file`) makes
    the API create a NEW banner — for that use the create-first replace flow
    (banner-create new → verify → banner-remove old).
    """
    banner: dict = {"id": args.banner_id}
    if args.name:
        banner["name"] = args.name
    if args.clickthru_url:
        banner["clickthruUrl"] = args.clickthru_url
    if args.status:
        banner["status"] = args.status

    if len(banner) == 1:
        _fail_msg("No fields to update. Use --name, --clickthru-url, or --status.")

    _api_call("banners.update", [[banner]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"updated": True, "bannerId": args.banner_id})
    else:
        print(f"Banner {args.banner_id} updated.")


def cmd_banner_restore(args: argparse.Namespace) -> None:
    """Restore (undelete) a removed banner."""
    _api_call("banners.restore", [[args.banner_id]], getattr(args, "user_id", None))
    if args.json:
        _output_json({"restored": True, "bannerId": args.banner_id})
    else:
        print(f"Banner {args.banner_id} restored.")
