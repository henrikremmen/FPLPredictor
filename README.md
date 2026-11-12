# FPL Model and Decision App

Forecasts Fantasy Premier League points and turns them into decisions: lineup,
captain, transfers, multiweek plans and chips. Web app (React), mobile app
(Expo) and a Python/FastAPI backend. Public FPL data only: it never logs in to
your account and never makes transfers for you.

The full reference is the **[handbook](docs/handbook.md)**.

## Start

Node.js 20 or later and Python 3.

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
npm install && npm install --prefix frontend
.venv/bin/python run_app.py            # web http://127.0.0.1:5173 · API http://127.0.0.1:8000/docs
```

Enter your FPL team ID, then **Load team**. Before a deadline, use
**Refresh forecast** to fetch the latest news, prices and forecasts. If the app
says it is already running, free the ports:
`kill $(lsof -tiTCP:8000 -sTCP:LISTEN) $(lsof -tiTCP:5173 -sTCP:LISTEN)`.

Mobile: `npm run mobile` (Expo Go/simulator) or `npm --prefix apps/mobile run web`.
For a phone on the same Wi-Fi, start the backend with `npm run backend:lan`.

## Everyday commands

When to run what, and what in the app needs it: [Updating](docs/updating.md).

```bash
./update.sh                                         # all routine steps below in order (./update.sh retrain also retrains)
.venv/bin/python src/capture_fpl.py                 # new FPL snapshot + forecasts (what Refresh forecast does)
.venv/bin/python src/prospective_loop.py auto       # before each deadline and after FPL checks a round (or the app's Lock button; Refresh forecast in the last 30 h also locks)
.venv/bin/python src/top_managers.py collect        # after a deadline: top 100, legacy, top 1% and YouTuber squads (or History → Top managers → Update)
.venv/bin/python src/copy_check.py collect --entry <FPL id>   # who in your mini-leagues looks most like a YouTuber or a friend (also part of Update)
.venv/bin/python src/fpl_collect.py --data-root fpl-data auto   # own data: daily snapshot, deadline checkpoints, finished rounds
.venv/bin/python src/build_dataset.py               # training table from vaastav + fpl-data seasons
```

## What it does

- **This week** (the start page): the round's steps in the order you do them in
  FPL: transfers with prices, the XI and bench after the transfer, captain and
  vice-captain, chip, what would change the plan, and a checklist to copy. The
  app never makes the transfers for you.
- **This round:** overview, recommended XI, captain and bench.
- **Transfers & plan:** strategy centre (roll or move), exact transfer search,
  a multiweek plan with chips, bench weights and requirements, plan A/B and
  scenarios with your own assumptions, chips, Free Hit and Wildcard squads.
- **Players:** market, fixture ticker, hold-versus-buy comparison, lock or exclude players, bench weights.
- **History:** manager and mini-league analysis, a timeline of every played
  Gameweek on the pitch, your decision journal, and the model and data quality.
- **My team:** correct squad, bank and free transfers; saved plans.

Risk profiles: **Balanced** ranks by expected points, **Stable** penalises wide
outcome ranges, and **Upside** weights the ceiling (0.7 × expected + 0.3 × Q90).

## Data and models

- Current-season data come from `fpl-data/`, filled by the collector. It runs
  by itself every hour while `run_app.py` is running, and can be run by hand. It writes vaastav-format CSVs and validates every round against a
  data contract. Earlier seasons come from vaastav.
- The production model is never replaced automatically. Challengers are locked
  before each deadline and scored afterwards on a leaderboard
  (`artifacts/prospective_eval/leaderboard.md`) under a
  [pre-registered criterion](docs/prospective_criterion_2026-10-22.md).

## Tests

`npm run test:all` runs the backend tests, the web, shared and mobile type
checks and the mobile tests in one go. No CI runs them, so run it before a commit.

```bash
.venv/bin/python -m unittest discover -s tests
npm run build --prefix frontend && npm run test:e2e:workspace --prefix frontend
npm run typecheck:mobile && npm run test:mobile
```

## More

[Handbook](docs/handbook.md) · [Data pipeline](docs/data_pipeline_2026-10-22.md) ·
[Deploy](docs/deploy.md) · [Chip strategy](docs/chip_strategy.md) ·
[Archive](docs/archive/) (finished plans, phase reports and research)

Two data checkouts live in the repository root and are ignored by Git:
`data-source/` ([vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League))
and `fpl-data/` (own collected data, a clone of the private github.com/henrikremmen/fpl-data).
