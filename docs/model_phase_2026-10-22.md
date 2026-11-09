# Modellfasen: utfordrere, prospektiv løype og ledertavle (fase 4)

22. oktober 2026. Gjelder fase 4 i [forbedringsplanen](forbedringsplan_2026-10-22.md)
(M1–M8). Bygger på datafasen ([rapport](data_pipeline_2026-10-22.md)).

Produksjonsmodellen er **uendret**:
`artifacts/models/production_market_0erysib7`, `market_hgb + fallback + minutes + quantiles`,
trent på 2020-21 til 2025-26. Utfordrere ligger i `artifacts/challengers/`
med `production_eligible: false`. Appen og innhentingen leser aldri derfra.

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| Utfordrere er låst | Oppfylt | GW8 er låst 22.10 kl. 16:20 UTC, før deadline 23.10 kl. 17:30 UTC: `artifacts/prospective/loop_gw8_20261022T162032Z` og `…_decisions`. Pakken har 2 672 rader og identiske kohorter for `incumbent`, `refit_20261022` (M1), `season_transfer_20261022` (M2) og `fpl_ep_next`. Hver modell har sin egen låste tropp, ellever og kaptein. |
| Utfordrere evalueres automatisk | Oppfylt | `prospective_loop.py auto` evaluerer hver runde FPL har kontrollert. GW7 er allerede evaluert endelig av løypen (`artifacts/prospective_eval/gw7_manual_20261010`). GW8 evalueres ved første kjøring etter at FPL har kontrollert runden (rundt 27.10). Etter ditt valg kjøres kommandoen manuelt, ikke av en installert tidsplan. |
| Ledertavle finnes | Oppfylt | `artifacts/prospective_eval/leaderboard.{md,json}` og `leaderboard_rounds.csv`. |
| Ingen produksjonsbytte uten forhåndsregistrert kriterium | Oppfylt | [Kriterium v1](prospective_criterion_2026-10-22.md) er registrert før noe GW8-utfall finnes. Det krever minst 8 løyperunder, et 95 %-bootstrapintervall for differansen i lagpoeng som ligger over 0, og MAE som ikke er dårligere. Løypen skriver aldri til `artifacts/models`; det er testet. |

## Hva som er laget

- `src/prospective_loop.py` (M4):
  - `lock`: referanse, utfordrere og FPLs `ep_next` scorer de samme radene fra
    siste capture før deadline. Pakken fryses med `prospective_lock`, og hver
    modell får låst tropp via `freeze_decisions`. Én pakke per runde, så ingen
    runde kan telles to ganger. Produksjonens `prediction`- og `p_`-kolonner
    fjernes før scoring, slik at en utfordrer aldri arver dem.
  - `evaluate`: endelig evaluering mot en capture der runden er
    `data_checked`. Resultatet skrives til nye mapper under
    `artifacts/prospective_eval/`.
  - `leaderboard`: tabeller og kriteriestatus, inkludert status for M7.
  - `auto`: låser når neste deadline er innen 30 timer, henter utfall ved
    behov, evaluerer og oppdaterer ledertavlen. Kommandoen er idempotent.
- `src/challengers.py`: register og trening.
  - Felles mønster for M2, M5 og M8: en liten korreksjonsmodell lærer avviket
    fra en basemodell, trent på prognoser utenfor utvalget. Basen trent til og
    med 2024-25 predikerer 2025-26, og basen trent til og med 2025-26 predikerer
    inneværende sesong. Den retrospektive sjekken lærer bare på 2025-26 og
    testes på 2026-27 GW1–7.
- `src/bonus_calibration.py` (M3) og `src/cup_minutes.py` (M8).
- `src/market_models.py` og `src/model_experiments.py`: features-mappe,
  sesonger og odds for inneværende sesong kan nå velges. Standardverdiene er
  uendret. `_production_model(..., include_current=True)` brukes bare av M1.
- `src/external_context.py`: aliaser for opprykkslagene Coventry, Hull og
  Ipswich. `team_key` slår nå også opp aliaser etter at `fc` er fjernet.
- Ny feature-tabell i `data/processed/features_20261022/` (258 382 rader, med
  2026-27 GW1–7). Den gamle tabellen som produksjonen er trent på, er urørt.

## Utfordrere

Retrospektiv sjekk på 2026-27 GW1–7 (4 551 rader). Produksjonsoppskriften
trent til og med 2025-26 har MAE 1,2078 og RMSE 2,1746. Sjekken er diagnostisk;
bare låste runder avgjør.

| Navn | Plan | Hva | MAE | RMSE | Låst fra |
|---|---|---|---:|---:|---|
| `refit_20261022` | M1 | Produksjonsoppskriften refittet med 2026-27 GW1–7 (167 623 rader, alle med odds) | – | – | GW8 |
| `season_transfer_20261022` | M2 | M1 pluss korreksjon fra forrige sesong koblet via `code` (poeng og xGI per 90, minutt- og startandel, flagg for ny spiller). Vekten faller lineært til 0 etter GW10. 72 % av spillerne i 2026-27 har forrige sesong. | 1,2520 | 2,1677 | GW8 |
| `crowd_20261022` | M5 | M1 pluss netto overganger, eierandel og prisstigning, rangert innen runden | 1,2114 | 2,1449 | GW9 |
| `openfpl_style_20261022` | M6 | Posisjonsvise ensembler av RandomForest og LightGBM | 1,2213 | 2,1788 | GW9 |
| `cup_minutes_20261022` | M8 | M1 pluss minutter i cup og Europa siste 7 og 14 dager (FPL-Core-Insights, kun forskning) | 1,2416 | 2,1715 | GW9 |
| `fpl_ep_next` | M5 | FPLs egen prognose, `ep_next` fra bootstrap, delt jevnt på spillerens kamper | – | – | GW8 |

Ingen utfordrer er tydelig bedre retrospektivt. M5 har lavest RMSE, men
omtrent samme MAE. Det er nettopp derfor beslutningen ligger i den låste,
prospektive løypen.

Etter refaktoren av treningskoden er M1 og M2 kontrollert mot den låste
GW8-pakken. De gir de samme prognosene, med avvik under 1e-15.

## Funn per tiltak

- **M3 (BPS 2026/27):** se `artifacts/model_research/bps_calibration_20261022/report.json`.
  Komponentmodell v2, faktisk bonus delt på forventet:

  | Posisjon | Kontroll 2025-26 GW1–7 (gamle regler) | 2026-27 GW1–7 (nye regler) |
  |---|---:|---:|
  | GK | 0,73 | 1,08 |
  | DEF | 1,11 | 0,93 |
  | MID | 0,98 | 1,12 |
  | FWD | 1,17 | 1,04 |

  Forsvarere taper og midtbanespillere vinner, som regelendringene tilsier.
  Modellfritt endret bonus per 90 seg lite: DEF fra 0,213 til 0,203, MID fra
  0,309 til 0,318, GK fra 0,213 til 0,257. Effekten er liten i poeng (rundt
  0,01 per spiller per kamp) og utvalget er lite (100–200 bonuspoeng per
  posisjon). Ingen egen utfordrer nå. Saken bør tas opp igjen etter rundt GW15
  med BPS-komponenter fra `fixtures[].stats`, som allerede lagres i `fpl-data`.
- **M5:** produksjonsmodellen bruker **ingen** publikumssignaler
  (`transfers_in_event`, eierandel, `cost_change_event`). De fryses i
  snapshotet, men er ikke features. Odds-features brukes. Publikumssignaler
  testes nå som utfordreren `crowd_20261022`, og `ep_next` som benchmark.
  `ep_next` som feature krever flere sesonger med `ep_next` fra før deadline.
  Vaastavs `xP` kan være registrert etter kamp. Det er ikke gjort.
- **M6:** OpenFPLs egen kode krever `xgboost`, som ikke er installert, og deres
  Understat-pipeline. Arkitekturen er derfor gjenskapt med installerte pakker,
  der LightGBM erstatter XGBoost. Å kjøre deres faktiske kode krever din
  godkjenning av en ny avhengighet.
- **M7:** isotonisk kalibrering av P(spiller) og P(60+) er implementert i
  `fit_minutes_calibration`. Den nekter å kjøre før det finnes 6 evaluerte
  runder; nå finnes 1 (GW7). Ledertavlen viser status. Dette er **blokkert av
  data**, ikke av kode.
- **M8:** FPL-Core-Insights har `playermatchstats` for cup og Europa med FPL-id
  og `player_code`: 2 389 opptredener i 2025-26 og 861 i 2026-27 så langt.
  Filene lagres med URL og SHA-256 i `data/raw/fpl_core_insights/`. Ved låsing
  festes minuttene til radene, og filene inngår som kildebevis. En nedlasting
  eldre enn 24 timer erstattes av en ny for inneværende sesong. Hele
  nedlastingen tok 20 minutter fordi GitHub raw er tregt.

## GW7, endelig

GW7 ble kontrollert av FPL etter forrige rapport. Den endelige evalueringen er
identisk med den foreløpige (ingen korreksjoner):

| | Referanse | Understat | Komponent v2 | Elo | Tilgjengelighet konstant |
|---|---:|---:|---:|---:|---:|
| Lagpoeng | 68 | 64 | 64 | 61 | 61 |
| MAE | 1,1364 | 1,1341 | 1,1784 | 1,1400 | 1,0801 |

Resultatene ligger i `artifacts/model_research/gw7_final_20261022/` og i løypens
`artifacts/prospective_eval/gw7_manual_20261010/`. GW7 vises på ledertavlen,
men teller ikke, fordi den ble låst manuelt før løypen fantes.

## Verifisering

```
.venv/bin/python -m unittest discover -s tests   -> Ran 183 tests, OK
                                                    (én feil sett i én kjøring; ikke gjenskapt i 6 påfølgende)
npm run build --prefix frontend                  -> ✓ built
npm run test:e2e:workspace --prefix frontend     -> 12 passed, 2 skipped (skjermbildetester)
npm run typecheck:mobile                         -> exit 0
npm run test:mobile                              -> 8 suites, 56 tests passed
```

Nye tester:
- `tests/test_prospective_loop.py`: låsing med tre modelltyper, at
  produksjonsutdata ikke lekker inn, at sen låsing og dobbel låsing feiler,
  at en `production_eligible`-utfordrer avvises, «pending», cupminutter ved
  låsing, kriteriet (8 runder, intervall og MAE-vakt, legacy-runder telles
  ikke, ingen skriving til `artifacts/models`) og M7-sperren.
- `tests/test_challengers.py`, `tests/test_bonus_calibration.py`,
  `tests/test_cup_minutes.py`.
- En ny aliastest i `tests/test_external_context.py`.

## Neste steg (krever tid eller deg)

1. **Etter at GW8 er kontrollert (rundt 27.10):** kjør
   `.venv/bin/python src/prospective_loop.py auto`. Den henter utfall og
   evaluerer runden.
2. **Mellom 30. og 31.10, før GW9-deadline:** kjør samme kommando. GW9 blir
   da låst med alle seks modellene.
3. **Kriteriet** kan tidligst være oppfylt etter 8 løyperunder, altså GW15 for
   M1 og M2 og GW16 for M5, M6 og M8.
4. **M7** blir aktuelt etter 6 evaluerte runder.
