# Goal-prompt for improvement plan 06.11

Kopier teksten i blokken under inn i `/goal` når du vil starte. Fyll inn
beslutningene i punkt 3 først (eller la standardvalgene stå).

```text
Innfør docs/improvement_plan_2026-11-06.md i FPLmodell, fase A til G, i den rekkefølgen planen angir.

1. FØR DU ENDRER NOE
- Les docs/improvement_plan_2026-11-06.md, docs/research_2026-11-06.md, docs/REPO_GUIDE.local.md, docs/prospective_criterion_2026-10-22.md og artifacts/prospective_eval/leaderboard.md.
- Planen ble skrevet 06.11.2026. Kontroller hva som har endret seg siden: dagens dato, gjeldende GW og deadlines (fersk bootstrap), hvilke runder som er låst og evaluert, siste bot-commit i henrikremmen/fpl-data, git status og branch. Skriv en kort statuslinje før du starter.
- Hvis et låsevindu er åpent (neste deadline innen 30 timer) og runden ikke er låst: kjør `.venv/bin/python src/prospective_loop.py auto` først, og igjen når et nytt vindu åpner mens du jobber. Si fra i rapporten.
- Hvis GW19-deadline er passert, flytt P2 (chips) til andre chip-sett (GW20–38) i stedet for å droppe den.
- Jobb på en ny branch fra nåværende branch: improvement-plan-2026-11. Eksisterende ucommittede endringer (f.eks. docs/research_2026-11-06.md) skal ikke overskrives.

2. FASTE REGLER (brudd = stopp)
- Aldri endre artifacts/prospective/* eller data/raw/live_fpl/capture_*. Nye resultater i nye mapper.
- Produksjonsmodellen (artifacts/models/production_market_0erysib7) byttes aldri. Nye modeller og nye tilgjengelighets-/kalibreringspolicyer blir utfordrere med production_eligible: false i den prospektive løypen. Løypa skal aldri skrive til artifacts/models.
- Kriterium v1 endres ikke. Kriterium v2 skrives som ny datert fil og registreres før noe utfall for rundene den gjelder finnes.
- Spør før: nye GitHub-repoer, secrets, aktivering/endring av workflows i fpl-data, nye Python- eller npm-avhengigheter, launchd/cron, eller sletting av data.
- Ingen API-nøkler i kode, logger eller commits.
- Ingen commits under kjøringen. Når alt er ferdig: foreslå commits fordelt per fase og vent på mitt ja.
- UI-tekst på engelsk, konsistent på web og mobil. FPL-Core-Insights kun forskning. Ingen odds-spillerprops.
- Gjenbruk eksisterende kode (capture_fpl.py, fpl_collect.py, data_contract.py, season_simulator.py, multiweek_planner.py, chip_strategy.py, challengers.py, prospective_loop.py, packages/shared tokens og packages/api-client typer) før du skriver nytt. Minste endring som løser problemet.
- Hver data- eller logikkendring får en kjørbar test. FPL-input valideres ved grensen.
- Behold react-native-web, react-dom og @expo/metro-runtime i apps/mobile.

3. BESLUTNINGER (standard hvis ikke endret)
- O2 låseknapp: [standard: banner + knapp som kjører prospective_loop.py auto som bakgrunnsjobb med status; ingen scheduler]
- P1 benkvekter: [standard: på, små vekter etter benkrekkefølge, kan justeres i UI, verdiene vises]
- E1 primær utfordrer i v2: [standard: features_v2 fra M11]
- Hostet backend, xgboost: ikke i denne kjøringen.

4. FASER (akseptkriteriene står i planens del 4)
A Drift: O1 (finn årsaken til at fpl-data stoppet 23.10 via Actions-loggen; fiks i kildene i dette repoet og kopiene i fpl-data; jeg må godkjenne push/workflow-endringer i fpl-data), O2.
B Riktige tall: M9 (kvantiler fra fordeling, tilgjengelighet som blanding; forventede poeng uendret; syntetiske tester fra F16; rapport over endrede Stable/Upside-valg), M10 (kun måling, eventuell ny policy som utfordrer), O3, E3.
C Evaluering: E1 (med styrkeberegning og kohort definert før deadline), E2 (skyggesesong i artifacts/shadow_season/, scoring med autosubs/VC via season_simulator), E4.
D Utfordrere: O4, O5, M11, M12, M13. Retrospektiv sjekk på inneværende sesong, deretter lås fra neste mulige GW. M13 skal ikke overskrive faktiske odds, og kilden skal merkes.
E Planlegger: P1, P2 (chips i MILP frem til halvsesonggrensen), P3, P4.
F UI: U9–U18 og T3. Skjermbilder i 390×844 og 1440×900 før og etter (SCREENSHOT_DIR=... npm --prefix frontend run test:e2e:workspace), samt Expo web for mobil.
G Scenarier: P5, U19, T4.
"Senere"-punktene i planen er utenfor målet.

5. VERIFISERING ETTER HVER FASE (alle må være grønne)
.venv/bin/python -m unittest discover -s tests
npm run build --prefix frontend
npm run test:e2e:workspace --prefix frontend
npm run typecheck:mobile
npm run test:mobile

6. RAPPORTERING
- Én datert rapport per fase i docs/ (samme stil som docs/model_phase_2026-10-22.md): resultat mot akseptkriteriene med bevis, hva som er laget, verifisering og hva som gjenstår.
- Oppdater README.md, docs/handbook.md og docs/REPO_GUIDE.local.md når filer, kommandoer eller UI endres.
- Hvis noe blokkeres av data eller tid (f.eks. kalibrering som trenger flere runder), dokumenter det som blokkert og gå videre til neste tiltak.
- Målet er nådd når fase A–G oppfyller akseptkriteriene eller er dokumentert som blokkert, alle tester er grønne og commit-forslaget er lagt frem.
```
