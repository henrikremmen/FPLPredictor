# Produktresearch: neste features for FPL Modell

Oppdatert 19. september 2026.

## Kort konklusjon

Appen har allerede mye av funksjonaliteten som normalt utgjør en FPL-hub:
lagimport, prognoser, laguttak, transferoptimalisering, flerukersplan, chips,
Free Hit-/Wildcard-lag, prisvarsler, managerhistorikk, miniliga og effective
ownership. Det viktigste neste steget er derfor ikke flere isolerte tabeller.

Bygg et **beslutningsverksted** som gjør modellens råd forståelige, redigerbare
og robuste:

1. forklar poengprognosen per spiller og kamp;
2. sammenlign spillere og «hold mot bytte» direkte;
3. la brukeren låse, ekskludere og planlegge bestemte spillere/bytter;
4. test rådet mot usikre minutter og små modellendringer;
5. vis hva som har endret seg siden forrige oppdatering før deadline.

Dette er høyere verdi enn å prioritere en full live-scoreklone. FPL tilbyr nå
selv live miniligaer, projisert bonus, flere squad-visninger og en offisiell
Price Change Predictor. En lokal analyseapp bør vinne på beslutningskvalitet og
transparens, ikke kopiere funksjoner brukeren allerede har i FPL.

## Metode og begrensning

Gjennomgangen kombinerer:

- offisielle FPL-endringer og regler for 2026/27;
- funksjonene i etablerte verktøy som FPL Review, LiveFPL og Fantasy Football
  Scout;
- eksplisitte ønsker og kritikk i FPL-miljøet på Reddit;
- en kode- og funksjonsrevisjon av denne appen.

Reddit-funnene er kvalitative signaler, ikke en representativ brukerundersøkelse.
Konkurrentenes funksjoner viser hva erfarne brukere har lært å forvente, men er
heller ikke bevis på effekt. Nye features må derfor måles prospektivt.

## Hva folk egentlig prøver å få gjort

### Før deadline

Brukeren vil først og fremst ha svar på fem beslutninger:

1. Skal jeg rulle eller gjøre et bytte?
2. Er en hit verdt fire poeng?
3. Hvem skal starte, benkes, være kaptein og visekaptein?
4. Er planen fortsatt riktig etter siste skade-, lag- eller prisnytt?
5. Hva ødelegger jeg i senere Gameweeks hvis jeg gjør dette nå?

Et treffende community-svar til en apputvikler var at det avgjørende er hva
brukeren åpner appen for fredag kveld: kaptein og om en hit er verdt det, ikke
minispill rundt FPL. Andre gjentakende ønsker er å bla fram i Gameweeks med
fixtures synlig på pitch, og bedre informasjon om forventede lagoppstillinger
og startplass.

### Når brukeren er uenig med modellen

Erfarne spillere ønsker ikke bare én fasit. De vil kunne uttrykke kunnskap og
preferanser uten å overta hele beregningen manuelt:

- «Jeg tror denne spilleren starter.»
- «Denne spilleren skal jeg beholde uansett.»
- «Ikke kjøp spillere fra dette laget.»
- «Jeg vil ha denne spilleren inn i GW8, hvordan kommer jeg dit?»
- «Vis beste plan uten spiller X og kostnaden ved det valget.»

FPL Review støtter nettopp editable expected minutes, lock/exclude, planlagte
framtidige bytter, alternative solve-linjer og egne solverinnstillinger. Dette
er ikke pynt; det gjør optimaliseringen til et verktøy for brukeren i stedet
for en svart boks.

### Etter deadline og på kampdag

Brukere ønsker live rank, EO, bonus, defensive contributions, miniligasvinger
og «hva hvis»-rank. Dette er populære funksjoner, men har lavere strategisk
prioritet her fordi:

- appen har allerede historikk, liga-EO og rankanalyse;
- den offisielle FPL-appen tilbyr nå live ligaoppdateringer og projisert bonus;
- LiveFPL og flere andre verktøy er spesialiserte på sanntidsopplevelsen.

Et lett matchday-lag kan være nyttig senere, men bør ikke forsinke features som
forbedrer faktiske valg før fristen.

## Gap mot dagens app

| Behov | Status nå | Gap |
|---|---|---|
| Import og korrigering av faktisk lag | God | Ingen kritisk mangel |
| Beste XI, benk, C/VC | God | Mangler sannsynlig autosub-/VC-verdi |
| Ett eller flere bytter | God | Mangler tvungne valg, hold-sammenligning og robusthet |
| Flerukersplan | God | Mangler interaktiv redigering, lagrede utkast og scenarier |
| FH/WC/chips | God | Mangler robusthetsandel og tydelig komponentforklaring |
| Miniliga, EO og rank-risk | God | Kan senere få sannsynlighetsbasert ligasimulator |
| Prisvarsler | Delvis god | Mangler varselmotor og «vent mot kjøp nå»-kostnad |
| Skader og minutter | Delvis | Ingen brukerstyrt xMins eller tydelig nyhetsdiff |
| Hvorfor spilleren får X poeng | Svak | Markedssignaler finnes i data, men totalen brytes ikke ned i UI |
| Sammenlign spillere | Mangler | Ingen side-by-side sammenligning eller hold-vs-buy |
| Modellrobusthet | Mangler | Q10/Q90 finnes, men beslutningen stresstestes ikke |
| Modellens historiske kvalitet | Delvis internt | Ingen enkel accuracy-/kalibreringsside for brukeren |
| Hva endret seg siden sist | Mangler | Snapshots finnes, men presenteres ikke som beslutningsdiff |
| Live matchday | Mangler | Nyttig, men lavere differensiering etter FPLs 2026/27-oppdatering |

## Prioritert feature-backlog

Skala: bruker-/beslutningsverdi 1–5, dataklarhet 1–5 og innsats S/M/L/XL.

| Prioritet | Feature | Verdi | Dataklarhet | Innsats | Hvorfor nå |
|---|---|---:|---:|---|---|
| P0 | Prognoseforklaring og spillersammenligning | 5 | 4 | M | Gjør hvert modellråd forståelig og kontrollerbart |
| P0 | Lås/ekskluder/tving spiller og framtidig bytte | 5 | 5 | M | Gjør eksisterende solver praktisk for ekte planer |
| P0 | Robusthets- og sensitivitetsanalyse | 5 | 4 | L | Skiller stabile råd fra marginale modellutslag |
| P0 | Deadline-diff: «hva endret seg?» | 5 | 4 | M | Retter oppmerksomheten mot ny informasjon som kan endre valget |
| P0 | xMins-/startplasspanel med manuell override | 5 | 3 | M | Minutter er ofte den største enkeltusikkerheten |
| P1 | Sannsynlige autosubs og visekapteinverdi | 4 | 4 | L | Verdsetter benken korrekt ved rotasjonsrisiko |
| P1 | Fixture-grid og rotasjonspar | 4 | 5 | M | Et gjentakende brukerønske og svært lett å forstå visuelt |
| P1 | Lagrede utkast og side-by-side planer | 4 | 5 | M | Lar brukeren sammenligne WC/FH/transferidéer uten å miste arbeid |
| P1 | Beslutningslogg og shadow-season | 4 | 5 | M | Måler råd mot informasjonen som fantes ved deadline |
| P1 | Accuracy- og kalibreringsdashboard | 4 | 4 | M | Bygger tillit og avslører hvilke komponenter som må forbedres |
| P1 | Blank/double-scenarier med sannsynlighet | 4 | 2 | L | Verdifullt for chips, men usikre terminlister må merkes tydelig |
| P2 | Lokale/push/e-postvarsler | 3 | 3 | L | Nyttig når det finnes en god endringsmotor; støy uten terskler |
| P2 | Live rank, bonus, DC og event-impact | 3 | 4 | L | Populært, men allerede godt dekket offisielt og av LiveFPL |
| P2 | Mini-liga Monte Carlo | 3 | 3 | L | Relevant sent i sesongen, mindre viktig tidlig |
| Ikke nå | Generisk AI-chat og innholdssammendrag | 2 | 2 | L | Kan høres smart ut uten å forbedre en konkret beslutning |

## P0: konkret produktspesifikasjon

### 1. «Hvorfor 5,4 poeng?» og spillersammenligning

Klikk på en spiller hvor som helst i appen og åpne et detaljpanel med:

- forventede minutter, start- og 60+-sannsynlighet;
- mål, assist, clean sheet, keeperredninger, bonus og defensive contributions;
- poeng per kommende Gameweek og samlet horisont;
- markedsestimat mot modellestimat;
- Q10, median og Q90 med en forklaring i vanlig språk;
- datatidspunkt og kilder;
- form-/rolletrend uten å blande faktisk resultat inn i forventede poeng.

Fra panelet skal brukeren kunne velge **Sammenlign** og få spiller A mot B:

- pris og salgspris;
- xPts i 1/3/5 Gameweeks;
- xMins og startusikkerhet;
- fixture-forløp;
- sannsynlige poengkilder;
- eierskap/EO og prisretning;
- direkte «hold A» mot «A → B», inkludert FT/hit og framtidig plan.

Viktig modellarbeid: totalprognosen må dekomponeres av den samme poengmotoren
som lager totalen. Ikke vis en illustrativ breakdown som ikke summerer til
modellpoengene.

**Akseptansekriterium:** alle viste komponenter summerer til total forventning
innen avrunding, og spillersammenligningen viser netto planforskjell etter hit.

### 2. Interaktiv solver

Legg kontrollene direkte i Flerukersplan, FH og WC:

- lås eide spillere;
- ekskluder spillere eller klubber;
- krev spiller X inn innen valgt GW;
- krev spiller X ut i valgt GW;
- tving et konkret framtidig bytte;
- sett maks keeperpris eller maks forsvarseksponering per klubb;
- velg 3–5 alternative planer innen for eksempel to poeng fra optimum;
- lagre og navngi utkast lokalt.

Vis alltid kostnaden ved brukerens constraint: «Dette ønsket koster 1,3
forventede poeng over fire GW». Det hindrer at modellen presenterer et tvunget
valg som sitt eget optimale råd.

**Akseptansekriterium:** constraints håndheves i hele horisonten, alternativene
er lovlige, og UI skiller modelloptimum fra brukerbegrenset optimum.

### 3. Robusthetsanalyse

Kjør 20–100 alternative solves hvor plausible input varierer:

- forventede minutter, mer for rotasjonsutsatte spillere;
- angreps- og forsvarsstyrke;
- mål-, assist- og clean-sheet-komponenter;
- eventuelt planleggingsparametere som framtidsdiskontering og FT-verdi.

Rapporter:

- hvor ofte hvert rotbytte er førstevalg;
- hvor ofte hver spiller er i FH/WC-laget;
- median, P10 og P90 for planens fordel over hold;
- «robust», «åpent valg» eller «fragilt råd»;
- hvilke antakelser som oftest snur beslutningen.

Eksempel: «Konsa beholdes i 78 % av scenariene. Salg blir best dersom forventet
startandel faller under 62 %.»

**Akseptansekriterium:** resultatet er reproduserbart med lagret random seed,
viser minst 20 solves og må ikke omtale 51 % som et sikkert råd.

### 4. Deadline-diff

Snapshots er allerede tidsstemplet. Gjør forskjellene handlingsrettede:

- nye eller endrede skadeflagg;
- endring i xMins/startandel;
- flyttet kamp, blank eller double;
- vesentlig oddsbevegelse i lagmål/clean sheet;
- prisprognose som krysser terskel;
- rolleendring på straffer/dødballer;
- endret anbefalt XI, kaptein, transfer eller chip;
- endring i prognose over en terskel, for eksempel 0,5 poeng.

Strategisenteret bør begynne med «Siden sist» og bare vise materiale. Råstøy i
odds eller eierskap skal ikke bli et varsel.

**Akseptansekriterium:** hver endring viser før, etter, tidspunkt, kilde og om
det faktisk endret en anbefaling.

### 5. Expected minutes og menneske-i-løkken

Vis modellens minutter per spiller og Gameweek. La brukeren midlertidig endre:

- startsannsynlighet;
- forventede minutter gitt start;
- cameo-sannsynlighet;
- tilgjengelighet;
- straffe-/dødballrolle.

Deretter beregnes prognose og planer på nytt, tydelig merket «dine antakelser».
En reset-knapp går tilbake til modellens verdier. Overrides må lagres med
tidspunkt og aldri blandes inn i treningsdata som sannhet.

Automatisk predicted-lineup-data bør først påvirke produksjonsmodellen etter
prospektiv validering. Før det kan den vises som separat kilde og avvikssignal.

## P1: features som bygger videre på P0

### Sannsynlige autosubs og benkeverdi

Dagens lineære laguttak bør suppleres med en sannsynlighetsmodell som verdsetter
at startere kan utebli, at benkerekkefølgen må bevare lovlig formasjon, og at
visekapteinen bare dobles dersom kapteinen ikke spiller. Vis både rå XI-xPts og
total forventning etter autosubs.

### Fixture-grid og rotasjon

Lag en horisontal 3–10 GW-matrise med motstander, hjemme/borte, individuell xPts,
lagmål, clean-sheet-sannsynlighet og blank/double. Pitch-visningen skal kunne
flyttes fram én GW om gangen. En rotasjonsmodus finner hvilke to eller tre
budsjettspillere som komplementerer hverandres fixtures og xPts.

### Lagrede utkast

Brukeren bør kunne beholde «Plan A», «Plan B», «Wildcard nå» og «Wildcard GW8»
side om side. Vis total xPts, hits, FT brukt/beholdt, bank, usikkerhet og hvilke
spillere som skiller planene. Utkast kan lagres lokalt uten konto.

### Beslutningslogg og accuracy

Frys følgende før hver deadline:

- prognoser og komponenter;
- modellens førstevalg og alternativer;
- brukerens valgte plan hvis den registreres;
- datakilder og tidspunkt.

Etter runden evalueres kalibrering, ikke bare poeng: P(start), P(60+), P(clean
sheet), P(mål), P(assist), DC-terskel og prognoseintervaller. Skill tilfeldige
enkeltresultater fra systematisk feil. Dette er også grunnlaget for å vite om
framtidige features faktisk gjør appen bedre.

## Datakilder og gjennomførbarhet

| Feature | Kan bygges fra dagens data? | Nytt behov |
|---|---|---|
| Spillersammenligning | Ja, i stor grad | Konsistent poengdekomponering per GW |
| Lock/exclude/forced moves | Ja | Nye solver-constraints og API-kontrakt |
| Sensitivitet | Ja | Simuleringslag, seeds, kø/progress |
| Deadline-diff | Ja, snapshots finnes | Normalisert diff og materialitetsterskler |
| xMins override | Delvis | Per-GW minutes-komponent og lokal override-lagring |
| Predicted lineups | Nei | Lisensiert kilde, manuell input eller validert ny feed |
| Autosubs | Delvis | Sannsynlig start/cameo og felles scenariofordeling |
| Fixture-scenarier | Delvis | Cup-/TV-sannsynligheter og eksplisitt scenarioformat |
| Pushvarsler | Nei | Bakgrunnsjobb og valgt kanal; lokale varsler kan komme først |
| Live matchday | Ja, offentlig live-feed | Polling/cache og robust håndtering av scorekorreksjoner |

Odds skal fortsatt brukes som markedsprior i modellen, ikke vises som sannhet.
Predicted lineups og nyhetstolkning må tidsstemples og måles mot faktiske
startere. Ingen ekstern feed bør få produksjonsvekt bare fordi den intuitivt
virker riktig.

## Foreslått leveranserekkefølge

### Fase A: forklar og sammenlign

1. Poengdekomponering i forecast/API.
2. Klikkbart spillerpanel.
3. To-spiller- og hold-vs-transfer-sammenligning.
4. Datakilde, sist oppdatert og usikkerhetsforklaring.

### Fase B: la brukeren styre planen

1. Lock/exclude.
2. Tvungne framtidige trekk.
3. Alternative planer og opportunity cost.
4. Lagrede lokale utkast.

### Fase C: gjør rådene robuste

1. Sensitivitet på xMins og prognosekomponenter.
2. Robusthetsandel i transfers, FH og WC.
3. Deadline-diff.
4. Manuelle xMins-overrides.

### Fase D: forbedre realismen

1. Sannsynlige autosubs/VC.
2. Fixture- og rotasjonsvisning.
3. Blank/double-scenarier.
4. Prospektiv predicted-lineup-pilot.

### Fase E: tillit og oppfølging

1. Beslutningslogg.
2. Accuracy- og kalibreringsdashboard.
3. Varsler med materialitetsterskler.
4. Et begrenset matchday-lag hvis brukerne fortsatt etterspør det.

## Hva som bør måles

Produktbruk alene er ikke nok. Mål både om funksjonen brukes og om rådene blir
bedre:

- andel anbefalinger hvor brukeren åpner «hvorfor»;
- andel planer hvor lock/exclude brukes;
- hvor ofte toppvalget er robust i minst 70 % av scenariene;
- netto forventet gevinst og faktisk beslutningsregret for hold/bytte;
- kalibrering av minutter og poengkomponenter;
- hvor ofte deadline-diff oppdager en materiell endring;
- varsler åpnet kontra ignorert;
- tid fra «Last inn lag» til en ferdig, forstått beslutning;
- shadow-season-resultat med kun informasjon tilgjengelig før deadline.

## Kilder

- Premier League, nye FPL-funksjoner 2026/27:
  https://www.premierleague.com/en/news/4679873
- Premier League, defensive contributions 2026/27:
  https://www.premierleague.com/en/news/4361991
- FPL Review, produktets utvikling og kjernefunksjoner:
  https://docs.fplreview.com/getting-started/about-fplreview/
- FPL Review, sensitivity analysis:
  https://docs.fplreview.com/the-model/solvers/sensitivity-analysis/
- FPL Review, forced decisions:
  https://docs.fplreview.com/the-model/solvers/forced-decisions/
- FPL Review, expected minutes:
  https://docs.fplreview.com/the-model/projections/xmins/
- FPL Review, full kontra lineær evaluering/autosubs:
  https://docs.fplreview.com/the-model/solvers/evaluation-score/
- LiveFPL, planner- og matchday-funksjoner:
  https://www.livefpl.com/
- Fantasy Football Scout, spiller-/lagsammenligning:
  https://www.fantasyfootballscout.co.uk/how-to-use-the-comparison-tool-in-the-members-area
- OpenFPL, prospektivt evaluert åpen prognosemetode:
  https://arxiv.org/abs/2508.09992
- Reddit, ønske om framtidige GW-visninger og fixtures i planner:
  https://www.reddit.com/r/FantasyPL/comments/16mn1o2/featuresimprovements_to_fpl/
- Reddit, etterspørsel etter predicted lineups/startplass:
  https://www.reddit.com/r/FantasyPL/comments/1mdz513/where_does_everyone_get_their_info_on_predicted/
- Reddit, produktkritikk: hjelp med kaptein/hit framfor sidefunksjoner:
  https://www.reddit.com/r/fplAnalytics/comments/1teqgok/built_an_ios_app_for_fpl_fans_because_i_got_tired/

