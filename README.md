# Sklik PPC App

CLI aplikace pro správu PPC kampaní na **Seznam Sklik** přes [API Drak](https://api.sklik.cz/drak/) (JSON, verze v5).

Pokrývá kompletní životní cyklus *search* i *obsahových* kampaní — kampaně, sestavy, klíčová slova, inzeráty, vylučující slova, výzkum klíčových slov, statistiky — plus měření konverzí, retargetingová publika, cílení (regiony / zařízení / rozvrh), obrázkové bannery a kombinovanou (nativní) reklamu.

> 🎓 **Tahle appka je doprovodný materiál k 7. lekci kurzu [AI First](https://aifirst.cz).** V lekci ukazuju marketérům, jak využít vibe coding v každodenní práci — postavit si vlastní nástroj, který za vás dělá rutinu (tady správu Sklik kampaní z Claude Code) a šetří hodiny času. Součástí repa je i [skill pro Claude Code](#skill-pro-claude-code-sklik-ppc), který appku obaluje. Chceš se to naučit prakticky? → **[aifirst.cz](https://aifirst.cz)**

## 🆕 Co je nového

**10. 6. 2026 — v1.1.0: Kombinovaná (nativní) reklama** 🎉

Přibyl příkaz [`combined-create`](#kombinovaná-nativní-reklama) — vytváření **kombinované reklamy** přes API. To je formát, kterým se na obsahové síti Seznamu zobrazuje i **nativní reklama v článcích**: dodáš texty + obrázky a Sklik z nich sám skládá podobu pro nativní pozice v článcích i responzivní bannerové sloty. Výpis přes `ads` (`adType: combined`), statistiky přes `ad-stats`.

## Požadavky

- Python 3.10+
- Sklik API token ([jak ho získat](#získání-api-tokenu))

## Instalace

```bash
# Setup skript (vytvoří venv, nainstaluje závislosti, založí .env)
./setup.sh

# Doplň API token do .env
nano .env
```

Nebo ručně:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # a doplň token
```

## Autentizace

### Získání API tokenu

1. Přihlas se do Skliku a otevři **[www.sklik.cz/settings](https://www.sklik.cz/settings)**.
2. Najdi sekci **„Přístup k API Drak"**.
3. Vygeneruj / zkopíruj svůj **API token**.
4. Token vlož do souboru `.env` jako `SKLIK_API_TOKEN` (viz [Konfigurace](#konfigurace) níže).

> Token je heslo k tvému Sklik účtu přes API — nikam ho nedávej do kódu ani do gitu, patří **výhradně** do `.env` (které je v `.gitignore`).

### Konfigurace

Tokeny patří do `.env` (soubor je v `.gitignore`, nikdy se necommituje):

```bash
SKLIK_API_TOKEN=tvuj-token            # výchozí účet (--account vynechán)
SKLIK_API_TOKEN_CLIENTB=tvuj-token    # volitelný další login → --account clientb
```

Účty se zjistí z prostředí za běhu — žádná jména nejsou natvrdo v kódu, takže můžeš mít libovolný počet loginů. Session se po přihlášení cachuje 25 minut do `.session_cache_<account>.json` (taky gitignored) a automaticky se obnoví při vypršení (401).

### Účty vs. spravované účty

Dva nezávislé globální přepínače (uvádějí se **před** názvem příkazu):

- **`--account <name>`** — který *login / token* se použije. Bez přepínače = `default` (`SKLIK_API_TOKEN`); `--account <name>` čte `SKLIK_API_TOKEN_<NAME>`.
- **`--user-id <id>`** — *spravovaný účet* pod aktivním loginem (agentura → klientský účet).

```bash
python sklik_cli.py account                          # výchozí login
python sklik_cli.py --account clientb account         # jiný login
python sklik_cli.py --user-id 123456 campaigns        # spravovaný účet pod aktivním loginem
```

> `suggest` a `suggest-stats` `--user-id` nepodporují (ale `--account` ano).

## Použití

Příkazy se spouští přes `run.sh` (sám aktivuje venv):

```bash
./run.sh <příkaz> [přepínače]
# ekvivalent: source venv/bin/activate && python sklik_cli.py <příkaz> [přepínače]
```

**Konvence napříč CLI:**

- **Ceny v CZK** — CLI přijímá i zobrazuje koruny; na haléře (×100) převádí samo.
- **`--json`** — strojově čitelný výstup (použij při parsování).
- **`--confirm`** — povinný u všech mazacích operací (`*-remove`).
- Filtry `--campaign-id` / `--group-id` / `--status` se aplikují na straně klienta (API je v restriction nepodporuje).
- Výchozí rozsah statistik je posledních 30 dní.

### Účet

| Příkaz | Popis |
|--------|-------|
| `account` | Info o účtu, zůstatek peněženky, spravované účty |

### Kampaně

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `campaigns` | `--status active/suspend`, `--json` |
| `campaign-create` | `--name`, `--day-budget` (CZK), `--type fulltext/context/product`, `--regions`, `--device-bids`, `--json` |
| `campaign-update` | `--campaign-id`, `--name`, `--day-budget`, `--status`, `--regions`, `--device-bids`, `--schedule-json`, `--json` |
| `campaign-remove` | `--campaign-id`, `--confirm`, `--json` |
| `campaign-stats` | `--campaign-id`, `--date-from`, `--date-to`, `--json` |
| `campaign-targeting` | `--campaign-id`, `--json` — přehled geo / zařízení / rozvrhu |

**Cílení** (`campaign-create` / `campaign-update`):

- `--regions` — ID regionů oddělená čárkou (prázdný řetězec při update geo cílení smaže)
- `--device-bids` — modifikátory v % jako `desktop:mobile:tablet:other`, např. `0:-30:-30:-100`
- `--schedule-json` (jen update) — `{"daySchedule":[{"value":[24 hodinových hodnot 0-100]}, …×7]}`, týden začíná pondělím

### Sestavy (ad groups)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `groups` | `--campaign-id`, `--json` |
| `group-create` | `--campaign-id`, `--name`, `--cpc` (CZK), `--json` |
| `group-update` | `--group-id`, `--name`, `--cpc`, `--status`, `--json` |
| `group-remove` | `--group-id`, `--confirm`, `--json` |
| `group-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--json` |

### Klíčová slova

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `keywords` | `--group-id`, `--campaign-id`, `--json` |
| `keyword-create` | `--group-id`, `--name`, `--match-type broad/phrase/exact`, `--cpc` (CZK), `--json` |
| `keyword-create-batch` | `--group-id`, `--keywords-json`, `--json` |
| `keyword-update` | `--keyword-id`, `--cpc`, `--status`, `--url`, `--json` |
| `keyword-remove` | `--keyword-id`, `--confirm`, `--json` |
| `keyword-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--json` |

> `name` ani `matchType` klíčového slova nelze měnit — je nutné slovo smazat a vytvořit znovu.

### Inzeráty (ETA)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `ads` | `--group-id`, `--json` |
| `ad-create` | `--group-id`, `--headline1/2/3`, `--description1/2`, `--final-url`, `--path1/2`, `--json` |
| `ad-update` | `--ad-id`, `--status`, `--json` |
| `ad-remove` | `--ad-id`, `--confirm`, `--json` |
| `ad-stats` | `--group-id`, `--date-from`, `--date-to`, `--json` |

> Změna kreativních polí inzerátu vytvoří nový inzerát (API vrací `newAdIds`).

### Kombinovaná (nativní) reklama

Formát pro obsahovou síť, kterým se zobrazuje i **nativní reklama v článcích** na webech Seznamu. Sklik z dodaných textů a obrázků automaticky skládá výslednou podobu (nativní pozice v článku, responzivní sloty, branding) — konkrétní umístění nevybíráš.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `combined-create` | `--group-id`, `--short-line` (max 25 zn.), `--long-line` (max 90), `--description` (max 90), `--company-name` (max 25), `--final-url`, `--image-landscape` (1,91:1, min 600×314 px), `--image-square` (1:1, min 300×300 px), `--image-logo`, `--image-landscape-logo`, `--color-main/--color-accent` (hex), `--mobile-final-url`, `--tracking-template`, `--status`, `--json` |

Výpis přes `ads` (`adType: combined`), statistiky přes `ad-stats`, smazání přes `ad-remove`. Obrázky: lokální cesta nebo URL (jpg/png/gif, max 1 MB), CLI je zakóduje samo.

> **Pozor:** Sklik z textů **tiše odstraňuje zakázané znaky** (např. pomlčku „—" z titulku) — bez chyby i bez warningu. Po vytvoření si finální znění ověř přes `ads --group-id X --json`. Úprava textů/obrázků není možná — smaž (`ad-remove`) a vytvoř znovu.

### Vylučující klíčová slova

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `negatives` | `--group-id`, `--campaign-id`, `--json` |
| `negative-add` | `--group-id`/`--campaign-id`, `--name`, `--match-type negativeBroad/negativePhrase/negativeExact`, `--json` |
| `negative-add-batch` | `--group-id`/`--campaign-id`, `--keywords-json`, `--json` |
| `negative-remove` | `--keyword-id`, `--confirm`, `--json` |

### Výzkum klíčových slov

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `suggest` | `--query`, `--limit`, `--related`, `--order-by avgSearchCount/cpc/score`, `--json` |
| `suggest-stats` | `--queries` (oddělené čárkou), `--granularity monthly/daily`, `--json` |

### Vyhledávací dotazy

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `search-queries` | `--campaign-id`, `--group-id`, `--date-from`, `--date-to`, `--limit`, `--json` |

### Sitelinky

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `sitelinks` | `--json` |
| `sitelink-create` | `--name`, `--url`, `--json` |
| `sitelink-remove` | `--sitelink-id`, `--confirm`, `--json` |

### Konverze (definice měření)

Konverze = pojmenovaná definice cílové akce (nákup, registrace…) a její hodnoty. CLI spravuje *definice*; samotné měření (pixel / SEM) žije na webu.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `conversions` | `--json` |
| `conversion-types` | `--json` — ID typů použitých na účtu (viz poznámka níže) |
| `conversion-create` | `--name`, `--type-id`, `--value` (CZK), `--color`, `--json` |
| `conversion-update` | `--conversion-id`, `--name`, `--value`, `--color`, `--json` |
| `conversion-remove` | `--conversion-id`, `--confirm`, `--json` |

> **Pozn.:** Účty se zapnutým **SEM** (Seznam Event Measurement) `conversions.*` metody používat nemohou — CLI v takovém případě vypíše srozumitelnou hlášku. Metoda `listConversionTypes` je na straně Sklika nefunkční (HTTP 500), proto `conversion-types` odvozuje typy z existujících konverzí.

### Retargeting (publika)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `retargeting` | `--json` |
| `retargeting-create` | `--name`, `--membership` (dny), `--description`, `--use-historic`, `--take-all-users`, `--conditions-json`, `--json` |
| `retargeting-update` | `--list-id`, `--name`, `--membership`, `--description`, `--json` |
| `retargeting-remove` | `--list-id`, `--confirm`, `--json` |

### Obrázkové bannery

Statické bannery (jpg/png/gif) pro obsahovou síť. Pro HTML5 bannery použij jiný nástroj — tady jde o statické formáty.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `banner-formats` | `--json` — povolené rozměry a limity velikosti |
| `banners` | `--group-id`, `--json` |
| `banner-create` | `--group-id`, `--name`, `--clickthru-url`, `--image` (lokální cesta **nebo** http URL), `--status`, `--json` |
| `banner-remove` | `--banner-id`, `--confirm`, `--json` |

> `--image` přijme lokální soubor i veřejnou URL — CLI obrázek načte a pošle do Skliku zakódovaný (base64). Drž se povolených formátů z `banner-formats` (pevné rozměry, ≤ 250 KB).

## Příklady

```bash
# Výzkum klíčových slov
./run.sh suggest --query "kurz ai" --related --limit 30

# Sestavení kampaně shora dolů
./run.sh campaign-create --name "AI kurzy - Search" --day-budget 300 --type fulltext
./run.sh group-create --campaign-id 123 --name "Obecné" --cpc 8
./run.sh keyword-create-batch --group-id 456 \
  --keywords-json '[{"name":"kurz ai","matchType":"phrase","cpc":12},{"name":"ai školení"}]'
./run.sh ad-create --group-id 456 \
  --headline1 "Kurz AI pro firmy" --headline2 "Prakticky a hned" \
  --description1 "Naučte se AI využívat v praxi. Přihlaste se ještě dnes." \
  --final-url "https://example.cz/kurz"

# Vyloučit nerelevantní dotazy (campaign-level)
./run.sh negative-add-batch --campaign-id 123 --keywords-json '["zdarma","free","práce"]'

# Cílení: snížit nabídku na mobilu/tabletu, vyloučit ostatní zařízení
./run.sh campaign-update --campaign-id 123 --device-bids 0:-30:-30:-100
./run.sh campaign-targeting --campaign-id 123

# Statistiky za konkrétní období (JSON pro další zpracování)
./run.sh campaign-stats --campaign-id 123 --date-from 2026-01-01 --date-to 2026-01-31 --json

# Vyhledávací dotazy, které spustily reklamu
./run.sh search-queries --campaign-id 123 --limit 50

# Měření a publika
./run.sh conversions
./run.sh retargeting
./run.sh banner-formats

# Kombinovaná (nativní) reklama pro obsahovou síť
./run.sh combined-create --group-id 789 \
  --short-line "Kurz AI pro firmy" \
  --long-line "Naučte se AI využívat v každodenní praxi" \
  --description "Praktický videokurz pro marketéry a podnikatele." \
  --company-name "Example s.r.o." \
  --final-url "https://example.cz/kurz" \
  --image-landscape ./obrazky/landscape_1200x628.jpg \
  --image-square ./obrazky/square_1200x1200.jpg
```

## Skill pro Claude Code (`/sklik-ppc`)

Součástí repa je i **skill pro [Claude Code](https://claude.com/claude-code)** ve složce [`skill/`](skill/). Ten obaluje tohle CLI a přidává PPC know-how (pravidla inzerátů, struktura kampaní, scénáře pro search i bannery), takže můžeš celé kampaně spravovat konverzací — `/sklik-ppc create search`, `/sklik-ppc optimize`, …

Skill ti dává **mechaniku** (jak věci udělat nástrojem) a **pravidla** (co Sklik povoluje). Strategii průběžné optimalizace si nastavíš podle svých cílů.

➡️ **Instalace skillu:** viz [`skill/INSTALL.md`](skill/INSTALL.md) (zkopíruj složku do `~/.claude/skills/` a nastav cestu k appce).

## Struktura projektu

```
sklik-ppc-app/
├── sklik_cli.py        # Celé CLI (jeden soubor)
├── requirements.txt    # Závislosti (requests, python-dotenv)
├── setup.sh            # Instalační skript
├── run.sh              # Spouštěcí skript (aktivuje venv)
├── .env.example        # Šablona pro tokeny
├── CLAUDE.md           # Vývojářská reference
├── .env                # Tokeny (NEVERZOVAT)
└── skill/              # Skill pro Claude Code (/sklik-ppc) + INSTALL.md
```

## API poznámky

- Protokol: JSON-RPC `POST` na `https://api.sklik.cz/drak/json/v5/{metoda}`. Endpoint je **připnutý na v5**, aby se CLI tiše nerozbilo při major změně API.
- Reporty jsou dvoukrokové: `createReport` (filtry + období) → `readReport` (stránkování + sloupce).
- API **nepodporuje** filtry na nadřazené entity (`campaign.ids`, `group.ids`, `status`) v `restrictionFilter` — proto se aplikují na straně klienta.
- Příklady použití API Drak: [github.com/seznam/sklik-api-examples](https://github.com/seznam/sklik-api-examples).

## O kurzu AI First

Tahle appka vznikla jako ukázka do **7. lekce kurzu [AI First](https://aifirst.cz)** — praktického videokurzu AI a vibe codingu pro marketéry, podnikatele a kohokoli s chutí tvořit.

Lekce ukazuje, jak vibe coding zapojit do **každodenní marketingové práce**: postavit si vlastní nástroje na míru, automatizovat rutinu, ušetřit hodiny času a zvednout efektivitu — bez programátora.

> *„Nechte AI dělat práci, kterou musíte, ať můžete dělat práci, kterou chcete."*

- 🎬 18,5 hodiny praktických videí, 10 lekcí
- 🚀 Reálná praxe — stavíš věci, které opravdu používáš (jako tenhle nástroj)
- ⏱️ Důraz na úsporu času a efektivitu v běžné práci
- 👉 **[aifirst.cz](https://aifirst.cz)**

## Licence

MIT

