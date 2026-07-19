"""Image IO shared by combined ads and banners."""
from __future__ import annotations

import base64
import re

import requests

from sklik.api import _fail_msg



# ---------------------------------------------------------------------------
# Commands — Image banners (context/display network)
# ---------------------------------------------------------------------------
# banners.create takes the image bytes directly in `file` (base64 over JSON),
# so the CLI accepts either a local path or a public URL and encodes it. Allowed
# formats/sizes come from images.constraints.list (e.g. 300×300, 728×90; ≤250 KB).

def _load_image_b64(src: str) -> str:
    """Read an image from a local path or http(s) URL and return base64 bytes."""
    try:
        if src.startswith(("http://", "https://")):
            resp = requests.get(src, timeout=30)
            resp.raise_for_status()
            raw = resp.content
        else:
            with open(src, "rb") as f:
                raw = f.read()
    except (OSError, requests.RequestException) as e:
        _fail_msg(f"Could not load image '{src}': {e}")
    return base64.b64encode(raw).decode("ascii")


def _image_ext(url: str, content_type: str | None) -> str:
    """Best-effort file extension from a URL or Content-Type header."""
    m = re.search(r"\.(jpe?g|png|gif|webp)(?:$|\?)", url, re.I)
    if m:
        return "jpg" if m.group(1).lower() in ("jpeg", "jpg") else m.group(1).lower()
    ct = (content_type or "").lower()
    for key, ext in (("jpeg", "jpg"), ("png", "png"), ("gif", "gif"), ("webp", "webp")):
        if key in ct:
            return ext
    return "img"
