# FPL-modell og beslutningsapp

Prosjektet trener en modell for neste Gameweek-poeng og har en lokal React-app
som gjør prognosene om til FPL-valg. Appen er skrivebeskyttet mot FPL: den kan
anbefale valg, men logger aldri inn eller utfører dem.

## Start webgrensesnittet

Fra prosjektmappen:

```bash
.venv/bin/python -m pip install -r requirements.txt
npm install --prefix frontend
.venv/bin/python run_app.py
```

Dette krever Node.js 20 eller nyere. Nettleseren åpner normalt automatisk på
`http://127.0.0.1:5173`. API-dokumentasjon finnes på
`http://127.0.0.1:8000/docs`. Laglenken din
er fylt inn som eksempel; velg horisont og risikoprofil og trykk **Last inn
laget**.

Grensesnittet har faner for:

- tropp, priser, motstandere og modellpoeng
- manageranalyse med sesongkurve, historiske Gameweek-tropper, poengkilder,
  kaptein, benk, transfersving og utvikling i overall rank
- miniligaanalyse med tabell, historisk ligarank, gap til leder, liga-EO,
  differensialer og rank-trusler
- global benchmark mot FPL-snitt, samlet eierskap og et merket stratifisert
  utvalg av offentlige lag fra rank 1–10 000
- anbefalt startellever, formasjon, kaptein, visekaptein og benk
- ett til fem bytter, enten fritt optimert eller med 1–5 bestemte spillere
  valgt ut, med en eksakt global MILP-plan og automatisk poengtrekk
- flerukersplan for 1–8 GW med bytter, rullering av inntil fem gratisbytter,
  startellever og kaptein i hver runde
- filtrerbare kjøpskandidater og rangerte salgskandidater
- kortsiktig chipanalyse for Wildcard, Free Hit, Triple Captain, Bench Boost og
  sekvensen Wildcard → Bench Boost
- egne Free Hit-lag for hver kjent Gameweek og et langsiktig Wildcard-lag med
  XI, benk, kaptein og planlagte senere bytter

Bank og gratisbytter kan korrigeres i sidepanelet dersom de offentlige
estimatene avviker fra tallene inne i FPL. Knappen **Oppdater prognosen** henter
et nytt offentlig snapshot; dette kan ta rundt ett minutt. Appen logger aldri
inn og kan ikke utføre bytter.

Når FPL skifter til en ny Gameweek før appen har en prognose for den, kan
**Oppdater prognose** også brukes før laget er lastet inn. Etter innhentingen
lastes laget automatisk med den nye runden.

Offentlige lagdata viser heller ikke bytter som er gjort etter siste deadline.
Bruk derfor fanen **Korriger lag** når appen viser en gammel tropp:

- **Allerede gjort** erstatter spillere og lagrer faktisk bank og antall
  gratisbytter fra FPL, uten å belaste byttene på nytt.
- **Nye bytter** simulerer nye endringer fra appens aktive lag og beregner bank,
  gjenværende gratisbytter og eventuelt poengtrekk.

Den korrigerte troppen brukes av laguttak, transferforslag, flerukersplan,
strategisenter, Free Hit og Wildcard. Den lagres lokalt for samme FPL-ID og
Gameweek, overlever prognoseoppdateringer og kan fjernes med **Tilbakestill til
FPL**. Appen endrer fortsatt aldri det virkelige FPL-laget.

Fanen **Analyse** bruker bare offentlige data. Velg Gameweek for å se den
låste 15-mannstroppen, hvem som ga gevinst eller tap mot miniligaens effective
ownership, og hvilke benk-/kapteinsvalg som slo ut. Under **Risiko &
differensialer** kombineres flerukersprognosen med liga-EO og EO i et
topprank-utvalg. Metode, formler og begrensninger er dokumentert i
`docs/manager_analytics_research_2026.md`.

## Prosjektstruktur og rotkommandoer

Repoet er et lite monorepo. `src/` (Python-modell og FastAPI-bro) og
`frontend/` (React-webapp) er de opprinnelige delene og er uendret i
oppsettet sitt. Mobilappen legger til:

```
apps/mobile/          Expo/React Native-app (TypeScript, Expo Router)
packages/api-client/  Typet fetch-klient mot src/api.py + typer
packages/shared/      Delte konstanter og formattering (web + mobil)
```

`packages/*` og `apps/*` er npm-workspaces (rot-`package.json`).
`frontend/` er bevisst **ikke** en del av workspacet — den installeres og
kjøres akkurat som før, uavhengig av mobilappen, slik at ingenting i den
endret seg.

Installer alt du trenger for mobil/monorepo-delen fra prosjektroten:

```bash
npm install
```

Deretter har roten noen få hjelpekommandoer (se `package.json`):

```bash
npm run backend        # start API-et på 127.0.0.1 (samme som run_app.py alene)
npm run backend:lan    # start API-et på 0.0.0.0, for en fysisk iPhone på samme Wi-Fi
npm run web            # start React-webappen (frontend/)
npm run mobile         # start Expo dev-serveren for apps/mobile
npm run mobile:ios     # start Expo og åpne iOS-simulatoren
npm run test:backend   # kjør hele Python-testsuiten
npm run test:mobile    # kjør mobilappens Jest-tester
npm run typecheck:mobile
```

Disse er tynne wrappere rundt de samme kommandoene som er dokumentert lenger
ned (`.venv/bin/python run_app.py`, `npm --prefix frontend run dev`,
`npx expo start` i `apps/mobile/`) — bruk enten roten eller de underliggende
kommandoene, de gjør det samme.

## Mobilapp (Expo/React Native)

`apps/mobile` er en ekte native React Native-app (ikke en WebView rundt
webappen) bygget med Expo, TypeScript og Expo Router. Den bruker samme
backend som webappen (`src/api.py`) via `packages/api-client` — **all**
beregning (budsjett, salgspris, posisjoner, klubbgrense, gratisbytter, hits,
MILP-optimering) skjer på serveren, appen viser bare resultatet. Den lagrer
FPL-ID, horisont, risikoprofil og markedsfiltre lokalt på telefonen
(`AsyncStorage`) og har ingen brukerkonto i denne versjonen.

### Expo-serveren vs. FastAPI-backenden

To separate ting kjører samtidig når du utvikler:

- **FastAPI-backenden** (`src/api.py`, port 8000) gjør selve jobben: henter
  FPL-data, kjører modellen, optimerer bytter. Både webappen og mobilappen
  er rene klienter mot denne.
- **Expo-serveren** (`npx expo start`) er kun et utviklingsverktøy: den
  bundler JavaScript/TypeScript-koden til mobilappen og serverer den til
  Expo Go, en simulator eller en development build over samme Wi-Fi/USB. Den
  finnes ikke i en ferdig App Store-bygd app — der er koden allerede bundlet
  inn i selve appen.

Mobilappen snakker **aldri** til Expo-serveren for FPL-data — kun til
`EXPO_PUBLIC_API_URL`.

### Kom i gang lokalt (simulator, samme Mac som backend)

```bash
cp apps/mobile/.env.example apps/mobile/.env   # EXPO_PUBLIC_API_URL=http://127.0.0.1:8000
.venv/bin/python run_app.py                     # start backend i ett terminalvindu
cd apps/mobile && npx expo start                # start Expo i et annet
```

Trykk `i` for iOS-simulator (krever Xcode) eller `w` for web-forhåndsvisning.
iOS-simulatoren kan nå `127.0.0.1` direkte fordi den deler nettverk med
Mac-en.

### Fysisk iPhone på samme Wi-Fi

Simulatoren og en fysisk iPhone er ikke det samme nettverket som
`127.0.0.1` — backenden må lytte på alle grensesnitt, og appen må pekes på
maskinens faktiske IP:

```bash
npm run backend:lan
# eller: FPL_API_HOST=0.0.0.0 .venv/bin/python run_app.py
```

Dette skriver ut noe slikt:

```
Backend lytter på alle nettverk (0.0.0.0:8000).
Fra en iPhone på samme Wi-Fi, sett apps/mobile/.env til EXPO_PUBLIC_API_URL=http://192.168.1.23:8000
```

Kopier den `EXPO_PUBLIC_API_URL`-linjen inn i `apps/mobile/.env`, start Expo
på nytt, og åpne appen i **Expo Go** (App Store) ved å skanne QR-koden Expo
viser i terminalen — telefonen og Mac-en må være på samme Wi-Fi, og
macOS-brannmuren kan be om tillatelse for `python`/`uvicorn` første gang.

### Development build

Expo Go dekker det aller meste, men støtter ikke alle native moduler i et
fremtidig oppsett. En development build er den anbefalte hovedløsningen for
videre arbeid:

```bash
cd apps/mobile
eas build --profile development --platform ios
```

Dette **krever en Apple-konto og en innlogget `eas`-CLI**
(`eas login`) — se `docs/mobile/app-store-checklist.md` for hele kjeden fram
til TestFlight og App Store. Uten Apple-konto kan du fortsatt utvikle og
teste fullt ut via Expo Go eller iOS-simulatoren.

### TestFlight og produksjons-API

TestFlight-testere er ikke på ditt lokale Wi-Fi, så en `preview`- eller
`production`-bygd app trenger en offentlig HTTPS-backend (se
`docs/deploy.md`). Adressen settes **per EAS-profil**, ikke i koden — rediger
`env.EXPO_PUBLIC_API_URL` for riktig profil i `apps/mobile/eas.json`, ikke
`apps/mobile/.env` (som kun brukes lokalt av `expo start`).

```bash
eas build --profile preview --platform ios     # intern testing
eas build --profile production --platform ios  # App Store-innsending
eas submit --profile production --platform ios
```

Full sjekkliste, inkludert hvilke steg som krever Apple-konto, hosting eller
betaling: `docs/mobile/app-store-checklist.md`. Personvernerklæring,
support-side-utkast og App Privacy-svar: `docs/mobile/`.

### Mobiltester og kvalitetsporter

```bash
cd apps/mobile
npm run typecheck     # tsc --noEmit
npm run lint          # expo lint
npm test              # jest (jest-expo)
npx expo-doctor        # SDK/avhengighets-/metro-konfig-sjekker
npx expo export --platform ios   # verifiserer at appen faktisk bundler
```

## Alternativ: terminalappen

Terminalversjonen er fortsatt tilgjengelig:

```bash
.venv/bin/python src/fpl_app.py "https://fantasy.premierleague.com/en/entry/5139814/event/4"
```

Den importerer de 15 spillerne fra den offentlige laglenken og viser en meny
for:

1. lagoversikt med modellpoeng, priser og neste motstander
2. startellever, formasjon, kaptein, visekaptein og benkerekkefølge
3. beste lovlige enkeltbytter
4. beste lovlige flerbytter
5. kjøpskandidater
6. salgskandidater
7. global flerukersplan

Den nyeste prognosen kan hentes og fryses før appen åpnes:

```bash
.venv/bin/python src/fpl_app.py "5139814" --refresh
```

Dette henter offentlig FPL-data for alle spillere og kan ta rundt ett minutt.
Hvis bare modellen er endret, kan siste komplette råsnapshot gjenbrukes uten
nye API-kall:

```bash
.venv/bin/python src/capture_fpl.py --rescore-latest
```

Liveprognosen bruker en beslutningsvoktet produksjonsartefakt: poengmotoren må
både passere vanlige prediksjonsporter og en historisk FPL-optimering med
budsjett, posisjoner, klubbgrense, startellever og kaptein. P(60+)-modellen
evalueres og refittes separat, slik at den ikke bestemmer poengrangeringen.

## Direkte kommandoer

Menyen kan hoppes over, for eksempel:

```bash
.venv/bin/python src/fpl_app.py "5139814" --action lineup
.venv/bin/python src/fpl_app.py "5139814" --action transfers --max-transfers 5
.venv/bin/python src/fpl_app.py "5139814" --action targets --position MID --max-price 7.0
.venv/bin/python src/fpl_app.py "5139814" --action sells
.venv/bin/python src/fpl_app.py "5139814" --horizon 3 --action transfers --max-transfers 5
.venv/bin/python src/fpl_app.py "5139814" --horizon 3 --action transfers --risk-profile stable
.venv/bin/python src/fpl_app.py "5139814" --horizon 8 --action plan
.venv/bin/python src/fpl_app.py "5139814" --action lineup --risk-profile upside
```

`--horizon 2` til `--horizon 8` summerer nåværende prognoser over flere
Gameweeks for kjøp og salg. Fanen **Flerukersplan** optimerer hele sekvensen av
tropp, bytter, startellever og kaptein. Vanlig **Laguttak** gjelder fortsatt
bare neste Gameweek. Flerukersfilen opprettes av `--refresh`; eldre snapshots
med bare tre runder må derfor oppdateres før en lengre horisont kan velges.

Risikoprofilene endrer beslutningsscore, ikke modellens forventede poeng:

- `balanced` bruker forventede poeng og er standard
- `stable` trekker fra `0,1 × (Q90−Q10)` og foretrekker smalere modellspenn
- `upside` bruker `0,7 × forventning + 0,3 × Q90` og søker en høyere øvre hale

`stable` slo balanced med 85 poeng over de to valideringssesongene og 20 poeng
i 2025–26-testen. `upside` vant 64 poeng i validering, men tapte 28 i testen;
der økte 90-persentilen fra 76,0 til 79,8 samtidig som variasjonen steg.
Profilene er derfor valgfrie nyttefunksjoner, ikke nye forventede poeng eller
garantier om risiko. En separat sekvensiell transferkontroll er beskrevet under
modellkommandoene.

## Hva beslutningslaget validerer

- 15 spillere med 2 keepere, 5 forsvarere, 5 midtbanespillere og 3 spisser
- lovlig startellever: 1 keeper, 3–5 forsvarere, 2–5 midtbanespillere og 1–3 spisser
- inn- og utgående spiller har samme posisjon
- kjøp holder seg innenfor bank + estimert salgspris
- maksimalt tre spillere fra samme klubb
- minus fire poeng per bytte utover estimerte gratisbytter

Enkeltbyttesøket vurderer hele spillermarkedet. For to bytter løses topplanen
globalt med en flerukers MILP, mens appen også viser praktiske reserveplaner.
For tre til fem bytter vises den eksakte globale planen over hele markedet.

Reglene er basert på [FPLs offisielle spilleregler](https://fantasy.premierleague.com/help/rules)
og Premier Leagues forklaring av [bytter og salgspris](https://www.premierleague.com/en/news/2174907).

## Viktige begrensninger

- Forslagene rangeres på modellens poeng for **neste Gameweek**, ikke en
  flerukershorisont, med mindre `--horizon 2` til `--horizon 8` velges.
- En offentlig laglenke gir ikke eksakt salgspris eller saldoen av gratisbytter.
  Appen rekonstruerer kjøpspris fra offentlig historikk, bruker FPLs prisregel og
  estimerer gratisbytter fra laghistorikken. Kontroller disse to tallene i FPL før
  du bekrefter et bytte.
- Modellpoeng justeres ned ved et kjent `chance_of_playing_next_round`-flagg, men
  modellen inneholder ikke en full nyhets- eller skadeanalyse.
- Den eksisterende modellen er eksperimentell og er trent med historiske
  pre-fixture-features. Den er ikke en garanti for faktiske poeng.
- Appen logger aldri inn og utfører aldri endringer i FPL-laget.
- Flerukersplanen bruker dagens kjøps- og salgspriser som konstante gjennom
  horisonten. Kjør planen på nytt etter hver deadline og prisendring.

## Deadline-snapshots og valgfrie datakilder

`capture_fpl.py` fryser nå flere offisielle pre-deadline-felt: status og
spillesjanse, pris-/transfertrend, dødballrekkefølge, lagstyrke,
forsvarsbidrag, CBI, taklinger, gjenvinninger, kort, bonus og xG/xA/xGI/xGC.
Råresponsene hashes og lagres med mottakstid, slik at senere trening kan bevise
hva som faktisk var kjent før deadline.

Standardoppsettet er manuell innhenting. Knappen **Oppdater prognose** i
webappen, eller `--refresh` i kommandolinjeappen, henter FPL-data og alle
konfigurerte valgfrie API-kilder før den lager en ny frosset prognose:

```bash
.venv/bin/python src/fpl_app.py "5139814" --refresh
```

Kjør oppdateringen så nær deadline som det er praktisk. Det er ikke nødvendig
med daglig innhenting for å bruke appen, men snapshots fra flere ferdigspilte
Gameweeks er nødvendige før odds- og belastningsfeltene kan trenes og valideres
som modellfeatures.

Automatisk innhenting er valgfritt. Samleren kan kjøres hvert femte minutt og
tar ett idempotent snapshot rundt 24, 6 og 1 time før hver deadline:

```bash
.venv/bin/python src/deadline_collector.py --watch
```

Alternativt kan cron kjøre en enkel kontroll hvert tiende minutt:

```cron
*/10 * * * * cd /absolutt/sti/til/fplmodell && .venv/bin/python src/deadline_collector.py --check >> deadline_collector.log 2>&1
```

Ingen `.env` er nødvendig for de offisielle FPL-dataene. Kopier
`.env.example` til `.env` bare dersom de valgfrie kildene skal brukes:

```bash
cp .env.example .env
```

- `ODDS_API_KEY` henter og de-vigger konsensus for kampvinner og over 2,5 mål.
  Dette omregnes også til forventede lagmål og clean-sheet-sannsynligheter.
- `ODDS_PLAYER_PROPS=1` aktiverer de mer kredittkrevende eventkallene for
  anytime-målscorer og over/under 0,5 assists. Props dekker primært amerikanske
  bookmakere og lagres foreløpig som forskningssignaler.
- `FOOTBALL_DATA_API_KEY` henter cup-, Europa- og landskampbelastning fra
  football-data.org.

Nøklene lagres aldri i snapshots eller Git; `.env` er ignorert. Manglende
nøkler stopper ikke innhentingen, men registreres som en hoppet valgfri kilde i
manifestet. Tekstbasert nyhets-/LLM-tolkning er med vilje ikke implementert.

### Historisk markedsmodell

The Odds API-nøkkelen på gratisplan gir liveodds, men ikke det betalte
historikkendepunktet. Modelltreningen bruker derfor gratis, historiske
pre-closing-markedsgjennomsnitt fra football-data.co.uk for 2020/21–2025/26.
Closing-kolonnene brukes ikke, fordi de kan inneholde informasjon som kom etter
FPL-deadline. Kildens råfiler og SHA-256 lagres under
`data/raw/historical_odds/football_data_uk/`.

Benchmarken kan reproduseres med:

```bash
PYTHONPATH=src .venv/bin/python src/market_models.py --root .
```

Den sammenligner incumbent, en lik grunnmodell uten odds, ren markedsmodell,
lineær modell og tre faste blandingsvekter med kronologisk validering. 2025/26
holdes utenfor modellvalget. Den valgte produksjonsmodellen bruker markedsmodellen
per kamp når odds finnes og faller tilbake til incumbent for kamper uten odds.

Football-data.orgs gratisdekning ga bare komplett Champions League-historikk fra
2023/24 og mangler Europa League, Conference League, FA Cup og ligacupen. En
separat CL-belastningsmodell ble derfor testet, men ikke aktivert: den forbedret
verken RMSE, candidate-RMSE eller topp-25-utvelgelsen i begge evalueringssesonger.

Den detaljerte modellrevisjonen, Konsa-diagnosen, feature-ablasjonen og
prioritert dataveikart ligger i
[docs/model_research_2026.md](docs/model_research_2026.md).

Produktresearchen om hvilke analyse- og planleggingsfunksjoner FPL-brukere
etterspør, gapet mot dagens app og en prioritert implementeringsrekkefølge
ligger i
[docs/product_feature_research_2026.md](docs/product_feature_research_2026.md).

## Chipstrategi

Chipmotoren måler hver chip mot den beste vanlige planen med tilgjengelige
gratisbytter. Den bruker samme budsjett-, posisjons-, klubb-, laguttaks- og
kapteinsregler som byttemotoren. Wildcard og Free Hit får en optimal tropp,
Triple Captain får ett ekstra sett kapteinspoeng, og Bench Boost legger til
benkens prognose. Wildcard → Bench Boost optimeres samlet som en sekvens.

FPL 2026/27 gir ett sett Wildcard, Free Hit, Triple Captain og Bench Boost i
hver sesonghalvdel. Første sett må brukes før GW19-fristen, bare én chip kan
brukes per Gameweek, og Free Hit kan ikke brukes i to påfølgende Gameweeks.
Implementasjonen følger [Premier Leagues offisielle 2026/27-regler](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627).

Analysen er med hensikt merket **kort horisont**. Med bare 1–3 prognostiserte
Gameweeks kan den finne poengmaksimum i det kjente vinduet, men den kan ikke
vite om en senere blank- eller dobbelrunde blir bedre. Bruk derfor `Spill` som
et sterkt modellsignal, ikke som bevis på sesongoptimal timing. Metode og
forskningsvalg er dokumentert i [docs/chip_strategy.md](docs/chip_strategy.md).

## Modell og data

Historiske data bygger på
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League).
Liveprognoser lages av `src/capture_fpl.py`, mens beslutningsappen ligger i
`src/fpl_app.py`.

Kjør den utvidede modellbenchmarken og den automatiske promoteringsporten med:

```bash
.venv/bin/python src/nextgen_models.py
```

Forskningsbenchmarkene for rikere features og komponentmodellen kjøres med:

```bash
.venv/bin/python src/model_lab.py
.venv/bin/python src/component_benchmark.py
```

`model_lab.py` sammenligner incumbent med CatBoost og, når systembiblioteket
finnes, LightGBM. På macOS trenger LightGBM OpenMP; godta først Xcode-lisensen
og installer biblioteket manuelt dersom importen feiler:

```bash
sudo xcodebuild -license accept
brew install libomp
```

CatBoost forbedret enkelte topp- og kapteinsmål, men tapte samlet RMSE på den
urørte 2025/26-holdouten og ble derfor ikke promotert. LightGBM hoppes trygt
over dersom `libomp` mangler; feilen skrives i benchmarkens `settings.json`.
Å øke fra 500 til 800 iterasjoner med grunnere trær forbedret topp-25-utvalget,
men ikke den primære kandidat-RMSE-en; lengre trening alene var altså ikke nok.

Komponentmodellen lærer minutter, mål, assists, clean sheet, innslupne mål,
redninger, bonus, kort og forsvarsbidrag separat, og setter dem sammen med FPLs
poengregler. Monte Carlo gir forventning, Q10/Q50/Q90 og sannsynlighet for minst
5 eller 10 poeng. På 66 valideringsrunder ga dens lovlige tropp/XI/kaptein
12 flere faktiske poeng enn incumbent, men 95 %-intervallet for forbedringen
inkluderte null. På etablerte kandidater dekket Q10–Q90 85,3 % i 2025/26.
Artefakten er derfor fortsatt merket `production_eligible: false` og må samle
prospektive snapshots under dagens forsvarsbidragsregler før eventuell bruk.

Kjør deretter den begrensede beslutningsbenchmarken og bygg en refittet
produksjonsmodell på alle ferdige sesonger:

```bash
.venv/bin/python src/decision_backtest.py
.venv/bin/python src/uncertainty_models.py
.venv/bin/python src/risk_profiles.py
.venv/bin/python src/season_simulator.py --transfer-policy historical --minimum-gain 0
.venv/bin/python src/season_simulator.py --transfer-policy historical --minimum-gain 1
.venv/bin/python src/season_simulator.py --transfer-policy historical --minimum-gain 2
.venv/bin/python src/production_models.py
.venv/bin/python src/capture_fpl.py --rescore-latest
```

Beslutningsbenchmarken laster historiske priser og klubber fra kilderepoet og
løser uttaket eksakt med `scipy.optimize.milp`. Historisk `value` er samlet etter
Gameweek og er derfor ikke en sertifisert deadline-pris; resultatet brukes som
en streng utrullingsport, ikke som en full sesongsimulering.

Kvantilmodellen estimerer Q10, median og Q90. Disse er betingede
modellkvantiler, ikke et garantert konfidensintervall. På etablerte kandidater
dekket Q10–Q90 85,5 % i validering og 85,0 % i 2025–26-testen.
For flere Gameweeks summeres kampkvantilene som en beslutningsheuristikk; summen
er ikke et kalibrert flerukersintervall.

Den sekvensielle simulatoren starter profilene fra samme tropp og håndterer
bank, individuell salgspris, C/VC og lovlige autosubs. Den bruker historisk
korrekt grense på to oppsparte gratisbytter i 2023–24, fem fra 2024–25, og
AFCON-påfyllet til fem etter GW15 i 2025–26. Når flere bytter er tilgjengelige,
velger en eksakt MILP sluttropp, XI og kaptein samlet; dette fanger blant annet
premiumkjøp som krever et finansieringsbytte.

Resultatet er følsomt for alternativkostnaden per brukt gratisbytte:

| Minimum modellgevinst per bytte | balanced | stable | upside | Vinner |
|---:|---:|---:|---:|---|
| 0,0 | 5 631 | **5 773** (+142) | 5 565 (−66) | stable |
| 1,0 | 5 502 | **5 740** (+238) | 5 577 (+75) | stable |
| 2,0 | **5 563** | 5 424 (−139) | 5 543 (−20) | balanced |

Ved terskel 1,0 vant `stable` alle tre sesonger, men ved 2,0 tapte den samlet
klart. Terskel 1,0 er undersøkt retrospektivt og kan derfor ikke brukes som en
ny produksjonsstandard uten en separat, prospektiv beslutningstest. Simulatoren
er dessuten fortsatt nærsynt: den optimaliserer neste Gameweek, ikke hele
fixtureblokken. Regelimplementasjonen følger Premier Leagues beskrivelser av
[fem oppsparte bytter fra 2024–25](https://www.premierleague.com/en/news/4059225)
og [AFCON-påfyllet i 2025–26](https://www.premierleague.com/en/news/4461660).

Kjør alle tester med:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Kjør en ekte Chromium-test mot lokalt API, live FPL-lag og den aktive
prognoseartefakten med:

```bash
npm --prefix frontend run test:e2e:live
```

Denne testen importerer laget med åtte Gameweeks og kontrollerer laguttak,
marked, bytter og at flerukersplanen faktisk viser åtte runder. Den krever
nettverk og en aktiv prognose, og er derfor en eksplisitt live-test fremfor en
isolert enhetstest.

## Managerstrategi og beslutningsstøtte

React-appen har et strategisenter som samler flerukersvalget mellom å rulle,
bytte og ta hit, troppshelse, kapteinsmargin, deadline-sjekkliste, offisielle
prisvarsler og modellfiltrerte watchlists. Hit-planer sammenlignes med et eget
scenario uten poengtrekk og må ha en usikkerhetsbuffer før de anbefales.

Se `docs/fpl_manager_strategy_research_2026.md` for forskningsgrunnlaget, dagens
produktstatus og prioritert videre veikart.
