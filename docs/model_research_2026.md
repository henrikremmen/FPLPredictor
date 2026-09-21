# Modellrevisjon, odds og laganbefalinger (september 2026)

## Kort konklusjon

Den største svakheten er ikke mangel på enda en generell boostingmodell. Det er
forventede minutter og informasjon som endrer seg tett på deadline. Dagens
poengmodell reagerer for tregt når en spiller nylig har fått en ny rolle. Odds,
forventede lagoppstillinger og skade-/rotasjonsinformasjon bør derfor behandles
som tidsstemplet deadline-informasjon, ikke som udokumenterte manuelle tillegg.

Lagform finnes allerede i modellen gjennom sesongrater og enkelte femkampersfelt,
men den tidligere implementasjonen var asymmetrisk: laget hadde bare nylige mål
scoret, mens motstanderen bare hadde nylige mål sluppet inn. Snapshotbyggeren
lager nå både scoret, sluppet inn, poeng og antall kamper siste fem for begge lag.

## Konsa-diagnosen

Snapshotet før GW5 ga Ezri Konsa 2,0649 poeng. Han var da Arsenal-spiller og
historikken var 0, 11, 90 og 90 minutter. Likevel ga spilletidsmodellen bare
67,39 prosent sannsynlighet for 60+ minutter. Det er hovedårsaken til den lave
prognosen. Den separate komponentmodellen ga 2,3257, men estimerte bare 14,84
prosent clean-sheet-sannsynlighet mot Brighton fordi Brightons tidlige
målrate var svært høy. Den offisielle FPL-verdien `ep_next` var 2,8.

Dette viser to problemer:

- Et femkampers vindu reagerer tregt på to helt nye starter.
- Fire seriekamper gir ekstreme lagrater; form må krympes mot en lengre prior
  eller forankres i et oddsmarked.

En kontrollert feature-test la til kortere start-/minuttvinduer og symmetrisk
lagform. Kortere rollehistorikk forbedret 2025/26, men forverret gjennomsnittet
på de to kronologiske valideringssesongene. Varianten ble derfor ikke promotert.

| Variant | Validering RMSE | Kandidat-RMSE | 2025/26 RMSE | 2025/26 P(60+) Brier |
|---|---:|---:|---:|---:|
| Produksjonsfeature-sett | **1,91254** | **3,07456** | 1,93061 | 0,08146 |
| Kort rollehistorikk | 1,91308 | 3,07692 | 1,92863 | **0,08112** |
| Symmetrisk lagform | 1,91320 | 3,07668 | 1,93065 | 0,08146 |
| Begge | 1,91313 | 3,07663 | **1,92853** | 0,08112 |

## Odds: hva som kan og ikke kan hentes

[The Odds API](https://the-odds-api.com/sports/epl-odds.html) gir 1X2 og
over/under via liga-endepunktet. Event-endepunktet tilbyr også EPL-markedene
`player_goal_scorer_anytime` og `player_assists`, men spillerprops er i dag
begrenset til amerikanske bookmakere. Direkte clean-sheet-odds er ikke et
standardmarked i denne kilden. Implementasjonen de-vigger bookmakerne og
tilpasser i stedet to Poisson-målrater til 1X2 og over 2,5. Da følger forventede
lagmål og clean-sheet-sannsynligheter fra samme konsistente kampfordeling.

Spillerprops er valgfritt fordi eventkall bruker vesentlig flere API-kreditter.
Sett `ODDS_PLAYER_PROPS=1` sammen med `ODDS_API_KEY` for å fryse mål- og
assistodds. Historiske odds, inkludert props, krever en betalt historikkplan.
Uten historiske snapshots brukes ikke disse signalene til å omskrive
produksjonspoengene; de lagres først for en kronologisk benchmark.

## Prioritert forbedringsrekkefølge

1. **Forventede minutter og forventet XI.** Samle prospektive lineup-estimater,
   skader og startkandidater før hver deadline. Sportmonks tilbyr et
   [Expected Lineups API](https://www.sportmonks.com/football-api/expected-lineups-api/),
   men det er et kostbart tillegg. En ny kilde må først måles mot faktisk 60+
   og tidspunktet dataene ble kjent.
2. **Markedskomponenter.** Backtest de-viggede clean-sheet-, lagmål-, mål- og
   assist-sannsynligheter med log-loss/Brier og FPL-poeng. Bruk markedet som en
   egen komponent eller kalibrert blend, ikke som et ukontrollert påslag.
3. **Komponentmodell.** Modellen som lærer minutter, mål, assists, clean sheet,
   redninger, bonus og defensive bidrag separat slo incumbent med 12 poeng i
   66 valideringsrunder, men intervallet inkluderte null. Fortsett prospektiv
   testing under dagens defensive-contribution-regler før promotering.
4. **Bayesiansk lagform.** Krymp tre-/femkampers mål- og xG-form mot en
   hjemme-/borteprior. Tidlig sesong bør marked/FPL-lagstyrke veie mer; senere
   kan observert form få høyere vekt.
5. **Kampbelastning og dødballer.** Cup-/Europa-/landskamper, hviledager og
   straffe-/cornerrekkefølge er samlet i snapshots. De må få nok historikk før
   de legges til modellen.
6. **Beslutningsmål.** Fortsett å kreve forbedring i lovlig tropp, XI og kaptein,
   ikke bare lavere total RMSE. Nullminuttsrader gjør vanlig RMSE misvisende for
   spillerkjøp.

## Features som bør utfordres, ikke bare beholdes

- Tre sterkt overlappende poengvinduer og ICT-delene kan gi unødvendig
  redundans. Test grupperte ablasjoner over flere sesonger.
- Faktiske mål og assists siste fem bør sammenlignes mot en ren xG/xA-variant;
  små vinduer gir mye finishing-støy.
- `selected_by_percent`, transfertrend og prisendring kan være gode
  nyhetsproxyer, men må aldri brukes fra et snapshot tatt etter deadline.
- FPLs historiske `xP` er fortsatt utelatt fordi kilderepoet advarer om mulig
  post-match-timing. Live `ep_next` kan vises som ekstern referanse, men bør
  ikke trenes inn uten sertifisert historikk.

Features fjernes først når en forhåndsdefinert ablasjon forbedrer både
kalibrering og beslutningsbacktest. Feature importance alene er ikke nok.

## Forskningsgrunnlag

- [OpenFPL](https://arxiv.org/abs/2508.09992) støtter prospektiv evaluering,
  posisjonsspesifikke ensembler og separate én- til treukersprognoser. Vår
  posisjonsspesifikke kandidat ble testet og tapte; ideen ble ikke bare antatt.
- [Dixon og Coles](https://doi.org/10.1111/1467-9876.00065) er standardreferansen
  for dynamiske Poisson-baserte fotballresultater og motiverer den eksplisitte
  kampmålsmodellen.
- [Datadrevet FPL-optimering](https://arxiv.org/abs/2505.02170) viser hvorfor
  prediksjon og lovlig heltallsoptimering må evalueres samlet.
- De [offisielle FPL-poengreglene](https://www.premierleague.com/en/news/2174909)
  bekrefter at minutter, clean sheet, mål, assists, redninger og defensive
  bidrag bør modelleres som egne hendelser når datagrunnlaget er sterkt nok.

## Nye laganbefalinger

Appen har nå en egen **FH / WC-lag**-side:

- beste lovlige 15-manns Free Hit-tropp, XI, benk, kaptein og visekaptein for
  hver Gameweek i den frosne horisonten;
- beste Wildcard-tropp med 0,9 diskontering per senere runde;
- en ny eksakt flerukersplan fra Wildcard-troppen som viser planlagte ut/inn,
  kaptein, bank og eventuelle hits i hver senere runde.

Wildcard-planen er en rullerende plan, ikke et løfte. Priser, skader og ny
informasjon er statiske i dagens løsning, så den må beregnes på nytt før hver
deadline.
