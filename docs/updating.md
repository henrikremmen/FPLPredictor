# Updating

How to keep the app's data and forecasts current with `update.sh`, and which
parts of the app need an update before use.

## In short

Run `./update.sh` from the repository root before you use the app, and always
before and after each deadline. Every step works out by itself what is due and
skips what is already done, so it is safe to run as often as you like.

```bash
./update.sh
```

It is finished when it prints `Done.` Reload the app afterwards to see the new
numbers. The app can stay running while the script runs.

## Using update.sh

```bash
./update.sh            # routine update, a few minutes
./update.sh retrain    # the same, plus retraining the model (slow)
```

The steps run in this order, and each prints `== <name>` in the terminal:

1. **Own data (fpl-data):** `fpl_collect.py auto` takes the daily snapshot,
   the deadline checkpoints and finished rounds. If anything changed, it is
   saved with a local commit in `fpl-data`. Nothing is pushed.
2. **Training table and features, Retrain (only with `retrain`):**
   `build_dataset` → `build_features` → `nextgen_models` → `decision_backtest`
   → `production_models`. Runs before the forecast, so the forecast uses the
   new model.
3. **Forecast:** `capture_fpl.py` fetches prices, injuries and fixtures and
   makes a new forecast. The same as **Refresh forecast** in the app.
4. **Prospective loop:** `prospective_loop.py auto` locks the round when the
   deadline is less than 30 hours away and evaluates rounds FPL has checked. It
   reuses the forecast from step 3. **Refresh forecast** in the app starts this lock by
   itself when the window is open and the round is not locked yet.
5. **Top managers:** `top_managers.py collect` fetches what the top 100,
   legacy, top 1% and YouTuber managers fielded in the latest round.

Retraining is not needed every week. Run it when several new rounds have been
added since the last time, for example every few weeks.

## When to run it

| When | What happens | What update.sh does |
|---|---|---|
| Every day after 02:30 UTC | FPL price changes are done | Daily snapshot |
| 30 hours before the deadline | The lock window opens | Locks the round in the prospective loop |
| 24, 6 and 1 hours before the deadline | Deadline checkpoints | Snapshot. These cannot be fetched afterwards |
| Right before the deadline | Last chance to decide | Fresh forecast with the latest news |
| After the deadline | FPL moves to the next round | Forecast for the new round, top-manager squads |
| When FPL marks a round `finished` and `data_checked` | The round's data is final | Round export and evaluation |

In practice: run it before the deadline (within 30 hours, and again right
before you decide) and after the deadline. A missed day only loses that day's
snapshot; finished rounds can always be fetched later.

## What in the app needs an update

Almost everything in the app is built on the forecast, and the forecast must be
updated after every deadline. A forecast belongs to one specific round, so when
FPL moves on, **Load team** stops until you update.

| Part of the app | Built on | Update | Without an update |
|---|---|---|---|
| This round: recommended XI, captain, bench | Forecast (step 3) | After every deadline, and right before you decide | After the deadline: `No model forecast found for GW…`. Before the deadline: no new odds, expected minutes or press-conference news since last time |
| Transfers & plan: transfers, multiweek plan, chips, recommended squads | Forecast (step 3) | As above | As above |
| Scenarios and player details | Forecast (step 3) | As above | As above |
| Ask Claude | Forecast (step 3) | As above | Answers from the old forecast |
| Changes since last time | The two latest forecasts | Every time the forecast is updated | Shows changes from an older forecast |
| Leaderboard and model card | Lock (step 4) | Within 30 hours before the deadline | The round does not count in the model comparison. Advice is not affected |
| Top managers: top 100, legacy, top 1%, YouTubers | `top_managers.py collect` (step 5) | After the deadline | Shows the previous round, or nothing |
| Copy check | **Update** under History → Top managers | After the deadline | Missing. Not part of `update.sh`, because it needs your team ID |
| Data quality and training | Own data (step 1) | At least once a day | The app warns when the latest snapshot is over 36 hours old. Training misses new rounds |

## What is live

Fetched from FPL every time you load your team, so never in need of an update:

- your squad, bank and free transfers
- prices and player status (injured, doubtful, suspended)
- History: your own rounds and your mini-leagues

The model forecast itself is not live. The app scales it by FPL's live chance
of playing, so a player flagged as injured drops at once, but new odds,
expected minutes and form only arrive when you update the forecast.

## Not included, and troubleshooting

Not part of `update.sh`:

- **Copy check:** press **Update** under History → Top managers in the app, or
  run `.venv/bin/python src/copy_check.py collect --entry <team id>`.
- **Pushing fpl-data:** the script only makes a local commit.

When a step fails, the script stops and shows the error under that step. The
steps after it do not run. Running it again is always safe.

| Error | Cause | Fix |
|---|---|---|
| Connection error or timeout against FPL | The FPL API is down or updating, often around a deadline | Wait a few minutes and run again |
| `ContractError` in step 1 | A round from FPL breaks the data contract. Nothing is written | Wait until FPL has corrected the data and run again |
| `No production-eligible nextgen artifact` during retrain | No new model passed validation | Point at the folder manually, see section 3 in [SETUP](../SETUP.md) |
| `No Gameweek has started yet` in step 5 | The season has not started | Nothing to do. All earlier steps ran |
