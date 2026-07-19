# Changelog

Verze aplikace je v `sklik/__init__.py` (`__version__`, SemVer). Formát vychází z [Keep a Changelog](https://keepachangelog.com/). Datum je vydání dané verze.

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
