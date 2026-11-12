# Pre-registered criterion for a model switch (version 1)

*Translated from Norwegian on 11 November 2026. The content is unchanged; the
original text is in commit 9305dcf.*

Registered on 22 October 2026, before the deadline and outcomes of GW8, the
first round the automatic prospective loop locks (`src/prospective_loop.py`).
The criterion is also in the code (`CRITERION` in `prospective_loop.py`), and
the leaderboard shows the version. Changes require a new, dated version. Rounds
evaluated under an older version are still reported under that version.

## What counts

- Only rounds where the reference and the challengers were locked by the loop
  before the deadline, with identical player and fixture cohorts and hashes
  (`prospective_lock.verify_lock`).
- Only final outcomes. FPL must have marked the round `finished` and
  `data_checked`. Provisional evaluation does not count.
- The reference is the production model at the time of the lock (`incumbent`).

## Primary measure and rule

For each round, the difference between challenger and reference is computed in
**locked team points**. These are the points of the XI and captain from each
model's own legal 100 million squad, chosen before the deadline
(`freeze_decisions`).

A challenger is **eligible for a switch review** only when all three points
hold:

1. At least **8** evaluated rounds.
2. The whole 95% bootstrap interval for the mean difference per round lies
   **above 0**. The interval is computed with 10,000 draws of rounds with
   replacement and seed 20261022.
3. The mean difference in MAE for weekly points per player is **≤ 0**, that is,
   no worse point forecasts.

## What the criterion does not do

- The loop never switches the production model. The leaderboard only shows
  whether the criterion is met.
- A switch is a manual decision. It is documented, dated, in `docs/` with the
  leaderboard as its basis, and built with the usual refit code.
- Challengers are stored in `artifacts/challengers/` with
  `production_eligible: false`. `capture_fpl.select_model_path` never reads from
  there.

## Secondary measures (reported, not deciding)

MAE and RMSE per fixture and per week, captain points, Brier for 60+ minutes and
calibration groups when the model gives probabilities.
