# Personvernerklæring for FPL Modell (utkast)

*Dette er et utkast til bruk i App Store Connect og på en support-side. Fyll
inn faktisk kontakt-e-post og utgivelsesdato før publisering, og få det
gjerne lest av noen med juridisk kompetanse hvis appen skal selges eller nå
mange brukere.*

**Sist oppdatert:** [dato]

FPL Modell er en uavhengig analyseapp for Fantasy Premier League. Appen er
skrivebeskyttet: den logger aldri inn på fantasy.premierleague.com og kan
aldri gjøre endringer i din ekte FPL-tropp.

## Hvilke data appen bruker

- **FPL-lagreferanse** (lag-ID eller offentlig laglenke) du selv skriver inn.
  Dette er et offentlig nummer FPL selv viser i URL-en til enhver
  managerprofil, og regnes ikke som en hemmelighet.
- **Horisont, risikoprofil og filterpreferanser** du velger i appen.
- **Offentlige FPL-data** (tropp, poeng, priser, minligatabeller) hentet fra
  Fantasy Premier Leagues offentlige API, via vår egen server.

## Hvor dataene lagres

- FPL-ID, horisont, risikoprofil og preferanser lagres **kun lokalt på din
  telefon** (Expo/React Native `AsyncStorage`). De sendes ikke til noen
  tredjepart og synkroniseres ikke til en konto, fordi appen ikke har
  brukerkontoer i denne versjonen.
- Serveren appen snakker med holder et midlertidig øktobjekt (den importerte
  troppen din) i minnet og i et lite lokalt register som lar økten overleve
  en omstart av serveren. Den lagrer ingen passord og har ingen tilgang til
  den ekte FPL-kontoen din.
- Ingen analytics-, annonse- eller sporings-SDK-er er bygget inn i appen.

## Tredjeparter

Appen kaller vår egen backend, som i sin tur henter offentlige data fra
`fantasy.premierleague.com`. Backenden kan valgfritt bruke odds- og
kampbelastningsdata fra The Odds API og football-data.org for å forbedre
prognosene; disse kallene skjer fra serveren, ikke fra telefonen din, og
sender aldri din identitet eller ditt FPL-passord videre.

## Sletting

Siden appen ikke har en brukerkonto, sletter du all lokal appdata ved å
avinstallere appen, eller ved å bruke en «Tilbakestill»-handling i appen som
fjerner lagret FPL-ID, horisont, risikoprofil og preferanser fra telefonen.
Hvis en fremtidig versjon innfører kontoer, vil denne siden oppdateres med en
konkret slettefunksjon i appen, i tråd med Apples krav om kontosletting.

## Barn

Appen er ikke rettet mot barn og samler ikke inn data som identifiserer
alder.

## Kontakt

Spørsmål om personvern: [support-e-post, se docs/mobile/support.md]
