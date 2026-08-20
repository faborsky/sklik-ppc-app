# Changelog

Verze aplikace je v `sklik/__init__.py` (`__version__`, SemVer). Formát vychází z [Keep a Changelog](https://keepachangelog.com/). Datum je vydání dané verze.

## [1.8.1] — 2026-08-20 — Cílení kampaní opraveno: geo, modifikátory zařízení, rozvrh 🎯

Celá trojice přepínačů pro cílení kampaní posílala do API špatné datové tvary, takže
**žádný z nich nikdy nefungoval** — vždycky skončil chybou `400 Bad arguments`. Nahlásil
student kurzu AI First (`--regions`); zbylé dvě chyby vyplavala kontrola zbytku téhle
rodiny přepínačů proti dokumentaci API a živé ověření přes `campaigns.check`.

- **FIX: `--regions` posílalo holá čísla místo structů.** API čeká
  `[{"predefinedId": 100001}, …]`, CLI posílalo `[100001]` → `400 Parameter
  campaigns[0].regions[0] must be struct, not int`. Geo cílení tedy nešlo nastavit
  vůbec — ani při `campaign-create`, ani při `campaign-update`.
- **FIX: `--device-bids` posílalo desetinná čísla.** Hodnoty se parsovaly přes `float()`,
  takže i `0:-30:-30:-100` odešlo jako `0.0/-30.0/…` → `400 … devicesPriceRatio.desktop
  must be int, not double`. Nově jdou jako celá čísla; desetinný vstup (`-30.5`) CLI
  odmítne s vysvětlením místo záhadné chyby z API.
- **FIX: `--schedule-json` byl dokumentovaný v tvaru, který API odmítá.** README i nápověda
  ukazovaly `{"daySchedule":[{"value":[…]}, …]}` — což je tvar, v jakém API rozvrh **vrací**,
  ne v jakém ho přijímá (`400 … schedule must be array or nil, not struct`). Zápis chce
  **7 polí po 24 hodnotách 0–100** (`[[0,…,100,…], …×7]`, týden od pondělí). CLI teď přijme
  oba tvary a převede, `null` rozvrh smaže, a špatný počet dní/hodin odchytí lokálně
  (dřív z toho bylo `406 campaign_invalid_schedule_size`).
- **Zrušení geo cílení přes API nejde** — a `--regions ""` to dřív tiše slibovalo. API
  odmítá prázdné pole (`400 Array cannot be empty`) i `nil` (`400 … regions cannot be nil`),
  takže regiony jde odebrat jedině ve webovém rozhraní Skliku. CLI to teď řekne rovnou
  místo odeslání payloadu, který vždycky spadne. Nastavení regionů navíc **nahrazuje
  celou sadu**, což je nově v dokumentaci.
- **Kontrola zbytku appky:** všechny ostatní zapisované payloady byly porovnány s oficiální
  dokumentací API metod (structy vs. skaláry, int vs. double). Další chybu stejného druhu
  nenašla — peněžní hodnoty jdou do API vždy přes `_czk_to_halere()` jako `int`, ostatní
  číselné přepínače jsou `type=int`. Ověřen i tvar `--conditions-json`
  (`retargeting-create`), který dosud nikde nebyl popsaný.
- **Dokumentace:** `docs/api-notes.md` má nově u kampaňového cílení explicitně **zápisový vs.
  čtecí tvar** všech tří polí (liší se u regionů i rozvrhu) a poznámku, že **`campaigns.check`
  ověří payload zadarmo** — stejné vstupy jako create/update, žádný zápis, jedno volání.
  Do `CLAUDE.md` přibylo pravidlo kontrolovat tvar payloadu při každé změně zápisu.

## [1.8.0] — 2026-08-11 — Win rate, granularita statistik a oprava zobrazení CTR 📊

- **NOVÉ: `winRate` ve statistikách sestav** (`group-stats`) — podíl vyhraných aukcí.
  Do teď nebyl v CLI vůbec dostupný, přestože ho API vrací; jediné, co se dalo číst,
  byly `ish`/`ishSum`/`missImpressions`, které jsou u obsahových kampaní konstantní
  a nenesou informaci. **Existuje jen na sestavách** — kampaně, klíčová slova ani
  inzeráty ekvivalent nemají.
- **NOVÉ: `--granularity {total,daily,weekly,monthly,quarterly,yearly}`** u `campaign-stats`,
  `group-stats`, `keyword-stats` a `ad-stats`. Dvoukrokový report to uměl už dřív, ale
  CLI to nevystavovalo — denní řadu šlo dosud získat jen voláním po jednom dni.
  U ne-`total` granularity přibude v lidském výstupu datum období.
- **NOVÉ statistické sloupce** tam, kde je API pro danou entitu zná: `exhaustedBudgetShare`
  (podíl dne s vyčerpaným rozpočtem — jemnější než binární `exhaustedBudget`),
  `impressionMoney` / `clickMoney` (rozpad útraty), `avgCpt`, `underForestThreshold`,
  `stoppedBySchedule`.
- **NOVÉ: `adSelection` (rotace reklam) ve výpisu `campaigns`** — sloupec `Rotation`
  v lidském výstupu a klíč v `--json`. Nastavit ji šlo dosud přes `--ad-selection`,
  ale přečíst zpátky ne.
- **FIX: CTR se v lidském výstupu tisklo 100× menší.** API vrací `ctr` jako podíl
  (0,0073), CLI ho tisklo jako procento → `CTR: 0.01%` místo `0.73%` v `campaign-stats`,
  `group-stats`, `keyword-stats`, `ad-stats` a `search-queries`. `pulse` a `account`
  si CTR počítají samy, ty postižené nebyly. **`--json` výstup se nemění** (`ctr`
  zůstává podílem) — na jeho tvaru stojí navazující automatizace.
- **FIX: `avgCpt` se nepřevádělo z haléřů** na Kč jako ostatní peněžní sloupce.
- **FIX: `sitelinks` padalo na `TypeError`**, když měl odkaz prázdnou URL — API vrací `url: null`
  a `.get("url", "")` proti `None` nechrání (klíč existuje, default se nepoužije). Nalezeno při
  regresním testu této verze. ⚠️ Stejný vzorec je i v dalších výpisech (`campaigns`, `groups`,
  `keywords`, `retargeting`, `conversions`, `account`) — tam zatím pád nikdo nenahlásil, takže
  zůstávají beze změny; `banners` a `placements` už ošetřené byly.
- **Interně:** `STAT_COLUMNS` nahrazen funkcí `stat_columns(entity)`, protože sloupce
  povolené pro jednu entitu shodí `readReport` u jiné (`400 Bad arguments`). Původní
  název zůstává kvůli zpětné kompatibilitě. Kompletní mapa sloupců podle entit +
  poznámka, že **kampaňová frekvence zobrazení v API vůbec neexistuje** (a že
  **sestavový cap přebíjí kampaňový**), je v `docs/api-notes.md`.

## [1.7.2] — 2026-07-20 — Oprava jednotek hodnoty konverzí (100×) 🐛

- **FIX: `conversionValue` ze statistik se už nedělí stem.** API vrací sloupec
  `conversionValue` v reportech **přímo v Kč** (je to hodnota posílaná konverzním
  kódem), na rozdíl od ostatních peněžních sloupců (`totalMoney`, `avgCpc`,
  `clickMoney`, `impressionMoney`), které jsou v haléřích. CLI ho převádělo
  jako haléře → **100× podhodnocená hodnota konverzí** v `--json` výstupu
  `campaign-stats`, `group-stats`, `keyword-stats`, `ad-stats` a
  `search-queries`, a v `pulse` navíc **100× nadhodnocené PNO** (počítalo se
  z haléřových nákladů proti korunové hodnotě). Ověřeno živě proti sloupci
  `pno`, který počítá samo API. Nahlásil uživatel — díky!
- Audit všech ostatních peněžních míst (bidy, rozpočty, kredit, suggest CPC,
  konverzní definice) proti surovým odpovědím API: jednotky správně, beze změn.
- Z převodní tabulky odstraněn i mrtvý sloupec `conversionPrice` — API žádný
  takový report sloupec nemá (`readReport` ho odmítá) a CLI ho nikdy nežádalo.
- Quirk zdokumentován v `docs/api-notes.md` (tři jednotkové konvence API:
  haléře / Kč ve `sharedbudgets` + `getCredit` + stats `conversionValue`).

## [1.7.1] — 2026-07-20 — Čtení frekvenčního stropu sestavy 📖

- **`groups` nově vrací `maxUserDailyImpressions`** (frekvenční strop sestavy —
  max zobrazení na uživatele za den) v `--json` i v tabulkovém výpisu (sloupec
  `Freq/day`, `—` když není nastaven). Hodnotu šlo dosud jen **nastavit**
  (`--max-daily-impression` na create/update), ne přečíst — čtecí sloupec v API
  je plurál `maxUserDailyImpressions` (setter je singulár). Vytáhlo si to čtení
  nočního bid automatu (`ppc-automat`), který cíl zobrazení počítá z frekvence —
  ať ho bere z živé hodnoty, ne z předpokladu. Čistě aditivní, žádný nový příkaz.

## [1.7.0] — 2026-07-19 — Vizuální podpis + čitelný help 🎨

- **ASCII banner s barvami** („SKLIK" v seznamácké červené + verze a tagline) —
  vypíše se **jen člověku v terminálu** (stdout je TTY a neběží `--json`).
  Pipe, skripty a agentní tool-cally dostávají dál čistý výstup bez jediného
  znaku navíc. Respektuje `NO_COLOR`.
- **Seskupený `--help`**: místo jednoho plochého seznamu 88 příkazů přehled
  po doménách (Účet, Kampaně, Sestavy, Klíčová slova, Inzeráty, Výzkum,
  Sitelinky, Konverze, Retargeting, Bannery, Umístění, Cílení obsahovky,
  Rozpočty). Seznam se generuje ze skutečně registrovaných subparserů —
  nemůže se rozjet s realitou; nezařazený příkaz spadne viditelně do
  „Ostatní".
- **Doplněný chybějící soubor LICENSE (MIT)** — README licenci deklarovalo
  už dřív, ale bez souboru v repu nebyla právně platná (veřejné repo bez
  licence = všechna práva vyhrazena).

## [1.6.0] — 2026-07-19 — Kompletní pokrytí obsahovky + záchranná brzda 🚀

Největší rozšíření od začátku: 34 nových příkazů (54 → 88), postavené podle gap analýzy oficiální DRAK dokumentace. Všechno otestované živě na sandbox kampani (vytvořena → proklikána → smazána).

- **Remarketing konečně celý přes API: `retargeting-attach` / `retargeting-detach` / `retargeting-attached`.** Napojení publika na sestavu bylo dosud považované za „jen přes web UI" — ukázalo se, že žije v samostatném namespace `retargeting.group.lists.*`. Celý workflow (vytvoř publikum → napoj na sestavu → zkontroluj) teď jde bez klikání.
- **Negativní retargeting: `retargeting-exclude` / `retargeting-excluded` / `retargeting-exclude-remove`** — vyloučení publika z kampaně nebo sestavy (typicky „vyluč zákazníky z akviziční kampaně"); na rozdíl od napojení funguje i na search kampaních.
- **Vylučující umístění: `placement-exclude` / `placements-excluded` / `placement-exclude-remove` / `placement-exclude-restore`** — vyloučení webů z obsahových sestav (`patterns.negative.*`), základ optimalizace obsahovky. Pozor na dva quirky (API nevrací text vzoru; smazané vyloučení blokuje re-create → restore) — zdokumentováno v api-notes.
- **Cílení na zájmy / témata / úmysly: `targeting-categories` / `targeting` / `targeting-add` / `targeting-exclude` / `targeting-remove` / `targeting-restore`** s jednotným `--type interest/theme/intend` — tři dosud nedostupné dimenze cílení obsahové sítě, včetně vyloučení a CPC/CPT na kategorii. Výpis joinuje názvy kategorií z číselníku.
- **Sitelinky dotažené: `sitelink-update`, `sitelink-assign` (kampaň i sestava; nahrazuje celou sadu), `sitelinks-assigned`.** Dosud šly sitelinky jen vytvořit „do vzduchu" — teď jde celý životní cyklus. Přejmenování vytváří nové ID (server remove+create) — CLI ho vrací.
- **Sdílené rozpočty: `budgets` / `budget-create` / `budget-update` / `budget-remove`** — jeden denní rozpočet pro víc kampaní; přiřazení kampaní se řídí na rozpočtu. Quirk: částky v Kč, ne haléřích (jediný namespace bez konverze).
- **`*-restore` (undelete) pro kampaně, sestavy, klíčová slova, inzeráty a bannery** — záchranná brzda k `--confirm`; omylem smazané jde vrátit.
- **`keyword-set`** — deklarativní nastavení slov sestavy (upsert; `--remove-others` = plná synchronizace podle seznamu). **`banner-update`** — status/název/URL banneru bez remove+create.
- **`pulse` hlídá validitu dat**: přes `stats.status` zkontroluje, že statistiky za okno jsou kompletní, a když ne (dnešek bývá „preparing"), přidá varování — konec srovnávání s částečnými čísly. **`credit`** — zůstatek peněženky (i spravovaných účtů). **`regions`** — číselník ID pro `--regions`. **`autotagging` / `autotagging-update`** — správa UTM konfigurace.
- **Robustnost:** ne-JSON odpověď API (neznámá metoda, výpadek) už neshodí CLI tracebackem, ale vrátí strukturovanou chybu; `sitelinks` filtruje soft-smazané záznamy.
- **Tooling:** `scripts/check_docs_consistency.py` — mechanická kontrola CLI ↔ README ↔ CLAUDE.md ↔ skill (parita příkazů, počty, verze, fantomové příkazy). Spouštět před releasem.

## [1.5.0] — 2026-07-18 — Bezpečná výměna inzerátů + robustnost + chybějící funkce 🔧

Sada oprav z reálného nasazení — hlavně aby appka nikdy tiše nepoškodila účet a nemaskovala chyby:

- **`ad-replace` — bezpečná změna textu inzerátu.** Sklik neumí upravit text na místě; `ads.update` proto starý inzerát smaže a nový vytvoří v **jedné atomické serverové operaci** (vrací `newAdIds`) — takže když nový neprojde validací (typicky `ad_duplicate_in_db`), **původní zůstane nedotčený**. Nahrazuje nebezpečný ruční `ad-remove` + `ad-create`, kde selhaný create po removu tiše ztratil inzerát (reálně se stalo). Načte stávající inzerát, aplikuje jen zadaná pole, předvaliduje přes `ads.check`, pak provede výměnu.
- **Chyby jdou čitelně na stdout jako `{"error": …}`** (v `--json` režimu) — už se neschovávají za urllib3 `NotOpenSSLWarning`, který je navíc potlačený, takže stdout je vždy čistý JSON. Konec „záhad", kde se reálná chyba (duplicate) ztratila.
- **`group-update` / `group-create` `--max-daily-impression N`** — frekvenční limit (max. zobrazení na uživatele za den, `maxUserDailyImpression`).
- **`campaign-update` / `campaign-create` `--ad-selection {weighted,random,cpa,cos}`** — rotace inzerátů; `random` = rovnoměrně pro čistý A/B test kreativ.
- **`banner-download --group-id X --out DIR`** — stáhne obrázky bannerů sestavy na disk (čte `image.url`) pro verzování kreativ.
- **Interní přestavba (bez změny chování):** monolit `sklik_cli.py` rozdělen do balíku `sklik/` (engine `api.py`, `formatting`, `reports`, `images`, `commands/*`, `cli.py`); dokumentace srovnána — štíhlý `CLAUDE.md` signpost, hutná API reference v `docs/api-notes.md`, tenhle `CHANGELOG.md`, konec duplicit.
- **Drobnosti:** `ads --campaign-id` (filtr jako u `keywords`); `--description` jako alias k `--description1` (sjednocení s výstupním polem `description`); `negatives --campaign-id` reálně filtruje (přes sestavy kampaně — kampaňové vylučovačky jsou v API write-only, vypsat je nelze); opraveno zjištění, že přiřazení publika k sestavě v API **je** (`retargeting.group.lists.*`, zatím mimo CLI).

## [1.4.0] — 2026-06-23 — Respektování API limitů — ochrana účtu 🛡️

Aby se předešlo riziku **throttlingu nebo zablokování účtu** kvůli překračování limitů API (reálné riziko zvlášť u klientských účtů s vysokými spendy), appka teď API limity **aktivně hlídá**:

- Nový příkaz `api-limits` zjistí reálné per-account limity za běhu (`minuteRequestLimit`, `dayRequestLimit`, `statsDataLimit`, batch capy) a ukáže i živé lokální využití (requesty za posledních 60 s / 24 h).
- **Lokální request-budget napříč session.** Každé volání se počítá do per-account souboru `.rate_limit_<account>.json`, který přežívá restart i paralelní běhy, a kontroluje se *před* každým requestem: na 90 % minutového limitu počká do uvolnění okna, na denním limitu operaci **odmítne** (místo nekonečného mlácení do API). Limity se berou z `api.limits` (cache ~1×/den), ne natvrdo.
- `429` retry je nově **capovaný** (3× s back-offem, pak skončí); `413` (přetečení dávky) a doporučené limity počtu entit jsou zdokumentované ve skillu.

## [1.3.0] — 2026-06-20 — `pulse`: přehled účtu jedním voláním ⚡

Přibyl příkaz `pulse` — **account-wide souhrn jedním voláním**: totály, per-kampaň statistiky, delty vůči předchozímu stejně dlouhému období a top movery, vše předpočítané do kompaktního digestu (~400 tokenů). Nahrazuje řetězení `account` + `campaigns` + `campaign-stats`, takže analytický pull (i přes Claude Code) je výrazně levnější na tokeny a rychlejší. `--days N` (default 7), `--date-from/--date-to`, `--no-compare`, `--json`. Do granulárních `*-stats` se jde až na to, co `pulse` vypíchne.

## [1.2.0] — 2026-06-10 — Cílení na umístění (placementy) 🎯

Přibyly příkazy `placements`, `placement-create`, `placement-remove` — cílení obsahových sestav na konkrétní weby přes API (`patterns.*` namespace). Vzor je doména nebo cesta (`"forbes.cz"`, `"www.e15.cz/byznys"`), volitelně s vlastním CPC. Pozor: nová obsahová sestava bez umístění běží po **celé** obsahové síti — placementy přidávejte před aktivací kampaně.

## [1.1.0] — 2026-06-10 — Kombinovaná (nativní) reklama 🎉

Přibyl příkaz `combined-create` — vytváření **kombinované reklamy** přes API. To je formát, kterým se na obsahové síti Seznamu zobrazuje i **nativní reklama v článcích**: dodáš texty + obrázky a Sklik z nich sám skládá podobu pro nativní pozice v článcích i responzivní bannerové sloty. Výpis přes `ads` (`adType: combined`), statistiky přes `ad-stats`.
