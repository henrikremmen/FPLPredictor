# Modellforsøk

Åpne `01_dummy_baseline.ipynb`, `02_ridge_baseline.ipynb` og
`03_hist_gradient_boosting.ipynb` med prosjektets `.venv`. Notebookene deler
datakontroller, feature-policy og evaluering i `src/model_experiments.py`.
De inneholder kjørte tabeller og figurer. Nye kjøringer lagres separat under
`artifacts/models/`, inkludert modellen og kolonnene den forventer.

## Resultater

Valg av features, treningsvindu og parameter ble gjort på 2024–25, med RMSE
som kriterium for forventede poeng. Alle varianter finnes i notebookene.

| Modell | Validering RMSE | Validering MAE | Holdout RMSE | Holdout MAE |
|---|---:|---:|---:|---:|
| Dummy, gjennomsnitt | 2,311 | 1,436 | 2,352 | 1,501 |
| Ridge | 1,926 | 1,035 | 1,943 | 1,002 |
| HistGradientBoosting | 1,928 | 1,008 | 1,936 | 0,969 |

Ridge valgte alpha=100 og trening på 2023–24. Boosting valgte 7 blad og
trening på 2022–23 + 2023–24. Begge valgte context-settet med 34 features:
spilletid, FPL/ICT-form, underliggende angrep, keeper/forsvar, posisjon,
hjemme/borte og lag/motstander. Deretter ble valgt treningsvindu utvidet med
2024–25 og modellene evaluert på 2025–26.

Valideringsforskjellen i RMSE er svært liten og dokumenterer ingen sikker
vinner. Ridge er den forklarbare referansen. Boosting er en lovende kandidat
for videre utvikling, med lavere MAE og litt bedre rangering. Det er ikke
grunnlag for å kaste Ridge. Permutasjon av `minutes_last1` ga klart størst
økning i boostingmodellens valideringsfeil. Flere tidsfold og vurdering av
usikkerhet bør komme før større modellvalg.

## Hva resultatene betyr

- SAFE-kolonner er kandidater, ikke en garanti for tilgjengelighet ved
  FPL-deadline. Historikken er forskjøvet per kamp. En kamp senere i samme
  gameweek kan ha historikk fra en tidligere kamp i runden. Resultatene her
  gjelder prediksjon før hver kamp. Deadline-backtesting krever at alle
  historiske input rekonstrueres ved deadline.
- 2025–26 er allerede undersøkt i utforskningsnotebooken og er ikke en urørt
  bekreftende test. Denne sammenligningen tuner ikke på den sesongen.
- 322 Assistant Manager-rader i 2024–25 er utelatt. Null minutter beholdes.
  Omtrent 60 prosent av radene har null poeng; samlet MAE alene er derfor
  utilstrekkelig. Rapportene viser posisjon, faktisk spilletid, gameweek,
  kalibrering og topp-k-rangering.
- Topp-k summerer doble kamper per spiller/gameweek, men er retrospektiv og
  har ingen budsjett-, lag- eller posisjonsbegrensninger. Dummy-topplister er
  vilkårlige ved lik prediksjon. Dette er ikke en FPL-strategibacktest.
- Markedsfeatures og xP er utelatt. `position` og `was_home` er eksplisitte
  REVIEW-unntak. `target_points` og andre kamputfall går aldri inn i X.
- Imputering, skalering og fjerning av konstante/tomme features tilpasses
  treningsdata. xG/xA per 90 har mye NaN ved liten/ingen tidligere spilletid;
  det behandles som manglende data, ikke null prestasjon.

Neste nyttige forbedring er historikk ved FPL-deadline og validering på flere
tidligere tidsperioder. Det vil gi et sikrere grunnlag enn å utvide til flere
hundre features ut fra den ene holdout-sesongen.
