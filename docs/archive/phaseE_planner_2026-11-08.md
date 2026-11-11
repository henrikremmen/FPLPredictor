# Fase E: planlegger (P1, P2, P3, P4)

8. november 2026. Gjelder fase E i [planen 06.11](improvement_plan_2026-11-06.md).
GW19-deadline (1.1.2027) er ikke passert, så P2 gjelder første chip-sett.

## Resultat mot akseptkriteriene

| Kriterium | Status | Bevis |
|---|---|---|
| Lovlige planer med chip, benk og VC | Oppfylt | Flerukeplanen validerer hver løsning mot alle begrensninger (som før). Chips, benkplasser og autosub/VC er lagt til. Ekte lag 5139814, 8 GW med chips: 12,7 s, MIP-gap 0,1 %, Bench Boost i GW10. Uten chips: 9,9 s. Med kalender: 23 s. |
| Test for chip-utløp ved GW19 | Oppfylt | `ChipPlanTests.test_chips_expire_after_their_last_gameweek`: med utløp GW5 brukes ingen chip senere. Utløp leses fra `chip_status.expires_after_gw` (19 for første sett). |
| Maks én chip per GW | Oppfylt | `ChipPlanTests.test_triple_captain_on_the_big_week_and_one_chip_per_week` (også høyst én gang per chip). |
| Krav og alternativkostnad | Oppfylt | `RequirementTests`: «selg i GW», «eie innen GW», maks per posisjon og ukjent krav avvist. Kostnaden er planpoeng uten kravet minus med kravet. API-et validerer at påkrevde felter finnes (422). |
| Benk og VC | Oppfylt | `BenchWeightTests`, `BenchBoostTests` og `tests/test_autosub_value.py` (fravær av kaptein gir VC dobbelt og innbytter inn). |

## P1: benkvekt (standard på)

- `fpl_app.BENCH_WEIGHTS = (0.03, 0.12, 0.06, 0.03)` for reservekeeper og
  benk 1–3. Samme verdier ligger i `packages/shared` (`BENCH_WEIGHTS`).
- Flerukeplanen har kontinuerlige benkplass-variabler. Tildelingen er
  integral når tropp og XI er gitt, så det trengs ingen nye binærvariabler.
- Byttemotoren har samme ledd i den eksakte MILP-en (3–5 bytter) og i
  oppramsingen (`_lineup_total_records(..., bench_weights)`).
- Beslutningspoengene inkluderer benken. Forventede XI-poeng
  (`projected_points`, `expected_*`) er fortsatt bare XI og kaptein.
- `season_simulator` og backtestene er uendret.
- Vises og kan justeres:
  - Web: Player preferences → Bench weights, med knapp tilbake til
    standardverdiene.
  - Mobil: Preferanser → Bench weights.
  - Vektene sendes med alle optimeringskall (`bench_weights` i
    `ConstraintsRequest`, 0–1, ellers 422).
  - Planen viser vektene og benken per uke.

## P2: chips i flerukeplanen (av som standard)

- Binær Bench Boost, Triple Captain, Free Hit og Wildcard per GW. Høyst én
  per GW og hver høyst én gang. Bare tilgjengelige chips og bare til og med
  `expires_after_gw`.
- Modellering:
  - **TC**: en ekstra kapteinsandel.
  - **BB**: «XI på 15», altså Σ starter = 11 + 4·BB og begge keeperne. Den
    første formuleringen med egne benkandeler ga 47 s og 7–11 % gap. Den nye
    gir 12,7 s og 0,1 %.
  - **WC**: byttene den uka absorberes og koster ikke, og opptil 15 bytter er
    lov.
  - **FH**: egen éukes tropp (15 spillere, posisjoner, høyst tre per klubb,
    budsjett lik forrige ukes bank og salgsverdi). XI og kaptein velges fra
    den, og hovedtroppen står stille. Kandidatene er topp 25 per posisjon den
    uka (ponytail-merket).
- Chip-kalender (`plan_with_context`): hver chip planen bruker forbys den uka,
  og planen løses på nytt. Forskjellen og nærmeste alternative uke vises.
  Ekte lag: Bench Boost i GW10, alternativ GW12, +0,42 poeng.
- Merk: dagens capture er fra 6.11 og planlegger fra GW10, som allerede er
  spilt. Oppdater prognosen før bruk.
- UI: «Plan chips too» i web og mobil (tregere), chip-merke per uke og kalender.

## P3: autosubs og visekaptein med sannsynligheter

- `src/autosub_value.py`: hver spiller spiller med sannsynlighet
  P(opptreden) × tilgjengelighet. Når han spiller, får han
  forventning / sannsynlighet, så forventningen er uendret.
- 300 trekk med fast seed, scoret med `season_simulator.autosub_score`, den
  samme regelmotoren som i backtestene.
- `GET /api/team/{id}/lineup-value` gir XI-forventning og forventning
  inkludert autosubs og VC. Ekte lag: 50,69 → 53,28 (+2,59). Tar 0,8 s og er
  derfor et eget kall, så vanlige teamkall ikke blir tregere.
- Planen viser det samme per uke (150 trekk), ikke for BB- og FH-uker.
- UI: lagoppstillingen (web og mobil) viser «If someone misses the round».
  Hver planuke viser verdien med autosubs.

## P4: fremtidskrav

- `requirements` i planen:
  - `own_by` (eie spiller innen GW);
  - `sell_in` (selge i GW);
  - `max_club` (høyst N fra klubb);
  - `max_position` (høyst N startende per posisjon).
- Kostnaden er planen uten kravet minus planen med kravet, og vises som
  «costs 1.30 points over N GW».
- UI (web): kravredigering i flerukeplanen med spiller og GW. Mobil har ikke
  kravredigering ennå (se Gjenstår).

## Verifisering

```
.venv/bin/python -m unittest discover -s tests   # 222 OK
npm run build --prefix frontend                  # OK
npm run test:e2e:workspace --prefix frontend     # 16 passert (ny: planner …), 2 skjermbildetester hoppet over
npm run typecheck:mobile                         # OK
npm run test:mobile                              # 60 OK
```

## Gjenstår

- Kravredigering på mobil. Mobil viser kalender, chips og benk, men lager ikke
  egne krav.
- `global_optimum` er fortsatt ofte `False` uten chips også (fantes før
  fasen). Planen viser gap og forbehold.
- FH-kandidatene er begrenset til topp 25 per posisjon.
