# Nye modellforsøk

Kjør eller les `04_improved_models.ipynb`. Alle celler er kjørt med prosjektets
`.venv`, og tabeller/figurer er lagret i notebooken. Implementasjonen ligger i
`src/improved_models.py`. Tidligere modeller og resultater er bevart.

Åtte forhåndsdefinerte modeller ble sammenlignet på to kronologiske folds:
trening 2022–23 → validering 2023–24, deretter trening 2022–24 → validering
2024–25. Kriteriet var gjennomsnittlig sesong-RMSE. Dette er et annet
valideringsoppsett enn de første notebookene; sammenlign mot referansene som
er kjørt på samme folds her.

| Variant | Validering RMSE | Kandidat-RMSE |
|---|---:|---:|
| Gjennomsnitt av Ridge, utvidet HGB og spilletidsmodell | 1,91715 | 3,08332 |
| Ridge + utvidet HGB | 1,91860 | 3,08362 |
| Spilletidsmodell | 1,92174 | 3,09450 |
| Opprinnelig HGB-referanse | 1,92455 | 3,09725 |
| HGB med nye features | 1,92485 | 3,09907 |
| HGB med nye features og flere blad | 1,93197 | 3,11749 |

Kandidater defineres som spillere med minst 60 minutter i tidligere
femkampersgjennomsnitt. Fremtidig/faktisk spilletid brukes ikke til utvalget.
Spilletidsmodellen vekter separate poenganslag med predikerte sannsynligheter
for 0, 1–59 og 60+ minutter.

Vinneren ble refittet på 2022–25 og evaluert på 2025–26:

| Modell | RMSE | MAE | Spearman |
|---|---:|---:|---:|
| Tre-modellsensemble | 1,93332 | 0,96737 | 0,71443 |
| HGB-referanse | 1,93592 | 0,96860 | 0,71319 |

Forbedringen er liten. Ensemblet underpredikerer også gjennomsnittet litt
mer enn HGB (bias −0,094 mot −0,086). Ingen etterjustering er gjort på test.
Bootstrap over valideringsgameweeks gir positiv MSE-gevinst for ensemblet,
men intervallet er beskrivende og korrigerer ikke for at vinneren er valgt
blant flere modeller. Ingen garanti om fremtidig forbedring.

Holdout er tidligere undersøkt. Modellen gjelder fortsatt før hver kamp,
ikke historisk FPL-deadline; offisielle deadline-snapshots ble ikke funnet i
de undersøkte lokale kildene. En ekte deadline-backtest er fortsatt et
nødvendig datasteg før bruk til spillerkjøp. Retrospektiv topp-k er ingen
budsjettbegrenset FPL-strategi.

Verifisering: hele notebooken fullførte; spilletidssannsynligheter summerer
til 1; prediksjoner er endelige og endres ikke når faktisk target/minutter
endres på prediksjonsradene. Ny kjøring lagrer modell og tabeller i en ny
`artifacts/models/improved_*`-mappe. Ved lasting må `src` være på Python-stien,
og input må først behandles med `improved_models.enrich`.
