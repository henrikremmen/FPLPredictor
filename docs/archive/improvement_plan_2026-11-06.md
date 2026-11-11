# Improvement plan 06.11.2026

Plan, ikke implementert. Samler to research-runder fra 6. november 2026:

- Claude: drift, residualanalyse på 2026-27 GW1–7 (utenfor utvalg), oddsdekning,
  kriteriets styrke, planlegger og skjermbilder av alle sider.
- Codex: [research_2026-11-06.md](research_2026-11-06.md) (usikkerhet,
  evaluering, tidsriktige data, UI-hierarki, nye funksjoner).

Bygger videre på [forbedringsplanen 22.10](forbedringsplan_2026-10-22.md)
(fase 0–4 er levert). Tiltak-ID-er fortsetter der den slapp (M9+, U9+).

## 0. Status 6. november

| Hva | Status |
|---|---|
| Produksjonsmodell | Uendret: `artifacts/models/production_market_0erysib7` |
| Løype | GW8 låst og evaluert. **GW9 aldri låst (tapt).** GW10 låst 06.11 kl. 14:09 UTC (`loop_gw10_20261106T140930Z`, 8 modeller, 5 360 rader) |
| Neste lås | GW11, deadline 21.11 kl. 11:00 UTC. Vindu åpner 20.11 kl. 05:00 UTC |
| Kriterium v1 | Tidligst oppfylt GW16 (M1/M2) og GW17 (M5/M6/M8). Se E1 om styrke |
| `fpl-data` | **Ingen bot-commit siden 23.10 kl. 15:07 UTC.** GW8–9-eksport mangler |
| Chips | Første sett utløper før GW19-deadline |

## 1. Faste regler (gjelder alle tiltak)

- Aldri endre `artifacts/prospective/*` eller `data/raw/live_fpl/capture_*`. Nye resultater i nye mapper.
- Produksjonsmodellen byttes aldri automatisk. Nye modeller/justeringer blir
  utfordrere i den prospektive løypen med `production_eligible: false`.
- Kriterium v1 endres ikke. En v2 dateres og registreres før noe utfall den skal dekke finnes.
- Ingen API-nøkler i kode, logger eller commits. Ingen nye repoer, secrets,
  workflows eller nye avhengigheter uten å spørre.
- Egen branch. Ingen commits uten avtale; skill eksisterende ucommittede endringer fra nye.
- Løypa kjøres manuelt (`.venv/bin/python src/prospective_loop.py auto`); ingen launchd/cron.
- UI-språk engelsk. FPL-Core-Insights kun forskning. Ingen odds-spillerprops.
- Hver data-/logikkendring får en kjørbar test. Valider FPL-input ved grensen (D3).
- Gjenbruk eksisterende moduler (`capture_fpl.py`, `fpl_collect.py`,
  `season_simulator.py`, `multiweek_planner.py`, `challengers.py`) før ny kode.
- Oppdater `README.md`, `docs/handbook.md` og `docs/REPO_GUIDE.local.md` når filer eller kommandoer endres.

## 2. Funn

| # | Funn | Bevis | Kilde |
|---|---|---|---|
| F13 | `fpl-data` har stått stille siden 23.10. Daglig snapshot alene skulle gitt én commit per dag | GitHub commit-liste | Claude |
| F14 | GW9 ble ikke låst; ingen påminnelse finnes | `artifacts/prospective/` mangler `loop_gw9_*` | Claude |
| F15 | Kriterium v1 har svært lav styrke. SD for parvis lagpoeng-differanse ≈ 13/runde (66-GW backtest, CI −0,67…5,53). Ved 8 runder er 95 %-halvbredden ≈ 9 poeng/runde | `production_market_0erysib7/settings.json` | Claude |
| F16 | Kvantiler summeres over kamper og ganges med tilgjengelighet. Kvantilen av en sum er ikke summen av kvantiler; blanding ≠ skalering (50 % tilgjengelig, 10 eller 0 poeng: Q90 er 10, appen gir 5). Stable/Upside bruker tallene | `src/capture_fpl.py:385`, `src/fpl_app.py:231`, `:310-314`, `:334-342` | Codex, bekreftet |
| F17 | Mulig dobbelt skadefradrag: modellen predikerer P(0 min), appen ganger så med tilgjengelighet. Støttes av samlet undervurdering +0,115 (2026-27 GW1–7) og at justeringen økte undervurdering 0,093 → 0,202 i GW6 | residualanalyse; `docs/model_research_status.md` | Codex + Claude |
| F18 | DEFCON-features finnes i feature-tabellen, men brukes ikke i produksjon. Faste DEF (≥60 min snitt) undervurderes monotont med DC-rate: +0,14 / +0,28 / +0,43 / +0,52 poeng per kamp | `data/processed/features_20261022`, `src/model_experiments.py:28` | Claude |
| F19 | Pris er ikke feature. 5,5–6,0m undervurdert +0,85 | samme analyse | Claude |
| F20 | Toppen komprimeres: øverste prognose-kvintil 4,31 mot faktisk 4,79 (påvirker kaptein) | samme analyse | Claude |
| F21 | Straffe-/dødballroller brukes ikke. Straffetakere overvurdert −0,87 (n=32, indikativt). `penalties_order` og `set_piece_notes` hentes allerede | `src/capture_fpl.py:188` | Claude |
| F22 | Markedsfeatures finnes bare for de neste ~2 rundene (GW10–11). GW12–17 faller til modell uten marked; topp-50-snitt faller 4,04 → 3,85 og spredningen krymper. Planleggeren undervurderer senere kampprogram | `horizon_fixture_forecast.csv`, `MarketFallbackBlend` | Claude |
| F23 | Benken har vekt 0 i flerukeplanen; autosubs/VC prises ikke | `src/multiweek_planner.py:155-160` | Claude + Codex |
| F24 | Chips er ikke i flerukeplanen; chipmodulen ser 3 runder | `src/chip_strategy.py:5` | Claude |
| F25 | Robusthet/sensitivitet og egne spilletidsantakelser (P0 i egen research) er ikke laget | `docs/product_feature_research_2026.md` | Claude + Codex |
| F26 | Strategy, Transfers og Multiweek åpner med tom «Create plan». Hver side bruker ~400 px på status, horisont og stor H1 før innhold. Mobil-web har to navigasjoner. Ingen fixture-ticker | skjermbilder 1440/390 | Claude + Codex |
| F27 | To desimaler overalt; `PlayerRow` prioriterer `decision_points` mens oversikten bruker generelle poengetiketter; lagrede planer vises som nøkkel/verdi | `frontend/src/App.tsx`, `Workspace.tsx` | Codex |
| F28 | Evaluering velger ny 100m-tropp hver runde; byttestrategi, bank, FT og chips måles ikke | `src/freeze_decisions.py:74` | Codex |
| F29 | Manifest mangler `published_at`/`available_at`; ingen datakvalitetsoversikt | `src/capture_fpl.py` manifest | Codex |
| F30 | `fpl-data`-commits har forfatter `youremail@example.com` | GitHub | Claude |

## 3. Tiltak

### O – Drift og data

- **O1 Reparer `fpl-data`.** Finn årsaken (Actions-logg: kontraktsfeil ved GW8-eksport,
  push-konflikt, deaktivert cron). Fiks, kjør backfill av GW8+ og bygg datasettet på nytt.
  Rødt løp skal varsle (issue eller feilet jobb), ikke gi stille hull. Rett git-forfatter (F30).
  *Ferdig når:* bot-commits igjen daglig, CSV-er for alle `data_checked` runder består D3.
- **O2 Låsevindu i appen.** `GET /api/forecast/status` (eller ny `/api/loop/status`) returnerer
  neste deadline, om låsevinduet (≤30 t) er åpent, og om runden er låst. Banner i web og mobil:
  «Lock window open for GW N – lock now», med knapp som kjører `prospective_loop.py auto` som
  bakgrunnsjobb med status. Fortsatt manuelt; ingen scheduler.
  *Ferdig når:* test for åpent/lukket/låst vindu; dobbeltlåsing avvises (finnes allerede i løypa).
- **O3 Datakvalitetskort.** Siste vellykkede snapshot per kilde, andel kamper med odds per
  horisont-GW, ID-treff (Understat/code), andel prognoser uten marked, manglende låste runder,
  siste evaluerte runde. Internt i API; kort versjon i UI med beslutningskonsekvens.
- **O4 Tidsriktig manifest.** Legg `observed_at` (finnes), `published_at` når kjent,
  `available_at`, `source_version`, `rules_version` til nye manifester. Ukjent = ukjent.
  Arkiver odds slik de var ved prognosetid. Gamle manifester leses fortsatt.
- **O5 Bruk data vi allerede henter:** `penalties_order`, `corners_and_indirect_freekicks_order`,
  `direct_freekicks_order`, `set_piece_notes`, `defensive_contribution*`, pris. Historiser rollebytter. (Mater M11.)

### E – Evaluering

- **E1 Kriterium v2** (ny datert fil `docs/prospective_criterion_v2_<dato>.md`, v1 urørt).
  Gjelder runder låst etter registrering.
  - Primær: parvis feil per spiller (MAE og CRPS/pinball fra kvantiler) på en kohort definert
    **før deadline** (eide spillere i referansetropper, kapteinskandidater, topp-N etter
    prognose, spillere med P(start) ≥ terskel), bootstrap blokket per runde.
  - Sekundær: beslutningsmål fra E2 og syntetiske tropper (flere hundre lovlige tropper trukket
    fra eierskap; hver modell velger XI og kaptein).
  - Korriger for mange utfordrere (f.eks. Holm eller én forhåndsvalgt primær utfordrer).
  - Styrkeberegning i dokumentet: forventet antall runder for en realistisk gevinst.
- **E2 Skyggesesong.** Fra brukerens faktiske tropp ved GW N: hver policy (hold/rull, referanse,
  utfordrer) fører tropp, bank, kjøpspris, salgspris, FT og chips videre runde for runde, låst
  før deadline og scoret med autosubs/VC (gjenbruk `season_simulator.py`). Egne mapper under
  `artifacts/shadow_season/`.
- **E3 Flere mål i evalueringen:** Brier/log loss og kalibreringskurver for P(spiller) og P(60+),
  intervalltreff og bredde for Q10–Q90, bias per posisjon og DC-gruppe, T-24t vs T-6t vs siste
  snapshot. Antall runder og usikkerhet vises alltid sammen med resultat.
- **E4 Modellkort i UI.** Under History: tellende runder, ledertavle, kalibrering, kjente
  begrensninger, datadekning (fra O3). Ingen påstand om overlegenhet uten kriteriet.

### M – Modell (alle som utfordrere eller app-justeringer målt før bruk)

- **M9 Riktig usikkerhet.** Skill additive forventninger fra fordelinger i datakontrakten.
  Beregn GW- og horisontkvantiler fra en fordeling (simulering per kamp eller diskret
  fordeling: blanding av fravær/innhopp/start × poeng gitt bånd), og bruk blanding for
  tilgjengelighet, ikke skalering. Forventede poeng (`recommended_points`) uendret.
  *Ferdig når:* syntetiske eksempler fra F16 består; rapport over hvilke Stable/Upside-valg
  som endres på dagens snapshot; Balanced uendret.
- **M10 Dobbelt skadefradrag.** Mål bias for spillere med flagg/`chance_of_playing` < 100 med og
  uten appens tilgjengelighetsfaktor på GW6–siste evaluerte runde. Endring av policy låses som
  utfordrer-variant i løypa (som `availability_*` i dag), ikke direkte i produksjon.
- **M11 Utfordrer `features_v2`:** M1-refit + `defensive_contribution90_last5`,
  `defensive_contribution_rate5`, `price_last1`, straffe-/dødballrolle (O5).
  Retrospektiv sjekk per posisjon og DC-gruppe, deretter lås fra neste mulige GW.
- **M12 Toppkalibrering.** Utfordrer med monoton (isotonisk eller lineær på rang) kalibrering av
  punktprognosen, trent på data før evalueringsrundene. Sammenlign med enklere lineær
  kalibrering (lite utvalg).
- **M13 Lagstyrker fra odds for hele horisonten.** Tilpass angrep/forsvar per lag (Poisson,
  hjemmefordel, tidsvekting) til alle tilgjengelige h2h/totals-odds pluss resultater (scipy,
  ingen ny avhengighet). Fyll `market_*`-features for kamper uten odds. Merk kilde
  (`market_source = odds|implied`). Utfordrer først; mål effekt på GW+2…+8.
  *Ferdig når:* ingen nivåhopp mellom siste odds-GW og neste (topp-50-snitt), test for
  sannsynligheter som summerer til 1 og at faktiske odds ikke overskrives.
- **M14 (senere) Sammenhengende spilletidsmodell:** fravær / innhopp / start <60 / start 60+,
  med cupbelastning, hviledager, nylig skade, konkurranse om plassen, trenerbytte.
  Forbedre eksisterende `cup_minutes`- og `season_transfer`-utfordrere fremfor nye parallelle.
- **M15 (senere) Felles kampsimulering:** spillere fra samme lag deler målsjanser og clean sheet.
  Trengs for lagintervaller, benkverdi og miniliga, ikke for forventning.

### P – Planlegger og beslutninger

- **P1 Benkvekt** i `multiweek_planner.py` og byttemotoren: benkspillere får liten vekt etter
  rekkefølge (konfigurerbar, vist i UI). Rask førsteversjon av F23.
- **P2 Chips i flerukeplanen** frem til halvsesonggrensen: binære BB/TC/FH/WC-variabler per GW,
  maks én chip per GW, tilgjengelighet fra `chip_status`, utløp ved GW19 (første sett).
  Vis «chip-kalender» med nærmeste alternativ og forskjell i poeng.
  Haster: verdien faller for hver runde før GW19.
- **P3 Autosubs og visekaptein med sannsynligheter:** gjenbruk regelmotoren i
  `season_simulator.py` til å evaluere toppkandidater fra solveren under scenarioer
  (0 minutter, innhopp). Vis XI-forventning og forventning inkl. benk/VC hver for seg.
- **P4 Fremtidskrav:** «kjøp X innen GW N», «selg Y i GW N», maks spillere per klubb/posisjon,
  med alternativkostnad («dette kravet koster 1,3 poeng over 4 GW»).
- **P5 Scenarier og robusthet:**
  - Plan A/B mot å holde: samme horisont, netto xP, hits, bank, FT, forskjellige spillere.
  - «Hva hvis han benkes?»: overstyr P(start)/minutter per spiller og kamp, merket
    «Your assumptions», med reset. Lagret lokalt, aldri i treningsdata.
  - Bruddpunkt: hvilken antakelse som snur anbefalingen («selg hvis P(start) < 62 %»).
  - Robusthet: generer noen gode kandidater med dagens solver, evaluer på samme 20–100
    scenarioer (seed lagret). Første rundes handling er lik på tvers av scenarioer.
    Formuler som «valgt i X % av scenarioene», ikke sannsynlighet for å vinne.
- **P6 (senere) Kostnaden ved å vente:** når en prisendring gjør en plan umulig eller dyrere.

### U – UI (web og mobil, engelsk)

- **U9 Beslutningskort øverst på Overview:** GW, deadline i lokal tid, datastatus;
  anbefaling (rull/bytt + kort hvorfor), kaptein og nærmeste alternativ, viktig nyhet,
  chip-hint, robusthetsmerke når P5 finnes. Knapper til sammenligning og lagoppstilling.
- **U10 Forhåndsberegning:** strategi beregnes i bakgrunnen ved import/refresh og caches;
  sider viser svar, ikke tom «Create plan». Gammelt resultat merkes utdatert ved endret input.
- **U11 Kompakt header:** én statuslinje (data- og prognosetid, detaljer på trykk) og horisont i
  toppfeltet. Mindre H1 på undersider.
- **U12 Tall:** én desimal som standard. Forventede poeng som hovedtall; risikoprofilens score
  ved siden av med forklaring, konsekvent på alle sider.
- **U13 Lagrede planer som kort:** bytter, hits, bank, FT, forskjell mot å holde.
- **U14 Spillerpanel** som bunnark på mobil: sammendrag først, tabeller og kilder foldes ut.
- **U15 Import:** vis når troppen sist var offentlig, rask korrigering av bank/FT/spillere.
- **U16 Fixture-ticker:** 3–8 GW-kolonner med motstander, H/B, xP, P(start), blanke/doble runder;
  for egen tropp og markedet.
- **U17 Én navigasjon på smal skjerm** (fjern topp-pillene eller bunnmenyen under 760 px).
- **U18 Tilgjengelighet:** ikke bare rød/grønn; tastatur, fokus etter dialog, zoom, 44 px mål.
- **U19 Beslutningsjournal:** frys råd, alternativer, brukerens valg og kildetid før deadline;
  vis utfall etterpå. Deler lagring med E2.

### T – Teknikk

- **T3 Cache-nøkkel** = prognoseversjon + tropp + bank + FT + horisont + preferanser + scenarioer.
- **T4 Felles regelversjon** for scoring, planlegger og backtest (chips, FT, salgspris, DGW,
  autosubs), med tester på regelgrenser.
- **T5 Del opp `frontend/src/App.tsx` og flytt logikk ut av `src/fpl_app.py`** bare der filene
  uansett endres. Ingen omskriving.
- **T6 (senere) Jobbkø** med jobb-ID, fremdrift og deduplisering for refresh, lås og scenarioer.

### Senere / krever beslutning

- Hostet backend (Dockerfile finnes) så mobilen virker utenfor hjemme-Wi-Fi.
- Miniliga-simulator (krever M15). Relevante varsler (push/e-post). Live kampdag (lav: offisiell app dekker mye).
- Originale OpenFPL (krever `xgboost`). Betalte historiske odds.

## 4. Faser og akseptkriterier

| Fase | Innhold | Ferdig når |
|---|---|---|
| A – Drift (før 20.11) | O1, O2 | `fpl-data` committer igjen; banner + låseknapp testet; README/handbook oppdatert |
| B – Riktige tall | M9, M10 (måling), O3, E3 | Syntetiske tester for kvantiler består; rapport over endrede risikovalg; datakvalitet i API; nye mål i evalueringen |
| C – Evaluering | E1, E2, E4 | v2 registrert før neste lås; skyggesesong låser og scorer én runde ende til ende; modellkort i UI |
| D – Utfordrere | M11, M12, M13, O4, O5 | Retrospektiv rapport; utfordrere låst fra neste GW med `production_eligible: false`; ingen endring i `artifacts/models` |
| E – Planlegger | P1, P2, P3, P4 | Lovlige planer med chip/benk/VC; tester for chip-utløp ved GW19, maks én chip per GW, krav og alternativkostnad |
| F – UI | U9–U18, T3 | Skjermbilder 390×844 og 1440×900 før/etter; alle e2e og mobiltester grønne; ingen funksjon mistet |
| G – Scenarier | P5, U19, T4 | Plan A/B, overstyring med reset, bruddpunkt og robusthet med lagret seed; journal fryses før deadline |
| Senere | M14, M15, P6, T6, resten | Egen plan |

Hver fase krever:

```
.venv/bin/python -m unittest discover -s tests
npm run build --prefix frontend
npm run test:e2e:workspace --prefix frontend
npm run typecheck:mobile
npm run test:mobile
```

## 5. Beslutninger brukeren må ta

1. O2: skal låseknappen i appen kunne kjøre løypa (ellers bare banner med kommando)?
2. P1: standard benkvekter, eller bare som valg av?
3. E1: hvilken utfordrer er primær i v2 (anbefalt: `features_v2` fra M11)?
4. Hostet backend og eventuelle nye avhengigheter (`xgboost`): ikke nå med mindre du sier ja.
