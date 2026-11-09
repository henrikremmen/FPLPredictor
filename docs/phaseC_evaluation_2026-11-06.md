# Fase C: evaluering (E1, E2, E4)

6. november 2026. Gjelder fase C i [planen 06.11](improvement_plan_2026-11-06.md).
Kriterium v1 er uendret. Produksjonsmodellen er uendret.

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| v2 registrert før neste lås | Oppfylt | [docs/prospective_criterion_v2_2026-11-06.md](prospective_criterion_v2_2026-11-06.md) ble skrevet kl. 15:13 UTC og registrert kl. 15:30 UTC (`CRITERION_V2` i `src/criterion_v2.py`). Neste lås er GW11, tidligst 20.11 kl. 05:00 UTC. Ledertavlen lagrer dokumentets SHA-256. `applies()` teller bare pakker låst etter registreringen. GW8 og GW10 vises som diagnostikk og teller ikke (testet). |
| Styrkeberegning og kohort definert før deadline | Oppfylt | Kohorten er topp 100 etter referansen, P(opptreden) ≥ 0,5 eller med i en låst tropp. Den bygges bare fra låsen (GW8: 314 spillere). σ per runde ≈ 0,032 (2025-26, 38 runder). Med 8 runder kan omtrent δ ≥ 0,03 MAE påvises. v1 ville trengt omtrent 330 runder for 2 lagpoeng (`rounds_needed`, testet). |
| Skyggesesong låser og scorer én runde ende til ende | Delvis oppfylt; scoring venter på data | Ekte: lag 5139814 er startet fra offentlig tropp for GW10, og fem policyer ble låst 6.11 kl. 15:14 UTC (deadline 18:30), se `artifacts/shadow_season/2026-27_5139814/lock_gw10.json`. Scoring er mulig når fpl-data eksporterer GW10 (FPL `data_checked`, rundt 10.–11.11): `shadow_season.py score --event 10`. Ende til ende er vist med syntetiske data i `tests/test_shadow_season.py`: lås, avvist sen eller dobbel lås, scoring med autosub og VC-fallback, og neste tilstand med rullet FT, bank og kjøpspris. |
| Modellkort i UI | Oppfylt | Web: History → **Model and data** (`#/model`). Mobil: History → «Model and data quality» (`/model`). Kortet viser datakvalitet med beslutningskonsekvens (O3), låste runder med antall, kalibrering og kjente begrensninger, og påstår ingen overlegenhet. Testet i e2e (`model card: …`) og med `ModelCardTest`. |

## E1: kriterium v2

- `src/criterion_v2.py`:
  - `cohort`, `round_metrics` (absolutt ukefeil og pinball-tap fra
    Q10/Q50/Q90) og `summarize`. Sammendraget bruker blokk-bootstrap over
    runder med 10 000 trekk og seed 20261106, og Holm for utforskende
    utfordrere.
  - `rounds_needed` for styrkeberegningen.
  - `synthetic_squads` og `synthetic_squad_points`: 300 lovlige tropper vektet
    etter eierandel. Hver modell velger XI og kaptein.
- Primær utfordrer er `features_v2_20261106` (M11, [fase D](phaseD_challengers_2026-11-06.md)).
- `prospective_loop.leaderboard` har fått avsnittet «Criterion v2» med tellende
  runder (0 nå), diagnostikk for GW8 og syntetiske tropper.
  `synthetic_squads.csv` er bufret per runde som ny fil.
- GW8 som diagnostikk (teller ikke):
  - `refit_20261022` +0,016 MAE per kohortspiller og `season_transfer` +0,039,
    altså begge dårligere. `fpl_ep_next` +0,462.
  - Syntetiske tropper: incumbent 41,85, refit 41,80, season_transfer 41,85 og
    `ep_next` 39,93 poeng i snitt.

## E2: skyggesesong

- `src/shadow_season.py`: `start`, `lock` og `score`.
  - Gjenbruker `season_simulator.best_transfer_plan` (eksakt MILP innenfor
    gratisbytter), `lineup_for_ids` og `autosub_score`.
  - Policyer: `hold`, som ikke bytter, ruller FT og bruker incumbent til
    oppstilling, og hver modell i løypepakken.
  - Priser og prognoser kommer fra løypas låste pakke, altså frosset før
    deadline.
  - Låsen avvises etter deadline og når den finnes fra før. Filene skrives
    aldri over.
- Låst GW10 (FT 2, bank £1,3m):

| Policy | Bytter | Kaptein (id) | Projisert XI+C |
|---|---|---|---:|
| hold | – | 411 | 50,07 |
| incumbent | João Pedro → Barry, Schade → Iwobi | 411 | 52,73 |
| refit_20261031 | João Pedro → Barry, Schade → Wirtz | 411 | 53,53 |
| season_transfer_20261022 | Kostoulas → Evanilson, João Pedro → Barry | 411 | 54,63 |
| crowd_20261022 | João Pedro → Barry, Schade → Tavernier | 411 | 54,82 |

`prospective_loop.auto` (og dermed Lock-knappen) låser nå hver skyggesesong
når løypa har låst runden, og scorer runder når utfallet finnes
(`shadow_rounds`).

Begrensninger: ingen hits og ingen chips ennå. Chips føres som ubrukte, slik at
en senere policy kan spille dem (P2 i fase E). Utgangstroppen er den offentlige
troppen. Bytter du gjør før deadline, ser ikke skyggesesongen.

## E4: modellkort

- `data_quality.model_card` og `GET /api/model-card`. Innhold:
  - produksjonsmodell og -familie;
  - runder vist og tellende etter v1 og v2;
  - ledertavlen med Δ lagpoeng, ukentlig MAE og Q10–Q90-treff;
  - kalibrering (Brier 60+, treff mot 80 %, status for M7);
  - kjente begrensninger;
  - hele datakvalitetsrapporten fra O3.
- Web: `frontend/src/ModelCard.tsx`, ny side i History-gruppen.
- Mobil: `apps/mobile/app/model.tsx` med lenke fra History.
- Typer: `ModelCard` og `DataQuality` i `packages/api-client`.

## Verifisering

```
.venv/bin/python -m unittest discover -s tests   # 206 OK
npm run build --prefix frontend                  # OK
npm run test:e2e:workspace --prefix frontend     # 15 passert, 2 skjermbildetester hoppet over
npm run typecheck:mobile                         # OK
npm run test:mobile                              # 59 OK
```

`apps/mobile/.expo/types/router.d.ts` er generert og ignoreres av git. Den er
oppdatert lokalt med `/model`, og `expo start` lager den på nytt.

## Gjenstår

- GW10 scores ved første `prospective_loop.py auto` etter at fpl-data har
  eksportert GW10. GW11 låses i samme kjøring som løypelåsen.
- v2 får sin første tellende runde ved GW11-låsen.
