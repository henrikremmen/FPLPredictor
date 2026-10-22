# Forbedringsplan: data, modell, lagimport og UI

22. oktober 2026. Plan, ikke implementert. Bygger på kartlegging av koden,
`docs/REPO_GUIDE.local.md`, tidligere research i `docs/` og web-research
(kilder nederst). Rekkefølgen er valgt etter verdi per innsats og avhengigheter.

## 1. Funn fra kartleggingen

| # | Funn | Hvor | Konsekvens |
|---|---|---|---|
| F1 | vaastav har stoppet ukentlige oppdateringer etter 2024-25. Nå bare tre oppdateringer per sesong (start, etter januarvinduet, slutt). Lokal checkout: siste commit 2026-08-28 (GW1 2026-27). | `data-source/README.md` | Historisk datagrunnlag for inneværende sesong mangler GW2+. |
| F2 | Treningstabellen `cleaned_merged_seasons_team_aggregated_expanded.csv` ble bygget 21.09 av en notebook og ligger usporet inne i tredjeparts-checkouten. | `notebooks/build_expanded_dataset.ipynb`, `src/build_features.py:80` | Modellen trenes ikke på 2026-27 GW2–7. Manuelt steg, ikke reproduserbart. |
| F3 | Live-innhentingen henter allerede `element-summary` for alle spillere. Den inneholder hele inneværende sesong per kamp (xG, xA, DEFCON, pris, eierskap, overganger). | `src/capture_fpl.py` | Vi har allerede rådata for å lage vaastav-formatet selv. Ingen ny HTTP-kode trengs for selve sesongtabellen. |
| F4 | Ingen scheduler er installert. 30 innhentinger er kjørt manuelt. | `docs/REPO_GUIDE.local.md` | Pre-deadline-snapshots blir tilfeldige, og deadline-sertifiserte tester bygges ikke opp. |
| F5 | Rullerende features nøkles på `(season, player_id)`. FPLs `element`-ID byttes hver sesong, og stabil `code` brukes ikke. | `src/build_features.py:24` | Form nullstilles ved sesongstart. Svakere prognoser i GW1–10. |
| F6 | Bonuskomponenten er en Poisson-modell på `bonus_avg5`, trent på gamle BPS-regler. BPS er endret i 2026/27: CBI gir 1 BPS per tre, ikke per to; ingen −1 for å bli taklet; redninger utenfor boksen er fjernet, og «big chance saves» er nye. | `src/component_models.py:247` | Systematisk bonusfeil per posisjon i år. |
| F7 | Fra 2026/27 låses runden kl. 09:00 UK dagen etter siste kamp. | FPL-regler | Endelige utfall og `data_checked` kommer senere. Innhentingen må vente på flagget. |
| F8 | **Bug:** Webappens `DEFAULT_TEAM` er `…/entry/5139814/event/4`. `parse_entry_reference` returnerer da event 4, og `import_team` henter GW4-picks (`event = requested_event or current_event`). | `frontend/src/App.tsx:26`, `src/fpl_app.py:407` | Standardimport viser en gammel tropp fra GW4. |
| F9 | `manager_analytics` henter allerede picks for alle ferdige runder og alle bytter. Cachen er bare i minnet (TTL 300 s), og UI-et viser bare tabell og 8 GW-chips. Det finnes ingen banevisning bakover i tid. | `src/manager_analytics.py:33,107` | Tidslinjen kan bygges på eksisterende kall. Ferdige runder kan caches permanent. |
| F10 | Webappen har 13 flate menyvalg, ingen URL-ruting (`useState`) og blandet engelsk/norsk. Typene i `frontend/src/types.ts` er parallelle med `packages/api-client`. | `frontend/src/App.tsx:24-40` | Vanskelig å navigere og ingen deep links. Typene glir fra hverandre. |
| F11 | Mobilen har 6 faner med emoji-ikoner og en annen palett enn web. Den mangler sammenligning, preferanser og lagrede planer. | `apps/mobile/app/(tabs)/_layout.tsx`, `src/theme/index.ts` | Over HIG/M3-anbefalingen på 3–5 faner, inkonsistent visuelt og ujevn funksjonsparitet. |
| F12 | FBref mistet Opta-data 20.01.2026. | Web | Ikke bygg på FBref. |

## 2. Data: egen automatisk innhenting (erstatter vaastav)

### D1. Datarepo med GitHub Actions (anbefalt)

Et eget repo, for eksempel `fpl-data`, fungerer som vaastav gjorde, med cron
i GitHub Actions. FPL-Core-Insights kjører FPL-API-innhenting fra Actions to
ganger daglig, så Actions-IP-er fungerer i praksis. Test likevel først med
`workflow_dispatch`.

- **Lett snapshot:** `bootstrap-static/`, `fixtures/`, `event-status/` og
  `team/set-piece-notes/`.
  - Daglig ca. 02:30 UTC, etter prisendringene.
  - Pluss sjekkpunktene T-24t, T-6t og T-1t før deadline. Gjenbruk logikken i
    `deadline_collector.py`: workflow-en kjører hver time, og skriptet avgjør om
    et sjekkpunkt er aktuelt.
- **Full runde-eksport:** når `events[gw].data_checked == true` (se F7).
  - Hent `element-summary/{id}` for alle spillere, `event/{gw}/live/` og
    `fixtures/`.
  - Skriv vaastav-kompatible filer: `data/2026-27/gws/gw{N}.csv`,
    `merged_gw.csv`, `players_raw.csv`, `cleaned_players.csv`, `fixtures.csv`,
    `teams.csv` og `player_idlist.csv`.
  - Legg til `code`-kolonne for stabil spilleridentitet på tvers av sesonger.
- **Gjenbruk:** bruk `capture_endpoint`, manifest og hash fra `capture_fpl.py`.
  vaastavs skript har MIT-lisens og kan gjenbrukes for formatet, med
  attribusjon.
- **Robusthet:**
  - Idempotent kjøring og retry med backoff.
  - Tydelig User-Agent og maks cirka 2 forespørsler per sekund.
  - Feil skal gi rødt workflow-løp eller issue, ikke stille hull.
- **Backfill:** inneværende sesong GW1–7 kan bygges fra dagens
  `element-summary`-historikk (F3).
- **Størrelse:** mål faktisk størrelse per snapshot.
  - Over cirka 200 MB per sesong: legg rå `.json.gz` i Release-assets per
    runde, og la git bare inneholde CSV-er og manifest.
- **Lokal synk:** `data-source/` peker på det nye repoet, eller et lite
  synk-skript. Hold historiske vaastav-sesonger (≤ 2025-26) og egne sesonger
  adskilt, men i samme format.
- **Fallback:** en `launchd`-plist på Macen hvis FPL blokkerer Actions.
  Den kjører bare når maskinen er på.
- **Hemmeligheter:** `ODDS_API_KEY` og `FOOTBALL_DATA_API_KEY` legges som
  Actions-secrets, aldri i repoet.

### D2. Skriptet datasett

Erstatt notebooken med `src/build_dataset.py`, med samme logikk som
`build_expanded_dataset.ipynb`. Output skal til `data/processed/`, ikke inn i
tredjeparts-checkouten. Inndata er vaastav-sesonger pluss egne sesonger.
Kjøres etter hver full runde-eksport.

### D3. Datakontrakt og validering (kjøres før commit eller bruk)

- Ingen dupliserte `(season, element, fixture)`.
- Ingen manglende kickoff.
- Spillerantall er innenfor forventet område.
- Per lag og kamp: summen av `starts` er 11.
- Per lag og kamp: mål = summen av `goals_scored` + motstanders `own_goals`.
- Minutter er mellom 0 og 120.
- Priser er innenfor gyldig område, og prisendring per døgn er ≤ 0,1.
- FPL-korreksjoner av en ferdig runde logges som diff, ikke stille overskriving.
- Nye spillere midt i sesongen håndteres.
- Mapping mellom sesonger skjer via `code`. Tvetydighet feiler i stedet for å
  gjette.

### D4. Nye eller bedre utnyttede API-kall og kilder

| Kilde/kall | Bruk | Prioritet |
|---|---|---|
| `bootstrap-static` → `elements[].code` | Stabil spiller-ID på tvers av sesonger (M2) | Høy |
| `element-summary` → `history_past` | Tidligere sesongtotaler for førsterunder og nye spillere | Høy |
| `event-status/`, `events[].data_checked` | Riktig tidspunkt for endelige utfall | Høy |
| `event/{gw}/live/` (`explain`) og `fixtures[].stats` (bps) | Bonus/BPS-kalibrering under nye regler | Høy |
| `bootstrap` → `ep_next`, `transfers_in_event`, `cost_change_event`, `news_added` | FPLs egen xP som benchmark, crowd-signal og nyhetstidspunkt | Middels |
| `entry/{id}/history`, `entry/{id}/event/{gw}/picks` (`automatic_subs`, `active_chip`, `entry_history`), `entry/{id}/transfers` | Lagtidslinje (T2) | Høy |
| [FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights) | Oppdateres to ganger daglig og dekker 2026-27. Har Opta-lignende `playermatchstats`, ClubElo og cup-/Europakamper koblet til FPL-ID. Brukes til kryssvalidering av egne data, forskningsfeatures og minutter i andre turneringer. Lisensen er uklar (de ber om lenke tilbake), så avklar før appbruk. Hold kilden som separat leverandørkolonne, som Understat. | Middels |
| ClubElo CSV-API (`api.clubelo.com`) | Gratis daglig Elo, som benchmark mot egen `elo_features.py`. Lav, fordi Elo hittil ikke har gitt gevinst. | Lav |
| The Odds API, spillerprops | Finnes allerede. Bruk bare neste runde ved T-24t for å spare kreditter, og evaluer prospektivt. | Middels |
| Understat, football-data.co.uk | Behold | – |
| FBref | Ikke bruk (F12) | – |
| Predikerte startoppstillinger | Ingen gratis pålitelig kilde. Behold manuell minutt-override. | Hopp over |
| `my-team/{id}` | Krever innlogging. Behold korreksjonsskjermen. | Hopp over |

## 3. Modell

Prinsippet ligger fast: ingen automatisk forfremming. Utfordrere vurderes
prospektivt mot låst referanse, som i dag.

- **M1 – Fersk trening:** etter hver `data_checked` bygges en refit-kandidat på
  data som inkluderer 2026-27 (krever D1 og D2). Den evalueres i den
  eksisterende prospektive løypen.
- **M2 – Sesongoverføring via `code`:** forrige sesongs per-90-rater,
  minuttandel og xGI blir features med vekt som avtar over de første N
  rundene. I tillegg flagg for opprykk eller ny spiller, og bruk av
  `history_past`. Forventet størst effekt i GW1–10 (F5).
- **M3 – BPS 2026/27:** mål bonus-kalibrering per posisjon på GW1–7 i år.
  Deretter enten regelversjon som feature, sterkere vekt på 2026-27, eller en
  bonusmodell basert på BPS-komponenter fra `fixtures[].stats`.
- **M4 – Automatisk prospektiv sløyfe:** workflow-en låser referanse og
  utfordrere før hver deadline og evaluerer automatisk etter `data_checked`.
  - Akkumulert ledertavle: MAE, RMSE, låste lagpoeng, kaptein og kalibrering.
  - Forhåndsregistrert kriterium, for eksempel ≥ 8 runder og et
    bootstrap-intervall som ikke krysser 0, før en forfremmingsbeslutning.
  - Dette løser «ingen utfordrer har nok dokumentasjon» over tid.
- **M5 – Crowd- og markedssignal:** kontroller at `transfers_in_event`, endring
  i eierskap og `cost_change_event` faktisk er med i produksjonsmodellen. Test
  FPLs `ep_next` som benchmark og feature.
- **M6 – Ekstern benchmark:** [OpenFPL](https://arxiv.org/abs/2508.09992) har
  åpen kode med posisjonsspesifikke ensembler (RF og XGBoost) på FPL- og
  Understat-data. Kjør den som utfordrer på samme kohort.
- **M7 – Kalibrering:** isotonisk kalibrering av P(start) og P(60+) når det
  finnes ≥ 5–6 prospektive runder med etiketter.
- **M8 – Rotasjon:** spillerens minutter i cup og Europa (FPL-Core-Insights
  eller football-data.org) som feature på spillernivå, ikke bare klubbens
  kamptetthet.

## 4. Lagimport med ID og lagtidslinje

### T1. Bare lag-ID (fikser F8)

- **Web og mobil:** numerisk felt (`inputMode="numeric"`).
  - Limes det inn en URL, trekkes ID-en ut automatisk og `/event/N` ignoreres.
  - Siste ID huskes: `localStorage` på web; mobilen har allerede AsyncStorage.
  - Fjern hardkodet `DEFAULT_TEAM`.
- **Backend:** import bruker alltid `current_event`. URL-støtten beholdes, men
  event-delen påvirker ikke importert tropp. Historiske runder hentes bare via
  tidslinjen.
- **Test:** URL med `/event/4` gir samme tropp som ren ID.

### T2. Tidslinje: bla bakover i tid

- **Endepunkt:** `GET /api/team/{session_id}/timeline` (eller utvid analytics).
  Per GW returneres:
  - 15 picks med posisjon, C/VC, benkrekkefølge og multiplier.
  - `automatic_subs`, `active_chip` og poeng per spiller fra `event/{gw}/live`.
  - Bytter inn og ut med pris, hit-kostnad, bank, lagverdi og OR/GW-rank.
- **Cache:** ferdige runder endres ikke, så de caches permanent på disk
  (`data/local/cache/entry/{id}/gw{N}.json`). Bare den aktive runden har TTL.
- **UI:**
  - Banevisning med GW-stepper (`← GW7 →`): swipe på mobil, piltaster på web.
  - En stripe med alle runder og markører for chip, hit og rank-endring.
  - «Endringer denne runden» med inn/ut-piler og markert diff mot forrige runde.
  - Standardvisning er siste runde.
- **Utvidelse:** samme komponent kan vise flerukeplanen fremover (GW8→15), slik
  at fortid og plan blir én tidslinje.

## 5. UI og UX, web og mobil

- **U1 – Felles designtokens** i `packages/shared`: farger, spacing, radius og
  typografi. Brukes av web via CSS-variabler og av mobil via theme. Én palett.
- **U2 – Web-IA:** 13 menyvalg samles i 5 grupper.
  - *Denne runden:* oversikt, lagoppsett, kaptein.
  - *Bytter og plan:* strategi, bytter, flerukeplan, chips, FH/WC.
  - *Spillere:* marked, sammenlign, preferanser.
  - *Historikk:* analyse, tidslinje.
  - *Mitt lag:* rediger tropp, lagrede planer.
  - Hash-ruting (`location.hash`, ingen ny avhengighet) gir deep links, og
    tilbake-knapp og refresh beholder siden.
- **U3 – Responsiv web:** under 760 px brukes en bunnmeny med de samme 5
  gruppene. Tabeller blir kort eller får sticky første kolonne.
  Berøringsflater er ≥ 44 px.
- **U4 – Mobil:**
  - 6 faner blir 5, for eksempel ved at «Squad» flyttes inn i Oversikt, eller
    at Strategi og Bytter blir «Plan».
  - SVG-ikoner med `react-native-svg` (allerede installert; port ikonene fra
    `frontend/src/icons.tsx`) i stedet for emoji.
  - Expo Router native tabs (Liquid Glass/M3) er fortsatt alfa i SDK 57, så
    vurder dem bare som et valgfritt eksperiment.
  - Pull-to-refresh og skeleton-lasting.
- **U5 – Paritet:** mobilen får tidslinje og spillersammenligning først,
  deretter preferanser (lås/ekskluder) og lagrede planer.
- **U6 – Språk:** ett språk konsekvent (se beslutning 2).
- **U7 – Typer:** webappen bruker `packages/api-client` i stedet for egen
  `types.ts`.
- **U8 – Verifisering:**
  - Playwright-skjermbilder i 390×844 og 1440×900 av hver hovedside, før og
    etter.
  - Skjermbilder fra Expo web eller simulator.
  - WCAG AA-kontrast, fokusrekkefølge og aria-labels.

## 6. Faser og akseptkriterier

| Fase | Innhold | Ferdig når |
|---|---|---|
| 0 | T1 og bugfiks F8 | Test for URL med /event/N = ID. Web og mobil tar ren ID. |
| 1 | D1–D3 og backfill av 2026-27 | Workflow har kjørt grønt minst én gang manuelt. Vaastav-kompatible CSV-er for GW1–7 består D3. `build_dataset.py` gir samme resultat som notebooken på gamle sesonger. |
| 2 | T2 | Endepunkt med tester. Tidslinje på web og mobil. Permanent cache er verifisert (andre kall gir 0 nettverkskall for ferdige GW). |
| 3 | U1–U8 | Skjermbilder i begge størrelser. Alle eksisterende e2e- og mobiltester er grønne. Ingen funksjon er mistet. |
| 4 | M1–M4, deretter M5–M8 | Utfordrere er låst og evaluert automatisk. Ledertavle finnes. Ingen produksjonsbytte uten forhåndsregistrert kriterium. |

Hver fase krever:

- `.venv/bin/python -m unittest discover -s tests`
- `npm run build --prefix frontend`
- `npm run test:e2e:workspace --prefix frontend`
- `npm run typecheck:mobile`
- `npm run test:mobile`

## 7. Beslutninger brukeren må ta

1. **Hvor innhentingen kjører:** GitHub Actions i nytt repo (anbefalt; privat
   eller offentlig) eller `launchd` på Mac.
2. **UI-språk:** norsk eller engelsk.
3. **FPL-Core-Insights:** greit å bruke med attribusjon, eller bare til
   forskning og validering?
4. **Odds-kreditter:** skal spillerprops aktiveres (én runde ved T-24t)?

## 8. Kilder

- vaastav-varsel om stoppet ukentlig oppdatering: `data-source/README.md`
  ([repo](https://github.com/vaastav/Fantasy-Premier-League))
- [FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights)
- [FPL 2026/27-regelendringer (Fantasy Football Scout)](https://www.fantasyfootballscout.co.uk/2026/07/20/fpl-2026-27-5-rule-changes-new-features-announced)
- [FBref mister Opta-data](https://www.theixsports.com/the-ix-soccer/fbrefs-loss-advanced-stats-womens-soccer-data-accessibility/)
- [OpenFPL (arXiv 2508.09992)](https://arxiv.org/abs/2508.09992)
- [FPL API-endepunkter (cheatsheet)](https://glama.ai/mcp/servers/@owen-lacey/fpl-mcp/blob/e9171d6bb4bc00c522d02752962554112a340d30/docs/fpl-api-cheatsheet.md)
- [ClubElo via soccerdata](https://soccerdata.readthedocs.io/en/latest/datasources/ClubElo.html)
- [Expo Router native tabs (SDK 57)](https://docs.expo.dev/versions/v57.0.0/sdk/router/native-tabs/)
- [Apple HIG: tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars)
- [Material 3: navigation bar](https://m3.material.io/components/navigation-bar/guidelines)
- [GitHub Actions: schedule-trigger](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule)
- Tidligere intern research: `docs/product_feature_research_2026.md`,
  `docs/model_research_status.md`, `docs/gw7_review_2026-10-20.md`
