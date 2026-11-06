# Sklik PPC App

CLI aplikace pro správu PPC kampaní na **Seznam Sklik** přes [API Drak](https://api.sklik.cz/drak/) (JSON, verze v5). Je pro marketéry a agentury, kteří chtějí kampaně spravovat z terminálu nebo konverzací s Claude Code místo ručního klikání ve webovém Skliku.

Pokrývá kompletní životní cyklus *search* i *obsahových* kampaní: kampaně, sestavy, klíčová slova, inzeráty, vylučující slova, výzkum klíčových slov, statistiky. K tomu měření konverzí, retargetingová publika, cílení (regiony / zařízení / rozvrh), obrázkové bannery a kombinovanou (nativní) reklamu.

Autor: [Jindřich Fáborský](https://www.faborsky.cz) · kurz [AI First](https://aifirst.cz)

> [!TIP]
> **Appka je zdarma a je tvoje.** Naklonuj si ji, používej ji, přestav si ji po svém.
>
> Nevíš, jak ji rozjet? Nebo chceš AI v marketingu používat systematicky: řídit z jednoho místa všechny kanály, automatizovat rutinu, postavit si vlastní znalostní bázi a vibe codovat si nástroje na míru své firmě? To učím v kurzu **[AI First](https://aifirst.cz)**. Tahle appka je v něm vysvětlená i s tím, jak si postavit vlastní.

Součástí repa je i [skill pro Claude Code](#skill-pro-claude-code-sklik-ppc), který appku obaluje.

## 🆕 Co je nového

Poslední verze je **1.12.0**. Celá historie: **[CHANGELOG.md](CHANGELOG.md)**.

- **1.12.0**: **opraveno `negative-remove`**, které po změně DRAKu 11.27.0 (14. 9. 2026) nefungovalo: maže se podle sestavy, textu a typu shody (`--group-id`, `--name`, `--match-type`), trvale a bez možnosti obnovy; `--keyword-id` funguje dál. **`suggest-stats`** zvládne libovolný počet dotazů (posílá je po 100), **HTTP 429 bez těla** už nekončí chybou, ale počká a zopakuje se, a **`feed-status` skrývá přístupové klíče v URL feedu** (`?hash=***`). Nové příkazy na **popisky** (`callout-*`) a `sitelink-assign` už při přiřazení sitelinků nesmaže popisky. Navíc kampaň a reklamu jde přes Fénix (specifikace 1.34.0) i upravit. **`fenix-campaign-update`** nastaví začátek a konec kampaně, frekvenční strop **na úrovni kampaně** (DRAK ho nečte ani nezapisuje), celkový rozpočet, vyloučené weby, stav a denní rozpočet. **`fenix-ad-update`** nastaví stav, začátek a konec u libovolného typu reklamy včetně **bannerů** (DRAK u nich datum nemá) a umí víc reklam jedné sestavy najednou. Oba mají `--dry-run` s ověřením na straně API. DRAKové `campaign-create` a `campaign-update` dostaly `--start-date` a `--end-date`. Výpisy `fenix-campaigns` a `fenix-ads` nově ukazují data a frekvenční strop.
- **1.11.0** (nevyšla samostatně, je součástí 1.12.0): nová skupina příkazů **`fenix-*`** nad API Fénix 1.30.0: výpis kampaní, sestav, inzerátů a hlavně **vylučujících slov na úrovni kampaně** (`fenix-negatives`), která DRAK přečíst neumí. K tomu zakládání kampaní, sestav a ETA inzerátů s **`--dry-run`** (API jen ověří, nic nezaloží) a přidání/smazání vylučujících slov. Nová kampaň se zakládá **pozastavená**. Engine Fénixu nově čeká přesně tak dlouho, jak API řekne v hlavičce `Retry-After`. **Čtecí příkazy `fenix-*` a `--dry-run` u kampaně jsou ověřené na živém účtu, ostré zápisy zatím jen proti specifikaci** (podrobně níže). Volitelně jde tokeny držet ve správci hesel místo v `.env` (skript `run-op.sh` pro 1Password); přihlášení tokenem v `.env` se nemění.
- **1.10.1**: oprava jednotek u `nakupy-campaigns`. Denní rozpočet se tiskl 100× vyšší (250 Kč jako 25 000 Kč) a modifikátory nabídek obráceně. `maxCpcMultiplier` navzdory jménu není násobič se základnou 100 %, ale znaménkové procento se stejnou konvencí jako DRAK (`0` = beze změny, `-100` = vypnuto). Specifikace Fénixu tvrdí u obou polí něco jiného než živý účet; díky za ověření patří opět uživateli ArkAngelMichael.
- **1.10.0**: nová skupina příkazů **Nákupy / feed (API Fénix)**: `feed-status`, `feed-diagnostics`, `nakupy-campaigns`, `nakupy-stats`, `shop-items`. U nákupních kampaní (Seznam Nákupy, dřív Zboží.cz) vidí DRAK jen agregát na kampani a sestavě. Feed, jednotlivé produkty ani rozpad výkonu podle umístění (Seznam × Zboží, typ aukce, zařízení) neukáže vůbec. To teď doplňuje API Fénix; potřebuje vlastní token v `.env`. **Za nápad i za první implementaci děkuji uživateli ArkAngelMichael.**
- **1.9.0**: výpisy vrací kompletní data. `campaigns` bralo z API jen prvních 100 kampaní (a `--status` filtroval až nad touhle useknutou stovkou), `groups`/`ads`/`banners` 500 řádků. Větší účet tak tiše přišel o zbytek a nikde to nebylo vidět. Nově se všechny výpisy i reporty stránkují až do konce. Díky za nahlášení patří studentovi kurzu AI First.
- **1.8.1**: opraveno cílení kampaní. `--regions` posílalo do API holá čísla místo structů (každý pokus o geo cílení končil chybou `regions[0] must be struct, not int`), `--device-bids` posílalo desetinná čísla místo celých (`must be int, not double`) a `--schedule-json` byl v dokumentaci v tvaru, který API odmítá. Díky za nahlášení patří studentovi kurzu AI First.
- **1.8.0**: statistiky umí **`winRate`** (podíl vyhraných aukcí, jen u sestav) a **`--granularity daily`** pro denní řady; přibyly sloupce `exhaustedBudgetShare`, `impressionMoney`/`clickMoney`, `avgCpt`, a `campaigns` teď ukazuje i rotaci reklam (`adSelection`). **Opraveno: CTR se v lidském výstupu tisklo 100× menší** (`0.01%` místo `0.73%`); `--json` se nemění.
- **1.7.2**: oprava jednotek `conversionValue` (100× podhodnocená hodnota konverzí).

> 💡 Chceš dostávat upozornění na nové verze? Na GitHubu: **Watch → Custom → Releases**.

## Dva způsoby, jak appku používat

**A) Orchestrace přes Claude Code (výchozí a nejjednodušší).** Appku řídí Claude Code (nebo jiný coding agent) přes přibalený skill: ty zadáváš cíle česky, agent volá CLI, drží bezpečnostní pravidla (schválení před zápisem, `--confirm` u mazání, atomická výměna inzerátů) a hlídá API limity. Nejrychlejší start: otevři Claude Code a vlož mu prompt typu:

> *Naklonuj https://github.com/faborsky/sklik-ppc-app, spusť `./setup.sh`, nainstaluj mi přibalený skill podle `skill/INSTALL.md` a pak mi řekni, kam mám vložit svůj Sklik API token.*

Claude vše připraví; **token pak vlož ručně do `.env`** (soubor je v `.gitignore`, token nikdy neposílej do chatu ani nikam do kódu). Odteď stačí `/sklik-ppc` z libovolného projektu. Detaily instalace skillu: [skill/INSTALL.md](skill/INSTALL.md).

**B) Vlastní automatizace a agentní řešení (pro pokročilé).** Appka je normální CLI stavěné na strojové řízení: `--json` výstupy, chyby jako `{"error": …}` na stdout, request-budget vestavěný (neuřídíš API limity omylem). Vezmi si ji do vlastních skriptů, cronů nebo agentních workflow. Kompletní referenci příkazů máš níže v tomhle README a chování API (quirky, limity, status kódy) v [docs/api-notes.md](docs/api-notes.md).

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
2. Najdi sekci **„Přístup k API Drak“**.
3. Vygeneruj / zkopíruj svůj **API token**.
4. Token vlož do souboru `.env` jako `SKLIK_API_TOKEN` (viz [Konfigurace](#konfigurace) níže).

> Token je heslo k tvému Sklik účtu přes API. Nikam ho nedávej do kódu ani do gitu, patří **výhradně** do `.env` (které je v `.gitignore`), případně do správce hesel (viz [Tokeny ve správci hesel](#tokeny-ve-správci-hesel-volitelné)).

### Konfigurace

Tokeny patří do `.env` (soubor je v `.gitignore`, nikdy se necommituje):

```bash
SKLIK_API_TOKEN=tvuj-token            # výchozí účet (--account vynechán)
SKLIK_API_TOKEN_CLIENTB=tvuj-token    # volitelný další login → --account clientb
```

Účty se zjistí z prostředí za běhu. Žádná jména nejsou natvrdo v kódu, takže můžeš mít libovolný počet loginů. Session se po přihlášení cachuje 25 minut do `.session_cache_<account>.json` (taky gitignored) a automaticky se obnoví při vypršení (401).

### Tokeny ve správci hesel (volitelné)

**Nic z toho dělat nemusíš.** Token v `.env` a `./run.sh` fungují dál úplně stejně. Tohle je doplněk pro případ, že dlouhodobý token nechceš mít na disku jako čistý text, třeba když máš složku s appkou v synchronizovaném úložišti nebo v zálohách.

Princip je obecný: appka čte tokeny z proměnných prostředí a `.env` je jen jeden ze způsobů, jak je tam dostat. Knihovna `python-dotenv` navíc **nepřepisuje proměnné, které už v prostředí jsou**. Funguje tedy cokoli, co umí spustit příkaz s doplněnými proměnnými: `op run` u 1Passwordu, obdobné příkazy jiných správců hesel, nebo jeden řádek v shellu. Stačí, aby při spuštění `./run.sh` existovaly `SKLIK_API_TOKEN` a případně `SKLIK_FENIX_REFRESH_TOKEN`. Příklad s Klíčenkou na macOS:

```bash
SKLIK_API_TOKEN="$(security find-generic-password -s sklik-api -w)" ./run.sh account
```

Pro **1Password CLI** je v repu hotový skript `run-op.sh`:

1. Nainstaluj si [1Password CLI](https://developer.1password.com/docs/cli/get-started/) (`op`) a přihlas ho. Nejpohodlnější je propojení s aplikací 1Password, pak se odemyká otiskem.
2. Token ulož do 1Passwordu a do `.env` napiš místo hodnoty odkaz na něj:

   ```bash
   SKLIK_API_TOKEN=op://<trezor>/<položka>/<pole>
   SKLIK_FENIX_REFRESH_TOKEN=op://<trezor>/<položka>/<pole>
   ```

3. Místo `./run.sh` spouštěj `./run-op.sh`, přepínače zůstávají stejné:

   ```bash
   ./run-op.sh account
   ./run-op.sh campaigns --json
   ```

`run-op.sh` jen zavolá `op run --env-file=.env -- ./run.sh …`. `op` si vyžádá odemčení (otisk nebo heslo) a dosadí skutečné hodnoty do prostředí toho jednoho procesu. Na disk se nezapíšou. Když omylem spustíš obyčejné `./run.sh`, appka pozná nevyřešený odkaz `op://…`, nic nikam nepošle a napíše ti, ať použiješ `./run-op.sh`.

**Co tím získáš a co ne:**

- Dlouhodobý token už neleží v čistém textu na disku, takže ani v cloudové synchronizaci a zálohách. Každé použití navíc musíš odemknout.
- Krátkodobé přihlášení se na disk ukládá dál: session DRAKu (25 minut) do `.session_cache_<account>.json` a access token Fénixu (1 hodina) do `.fenix_cache_<account>.json`. Kdo se k těm souborům dostane, může do vypršení jednat za tebe. Oba soubory jsou v `.gitignore`.
- Proti škodlivému programu, který běží pod tvým účtem ve chvíli, kdy máš 1Password odemčený, to neochrání.

**Na čem se dá zaseknout:**

- Máš v 1Passwordu přihlášených víc účtů? Řekni `op`, který má použít: `OP_ACCOUNT=my.1password.com ./run-op.sh account` (adresa účtu, jak ji vypíše `op account list`). Skript žádný účet sám nevybírá.
- Jedno spuštění `op run` řeší odkazy jen v rámci jednoho účtu. Všechny tokeny z `.env` proto musí být v tomtéž účtu 1Passwordu.
- Název pole závisí na typu položky: u typu *API Credential* je to `credential`, u *Secure Note* `notesPlain`.
- Když nepotvrdíš výzvu k odemčení včas, skončí příkaz chybou `authorization timeout`. Stačí ho pustit znovu.

### Účty vs. spravované účty

Dva nezávislé globální přepínače (uvádějí se **před** názvem příkazu):

- **`--account <name>`**: který *login / token* se použije. Bez přepínače = `default` (`SKLIK_API_TOKEN`); `--account <name>` čte `SKLIK_API_TOKEN_<NAME>`.
- **`--user-id <id>`**: *spravovaný účet* pod aktivním loginem (agentura → klientský účet).

```bash
python sklik_cli.py account                          # výchozí login
python sklik_cli.py --account clientb account         # jiný login
python sklik_cli.py --user-id 123456 campaigns        # spravovaný účet pod aktivním loginem
```

> `suggest` a `suggest-stats` přepínač `--user-id` tiše ignorují (API metody parametr spravovaného účtu nemají), volej je bez něj. `--account` funguje normálně.

## Použití

Příkazy se spouští přes `run.sh` (sám aktivuje venv):

```bash
./run.sh <příkaz> [přepínače]
# ekvivalent: source venv/bin/activate && python sklik_cli.py <příkaz> [přepínače]
```

**Konvence napříč CLI:**

- **Ceny v CZK**: CLI přijímá i zobrazuje koruny; na haléře (×100) převádí samo.
- **`--json`**: strojově čitelný výstup (použij při parsování).
- **`--confirm`**: povinný u všech mazacích operací (`*-remove`).
- Filtry `--campaign-id` / `--group-id` / `--status` se aplikují na straně klienta (API je v restriction nepodporuje).
- Výchozí rozsah statistik je posledních 30 dní.

### Účet

| Příkaz | Popis |
|--------|-------|
| `account` | Info o účtu, zůstatek peněženky, spravované účty |
| `api-limits` | Reálné API limity účtu (rate/batch/hodnotové rozsahy) + živé lokální využití request-budgetu; `--json` |
| `credit` | Zůstatek kreditu peněženky v Kč (bez DPH i s DPH), i pro spravované účty; `--json` |
| `regions` | Číselník ID regionů pro `--regions` cílení; `--json` |
| `autotagging` | Aktuální konfigurace autotaggingu (UTM parametry); `--json` |
| `autotagging-update` | `--enabled on/off`, `--config-json` (částečná konfigurace, mergne se přes současnou); `--json` |

```bash
./run.sh api-limits            # limity + kolik requestů jsi spotřeboval (60 s / 24 h)
./run.sh api-limits --json     # strukturovaný výstup
```

> **Ochrana účtu před zablokováním.** Appka počítá každé volání do per-account souboru `.rate_limit_<account>.json` (přežívá napříč session i paralelními běhy) a kontroluje ho *před* každým requestem: na 90 % minutového limitu počká, na denním limitu operaci odmítne. Limity bere z `api.limits` (cache ~1×/den). Counter neřešíš ručně, appka to hlídá za tebe.

### Pulse

Souhrn celého účtu **jedním voláním**, místo řetězení `account` + `campaigns` + `campaign-stats`. Vrátí totály, statistiky po kampaních, delty vůči předchozímu stejně dlouhému období a top movery, předpočítané do kompaktního digestu. Hodí se na levný a rychlý analytický pull.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `pulse` | `--days N` (default 7), `--date-from`/`--date-to` (přebijí `--days`), `--no-compare` (vynechá delty, o 1 API volání míň), `--json` |

```bash
./run.sh pulse                 # posledních 7 dní vs předchozích 7
./run.sh pulse --days 30       # posledních 30 dní vs předchozích 30
./run.sh pulse --no-compare    # bez srovnání s předchozím obdobím
./run.sh pulse --json          # strukturovaný výstup pro další zpracování
```

> `pulse` si přes `stats.status` ověří, že statistiky za celé okno jsou už kompletní. Když ne (typicky dnešek je „preparing“), přidá varování (`statsWarning` v `--json`), že čísla a delty jsou zatím z částečných dat.

### Kampaně

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `campaigns` | `--status active/suspend`, `--json` |
| `campaign-create` | `--name`, `--day-budget` (CZK), `--type fulltext/context/product`, `--status active/suspend`, `--regions`, `--device-bids`, `--ad-selection`, `--start-date`, `--end-date` (`YYYY-MM-DD`), `--json` |
| `campaign-update` | `--campaign-id`, `--name`, `--day-budget`, `--status`, `--regions`, `--device-bids`, `--schedule-json`, `--ad-selection`, `--start-date`, `--end-date` (`YYYY-MM-DD`, `none` datum smaže), `--json`. Frekvenční strop kampaně DRAK nemá, nastavuje ho `fenix-campaign-update` |
| `campaign-remove` | `--campaign-id`, `--confirm`, `--json` |
| `campaign-stats` | `--campaign-id`, `--date-from`, `--date-to`, `--granularity {total,daily,weekly,monthly,quarterly,yearly}`, `--json` |
| `campaign-targeting` | `--campaign-id`, `--json`. Přehled geo / zařízení / rozvrhu |
| `campaign-restore` | `--campaign-id`, `--json`. Obnoví smazanou kampaň (undelete) |

**Cílení** (`campaign-create` / `campaign-update`):

- `--regions`: ID regionů oddělená čárkou (číselník: příkaz `regions`). Nastavení **nahrazuje celou sadu** regionů. Geo cílení **nejde přes API zrušit**, API odmítá prázdné pole i `nil`. Smazat ho jde jen ve webovém rozhraní Skliku.
- `--device-bids`: modifikátory v % jako `desktop:mobile:tablet:other`, např. `0:-30:-30:-100`. Musí to být **celá procenta** (API odmítá desetinná čísla).
- `--schedule-json` (jen update): **7 polí po 24 hodinových hodnotách 0–100**, týden začíná pondělím: `'[[0,0,…,100,100,…], …×7]'`. Hodnota `null` rozvrh smaže. (CLI přijme a převede i starší tvar `{"daySchedule":[{"value":[…]}, …]}`, v jakém API rozvrh *vrací*.)
- `--ad-selection`, rotace inzerátů (`adSelection`): `weighted` (preferuj vyšší CTR, výchozí), `random` (rovnoměrně, čistý A/B test kreativ), `cpa` (nižší CPA), `cos` (nižší CTR)

### Sestavy (ad groups)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `groups` | `--campaign-id`, `--json`. Výpis vrací i `maxUserDailyImpressions` (frekvenční strop sestavy) |
| `group-create` | `--campaign-id`, `--name`, `--cpc` (CZK), `--max-daily-impression`, `--json` |
| `group-update` | `--group-id`, `--name`, `--cpc`, `--status`, `--max-daily-impression`, `--json` |
| `group-remove` | `--group-id`, `--confirm`, `--json` |
| `group-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--granularity …`, `--json`. Jako jediná entita vrací i **`winRate`** (podíl vyhraných aukcí) |
| `group-restore` | `--group-id`, `--json`. Obnoví smazanou sestavu (undelete) |

> `--max-daily-impression N` = frekvenční limit (max. zobrazení na uživatele za den), v Skliku pole `maxUserDailyImpression`.

### Klíčová slova

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `keywords` | `--group-id`, `--campaign-id`, `--json` |
| `keyword-create` | `--group-id`, `--name`, `--match-type broad/phrase/exact`, `--cpc` (CZK), `--url`, `--json` |
| `keyword-create-batch` | `--group-id`, `--keywords-json`, `--json` |
| `keyword-update` | `--keyword-id`, `--cpc`, `--status`, `--url`, `--json` |
| `keyword-remove` | `--keyword-id`, `--confirm`, `--json` |
| `keyword-stats` | `--group-id`, `--campaign-id`, `--date-from`, `--date-to`, `--granularity …`, `--json` |
| `keyword-restore` | `--keyword-id`, `--json`. Obnoví smazané slovo (undelete) |
| `keyword-set` | `--group-id`, `--keywords-json`, `--remove-others`, `--json`. Deklarativní nastavení slov sestavy |

> `name` ani `matchType` klíčového slova nelze měnit, slovo je nutné smazat a vytvořit znovu.
> `keyword-set` je **upsert**: chybějící slova přidá, existujícím upraví CPC/URL, dříve smazaná obnoví. S `--remove-others` navíc smaže všechna slova, která v payloadu nejsou: plná synchronizace sestavy podle seznamu.

### Inzeráty (ETA)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `ads` | `--group-id`, `--campaign-id`, `--json` |
| `ad-create` | `--group-id`, `--headline1/2/3`, `--description1/2` (alias `--description`), `--final-url`, `--path1/2`, `--json` |
| `ad-update` | `--ad-id`, `--status`, `--json` (jen stav, na místě) |
| `ad-replace` | `--ad-id`, `--headline1/2/3`, `--description/--description2`, `--final-url`, `--path1/2`, `--json` |
| `ad-remove` | `--ad-id`, `--confirm`, `--json` |
| `ad-stats` | `--group-id`, `--date-from`, `--date-to`, `--granularity …`, `--json` |
| `ad-restore` | `--ad-id`, `--json`. Obnoví smazaný inzerát (undelete) |

> **Změna textu inzerátu = `ad-replace`, NIKDY ruční `ad-remove` + `ad-create`.** Sklik neumí text upravit na místě: jakákoli změna kreativy udělá přes `ads.update` **atomickou výměnu na serveru** (smaže starý + vytvoří nový v JEDNÉ operaci, vrátí `newAdIds`). Když nový inzerát neprojde validací (typicky `ad_duplicate_in_db`), **původní zůstane nedotčený**. Ruční remove+create tuhle jistotu nemá. Když selže create po removu, sestava tiše ztratí inzerát (reálně se to stalo). `ad-replace` načte stávající inzerát, aplikuje jen zadaná pole (zbytek zachová), předvaliduje přes `ads.check` a pak provede atomickou výměnu. Jen textové (eta) inzeráty.

### Kombinovaná (nativní) reklama

Formát pro obsahovou síť, kterým se zobrazuje i **nativní reklama v článcích** na webech Seznamu. Sklik z dodaných textů a obrázků automaticky skládá výslednou podobu (nativní pozice v článku, responzivní sloty, branding). Konkrétní umístění nevybíráš.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `combined-create` | `--group-id`, `--short-line` (max 25 zn.), `--long-line` (max 90), `--description` (max 90), `--company-name` (max 25), `--final-url`, `--image-landscape` (1,91:1, min 600×314 px), `--image-square` (1:1, min 300×300 px), `--image-logo`, `--image-landscape-logo`, `--color-main/--color-accent` (hex), `--mobile-final-url`, `--tracking-template`, `--status`, `--json` |

Výpis přes `ads` (`adType: combined`), statistiky přes `ad-stats`, smazání přes `ad-remove`. Obrázky: lokální cesta nebo URL (jpg/png/gif, max 1 MB), CLI je zakóduje samo.

> **Pozor:** Sklik z textů **tiše odstraňuje zakázané znaky** (třeba dlouhou pomlčku z titulku), bez chyby i bez warningu. Po vytvoření si finální znění ověř přes `ads --group-id X --json`. Kombinovanou reklamu nelze upravit na místě (`ad-replace` je jen pro textové inzeráty kvůli obrázkům): **vytvoř nový inzerát, ověř, a teprve pak smaž starý** (create-first, aby selhaný create nikdy nesmazal poslední inzerát).

### Vylučující klíčová slova

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `negatives` | `--group-id`, `--campaign-id`, `--json` |
| `negative-add` | `--group-id`/`--campaign-id`, `--name`, `--match-type negativeBroad/negativePhrase/negativeExact`, `--json` |
| `negative-add-batch` | `--group-id`/`--campaign-id`, `--keywords-json`, `--json` |
| `negative-remove` | `--group-id` + `--name` + `--match-type` (výchozí `negativeBroad`), **nebo** `--keyword-id`; `--confirm`, `--json`. Maže **trvale**, obnovit nejde |

> `negatives` umí vypsat jen **skupinové** vylučovačky (`--campaign-id` filtruje přes sestavy dané kampaně). Kampaňové vylučovačky (`negative-add --campaign-id`) jsou v API **write-only**: zapsat jdou, ale zpětně vypsat ne. Přečíst a smazat je jde přes `fenix-negatives` / `fenix-negative-remove --campaign-id` (API Fénix), jinak jen ve webovém rozhraní Skliku.
>
> **`negative-remove` maže podle textu a typu shody v sestavě** (od DRAKu 11.27.0, 14. 9. 2026 metoda ID nebere). Se `--keyword-id` si CLI záznam nejdřív dohledá. `negatives` vypisuje typ shody krátce (`broad`/`phrase`/`exact`), `--match-type` bere oba tvary. `negative-add` od téže změny API nevrací ID, hlásí se počet přidaných slov.

### Výzkum klíčových slov

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `suggest` | `--query`, `--limit`, `--related`, `--order-by avgSearchCount/cpc/score`, `--json` |
| `suggest-stats` | `--queries` (oddělené čárkou; API bere max. 100 na volání, CLI delší seznam samo rozdělí), `--granularity monthly/daily`, `--json` |

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
| `sitelinks-assigned` | `--campaign-id` **nebo** `--group-id`, `--json`. Co je aktuálně přiřazené |

> **`sitelink-assign` NAHRAZUJE celou sadu** přiřazených sitelinků kampaně/sestavy, vždy pošli kompletní seznam, ne jen přírůstek. Přiřazené popisky ponechá (od 1.12.0, dřív je smazal). **Přejmenování sitelinku (`sitelink-update --name`) vytvoří NOVÉ ID** (server dělá remove+create), CLI nové ID vypíše; změna `--url` ID zachová.

### Popisky

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `callouts` | `--json` |
| `callout-create` | `--name`, `--json` |
| `callout-remove` | `--callout-id`, `--confirm`, `--json` |
| `callout-assign` | `--campaign-id` **nebo** `--group-id`, `--callout-ids "1,2,3"` (`""` = odpojit všechny popisky), `--dry-run`, `--json` |
| `callouts-assigned` | `--campaign-id` **nebo** `--group-id`, `--json`. Co je aktuálně přiřazené |

> **Popisek je v API sitelink bez URL**, vlastní metody nemá. CLI je přesto drží odděleně: `callout-*` pracují jen se záznamy bez URL a na sitelinky nesáhnou. **`callout-assign` nahradí popisky kampaně/sestavy a přiřazené sitelinky ponechá** (`--dry-run` ukáže výslednou sadu bez zápisu). Opačný směr funguje stejně: **`sitelink-assign` nahradí sitelinky a popisky ponechá.** `sitelink-update` popisek odmítne (URL by z něj udělala sitelink), text popisku se mění přes `callout-remove` a `callout-create`. Výpis `sitelinks` ukazuje obojí, popisky mají prázdné URL.

### Konverze (definice měření)

Konverze = pojmenovaná definice cílové akce (nákup, registrace…) a její hodnoty. CLI spravuje *definice*; samotné měření (pixel / SEM) žije na webu.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `conversions` | `--json` |
| `conversion-types` | `--json`. ID typů použitých na účtu (viz poznámka níže) |
| `conversion-create` | `--name`, `--type-id`, `--value` (CZK), `--color`, `--json` |
| `conversion-update` | `--conversion-id`, `--name`, `--value`, `--color`, `--json` |
| `conversion-remove` | `--conversion-id`, `--confirm`, `--json` |

> **Pozn.:** Účty se zapnutým **SEM** (Seznam Event Measurement) `conversions.*` metody používat nemohou, CLI v takovém případě vypíše srozumitelnou hlášku. Metoda `listConversionTypes` je na straně Sklika nefunkční (HTTP 500), proto `conversion-types` odvozuje typy z existujících konverzí. SEM konverze spravují příkazy [`sem-*`](#sem--měření-událostí-api-fénix) níže.

### SEM — měření událostí (API Fénix)

Účty se zapnutým **SEM** (Seznam Event Measurement) nemohou přes DRAK používat konverze (`conversions.*`). Tyhle příkazy proto jdou přes **API Fénix**. Konverze v SEM stojí na události (`Purchase`, `AddToCart`, `InitiateCheckout`, `Lead`…) a může mít podmínky na její rozměry: hodnotu, URL, kategorii, ID produktu… **Založením konverze vznikne i retargetingový seznam**. Tak se dělají publika typu „nákup nad 1 500 Kč“, která běžné URL seznamy z DRAKu neumí.

**Přihlášení:** stejný Fénix refresh token jako u [Nákupů](#nákupy--feed-api-fénix) (`SKLIK_FENIX_REFRESH_TOKEN` / `SKLIK_FENIX_REFRESH_TOKEN_<NAME>`), pro zápis s právem `rw`. `premiseId` nepotřebuje. Spravované účty se otevírají přes `--user-id` stejně jako jinde.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `sem-status` | `--json`. Je SEM aktivní a od kdy |
| `sem-conversions` | `--include-deleted`, `--json`. Konverze s událostí a podmínkami |
| `sem-conversion-create` | `--name`, `--event` (Purchase, AddToCart, InitiateCheckout…), `--value` (Kč, výchozí 0), `--description`, `--condition KLÍČ:TYP:HODNOTA` (opakovatelné), `--conditions-json`, `--dry-run`, `--json` |
| `sem-conversion-update` | `--conversion-id`, `--name`, `--description`, `--value`, `--condition` (nahradí podmínky), `--conditions-json`, `--dry-run`, `--json` |
| `sem-conversion-remove` | `--conversion-id`, `--confirm` (nebo `--restore`), `--json` |

`--dry-run` u `sem-conversion-create` a `sem-conversion-update` pošle `dryRun=true`: API požadavek zkontroluje a nic neuloží. Příklad, publikum high-value zákazníků:

```bash
./run.sh --user-id <ID účtu> sem-conversion-create --name "Nákup nad 1 500 Kč (vedlejší)" \
  --event Purchase --value 0 --condition value:greater_than:1500 --dry-run
```

> **Pozor na dvojí počítání:** podmíněná konverze na události, kterou už měří jiná konverze (např. high-value `Purchase` vedle hlavní „Objednávky“), započítá stejnou objednávku v reportu konverzí dvakrát. Proto ji pojmenuj „(vedlejší)“, dej hodnotu 0 a nikdy ji nepoužívej jako cíl automatické strategie. Hodnota v podmínce `value` se zadává v Kč (API ji chce v haléřích, appka převádí). Víc `--condition` jde do jedné skupiny; jestli se v ní kombinují jako A, nebo NEBO, dokumentace API neuvádí, takže u víc podmínek ověř velikost výsledného publika.

### Retargeting (publika)

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `retargeting` | `--json` |
| `retargeting-create` | `--name`, `--membership` (dny), `--description`, `--use-historic`, `--take-all-users`, `--conditions-json` (tvar: `[{"conditions":[{"type":"contains","value":"/dekujeme"}]}]`), `--json` |
| `retargeting-update` | `--list-id`, `--name`, `--membership`, `--description`, `--json` |
| `retargeting-remove` | `--list-id`, `--confirm`, `--json` |
| `retargeting-attach` | `--list-id`, `--group-id`, `--json`. Napojí publikum na sestavu jako cílení |
| `retargeting-detach` | `--list-id`, `--group-id`, `--confirm`, `--json` |
| `retargeting-attached` | `--group-id` (bez něj všechny sestavy), `--json`. Co je kde napojené |
| `retargeting-exclude` | `--list-id`, `--campaign-id` **nebo** `--group-id`, `--json`. Vyloučí publikum (negativní retargeting) |
| `retargeting-exclude-remove` | `--list-id`, `--campaign-id`/`--group-id`, `--confirm`, `--json` |
| `retargeting-excluded` | `--campaign-id`/`--group-id` (bez nich vše na obou úrovních), `--json` |

> Publikum jde napojit jen na sestavy **obsahových** kampaní. Pokus o napojení **smazaného** seznamu vrací `406 Bad values` bez bližší diagnostiky, zkontroluj `deleted` ve výpisu `retargeting --json`.
> **Vyloučení publika** (`retargeting-exclude`) funguje na úrovni kampaně i sestavy, typicky „vyluč stávající zákazníky z akviziční kampaně“. Na rozdíl od napojení funguje i na search kampaních.

### Obrázkové bannery

Statické bannery (jpg/png/gif) pro obsahovou síť. Pro HTML5 bannery použij jiný nástroj, tady jde o statické formáty.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `banner-formats` | `--json`. Povolené rozměry a limity velikosti |
| `banners` | `--group-id`, `--json` |
| `banner-create` | `--group-id`, `--name`, `--clickthru-url`, `--image` (lokální cesta **nebo** http URL), `--status`, `--json` |
| `banner-download` | `--group-id`, `--out` (složka), `--json`. Stáhne obrázky bannerů sestavy na disk |
| `banner-update` | `--banner-id`, `--name`, `--clickthru-url`, `--status`, `--json` (beze změny obrázku) |
| `banner-remove` | `--banner-id`, `--confirm`, `--json` |
| `banner-restore` | `--banner-id`, `--json`. Obnoví smazaný banner (undelete) |

> `--image` přijme lokální soubor i veřejnou URL, CLI obrázek načte a pošle do Skliku zakódovaný (base64). Drž se povolených formátů z `banner-formats` (pevné rozměry, ≤ 250 KB).
> `banner-download` čte `image.url` (staré pole `imageURL` je deprecated) a uloží kreativy lokálně, což se hodí pro verzování kreativ do repa před výměnou. Výměna banneru = **vytvoř nový a teprve pak smaž starý** (create-first).

### Umístění (cílení na konkrétní weby)

Cílení obsahových sestav na konkrétní weby (v Skliku „umístění“). Vzor je doména nebo cesta: `"mediar.cz"`, `"www.e15.cz/byznys"`.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `placements` | `--group-id`, `--json` |
| `placement-create` | `--group-id`, `--pattern "forbes.cz"`, `--cpc` (CZK, volitelně přebije CPC sestavy), `--status`, `--json` |
| `placement-remove` | `--pattern-id`, `--confirm`, `--json` |
| `placements-excluded` | `--group-id`, `--json`. Výpis vyloučených webů |
| `placement-exclude` | `--group-id`, `--pattern "spamweb.cz"`, `--json`. Vyloučí web ze sestavy |
| `placement-exclude-remove` | `--pattern-id`, `--confirm`, `--json` |
| `placement-exclude-restore` | `--pattern-id`, `--json`. Znovu vyloučí dříve odvyloučený web |

> **Pozor:** Nová obsahová sestava bez umístění běží po **celé** obsahové síti. Když chceš cílit na konkrétní weby, přidej umístění **před aktivací** kampaně.
> **Quirky vyloučených umístění** (ověřeno 2026-07): (1) API ve výpisu **nevrací text vzoru**, `placements-excluded` ukáže jen ID, sestavu a datum; text vidíš ve web UI, tak si ho po `placement-exclude` poznamenej (ID se vrací). (2) Smazané vyloučení **blokuje opětovné vyloučení stejného vzoru** (`group_pattern_duplicity`), místo nového create použij `placement-exclude-restore` se starým ID.

### Cílení obsahové sítě: zájmy / témata / úmysly

Tři dimenze cílení obsahových sestav nad rámec umístění a publik: **zájmy** (interest, dlouhodobé zájmy uživatele), **témata** (theme, tematika webů, kde se reklama zobrazí) a **úmysly** (intend, nákupní záměr). Všechny sdílejí stejné příkazy s přepínačem `--type interest/theme/intend`; váží se na **sestavu**.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `targeting-categories` | `--type`, `--json`. Číselník kategorií dané dimenze |
| `targeting` | `--type`, `--group-id`, `--negative` (výpis vyloučení), `--json` |
| `targeting-add` | `--type`, `--group-id`, `--category-id`, `--cpc`/`--cpt` (CZK, volitelně), `--status`, `--json` |
| `targeting-exclude` | `--type`, `--group-id`, `--category-id`, `--json`. Vyloučí kategorii |
| `targeting-remove` | `--type`, `--id`, `--negative`, `--confirm`, `--json` |
| `targeting-restore` | `--type`, `--id`, `--negative`, `--json`. Obnoví smazané cílení |

> Mazání je **soft-delete**: opětovné přidání stejné kategorie po smazání vrací `409 entity_already_exists`, použij `targeting-restore` se starým ID (CLI výpisy smazané položky skrývají, ID najdeš v původním výstupu `targeting-add`/`targeting-remove`).

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
| `budgets` | `--json`. Výpis vč. přiřazených kampaní a čerpání |
| `budget-create` | `--name`, `--day-budget` (Kč), `--campaign-ids "1,2"`, `--json` |
| `budget-update` | `--budget-id`, `--name`, `--day-budget`, `--add-campaign-ids`, `--remove-campaign-ids`, `--remove-all-campaigns`, `--json` |
| `budget-remove` | `--budget-id`, `--confirm`, `--json` |

### Nákupy / feed (API Fénix)

Seznam Nákupy (dřív Zboží.cz): feed, diagnostika položek, modifikátory nabídek a statistiky rozpadlé podle umístění. Jede přes **API Fénix** (`api.sklik.cz/v1`), což je jiné rozhraní a **jiný token** než zbytek CLI:

- Vygeneruj si **Fénix refresh token** ve webovém rozhraní Skliku a vlož ho do `.env` jako `SKLIK_FENIX_REFRESH_TOKEN` (pro pojmenovaný účet `SKLIK_FENIX_REFRESH_TOKEN_<NAME>`). Token z DRAKu tu nefunguje.
- Každé volání potřebuje `premiseId`, tedy ID **provozovny/obchodu**, ne kampaně: z `--premise-id`, nebo z `SKLIK_FENIX_PREMISE` v `.env`.
- Přístupový token (platnost 1 h) se cachuje v `.fenix_cache_<account>.json`. `--user-id` funguje i tady (Fénix bere spravovaný účet už při vydání tokenu).

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `feed-status` | `--premise-id`, `--json`. ID a URL feedu, poslední úspěšný import, limit stahování za den. Přístupové klíče v URL (`hash`, `token`, `key`, `password`…) jsou skryté jako `***`, i v `--json` |
| `feed-diagnostics` | `--premise-id`, `--json`. Zdraví nabídek: OK / chyba / neviditelné / „lze vylepšit“ / bez kategorie |
| `nakupy-campaigns` | `--premise-id`, `--json`. Nákupní kampaně + modifikátory nabídek (web / zařízení / typ aukce) |
| `nakupy-stats` | `--date-from`, `--date-to`, `--split "webType,deviceType,productType,conversionId"`, `--by-category`, `--granularity`, `--premise-id`, `--json` |
| `shop-items` | `--premise-id`, `--all`, `--limit`, `--unpaired`/`--paired`, `--item-id "A,B"`, `--product-detail` (pozice v aukci + potřebná CPC), `--search-info`, `--json` |

**Dvě konvence se tu liší od zbytku appky:**

- **Statistiky a ceny u položek feedu jsou v korunách, ne v haléřích.** Výjimka je denní rozpočet kampaně: `budget.dayBudget` i `exhaustedDayBudget` jsou v haléřích (endpoint nákupních kampaní vrací hodnoty rovnou z DRAKu). V lidském výstupu se převádí, `--json` vrací syrová data z Fénixu.
- **Modifikátor nabídky je znaménkové procento, stejně jako v DRAKu: 0 = beze změny, `+20` = +20 %, `-100` = umístění vypnuté.** Hodnota se dá z `nakupy-campaigns` přepsat do `campaign-update --device-bids` bez přepočtu. Umístění, u kterého modifikátor nastavený není, se ve výpisu vůbec neobjeví. Modifikátory podle **webu a typu aukce jde přes API jen číst**, měnit se dají výhradně ve webovém Skliku; podle **zařízení** je zapisuje DRAK.

### Kampaně přes API Fénix (`fenix-*`)

Druhá cesta ke kampaním, vedle DRAKu. Používá **stejný Fénix token** jako příkazy pro Nákupy, ale `premiseId` nepotřebuje. DRAK zůstává výchozí: Fénix neumí klíčová slova, návrhy klíčových slov ani report vyhledávacích dotazů. Přináší dvě věci, které DRAK nemá:

- **`fenix-negatives --campaign-id X` vypíše vylučující slova na úrovni kampaně.** DRAK je umí jen zapsat.
- **`--dry-run` u zakládání** pošle požadavek s `dryRun=true`: API ho zkontroluje a nic neuloží.

> ⚠️ **Čtení je ověřené na živém účtu, zápisy zatím ne.** Příkazy jsou napsané podle OpenAPI specifikace Fénixu 1.30.0. Na živém účtu (2. 10. 2026) prošly `fenix-me`, `fenix-credit`, `fenix-accounts`, `fenix-campaigns`, `fenix-groups`, `fenix-negatives --campaign-id` a `fenix-campaign-create --dry-run` (platný požadavek API přijme a nic nezaloží, neplatný odmítne s názvem pole). **Naostro zatím nikdo nespustil** žádné zakládání bez `--dry-run`, `--dry-run` u sestavy a inzerátu, `fenix-negative-add`, `fenix-negative-remove` ani `fenix-ads`. U Nákupů se specifikace ve dvou polích spletla (viz verze 1.10.1), takže první zápis ber jako test: začni `fenix-me`, pak `--dry-run`.

Token potřebuje úroveň přístupu **`rw`** pro zápis (volí se při generování refresh tokenu ve Skliku); na výpisy stačí `r`. Co token smí, ukáže `fenix-me`.

| Příkaz | Klíčové přepínače |
|--------|-------------------|
| `fenix-me` | `--json`. Za koho token jedná a jaká má oprávnění (scopes) |
| `fenix-credit` | `--json`. Kredit účtu v Kč; u klienta agentury limit od agentury |
| `fenix-accounts` | `--json`. Účty dostupné tokenu (ID pro `--user-id`, úroveň přístupu) |
| `fenix-campaigns` | `--status active\|suspend`, `--json` |
| `fenix-groups` | `--campaign-id`, `--json` |
| `fenix-ads` | `--campaign-id`, `--group-id`, `--json` |
| `fenix-negatives` | `--campaign-id`, `--group-id` (bez něj = úroveň kampaně), `--json` |
| `fenix-campaign-create` | `--name`, `--day-budget` (Kč), `--type fulltext\|context\|product`, `--status` (výchozí `suspend`), `--ad-selection`, `--dry-run`, `--json` |
| `fenix-group-create` | `--campaign-id`, `--name`, `--cpc` nebo `--cpm` (Kč), `--status`, `--dry-run`, `--json` |
| `fenix-ad-create` | `--campaign-id`, `--group-id`, `--headline1`, `--headline2`, `--headline3`, `--description1` (alias `--description`), `--description2`, `--final-url`, `--path1`, `--path2`, `--mobile-final-url`, `--tracking-template`, `--dry-run`, `--json`. Inzerát vzniká vždy aktivní, `status` API při zakládání odmítá |
| `fenix-negative-add` | `--campaign-id`, `--group-id`, `--name`, `--match-type negative\|negativePhrase\|negativeExact`, `--dry-run`, `--json` |
| `fenix-negative-remove` | `--campaign-id`, `--group-id`, `--name`, `--match-type` (povinný), `--confirm`, `--dry-run`, `--json` |
| `fenix-campaign-update` | `--campaign-id`, `--type` (bez něj se dohledá), `--name`, `--status`, `--day-budget` (Kč), `--total-budget` (Kč, `none` = bez limitu), `--start-date`, `--end-date` (`YYYY-MM-DD`, `none` datum smaže), `--capping-max`, `--capping-period daily\|weekly\|monthly\|whole`, `--capping-min-delay`, `--capping-min-delay-period minute\|hour` (hodnota a období vždy spolu), `--no-capping`, `--excluded-urls URL …` (nahradí celý seznam), `--no-excluded-urls`, `--dry-run`, `--json` |
| `fenix-ad-update` | `--campaign-id`, `--group-id`, `--ad-id ID …` (víc reklam jedné sestavy), `--type` (bez něj se dohledá), `--status`, `--start-date`, `--end-date` (`YYYY-MM-DD`, `none` smaže), `--name` (jen banner a branding), `--dry-run`, `--json`. Funguje pro všechny typy reklam včetně bannerů |

Příklad: konec kampaně a strop 3 zobrazení denně, pak konec bannerů o týden dřív (nejdřív vždy `--dry-run`):

```bash
./run.sh fenix-campaign-update --campaign-id 123 --end-date 2026-11-10 --capping-max 3 --capping-period daily --dry-run
./run.sh fenix-ad-update --campaign-id 123 --group-id 456 --ad-id 11 12 13 --end-date 2026-11-04 --dry-run
```

Datum se posílá bez času; API ho uloží jako půlnoc místního času (`2026-11-10T00:00:00+01:00`). Jestli kampaň ten den ještě běží, specifikace neříká, ověř to ve webovém Skliku.

**Čtyři věci, které se liší od příkazů nad DRAKem:**

- **Nová kampaň je pozastavená.** `fenix-campaign-create` posílá `status: suspend`, dokud nepřidáš `--status active`. Sestava se bez `--status` založí aktivní (výchozí hodnota API).
- **`--dry-run` znamená dvě různé věci.** U `fenix-campaign-create`, `fenix-group-create`, `fenix-ad-create`, `fenix-campaign-update` a `fenix-ad-update` je to skutečné ověření na straně API. U `fenix-negative-add` a `fenix-negative-remove` API žádný `dryRun` nemá, takže přepínač jen vypíše požadavek a **nic neodešle a nic neověří**.
- **Vylučující slova nemají ID.** Mažou se textem a typem shody (`--name` + `--match-type`) a smazání je trvalé. Volná shoda se ve Fénixu jmenuje `negative`; DRAKové `negativeBroad` příkazy přijmou a převedou.
- **`--json` vrací částky v haléřích.** Přepínače berou koruny a lidský výstup koruny ukazuje, ale `--json` je syrová odpověď API: `budget.dayBudget`, `exhaustedDayBudget`, `cpc` a `cpm` jsou v haléřích. Pozor na rozdíl proti `campaigns --json` a `groups --json`, které vrací koruny. Kredit ve `fenix-credit` je v korunách.

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

# Nákupy (Seznam Nákupy) — zdraví feedu, kde se výkon ztrácí, co není spárované
./run.sh feed-diagnostics
./run.sh nakupy-stats --split webType,deviceType --date-from 2026-08-01 --date-to 2026-08-31
./run.sh shop-items --unpaired --all --json

# Kampaně přes API Fénix — ověřit požadavek bez zápisu, pak založit (pozastavenou)
./run.sh fenix-me
./run.sh fenix-campaign-create --name "Search - Brand" --day-budget 250 --dry-run
./run.sh fenix-campaign-create --name "Search - Brand" --day-budget 250
./run.sh fenix-negatives --campaign-id 123           # vylučující slova kampaně (DRAK neumí)

# Měření a publika
./run.sh conversions
./run.sh sem-conversions                              # SEM účty: konverze přes Fénix
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

Součástí repa je i **skill pro [Claude Code](https://claude.com/claude-code)** ve složce [`skill/`](skill/). Ten obaluje tohle CLI a přidává PPC know-how (pravidla inzerátů, struktura kampaní, scénáře pro search i bannery), takže můžeš celé kampaně spravovat konverzací: `/sklik-ppc create search`, `/sklik-ppc optimize`, …

Skill ti dává **mechaniku** (jak věci udělat nástrojem) a **pravidla** (co Sklik povoluje). Strategii průběžné optimalizace si nastavíš podle svých cílů.

➡️ **Instalace skillu:** viz [`skill/INSTALL.md`](skill/INSTALL.md) (zkopíruj složku do `~/.claude/skills/` a nastav cestu k appce).

## Struktura projektu

```
sklik-ppc-app/
├── sklik_cli.py        # Tenký entrypoint (volá sklik.cli.main)
├── sklik/              # Balík s implementací
│   ├── api.py          #   engine: auth, session, rate-limit, _api_call, stránkování, chyby
│   ├── fenix.py        #   engine pro REST API Fénix (Nákupy + příkazy fenix-*): auth, Retry-After, stránkování
│   ├── formatting.py   #   převod CZK⇄haléře + JSON výstup
│   ├── reports.py      #   dvoukrokový report helper
│   ├── images.py       #   načítání/kódování obrázků (bannery + combined)
│   ├── cli.py          #   argparse + dispatch
│   └── commands/       #   jeden modul na doménu (ads, campaigns, keywords, …)
├── requirements.txt    # Závislosti (requests, python-dotenv)
├── setup.sh · run.sh   # Instalační / spouštěcí skript (aktivuje venv)
├── run-op.sh           # Volitelné: spuštění s tokeny z 1Passwordu (op run → run.sh)
├── .env.example        # Šablona pro tokeny
├── CLAUDE.md           # Signpost pro Claude Code (+ dokumentační mapa)
├── docs/api-notes.md   # Hutná reference chování API Drak
├── CHANGELOG.md        # Historie verzí
├── .env                # Tokeny nebo odkazy op:// (NEVERZOVAT)
└── skill/              # Skill pro Claude Code (/sklik-ppc) + INSTALL.md
```

## API poznámky

- Protokol: JSON-RPC `POST` na `https://api.sklik.cz/drak/json/v5/{metoda}`. Endpoint je **připnutý na v5**, aby se CLI tiše nerozbilo při major změně API.
- Reporty jsou dvoukrokové: `createReport` (filtry + období) → `readReport` (stránkování + sloupce).
- API **nepodporuje** filtry na nadřazené entity (`campaign.ids`, `group.ids`, `status`) v `restrictionFilter`, proto se aplikují na straně klienta, ale až nad kompletním seznamem.
- **Výpisy jsou kompletní, appka je sama stránkuje.** Metody `*.list` vrací najednou nejvýš 5000 řádků (`statsDataLimit`) a **nehlásí, že něco useknuly** (v odpovědi není celkový počet). CLI proto prochází offsety až do konce: `campaigns`, `groups`, `keywords`, `negatives`, `ads`, `banners` i statistiky vrací celý účet. Do verze 1.8.1 tu byly natvrdo zadané stropy (kampaně 100, sestavy/inzeráty/bannery 500 řádků) a větší účet tiše přišel o zbytek.
- Příklady použití API Drak: [github.com/seznam/sklik-api-examples](https://github.com/seznam/sklik-api-examples).
- **API Fénix** (Seznam Nákupy a příkazy `fenix-*`) je samostatné REST rozhraní na `https://api.sklik.cz/v1` s vlastní autentizací (refresh token → hodinový access token) a vlastními konvencemi: u Nákupů koruny místo haléřů, u kampaní haléře jako v DRAKu. Limit je 5 požadavků za sekundu (některé endpointy Nákupů míň); při překročení vrátí `429` s hlavičkou `Retry-After` a CLI počká přesně tak dlouho. Dokumentace: [api.sklik.cz/fenix](https://api.sklik.cz/fenix/), specifikace: `api.sklik.cz/v1/openapi.json`.

> Kompletní chování API (kvirky reportů, bezpečná výměna inzerátů, bannery, konverze, retargeting, rate limity, stavové kódy): **[docs/api-notes.md](docs/api-notes.md)**.

## Licence

MIT, viz [LICENSE](LICENSE).

## Autor

[Jindřich Fáborský](https://www.faborsky.cz), marketér a lektor. Vibe coding a AI v marketingu učím v kurzu [AI First](https://aifirst.cz).

Sklik PPC App používám na vlastní kampaně a v kurzu je doprovodným materiálem k 7. lekci, která ukazuje, jak vibe coding zapojit do každodenní marketingové práce. Další appky pro foundery a marketéry najdeš na **[faborsky.cz/appky](https://www.faborsky.cz/appky)**.
