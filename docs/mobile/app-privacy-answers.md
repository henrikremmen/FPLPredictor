# App Store "App Privacy" spørreskjema (utkast)

Svarene under er utkast til Apples App Privacy-seksjon i App Store Connect,
basert på hva appen faktisk gjør per i dag (ingen brukerkonto, ingen
analytics-SDK, ingen annonser). Verifiser mot koden på nytt før innsending
hvis noe endres.

## Samler appen inn data?

**Nei, koblet til deg eller din enhet, i App Store-forstand.**

Appen sender kun:
- En FPL-lagreferanse (lag-ID/lenke) du selv skriver inn, til vår egen
  server, for å hente offentlige FPL-data på dine vegne.

Dette regnes normalt *ikke* som "data linked to you" i Apples skjema fordi:
- Det er et offentlig nummer FPL selv publiserer i enhver managerprofil-URL.
- Det brukes ikke til reklame, sporing på tvers av apper, eller til å bygge
  en profil om deg utover selve FPL-troppen.
- Det lagres ikke i en brukerkonto (appen har ingen kontoer i denne
  versjonen).

## Anbefalt utfylling

| Kategori | Svar |
|---|---|
| Kontaktinformasjon | Samles ikke inn |
| Helse og trening | Samles ikke inn |
| Finansiell informasjon | Samles ikke inn |
| Plassering | Samles ikke inn |
| Sensitiv informasjon | Samles ikke inn |
| Kontakter | Samles ikke inn |
| Brukerinnhold | Samles ikke inn |
| Browsingdata | Samles ikke inn |
| Identifikatorer | Samles ikke inn (ingen bruker-ID, enhets-ID eller annonse-ID sendes) |
| Kjøpshistorikk | Samles ikke inn |
| Bruksdata | Samles ikke inn (ingen analytics-SDK er integrert) |
| Diagnostikk | Samles ikke inn (med mindre et krasjrapporteringsverktøy legges til senere — oppdater denne siden da) |
| Annet | FPL-lagreferanse, sendt til utviklerens egen server for å hente offentlige data. Ikke koblet til identitet, ikke brukt til sporing. |

## Sporing (App Tracking Transparency)

Appen ber ikke om ATT-tillatelse fordi den ikke sporer brukere på tvers av
apper eller nettsteder eid av andre selskaper.

## Før innsending

- Verifiser at ingen tredjeparts-SDK for analytics/annonser er lagt til
  siden dette ble skrevet (`apps/mobile/package.json`).
- Hvis et krasjrapporteringsverktøy (f.eks. Sentry) legges til, oppdater
  «Diagnostikk»-raden og legg til leverandøren i personvernerklæringen.
