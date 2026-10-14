# Modellutfordrere – arbeid pågår

Ingen av variantene nedenfor er godkjent for produksjon. Hele målet om
skadeforløp, Understat, Elo, komponenter og prospektiv evaluering er fortsatt åpent.

## Start, innhopp og fravær

`src/role_models.py` bruker observerte `starts`, ikke en 60-minuttersgrense,
til å lage tre separate utfall. Manglende startetiketter utelates fra trening
og evaluering. De finnes først fra 2022/23 i dagens bearbeidede datasett.

Kjør `.venv/bin/python src/role_models.py`. Resultatene ligger i
`artifacts/model_research/role_benchmark.json`. Kronologisk trening gir
multiklasse-Brier 0,265 / 0,267 / 0,243 i 2023/24, 2024/25 og 2025/26.
Referansen er treningsperiodens konstante klassefrekvenser, ikke den godkjente
poengmodellen. Dette dokumenterer ennå ingen forbedring av poeng eller lagvalg.

## Skadeforløp som datostyrte scenarioer

`src/availability_forecast.py` leser eksplisitte «Expected back»-datoer fra
FPL-nyheter med `news_added` senest ved innsamlingen. Ukjent eller utløpt
returdato regnes ikke som friskmelding. Årsskiftet løses fra nyhetsdatoen.
Neste rundes offisielle prosent beholdes selv om returdatoen skulle antyde
noe annet. I senere runder sammenlignes fortsatt skadefradrag med et scenario
der ekstra skadefradrag fjernes fra rapportert returdato. Faktor 1 betyr her
at grunnmodellens spilletid får gjelde, ikke sikker start eller deltakelse.

Scenariene beregnes per kamp, slik at en retur mellom to kamper i samme GW
kan få ulik virkning. Begge er uttrykkelig ukalibrerte og er foreløpig ikke
koblet til produksjonsrangeringen. Empirisk overgangsmodell og integrasjon
gjenstår; dette er ikke en ferdig løst skadeprognose.

Snapshot fra 9. oktober er analysert i
`artifacts/model_research/injury_scenarios_20261010/`: 5 336 kampprognoser,
667 spillere og 23 spillere med endret horisont i returscenarioet. Kildehashene
ligger i rapporten. Dette er avspilling av et historisk snapshot, ikke bevis
for at den nye scenariomodellen var låst før den opprinnelige deadline.
Fire tester dekker dobbeltrunde, ukjent/utløpt retur, fremtidige nyheter og
årsskifte.

## Elo

`src/elo_features.py` beregner egen Elo fra lokale FPL-kampresultater, med
rating over sesonggrenser, K=20 og hjemmefordel 60. Dette er ikke ClubElo.
Nye lag får 1500 og en eksplisitt teller for antall observerte kamper.
Resultater gjøres tilgjengelige ved neste UTC-døgn som konservativ proxy;
det er ikke dokumentasjon av leverandørens publiseringstid. Bare resultater
strengt før spørringens tidspunkt oppdaterer ratingen. Like tidspunkt behandles
samlet, og tester kontrollerer at fremtidige resultater ikke påvirker fortiden.

Kjør `.venv/bin/python src/elo_benchmark.py`. Samme HGB7-poengmodell, samme
treningsrader og hyperparametre brukes i fire varianter:

| Testsesong | Uten odds | Uten odds + Elo | Med odds | Med odds + Elo |
|---|---:|---:|---:|---:|
| 2023/24 RMSE | 1,91097 | 1,90566 | 1,90212 | 1,90185 |
| 2024/25 RMSE | 1,92300 | 1,91932 | 1,91536 | 1,91386 |
| 2025/26 RMSE | 1,93503 | 1,93140 | 1,92701 | 1,92737 |

Elo gir en liten, konsekvent RMSE-forbedring uten odds. Tilleggsverdien med
odds er mindre og ikke konsekvent. Dette er en diagnostisk ablasjon, ikke en
sammenligning mot hele produksjonsensemblet. Resultatet gir ikke grunnlag
for automatisk overgang til Elo-modellen.

Begrensninger: historiske grunnfeatures er forskjøvet per kamp, ikke bygget
på nytt ved dokumenterte FPL-deadlines. Elo-testen bruker første observerte
GW-avspark minus 90 minutter som eksplisitt deadline-proxy. Historiske odds
mangler verifisert publiseringstid. 2025/26 er allerede undersøkt i tidligere
eksperimenter og er derfor ikke et nytt urørt holdout. Resultatene må ikke
presenteres som en sertifisert deadline-backtest.

## Understat-datadekning

Inventaret ligger i `artifacts/model_research/understat_inventory.json`.
Spillerfiler med kampstatistikk finnes i 2021/22–2024/25. Eksplisitte
FPL/Understat-ID-tabeller finnes bare i 2021/22 og 2022/23. FPL-ID-er kan
ikke ukritisk gjenbrukes over sesonggrenser. Nyere sesonger mangler lokale
Understat-filer. Eksisterende spillerfiler inneholder npxG, xG, xA, skudd,
posisjon, xGChain og xGBuildup, men ikke skuddkoordinater eller antall
straffeskudd. npxG er ikke nok til å rekonstruere antall skudd uten straffer.

`src/understat_features.py` bygger nå en bro fra de eksplisitte mappingene via
stabil FPL-`code` til sesongens `player_id`. Det gir 495 koblede spillere i
2023/24 og 418 i 2024/25. Dette er identitetsdekning, ikke garanti for ferske
kampdata. Tvetydige identitetskoblinger avvises. Overlappende karrierehistorikk
dedupliseres; eldste lokale sesongarkiv foretrekkes ved statistikkrevisjoner.
Ti spiller/kamp-par med motstridende kampdatoer settes i karantene. Ingen av
disse retrospektive arkivvalgene dokumenterer historisk publiseringstid.

Understat-features har eget `us_`-prefiks og erstatter ikke FPL-xG/xA. Første
versjon inkluderer siste fem observerte kamper med minutter, skudd, xG,
npxG, xA, nøkkelpasninger, xGChain, xGBuildup, xG per skudd og per-90-rater.
Opplysninger ved eller etter prognosetidspunktet utelates. Manglende
identiteter gir manglende verdier, ikke nuller. Karrierehistorikken kan
inkludere andre ligaer, og gamle observasjoner kan være foreldet; alder og
ligakontekst må derfor undersøkes før produksjonsbruk.

Kjør `.venv/bin/python src/elo_benchmark.py --understat` for alle åtte
kombinasjoner av odds, Elo og Understat på samme evalueringsrader. Rapporten
`artifacts/model_research/source_ablation.json` inkluderer datadekning og
revisjonsaudit. Dette er fortsatt en diagnostisk HGB-sammenligning.


Resultater med odds (RMSE, lavere er bedre):

| Sesong | Referanse | + Understat | + Elo | + begge |
|---|---:|---:|---:|---:|
| 2023-24 | 1.90212 | 1.89730 | 1.90185 | 1.89739 |
| 2024-25 | 1.91536 | 1.90761 | 1.91386 | 1.90692 |
| 2025-26 | 1.92701 | 1.92738 | 1.92737 | 1.92710 |

Alle 24 sammenligninger er fullført. Understat gir små forbedringer i de to første evalueringssesongene, men ingen stabil RMSE-gevinst i 2025/26. Siste tilgjengelige Understat-kamp blir tilgjengelig med datoproxy 8. april 2025; selv 2024/25 er dermed ufullstendig. Featuredekningen er cirka 62,5 %, 57,8 % og 41,3 % av evalueringsradene. Ingen produksjonsovergang.

## Komponentmodell v2

`CoherentComponentPointsModel` er en separat utfordrer i
`src/component_models.py`. Den beregner forventede poeng fra samme
minuttbetingede tellefordelinger som simuleringen. Bonusbegrensningen til tre,
heltallsgrenser for redninger/innslupne mål, clean-sheet-sannsynlighet og
defensive terskler behandles likt i middelverdien og simuleringen.
`point_contributions()` gir forklarbare forventede poeng per komponent.

V2 fjerner også kravet om 60 minutter for trekk ved innslupne mål. Det kravet
gjelder clean-sheet-poeng, ikke trekk for hvert andre innslupne mål, jf.
[Premier Leagues poengregler](https://www.premierleague.com/en/news/2174909).
Arkiverte v1-modeller beholder sin tidligere oppførsel.

Fem komponenttester består, inkludert sammenligning mellom analytisk
forventning og 150 000 simuleringer, innslupne mål under 60 minutter og null
poeng ved sikkert fravær. Modellen antar fortsatt betinget uavhengige hendelser;
for eksempel er clean sheet og antall innslupne mål ikke samlet i en full
kampsimulering. V2-trening avviser manglende telleetiketter i stedet for å
konvertere dem til null; eksisterende data fra 2020/21 har ingen manglende
verdier i disse tellekolonnene. Historiske regelendringer krever fortsatt
ytterligere arbeid.

Kjør `.venv/bin/python src/component_coherence_benchmark.py` for en isolert
v1/v2-sammenligning med identiske trente delmodeller. Dette er ikke i seg selv
en test mot produksjonsensemblet eller en produksjonsgodkjenning.


Fullført v1/v2-sammenligning (RMSE):

| Sesong | V1 | V2 |
|---|---:|---:|
| 2023-24 | 1.909931 | 1.909366 |
| 2024-25 | 1.919902 | 1.919530 |
| 2025-26 | 1.837024 | 1.836913 |

V2 forbedrer RMSE marginalt i alle tre sesonger. For 2025/26 er faktiske defensive bidrag trukket fra målpoengene for sammenlignbarhet med treningsperiodens regler. Det er derfor ikke en full test under dagens regler. Rapportene ligger i `artifacts/model_research/component_coherence.json` og `component_contributions.csv`.

## Gjenstående arbeid

- Utvide de sikre sesongavhengige identitetskoblingene til nye spillere og hente
  manglende Understat-data med proveniens; egne skudddata kreves for soner og
  ikke-straffeskudd.
- Bygge deadline-baserte features og teste Understat/Elo/kombinasjonen mot
  produksjonsensemblet på sammenlignbare rader.
- La skadeinformasjon variere per GW med eksplisitte kilder og usikkerhet.
- Videreutvikle komponentmodellen og vurdere poeng, kalibrering og lovlige
  lag-/kapteinsvalg samlet.
- Fryse utfordrerprognoser før fremtidige deadlines og evaluere etter kampene.


## Ny Understat-innsamler og skuddfeatures

Nettstedets nåværende Javascript bruker `getLeagueData/EPL/{year}` og
`getMatchData/{id}`. `src/capture_understat.py` lagrer de offentlige
JSON-responsene separat med URL, start-/mottakstid og SHA-256. Eksisterende
cache valideres ved gjenopptakelse. Dette gir tilgang til nyere data enn de
lokale CSV-arkivene, fra [Understat EPL](https://understat.com/league/EPL/2026).

`src/understat_shots.py` normaliserer lagoppstillinger og skudd. Straffer
utelates fra antall ikke-straffeskudd, npxG og npxG per skudd. En eksplisitt
koordinatsone defineres av X >= 0,83 og Y mellom 0,25 og 0,75; den må ikke
omtales som en nøyaktig straffefeltgrense. Spillerens andel av lagets npxG
beregnes fra samme kamper. Rolling features bruker siste fem observerte
kamper og inkluderer hvor gammel siste kamp er.

Featurekoblingen krever eksplisitt `mode="observed"` eller
`mode="retrospective"`. Førstnevnte krever både kampdato og faktisk mottakstid
før cutoff. Sistnevnte bruker dagen etter kampen som en deklarert proxy.
Dermed kan en historisk innsamling ikke feilaktig brukes som dokumentasjon
på data som var tilgjengelige før en tidligere deadline.

Seks Understat-tester består, inkludert straffeekskludering, identitets- og
kampkoblinger, duplikater og skillet mellom faktisk hentetid og historisk
kampdato. Nyere skuddfeatures er ennå ikke modellvalidert.

Innsamlingen er fullført: 810 kamper (380 i 2024/25, 380 i 2025/26 og 50 i 2026/27), med 24 595 normaliserte spillerkamper. Rådata: `data/raw/understat/capture_20261010/`. Modellgrunnlag: `artifacts/model_research/understat_shot_history.csv`. Alle matchresponser er hashkontrollert under normaliseringen. Innsamlingen er gjort etter GW6-deadline og kan derfor ikke brukes som predeadline-evidens for GW6.


## Utvidet ID-audit og nye skuddtester

`src/understat_identity.py` utvider stabile kodekoblinger med eksakt
normaliserte navn og minst tre felles kamper med minuttsamsvar (+/- ett minutt).
Kampene må ha samme dato og lag. Fravær hos én leverandør og spilletid hos
den andre, eller et avvik på minst 45 minutter, avviser en ny kobling.
Andre minuttavvik ignoreres som evidens. Konflikter med eksisterende stabile
kodekoblinger godtas ikke; tvetydige kandidater forblir ukoblet.

Dette øker dekningen blant aktive Understat-spillere til 482/562 i 2024/25,
441/537 i 2025/26 og 283/421 i 2026/27. Det er fremdeles ufullstendig dekning.
Identitetsbevisene er samlet i ettertid; historiske eksperimenter er derfor
fortsatt retrospektive. Identitets- og auditfiler ligger i
`artifacts/model_research/understat_identities.csv` og
`understat_identity_audit.csv`. Fire nye tester kontrollerer kampbevis,
navnenormalisering og duplikater; ti Understat-tester totalt består.

`src/shot_benchmark.py` sammenligner produksjonens `market_hgb`-poengarkitektur
med tillegg av skuddfeatures, Elo og begge. Alle varianter har samme
2022+-ensemble som fallback ved manglende odds og trenes på data før 2025/26.
Innsamlet skuddhistorikk begynner i 2024/25; eldre treningsrader mangler derfor
disse verdiene. Dette begrenser testen til én sesong med skuddtreningsdata.
Resultater og individuelle prediksjoner lagres separat fra produksjonen.

Fullført 2025/26-test:

| Variant | RMSE | MAE | Kaptein, faktisk gjennomsnitt |
|---|---:|---:|---:|
| market_elo0_shots0 | 1.927010 | 0.970823 | 6.459 |
| market_elo0_shots1 | 1.925465 | 0.973745 | 6.135 |
| market_elo1_shots0 | 1.927369 | 0.970283 | 6.243 |
| market_elo1_shots1 | 1.926327 | 0.974314 | 6.243 |

Skuddfeatures alene forbedrer RMSE svakt, men forverrer MAE og kapteinsmålet. Kombinasjonen med Elo forbedrer topplister noe, men har også svakere kapteinsmål enn referansen. Kapteinsmålet er rangering over spillere, ikke en komplett lovlig lag-/overgangssimulering. Minuttmål er ikke evaluert her og står som null i JSON, siden dette eksperimentet bare endrer poengdelen. Ingen variant er godkjent for produksjon.


## Lovlige tropps-, ellever- og kapteinsvalg

`src/source_decision_benchmark.py` kjører de fire skudd/Elo-variantene gjennom
samme heltallsoptimalisering for hver runde. Hver tropp har 15 spillere,
korrekt posisjonsfordeling, maks tre per klubb og budsjett 100,0. Startelleveren
har lovlig formasjon og én kaptein. Før sammenligning kontrolleres identiske
spillerutvalg, utfall, posisjoner, lag og priser på tvers av modellene.

Testen dekker GW6–38 i 2025/26 (33 runder):

| Tillegg til produksjonsarkitektur | Samlet poenggevinst | Gevinst per GW | Bootstrap 95 % intervall per GW |
|---|---:|---:|---:|
| market_elo0_shots1 | -50 | -1.52 | [-3.79, 0.70] |
| market_elo1_shots0 | 11 | 0.33 | [-2.39, 2.73] |
| market_elo1_shots1 | 70 | 2.12 | [-1.09, 4.94] |

Kombinasjonen får høyest poengsum i dette eksperimentet, men intervallet
inkluderer null/negativ gevinst. Understat alene gir svakere lagvalg til tross
for marginalt bedre RMSE. Dette underbygger behovet for beslutningsmål i
modellvalget. Ingen produksjonsgodkjenning gis på dette grunnlaget.

Begrensningene er vesentlige: en ny tropp optimaliseres hver runde; ingen
transfers, chips, autosubs, visekaptein eller dynamisk lagverdi. Prisene er
historiske observasjoner etter runden og ikke sertifiserte deadline-priser.
Grunnfeatures og eksterne historiske data er fortsatt retrospektive.
Bootstrapen trekker runder uavhengig og modellerer ikke tidsavhengighet.
Rapporter: `artifacts/model_research/source_decision_{gameweeks,summary}.csv`
og `source_decision_report.json`. Tre nye sammenligningstester og den
eksisterende optimizer-testen består.


## Første prospektive referanse er låst

`src/prospective_lock.py` kopierer kildedata og modellfiler til en ny mappe,
lagrer hashverdier, avviser etterdeadline-opprettelse og hindrer overskriving.
Kandidatene i samme bundle må ha samme spiller/kamp-utvalg. Verifikasjon
oppdager endrede filer og ufullstendige manifester. Dette er et lokalt auditspor,
ikke uavhengig tidsstempling eller bevis på historisk treningsdatakvalitet.

`src/freeze_incumbent.py` har beregnet og låst produksjonsmodellens referanse
for **GW7, 667 spillerkamper**, 10. oktober 2026 kl. 12:31:54 UTC.
Deadline er **17. oktober 2026 kl. 10:00 UTC**. Kilde-snapshotet er fra
9. oktober. Prognosen er derfor uttrykkelig basert på eldre informasjon.
Samtlige vellykkede råresponser ble hashkontrollert før kopiering, og
modellhashen er kontrollert mot snapshot-manifestet.

Bundle: `artifacts/prospective/gw7_incumbent_20261010/`.
Prediksjonene inkluderer poeng, minuttbånd og kvantiler. Dette er kun
referansen; utfordrerne og senere utfallsevaluering gjenstår. To tester
kontrollerer overskriving, endrede kopier, etterdeadline-forsøk og ulike
kandidatpopulasjoner. Bundlen er verifisert etter opprettelse.


## GW7: referanse og kildeutfordrere låst

`artifacts/prospective/gw7_sources_20261010/` ble låst 10. oktober 2026
kl. 12:34:25 UTC, før deadline 17. oktober kl. 10:00 UTC. Bundlen inneholder
2 668 prognoser: samme 667 spillerkamper for produksjonsreferansen,
Understat, Elo og kombinasjonen. Den kopierer referansens eksisterende
prognoser uendret og lagrer egne trente utfordrermodeller.

Fremtidige skuddfeatures bruker `observed`-modus med faktisk innsamling før
prognosen. Understat-featuredekningen er 56,2 %. Historisk trening er fortsatt
retrospektiv og inkluderer sesonger til og med 2025/26. Alle prognosene har
odds i dette snapshotet; kildeutvidet fallback uten odds er derfor ikke aktiv
for denne runden. Den nye fallbacken erstatter bare HGB-delen i det eksisterende
ensemblet og krever egen evaluering når den brukes.

`src/source_challengers.py` definerer de serialiserbare modellene;
`src/freeze_source_challengers.py` trener, predikerer og låser. Prognosene er
utfordrere, ikke godkjente erstatninger. Role/minutt- og komponentutfordrere,
full evaluering etter kampene og videre deadline-basert testing gjenstår.


## GW7: rolle- og komponentutfordrere låst

`artifacts/prospective/gw7_components_20261010/` ble låst 10. oktober 2026
kl. 12:37:30 UTC. Den inneholder 2 001 rader: referansen, separate
start/innhopp/fravær-sannsynligheter og komponentmodell v2 for samme 667
spillerkamper. Rollemodellen endrer ikke referansens poengprognose; den skal
måles på korrekt definerte rolleutfall. Start og 60+ minutter er forskjellige
mål og rapporteres ikke som om de var det samme.

Rollemodellen trenes på 2022/23–2025/26. Komponentmodellen trenes på
2020/21–2025/26 og har denne gangen en trent modell for defensive bidrag.
Alle forventede poengbidrag er inkludert separat. Manglende startvinduer i
referansens features er beregnet fra de pinnede spillerhistorikkene, med kun
kamper som kildens fixture-snapshot markerer som ferdige.

`src/freeze_component_challengers.py` lager bundlen. En ny test bekrefter at
uferdige kamper ikke kommer inn i startmålene. Etter låsing er alle 667
rollefordelinger og 667 komponentprognoser gjenskapt fra kopierte modellfiler
og features. Sannsynlighetene summerer til én, komponentbidragene summerer
til poengprognosen, og kildehashene består kontrollen. Dette dokumenterer
reproduserbarhet, ikke bedre prediksjonsevne; kampresultatene gjenstår.


## Evaluering og beslutninger før fremtidige utfall

`src/prospective_evaluation.py` kontrollerer låste filer og krever en komplett
FPL-snapshot fra samme sesong, med ferdig og `data_checked` gameweek.
Spillerresultater må være hentet etter deadline, ha ferdige kamper og dekke
alle låste spiller/kamp-nøkler. Manglende resultater blir ikke nuller.
Poengfeil beregnes både per kamp og per spiller/GW. Rolle- og minuttbånd
skåres separat med sannsynlighetsmål. Tre tester består, inkludert at
historiske featurekolonner med minutter/start ikke kan forveksles med utfall.

En prøve mot siste tilgjengelige snapshot ble korrekt avvist fordi GW7
ikke er ferdig. Det finnes derfor fortsatt ingen prospektive resultatmål.
Kjør senere for hver forecast-bundle:

```sh
.venv/bin/python src/prospective_evaluation.py BUNDLE FULLFORT_FPL_SNAPSHOT NY_RESULTATMAPPE
```

`src/freeze_decisions.py` har dessuten låst alle seks modellvarianters
15-mannstropp, startellever og kaptein 10. oktober kl. 12:41:05 UTC.
Bundle: `artifacts/prospective/gw7_decisions_20261010/`. Prisene er de observerte
prisene fra 9. oktober; alle valgte spillere var markeret valgbare da.
En separat kontroll verifiserte budsjett, posisjoner, klubbegrensning, ellever,
kaptein og filhash for samtlige seks lag. Rollevarianten har samme poeng og
valg som referansen, fordi det foreløpig bare er sannsynlighetene som endres.
Alle modellene valgte samme kaptein i denne runden.

Dette er statiske sammenligningslag, ikke brukerens eksisterende lag eller
en sesongsimulering med overganger. Automatisk scoring av disse valgene,
skadeforløp i brukeropplevelsen og bredere deadline-trening gjenstår sammen
med fremtidige kampresultater.


## Lagscoring og skadescenario i webappen

`src/prospective_decisions.py` evaluerer de låste lagene uten ny optimalisering.
Den krever utfall for samtlige planlagte kamper til de valgte spillerne,
kontrollerer tropp/ellever og legger kapteinspoengene til én ekstra gang.
Benkepoeng rapporteres separat og telles ikke. Tre nye tester bekrefter
kapteinsdobling, uendret benk og avvisning av manglende dobbeltrundekamper.
Kommando etter ferdig, kontrollert GW7:

```sh
.venv/bin/python src/prospective_decisions.py artifacts/prospective/gw7_decisions_20261010 FULLFORT_FPL_SNAPSHOT NY_RESULTATMAPPE
```

Spillerpanelet i webappen viser nå et separat **Return-date scenario** når
FPL oppgir en brukbar forventet returdato. Tabellen viser per kamp dagens
konservative poengjustering og et scenario der ekstra skadefradrag fjernes
etter returdatoen i senere runder. Spillerens nyeste importerte nyhet brukes,
og tidspunktet for spillerdata er bevart. Ukjent eller utløpt returdato
viser ikke et konstruert friskmeldingsscenario. Panelet sier eksplisitt at
scenarioet ikke er en kalibrert sannsynlighet eller garanti for start.
Anbefalingene beholder dagens konservative justering inntil forbedringen
har bedre evalueringsgrunnlag.

Validering: frontend-build, seks Playwright-workspace-tester, 14 backend-
workspace-tester, åtte tester for prospektiv låsing/evaluering og fire
skadescenariotester består. Nettlesertestene dekker scenarioets merking og
at spillerpanelet fortsatt fungerer på mobil.
