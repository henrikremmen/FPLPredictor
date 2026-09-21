# Manageranalyse, miniliga og rank-risk

Oppdatert 18. september 2026. Målet er å støtte beslutningene til en ambisiøs
FPL-manager uten innlogging eller private API-endepunkter.

## Hva en god analyse må skille mellom

1. **Resultat:** faktiske poeng, totalrank, ligarank og lagverdi.
2. **Prosess:** kapteinsvalg, benkevalg, hits og umiddelbar transfersving.
3. **Relativ effekt:** hva et spillerpoeng var verdt mot akkurat feltet.
4. **Fremtidig beslutning:** modellforventning kombinert med liga- og
   topprank-EO, tilgjengelighet, pris og horisont.

Poeng alene kan ikke fortelle om beslutningen var god. Et modellsterkt valg kan
gi et dårlig enkeltutfall, mens et svakt valg kan lykkes. Appen viser derfor
både historisk utfall og fremoverskuende forventning.

## Effective ownership

Premier Leagues egen ordliste definerer en differensial som en spiller under
10 prosent eierskap og EO som startandel pluss kapteinsandel. Høy EO betyr at
et avkastende spiller du ikke har kan skade ranken, mens lav EO gir større
positiv rankeffekt dersom du eier spilleren:

- https://www.premierleague.com/en/news/2683145

For en konkret liga beregner appen den mer generelle og eksakte formen:

```text
EO = 100 × sum(poengmultiplikator) / antall analyserte managere
relativt spillerbidrag = spillerpoeng × (din multiplikator − EO / 100)
```

Dette håndterer benk, kaptein, Triple Captain og Bench Boost uten egne
spesialregler. Summen over alle spillere viser omtrent hvor mye laget vant eller
tapte mot ligaens gjennomsnittlige tellende XI, før individuelle transferhits.

EO må måles i riktig felt. LiveFPL beskriver hvorfor topprank-EO kan avvike mye
fra samlet globalt eierskap og bruker selv utvalg på tvers av ranknivåer:

- https://www.livefpl.com/blog/fpl-effective-ownership

Appen viser derfor tre forskjellige signaler:

- samlet globalt eierskap fra FPL
- eksakt EO i miniligaen, eller et merket utvalg i ligaer over 100 medlemmer
- et stratifisert utvalg på 25 offentlige lag rundt rank 1, 2 500, 5 000,
  7 500 og 10 000

Topprank-utvalget er en indikator, ikke en full opptelling av topp 10 000.

## Kaptein og risikoprofil

FPL-vinner Ali Jahangirov fremhever at kapteinen bør ses i lys av om manageren
jager eller forsvarer en posisjon. Populær kaptein reduserer varians; et
modellsterkt avvik kan være riktig når en må hente inn et gap:

- https://www.premierleague.com/en/news/3527473

Appen bruker dette slik:

- **Protect:** ligaleder; prioriter forventede poeng og store EO-trusler.
- **Balanced:** tidlig/midt i sesongen eller håndterbart gap; forventede poeng
  først, differensialer bare med modellstøtte.
- **Chase:** minst 20 poeng bak med åtte eller færre runder igjen; større vekt
  på modellsterke liga-differensialer og avvikende kaptein.

Kapteinsmatrisens isolerte rank-edge er
`modellpoeng × (2 − liga-EO/100)`. Den rangerer ikke alene kapteinsvalget, fordi
den ikke trekker fra alternativkostnaden ved å ikke kapteine nest beste spiller.

## Offentlig datagrunnlag

Analysen bruker disse lesbare FPL-endepunktene:

- `entry/{id}/history/`: poeng, rank, hits, benk og verdi per Gameweek
- `entry/{id}/event/{gw}/picks/`: låst squad, benk og kaptein
- `event/{gw}/live/`: faktiske spillerpoeng og minutter
- `entry/{id}/transfers/`: spillere inn og ut
- `leagues-classic/{id}/standings/`: miniligatabell og overall-utvalg
- `bootstrap-static/`: globalt eierskap, Gameweek-snitt og spillermetadata

Endepunktene er dokumentert og live-verifisert her:

- https://github.com/jakesmith1997-sfc/fpl-api

Offentlige picks blir først tilgjengelige etter deadline. Autentisert bank,
gratisbytter og ventende transfers er derfor fortsatt utenfor analysen.

## Fanene

### Sesong

- poeng mot globalt Gameweek-snitt og kumulativ differanse
- overall rank, rankflytt og persentil
- beste/svakeste runde, lagverdi og posisjonsbidrag
- kapteinsbonus, estimert kapteinsmulighet, benkepoeng, hits og brutto
  transfersving
- benchmark mot det stratifiserte topprank-utvalget

### Gameweek

- den faktiske 15-mannstroppen fra valgfri historisk Gameweek
- minutter, råpoeng, tellende poeng, globalt eierskap og liga-EO
- største positive og negative relative spillere, også spillere manageren ikke
  eide

### Miniliga

- tabell, gap til leder og historisk ligarank
- league template, startandel, kapteinsandel og EO
- eksplisitt protect/balanced/chase-modus

### Risiko og differensialer

- modellsterke, ikke-eide spillere med lav liga-EO
- høyt projiserte, ikke-eide rank-trusler
- egen leverage og kapteinsmatrise
- både liga-EO og EO i topprank-utvalget

## Ytelse og pålitelighet

FPL-svar caches i fem minutter. Uavhengige picks og historikker hentes med
maks åtte samtidige forespørsler. Ett manglende rivalendepunkt (for eksempel en
manager som startet senere) skal redusere utvalget, ikke velte hele analysen.
Store ligaer begrenses til 100 managere og merkes som utvalg.

Transfer-sving er brutto poengforskjell mellom spiller inn og ut i samme runde;
det er ikke en kausal vurdering og inkluderer ikke fremtidige poeng. Kapteins-
mulighet sammenligner med beste spiller i egen tellende XI og er en retrospektiv
mulighetskostnad, ikke et mål på kvaliteten på informasjonen før deadline.
