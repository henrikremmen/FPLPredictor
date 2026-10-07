# FPL Model and Decision App

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
Choose a forecast horizon and risk profile, then click **Load team**. A sample
team URL is prefilled.

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
[manager analytics research](docs/manager_analytics_research_2026.md) for methods
and limitations.

## Repository structure and commands

```text
src/                 Python models, decision engine and FastAPI backend
frontend/            React web app
apps/mobile/         Expo/React Native app with TypeScript and Expo Router
packages/api-client/ Typed client for src/api.py and shared API types
packages/shared/     Shared constants and formatting
notebooks/           Data exploration, model evaluation and forecast comparisons
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
[the App Store checklist](docs/mobile/app-store-checklist.md).

TestFlight testers need a public HTTPS backend; see [deployment](docs/deploy.md).
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

See [model research](docs/model_research_2026.md),
[product research](docs/product_feature_research_2026.md) and
[manager strategy research](docs/fpl_manager_strategy_research_2026.md).

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
See [chip methodology](docs/chip_strategy.md).

## Training and model evaluation

Historical data use
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League).
Live forecasts are generated by `src/capture_fpl.py`; the decision app is in
`src/fpl_app.py`. Production promotion requires both prediction-quality gates
and a historical budget/position/club/lineup/captain backtest. The P(60+) model
is evaluated and refitted separately from points ranking.

```bash
.venv/bin/python src/nextgen_models.py
.venv/bin/python src/model_lab.py
.venv/bin/python src/component_benchmark.py
```

`model_lab.py` compares the incumbent with CatBoost and, when available,
LightGBM. On macOS, LightGBM requires OpenMP; if needed:

```bash
sudo xcodebuild -license accept
brew install libomp
```

CatBoost improved some top-selection and captain metrics but lost overall RMSE
on the untouched 2025/26 holdout and was not promoted. Missing `libomp` causes
LightGBM to be skipped and the error recorded in `settings.json`. Increasing
training from 500 to 800 iterations with shallower trees improved top-25
selection but not the primary candidate RMSE.

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
.venv/bin/python src/uncertainty_models.py
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

Open [prediction vs actual](notebooks/07_prediction_vs_actual.ipynb) with the
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
[manager strategy research](docs/fpl_manager_strategy_research_2026.md).
