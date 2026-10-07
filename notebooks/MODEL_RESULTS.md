# Baseline model results

The baseline notebooks are `01_dummy_baseline.ipynb`, `02_ridge_baseline.ipynb` and `03_hist_gradient_boosting.ipynb`. Shared experiments live in `src/model_experiments.py`. Run them with the project's `.venv`; notebook outputs can be regenerated locally.

## Chronological evaluation

Features, training windows and parameters were selected on 2024–25 validation RMSE. Selected models were then refitted through 2024–25 and evaluated on 2025–26.

| Model | Validation RMSE | Validation MAE | Holdout RMSE | Holdout MAE |
|---|---:|---:|---:|---:|
| Dummy | 2.311 | 1.436 | 2.352 | 1.501 |
| Ridge | 1.926 | 1.035 | 1.943 | 1.002 |
| HGB | 1.928 | 1.008 | 1.936 | 0.969 |

Ridge selected alpha 100 and training on 2023–24. HGB selected seven leaves and training on 2022–23 plus 2023–24. Both selected 34 contextual features covering minutes, FPL/ICT form, underlying attack, goalkeeper/defensive statistics, position, home/away, team and opponent.

The difference is small. Ridge offers a more interpretable reference; HGB has lower MAE and useful ranking performance. `minutes_last1` is its most important feature.

## Timing and interpretation

- SAFE features are calculated before each fixture. They are not certified deadline features: later fixtures in a double gameweek can incorporate earlier results from that gameweek.
- The 2025–26 season has already been explored and is no longer a pristine holdout. Do not tune further on it.
- The dataset excludes 322 Assistant Manager rows from 2024–25 and retains zero-minute players. Roughly 60% of outcomes are zero points; segmented metrics matter.
- Top-k metrics aggregate double-gameweek points retrospectively and do not enforce a legal squad or budget.
- Historical `xP` and market fields are excluded. Position and home/away fields require explicit timing review. Targets never enter X.
- Preprocessing fits training data only. Missing xG stays missing rather than becoming zero.

Next steps are more chronological folds and verified deadline-history snapshots. See `IMPROVED_RESULTS.md`, `NEXTGEN_RESULTS.md` and `DEADLINE_BACKTEST.md` for subsequent experiments and limitations.
