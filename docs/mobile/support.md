# Support for FPL Modell (utkast)

*App Store Connect krever en offentlig support-URL. Publiser dette innholdet
på en side du kontrollerer (GitHub Pages, et enkelt nettsted e.l.) før
innsending, og bytt ut plassholderne under.*

## Om appen

FPL Modell er en uavhengig, skrivebeskyttet analyseapp for Fantasy Premier
League. Den importerer laget ditt via en offentlig laglenke, viser
modellprognoser, laguttak, bytteforslag og analyse, men logger aldri inn på
FPL og gjør aldri endringer i din ekte tropp. Se
[uavhengighets-disclaimeren](./app-store-checklist.md#uavhengighets-disclaimer).

## Vanlige spørsmål

**Appen finner ikke laget mitt.**
Sjekk at lagreferansen er riktig — enten et rent tall (lag-ID) eller en full
`fantasy.premierleague.com/entry/…`-lenke. Laget må ha minst én ferdig eller
aktiv Gameweek.

**Bank eller gratisbytter stemmer ikke.**
Offentlige laglenker viser ikke bytter gjort etter siste deadline. Bruk
«Korriger lag» i appen for å synkronisere faktisk bank og gratisbytter, eller
simulere nye bytter.

**Appen får ikke kontakt med backend.**
Backend-adressen appen bruker settes via `EXPO_PUBLIC_API_URL`. Se README for
hvordan du peker appen mot en lokal server på samme Wi-Fi eller en publisert
backend.

**Prognosen er gammel.**
Trykk «Oppdater prognosen». Dette henter et nytt offentlig snapshot og kan ta
rundt ett minutt.

## Kontakt

E-post: [support-e-post]
Svartid: [f.eks. innen noen dager]

## Feilrapportering

Beskriv gjerne: lag-ID (uten passord — appen har ingen passord), hvilken
Gameweek, og hva du forventet vs. hva som skjedde.
