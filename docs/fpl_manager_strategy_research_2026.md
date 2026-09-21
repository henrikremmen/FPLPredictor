# Research: hvordan appen kan bli en bedre FPL-manager

Oppdatert 18. september 2026. En god spillerprognose, en god beslutningsmotor og
en god ukentlig arbeidsflyt er tre forskjellige ting. Lav RMSE alene styrer ikke
et FPL-lag godt.

## Konklusjon

Appen bør optimalisere **beslutninger over tid**, ikke bare vise spillerne med
høyest forventede poeng. Den mest verdifulle managerhjelpen er:

1. et eksplisitt valg mellom å rulle, bytte og ta hit;
2. flerukersplanlegging med ny beregning før hver frist;
3. robusthet mot usikre minutter, skader og modellfeil;
4. kapteinsvalg med margin og risiko, ikke bare nummer én på en liste;
5. offisielle prisvarsler uten å oppmuntre til blinde tidlige bytter;
6. chips vurdert mot alternativet og framtidig opsjonsverdi;
7. en prioritert fristsjekkliste som sier hva manageren faktisk skal gjøre.

Strategisenteret som nå er bygget inn i appen dekker punkt 1, 2, 4, 5 og 7,
og deler av punkt 3 og 6.

## Hva forskning og de beste managerne peker på

### Tålmodighet og bankede bytter har reell verdi

2025/26-vinner Erik Ibsen tok ingen poengtrekk, gjorde null bytter i 15 av 38
runder og brukte bankede bytter til større, koordinerte endringer. Dette beviser
ikke at hits alltid er feil, men støtter at modellen bør kreve klar margin før
den anbefaler minuspoeng. Kilde:
[FPL champion: The secrets to my success](https://www.premierleague.com/en/news/4671784).

Konsekvens for appen:

- «Rull» må være et reelt alternativ i samme optimering som ett eller flere
  bytter.
- En hit bør ikke godtas fordi punktestimatet er 0,1 bedre etter trekket.
  Strategisenteret sammenligner nå hit-planen med en hit-fri plan og krever 2,0
  ekstra modellpoeng per betalt bytte etter at −4 allerede er trukket.
- Fleksibilitet er særlig verdifull rundt skader, terminlisteendringer og
  planlagte premiumbytter.

### Planlegg i blokker, men ikke lat som framtiden er sikker

Vinneren beskrev at han planla spillere og premiumendringer i blokker av
Gameweeks. En stor studie av rundt én million FPL-managere fant også at
langsiktig planlegging og jevnt gode beslutninger skilte sterke managere fra
svakere. OpenFPL viser samtidig nytte av prospektive prognoser over én til tre
runder.

Kilder:

- [Identification of skill in an online game](https://arxiv.org/abs/2009.01206)
- [OpenFPL](https://arxiv.org/abs/2508.09992)
- [Championens transferstrategi](https://www.premierleague.com/en/news/4671982/fpl-champion-how-to-build-the-perfect-squad-and-make-the-best-transfers)

Konsekvens for appen:

- Tre til fem GW er normalt en bedre operativ horisont enn én eller åtte.
- Senere uker bør diskonteres.
- Planen må beregnes på nytt etter hver deadline, prisendring, skade og
  terminlisteendring. Et veikart er ikke en kontrakt.
- Appen bør etter hvert vise planens stabilitet på tvers av scenarier, ikke bare
  ett deterministisk optimum.

### En spillbar benk gir fleksibilitet, men benkepenger har en kostnad

Ibsen prioriterte 15 spillbare spillere og brukte seks forskjellige formasjoner.
Det ga dekning og rotasjon, men han benket også mange poeng. Lærdommen er ikke
«bruk mest mulig på benken», men «kjenn marginalverdien av benken».

- Mål antall spillbare spillere, forventede benkepoeng og om første reserve kan
  dekke en usikker starter.
- På Wildcard må benkstyrke vurderes sammen med en mulig Bench Boost.
- Uten planlagt Bench Boost bør en dyr reserve sammenlignes med hva pengene kan
  gi i startelleveren.

### Kapteinen er både forventede poeng og rank-risiko

Den regjerende vinneren brukte Haaland som kaptein i 22 av 38 runder og advarte
mot unødvendig kapteinsrisiko, men beholdt differensialer andre steder. FPLs
effektive eierskap forklarer hvorfor en svært eid kaptein kan gi stor negativ
rank-effekt dersom man går imot ham.

Kilder:

- [Championens kapteins- og chipstrategi](https://www.premierleague.com/ar/news/4672128/fpl-champion-how-to-pick-your-captain-and-maximise-your-chips)
- [FPL glossary](https://www.premierleague.com/en/news/2683145)
- [GW5 captain analysis](https://www.premierleague.com/en/news/4720208)

Konsekvens for appen:

- Vis marginen mellom de tre beste kapteinene.
- Bruk forventede poeng som hovedregel. Eierskap beskriver risiko; det skal ikke
  kunstig øke prognosen.
- Senere bør totalrank, mini-ligaposisjon og runder igjen styre en eksplisitt
  rank-utility. «Chasing» og «protecting» må være brukervalg.

### Lagverdi betyr mest tidlig, men prisjakt kan koste poeng

Vinneren var mer aktiv i første halvdel for å bygge lagverdi. Historiske data
viser også en positiv sammenheng mellom lagverdi ved halvspilt sesong og
sluttpoeng. FPL har i 2026/27 lansert en offisiell Price Change Predictor.
Verdier over 100 prosent antyder at terskelen passeres, men er ingen garanti.

Kilder:

- [Official Price Change Predictor](https://www.premierleague.com/en/news/4680462)
- [Championens lagverdi og bytter](https://www.premierleague.com/en/news/4671982/fpl-champion-how-to-build-the-perfect-squad-and-make-the-best-transfers)
- [Identification of skill in an online game](https://arxiv.org/abs/2009.01206)

Konsekvens for appen:

- Bruk de offisielle feltene `price_change_percent`, neste prognose og
  transferstrømmen fra FPL-snapshotet.
- Varsle om eide fallkandidater og relevante kjøpsmål som stiger.
- Ikke anbefal et tidlig bytte bare for £0,1m dersom spilleren har midtukekamp,
  usikre minutter eller nyhetsrisiko.
- Verdsett kjøpspris og salgsverdi korrekt; opparbeidet verdi påvirker hvor
  dyrt et sideveis bytte er å reversere.

### Chips har opsjonsverdi og må vurderes mot et alternativ

I 2026/27 finnes Wildcard, Free Hit, Triple Captain og Bench Boost i hver
sesonghalvdel. Første sett utløper etter GW19. Blank- og dobbelrunder er typiske
muligheter, men første halvdel kan også gi gode enkeltkamper. Per 18. september
peker flere eksperter på Wildcard i GW6 og mulig Bench Boost i GW7, men panelet
er langt fra enstemmig. Appen må derfor regne på brukerens lag, ikke kopiere en
universell kalender.

Kilder:

- [Official chip rules and strategy 2026/27](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627)
- [Current chip opportunities](https://www.premierleague.com/en/news/4362085)
- [Experts' current chip plans](https://www.premierleague.com/en/news/4685105)

Konsekvens for appen:

- Chipgevinst = optimal chip-score minus beste lovlige normalplan.
- Wildcard skal bruke flere GW og inkludere framtidige bytter.
- Bench Boost må ta hensyn til fire reelle benkespillere, minutter og bundet
  budsjett.
- Triple Captain trenger både høyt tak og høy sannsynlighet for minutter.
- Free Hit må måles mot hvor mange blanke/svake spillere det permanente laget
  faktisk har.

### Deadlineinformasjon slår ofte en marginal modellforskjell

FPL-fristen er 90 minutter før første kamp. Status, pressekonferanser,
midtukebelastning og forventet startplass kan endre minutter langt mer enn en
liten forskjell i forventede mål.

Kilde: [Managing your FPL team](https://www.premierleague.com/en/news/2174899).

- En flagget anbefalt starter skal overstyre den vanlige sjekklisten.
- Prognosen bør oppdateres etter siste relevante pressekonferanse og kamp.
- Expected-lineups-data må tidsstemples og valideres prospektivt før de får
  påvirke modellen.
- Appen bør vise når data sist ble oppdatert og hva som endret seg.

### Nye poengregler gir enkelte spillere et høyere gulv

Defensive contributions består i 2026/27. Forsvarere får to poeng ved minst ti
CBIT, mens midtbanespillere og angripere trenger tolv CBIRT. Poengene er
begrenset til to per kamp. Dette gir enkelte stoppere og defensive
midtbanespillere et bedre gulv enn eldre modeller antar.

Kilder:

- [How defensive contribution points work](https://www.premierleague.com/en/news/4361991)
- [Current 2026/27 DC leaders](https://www.premierleague.com/en/news/4713244)

Konsekvens for appen:

- Modellér sannsynligheten for å nå terskelen, ikke bare gjennomsnittlige
  defensive aksjoner.
- Rolle, motstand og forventet kampbilde kan forklare terskelsannsynligheten.
- Vis poengdekomponering: minutter, clean sheet, mål, assist, bonus, redninger
  og defensive bidrag.

## Produktstatus etter gjennomgangen

### Nå implementert

- Nytt **Strategisenter** i React-appen.
- Eksakt flerukersvalg mellom å rulle og å gjøre bytter.
- Separat hit-fri scenarioanalyse med usikkerhetsbuffer.
- Prioritert deadline-sjekkliste.
- Troppshelse: spillbare spillere, flaggede startere, benk og klubbrisiko.
- Kapteinsmargin, visekaptein og tre alternativer.
- Offisiell FPL Price Change Predictor for eide fallkandidater og relevante mål.
- Watchlists for høyest prognose, under ti prosent eierskap og verdi per £m.
- Oversikt over blanks/doubles i den kjente horisonten.
- Totalpoeng, totalrank og lagverdi fra offentlig laghistorikk.

### Neste prioritet: høy verdi

1. **Scenario- og robust optimering.** Kjør planen med lav/median/høy spilletid,
   skade på nøkkelspiller og ulike kamputfall. Vis hvilke bytter som overlever.
2. **Forklarbar poengdekomponering.** Vis hvorfor én spiller er 4,8 og en annen
   4,2: minutter, clean sheet, mål, assist, bonus, DC og odds.
3. **Eksakt brukerstatus via valgfri innlogging.** Offentlig historikk kan bare
   estimere gratisbytter og anskaffelsespris. Hent autoritativ saldo uten å
   utføre bytter.
4. **Forventede lagoppstillinger og nyhetsdiff.** Varsle bare når startplass
   eller minutter endrer seg materielt siden forrige snapshot.
5. **Terminlistescenarier.** Modellér sannsynlige blanks/doubles fra cup- og
   Europakamper før de er offisielt plassert, tydelig merket som scenarier.
6. **Mini-liga- og rankmodus.** La brukeren velge maks forventede poeng, forsvare
   ledelse eller jage differanse. Dette krever rivaldata og eksplisitt valg.
7. **Beslutningslogg.** Lagre rådet før fristen, brukerens valg og utfallet.
8. **Varsler.** Lokale/e-post/push-varsler for pris, skade, deadline og endret
   anbefaling, med terskler for å unngå støy.

### Senere prioritet

- Live Gameweek-visning med autosubs, bonus og defensive bidrag.
- Mini-liga-simulator med sannsynlighet for å hente eller forsvare en ledelse.
- Hva-hvis-verktøy der brukeren kan låse, ekskludere eller tvinge en spiller.
- Kalender for planlagte bytter og automatisk replanlegging.
- Personlig risikokalibrering basert på eksplisitte valg, ikke kortsiktige
  resultater.

## Datakilder og riktig rolle

| Kilde | Bruk | Viktig begrensning |
|---|---|---|
| Offentlig FPL API | pris, eierskap, status, DC, dødballer, offisiell prisindikator | gratisbytter er ikke autoritative uten autentisering |
| FPL snapshots før deadline | prospektiv trening og evaluering | må være tidsstemplet før fristen |
| Oddsmarked | lagmål, clean sheet, mål/assist-sannsynlighet | fjern bookmaker-margin og mål datadekning |
| Understat/OpenFPL-type data | xG/xA, skudd og spillerform | roller og ligaoverganger krever forsiktighet |
| Expected lineups | start- og minuttsannsynlighet | leverandøravhengig; må backtestes |
| Offisielt lagnytt | skader, suspensjon, trenerutsagn | tekst må struktureres uten å overtolkes |
| Cup/UEFA-terminliste | blank/double-scenarier og belastning | framtidige runder er sannsynligheter, ikke fakta |

## Ting appen ikke bør gjøre

- Bruke rå form fra tre-fire kamper som stabil ferdighet.
- Legge eierskap direkte inn i forventede poeng.
- Anbefale en differensial bare fordi eierskapet er lavt.
- Jage pris og ignorere midtukeskader eller benkingsrisiko.
- Anta at to kamper automatisk gjør en svak DGW-spiller bedre enn en sterk
  enkeltkamp-spiller.
- Promotere nye features fordi de ser fotballmessig riktige ut; de må slå
  baseline prospektivt og være kalibrerte.
- Vise «globalt optimum» dersom løseren bare har funnet en validert incumbent.

## Hvordan vi måler om appen faktisk blir bedre

Følg både prognose- og beslutningsmetrikker:

- netto poeng fra anbefalte bytter mot å holde;
- poeng spart/tapt på hits;
- verdien av bankede gratisbytter;
- kapteinsregret mot realistiske pre-deadline-alternativer;
- chipgevinst mot beste normalplan;
- prisendringer som faktisk ville blokkert en plan;
- anbefalingsstabilitet 24 t, 6 t og 1 t før deadline;
- kalibrering av minutter, clean sheet, mål, assist og DC;
- sluttresultat fra en full sesongsimulator med bare informasjon tilgjengelig
  før hver deadline.

Den viktigste testen er en låst, prospektiv «shadow season»: appen registrerer én
anbefaling før hver deadline og får ikke omskrive historien etter at poengene er
kjent.
