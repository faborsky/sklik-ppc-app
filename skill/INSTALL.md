# Instalace skillu `/sklik-ppc` do Claude Code

Tahle složka obsahuje **skill pro Claude Code**, který obaluje CLI aplikaci v tomhle repu a přidává PPC know-how (pravidla inzerátů, struktura kampaní, bannerové scénáře). Po instalaci ho v Claude Code vyvoláš jako `/sklik-ppc`.

> Skill bez aplikace nefunguje — nejdřív zprovozni samotnou appku podle hlavního `README.md` (`./setup.sh` + token v `.env`).

## Předpoklady

1. **Naklonovaný tenhle repozitář** a funkční appka (`./setup.sh` proběhl, `.env` má token).
2. Nainstalovaný **Claude Code**.

### Kde vzít API token Skliku

1. Přihlas se do Skliku a otevři **[www.sklik.cz/settings](https://www.sklik.cz/settings)**.
2. Sekce **„Přístup k API Drak"** → vygeneruj / zkopíruj svůj **API token**.
3. Token vlož do `.env` v repu appky jako `SKLIK_API_TOKEN` (detaily v hlavním `README.md`).

> Token je heslo k účtu přes API — patří jen do `.env` (v `.gitignore`), nikdy do kódu ani gitu.

## Krok za krokem

Předpokládejme, že sis repo naklonoval do `~/dev/sklik-ppc-app` (uprav cesty podle sebe).

### 1) Zkopíruj skill do své Claude Code složky se skilly

```bash
mkdir -p ~/.claude/skills
cp -R ~/dev/sklik-ppc-app/skill/sklik-ppc ~/.claude/skills/sklik-ppc
```

### 2) Nastav skillu cestu k appce

Skill volá aplikaci přes placeholder `<SKLIK_APP_DIR>`. Nahraď ho **absolutní cestou** ke svému klonu repa. Jednorázově:

```bash
# macOS / Linux — uprav cestu za = na svoji
APP_DIR="$HOME/dev/sklik-ppc-app"
sed -i '' "s#<SKLIK_APP_DIR>#$APP_DIR#g" ~/.claude/skills/sklik-ppc/SKILL.md   # macOS
# na Linuxu použij: sed -i "s#<SKLIK_APP_DIR>#$APP_DIR#g" ~/.claude/skills/sklik-ppc/SKILL.md
```

> Můžeš to udělat i ručně — otevři `~/.claude/skills/sklik-ppc/SKILL.md` a nahraď všechny výskyty `<SKLIK_APP_DIR>` cestou ke své appce.

### 3) Ověř

Otevři Claude Code a napiš:

```
/sklik-ppc
```

Skill by se měl nabídnout. Zkus třeba:

```
/sklik-ppc create search   (a popiš svůj projekt)
```

Claude se tě nejdřív doptá na kontext, navrhne strukturu a **počká na tvoje schválení** — nic nevytvoří bez potvrzení.

## Co skill umí

- **create search** — výzkum klíčových slov, struktura kampaně, texty inzerátů, založení přes CLI
- **optimize search** — vytáhne statistiky a pomůže s úpravami (bidy, negativa, rozpočty)
- **review-banners / replace-banners** — přehled a výměna bannerů
- **create / optimize display** — obsahové a remarketingové kampaně

> Skill ti dává **mechaniku** (jak věci udělat nástrojem) a **pravidla** (co Sklik povoluje, jak psát inzeráty). **Strategii průběžné optimalizace** — kdy co měnit, jaké KPI sledovat, jak reportovat — si nastav podle svých cílů a účtů. To je ta zajímavá část, kterou se učíš v kurzu. 🙂

## Doplň si skill o své vlastní know-how (doporučeno!)

Tenhle skill je **schválně univerzální** — záměrně neobsahuje konkrétní strategii, protože ta je u každé firmy jiná. Největší hodnotu z něj dostaneš, když si ho **přizpůsobíš sobě**. Skill je jen složka markdown souborů, takže je to snadné:

1. **Přidej vlastní referenční dokument.** Do `~/.claude/skills/sklik-ppc/` si vytvoř např. `moje-strategie.md` a sepiš do něj:
   - jak ty stavíš a optimalizuješ kampaně (tvoje postupy, prahy, kadence kontrol),
   - cílové KPI a CPA/PNO pro tvoje produkty,
   - tón a styl inzerátů tvojí značky, no-go fráze,
   - vylučující slova, která se ti osvědčila,
   - tvoji firemní strategii / segmenty / sezónnost.

2. **Odkaž na něj ze `SKILL.md`.** V sekci *„Load Reference Documents"* přidej řádek, ať Claude tvůj dokument načítá:
   ```
   - `moje-strategie.md` — moje postupy a firemní strategie (VŽDY přečíst)
   ```

3. **Klidně si uprav i scénáře.** Můžeš si do `SKILL.md` doplnit vlastní krok pro reporting, PPC deník, schvalovací proces apod.

> Čím konkrétnější kontext skillu dáš, tím lepší a „tvoje" budou návrhy. Univerzální skill = univerzální výstup; tvoje know-how = výstup na míru.

## Aktualizace skillu

Když stáhneš novější verzi repa, zopakuj krok 1 (přepíše starou verzi) a krok 2 (znovu nastav cestu).
