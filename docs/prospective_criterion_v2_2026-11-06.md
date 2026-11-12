# Pre-registered criterion for a model switch (version 2)

*Translated from Norwegian on 11 November 2026. The content is unchanged; the
original text is in commit 78eb82c.*

Registered on 6 November 2026 at 15:30 UTC. That is before GW11 is locked (the
window opens 20 November at 05:00 UTC) and before any outcome exists for the
rounds this version covers. [Version 1](prospective_criterion_2026-10-22.md) is
unchanged. It is still computed and reported for every loop round. The
criterion is also in the code (`CRITERION_V2` in `src/criterion_v2.py`) and is
shown on the leaderboard. Changes require a new, dated version.

## Why a v2

v1 compares team points for each model's own squad. The difference per round
has a standard deviation of about 13 points (66-round backtest, see
`production_market_0erysib7/settings.json`). Detecting a gain of 2 team points
per round with 80% power and 95% confidence needs about
(2.80 × 13 / 2)² ≈ 330 rounds. v1 will therefore almost never be met, even for
a real improvement. v2 uses the whole cohort of relevant players in each round.

## What counts

- Only loop bundles (`loop-v1`) locked after the registration time. The first
  possible round is GW11. GW8 and GW10 are shown as diagnostics and do not
  count.
- Only final outcomes: FPL has marked the round `finished` and `data_checked`.
  Lock rules, hashes and identical cohorts are as in v1.
- The reference is `incumbent`, the production model at the time of the lock.

## Cohort (fixed before the deadline)

The cohort is determined only by what is frozen in the lock: the reference's
forecasts and probabilities and the squads the models chose. A player is
included if at least one of these holds:

1. The player is among the top 100 by the reference's forecast for the round.
2. The reference's probability of at least one appearance in the round is at
   least 0.5.
3. The player is in at least one locked squad (all models, including
   `fpl_ep_next`).

In GW8 this gave 314 players. Actual minutes are never used to select the
cohort.

## Primary measure and rule

For each round *r* and each cohort player, the absolute error in weekly points
is computed. d_r is the cohort mean of (challenger's error − reference's
error). A negative value means the challenger is better.

**Primary challenger:** `features_v2_20261106` (plan M11). It is locked from the
first possible round after registration. The primary challenger is **eligible
for a switch review** only when all three points hold:

1. At least **8** counting rounds.
2. The whole 95% interval for the mean of d_r lies **below 0**. It is a block
   bootstrap in which whole rounds are drawn with replacement, with 10,000
   draws and seed 20261106.
3. The guard: the mean difference in pinball loss (Q10/Q50/Q90, a three-point
   approximation to CRPS) is **≤ 0** when both models have quantiles.

**Other challengers** are exploratory. Their one-sided bootstrap p-values (the
share of draws with a mean ≥ 0) are Holm-corrected. An exploratory challenger
is eligible only with Holm p < 0.05, at least 8 rounds and the guard met. This
prevents picking a random winner among many.

## Secondary measures (reported, not deciding)

- v1 team points for the model's own squad.
- **Synthetic squads:** 300 legal squads (2/5/5/3, at most three per club, at
  most £100m) drawn in proportion to ownership from the locked bootstrap file,
  with seed 20261106. Each model picks XI and captain in each squad
  (`fpl_app.optimal_lineup`). The number is actual points with captain × 2,
  without autosubs.
- The shadow season (E2) with bank, free transfers and autosubs/VC, once it has
  rounds.
- The E3 measures: Brier, calibration, interval hit rate and width, and bias by
  position and DC group.

## Power calculation

d_r has a standard deviation σ per round. It is estimated from 2025-26 (38
rounds, top 100 cohort, `artifacts/models/market_1sny_8dq/test_predictions.csv`)
for two model pairs: 0.020 and 0.044, median **0.032**. The number of rounds for
80% power (two-sided 95%) is n = ((1.96 + 0.84) · σ / δ)²
(`criterion_v2.rounds_needed`):

| Real gain δ in MAE per cohort player | About % of MAE (≈ 2.0) | Rounds |
|---:|---:|---:|
| 0.10 | 5% | 1 (minimum of 8 applies) |
| 0.05 | 2.5% | 4 (minimum of 8 applies) |
| 0.032 | 1.6% | 8 |
| 0.02 | 1% | 20 |

With 8 rounds we can expect to detect about δ ≥ 0.03. For comparison,
`refit_20261022` differed from the reference by +0.016 in GW8 (worse). σ is
estimated on one season and two model pairs, so the numbers are rough.

## What the criterion does not do

As in v1, the loop never switches the production model. A switch is a manual
decision. It is documented, dated, with the leaderboard as its basis, and built
with the usual refit code. Challengers have `production_eligible: false`.
