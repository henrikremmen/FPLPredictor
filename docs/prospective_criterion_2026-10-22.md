# Forhåndsregistrert kriterium for modellbytte (versjon 1)

Registrert 22. oktober 2026, før deadline og utfall i GW8, som er den første
runden den automatiske prospektive løypen låser (`src/prospective_loop.py`).
Kriteriet ligger også i koden (`CRITERION` i `prospective_loop.py`), og
ledertavlen viser versjonen. Endringer krever en ny, datert versjon. Runder
evaluert under en eldre versjon rapporteres fortsatt under den.

## Hva som teller

- Bare runder der referanse og utfordrere er låst av løypen før deadline, med
  identiske spiller- og kampkohorter og hasher (`prospective_lock.verify_lock`).
- Bare endelige utfall. FPL må ha markert runden `finished` og `data_checked`.
  Foreløpig evaluering teller ikke.
- Referansen er produksjonsmodellen på låsetidspunktet (`incumbent`).

## Primærmål og regel

Per runde regnes differansen mellom utfordrer og referanse i **låste lagpoeng**.
Det er poengene til ellever og kaptein fra hver modells egen lovlige tropp til
100 millioner, valgt før deadline (`freeze_decisions`).

En utfordrer er **kvalifisert for en bytte-vurdering** bare når alle tre
punktene holder:

1. Minst **8** evaluerte runder.
2. Hele 95 %-bootstrapintervallet for gjennomsnittlig differanse per runde
   ligger **over 0**. Intervallet beregnes med 10 000 trekk av runder med
   tilbakelegging og seed 20261022.
3. Gjennomsnittlig differanse i MAE for ukepoeng per spiller er **≤ 0**, altså
   ikke dårligere poengprognoser.

## Hva kriteriet ikke gjør

- Løypen bytter aldri produksjonsmodell. Ledertavlen viser bare om
  kriteriet er oppfylt.
- Et bytte er en manuell beslutning. Den dokumenteres datert i `docs/` med
  ledertavlen som grunnlag, og bygges med den vanlige refit-koden.
- Utfordrere lagres i `artifacts/challengers/` med `production_eligible: false`.
  `capture_fpl.select_model_path` leser aldri derfra.

## Sekundære mål (rapporteres, avgjør ikke)

MAE og RMSE per kamp og per uke, kapteinspoeng, Brier for 60+ minutter og
kalibreringsgrupper når modellen gir sannsynligheter.
