# FPL Model support (draft)

*App Store Connect requires a public support URL. Publish this content on a site
you control and replace the placeholders before submission.*

## About the app

FPL Model is an independent, read-only Fantasy Premier League analytics app.
It imports your team through a public URL and shows forecasts, lineups,
transfer suggestions and analysis. It never logs in to FPL or changes your real
squad. See the [independence disclaimer](./app-store-checklist.md#independence-disclaimer).

## Frequently asked questions

**The app cannot find my team.**
Check the reference: use a numeric team ID or a full
`fantasy.premierleague.com/entry/…` URL. Your team needs at least one completed
or active Gameweek.

**Bank or free transfers are wrong.**
Public team URLs do not show transfers made after the last deadline. Use
**Edit squad** to synchronise actual bank/free transfers or simulate new moves.

**The app cannot reach the backend.**
The backend address is set with `EXPO_PUBLIC_API_URL`. See the README for
connecting to a local server on the same Wi-Fi or a public backend.

**The forecast is old.**
Click **Refresh forecast** to capture new public data. This usually takes about
a minute.

## Contact

Email: [support email]
Expected response time: [for example, within a few days]

## Reporting a problem

Include the team ID, Gameweek, expected behaviour and actual behaviour.
Never include a password; the app does not need one.
