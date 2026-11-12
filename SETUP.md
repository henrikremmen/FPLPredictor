# Set up the project yourself

Step by step from `git clone` to running the web and mobile apps with your own
model. Run every command from the repository root unless stated otherwise.
More detail is in the [handbook](docs/handbook.md).

## 1. Requirements and installation

- Python 3.11 or later (developed on 3.13)
- Node.js 20 or later
- Git
- macOS: LightGBM needs OpenMP: `brew install libomp`

```bash
git clone https://github.com/henrikremmen/FPLPredictor.git
cd FPLPredictor

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt

npm install                     # mobile app and shared packages (npm workspaces)
npm install --prefix frontend   # the web app is installed separately
```

## 2. Data

The model needs two data sources. Both live in the repository root and are
ignored by Git.

### Historical seasons: vaastav

Seasons up to 2025-26 come from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League).
Clone it into `data-source/`:

```bash
git clone --depth 1 https://github.com/vaastav/Fantasy-Premier-League.git data-source
```

The repository is large, so `--depth 1` saves time and space.

### Current season: your own collection in `fpl-data/`

vaastav is no longer updated weekly, so the current season is collected from
the public FPL API with the project's own scraper, `src/fpl_collect.py`. The
original `fpl-data` is a private repository, so you build your own. Create an
empty folder and run the scraper once:

```bash
mkdir fpl-data
.venv/bin/python src/fpl_collect.py --data-root fpl-data auto
```

The first run fetches every finished and data-checked round of the season and
writes them as vaastav-compatible CSVs to `fpl-data/data/<season>/gws/`. It
takes a while. Every round is validated against a data contract
(`src/data_contract.py`) before anything is written. If the contract fails, the
scraper exits with an error code and writes nothing.

For history and backup, you can make the folder its own private Git repository:
`git -C fpl-data init`.

## 3. Train the first model

The app uses the model in `artifacts/models/production_*`. That folder is not
in Git, so you have to train the model yourself the first time.

### Build the training table and features

```bash
.venv/bin/python src/build_dataset.py    # vaastav + fpl-data -> data/processed/cleaned_merged_seasons_team_aggregated_expanded.csv
.venv/bin/python src/build_features.py   # -> data/processed/player_fixture_features.csv + feature_metadata.csv
```

An own season in `fpl-data` replaces vaastav's copy of the same season.

### Train, test and build the production model

```bash
.venv/bin/python src/nextgen_models.py      # trains and validates candidates -> artifacts/models/nextgen_*
.venv/bin/python src/decision_backtest.py   # decision test (squad, captain, budget) -> nextgen_*/decision_backtest.json
.venv/bin/python src/production_models.py   # refits on every completed season -> artifacts/models/production_*
```

This takes a long time. If the candidate does not beat the reference model,
`production_models.py` falls back to the reference model (`incumbent_blend`),
so you get a usable model either way.

If `decision_backtest.py` stops with `No production-eligible nextgen artifact`,
no candidate passed validation. Point at the folder manually instead:

```bash
.venv/bin/python src/decision_backtest.py --artifact artifacts/models/nextgen_XXXX
.venv/bin/python src/production_models.py --evaluation artifacts/models/nextgen_XXXX
```

### Optional: the market model

With `FOOTBALL_DATA_API_KEY` set (see section 6) you can also train the model
that uses odds. It is the one used in the original setup:

```bash
PYTHONPATH=src .venv/bin/python src/market_models.py --root .
```

It downloads historical odds from football-data.co.uk and creates
`artifacts/models/production_market_*` if it passes the tests. The app always
uses the newest approved `production_*` model.

### First forecast

```bash
.venv/bin/python src/capture_fpl.py
```

This takes a snapshot of FPL (prices, injuries, fixtures) and saves forecasts in
`data/raw/live_fpl/capture_*/`. The **Refresh forecast** button in the app does
the same.

## 4. Between Gameweeks

Shortcut: `./update.sh` runs the scraper, a fresh forecast, the prospective
loop and the top-manager collection in that order; `./update.sh retrain` also
does the training from section 3. The steps are described below; when to run
it and what in the app needs it is in [Updating](docs/updating.md).

Run the scraper regularly. It works out by itself what is due:

```bash
.venv/bin/python src/fpl_collect.py --data-root fpl-data auto
```

- **Daily, after 02:30 UTC:** a light snapshot (prices, status, fixtures).
- **24, 6 and 1 hour before the deadline:** checkpoints. These cannot be
  fetched afterwards, so run the scraper in these windows if you want them.
- **When FPL marks a round `finished` and `data_checked`:** a full export of the
  round. A missed day only loses that day's snapshot; finished rounds can always
  be fetched later.

Runs are idempotent: a second run in the same hour does nothing. The output
shows `gap_hours` since the previous snapshot.

Before each deadline, fetch a fresh forecast with **Refresh forecast** in the
app or with `.venv/bin/python src/capture_fpl.py`.

For the model to learn from the new rounds, run section 3 again:
`build_dataset.py` and `build_features.py`, then the training. This is not
needed every week.

## 5. Run the apps

### Web app

```bash
.venv/bin/python run_app.py
```

- Web app: http://127.0.0.1:5173
- API documentation: http://127.0.0.1:8000/docs

Enter your FPL team ID (the number in your team link, or the whole link) and
click **Load team**. If the app says it is already running, free the ports:

```bash
kill $(lsof -tiTCP:8000 -sTCP:LISTEN) $(lsof -tiTCP:5173 -sTCP:LISTEN)
```

### Mobile app (Expo)

The mobile app uses the same backend. Start the backend in one terminal and
Expo in another.

**Simulator or browser on the same machine:**

```bash
cp apps/mobile/.env.example apps/mobile/.env   # EXPO_PUBLIC_API_URL=http://127.0.0.1:8000
.venv/bin/python run_app.py                    # terminal 1
npm run mobile                                 # terminal 2: i = iOS simulator (needs Xcode), w = browser
```

Without a simulator: `npm --prefix apps/mobile run web`.

**Physical phone on the same Wi-Fi:**

First put a long random `FPL_API_TOKEN` in the root `.env` (for example from
`openssl rand -hex 24`) and the same value as `EXPO_PUBLIC_API_TOKEN` in
`apps/mobile/.env`. The API refuses to start on `0.0.0.0` without it, and
every request except `/api/health` must then carry it.

```bash
npm run backend:lan     # API on 0.0.0.0, prints your local IP
```

Put the IP in `apps/mobile/.env`, for example
`EXPO_PUBLIC_API_URL=http://192.168.1.23:8000`. Then start Expo
(`npm run mobile`) and scan the QR code with Expo Go. Restart Expo after
changing `.env`. Allow incoming connections for Python if the macOS firewall
asks.

## 6. API keys in `.env`

The app works without keys, because the public FPL API needs none. The keys give
better forecasts and more features. Copy the template and put each value right
after the `=`, without quotes or spaces:

```bash
cp .env.example .env
```

| Variable | What it gives | Where to get it |
|---|---|---|
| `ODDS_API_KEY` | Match-result and over/under 2.5 goals odds, converted to expected team goals and clean-sheet probabilities. The market model uses these and falls back to the model without odds when they are missing. | [the-odds-api.com](https://the-odds-api.com/) (a free plan exists) |
| `ODDS_PLAYER_PROPS` | `1` also fetches anytime-goalscorer and assist odds. Uses many credits (one request per fixture) and is currently for research only. Leave it at `0`. | Uses `ODDS_API_KEY` |
| `FOOTBALL_DATA_API_KEY` | Cup, European and international schedules. Also needed to train the market model. | [football-data.org](https://www.football-data.org/client/register) (free key) |
| `ANTHROPIC_API_KEY` | The **Ask Claude** chat in the web app. Reread on every message, so no restart is needed. | [console.anthropic.com](https://console.anthropic.com/settings/keys). The account needs credits under Billing. |

About the keys:

- The odds and football-data keys are read by `capture_fpl.py`. Run
  **Refresh forecast** after adding them.
- A missing key just skips that source. This is recorded in the forecast
  manifest.
- The keys are read only by the Python backend and never sent to the browser or
  the mobile app. Do not put them under `frontend/`, in a `VITE_` variable or in
  `apps/mobile/.env`.
- `.env` is ignored by Git. Do not commit it.

The chat costs about $0.37 for the first question of a conversation. That sends
around 90,000 tokens of forecast and team data, cached for an hour. Follow-up
questions within the hour cost about $0.02–0.04. If you make the API reachable
from outside your own machine, anyone who can reach it can spend your key, so
add authentication and limits first (see [deploy](docs/deploy.md)).

`apps/mobile/.env` has a single variable, `EXPO_PUBLIC_API_URL`, the address of
the backend (see section 5). Host, port, CORS and database variables for
deployment are in [docs/deploy.md](docs/deploy.md).

## 7. Check that everything works

```bash
.venv/bin/python -m unittest discover -s tests
npm run build --prefix frontend
npm run typecheck:mobile && npm run test:mobile
```
