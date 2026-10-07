# App Store App Privacy questionnaire (draft)

These draft answers describe the current app: no user accounts, analytics SDKs
or advertising. Recheck the implementation and Apple's definitions before
submission, especially if dependencies or backend retention change.

## Data sent by the app

The app sends the user-entered public FPL team reference to our server to retrieve
public data. It is not used for advertising, cross-app tracking or building an
unrelated profile. The absence of a private login does not by itself determine
how Apple classifies the identifier; review the final disclosure before submission.

## Draft category answers

| Category | Draft answer |
|---|---|
| Contact information | Not collected |
| Health and fitness | Not collected |
| Financial information | Not collected |
| Location | Not collected |
| Sensitive information | Not collected |
| Contacts | Not collected |
| User content | Not collected |
| Browsing history | Not collected |
| Identifiers | No device or advertising ID; assess the public FPL reference and backend session identifier before submission |
| Purchase history | Not collected |
| Usage data | No analytics SDK integrated |
| Diagnostics | No crash-reporting SDK integrated; update this if one is added |
| Other | Public FPL team reference sent to the developer's backend for app functionality; not used for tracking |

## Tracking / App Tracking Transparency

The app does not request ATT permission because it does not track users across
apps or websites owned by other companies.

## Before submission

- Check `apps/mobile/package.json` for newly added analytics or advertising SDKs.
- If crash reporting such as Sentry is added, update Diagnostics and identify
  the provider in the privacy policy.
- Review server-side session storage together with the device-side behaviour.
