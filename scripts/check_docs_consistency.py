#!/usr/bin/env python3
"""Mechanická kontrola konzistence CLI ↔ dokumentace ↔ bundled skill.

Spouštět před každým releasem (a klidně v CI):

    python scripts/check_docs_consistency.py

Kontroluje:
  1. parser/dispatch parita v sklik/cli.py
  2. každý CLI příkaz je zmíněný v README.md
  3. počet příkazů deklarovaný v CLAUDE.md ("## Commands (N, ...)") sedí
  4. verze v sklik/__init__.py je v README.md i CHANGELOG.md
  5. žádný dokument/skill nezmiňuje neexistující příkaz (fantom po přejmenování)

Exit 0 = vše OK; exit 1 = aspoň jeden nález (vypsané na stderr).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Kebab tokeny záměrně zmiňované jako NEexistující příkazy (docs vysvětlují,
# že takový příkaz není) — nejsou to fantomy.
ALLOWED_NON_COMMANDS = {
    "banner-replace",
    "banner-create-batch",
}

# Fantomy hledáme jen u tokenů s těmito prefixy (jinak by pravidlo chytalo
# běžná slovní spojení typu `create-first`).
COMMAND_PREFIXES = (
    "campaign-", "group-", "keyword-", "ad-", "negative-", "banner-",
    "placement-", "placements-", "targeting-", "budget-", "retargeting-",
    "sitelink-", "sitelinks-", "conversion-", "combined-", "suggest-",
    "autotagging-", "search-", "api-", "keyword-",
)

DOC_FILES = [
    "README.md",
    "CLAUDE.md",
    "docs/api-notes.md",
    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "skill" / "sklik-ppc").glob("*.md")),
]


def main() -> int:
    errors: list[str] = []

    cli_src = (ROOT / "sklik" / "cli.py").read_text()
    commands = set(re.findall(r'add_parser\(\s*"([a-z][a-z0-9-]*)"', cli_src))
    dispatch = set(re.findall(r'"([a-z][a-z0-9-]*)":\s*cmd_', cli_src))

    # 1. parser/dispatch parita
    if commands != dispatch:
        errors.append(f"cli.py: parser/dispatch mismatch: {sorted(commands ^ dispatch)}")

    # 2. každý příkaz zdokumentovaný v README
    readme = (ROOT / "README.md").read_text()
    undocumented = sorted(c for c in commands if f"`{c}`" not in readme)
    if undocumented:
        errors.append(f"README.md: nezdokumentované příkazy: {undocumented}")

    # 3. počet příkazů v CLAUDE.md
    claude = (ROOT / "CLAUDE.md").read_text()
    m = re.search(r"## Commands \((\d+)", claude)
    if not m:
        errors.append('CLAUDE.md: chybí nadpis "## Commands (N, ...)"')
    elif int(m.group(1)) != len(commands):
        errors.append(f"CLAUDE.md: deklaruje {m.group(1)} příkazů, cli.py jich má {len(commands)}")

    # 4. konzistence verze
    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "sklik" / "__init__.py").read_text()).group(1)
    if version not in readme:
        errors.append(f"README.md: nezmiňuje aktuální verzi {version}")
    if version not in (ROOT / "CHANGELOG.md").read_text():
        errors.append(f"CHANGELOG.md: nemá záznam pro verzi {version}")

    # 5. fantomové příkazy v docs/skillu
    for rel in DOC_FILES:
        text = (ROOT / rel).read_text()
        for snippet in re.findall(r"`([^`\n]+)`", text):
            token = snippet.split()[0] if snippet.split() else ""
            if token.startswith("--") or "." in token or "/" in token:
                continue
            if not re.fullmatch(r"[a-z][a-z0-9]*(-[a-z0-9]+)+", token):
                continue
            if not token.startswith(COMMAND_PREFIXES):
                continue
            if token not in commands and token not in ALLOWED_NON_COMMANDS:
                errors.append(f"{rel}: zmiňuje neexistující příkaz `{token}`")

    if errors:
        print(f"KONZISTENCE: {len(errors)} nález(ů):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {len(commands)} příkazů, dokumentace i skill konzistentní (verze {version}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
