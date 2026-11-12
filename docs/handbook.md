# FPL Model handbook

The full reference. Start with the short [README](../README.md).

This project predicts points for upcoming Fantasy Premier League Gameweeks and
turns those forecasts into team decisions through a local React app. It uses
public FPL data, never logs in to your account and never makes transfers for you.

## Start the web app

Run these commands from the project directory:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
npm install --prefix frontend
.venv/bin/python run_app.py
```

Node.js 20 or later is required. The browser normally opens automatically at
`http://127.0.0.1:5173`. API documentation is at `http://127.0.0.1:8000/docs`.
Enter your FPL team ID (a pasted team link also works), choose a forecast
horizon and risk profile, then click **Load team**.

The app includes:

- Squad, prices, opponents and model points.
- Manager analysis: season performance, historical squads, sources of points,
  captaincy, bench decisions, transfer swings and overall rank.
- Mini-league standings, rank history, gaps, effective ownership (EO),
  differentials and rank threats.
- Global benchmarks and a labelled, stratified sample of teams ranked 1–10,000.
- Recommended starting XI, formation, captain, vice-captain and bench order.
- One to five transfers, either unrestricted or with selected outgoing players,
  using a global MILP with points hits included.
- Multiweek planning over 1–8 Gameweeks, including transfers, up to five banked
  free transfers, starting XIs and captains.
- Buy and sell candidates, short-term chip analysis, Free Hit squads and a
  long-term Wildcard squad with a subsequent transfer plan.

Correct bank and free transfers in the sidebar if the estimates differ from
FPL. **Refresh forecast** downloads a new public snapshot and usually takes
about a minute. You can refresh before loading a team when FPL advances to a
Gameweek for which no forecast exists; the app then imports the team again.

Public team data do not show transfers made after the last deadline. Use
**Edit squad** to correct this:

- **Already made** synchronises the squad with actual bank and remaining free
  transfers, without charging for those moves again.
- **New transfers** simulates changes using the app's active squad, calculating
  the bank, remaining free transfers and any points hit.

The corrected squad is used by all decision tools. It is saved locally for the
same FPL ID and Gameweek, survives forecast refreshes and can be removed with
**Reset to FPL**. It never changes the real FPL team.

The **Analysis** tab uses public data only. Historical outcomes and EO are
separate from forward-looking forecasts. See
[manager analytics research](archive/manager_analytics_research_2026.md) for methods
and limitations.

## This week (W1, 12 November 2026)

- **This week** is the start page (first in **This round**; mobile: top of the
  Round tab). It lists the round's steps in the order you do them in FPL:
  1. transfers: what to sell and buy with prices, bank afterwards, hit, the gain
     over rolling and how often each plan won across the sampled scenarios, plus
     a warning when a player you buy is close to a price rise;
  2. the XI and bench order **after** the transfer, with the expectation
     including autosubs and the vice-captain;
  3. captain and vice-captain; 4. chip.
  Then what would change the plan (flagged starters and the tipping point for
  the player you buy and the captain) and the weeks after.
- **Copy to FPL** (mobile: **Share as text**) gives the same checklist on both
  (`fplChecklist` in `packages/shared`). Steps you tick stay in the browser or
  on the phone for that team and Gameweek. Nothing is sent to FPL.
- `POST /api/team/{id}/this-week` builds it from the same cached results as
  Strategy, Chips and Scenarios, so the numbers match those pages. Import and
  refresh precompute chips and scenarios as well.
- Strategy now takes captain, vice-captain and squad health from the squad
  **after** the plan's first transfers (`lineup_after` in
  `src/strategy_advisor.py`, finding F31).
- Advanced pages (Scenarios, FH/WC squads, Compare players, Player preferences,
  Model and data, Saved plans) sit under a folded **More** in each sidebar
  section (U20). Deep links are unchanged.
- **Plan changed since you last looked** (L1): the browser (or phone) keeps a
  summary of the advice it last showed for that team and Gameweek: transfers,
  captain, vice-captain, chip. When any of them differs on the next visit, a line
  says what changed (`adviceSummary`/`adviceDiff` in `packages/shared`).
- **Following the model** (L2): when a shadow season exists for your team and
  has scored rounds, This week shows its points next to yours over the same
  rounds, and the hold policy's (`GET /api/team/{id}/shadow-summary`; your
  points are net of hits, from FPL's public history).
- **Autopilot policy** (L3, Player preferences): *Margin per transfer* is how
  many planning points a move must beat rolling by per free transfer it spends,
  and a hit must beat the no-hit plan by per paid transfer (default 2.0, as
  before). *Largest hit* caps the hit the strategy may recommend (default any).
  Both travel with every request like the other preferences and are part of
  the cache key. No notifications are sent; the app still never makes transfers.

**Paste team news (M20, web).** Under This week step 5 and on Scenarios, paste
what a manager said or a team-news post and press **Read with Claude**. Claude
(`claude-opus-5-5`, low effort, structured output) proposes a chance of playing
for each player the text names, with the supporting phrase and FPL's current
figure. Nothing changes until you press **Accept**; accepted proposals join
**Your assumptions** (the same overrides as P5) and are never stored on the
server or trained on (`POST /api/team/{id}/news-assumptions`). Unknown players
are dropped and chances are clamped to 0–1. It needs `ANTHROPIC_API_KEY`; one
reading of a short text cost about $0.03 on 12 November 2026.

## Decision-first layout (plan phase F, November 2026)

- **Overview** shows the squad, key numbers and what changed since last time.
  (Until 12 November it opened with a decision card; **This week** replaced it.)
- **Strategy, transfers and the multiweek plan** calculate as soon as you open
  them. The API also precomputes the default answers after an import or
  refresh. Results are cached under a key that covers the forecast, squad,
  bank, free transfers, horizon, profile, preferences, bench weights and
  options, so a fast answer is never a stale one (`src/result_cache.py`).
- One status line shows the forecast time (details on tap) and the horizon.
  Points have one decimal. Expected points are the main number; a Stable or
  Upside score sits beside it.
- **Players → Fixtures** shows the next Gameweeks per player: opponent, home or
  away, expected points, the chance of 60+ minutes, blanks and doubles.
- On a phone the bottom bar is the only navigation. A section with several
  pages opens a sheet of them. The player panel is a bottom sheet with its
  tables folded.

## Scenarios, your assumptions and the decision journal (plan phase G)

- **Transfers & plan → Scenarios** compares holding, the best plan (A) and the
  best plan without A's first signing (B) on the same horizon and inputs. Each
  row shows net points, hits, bank and free transfers. Each plan is scored on 50
  sampled scenarios with a stored seed and reported as "chosen in X % of
  scenarios"; that depends on how the scenarios are drawn and is not a chance of
  winning.
- **Your assumptions** ("What if he is benched?") set your own chance of playing
  for a player. Every calculation uses it until you reset it. A notice on every
  page says so. It stays in the browser and is never stored or trained on.
- **Find the tipping point** gives the chance of playing at which the plan's
  first-week action changes.
- **Record my decision** (Overview) freezes the advice, the alternatives, your
  choice and the source times before the deadline. History → Decision journal
  shows them, and the outcome once FPL has checked the round. Entries sit next
  to the shadow season in `artifacts/shadow_season/<season>_<team>/` and are
  never overwritten.
- The FPL rules (squad shape, formations, hits, selling price, free transfers,
  chip halves) live in one module, `src/fpl_rules.py`, used by the planner, the
  apps, the shadow season and the backtests.

## Ask Claude (web app chat)

- Set `ANTHROPIC_API_KEY` in the root `.env` (see `.env.example`), load your
  team and click **Ask Claude** in the bottom right corner. The key is reread
  on every message, so no restart is needed. The web app only; not the mobile app.
- Claude (`claude-opus-5-5`, low effort) sees what the app shows you:
  - the forecast for every player and club over every forecast gameweek (up to 8);
  - the model card;
  - your squad, finances, chips, preferences and assumptions;
  - every computed result: strategy, transfer search, multiweek plans with and
    without chips, chip windows, Free Hit/Wildcard squads, scenarios, fixtures,
    news changes, manager and mini-league analysis, journal and saved plans;
  - the page you have open, with that page's settings.
- It runs the transfer search, planner, comparisons and what-ifs itself through
  read-only tools that call the same code as the pages, so its numbers match the
  app. It cannot change your squad or anything else.
- How the context is kept:
  - The forecast goes into a frozen system prompt that is cached.
  - Team state and the open page follow the question as `role: "system"`
    messages, only when they change.
  - A new forecast starts a new chat.
  - Conversations live in the API process and are lost on restart (`src/chat.py`).
- Cost, measured on GW11 for a real team:
  - The context is about 90k tokens. The forecast snapshot, model card and tools
    are 46k; players under 1 xP over the window are left out and reachable
    through tools. The team state is 43k: Free Hit/Wildcard squads, fixtures and
    the sell ranking are tools, not context.
  - The prompt cache lasts one hour. On Sonnet 5.5 the first question of a chat
    costs about $0.37, and follow-ups within the hour about $0.02–0.04. Opus 5.5
    measured $0.70 and $0.03–0.07; `MODEL` in `src/chat.py` switches.

## Decision workspace

The web app now includes:

- **Since last time**, on Overview: news, availability, price, fixture and material
  expected-point changes for your current squad compared with the latest earlier
  snapshot covering the same horizon. Point changes below 0.5 are omitted.
- **Clickable player names**: per-round fixtures and points, per-fixture playing-time
  probabilities and Q10–Q90, news, and separate forecast and player-data timestamps.
  The current model predicts minute bands, not an exact expected-minutes figure.
- **Compare players**: a legal same-position replacement versus holding, using selling
  prices, bank, club limits, optimal XI/captain and a single transfer hit when needed.
  Player projections and total team gains are shown separately.
- **Player preferences**: lock owned players or exclude players. These constraints
  apply inside the transfer, multiweek and FH/WC optimizers, and filter market
  suggestions and strategy watchlists. Excluding an owned player
  requires selling them in a proposed squad; conflicting or impossible requests do
  not silently relax the constraints. Current holdings and actual FPL teams are unchanged.
- **Saved plans**: named transfer, player-comparison, multiweek and chip alternatives,
  including their original squad, finances and preferences. Select two for A/B review.
  Numerical differences are shown only for compatible analysis types, inputs and chip
  evaluation windows/baselines. You can rename or delete drafts.
- **Team ID import**: enter the numeric FPL team ID (a pasted team link also
  works). Imports always use the current Gameweek; an `/event/N` part of a link is
  ignored. The last ID is remembered in this browser (AsyncStorage on mobile).
- **Timeline** (web page, mobile screen from Analysis): every played Gameweek on
  the pitch with points, C/VC/TC, chip, automatic substitutions, transfers with
  prices and hits, rank and bank. Step with ← and →, the season ribbon or a swipe.
  `GET /api/team/{session_id}/timeline` caches rounds FPL has data-checked in
  `data/local/cache/entry/{id}/gw{N}.json` and never requests them again.
- **Top managers** (History, mobile screen from History): today's overall top 100,
  the all-time **Legacy** 100 who still play and the **top 1%**. Each tab shows the
  points gap and the gap per remaining round, your squad match (multiplier-weighted
  overlap of your planned XI and captain with their effective ownership), what they
  bought and sold, captains and chips, their template next to your role, the players
  they have and you don't, and (top 100 and legacy) every manager with match and
  shared players. Squads are public only after a deadline, so this is always the
  last round. Press **Update** after the deadline when you prepare the app for a new
  round, or run `.venv/bin/python src/top_managers.py collect` (`--force` retakes a
  finished round, `--rebuild-legacy` rebuilds the legacy list). One run reads about
  2,650 public FPL pages at most 10 per second (4 workers, backoff on 429) and takes
  4–5 minutes; results go to `data/local/top_managers/<season>/gwNN.json` (local,
  gitignored). The top 1% is a random sample of 40 standings pages (2,000 managers,
  ownership within ±2.2 pp 19 times in 20); its points cutoff is exact. Legacy
  candidates are the top 300 of Fantasy Football Pundit's all-time table (it links
  this season's FPL ids); we score them from FPL history as a recency-weighted mean
  of log10(overall rank) (each older season weighs 0.8 of the next, at least five
  seasons) and keep the best 100 who played the latest round, once per season.
  Analysis uses the same top 1% sample for its "top 1% EO".
  A **YouTubers** tab follows well-known creators (`CREATORS` in
  `src/top_managers.py`: this season's FPL ids, checked against FPL; add one line per
  creator). **Copy check** shows, for each member of your mini-leagues, the YouTuber
  whose squads look most like theirs over every finished round, a signal (Strong:
  more alike than 95% of 75 random top-1M managers, Some: 80%), the rarest shared
  buys, shared chip rounds, overlap per round against a typical manager, and the
  closest friend, plus a friend-vs-friend matrix. Squad overlap weights each shared
  player by −ln(ownership); same-round buys (net squad changes, so wildcard re-edits
  count once and a Free Hit return is no buy) by −log10(share of managers who made
  the buy). Each measure is a percentile against the baseline managers for the same
  creator, the stronger of the two counts, and the member's best creator is
  compared with the baseline managers' best. Transfer times are not used. It is similarity, not proof. Update runs it for
  your mini-leagues after the top managers (`src/copy_check.py collect --entry ID`:
  about 2.5 minutes the first time, rounds FPL has checked are cached in
  `data/local/cache/entry/`); results in `data/local/copy_check/<season>/`.
- **Update status**: source/history/scoring stages and elapsed time during forecast
  refreshes. Previous results stay visible on refresh or calculation failure, and
  results are marked outdated when forecasts, squad, finances or preferences change.

Preferences and saved plans are stored in this browser for each FPL entry ID. They
survive reloads but do not sync across browsers/devices. Saved plans are snapshots;
recalculate outdated advice before saving a new version. These features do not
change the production model or calibrate injury recovery across future gameweeks.

Run the deterministic workspace browser tests without live FPL or paid API calls:

```bash
npm --prefix frontend run test:e2e:workspace
# Screenshots of every page at 390×844 and 1440×900 (optionally with a real timeline payload):
SCREENSHOT_DIR=/abs/dir [TIMELINE_FIXTURE=/abs/timeline.json] npm --prefix frontend run test:e2e:workspace
```

## Repository structure and commands

```text
src/                 Python models, decision engine and FastAPI backend
frontend/            React web app
apps/mobile/         Expo/React Native app with TypeScript and Expo Router
packages/api-client/ Typed client for src/api.py and shared API types
packages/shared/     Shared constants and formatting
tests/               Python unit tests (unittest)
notebooks/           Deadline backtest, live snapshots, prediction vs actual; dataset parity reference
docs/archive/        Finished plans, phase reports and research
```

`packages/*` and `apps/*` are npm workspaces. `frontend/` is installed and run
separately. Install workspace dependencies from the repository root:

```bash
npm install
```

Root commands are wrappers around the underlying app commands:

```bash
npm run backend          # API on 127.0.0.1
npm run backend:lan      # API on 0.0.0.0 for a phone on the same Wi-Fi
npm run web              # React web app
npm run mobile           # Expo development server
npm run mobile:ios       # Expo and the iOS simulator
npm run test:backend     # Python test suite
npm run test:mobile      # Mobile Jest tests
npm run typecheck:mobile
npm run typecheck:shared
```

## Mobile app

`apps/mobile` is a native React Native app, not a WebView. All budget,
selling-price, position, club-limit, transfer, hit and optimisation calculations
run in the shared backend. The app stores the FPL ID, horizon, risk profile and
market preferences locally with `AsyncStorage`; this version has no user accounts.

Web and mobile share one structure and one palette. The five sections are
**This round** (this week, overview, lineup), **Transfers & plan** (strategy, transfers,
multiweek plan, chips, FH/WC squads), **Players** (market, compare, player
preferences), **History** (analysis, timeline) and **My team** (edit squad,
saved plans). The web app shows them as sidebar groups and, below 760 px, as a
bottom bar with section tabs; every page has a deep link (`#/transfers`) and a
refresh restores the last team session. The mobile app uses the same five tabs
with SVG icons, pull-to-refresh and skeleton loading. Mobile player preferences
(lock/exclude) reach every optimiser call, and saved plans stay on the device.
Colours, spacing, radii and type sizes come from `packages/shared/src/tokens.ts`
(CSS variables on the web, the theme on mobile); a test checks WCAG AA contrast.
Response types live in `packages/api-client` and are used by both clients.

Expo web (`npm --prefix apps/mobile run web`) runs the mobile app in a browser,
which is useful for screenshots without a simulator.

FastAPI performs the data retrieval and calculations. The Expo development
server only bundles the mobile JavaScript/TypeScript code and serves it to Expo
Go, a simulator or a development build. A released App Store build bundles that
code inside the app and does not need the Expo server. Mobile API requests go to
`EXPO_PUBLIC_API_URL`.

### Local simulator

```bash
cp apps/mobile/.env.example apps/mobile/.env
.venv/bin/python run_app.py
cd apps/mobile && npx expo start
```

Use separate terminals for the backend and Expo. Press `i` for the iOS simulator
(requires Xcode), or `w` for a web preview. The simulator can reach the Mac's
`127.0.0.1` address.

### Physical iPhone on the same Wi-Fi

First put a long random `FPL_API_TOKEN` in the root `.env` (for example from
`openssl rand -hex 24`) and the same value as `EXPO_PUBLIC_API_TOKEN` in
`apps/mobile/.env`. The API refuses to start on `0.0.0.0` without it, and
every request except `/api/health` must then carry it.

```bash
npm run backend:lan
# Alternatively:
FPL_API_HOST=0.0.0.0 .venv/bin/python run_app.py
```

The launcher prints a local address to put in `apps/mobile/.env`, for example:

```dotenv
EXPO_PUBLIC_API_URL=http://192.168.1.23:8000
```

Restart Expo after changing it. Open Expo Go on your phone and scan the QR code.
The Mac and phone must use the same Wi-Fi; allow incoming Python/uvicorn
connections if the macOS firewall prompts you.

### Development builds, TestFlight and production

Expo Go supports the current workflow but may not support future native modules.
For a development build:

```bash
cd apps/mobile
eas build --profile development --platform ios
```

This requires an Apple account and an authenticated EAS CLI (`eas login`). See
[the App Store checklist](mobile/app-store-checklist.md).

TestFlight testers need a public HTTPS backend; see [deployment](deploy.md).
Set `env.EXPO_PUBLIC_API_URL` for each profile in `apps/mobile/eas.json`.
`apps/mobile/.env` is used for local development with Expo.

```bash
eas build --profile preview --platform ios
eas build --profile production --platform ios
eas submit --profile production --platform ios
```

Draft privacy, support and App Privacy documents are in `docs/mobile/`.

### Mobile checks

```bash
cd apps/mobile
npm run typecheck
npm run lint
npm test
npx expo-doctor
npx expo export --platform ios
```

## Terminal app

```bash
.venv/bin/python src/fpl_app.py "https://fantasy.premierleague.com/en/entry/5139814/event/4"
```

The interactive menu provides squad details, lineup and captain selection,
single and multiple transfers, buy candidates, sell candidates and multiweek
planning. Direct commands are also available:

```bash
.venv/bin/python src/fpl_app.py "5139814" --refresh
.venv/bin/python src/fpl_app.py "5139814" --action lineup
.venv/bin/python src/fpl_app.py "5139814" --action transfers --max-transfers 5
.venv/bin/python src/fpl_app.py "5139814" --action targets --position MID --max-price 7.0
.venv/bin/python src/fpl_app.py "5139814" --action sells
.venv/bin/python src/fpl_app.py "5139814" --horizon 3 --action transfers --risk-profile stable
.venv/bin/python src/fpl_app.py "5139814" --horizon 8 --action plan
.venv/bin/python src/fpl_app.py "5139814" --action lineup --risk-profile upside
```

`--horizon 2` through `--horizon 8` sums forecasts over multiple Gameweeks.
Lineup selection still concerns the next Gameweek. Older snapshots may contain
only three rounds; refresh to obtain a longer horizon.

If only the model has changed, rescore the latest complete raw snapshot without
making new API calls:

```bash
.venv/bin/python src/capture_fpl.py --rescore-latest
```

## Risk profiles and decision constraints

Profiles change the decision score, not the model's expected points:

- `balanced`: expected points; the default.
- `stable`: expected points minus `0.1 × (Q90−Q10)`.
- `upside`: `0.7 × expected points + 0.3 × Q90`.

In the original decision benchmark, `stable` gained 85 points across the two
validation seasons and 20 in the 2025–26 test. `upside` gained 64 in validation
but lost 28 in the test; its 90th percentile rose from 76.0 to 79.8 with higher
variation. These are optional utility functions, not new expected-point
estimates or guarantees about risk.

Q10, Q50 and Q90 come from a point distribution (`src/point_distribution.py`,
plan M9), not from adding up quantiles. Each fixture's three model quantiles
define a piecewise-linear distribution. Fixtures are drawn independently and
summed over the Gameweek or horizon. Availability is a mixture: with
probability 1 − availability the player scores 0. Expected points still add up
and scale with availability, so Balanced is unaffected. The tails and the
independence between fixtures are assumptions.
`.venv/bin/python src/quantile_audit.py --team ID --output DIR` shows which
Stable/Upside choices change compared with the old summed-and-scaled numbers.

**Bench weights (plan P1).** Decisions also count a small share of each bench
player's forecast, in FPL bench order: reserve keeper 0.03, then bench 1–3 at
0.12, 0.06 and 0.03. This is a rough stand-in for autosubs. Change the weights
under Player preferences (web) or Preferences (mobile); set all to 0 to ignore
the bench. Expected points shown as XI totals stay XI + captain only.

**Chips and requirements in the multiweek plan (P2, P4).** "Plan chips too"
adds Bench Boost, Triple Captain, Free Hit and Wildcard to the optimisation:
at most one per Gameweek, each at most once, and only until the chip expires
(GW19 for the first set). A chip calendar shows each planned chip, the nearest
alternative week and the points between them. Requirements ("own X by GW N",
"sell Y in GW N", club and position limits) are hard constraints, and the plan
shows what each one costs. The lineup page and each planned week also show the
expectation with autosubs and vice-captain (P3, `GET /api/team/{id}/lineup-value`).
It is a Monte Carlo over who plays, scored with the backtests' autosub rules.

The decision engine enforces:

- A 15-player squad: 2 goalkeepers, 5 defenders, 5 midfielders and 3 forwards.
- A legal XI: 1 goalkeeper, 3–5 defenders, 2–5 midfielders and 1–3 forwards.
- Matching positions for incoming and outgoing players.
- Purchases within bank plus estimated selling proceeds.
- A maximum of three players per club.
- A four-point hit per transfer beyond the estimated free-transfer allowance.

Single-transfer searches cover the full market. For two transfers, the top
plan is solved globally and broad backup options are also shown. For three to
five transfers, the app returns the exact global plan over the market.
See [FPL rules](https://fantasy.premierleague.com/help/rules) and
[transfer and selling-price guidance](https://www.premierleague.com/en/news/2174907).

## Limitations

Public team links do not expose exact selling prices, bank or current free
transfers. These are reconstructed from public history and must be checked in
FPL. Known availability flags reduce recommended points, but the model does not
perform a complete injury or news analysis. Multiweek plans hold current prices
constant and use current injury information; recalculate after each deadline
and material update. The model is experimental and trained on historical
pre-fixture features, not a fully verified deadline dataset.

## Snapshots and optional data sources

`capture_fpl.py` freezes status, playing chances, prices, transfers, set-piece
order, team strength, defensive contributions, CBI, tackles, recoveries, cards,
bonus and expected-goal statistics. Raw responses have hashes and receipt times
to establish what was known before the deadline.

Refresh manually near the deadline. Daily collection is not required for app
use, but multiple completed Gameweeks of snapshots are needed to validate
odds and workload features. Optional automatic checkpoints are available:

```bash
.venv/bin/python src/deadline_collector.py --watch
.venv/bin/python src/deadline_collector.py --check
```

The collector checks for idempotent snapshots around 24, 6 and 1 hour before
each deadline. For example, run a check every ten minutes with cron:

```cron
*/10 * * * * cd /absolute/path/to/fplmodell && .venv/bin/python src/deadline_collector.py --check >> deadline_collector.log 2>&1
```

Official FPL endpoints need no `.env` file. For optional sources, copy
`.env.example` to `.env` and configure:

- `ODDS_API_KEY`: de-vigged consensus match-result and over/under 2.5 odds,
  converted to expected team goals and clean-sheet probabilities.
- `ODDS_PLAYER_PROPS=1`: additional, more credit-intensive anytime-goalscorer
  and over/under 0.5 assists calls; primarily US bookmakers and currently
  retained as research signals.
- `FOOTBALL_DATA_API_KEY`: cross-competition schedules from football-data.org.

Missing keys skip the optional source and are recorded in the manifest.
Keys are excluded from Git and snapshots. Automated text/LLM news analysis is
not implemented. Individual international minutes and travel are not modelled.

### Own data repository (fpl-data)

vaastav stopped weekly updates after 2024-25, so current seasons come from our
own collection in `fpl-data/` (a clone of the private repository
`henrikremmen/fpl-data`). The collector runs locally, on demand, and decides
from the files already there what is due:

- a light snapshot (bootstrap, fixtures, event status, set-piece notes) once a
  day after 02:30 UTC and in the T-24h/6h/1h windows before each deadline;
- a full round export once FPL marks a Gameweek `finished` and `data_checked`,
  written as vaastav-compatible CSVs with an extra stable `code` column.

Every payload is validated at the boundary and every export must pass the data
contract (`src/data_contract.py`) before anything is written; a failure exits
non-zero. Corrections to exported rounds are logged in `corrections.csv`.

`run_app.py` runs it at start and then every hour while the app is open (plan
D2, 12 November 2026); a failure is printed and never stops the app. Docker and
a bare `uvicorn` do not. Otherwise run it by hand, at least once a day after
02:30 UTC, and right before `prospective_loop.py auto` locks a round. Deadline checkpoints cannot be
fetched afterwards; finished rounds can, so a missed day only loses that day's
snapshot. Each run reports `gap_hours` since the previous snapshot, and the
app's lock banner warns when the latest snapshot is over 36 hours old.

```bash
.venv/bin/python src/fpl_collect.py --data-root fpl-data auto      # what is due now
git -C fpl-data add -A && git -C fpl-data commit -qm "data: local $(date -u +%FT%H:%MZ)" && git -C fpl-data push   # optional backup
```

The GitHub Actions workflow in `fpl-data` (hourly from 22 October 2026) was
removed on 11 November 2026: data collection on GitHub-hosted runners can fall
outside GitHub's Actions terms. Keep collection local.

The collector source is `src/fpl_collect.py`; `fpl-data/collector/` holds
copies, and the test suite fails if they drift.

```bash
git clone https://github.com/henrikremmen/fpl-data.git fpl-data   # once, ignored by Git
cp src/fpl_collect.py src/data_contract.py fpl-data/collector/      # after changing either file
.venv/bin/python src/fpl_collect.py --data-root fpl-data export --xp-snapshots data/raw/live_fpl
```

The last command re-exports every data-checked round (about ten minutes at two
requests per second); `auto` already exports rounds that are missing.

## Historical market model

The free Odds API plan provides live odds, not paid historical endpoints.
Training instead uses football-data.co.uk pre-closing market averages for
2020/21–2025/26. Closing columns are excluded because they may contain
post-deadline information. Raw files and hashes are saved under
`data/raw/historical_odds/football_data_uk/`.

```bash
PYTHONPATH=src .venv/bin/python src/market_models.py --root .
```

The benchmark compares the incumbent, the same baseline without odds, a market
model, a linear model and three fixed blends using chronological validation.
2025/26 is held out from model selection. The production model uses market
predictions when odds are available and falls back to the incumbent otherwise.

Free football-data.org coverage provided complete Champions League history
only from 2023/24, without Europa League, Conference League, FA Cup or League
Cup coverage. The tested CL workload model did not improve RMSE, candidate
RMSE and top-25 selection across both evaluation seasons, so it was not enabled.

See [model research](archive/model_research_2026.md),
[product research](archive/product_feature_research_2026.md) and
[manager strategy research](archive/fpl_manager_strategy_research_2026.md).

## Chip strategy

Each chip is compared with the best normal plan using available free transfers
and the same legality constraints. Free Hit and Wildcard optimise the squad;
Triple Captain adds another copy of the captain's points; Bench Boost adds the
bench. Wildcard → Bench Boost is optimised jointly.

The documented 2026/27 rules provide one chip set per season half. The first
set must be used before the GW19 deadline. Only one chip can be used per
Gameweek, and Free Hit cannot be used in consecutive Gameweeks.
See [the official rules](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627).

Chip advice is explicitly limited to the available horizon. A short forecast
cannot establish season-optimal timing or anticipate every later blank/double
Gameweek. **Play** is a strong model signal, not proof of optimal timing.
See [chip methodology](chip_strategy.md).

## Training and model evaluation

Historical data use
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League)
for seasons up to 2025-26 and `fpl-data/` for later seasons (an own season
replaces vaastav's copy of the same season). Build the training table, then the
features:

```bash
.venv/bin/python src/build_dataset.py      # data/processed/cleaned_merged_seasons_team_aggregated_expanded.csv
.venv/bin/python src/build_features.py
```

`build_dataset.py` replaces `notebooks/build_expanded_dataset.ipynb` and gives a
byte-identical file on the notebook's inputs.
Live forecasts are generated by `src/capture_fpl.py`; the decision app is in
`src/fpl_app.py`. Production promotion requires both prediction-quality gates
and a historical budget/position/club/lineup/captain backtest. The P(60+) model
is evaluated and refitted separately from points ranking.

```bash
.venv/bin/python src/nextgen_models.py
```

On macOS, LightGBM requires OpenMP; if needed:

```bash
sudo xcodebuild -license accept
brew install libomp
```

CatBoost improved some top-selection and captain metrics but lost overall RMSE
on the untouched 2025/26 holdout and was not promoted. Missing `libomp` causes
LightGBM to be skipped and the error recorded in `settings.json`. Increasing
training from 500 to 800 iterations with shallower trees improved top-25
selection but not the primary candidate RMSE.

### Challengers and the prospective loop

New models are challengers, never automatic replacements. They live in
`artifacts/challengers/<name>/` with `production_eligible: false`;
`capture_fpl.py` only ever loads `artifacts/models/production_*`.

```bash
.venv/bin/python src/challengers.py refit --features data/processed/features_20261022            # M1
.venv/bin/python src/challengers.py season-transfer --features … --base refit_20261022           # M2
.venv/bin/python src/challengers.py crowd --features … --base refit_20261022                     # M5
.venv/bin/python src/challengers.py openfpl-style --features …                                    # M6
.venv/bin/python src/cup_minutes.py download                                                       # M8 data (research only)
.venv/bin/python src/challengers.py cup-minutes --features … --base refit_20261022                # M8
.venv/bin/python src/prospective_loop.py auto     # run before each deadline and after FPL checks a round
```

`prospective_loop.py auto` locks the production model, every registered
challenger and FPL's `ep_next` on identical rows within 30 hours of the next
deadline (one bundle per round), evaluates every round FPL has data-checked
and rebuilds `artifacts/prospective_eval/leaderboard.md`. A round that is not
locked before its deadline is simply missing.

**Criterion v2** ([docs/prospective_criterion_v2_2026-11-06.md](prospective_criterion_v2_2026-11-06.md),
`src/criterion_v2.py`) counts rounds locked from GW11. It compares weekly
absolute error player by player on a cohort fixed in the lock: the top 100,
players likely to appear and every locked squad. Rounds are resampled as blocks.
The primary challenger is `features_v2_20261106`, and the others are corrected
with Holm. The leaderboard shows v1 and v2 side by side, plus a secondary
measure where each model picks XI and captain in 300 ownership-weighted legal
squads.

**Shadow season** (`src/shadow_season.py`, plan E2): each policy (`hold`,
`incumbent`, challengers) carries your real squad, bank, purchase prices and
free transfers forward round by round. It decides from the loop's locked bundle
before the deadline and is scored with autosubs and vice-captain fallback.
`prospective_loop.py auto` locks and scores shadow seasons automatically.

```bash
.venv/bin/python src/shadow_season.py start --team ID --event N --policies hold incumbent refit_20261031
```

The web History group has a **Model and data** page (mobile: History → Model
and data quality). It shows data quality and what it means for decisions,
locked rounds with their counts, calibration and known limitations
(`GET /api/model-card`).

On 12 November 2026 `cup_minutes_20261022`, `openfpl_style_20261022` and `refit_20261022` were set
`active: false` (superseded or research-only data) so fewer challengers share the Holm correction.
`crowd` and `season_transfer` stay active because the shadow season's policies need them.

Two more corrections were tried on 12 November 2026 and **not registered**,
because `train_extra` registers only when the retrospective MAE on this season
beats the base (reports in `artifacts/model_research/*_retrospective.json`):

```bash
.venv/bin/python src/challengers.py features-v3 --features DIR --base refit_20261031   # M19: season xG/xA per 90, shrunk, last 10
.venv/bin/python src/challengers.py minutes-v2 --features DIR --base refit_20261031    # M18: competition for the place
```

On 2026-27 GW1–10 (6,562 rows) both lowered RMSE and bias a little but raised
MAE (1.168 → 1.180 and 1.186). Deadline rows now also carry `start_rate10`,
`xG90_last10`, `xA90_last10` and season-so-far sums, so they can be rerun when
more rounds exist.

Challengers added 6–8 November 2026 (phase D, all `production_eligible: false`, locked from GW11):

```bash
.venv/bin/python src/role_history.py --output data/processed/role_history_DATE.csv            # O5 roles/DC/price over time
.venv/bin/python src/challengers.py features-v2 --features DIR --base refit_20261031 --roles CSV  # M11 (primary in v2)
.venv/bin/python src/challengers.py top-calibration --features DIR --base refit_20261031         # M12
.venv/bin/python src/challengers.py implied-market --base refit_20261031 --results E0_2627_DATE.csv  # M13
```

`implied-market` fits each club's attack, defence and home advantage to odds
and results (`src/team_strengths.py`). It fills market features only where
odds are missing and marks every row `market_source = odds | implied`.
New capture and fpl-data manifests (schema 2) record `observed_at`,
`available_at` and `published_at` per file. `published_at` is unknown (null)
unless the source gives it; for odds it is the newest bookmaker update. They
also record `source_version` and `rules_version`.

Evaluation also writes `extended.json` per round (plan E3): Q10–Q90 hit rate
and width, and bias by position and defensive-contribution band. The
leaderboard shows them as secondary measures that never decide the criterion.
Diagnostics that compare captures with fpl-data outcomes:

```bash
.venv/bin/python src/prospective_loop.py extend                                  # extended.json for older rounds
.venv/bin/python src/availability_bias.py --output artifacts/m10_availability_bias_DATE   # M10: injury factor bias
.venv/bin/python src/forecast_timing.py --output artifacts/e3_forecast_timing_DATE        # T-24h vs T-6h vs last
```

`GET /api/data-quality` (plan O3) reports source freshness, odds coverage per
forecast Gameweek, the share of forecasts without market data, FPL `code`
coverage, missed locks and the last evaluated round. Each issue is described
by its effect on decisions.

The app shows a banner while the lock window is open (30 hours before the
deadline) and the round is not locked: **Lock window open for GW N – lock now**.
Its button runs the same `prospective_loop.py auto` as a background job on the
machine running the API (`POST /api/loop/lock`; progress in
`GET /api/loop/status`). **Refresh forecast** inside the window also starts the
lock once the new forecast is saved (plan M16, 12 November 2026); if the lock
check fails, the forecast is kept and the banner still offers the button.
Nothing is scheduled; a second lock of a locked round is refused. The banner also lists rounds that were never locked and a stale
`fpl-data` checkout. A challenger becomes eligible
for a *manual* promotion review only under the pre-registered criterion in
[docs/prospective_criterion_2026-10-22.md](prospective_criterion_2026-10-22.md).
Reports: [data pipeline](data_pipeline_2026-10-22.md),
[model phase](archive/model_phase_2026-10-22.md).

The component model separately learns minutes, goals, assists, clean sheets,
goals conceded, saves, bonus, cards and defensive contributions, then applies
FPL scoring rules. Monte Carlo produces expected points, Q10/Q50/Q90 and the
probability of at least 5 or 10 points. Its legal squad/XI/captain selection
scored 12 more points over 66 validation rounds, but the 95% interval included
zero. Q10–Q90 covered 85.3% of established candidates in 2025/26. It remains
`production_eligible: false` pending prospective validation under current rules.

Further evaluation and refitting commands:

```bash
.venv/bin/python src/decision_backtest.py
.venv/bin/python src/risk_profiles.py
.venv/bin/python src/season_simulator.py --transfer-policy historical --minimum-gain 0
.venv/bin/python src/season_simulator.py --transfer-policy historical --minimum-gain 1
.venv/bin/python src/season_simulator.py --transfer-policy historical --minimum-gain 2
.venv/bin/python src/production_models.py
.venv/bin/python src/capture_fpl.py --rescore-latest
```

Historical `value` prices are collected after the Gameweek and are not
certified deadline prices. The decision backtest is a strict deployment gate,
not a fully certified season simulation. Q10–Q90 coverage was 85.5% in
validation and 85.0% in the 2025–26 test. Summing fixture quantiles over multiple
weeks is a decision heuristic, not a calibrated multiweek interval.

The sequential simulator starts profiles with the same squad and handles bank,
individual selling prices, C/VC and legal autosubs. It uses the historical limit
of two banked free transfers in 2023–24, five from 2024–25 and the 2025–26 AFCON
reset to five after GW15. A MILP jointly chooses the final squad, XI and captain,
including purchases that need a funding transfer.

| Minimum model gain per transfer | balanced | stable | upside | Winner |
|---:|---:|---:|---:|---|
| 0.0 | 5,631 | **5,773** (+142) | 5,565 (−66) | stable |
| 1.0 | 5,502 | **5,740** (+238) | 5,577 (+75) | stable |
| 2.0 | **5,563** | 5,424 (−139) | 5,543 (−20) | balanced |

At 1.0, `stable` won all three seasons; at 2.0 it lost overall. These thresholds
were explored retrospectively and cannot become a new default without a separate
prospective test. The simulator still optimises the next Gameweek, not the whole
fixture block. Rule sources:
[five banked transfers](https://www.premierleague.com/en/news/4059225) and
[AFCON allocation](https://www.premierleague.com/en/news/4461660).

## Tests and notebooks

```bash
.venv/bin/python -m unittest discover -s tests -v
npm --prefix frontend run build
npm --prefix frontend run test:e2e:live
```

The Chromium live test requires network access and an active forecast. It imports
a team with an eight-Gameweek horizon and checks lineup, market, transfers and
all eight planned rounds.

Open [prediction vs actual](../notebooks/07_prediction_vs_actual.ipynb) with the
project's `.venv` kernel and run all cells. Choose a Gameweek and a genuinely
pre-deadline snapshot to compare model/app points with final official points,
minutes, goals, assists and bonus. Pending or missing results are not treated
as zero. The notebook includes plots, MAE/RMSE, cross-round summaries and CSV
export. Notebook outputs are cleared in source control; rerun locally to
regenerate tables and charts in English.

## Weekly strategy support

The strategy centre combines rolling/transferring/hits, squad health, captain
margin, deadline checks, official price indicators and model-filtered watchlists.
Hit plans are compared against a separate no-hit scenario and need an uncertainty
buffer before they are recommended. Further research and priorities are in
[manager strategy research](archive/fpl_manager_strategy_research_2026.md).

Preparing the app for a new round, by hand: **Refresh forecast** (or
`src/capture_fpl.py`), `src/prospective_loop.py auto` before the deadline, and
after the deadline **History → Top managers → Update** (or
`src/top_managers.py collect`) to see what the top 100, legacy and top 1% fielded.


Two data checkouts live in the repository root and are ignored by Git:
`data-source/` (https://github.com/vaastav/Fantasy-Premier-League) and
`fpl-data/` (own collected data, a clone of the private https://github.com/henrikremmen/fpl-data).