# Privacy policy for FPL Model (draft)

*Draft for App Store Connect and the support site. Add the actual contact email
and publication date before publishing. Consider legal review before a commercial
or large-scale release.*

**Last updated:** [date]

FPL Model is an independent analytics app for Fantasy Premier League. It is
read-only: it never logs in to fantasy.premierleague.com or changes your actual
FPL squad. It is not affiliated with, endorsed by or sponsored by the Premier
League, Fantasy Premier League or any Premier League club.

## Data used

- **FPL team reference:** the team ID or public URL you enter. This public
  identifier appears in FPL manager-profile URLs and is not an account secret.
- **Preferences:** your selected horizon, risk profile and filters.
- **Public FPL data:** squads, points, prices and mini-league standings retrieved
  from the public FPL API through our backend.

## Storage

The mobile app saves your team reference and preferences locally using
Expo/React Native `AsyncStorage`. This version has no user accounts or
account-based synchronisation.

The backend receives the team reference and calculation settings, holds the
imported squad in memory and records a small session pointer so it can rebuild
the session after a restart. It does not store FPL passwords or access your
actual FPL account. There are no built-in analytics, advertising or tracking SDKs.

## Third parties

The app calls our backend, which retrieves public data from
`fantasy.premierleague.com`. The backend can optionally use The Odds API and
football-data.org for odds and fixture/workload context. These requests run on
the server, not the phone, and do not forward your identity or FPL password.

## Deletion

Uninstalling the app removes its local data. A reset action that clears local
settings can also remove the stored team reference and preferences from the
phone. This concerns device data, not a deletion of backend session records.
If user accounts are introduced, this policy will be updated with the account
deletion process required by Apple.

## Children

The app is not directed at children and does not collect age-identifying data.

## Contact

Privacy questions: [support email; see docs/mobile/support.md]
