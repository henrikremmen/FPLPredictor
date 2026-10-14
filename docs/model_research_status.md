# Modellarbeid: status 10. oktober 2026

## Oppfølging 14. oktober 2026

Siste kravkontroll: alle fire låste GW7-prognosepakker består hashkontroll.
FPL markerer GW6 ferdig/kontrollert og GW7 uferdig/ukontrollert. GW7-deadline
er 17. oktober kl. 12 norsk tid. Fremtidig poeng-, rolle- og beslutningstest
kan derfor ennå ikke kjøres. Separate rolleprognoser, Understat/Elo-tester og
komponentbidrag er implementert, men bedre prediksjoner er ikke bekreftet.
Skadeforløpet er fortsatt et datert scenario som mangler empirisk kalibrering.
Historiske tester mangler fortsatt tilstrekkelig dokumentasjon fra før
deadline. Målet er aktivt og ikke fullført; omtalen av blokkert status nederst
gjelder kontrollen 10. oktober, før det nye GW6-arbeidet.

Ny kronologisk komponenttest beholder DEFCON-poengene: trening på tidligere
sesonger og GW1–18 i 2025/26, test GW20–38, med kampdato som ekstra grense
for trening. Komponent v2 har RMSE 1,8404 mot markedsreferansens 1,8411,
men MAE er svakere (0,9279 mot 0,9213) og kapteinsgjennomsnittet lavere
(4,947 mot 5,263). Topp-25-snittet er bedre (4,714 mot 4,505).
Dette er blandede resultater, ikke grunnlag for produksjonsbytte.
Testen er retrospektiv og ikke deadline-sertifisert. Kjørbar kode:
`src/component_current_rules_benchmark.py`; rapport, identiske spillerkohorter
og komponentbidrag: `artifacts/model_research/component_current_rules/`.
Bidragenes sum er kontrollert mot poengprognosen på alle testradene.

Lovlige lagvalg på samme testsett er også evaluert: komponent v2 fikk 1117
poeng mot referansens 1116 over 19 runder. Gjennomsnittlig gevinst er 0,053
poeng/runde, med bootstrap-intervall 95 % fra −4,632 til +4,895. Modellen
vant 9 runder og tapte 10. Dette dokumenterer ingen tydelig beslutningsgevinst.
Testen velger en ny tropp til 100 millioner, lovlig ellever og kaptein hver
runde; historiske priser er etter runden og overganger/autosubs/chips inngår
ikke. Resultater: `component_current_rules/decision_report.json` og
`decision_gameweeks.csv`. Reproduser fra lagrede prognoser med
`.venv/bin/python src/component_current_rules_benchmark.py --decisions-only`.

Appens lagrede tilgjengelighetsjustering er også sammenlignet på identiske
667 GW6-spillere: MAE 0,987 mot 1,082 ujustert, RMSE 1,988 mot 2,037.
Justeringen endret 212 prognoser, men økte samlet undervurdering fra 0,093
til 0,202 poeng. Dette er én rundes diagnostikk, ikke dokumentasjon på
generell forbedring eller kalibrert skadeforløp. Resultater og faste
sannsynlighetsgrupper ligger i `gw6_observed_20261014/availability_calibration.json`
under `artifacts/model_research`. Prospektiv evaluering inkluderer nå samme
faste grupper for deltakelse og 60+ minutter. To grensetester og alle ti
prospektive tester består. Ingen kalibrator er tilpasset GW6-resultatene.

GW6 er nå `finished=true` og `data_checked=true`. De lagrede ujusterte
produksjonsprognosene fra 9. oktober er sammenlignet med offisielle sluttutfall
for alle 667 spillere: MAE 1,082, RMSE 2,037 og gjennomsnittlig bias −0,093.
Rapport, scorede rader og rå API-svar med kilde/tid/hash ligger i
`artifacts/model_research/gw6_observed_20261014/`. Prognosefilens registrerte
tid er før deadline, men en hash av prognosefilen fra før deadline er ikke
verifisert; rapporten er derfor diagnostisk. Appens skadejustering er ikke
anvendt her, og GW7-utfordrerne er ikke evaluert med disse resultatene.
352 spillere fikk null minutter, 109 fikk 1–59 og 206 fikk minst 60.
Sistnevnte gruppe hadde MAE 2,196. Gruppering etter faktisk spilletid er
diagnostikk; gruppenes bias alene beviser ikke feilkalibrering, siden
prognosene før kampen inkluderer usikkerhet om spilletid.

Evalueringsrapporten viser nå poengfeil separat for observerte 0, 1–59 og
60+ minutter. Hver gruppe har antall, gjennomsnittlig prognose og faktisk
poengsum, signert bias (prognose minus utfall), MAE og RMSE. Dette skiller
overvurdering av fraværende spillere fra feil blant spillere som faktisk
spiller. Gruppene er diagnostikk etter kampen, ikke treningsinformasjon eller
startetiketter. Tomme grupper får ingen oppdiktede feilverdier.
Alle ti tester for prospektiv låsing/evaluering/lagvalg består, inkludert
tester av at observerte minutter brukes selv når frosne input har andre
minutter. Ingen låste prognoser eller produksjonsmodeller er endret.

Produksjonsmodellen er uendret. Ingen utfordrer har tilstrekkelig dokumentasjon
til å overta. [Detaljrapport](model_research_2026-10-10.md).

| Mål | Implementert og kontrollert | Gjenstår |
|---|---|---|
| Spilletid og skader | Separate start/innhopp/fravær-prognoser; datert returscenario per kamp; scenario vist i spillerpanelet | Måle rolle- og skadeprognoser på fremtidige utfall; kalibrere skadeforløp før det påvirker anbefalingene |
| Understat | 810 kamper, 24 595 spillerkamper; skudd uten straffer, skuddsoner, kvalitet og angrepsandel; egne leverandørkolonner | Bedre ID-dekning og flere sesonger med skudddata; prospektiv bekreftelse av eventuell gevinst |
| Elo | Lang historikk over sesonggrenser; testet med/uten odds og sammen med Understat | Bekrefte tilleggsverdi på fremtidige runder |
| Komponentmodell | V2 med forklarbare bidrag og samsvar mellom forventning/simulering; defensive bidrag med i fremtidig modell | Sammenligning under dagens regler på fremtidige utfall; ingen produksjonsgodkjenning ennå |
| Evaluering | Kronologiske diagnostiske tester, lovlige lagvalg, låste GW7-prognoser og resultatverktøy | Historiske kamp-/historikkversjoner mangler predeadline-bevis; GW7 har ennå ingen ferdige resultater |

## Hva resultatene viser

- Understat-skuddfeatures gir marginalt bedre RMSE i 2025/26, men svakere MAE
  og svakere kapteinsmål. Det er ikke en entydig forbedring.
- I en statisk test med ny lovlig tropp hver runde ga Understat −50 poeng,
  Elo +11 og kombinasjonen +70 over 33 runder. Alle usikkerhetsintervallene
  inkluderer null gevinst. Testen bruker historiske priser etter runden.
- Komponentmodell v2 gir marginalt bedre RMSE enn v1 i tre sesonger.
  Dette alene viser ikke at den slår produksjonsmodellen under dagens regler.
- Deadline-auditen godkjenner null komplette historiske runder: deadlines og
  registre er dokumentert, men ikke tilstrekkelige fixture-/historikkversjoner.
  Diagnostiske resultater må derfor ikke omtales som sertifiserte deadline-tester.

## Låste fremtidige tester

Alle bundlene under gjelder GW7, deadline **17. oktober kl. 10:00 UTC**.
FPL-grunnlaget er snapshotet fra 9. oktober; nye Understat-data ble hentet
10. oktober. Prognosene er tidlige, ikke siste nyheter rett før deadline.

- `artifacts/prospective/gw7_sources_20261010`: referanse, Understat, Elo, begge.
- `artifacts/prospective/gw7_components_20261010`: referanse, rollemodell og
  komponentmodell med defensive bidrag.
- `artifacts/prospective/gw7_injury_20261010`: referanse, konstant skadejustering
  og datert returscenario. Returscenarioet endrer 17 spillerprognoser i GW7.
- `artifacts/prospective/gw7_decisions_with_injury_20261010`: låste tropper,
  ellevere og kapteiner for alle åtte varianter. Alle lagregler og hasher
  er kontrollert. Skadescenarioene gir samme startellever i denne runden.

Rollemodellens poeng er foreløpig lik referansen; dens nye utfall er
sannsynlighetene. Skadescenarioet er en eksplisitt antakelse, ikke en kalibrert
retursannsynlighet. Låsingen bruker lokale tider og hasher, ikke en uavhengig
tidsstemplingstjeneste. Den dokumenterer reproduserbarhet og hindrer utilsiktet
overskriving, men er ikke bevis for historisk treningsdatakvalitet.

## Når GW7 er ferdig

Bruk et nytt komplett FPL-snapshot der GW7 er `finished` og `data_checked`.
Resultatverktøyene avviser uferdige eller manglende utfall. Bruk nye
resultatmapper; låste prognoser og tidligere rapporter skal ikke overskrives.

```sh
.venv/bin/python src/prospective_evaluation.py FORECAST_BUNDLE FULLFORT_SNAPSHOT NY_RESULTATMAPPE
.venv/bin/python src/prospective_decisions.py artifacts/prospective/gw7_decisions_with_injury_20261010 FULLFORT_SNAPSHOT NY_BESLUTNINGSRAPPORT
```

Den første kommandoen kjøres for hver av de tre forecast-bundlene ovenfor.
Poeng, minuttbånd og roller evalueres separat. Lagvalgene scores uten ny
optimalisering. Overganger, autosubs, chips og dynamisk lagverdi er ikke med
i denne statiske beslutningstesten.

## Verifikasjon

Samlet backend-kjøring: 136 tester bestått før siste scenariolås. Den nye
scenariojusteringen har i tillegg en egen test; alle fem skadescenariotester
består. Frontend-build og seks Playwright-workspace-tester består. Låste
modellprognoser er gjenskapt fra kopierte modeller/features, og samtlige åtte
låste tropper er kontrollert separat.

Målet er ikke fullført. Fremtidige resultater og bedre tidsfestet historikk
kan ikke erstattes av flere tester på de samme retrospektive dataene.


## Ekstern ventebetingelse bekreftet

FPLs offisielle API ble kontrollert 10. oktober 2026 kl. 19:34 UTC:
GW7 er neste runde, `finished=false` og `data_checked=false`.
Deadline er fortsatt 17. oktober kl. 10:00 UTC. Alle fire forecast-bundler
og de åtte låste lagvalgene består ny hashkontroll. Kontrollrapport:
`artifacts/model_research/prospective_readiness_20261010.json`.

Den samme mangelen på fremtidige utfall er bekreftet over flere arbeidsrunder.
Målet er blokkert på ekstern datatilgang, ikke fullført. Neste nødvendige
hendelse er ferdige, kontrollerte GW7-resultater. Historiske evalueringer
har fortsatt en separat begrensning: tidsfestede fixture-/historikkversjoner
mangler. Videre kalibrering og eventuell produksjonsendring må vente på
sterkere evalueringsgrunnlag. Ingen automatisk oppfølging er installert.
