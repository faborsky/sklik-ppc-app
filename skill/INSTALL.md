# Instalace skillu `/sklik-ppc` do Claude Code

Tahle složka obsahuje **skill pro Claude Code**, který obaluje CLI aplikaci v tomhle repu a přidává PPC know-how (pravidla inzerátů, struktura kampaní, bannerové scénáře). Po instalaci ho v Claude Code vyvoláš jako `/sklik-ppc`.

> Skill bez aplikace nefunguje — nejdřív zprovozni samotnou appku podle hlavního `README.md` (`./setup.sh` + token v `.env`).

## Předpoklady

1. **Naklonovaný tenhle repozitář** a funkční appka (`./setup.sh` proběhl, `.env` má token).
2. Nainstalovaný **Claude Code**.

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

## Aktualizace skillu

Když stáhneš novější verzi repa, zopakuj krok 1 (přepíše starou verzi) a krok 2 (znovu nastav cestu).
