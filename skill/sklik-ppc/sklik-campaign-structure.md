# Best Practices — Struktura PPC kampaní ve Skliku

## Hierarchie

```
Účet
└── Kampaň (rozpočet, cílení, typ)
    └── Sestava / Ad Group (CPC, klíčová slova, inzeráty)
        ├── Klíčová slova (+ shody)
        ├── Inzeráty (min 3 varianty)
        ├── Vylučující slova (úroveň sestavy)
        └── Sitelinky
```

## Kampaně — organizace

### Dělení kampaní podle:
1. **Téma / produkt** — každý produkt/služba = vlastní kampaň
2. **Landing page** — různé LP = různé kampaně
3. **Sezónnost** — sezónní nabídky do oddělených kampaní (snadno zapnout/vypnout)
4. **Geografické cílení** — pokud se liší nabídka dle regionu
5. **Typ shody** — volitelně: broad kampaně vs exact kampaně (pro lepší kontrolu rozpočtu)

### Naming konvence
- Formát: `[produkt] - [téma] - [typ]`
- Příklad: `Eshop - Boty - Search`
- **Bez ampersandu (&)** — Sklik ho nepodporuje v názvech
- Konzistentní napříč účtem

### Rozpočet
- **Denní rozpočet**: Nastavuje se v CZK na kampaň
- Sklik může překročit denní rozpočet až o 20 % (vyrovná se v rámci měsíce)
- Minimální denní rozpočet: 10 Kč (doporučeno min 100 Kč pro smysluplný běh)
- Pro nové kampaně: konzervativní rozpočet, zvyšovat po validaci

### Typ kampaně
- `fulltext` — pro vyhledávání (search)
- `context` — pro obsahovou síť (display)
- `product` — pro Zboží.cz (produktové inzeráty)
- Nikdy nemíchat search a content do jedné kampaně

---

## Sestavy (Ad Groups) — organizace

### Tematické sestavy
- **1 sestava = 1 tematické téma**
- KW v sestavě musí být tematicky příbuzná
- Inzeráty v sestavě musí odpovídat KW

### NESKAG
- SKAG (single keyword ad groups) se nedoporučuje — příliš fragmentované
- Lepší: 5–20 KW na sestavu, tematicky konzistentní
- Výjimka: TOP konvertující KW může mít vlastní sestavu

### Pravidla
- **Neduplikovat KW mezi sestavami** — kanibalizace
- **Min 3 inzeráty na sestavu** — pro rotaci a testování
- **Max CPC na úrovni sestavy** jako default — přepsat na KW úrovni jen pro TOP slova

### Device Price Ratio
- Nastavuje se na kampani i sestavě
- Default: desktop=100, mobile=80, tablet=70
- Upravit dle dat: pokud mobil konvertuje lépe → zvýšit

---

## Klíčová slova — strategie

### Proces výběru
1. **Brainstorm** — jaká slova zákazník hledá
2. **Suggest** — rozšíření přes Sklik suggest API
3. **Objem + CPC** — ověření přes suggest-stats
4. **Třídění** — rozřazení do sestav
5. **Vylučovací slova** — hned od začátku

### Ideální KW profil
- Hledanost: min 5–10 měsíčně (nižší = long tail, vyšší = dražší)
- Relevance: přímo odpovídá nabídce
- Intent: transakční > informační (pro konverze)
- CPC: v rozmezí cílového CPA

### Shody — strategie
- **⚠️ Sklik broad = Google broad** (sémantické matchování, ne "všechna slova") — viz `sklik-search-rules.md`
- **Preferovaná strategie: phrase + exact** s co nejvíce variacemi (skloňování, synonyma, pořadí slov)
- Phrase na Skliku je sweet spot — slova v pořadí + extra slova okolo
- **Nová kampaň**: Začni s phrase + exact pro hlavní KW. Broad POUZE pro discovery s nízkým CPC a krátkodobě.
- **Po 2–4 týdnech**: Zkontroluj search queries z broad → dobré přidej jako phrase/exact, broad pausni
- **Průběžně**: Rozšiřuj vylučující slova z search queries (v negativePhrase/negativeExact, NE negativeBroad)
- **Pokrýt varianty explicitně**: "kurz umělé inteligence" i "kurz umělá inteligence", "školení ai" i "ai školení"

---

## Inzeráty — best practices

### Počet variant
- **Min 3 varianty** na sestavu
- Rotace: Sklik automaticky upřednostní lepší
- Po 2–4 týdnech: pausni nejhorší, přidej novou variantu

### Psaní inzerátů
1. **Headline1**: Klíčové slovo / hlavní nabídka
2. **Headline2**: Unikátní benefit (USP)
3. **Headline3**: Brand / doplňkový benefit / CTA
4. **Description1**: Konkrétní detaily nabídky (cena, termín, obsah)
5. **Description2**: Sociální důkaz / urgence / CTA

### A/B testování
- Měň vždy jen 1 element (headline NEBO description)
- Min 100 kliků na variantu před vyhodnocením
- Metrika: CTR pro awareness, konverze/CPA pro performance

---

## Bidding

### Manuální CPC
- Default pro search kampaně ve Skliku
- Nastavuj na úrovni sestavy, přepisuj pro TOP KW
- Začni konzervativně, zvyšuj na základě dat

### CPC doporučení
- Nová kampaň: začni na 60–80 % doporučeného CPC z suggest
- Po týdnu: upravuj dle pozice a CTR
- Cíl: pozice 1–3, ale ne za každou cenu

---

## Sitelinky

- Doplňkové odkazy pod inzerátem
- Max 4 zobrazené (přidej 4–6, Sklik vybere nejlepší)
- Každý sitelink = jiná stránka / nabídka
- Zvyšují CTR o 10–20 %
- Přiřazují se na úrovni kampaně
