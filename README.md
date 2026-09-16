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
- anbefalt startellever, formasjon, kaptein, visekaptein og benk
- ett til fem bytter, med en eksakt global MILP-plan og automatisk poengtrekk
- filtrerbare kjøpskandidater og rangerte salgskandidater
- kortsiktig chipanalyse for Wildcard, Free Hit, Triple Captain, Bench Boost og
  sekvensen Wildcard → Bench Boost

Bank og gratisbytter kan korrigeres i sidepanelet dersom de offentlige
estimatene avviker fra tallene inne i FPL. Knappen **Oppdater prognosen** henter
et nytt offentlig snapshot; dette kan ta rundt ett minutt. Appen logger aldri
inn og kan ikke utføre bytter.

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
.venv/bin/python src/fpl_app.py "5139814" --action lineup --risk-profile upside
```

`--horizon 2` eller `--horizon 3` summerer nåværende prognoser over flere
Gameweeks for kjøp og salg. Startelleveren og kapteinen beregnes alltid bare
for neste Gameweek. Flerukersfilen opprettes av `--refresh`.

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
  flerukershorisont, med mindre `--horizon 2` eller `--horizon 3` velges.
- En offentlig laglenke gir ikke eksakt salgspris eller saldoen av gratisbytter.
  Appen rekonstruerer kjøpspris fra offentlig historikk, bruker FPLs prisregel og
  estimerer gratisbytter fra laghistorikken. Kontroller disse to tallene i FPL før
  du bekrefter et bytte.
- Modellpoeng justeres ned ved et kjent `chance_of_playing_next_round`-flagg, men
  modellen inneholder ikke en full nyhets- eller skadeanalyse.
- Den eksisterende modellen er eksperimentell og er trent med historiske
  pre-fixture-features. Den er ikke en garanti for faktiske poeng.
- Appen logger aldri inn og utfører aldri endringer i FPL-laget.

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
