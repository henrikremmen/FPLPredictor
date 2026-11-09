# Fase D: utfordrere (O4, O5, M11, M12, M13)

6.–8. november 2026. Gjelder fase D i [planen 06.11](improvement_plan_2026-11-06.md).
Produksjonsmodellen er uendret. Ingenting i `artifacts/models` er endret etter
6.11 kl. 14:00 (`find artifacts/models -newermt …` er tom).

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| Retrospektiv rapport | Oppfylt | Tallene står nedenfor. Sjekkene ligger i hver `challenger.json` (`retrospective_check`, per posisjon og per DC-gruppe eller formkvintil). M13 ligger i `artifacts/m13_team_strengths_20261108/retrospective.csv`. |
| Utfordrere låst fra neste GW med `production_eligible: false` | Oppfylt; låses ved GW11 | `features_v2_20261106` (M11, primær i v2), `top_calibration_20261108` (M12) og `implied_market_20261108` (M13) er registrert med `production_eligible: false` og `active: true`. Neste lås er GW11 (vinduet åpner 20.11 kl. 05:00 UTC). En tørrkjøring scoret GW11-radene fra siste capture med alle registrerte utfordrere: endelige tall og kvantiler. GW10 var låst før de fantes. |
| M13: ingen nivåhopp mellom siste odds-GW og neste | Oppfylt for metoden | Topp-50-snittet for GW10–11 med odds fjernet og implisert er 4,07/4,10, mot 4,04 med faktiske odds og 3,90 uten marked. Fyllet gjenskaper altså nivået. Med implisert marked for GW12–17 er snittet 3,84, 3,90, 3,98, 3,88, 4,04 og 3,96 (uten: 3,84, 3,86, 3,85, 3,85, 3,92, 3,87). Fallet i GW12 er det samme med og uten fyll, så det er kampprogrammet og ikke metoden. |
| M13: sannsynligheter summerer til 1, faktiske odds overskrives ikke | Oppfylt | `tests/test_phase_d.py::ImpliedMarketTest`. På ekte data er største avvik i summen 6·10⁻⁶ (avkortet ved 12 mål), og alle radene for GW10–11 er uendret. |
| Ingen endring i `artifacts/models` | Oppfylt | Se over. |

## O4: tidsriktig manifest

- `fpl_collect.timing(record, published_at)`: hver filpost får `observed_at`,
  `available_at` (begge mottakstidspunktet, som er det vi kan bevise) og
  `published_at`. Den er `None` når kilden ikke oppgir tid.
- Odds: `published_at` er nyeste `last_update` hos bookmakerne
  (`capture_fpl.latest_update`). Odds arkiveres allerede slik de var da
  prognosen ble laget (`odds.json.gz` i hver capture).
- Manifestnivå: `manifest_schema: 2`, `source_version` og `rules_version: fpl-2026-27`.
- Gamle manifester leses som før (testet).
- `fpl-data/collector/fpl_collect.py` er oppdatert lokalt, men **ikke pushet**
  (venter på ditt ja sammen med commit-forslaget).

## O5: roller, DEFCON og pris over tid

- `src/role_history.py` leser alle arkiverte bootstrap-filer (app-captures og
  fpl-data-snapshots) og lagrer en ny versjon når et felt endres:
  straffe-, corner- og frisparkrekkefølge, DC per 90, pris og status.
- `as_of` kobler bare versjoner som er sett *før* et tidspunkt.
- `data/processed/role_history_20261106.csv`: 3 227 versjoner for 671 spillere
  fra 8.9. til 8.11. 11 spillere har byttet straffeposisjon i perioden.
- FPL lar rekkefølgen være tom for spillere uten rolle. Tom betyr derfor
  «ingen rolle» når en bootstrap er sett, og «ukjent» ellers.

## M11: `features_v2_20261106` (primær utfordrer i v2)

- `refit_20261031` pluss en liten korreksjonsmodell (samme mønster som M2, M5
  og M8). Inndata: DC per 90 og DC-andel siste 5, pris (`now_cost` live,
  `price_last1` i trening), om spilleren tar straffer og hvilken plass i
  rekkefølgen, og om spilleren tar dødballer.
- Retrospektiv sjekk på 2026-27 GW1–8 (5 220 rader). Korreksjonen er trent på
  2025-26, der rollene er ukjente, så sjekken ser bare effekten av DC og pris:

| Utvalg | n | MAE før → etter | Bias før → etter (prognose − faktisk) |
|---|---:|---|---|
| Alle | 5 220 | 1,200 → 1,223 | – |
| DEF | 1 706 | 1,400 → 1,425 | −0,218 → −0,119 |
| MID | 2 324 | 1,151 → 1,176 | −0,087 → −0,012 |
| FWD | 618 | 1,170 → 1,189 | −0,041 → +0,005 |
| GK | 572 | 0,830 → 0,847 | −0,030 → +0,009 |
| DC 11+ | 523 | 1,458 → 1,525 | −0,160 → +0,069 |
| DC 8–11 | 587 | 1,795 → 1,835 | −0,221 → −0,046 |

- Korreksjonen fjerner det meste av undervurderingen av forsvarere (F18).
  RMSE går litt ned (2,162 → 2,157), men MAE går opp. For en skjev
  poengfordeling er det vanlig at en forventningsrett korreksjon gir høyere
  MAE. Kriterium v2 måler MAE, så M11 kan godt tape på primærmålet selv om
  biasen er bedre. Det er et ærlig utgangspunkt, ikke et valgt resultat.
- 63,5 % av radene i inneværende sesong har kjent rolle (fra 8.9.). Den
  endelige modellen er trent med dem.

## M12: `top_calibration_20261108`

- Isotonisk kart fra basens prognose til forventet utfall, tilpasset på
  prognoser utenfor utvalget. Lineært kart er rapportert som det enklere
  alternativet.

| Formkvintil | n | Bias base | Isotonisk | Lineær | MAE base / iso / lin |
|---|---:|---:|---:|---:|---|
| Q1 | 911 | −0,052 | −0,065 | −0,045 | 0,265 / 0,251 / 0,269 |
| Q3 | 910 | −0,114 | −0,043 | −0,049 | 1,041 / 1,067 / 1,065 |
| Q4 | 910 | −0,098 | +0,099 | +0,047 | 1,725 / 1,786 / 1,770 |
| Q5 | 910 | −0,270 | −0,056 | −0,043 | 2,483 / 2,543 / 2,538 |
| Alle | 5 220 | – | MAE 1,226, RMSE 2,162 | MAE 1,227, RMSE 2,158 | base 1,200 / 2,162 |

- Toppen komprimeres mindre (F20). Lineært er like godt eller bedre med det
  lille utvalget. Bare isotonisk er registrert for å holde antall utfordrere
  nede.
- Kvintilene er etter form (`points_avg5`), ikke etter prognose.

## M13: `implied_market_20261108`

- `src/team_strengths.py`:
  - Angrep og forsvar per klubb pluss hjemmefordel, med Poisson-tap,
    ridge-straff og 90 dagers halveringstid.
  - Tilpasset odds-implisert xG for spilte kamper (football-data.co.uk, før
    lukking), faktiske mål (halv vekt) og oddsene som allerede ligger i
    låseradene (dobbel vekt).
  - `fill_market` fyller bare manglende `market_*` og merker raden
    `market_source = odds | implied`.
  - Modellen fyller sin egen kopi ved hver prediksjon, så produksjonens
    inndata er urørt.
- Retrospektivt på eldre captures (GW8–9 sett 2–3 runder fram uten odds,
  bare kamper spilt før capturen):

| Utvalg | MAE uten marked | Implisert | Bias uten | Implisert |
|---|---:|---:|---:|---:|
| Alle (667) | 1,207 | 1,200 | −0,097 | −0,101 |
| Topp 100 etter prognose | 2,594 | 2,562 | +0,307 | +0,227 |

- Grunnlaget er tre uavhengige sammenligninger. Det er indikativt; låste
  runder avgjør.

## Verifisering

```
.venv/bin/python -m unittest discover -s tests   # 212 OK
npm run build --prefix frontend                  # OK
npm run test:e2e:workspace --prefix frontend     # 15 passert, 2 skjermbildetester hoppet over
npm run typecheck:mobile                         # OK
npm run test:mobile                              # 59 OK
```

## Gjenstår

- Push av `fpl-data/collector/fpl_collect.py` (O4) venter på ditt ja.
- M13 lagrer observasjoner fra registreringen. Senere resultater kommer først
  med når modellen registreres på nytt (ponytail-merket i koden).
- M11 og M12 er trent på feature-tabellen `retrain_20261031` (GW1–8).
