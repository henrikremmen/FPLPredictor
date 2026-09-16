# Neste generasjon: modellrevisjon og resultater

## Konklusjon

`long_history_mixture_15` vant den ordinære prediksjonsbenchmarken, men erstatter
ikke tre-modellsensemblet som poengmotor. En ny, direkte beslutningsbenchmark
viste at lavere RMSE ikke ga bedre budsjettbegrensede laguttak. Produksjonen
bruker derfor incumbent-ensemblet for poeng og 15-bladsmodellen bare for P(60+).

Den viktigste forbedringen var ikke mer modellkompleksitet. Det var å utvide
treningshistorikken fra 2022–23 til 2020–21 for den eksisterende modellen som
skiller mellom 0, 1–59 og 60+ minutter, og å øke spilletidsklassifikatoren fra
7 til 15 blad. Posisjonsspesifikke modeller, Extra
Trees og et nytt globalt HGB-oppsett slo ikke denne løsningen samlet.

Begge komponentene er refittet etter evalueringen: poengmotoren på `2022–23`
til `2025–26`, og spilletidsmodellen på `2020–21` til `2025–26`. Dermed brukes
den siste komplette sesongen i liveprognosen uten å blande refittet inn i
holdoutresultatene.

## Sammenligning på identiske folds

Gjennomsnitt av trening → validering for `2023–24` og `2024–25`. Den lange
historikken starter i `2020–21`, mens enkelte kandidater starter i `2022–23`:

| Modell | RMSE | Kandidat-RMSE | Topp-25 faktiske poeng | Kaptein |
|---|---:|---:|---:|---:|
| Lang historikk + 15-blads spilletidsmiks | **1,91254** | **3,07456** | **4,7908** | 6,9459 |
| Lang historikk + 7-blads spilletidsmiks | 1,91349 | 3,07575 | 4,7643 | 7,1216 |
| Tidligere tre-modellsensemble | 1,91715 | 3,08332 | 4,7286 | 7,1216 |
| Lang historikk + HGB | 1,91752 | 3,07974 | 4,7735 | 6,6892 |
| Extra Trees | 1,91970 | 3,09186 | 4,6919 | 6,7973 |
| Lang historikk + Ridge | 1,92271 | 3,08407 | 4,7124 | **7,7838** |
| Posisjonsspesifikk spilletidsmiks | 1,93014 | 3,10896 | 4,5616 | 6,1081 |

Kandidater er definert utelukkende fra historisk informasjon som spillere med
`minutes_avg5 >= 60`. Topp-25 og kaptein aggregeres først per spiller/Gameweek,
slik at doble runder ikke telles som to spillere.

Paired gameweek-bootstrap for vinneren mot tidligere ensemble:

- MSE-gevinst: `0,01810`
- 95 % intervall: `[0,00583, 0,02980]`
- 76 hele Gameweek-blokker

Intervallet er beskrivende etter at kandidaten ble valgt blant flere modeller;
det er ikke korrigert for modellseleksjon.

## Beslutningsbenchmark med FPL-regler

For GW6–38 i begge valideringssesongene ble hver modell koblet til historisk
pris, klubb og posisjon. Et eksakt MILP valgte 15 spillere, lovlig startellever
og kaptein innenfor £100m og maks tre spillere per klubb.

| Modell | Gameweeks | Faktiske poeng | Poeng per GW | Gj.sn. regret mot oracle |
|---|---:|---:|---:|---:|
| Tidligere tre-modellsensemble | 66 | **4 171** | **63,197** | **93,106** |
| Lang historikk + 7-blads spilletidsmiks | 66 | 4 166 | 63,121 | 93,182 |
| Lang historikk + 15-blads spilletidsmiks | 66 | 4 153 | 62,924 | 93,379 |

15-bladsmodellen endte `18` poeng bak incumbent, eller `-0,273` per Gameweek.
Paired bootstrap-intervall var `[-3,591, 2,970]` poeng per Gameweek. Det er for
bredt til å bevise at kandidaten er dårligere, men den passerer ikke kravet om
minst like god observert beslutningsscore.

En 75 % kandidatblend vant 99 poeng i `2023–24`, men tapte 77 poeng i
`2024–25`. Dette demonstrerer hvorfor vekten ikke bør velges retrospektivt fra
de samme sesongene.

Benchmarken er fortsatt en statisk ukeoptimering, ikke en full FPL-simulering:
den modellerer ikke transfers, autosubs, chips eller dynamisk lagverdi.
Historisk `value` er dessuten samlet etter Gameweek og er ikke en sertifisert
deadline-pris.

## Holdout 2025–26

| Modell | RMSE | MAE | Spearman | Kandidat-RMSE | Topp-25 |
|---|---:|---:|---:|---:|---:|
| Lang historikk + 15-blads spilletidsmiks | **1,93061** | **0,96009** | **0,71849** | **3,11541** | **4,3319** |
| Lang historikk + 7-blads spilletidsmiks | 1,93193 | 0,96241 | 0,71768 | 3,11647 | **4,3881** |
| Tidligere ensemble | 1,93332 | 0,96737 | 0,71443 | 3,12020 | 4,2941 |

Holdouten var allerede utforsket tidligere. Resultatet er en promoteringsport,
ikke et nytt, urørt bekreftelseseksperiment.

## Kritikk av det vi har

1. **Ingen sertifisert deadline-backtest.** Kilderevisjonen har 152 verifiserte
   bootstrap-snapshots, men null runder med komplett verifisert fixture- og
   historikksnapshot. Modellresultatene gjelder derfor pre-fixture timing.
2. **Små forskjeller.** Den nye modellen er bedre, men forbedringen er for liten
   til å omtales som et gjennombrudd.
3. **Feil mål alene.** Total RMSE domineres av nullpoeng. Tidligere modellvalg
   kontrollerte ikke at kjøpskandidater faktisk ble bedre. Benchmarken rapporterer
   nå kandidat-RMSE, topp-25, kaptein og NDCG i tillegg.
4. **Kaptein er svært ustabilt.** Ridge vant kapteinsmålet i validering selv om
   den tapte totalfeil og topp-25. Appen viser nå lav modellmargin i stedet for å
   fremstille små C/VC-forskjeller som sikre.
5. **Bare offentlig tilgjengelighet, ikke forventede minutter.** Skader og
   rotasjon er fortsatt den største manglende eksterne signalgruppen.
6. **Flerukersmodellen er foreløpig en sum av enkeltkamp-prognoser.** Den bruker
   informasjon kjent i dag og tar ikke høyde for prisendringer, skader eller ny
   informasjon som kommer mellom rundene.
7. **Salgspris og gratisbytter er estimater.** Den offentlige laglenken gir ikke
   de autentiserte fasitfeltene.
8. **Beslutningskvalitet er ustabil mellom sesonger.** En modell eller blend som
   vinner én sesong kan tape den neste. Produksjonsvalget er derfor konservativt.
9. **Historisk pris har svak timing.** Beslutningsbenchmarkens pris er ikke et
   verifisert deadline-snapshot.

Spilletidssannsynlighetene er nå eksplisitt kontrollert. 15-bladsvarianten har
validerings-log-loss `0,48833`, Brier for 60+ `0,08600` og 10-bins ECE
`0,00663`; i holdout er de henholdsvis `0,45727`, `0,08146` og `0,00563`.
Temperaturkalibrering ble også testet, men avvist fordi den forverret neste
sesongs sannsynligheter og poeng-RMSE.

## Kvantiler og risikoprofiler

En separat HGB-modell estimerer Q10, Q50 og Q90 for poengutfallet. Alle tre
kvantilene slo en posisjonsspesifikk, ubetinget baseline på pinball loss i begge
valideringssesongene og i 2025–26-testen. Q10–Q90 dekket `85,49 %` av etablerte
kandidater i validering og `85,01 %` i testen. Intervallet er et betinget
modellspenn, ikke et garantert konfidensintervall.

Tre beslutningsprofiler ble undersøkt med samme budsjettoptimering:

| Profil | Formel | Validering mot balanced | 2025–26 mot balanced |
|---|---|---:|---:|
| balanced | forventede poeng | – | – |
| stable | forventning − `0,1 × (Q90−Q10)` | **+85** | **+20** |
| upside | `0,7 × forventning + 0,3 × Q90` | +64 | −28 |

I 2025–26 løftet upside 90-persentilen for faktisk ukescore fra `76,0` til
`79,8`, men senket gjennomsnittet og økte standardavviket. Navnet beskriver
derfor reell hale-/variansatferd. `balanced` forblir standard fordi profilene
er eksplorative og den sekvensielle kontrollen under er ustabil mellom sesonger.

### Sekvensiell transferkontroll

Profilene er nå også testet fra samme starttropp med historisk korrekte,
rullerende gratisbytter: maksimum to i `2023–24`, maksimum fem fra `2024–25`,
og påfyll til fem etter GW15 i `2025–26`. Simulatoren håndterer dynamisk bank,
individuell salgspris, kapteinreserve og formasjonsgyldige autosubs. En eksakt
MILP velger null til N samtidige bytter, sluttropp, XI og kaptein samlet. En
egen kontroll med N=1 gir identiske totalsummer som det uttømmende
enkeltbyttesøket.

| Min. modellgevinst per brukt bytte | balanced | stable | upside |
|---:|---:|---:|---:|
| 0,0 | 5 631 | **5 773** (+142) | 5 565 (−66) |
| 1,0 | 5 502 | **5 740** (+238) | 5 577 (+75) |
| 2,0 | **5 563** | 5 424 (−139) | 5 543 (−20) |

Ved terskel `0,0` tapte stable fortsatt 57 poeng i `2023–24`, vant 190 i
`2024–25` og vant 9 i `2025–26`. Ved `1,0` vant stable alle tre sesonger
(`+18`, `+91`, `+129` mot balanced), men ved `2,0` tapte den 139 samlet.
Dette viser både at rulling/flerbytter kan endre konklusjonen og at
alternativkostnaden er en svært sensitiv policyparameter. Fordi tersklene er
inspisert på de samme tre sesongene, ville det være etterpåtilpasning å
promotere `stable + 1,0` nå. `balanced` forblir produksjonsstandard.

Simulatoren er fortsatt nærsynt: beslutningen bruker bare neste Gameweek og
historisk pris er samlet etter runden, ikke ved deadline. Neste beslutningssteg
er derfor en ekte rullerende 3–6-GW-plan med kun informasjon som var kjent ved
hver deadline, evaluert prospektivt.

## Hva researchen endret

[OpenFPL](https://arxiv.org/abs/2508.09992) viser verdien av prospektiv testing,
posisjonsspesifikke ensembler, offentlige FPL/Understat-data og egne prognoser
for én, to og tre runder. Vi testet posisjonsspesifikke modeller i stedet for å
anta at de ville vinne; de tapte på våre data. Flerukersprognoser er likevel
implementert fordi kjøp og salg er flerukersbeslutninger.

Forskning på [prediksjon + heltallsoptimering](https://arxiv.org/abs/2505.02170)
understreker at prediksjonsfeil ikke er det samme som beslutningskvalitet, og at
usikkerhet kan inngå eksplisitt i lagvalg. Dagens app håndhever FPL-reglene, men
har ennå ikke robust scenariooptimering. Scikit-learn støtter
[kvantilmodeller og prediksjonsintervaller](https://scikit-learn.org/stable/auto_examples/ensemble/plot_hgbt_regression.html),
som er en naturlig neste utvidelse utover spilletidssannsynlighetene.

Kilderepoet advarer også eksplisitt om at historisk `xP` kan inneholde
post-match-informasjon. Det feltet er derfor ikke brukt som modellfeature.

Premier Leagues offisielle dokumentasjon viser at grensen ble økt fra to til
[fem oppsparte gratisbytter i 2024–25](https://www.premierleague.com/en/news/4059225),
og at alle lag ble fylt opp til fem umiddelbart etter GW15-deadline i 2025–26
på grunn av [AFCON](https://www.premierleague.com/en/news/4461660). Begge
historiske regimeskiftene er nå eksplisitt kodet i simulatoren; en universell
femgrense ville gitt feil kontroll for `2023–24`.

## Implementert og neste prioritering

- Reproduserbar benchmark: `src/nextgen_models.py`
- Eksakt budsjett-/laguttaksbenchmark: `src/decision_backtest.py`
- Kronologisk kvantilbenchmark: `src/uncertainty_models.py`
- Profilbenchmark: `src/risk_profiles.py`
- Sekvensiell transfer-/autosubsimulator: `src/season_simulator.py`
- Globalt optimalt første tobytteforslag over 1–3 GW i beslutningsappen
- Beslutningsvoktet refit: `src/production_models.py`
- Automatisk prediksjons- og beslutningsport med sporbare modellmetadata
- Live modellvelger som bare bruker refittede produksjonsartefakter
- 1–3 Gameweek liveprognoser fra samme tidsstemplede snapshot
- sannsynlighet for 60+ minutter fra spilletidsmodellen
- gjenbruk av siste råsnapshot ved modellendringer, uten 659 nye API-kall
- fortsatt automatisk scoring av frosne prognoser når fasit blir tilgjengelig

Neste prioritet er å samle nok ekte fremoverskuende deadline-prognoser til en
prospektiv evaluering. Deretter bør den nærsynt sekvensielle simulatoren utvides
til en rullerende flerukersoptimerer, og forventede minutter/tilgjengelighet
kalibreres mot disse snapshottene.
