# Fase B: riktige tall (M9, M10, O3, E3)

6. november 2026. Gjelder fase B i [planen 06.11](improvement_plan_2026-11-06.md).
Produksjonsmodellen er uendret. Ingen nye policyer i produksjonen.

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| Syntetiske tester for kvantiler består | Oppfylt | `tests/test_point_distribution.py` tester begge F16-eksemplene. (1) 10 poeng eller 0 med 50 % tilgjengelighet gir Q90 = 10, ikke 5. (2) To uavhengige kamper med 20 % sjanse for 10 poeng gir Q90 for totalen = 10, ikke 20. Testene dekker også DGW og en usikker spiller i `build_market` (`tests/test_fpl_app.py`). |
| Rapport over endrede risikovalg | Oppfylt | `artifacts/m9_quantile_audit_20261106/report.{md,json}` sammenligner gammel og ny metode på dagens capture (`capture_20261106T140714Z`) for lag 5139814. Tallene står nedenfor. |
| Balanced og forventede poeng uendret | Oppfylt | `recommended_points` er identisk for alle spillere, og Balanced har ingen scoreendring i noen horisont (revisjonen sjekker begge). |
| Datakvalitet i API | Oppfylt | `GET /api/data-quality`. Kortversjonen i UI kommer på History → Model sammen med modellkortet ([fase C](phaseC_evaluation_2026-11-06.md)). |
| Nye mål i evalueringen | Oppfylt | `extended.json` per evaluert runde med Q10–Q90-treff og -bredde og bias per posisjon og DC-gruppe. Ledertavlen har en ny tabell for sekundære mål, med antall runder. Timingrapporten ligger i `artifacts/e3_forecast_timing_20261106/`. Kriterium v1 er urørt. |

## M9: usikkerhet fra fordeling

- Ny `src/point_distribution.py`. Hver kamps fordeling bygges som en stykkevis
  lineær kvantilfunksjon gjennom modellens Q10, Q50 og Q90.
  - Halene er en antakelse: under Q10 går linjen ned til min(Q10, 0), og over
    Q90 forlenges den med avstanden fra Q50 til Q90.
  - Kampene trekkes uavhengig med stratifisert Latin hypercube (1 000 trekk,
    fast seed) og summeres.
  - Tilgjengelighet er en blanding: punktmasse i 0 med sannsynlighet 1 − a.
  - Én kamp regnes eksakt, uten trekk.
- `fpl_app.build_market` bruker kampfila (`horizon_fixture_forecast.csv`) når
  den finnes, ellers én rad per GW.
  - `prediction_q*` er nå kvantiler av totalen.
  - `recommended_q*` er nå blandingen.
  - `recommended_points` er uendret.
- `capture_fpl.aggregate_forecast` summerer ikke lenger kvantiler i en DGW. Nye
  `horizon_forecast.csv` får kvantiler av rundetotalen. Gamle filer leses som før,
  og appen regner uansett på nytt fra kampfila.
- Kjent begrensning: kampene er uavhengige. Felles kamputfall for spillere i
  samme lag er M15 (senere).

Revisjon på dagens capture (topp 10 per posisjon og lagets XI og kaptein):

| Horisont | Profil | Største scoreendring | Endring i topp 10 | XI og kaptein |
|---|---|---:|---|---|
| 1 GW (GW10) | Balanced | 0,00 | ingen | uendret |
| | Stable | 0,23 | ingen | uendret |
| | Upside | 0,54 | ingen | uendret |
| 3 GW (GW10–12) | Balanced | 0,00 | ingen | uendret |
| | Stable | 0,93 | DEF: Truffert inn, Gvardiol ut | uendret |
| | Upside | 2,31 | MID: Rice inn, Iwobi ut | uendret |

Medianforhold mellom ny og gammel Q90: 1,00 for 1 GW (1,22 for usikre spillere,
som før ble skalert ned) og 0,76 for 3 GW (summerte kvantiler var for brede).

## M10: dobbelt skadefradrag (bare måling)

`src/availability_bias.py` sammenligner GW6–9 (2 670 spiller-runder) mot
fpl-data. Bias er faktisk minus prognose, så positiv verdi betyr for lav prognose.

| Utvalg | n | Bias, bare modell | Bias med appens faktor | MAE, bare modell | MAE med faktor |
|---|---:|---:|---:|---:|---:|
| Alle | 2 670 | +0,094 (SE 0,039) | +0,191 (SE 0,038) | 1,102 | 1,021 |
| Flagget (tilgjengelighet < 100 %) | 819 | −0,309 (SE 0,032) | +0,008 (SE 0,025) | 0,454 | 0,189 |
| 0 % | 702 | −0,256 | +0,026 | 0,286 | 0,031 |
| 25 % | 10 | +0,166 | +1,242 | 2,000 | 1,580 |
| 50 % | 28 | −0,759 | −0,094 | 1,091 | 0,552 |
| 75 % | 79 | −0,681 | −0,274 | 1,523 | 1,284 |

- Funnet støtter ikke F17. For flaggede spillere fjerner faktoren en
  overvurdering og halverer MAE.
- Den samlede økningen i undervurdering (0,094 → 0,191) kommer av at faktoren
  fjerner overvurderingen som før skjulte undervurderingen av tilgjengelige
  spillere (F18–F20).
- Ingen ny tilgjengelighetspolicy er laget. 25 %-gruppen har n = 10 og er ikke
  tolkbar.
- Rapport: `artifacts/m10_availability_bias_20261106/`.

## O3: datakvalitet

`src/data_quality.py` og `report()` leser bare lokale filer og gir:

- siste snapshot i fpl-data og alder;
- kilder i siste capture med status;
- oddsdekning per prognose-GW: GW10–11 100 %, GW12–17 0 %;
- andel prognoserader uten marked: 75 %;
- `code`-dekning: 534 av 670 spillere (79,7 %) har tidligere PL-historikk, nye
  spillere mangler naturlig;
- Understat merket som bare forskning;
- tapte låser (GW9) og siste evaluerte løyperunde (GW8);
- beslutningskonsekvenser i klartekst, for eksempel «No odds for GW12–17 …».

## E3: flere mål

- `prospective_evaluation.extended_metrics` regner ut:
  - Q10–Q90-treff, andel under og over, og snittbredde;
  - bias (prognose minus faktisk) per posisjon og per DC-gruppe
    (<5, 5–8, 8–11, 11+ defensive bidrag per 90 før deadline), med n og SE.
- Grupperingen leses fra bootstrap-fila som er frosset i låsen, ikke fra
  utfallet.
- Skrives som ny fil `extended.json` ved hver evaluering.
  `prospective_loop.py extend` fylte inn GW7 og GW8 (bare nye filer).
- GW8, incumbent:
  - Q10–Q90 traff 88,3 % (nominelt 80 %), snittbredde 3,0;
  - DEF −0,36 og GK −0,26 (for lavt), FWD og MID omtrent 0;
  - DC 8–11: −0,42 (SE 0,29).
  - `season_transfer_20261022` traff bare 36,4 %, fordi kvantilene ikke er
    justert med korreksjonen. Det er et funn om utfordreren.
- Brier og log loss for P(spiller) og P(60+) og kalibreringsgrupper fantes fra
  før i `report.json`. Ledertavlen viser nå Brier for 60+, treff og bredde med
  antall runder.
- Timing (`src/forecast_timing.py`, GW6–9, samme 659 spillere per runde): MAE
  faller mot deadline.
  - GW8: 1,29 ved 893 t før, 1,10 ved 79 t, 1,08 ved 25 t og 1,06 ved 2 t.
  - Snitt per gruppe: T-24h+ 1,156 (5 runder), T-6–24h 1,021 (2), T-6h 1,050 (2),
    siste snapshot 1,035 (5).
  - Gruppene dekker ulike runder og er ikke direkte sammenlignbare. Det er
    radene per runde som viser effekten.

## Verifisering (dekker fase A og B)

```
.venv/bin/python -m unittest discover -s tests   # 199 tester OK
npm run build --prefix frontend                  # OK
npm run test:e2e:workspace --prefix frontend     # 14 passert, 2 skjermbildetester hoppet over
npm run typecheck:mobile                         # OK
npm run test:mobile                              # 59 OK
```

## Gjenstår

- Kalibrering av kvantilene, som at Q10–Q90 traff 88 % mot 80 % nominelt, krever
  flere runder. Det tas ikke inn i produksjonen nå.
- Kortversjonen av O3 i UI kommer i fase C (History → Model).
