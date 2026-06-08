# Pravidla textové reklamy ve Skliku

Vychází z oficiální nápovědy Seznam Sklik a z chování ověřeného v praxi.

## ETA (Extended Text Ad) formát

### Nadpisy (Headlines)
- **Headline1**: povinný, max 30 znaků
- **Headline2**: povinný, max 30 znaků
- **Headline3**: volitelný, max 30 znaků
- Zobrazení: `Headline1 | Headline2 | Headline3`

### Popisy (Descriptions)
- **Description1**: povinný, max 90 znaků
- **Description2**: volitelný, max 90 znaků

### URL
- **Final URL**: povinný, musí být platná URL
- **Path1**: volitelný, max 15 znaků (zobrazuje se jako `domena.cz/path1/path2`)
- **Path2**: volitelný, max 15 znaků (vyžaduje path1)

### Zakázané prvky
- **Vykřičníky v nadpisech**: ZAKÁZÁNO (v popisech max 1 vykřičník)
- **VELKÁ PÍSMENA celých slov**: ZAKÁZÁNO (výjimka: běžné zkratky jako AI, CRM, SEO)
- **Výzvy ke kliknutí**: "klikněte zde", "klikni sem" — ZAKÁZÁNO
- **Superlativy bez doložení**: "nejlepší", "nejlevnější" — vyžaduje důkaz/certifikát
- **Opakování interpunkce**: "!!!", "???", "..." — ZAKÁZÁNO
- **Emojis**: ZAKÁZÁNO v textových inzerátech
- **Ampersand (&)**: ZAKÁZÁNO v názvech kampaní a sestav

### Doporučení pro kvalitní inzerát
1. Headline1 = hlavní nabídka / klíčové slovo
2. Headline2 = benefit / USP / CTA
3. Headline3 = brand / doplňkový benefit
4. Description1 = rozvinutí nabídky s konkrétními detaily
5. Description2 = sociální důkaz / urgence / CTA
6. Jazyk inzerátu = jazyk klíčových slov
7. Min 3 varianty inzerátů na sestavu (pro A/B testování)

---

## Shody klíčových slov (Match Types)

### Volná shoda (broad)
- **⚠️ POZOR — Sklik broad = Google broad (sémantické matchování)**
- **Dokumentace Skliku tvrdí** "musí obsahovat všechna slova" — **v praxi to neplatí!**
- **Reálné chování**: Sklik matchuje sémanticky, dotaz NEMUSÍ obsahovat všechna slova z KW
- **Pozorováno v praxi**: "školení chatgpt" (broad) matchoval "chat gpt" a "chatgpt" (bez "školení"); "jak používat ai" (broad) matchoval "ai" samotné; broad KW dokáže matchovat i sémanticky vzdálené dotazy
- **Příklad**: KW `školení chatgpt` broad → zobrazí se i na: "chatgpt", "chat gpt", a další sémanticky příbuzné dotazy
- **Doporučení**: Broad match používat POUZE pro discovery s nízkým CPC. Pro řízený provoz preferovat phrase+exact.
- **Neexistuje BMM**: Sklik nemá broad match modifier (Google "+keyword"). Nejbližší náhrada = phrase match.

### Frázová shoda (phrase)
- **Chování**: KW se musí v dotazu vyskytovat ve správném pořadí slov
- **Příklad**: KW `kurz ai` → zobrazí se na: "online kurz ai pro firmy", "nejlepší kurz ai"
- **Nezobrazí se**: "ai kurz" (obrácené pořadí)
- **Použití**: Střední přesnost, dobrý poměr dosahu a relevance

### Přesná shoda (exact)
- **Chování**: Dotaz musí přesně odpovídat KW
- **Příklad**: KW `kurz ai` → zobrazí se pouze na: "kurz ai"
- **Nezobrazí se**: "kurz ai online" (extra slova)
- **Použití**: Nejvyšší relevance, nejvyšší CTR, ale nejmenší dosah

### Strategie shod v sestavě
- **Preferovaná strategie: phrase + exact** — maximální pokrytí variací s kontrolou relevance
- Phrase = slova ve správném pořadí + další slova okolo = ideální sweetspot
- Exact pro TOP konvertující KW a přesné dotazy
- Broad POUZE pro discovery fázi s nízkým CPC a pečlivým monitoringem search queries
- Po nasbírání dat z broad: přidat fungující dotazy jako phrase/exact, broad pausnout
- Neduplikovat KW se stejnou shodou mezi sestavami
- **Pokrýt skloňované varianty**: Sklik phrase nerozlišuje skloňování dostatečně, proto přidat explicitně (např. "kurz umělé inteligence" i "kurz umělá inteligence")

---

## Vylučující slova (Negative Keywords)

### Match typy
- **negativeBroad**: Vyloučí dotazy obsahující všechna slova (libovolné pořadí)
- **negativePhrase**: Vyloučí dotazy obsahující frázi ve správném pořadí
- **negativeExact**: Vyloučí pouze přesný dotaz

### ⚠️ Volba match typu u negativních slov — DŮLEŽITÉ
- **negativeBroad je nebezpečné** — stejně jako u pozitivních KW matchuje příliš široce
- Jedno slovo v negativeBroad (např. "plat") vyloučí JAKÝKOLI dotaz obsahující "plat"
- **Preferuj negativePhrase** pro fráze (2+ slova) — vyloučí jen dotazy s přesným pořadím slov
- **Preferuj negativeExact** pro jednotlivá slova — vyloučí jen přesný dotaz
- **Příklad**: Chceš vyloučit "kurzy pro seniory" → použij negativePhrase "kurz pro seniory", NE negativeBroad "seniory" (to by vyloučilo i relevantní dotazy obsahující slovo "seniory")

### 3 úrovně vylučování
1. **Skupina (group)**: Vylučuje pouze v dané sestavě
2. **Kampaň (campaign)**: Vylučuje v celé kampani
3. **Účet**: Vylučuje na celém účtu (přes sdílené seznamy)

### Pravidla diakritiky
- Vylučující slova ve Skliku **rozlišují diakritiku**
- Je nutné přidat varianty s diakritikou i bez ní, pokud se obě vyskytují
- Pro důkladné vyloučení např. ceny zdarma přidej: "zdarma", "zadarmo", "free", "gratis"

### Typické vylučující slova
- Cenové: zdarma, zadarmo, free, levně (pokud nechceme levné leads)
- Zaměstnanecké: práce, job, kariéra, plat, pozice
- Informační: co je, jak funguje, wiki, definice (pokud cílíme na transakční intent)
- Konkurence: název konkurenta (pokud nechceme konkurenční dotazy)
- Nerelevantní: recenze, zkušenosti (záleží na strategii)

---

## Léky a doplňky stravy

Pokud inzerát propaguje léky nebo doplňky stravy:
- **Povinné označení**: "Lék" / "Doplněk stravy" v textu inzerátu
- **Povinný odkaz**: Na příbalový leták nebo PIL
- Bez superlativů o účinnosti
- Sklik může inzerát zamítnout bez povinných označení

---

## Landing page pravidla

- URL musí fungovat (HTTP 200)
- Obsah landing page musí odpovídat inzerátu
- Žádné automatické přesměrování na jinou doménu
- Stránka musí obsahovat kontaktní údaje / identifikaci provozovatele
- HTTPS preferováno
