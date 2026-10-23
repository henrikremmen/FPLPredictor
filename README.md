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

```bash
.venv/bin/python src/capture_fpl.py                 # new FPL snapshot + forecasts (what Refresh forecast does)
.venv/bin/python src/prospective_loop.py auto       # before each deadline and after FPL checks a round
git -C fpl-data pull                                 # data collected hourly by the fpl-data repository
.venv/bin/python src/build_dataset.py               # training table from vaastav + fpl-data seasons
```

## What it does

- **This round:** overview, recommended XI, captain and bench.
- **Transfers & plan:** strategy centre (roll or move), exact transfer search,
  multiweek plan, chips, Free Hit and Wildcard squads.
- **Players:** market, hold-versus-buy comparison, lock or exclude players.
- **History:** manager and mini-league analysis, and a timeline of every
  played Gameweek on the pitch.
- **My team:** correct squad, bank and free transfers; saved plans.

Risk profiles: **Balanced** ranks by expected points, **Stable** penalises wide
outcome ranges, and **Upside** weights the ceiling (0.7 × expected + 0.3 × Q90).

## Data and models

- Current-season data come from the private `fpl-data` repository. Its GitHub
  Actions collector runs hourly, writes vaastav-format CSVs and validates every
  round against a data contract. Earlier seasons come from vaastav.
- The production model is never replaced automatically. Challengers are locked
  before each deadline and scored afterwards on a leaderboard
  (`artifacts/prospective_eval/leaderboard.md`) under a
  [pre-registered criterion](docs/prospective_criterion_2026-10-22.md).

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
npm run build --prefix frontend && npm run test:e2e:workspace --prefix frontend
npm run typecheck:mobile && npm run test:mobile
```

## More

[Handbook](docs/handbook.md) · [Data pipeline](docs/data_pipeline_2026-10-22.md) ·
[Model phase](docs/model_phase_2026-10-22.md) · [Deploy](docs/deploy.md) ·
[Chip strategy](docs/chip_strategy.md) · [Improvement plan](docs/forbedringsplan_2026-10-22.md)

Two data checkouts live in the repository root and are ignored by Git:
`data-source/` ([vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League))
and `fpl-data/` (github.com/henrikremmen/fpl-data, private).
