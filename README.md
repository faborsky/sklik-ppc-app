# Sklik PPC App

CLI aplikace pro správu PPC kampaní na **Seznam Sklik** přes [API Drak](https://api.sklik.cz/drak/) (JSON, verze v5).

Pokrývá kompletní životní cyklus *search* i *obsahových* kampaní — kampaně, sestavy, klíčová slova, inzeráty, vylučující slova, výzkum klíčových slov, statistiky — plus měření konverzí, retargetingová publika, cílení (regiony / zařízení / rozvrh), obrázkové bannery a kombinovanou (nativní) reklamu.

> 🎓 **Tahle appka je doprovodný materiál k 7. lekci kurzu [AI First](https://aifirst.cz).** V lekci ukazuju marketérům, jak využít vibe coding v každodenní práci — postavit si vlastní nástroj, který za vás dělá rutinu (tady správu Sklik kampaní z Claude Code) a šetří hodiny času. Součástí repa je i [skill pro Claude Code](#skill-pro-claude-code-sklik-ppc), který appku obaluje. Chceš se to naučit prakticky? → **[aifirst.cz](https://aifirst.cz)**

## 🆕 Co je nového

Poslední verze **1.7.1** — `groups` teď ve výpisu ukazuje i frekvenční strop sestavy (`maxUserDailyImpressions`); dosud šel jen nastavit, ne přečíst. Předtím **1.7.0** — vizuální podpis (ASCII banner jen pro lidi v terminálu) a seskupený `--help` (88 příkazů po doménách). Celá historie: **[CHANGELOG.md](CHANGELOG.md)**.

## Dva způsoby, jak appku používat

**A) Orchestrace přes Claude Code (výchozí a nejjednodušší).** Appku řídí Claude Code (nebo jiný coding agent) přes přibalený skill — ty zadáváš cíle česky, agent volá CLI, drží bezpečnostní pravidla (schválení před zápisem, `--confirm` u mazání, atomická výměna inzerátů) a hlídá API limity. Nejrychlejší start: otevři Claude Code a vlož mu prompt typu:

> *Naklonuj https://github.com/faborsky/sklik-ppc-app, spusť `./setup.sh`, nainstaluj mi přibalený skill podle `skill/INSTALL.md` a pak mi řekni, kam mám vložit svůj Sklik API token.*

Claude vše připraví; **token pak vlož ručně do `.env`** (soubor je v `.gitignore` — token nikdy neposílej do chatu ani nikam do kódu). Odteď stačí `/sklik-ppc` z libovolného projektu. Detaily instalace skillu: [skill/INSTALL.md](skill/INSTALL.md).

**B) Vlastní automatizace a agentní řešení (pro pokročilé).** Appka je normální CLI stavěné na strojové řízení: `--json` výstupy, chyby jako `{"error": …}` na stdout, request-budget vestavěný (neuřídíš API limity omylem). Vezmi si ji do vlastních skriptů, cronů nebo agentních workflow — kompletní referenci příkazů máš níže v tomhle README a chování API (quirky, limity, status kódy) v [docs/api-notes.md](docs/api-notes.md).

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

> `suggest` a `suggest-stats` přepínač `--user-id` tiše ignorují (API metody parametr spravovaného účtu nemají) — volej je bez něj. `--account` funguje normálně.

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
| `api-limits` | Reálné API limity účtu (rate/batch/hodnotové rozsahy) + živé lokální využití request-budgetu; `--json` |
| `credit` | Zůstatek kreditu peněženky v Kč (bez DPH i s DPH) — i pro spravované účty; `--json` |
| `regions` | Číselník ID regionů pro `--regions` cílení; `--json` |
| `autotagging` | Aktuální konfigurace autotaggingu (UTM parametry); `--json` |
| `autotagging-update` | `--enabled on/off`, `--config-json` (částečná konfigurace, mergne se přes současnou); `--json` |

```bash
./run.sh api-limits            # limity + kolik requestů jsi spotřeboval (60 s / 24 h)
./run.sh api-limits --json     # strukturovaný výstup
```

> **Ochrana účtu před zablokováním.** Appka počítá každé volání do per-account souboru `.rate_limit_<account>.json` (přežívá napříč session i paralelními běhy) a kontroluje ho *před* každým requestem: na 90 % minutového limitu počká, na denním limitu operaci odmítne. Limity bere z `api.limits` (cache ~1×/den). Counter neřešíš ručně — appka to hlídá za tebe.

### Pulse

Souhrn celého účtu **jedním voláním** — místo řetězení `account` + `campaigns` + `campaign-stats`. Vrátí totály, statistiky po kampaních, delty vůči předchozímu stejně dlouhému období a top movery, předpočítané do kompaktního digestu (ideální pro levný/rychlý analytický pull).

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `pulse` | `--days N` (default 7), `--date-from`/`--date-to` (přebijí `--days`), `--no-compare` (vynechá delty, o 1 API volání míň), `--json` |

```bash
./run.sh pulse                 # posledních 7 dní vs předchozích 7
./run.sh pulse --days 30       # posledních 30 dní vs předchozích 30
./run.sh pulse --no-compare    # bez srovnání s předchozím obdobím
./run.sh pulse --json          # strukturovaný výstup pro další zpracování
```

> `pulse` si přes `stats.status` ověří, že statistiky za celé okno jsou už kompletní — když ne (typicky dnešek je „preparing"), přidá varování (`statsWarning` v `--json`), že čísla a delty jsou zatím z částečných dat.

### Kampaně

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `campaigns` | `--status active/suspend`, `--json` |
| `campaign-create` | `--name`, `--day-budget` (CZK), `--type fulltext/context/product`, `--status active/suspend`, `--regions`, `--device-bids`, `--ad-selection`, `--json` |
| `campaign-update` | `--campaign-id`, `--name`, `--day-budget`, `--status`, `--regions`, `--device-bids`, `--schedule-json`, `--ad-selection`, `--json` |
| `campaign-remove` | `--campaign-id`, `--confirm`, `--json` |
| `campaign-stats` | `--campaign-id`, `--date-from`, `--date-to`, `--json` |
| `campaign-targeting` | `--campaign-id`, `--json` — přehled geo / zařízení / rozvrhu |
| `campaign-restore` | `--campaign-id`, `--json` — obnoví smazanou kampaň (undelete) |

**Cílení** (`campaign-create` / `campaign-update`):

- `--regions` — ID regionů oddělená čárkou (prázdný řetězec při update geo cílení smaže)
- `--device-bids` — modifikátory v % jako `desktop:mobile:tablet:other`, např. `0:-30:-30:-100`
- `--schedule-json` (jen update) — `{"daySchedule":[{"value":[24 hodinových hodnot 0-100]}, …×7]}`, týden začíná pondělím
- `--ad-selection` — rotace inzerátů (`adSelection`): `weighted` (preferuj vyšší CTR, výchozí), `random` (rovnoměrně — čistý A/B test kreativ), `cpa` (nižší CPA), `cos` (nižší CTR)

### Sestavy (ad groups)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `groups` | `--campaign-id`, `--json` — výpis vrací i `maxUserDailyImpressions` (frekvenční strop sestavy) |
| `group-create` | `--campaign-id`, `--name`, `--cpc` (CZK), `--max-daily-impression`, `--json` |
| `group-update` | `--group-id`, `--name`, `--cpc`, `--status`, `--max-daily-impression`, `--json` |
| `group-remove` | `--group-id`, `--confirm`, `--json` |
| `group-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--json` |
| `group-restore` | `--group-id`, `--json` — obnoví smazanou sestavu (undelete) |

> `--max-daily-impression N` = frekvenční limit (max. zobrazení na uživatele za den) — Sklik pole `maxUserDailyImpression`.

### Klíčová slova

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `keywords` | `--group-id`, `--campaign-id`, `--json` |
| `keyword-create` | `--group-id`, `--name`, `--match-type broad/phrase/exact`, `--cpc` (CZK), `--url`, `--json` |
| `keyword-create-batch` | `--group-id`, `--keywords-json`, `--json` |
| `keyword-update` | `--keyword-id`, `--cpc`, `--status`, `--url`, `--json` |
| `keyword-remove` | `--keyword-id`, `--confirm`, `--json` |
| `keyword-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--json` |
| `keyword-restore` | `--keyword-id`, `--json` — obnoví smazané slovo (undelete) |
| `keyword-set` | `--group-id`, `--keywords-json`, `--remove-others`, `--json` — deklarativní nastavení slov sestavy |

> `name` ani `matchType` klíčového slova nelze měnit — je nutné slovo smazat a vytvořit znovu.
> `keyword-set` je **upsert**: chybějící slova přidá, existujícím upraví CPC/URL, dříve smazaná obnoví. S `--remove-others` navíc smaže všechna slova, která v payloadu nejsou — plná synchronizace sestavy podle seznamu.

### Inzeráty (ETA)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `ads` | `--group-id`, `--campaign-id`, `--json` |
| `ad-create` | `--group-id`, `--headline1/2/3`, `--description1/2` (alias `--description`), `--final-url`, `--path1/2`, `--json` |
| `ad-update` | `--ad-id`, `--status`, `--json` (jen stav, na místě) |
| `ad-replace` | `--ad-id`, `--headline1/2/3`, `--description/--description2`, `--final-url`, `--path1/2`, `--json` |
| `ad-remove` | `--ad-id`, `--confirm`, `--json` |
| `ad-stats` | `--group-id`, `--date-from`, `--date-to`, `--json` |
| `ad-restore` | `--ad-id`, `--json` — obnoví smazaný inzerát (undelete) |

> **Změna textu inzerátu = `ad-replace`, NIKDY ruční `ad-remove` + `ad-create`.** Sklik neumí text upravit na místě: jakákoli změna kreativy udělá přes `ads.update` **atomickou výměnu na serveru** (smaže starý + vytvoří nový v JEDNÉ operaci, vrátí `newAdIds`). Když nový inzerát neprojde validací (typicky `ad_duplicate_in_db`), **původní zůstane nedotčený**. Ruční remove+create tuhle jistotu nemá — když selže create po removu, sestava tiše ztratí inzerát (reálně se to stalo). `ad-replace` načte stávající inzerát, aplikuje jen zadaná pole (zbytek zachová), předvaliduje přes `ads.check` a pak provede atomickou výměnu. Jen textové (eta) inzeráty.

### Kombinovaná (nativní) reklama

Formát pro obsahovou síť, kterým se zobrazuje i **nativní reklama v článcích** na webech Seznamu. Sklik z dodaných textů a obrázků automaticky skládá výslednou podobu (nativní pozice v článku, responzivní sloty, branding) — konkrétní umístění nevybíráš.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `combined-create` | `--group-id`, `--short-line` (max 25 zn.), `--long-line` (max 90), `--description` (max 90), `--company-name` (max 25), `--final-url`, `--image-landscape` (1,91:1, min 600×314 px), `--image-square` (1:1, min 300×300 px), `--image-logo`, `--image-landscape-logo`, `--color-main/--color-accent` (hex), `--mobile-final-url`, `--tracking-template`, `--status`, `--json` |

Výpis přes `ads` (`adType: combined`), statistiky přes `ad-stats`, smazání přes `ad-remove`. Obrázky: lokální cesta nebo URL (jpg/png/gif, max 1 MB), CLI je zakóduje samo.

> **Pozor:** Sklik z textů **tiše odstraňuje zakázané znaky** (např. pomlčku „—" z titulku) — bez chyby i bez warningu. Po vytvoření si finální znění ověř přes `ads --group-id X --json`. Kombinovanou reklamu nelze upravit na místě (`ad-replace` je jen pro textové inzeráty kvůli obrázkům) — **vytvoř nový inzerát, ověř, a teprve pak smaž starý** (create-first, aby selhaný create nikdy nesmazal poslední inzerát).

### Vylučující klíčová slova

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `negatives` | `--group-id`, `--campaign-id`, `--json` |
| `negative-add` | `--group-id`/`--campaign-id`, `--name`, `--match-type negativeBroad/negativePhrase/negativeExact`, `--json` |
| `negative-add-batch` | `--group-id`/`--campaign-id`, `--keywords-json`, `--json` |
| `negative-remove` | `--keyword-id`, `--confirm`, `--json` |

> `negatives` umí vypsat jen **skupinové** vylučovačky (`--campaign-id` filtruje přes sestavy dané kampaně). Kampaňové vylučovačky (`negative-add --campaign-id`) jsou v API **write-only** — zapsat jdou, ale zpětně vypsat ne; ověříš je jen ve webovém rozhraní Skliku.

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
| `sitelink-update` | `--sitelink-id`, `--name`, `--url`, `--json` |
| `sitelink-remove` | `--sitelink-id`, `--confirm`, `--json` |
| `sitelink-assign` | `--campaign-id` **nebo** `--group-id`, `--sitelink-ids "1,2,3"` (`""` = odpojit vše), `--json` |
| `sitelinks-assigned` | `--campaign-id` **nebo** `--group-id`, `--json` — co je aktuálně přiřazené |

> **`sitelink-assign` NAHRAZUJE celou sadu** přiřazených sitelinků kampaně/sestavy — vždy pošli kompletní seznam, ne jen přírůstek. **Přejmenování sitelinku (`sitelink-update --name`) vytvoří NOVÉ ID** (server dělá remove+create) — CLI nové ID vypíše; změna `--url` ID zachová.

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
| `retargeting-attach` | `--list-id`, `--group-id`, `--json` — napojí publikum na sestavu jako cílení |
| `retargeting-detach` | `--list-id`, `--group-id`, `--confirm`, `--json` |
| `retargeting-attached` | `--group-id` (bez něj všechny sestavy), `--json` — co je kde napojené |
| `retargeting-exclude` | `--list-id`, `--campaign-id` **nebo** `--group-id`, `--json` — vyloučí publikum (negativní retargeting) |
| `retargeting-exclude-remove` | `--list-id`, `--campaign-id`/`--group-id`, `--confirm`, `--json` |
| `retargeting-excluded` | `--campaign-id`/`--group-id` (bez nich vše na obou úrovních), `--json` |

> Publikum jde napojit jen na sestavy **obsahových** kampaní. Pokus o napojení **smazaného** seznamu vrací `406 Bad values` bez bližší diagnostiky — zkontroluj `deleted` ve výpisu `retargeting --json`.
> **Vyloučení publika** (`retargeting-exclude`) funguje na úrovni kampaně i sestavy — typicky „vyluč stávající zákazníky z akviziční kampaně". Na rozdíl od napojení funguje i na search kampaních.

### Obrázkové bannery

Statické bannery (jpg/png/gif) pro obsahovou síť. Pro HTML5 bannery použij jiný nástroj — tady jde o statické formáty.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `banner-formats` | `--json` — povolené rozměry a limity velikosti |
| `banners` | `--group-id`, `--json` |
| `banner-create` | `--group-id`, `--name`, `--clickthru-url`, `--image` (lokální cesta **nebo** http URL), `--status`, `--json` |
| `banner-download` | `--group-id`, `--out` (složka), `--json` — stáhne obrázky bannerů sestavy na disk |
| `banner-update` | `--banner-id`, `--name`, `--clickthru-url`, `--status`, `--json` (beze změny obrázku) |
| `banner-remove` | `--banner-id`, `--confirm`, `--json` |
| `banner-restore` | `--banner-id`, `--json` — obnoví smazaný banner (undelete) |

> `--image` přijme lokální soubor i veřejnou URL — CLI obrázek načte a pošle do Skliku zakódovaný (base64). Drž se povolených formátů z `banner-formats` (pevné rozměry, ≤ 250 KB).
> `banner-download` čte `image.url` (staré pole `imageURL` je deprecated) a uloží kreativy lokálně — vhodné pro verzování kreativ do repa před výměnou. Výměna banneru = **vytvoř nový a teprve pak smaž starý** (create-first).

### Umístění (cílení na konkrétní weby)

Cílení obsahových sestav na konkrétní weby (v Skliku „umístění"). Vzor je doména nebo cesta — `"mediar.cz"`, `"www.e15.cz/byznys"`.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `placements` | `--group-id`, `--json` |
| `placement-create` | `--group-id`, `--pattern "forbes.cz"`, `--cpc` (CZK, volitelně přebije CPC sestavy), `--status`, `--json` |
| `placement-remove` | `--pattern-id`, `--confirm`, `--json` |
| `placements-excluded` | `--group-id`, `--json` — výpis vyloučených webů |
| `placement-exclude` | `--group-id`, `--pattern "spamweb.cz"`, `--json` — vyloučí web ze sestavy |
| `placement-exclude-remove` | `--pattern-id`, `--confirm`, `--json` |
| `placement-exclude-restore` | `--pattern-id`, `--json` — znovu vyloučí dříve odvyloučený web |

> **Pozor:** Nová obsahová sestava bez umístění běží po **celé** obsahové síti. Když chcete cílit na konkrétní weby, přidejte umístění **před aktivací** kampaně.
> **Quirky vyloučených umístění** (ověřeno 2026-07): (1) API ve výpisu **nevrací text vzoru** — `placements-excluded` ukáže jen ID, sestavu a datum; text vidíš ve web UI, tak si ho po `placement-exclude` poznamenej (ID se vrací). (2) Smazané vyloučení **blokuje opětovné vyloučení stejného vzoru** (`group_pattern_duplicity`) — místo nového create použij `placement-exclude-restore` se starým ID.

### Cílení obsahové sítě: zájmy / témata / úmysly

Tři dimenze cílení obsahových sestav nad rámec umístění a publik: **zájmy** (interest — dlouhodobé zájmy uživatele), **témata** (theme — tematika webů, kde se reklama zobrazí) a **úmysly** (intend — nákupní záměr). Všechny sdílejí stejné příkazy s přepínačem `--type interest/theme/intend`; váží se na **sestavu**.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `targeting-categories` | `--type`, `--json` — číselník kategorií dané dimenze |
| `targeting` | `--type`, `--group-id`, `--negative` (výpis vyloučení), `--json` |
| `targeting-add` | `--type`, `--group-id`, `--category-id`, `--cpc`/`--cpt` (CZK, volitelně), `--status`, `--json` |
| `targeting-exclude` | `--type`, `--group-id`, `--category-id`, `--json` — vyloučí kategorii |
| `targeting-remove` | `--type`, `--id`, `--negative`, `--confirm`, `--json` |
| `targeting-restore` | `--type`, `--id`, `--negative`, `--json` — obnoví smazané cílení |

> Mazání je **soft-delete**: opětovné přidání stejné kategorie po smazání vrací `409 entity_already_exists` — použij `targeting-restore` se starým ID (CLI výpisy smazané položky skrývají, ID najdeš v původním výstupu `targeting-add`/`targeting-remove`).

```bash
./run.sh targeting-categories --type theme                       # jaká témata existují
./run.sh targeting-add --type theme --group-id 123 --category-id 102   # cíl na Auto-moto
./run.sh targeting-exclude --type theme --group-id 123 --category-id 103  # vyluč Bulvár
./run.sh targeting --type theme --group-id 123                   # co je nastavené
```

### Sdílené rozpočty

Jeden denní rozpočet sdílený více kampaněmi. Přiřazení kampaní se řídí **na rozpočtu** (ne přes `campaign-update`).

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `budgets` | `--json` — výpis vč. přiřazených kampaní a čerpání |
| `budget-create` | `--name`, `--day-budget` (Kč), `--campaign-ids "1,2"`, `--json` |
| `budget-update` | `--budget-id`, `--name`, `--day-budget`, `--add-campaign-ids`, `--remove-campaign-ids`, `--remove-all-campaigns`, `--json` |
| `budget-remove` | `--budget-id`, `--confirm`, `--json` |

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
├── sklik_cli.py        # Tenký entrypoint (volá sklik.cli.main)
├── sklik/              # Balík s implementací
│   ├── api.py          #   engine: auth, session, rate-limit, _api_call, chyby
│   ├── formatting.py   #   převod CZK⇄haléře + JSON výstup
│   ├── reports.py      #   dvoukrokový report helper
│   ├── images.py       #   načítání/kódování obrázků (bannery + combined)
│   ├── cli.py          #   argparse + dispatch
│   └── commands/       #   jeden modul na doménu (ads, campaigns, keywords, …)
├── requirements.txt    # Závislosti (requests, python-dotenv)
├── setup.sh · run.sh   # Instalační / spouštěcí skript (aktivuje venv)
├── .env.example        # Šablona pro tokeny
├── CLAUDE.md           # Signpost pro Claude Code (+ dokumentační mapa)
├── docs/api-notes.md   # Hutná reference chování API Drak
├── CHANGELOG.md        # Historie verzí
├── .env                # Tokeny (NEVERZOVAT)
└── skill/              # Skill pro Claude Code (/sklik-ppc) + INSTALL.md
```

## API poznámky

- Protokol: JSON-RPC `POST` na `https://api.sklik.cz/drak/json/v5/{metoda}`. Endpoint je **připnutý na v5**, aby se CLI tiše nerozbilo při major změně API.
- Reporty jsou dvoukrokové: `createReport` (filtry + období) → `readReport` (stránkování + sloupce).
- API **nepodporuje** filtry na nadřazené entity (`campaign.ids`, `group.ids`, `status`) v `restrictionFilter` — proto se aplikují na straně klienta.
- Příklady použití API Drak: [github.com/seznam/sklik-api-examples](https://github.com/seznam/sklik-api-examples).

> Kompletní chování API (kvirky reportů, bezpečná výměna inzerátů, bannery, konverze, retargeting, rate limity, stavové kódy): **[docs/api-notes.md](docs/api-notes.md)**.

## O kurzu AI First

Tahle appka vznikla jako ukázka do **7. lekce kurzu [AI First](https://aifirst.cz)** — praktického videokurzu AI a vibe codingu pro marketéry, podnikatele a kohokoli s chutí tvořit.

Lekce ukazuje, jak vibe coding zapojit do **každodenní marketingové práce**: postavit si vlastní nástroje na míru, automatizovat rutinu, ušetřit hodiny času a zvednout efektivitu — bez programátora.

> *„Nechte AI dělat práci, kterou musíte, ať můžete dělat práci, kterou chcete."*

- 🎬 18,5 hodiny praktických videí, 10 lekcí
- 🚀 Reálná praxe — stavíš věci, které opravdu používáš (jako tenhle nástroj)
- ⏱️ Důraz na úsporu času a efektivitu v běžné práci
- 👉 **[aifirst.cz](https://aifirst.cz)**

## Licence

MIT — viz [LICENSE](LICENSE).

