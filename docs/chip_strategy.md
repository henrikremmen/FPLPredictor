# Chipstrategi: regler, metode og begrensninger

## Regler som motoren håndhever

For 2026/27 finnes to sett med Wildcard, Free Hit, Triple Captain og Bench
Boost: ett i hver sesonghalvdel. Første sett utløper før fristen i GW19 og et
nytt sett blir tilgjengelig etterpå. Bare én chip kan brukes i samme Gameweek.
Free Hit kan ikke brukes i GW1 eller i to Gameweeks på rad. Kilde:
[Premier League, «What's happening with FPL chips in 2026/27?»](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627).

Premier Leagues strategiguider beskriver de vanlige bruksområdene: Bench Boost
og Triple Captain blir ofte sterkere i doble Gameweeks, Free Hit kan løse store
blankrunder, og Wildcard bør gi varig verdi og kan sette opp en senere Bench
Boost. Dette er heuristikker, ikke absolutte regler. Kilder:
[ekspertplaner for 2026/27](https://www.premierleague.com/en/news/4685105) og
[chipsekvenser brukt av FPL-vinneren](https://www.premierleague.com/en/news/4672128).

## Hvordan poengverdien beregnes

Alle scenarier sammenlignes mot en normalplan som får bruke lagets estimerte
gratisbytter. En MILP velger lovlig 15-mannstropp, startellever og kaptein under
følgende begrensninger:

- 2 keepere, 5 forsvarere, 5 midtbanespillere og 3 spisser
- lovlig formasjon og maksimalt tre spillere per klubb
- nåværende bank og individuelle estimerte salgspriser
- én kaptein blant de elleve som starter

Chipgevinst er differansen fra normalplanen:

- Triple Captain: ett ekstra sett av kapteinens forventede poeng
- Bench Boost: forventede poeng fra de fire benkespillerne
- Free Hit: beste énrundetropp minus beste normale énrundeplan
- Wildcard: beste permanente tropp minus normalplanen i hele prognosevinduet
- Wildcard → Bench Boost: samlet optimal tropp for Wildcard nå og Bench Boost i
  neste Gameweek

Forsiktige bruksterskler hindrer små, usikre gevinster fra å bli merket
`Spill`. Terskelen senkes nær utløpet av chipsettet. Resultatene `Spill`,
`Vurder` og `Hold` er beslutningsstøtte, ikke sannsynligheter.

## Hvorfor resultatet ikke er sesongoptimalt ennå

Modellen ser maksimalt tre Gameweeks frem. Den har ikke sikre fremtidige
blank-/dobbelrunder, cupresultater, skader eller framtidige lagnyheter. En
virkelig sesongoptimal policy krever scenarioer for hele halvåret, eksplisitt
usikkerhet og verdien av å vente. Relevant optimeringsforskning viser at slike
flerperiodeproblemer kan formuleres matematisk, men et godt resultat er fortsatt
avhengig av prognosekvalitet og framtidige fixture-scenarioer, se
[Solving Fantasy Football Using Mathematical Optimisation](https://arxiv.org/abs/2505.02170)
og [OpenFPL](https://arxiv.org/abs/2508.09992).

Neste naturlige steg er derfor å lagre ekte deadline-prognoser, bygge
halvsesongscenarier for blanke og doble Gameweeks og kalibrere chiptersklene mot
historiske beslutninger uten å lekke fasiten inn i prognosene.
