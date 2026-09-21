# TestFlight / App Store-sjekkliste

Denne sjekklisten dekker stegene fra en ferdig kodebase til en installerbar
build. Steg merket **krever Apple-konto**, **krever hosting** eller **krever
betaling** er ikke gjort av kodeendringer alene — de er manuelle handlinger
kontoeieren må ta.

## Uavhengighets-disclaimer

FPL Modell er **ikke tilknyttet, godkjent av eller sponset av** Premier
League, Fantasy Premier League eller noen Premier League-klubb. Alle
lagnavn, spillernavn og poeng vises som tekst hentet fra FPLs offentlige
API — appen bruker **ingen Premier League-logoer, drakter, klubbmerker eller
offisielle bilder**. Denne disclaimeren skal stå:

- I appens onboarding- eller "Om"-skjerm.
- I App Store-produktbeskrivelsen.
- I personvernerklæringen og support-siden (se `privacy-policy.md`,
  `support.md`).

## 1. Forutsetninger (krever Apple-konto)

- [ ] Apple Developer-konto (individuell eller organisasjon) — **krever
      betaling** (99 USD/år).
- [ ] `eas login` med en Expo-konto — gratis, men **krever konto**.
- [ ] `eas init` i `apps/mobile/` for å koble prosjektet til en ekte
      EAS-prosjekt-ID (erstatter placeholder-IDen i `app.config.ts`).
- [ ] Bekreft bundle-ID: `nb.fplmodell.app` (satt i `app.config.ts`). Endre
      den ene plassen hvis du registrerer en annen reverse-DNS-ID i Apples
      portal — den må være identisk der og i `app.config.ts`.

## 2. Backend må være offentlig tilgjengelig (krever hosting)

TestFlight-testere er ikke på ditt lokale Wi-Fi. Backenden må derfor kjøre
et sted med en offentlig HTTPS-adresse før du bygger en preview/production
-profil — se `docs/deploy.md`. Sett den adressen i `apps/mobile/eas.json`
under riktig profils `env.EXPO_PUBLIC_API_URL` (allerede forberedt med
placeholder-domener der).

## 3. Ikoner, splash og metadata

- [ ] Bytt ut placeholder-ikonene i `apps/mobile/assets/` (Expo-standard) med
      egendesignede ikoner. **Ingen Premier League-bilder eller -logoer.**
- [ ] Skjermbilder for App Store-oppføringen (tas manuelt fra simulator eller
      fysisk enhet — ikke generert av kodeendringer).
- [ ] Produktbeskrivelse, søkeord og kategorivalg i App Store Connect.
- [ ] Personvernerklæring publisert på en offentlig URL (fra
      `privacy-policy.md`) og lenket i App Store Connect.
- [ ] Support-URL publisert (fra `support.md`).
- [ ] Svar ut "App Privacy"-skjemaet (utkast i `app-privacy-answers.md`).

## 4. Bygg

```bash
cd apps/mobile
eas build --profile development --platform ios   # utvikling, installeres via development build
eas build --profile preview --platform ios        # intern testing / TestFlight-forhåndsvisning
eas build --profile production --platform ios     # App Store-innsending
```

Det første kallet med en ny Apple-konto ber EAS om å generere eller
importere signeringssertifikater — **krever Apple-konto-tilgang**, gjøres
interaktivt av kontoeieren.

## 5. TestFlight

```bash
eas submit --profile production --platform ios
```

- [ ] Fyll ut `appleId`, `ascAppId` og `appleTeamId` i `eas.json` (eller svar
      interaktivt) — **krever Apple-konto**.
- [ ] Legg til interne/eksterne testere i App Store Connect.
- [ ] Eksterne testere krever Apples "Beta App Review" (kan ta 1–2 dager) —
      **utenfor det kodeendringer kan garantere**.

## 6. App Store-innsending

- [ ] Fyll ut alle metadatafelt i App Store Connect.
- [ ] Send til review. Apple kan spørre om FPL-relatert innhold og
      opphavsrett — ha uavhengighets-disclaimeren klar som svar.
- [ ] Godkjenning er **ikke garantert av dette repoet** — det er en manuell
      Apple-prosess.

## Hva som IKKE er bekreftet av dette arbeidet

- Fysisk iPhone-testing, TestFlight-distribusjon og App Store-godkjenning er
  **ikke utført** som en del av kodeendringene — de krever en Apple-konto,
  et fysisk device eller ekstern review som ikke er tilgjengelig her. Det
  som er verifisert er: `expo-doctor` (21/21), typecheck, og en vellykket
  `expo export --platform ios`-bundling.
