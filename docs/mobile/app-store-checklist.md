# TestFlight / App Store checklist

This checklist covers the path from source code to an installable build.
Steps marked as requiring an account, hosting or payment need action by the
account owner; code changes alone do not complete them.

## Independence disclaimer

FPL Model is **not affiliated with, endorsed by or sponsored by** the Premier
League, Fantasy Premier League or any Premier League club. Team/player names
and points are text from the public FPL API. The app uses no official Premier
League logos, kits, club badges or photographs.

Include this disclaimer in onboarding/About, the App Store description, the
privacy policy and the support page.

## 1. Accounts

- [ ] Apple Developer account, individual or organisation. The original checklist
  records a USD 99/year fee; verify current pricing when registering.
- [ ] Expo account and `eas login`.
- [ ] Run `eas init` in `apps/mobile/` to replace the placeholder EAS project ID
  in `app.config.ts` with a real project.
- [ ] Confirm bundle ID `nb.fplmodell.app`. If you choose another reverse-DNS ID,
  change it in `app.config.ts` and ensure it matches Apple's portal.

## 2. Public backend

TestFlight testers need a public HTTPS backend. Follow `docs/deploy.md` and set
the appropriate profile's `env.EXPO_PUBLIC_API_URL` in `apps/mobile/eas.json`
before building. The existing domains are placeholders.

## 3. Assets and metadata

- [ ] Replace Expo placeholder icons in `apps/mobile/assets/` with original
  artwork; do not use Premier League imagery or logos.
- [ ] Capture App Store screenshots from a simulator or device.
- [ ] Add description, keywords and category in App Store Connect.
- [ ] Publish `privacy-policy.md` and link its public URL.
- [ ] Publish `support.md` and provide its public URL.
- [ ] Complete App Privacy; the draft is in `app-privacy-answers.md`.

## 4. Build

```bash
cd apps/mobile
eas build --profile development --platform ios   # Development build
eas build --profile preview --platform ios       # Internal preview
eas build --profile production --platform ios    # App Store submission
```

The first build with a new Apple account asks EAS to generate or import signing
credentials. This requires interactive access by the account owner.

## 5. TestFlight

```bash
eas submit --profile production --platform ios
```

- [ ] Fill `appleId`, `ascAppId` and `appleTeamId` in `eas.json`, or answer the
  interactive prompts using the Apple account.
- [ ] Add internal/external testers in App Store Connect.
- [ ] Allow time for Apple's Beta App Review for external testers. Approval and
  review timing cannot be guaranteed by this repository.

## 6. App Store submission

- [ ] Complete all metadata fields.
- [ ] Submit for review; keep the independence disclaimer available if Apple
  asks about FPL-related content or intellectual property.
- [ ] Approval is an external Apple process, not a result of the code changes.

## Verification scope

The original mobile implementation verified `expo-doctor` (21/21), typechecking
and an iOS export. Physical iPhone testing, TestFlight distribution and App Store
approval were not performed as part of those code changes.
