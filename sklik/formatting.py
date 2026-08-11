"""Pure formatting helpers: CZK/haléře conversion and JSON output."""
from __future__ import annotations

import json



# ---------------------------------------------------------------------------
# Price conversion helpers
# ---------------------------------------------------------------------------

def _czk_to_halere(czk: float) -> int:
    """Convert CZK to halere."""
    return int(round(czk * 100))


def _halere_to_czk(halere: int | None) -> float | None:
    """Convert halere to CZK."""
    if halere is None:
        return None
    return halere / 100.0


def _format_money(halere: int | None) -> str:
    """Format halere as CZK string."""
    if halere is None:
        return "—"
    return f"{halere / 100:.2f} Kč"


def _output_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _convert_stats_to_czk(stats: list[dict]) -> list[dict]:
    """Convert money fields in stats from halere to CZK.

    conversionValue is NOT here: the API returns it in plain CZK (it's the
    value the conversion code sends), unlike the other money columns —
    verified live against the API's own pno column, see docs/api-notes.md.
    """
    money_fields = ["avgCpc", "totalMoney", "clickMoney", "impressionMoney", "avgCpt"]
    result = []
    for s in stats:
        s2 = dict(s)
        for f in money_fields:
            if f in s2 and s2[f] is not None:
                s2[f] = round(s2[f] / 100, 2)
        result.append(s2)
    return result


def _format_stat_date(stat: dict, granularity: str = "total") -> str:
    """Row prefix with the period start date; empty for `total` granularity.

    Every stats row carries a `date` (API format `20260810`), but on `total`
    it's just the window's first day while the numbers are the whole-window
    sum — printing it there would label an aggregate as a single day. Only
    split granularities get the prefix, where it's what tells rows apart.
    """
    if granularity == "total":
        return ""
    raw = stat.get("date")
    if raw is None:
        return ""
    d = str(raw)[:8]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}  " if len(d) == 8 else f"{d}  "


def _format_share(value: float | None) -> str:
    """Format an API ratio (0–1) as a percentage string.

    The API returns ctr / winRate / exhaustedBudgetShare as fractions, not
    percentages — printing them raw understates them 100×.
    """
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"
