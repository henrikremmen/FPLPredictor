# Forhåndsregistrert kriterium for modellbytte (versjon 2)

Registrert 6. november 2026 kl. 15:30 UTC. Det er før GW11 låses (vinduet åpner
20.11 kl. 05:00 UTC) og før noe utfall finnes for rundene versjonen gjelder.
[Versjon 1](prospective_criterion_2026-10-22.md) er uendret. Den beregnes og
rapporteres fortsatt for alle løyperunder. Kriteriet ligger også i koden
(`CRITERION_V2` i `src/criterion_v2.py`) og vises på ledertavlen.
Endringer krever en ny, datert versjon.

## Hvorfor en v2

v1 sammenligner lagpoeng for hver modells egen tropp. Differansen per runde har
standardavvik på omtrent 13 poeng (66 runder backtest, se
`production_market_0erysib7/settings.json`). For å påvise en gevinst på 2 lagpoeng
per runde med 80 % styrke og 95 % konfidens trengs omtrent
(2,80 × 13 / 2)² ≈ 330 runder. v1 vil derfor nesten aldri bli oppfylt, selv for
en reell forbedring. v2 bruker hele kohorten av relevante spillere i hver runde.

## Hva som teller

- Bare løypepakker (`loop-v1`) som er låst etter registreringstidspunktet.
  Første mulige runde er GW11. GW8 og GW10 vises som diagnostikk og teller ikke.
- Bare endelige utfall: FPL har markert runden `finished` og `data_checked`.
  Låseregler, hasher og identiske kohorter er som i v1.
- Referansen er `incumbent`, altså produksjonsmodellen på låsetidspunktet.

## Kohort (fastsatt før deadline)

Kohorten bestemmes bare av det som er frosset i låsen. Det er referansens
prognoser og sannsynligheter og troppene modellene valgte. En spiller er med
hvis minst ett av punktene holder:

1. Spilleren er blant de 100 høyeste etter referansens prognose for runden.
2. Referansens sannsynlighet for minst én opptreden i runden er minst 0,5.
3. Spilleren er i minst én låst tropp (alle modeller, inkludert `fpl_ep_next`).

I GW8 ga dette 314 spillere. Faktiske minutter brukes aldri til å velge kohort.

## Primærmål og regel

For hver runde *r* og hver kohortspiller regnes absolutt feil i ukepoeng.
d_r er gjennomsnittet i kohorten av (utfordrerens feil − referansens feil).
Negativ verdi betyr at utfordreren er bedre.

**Primær utfordrer:** `features_v2_20261106` (plan M11). Den låses fra første
mulige runde etter registreringen. Primærutfordreren er **kvalifisert for en
bytte-vurdering** bare når alle tre punktene holder:

1. Minst **8** tellende runder.
2. Hele 95 %-intervallet for gjennomsnittet av d_r ligger **under 0**. Det er
   en blokk-bootstrap der hele runder trekkes med tilbakelegging, med 10 000
   trekk og seed 20261106.
3. Vernet: gjennomsnittlig differanse i pinball-tap (Q10/Q50/Q90, en
   trepunkts tilnærming til CRPS) er **≤ 0** når begge modellene har kvantiler.

**Andre utfordrere** er utforskende. Deres ensidige bootstrap-p-verdier
(andelen trekk med gjennomsnitt ≥ 0) korrigeres med Holm. En utforskende
utfordrer er kvalifisert bare med Holm-p < 0,05, minst 8 runder og vernet
oppfylt. Det hindrer at vi velger en tilfeldig vinner blant mange.

## Sekundære mål (rapporteres, avgjør ikke)

- v1-lagpoeng for modellens egen tropp.
- **Syntetiske tropper:** 300 lovlige tropper (2/5/5/3, høyst tre per klubb,
  høyst £100m) trekkes i forhold til eierandel fra den låste bootstrap-fila,
  med seed 20261106. Hver modell velger XI og kaptein i hver tropp
  (`fpl_app.optimal_lineup`). Tallet er faktiske poeng med kaptein × 2, uten
  autosubs.
- Skyggesesongen (E2) med bank, gratisbytter og autosubs/VC, når den har runder.
- E3-målene: Brier, kalibrering, intervalltreff og -bredde, og bias per
  posisjon og DC-gruppe.

## Styrkeberegning

d_r har standardavvik σ per runde. Det er estimert fra 2025-26 (38 runder, top
100-kohort, `artifacts/models/market_1sny_8dq/test_predictions.csv`) for to
modellpar: 0,020 og 0,044, median **0,032**. Antall runder for 80 % styrke
(tosidig 95 %) er n = ((1,96 + 0,84) · σ / δ)² (`criterion_v2.rounds_needed`):

| Reell gevinst δ i MAE per kohortspiller | Omtrent i % av MAE (≈ 2,0) | Runder |
|---:|---:|---:|
| 0,10 | 5 % | 1 (minimum 8 gjelder) |
| 0,05 | 2,5 % | 4 (minimum 8 gjelder) |
| 0,032 | 1,6 % | 8 |
| 0,02 | 1 % | 20 |

Med 8 runder kan vi forvente å påvise omtrent δ ≥ 0,03. Til sammenligning
skilte `refit_20261022` seg fra referansen med +0,016 i GW8 (dårligere). σ er
estimert på én sesong og to modellpar, så tallene er grove.

## Hva kriteriet ikke gjør

Som i v1 bytter løypa aldri produksjonsmodell. Et bytte er en manuell
beslutning. Den dokumenteres datert med ledertavlen som grunnlag og bygges med
den vanlige refit-koden. Utfordrere har `production_eligible: false`.
