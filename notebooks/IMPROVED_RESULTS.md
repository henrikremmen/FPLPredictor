# Improved model results

`04_improved_models.ipynb` uses `src/improved_models.py` and the project's `.venv`. Regenerate notebook outputs locally.

Eight predefined variants were compared on two chronological folds: train on 2022–23 and validate on 2023–24; then train on 2022–24 and validate on 2024–25. Selection uses mean seasonal RMSE. Compare candidates against references evaluated on these same folds, rather than against the earlier notebooks' different setup.

| Variant | Mean validation RMSE | Candidate RMSE |
|---|---:|---:|
| Ridge + extended HGB + minutes mixture | **1.91715** | **3.08332** |
| Ridge + HGB | 1.91860 | 3.08362 |
| Minutes mixture | 1.92174 | 3.09450 |
| Baseline HGB | 1.92455 | 3.09725 |
| New HGB | 1.92485 | 3.09907 |
| HGB with more leaves | 1.93197 | 3.11749 |

Candidates have historical `minutes_avg5 >= 60`; their actual future minutes are never used to select them. The minutes mixture models zero, 1–59 and 60+ minutes separately.

The winner was refitted on 2022–25 and evaluated on 2025–26:

| Model | RMSE | MAE | Spearman |
|---|---:|---:|---:|
| Three-model ensemble | **1.93332** | **0.96737** | **0.71443** |
| Baseline HGB | 1.93592 | 0.96860 | 0.71319 |

The improvement is small. Mean bias is approximately −0.094 for the ensemble and −0.086 for HGB. No bias adjustment is fitted on test data. Validation-gameweek bootstrapping gives positive MSE gains, but these intervals are descriptive and do not correct for candidate selection. Future gains are uncertain.

Features use pre-fixture timing rather than certified deadline timing. The holdout has been explored, and top-k performance is not a full transfer strategy evaluation. Probability checks verify finite outputs, class probabilities summing to one, and separation from actual future minutes and targets.

Generated `improved_*` artifacts require the matching source path and feature enrichment. The subsequent production decision is documented in `NEXTGEN_RESULTS.md`.
