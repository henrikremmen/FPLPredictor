# Next-generation model audit and results

## Conclusion

`long_history_mixture_15` won the prediction benchmark. Production continues to use the previous three-model ensemble for expected points because it scored better in the budget-constrained squad-selection benchmark. The 15-leaf model supplies P(60+ minutes).

The main improvement came from extending training history from 2022–23 to 2020–21 and increasing the minutes classifier from seven to 15 leaves. It distinguishes between zero, 1–59 and 60+ minutes. Position-specific models, Extra Trees and a new global HGB configuration did not outperform this approach overall.

After evaluation, the points engine was refitted on 2022–23 through 2025–26 and the minutes model on 2020–21 through 2025–26. These production refits are separate from the reported holdout evaluation.

## Comparison on identical folds

Results average the 2023–24 and 2024–25 validation seasons. Long-history candidates start training in 2020–21; other candidates start in 2022–23.

| Model | RMSE | Candidate RMSE | Top-25 actual points | Captain points |
|---|---:|---:|---:|---:|
| Long history + 15-leaf minutes mixture | **1.91254** | **3.07456** | **4.7908** | 6.9459 |
| Long history + 7-leaf minutes mixture | 1.91349 | 3.07575 | 4.7643 | 7.1216 |
| Previous three-model ensemble | 1.91715 | 3.08332 | 4.7286 | 7.1216 |
| Long history + HGB | 1.91752 | 3.07974 | 4.7735 | 6.6892 |
| Extra Trees | 1.91970 | 3.09186 | 4.6919 | 6.7973 |
| Long history + Ridge | 1.92271 | 3.08407 | 4.7124 | **7.7838** |
| Position-specific minutes mixture | 1.93014 | 3.10896 | 4.5616 | 6.1081 |

Candidates have historical `minutes_avg5 >= 60`. Top-25 and captain metrics aggregate player/gameweek rows first, so double gameweeks do not count a player twice.

Paired bootstrap over 76 whole gameweeks gives an MSE improvement of `0.01810` and a 95% interval of `[0.00583, 0.02980]`. This interval is descriptive: it does not correct for selection among multiple candidate models.

## Decision benchmark with FPL rules

For GW6–38 in both validation seasons, an exact MILP selected 15 players, a legal starting XI and a captain within £100m and three players per club. Historical price, club and position were attached to each prediction.

| Model | Gameweeks | Actual points | Points per GW | Mean regret against oracle |
|---|---:|---:|---:|---:|
| Previous three-model ensemble | 66 | **4,171** | **63.197** | **93.106** |
| Long history + 7-leaf minutes mixture | 66 | 4,166 | 63.121 | 93.182 |
| Long history + 15-leaf minutes mixture | 66 | 4,153 | 62.924 | 93.379 |

The 15-leaf candidate finished 18 points behind the incumbent, or −0.273 per gameweek. Its paired bootstrap interval, `[−3.591, 2.970]` points per gameweek, is too wide to establish inferiority. However, it fails the promotion requirement of matching the incumbent's observed decision score.

A 75% candidate blend gained 99 points in 2023–24 and lost 77 in 2024–25. Selecting its weight retrospectively on these same seasons would overfit the evaluation.

This benchmark optimizes each week independently. Transfers, automatic substitutions, chips and changing squad value are not simulated. Historical `value` was recorded after the gameweek and is not a verified deadline price.

## 2025–26 holdout

| Model | RMSE | MAE | Spearman | Candidate RMSE | Top-25 points |
|---|---:|---:|---:|---:|---:|
| Long history + 15-leaf minutes mixture | **1.93061** | **0.96009** | **0.71849** | **3.11541** | **4.3319** |
| Long history + 7-leaf minutes mixture | 1.93193 | 0.96241 | 0.71768 | 3.11647 | **4.3881** |
| Previous ensemble | 1.93332 | 0.96737 | 0.71443 | 3.12020 | 4.2941 |

This holdout had already been explored. It serves as a promotion check rather than an untouched confirmatory experiment.

## Limitations

1. The source audit verified 152 bootstrap snapshots, but no gameweeks with complete verified fixture and history snapshots. These model results use pre-fixture timing, not certified deadline timing.
2. Prediction improvements are small.
3. Overall RMSE is dominated by zero-point rows. Candidate RMSE, top-25, captain and NDCG metrics now provide additional decision checks.
4. Captain performance is unstable. Ridge led this metric despite worse overall error and top-25 performance. The app exposes small captain margins.
5. Injury and rotation signals remain incomplete. Public availability does not provide expected minutes.
6. Multiweek forecasts sum fixture predictions using information known today. They do not anticipate future injuries, price changes or news.
7. Public team links provide estimated selling prices and free transfers rather than authenticated values.
8. Decision performance varies between seasons, supporting a conservative production choice.
9. Historical prices are not verified deadline snapshots.

For the 15-leaf minutes model, validation log loss is `0.48833`, the 60+ Brier score is `0.08600`, and ten-bin ECE is `0.00663`. Holdout values are `0.45727`, `0.08146` and `0.00563`. Temperature calibration was rejected because it worsened the following season's probabilities and points RMSE.

## Quantiles and risk profiles

A separate HGB model estimates Q10, Q50 and Q90. All three beat a position-specific unconditional baseline on pinball loss in both validation seasons and the 2025–26 test. Q10–Q90 covered 85.49% of established candidates in validation and 85.01% in the test. This is a conditional model range, not a guaranteed confidence interval.

| Profile | Formula | Validation gain against balanced | 2025–26 gain against balanced |
|---|---|---:|---:|
| balanced | expected points | – | – |
| stable | expected points − `0.1 × (Q90−Q10)` | **+85** | **+20** |
| upside | `0.7 × expected points + 0.3 × Q90` | +64 | −28 |

In 2025–26, upside raised the 90th percentile of actual weekly scores from 76.0 to 79.8, while lowering the mean and increasing standard deviation. These profiles remain exploratory; balanced is the default.

### Sequential transfer evaluation

Profiles also start from the same squad with historically correct free-transfer rules: a maximum of two in 2023–24, five from 2024–25, and replenishment to five after GW15 in 2025–26. The simulator handles cash, individual selling prices, vice-captain substitution and formation-valid automatic substitutions. An exact MILP jointly selects zero to N transfers, the final squad, XI and captain. With N=1, totals match exhaustive single-transfer search.

| Minimum model gain per transfer used | balanced | stable | upside |
|---:|---:|---:|---:|
| 0.0 | 5,631 | **5,773** (+142) | 5,565 (−66) |
| 1.0 | 5,502 | **5,740** (+238) | 5,577 (+75) |
| 2.0 | **5,563** | 5,424 (−139) | 5,543 (−20) |

At 0.0, stable lost 57 points in 2023–24, gained 190 in 2024–25 and gained nine in 2025–26. At 1.0, it gained 18, 91 and 129 respectively. At 2.0, it lost 139 overall. Transfer banking and multiple moves affect the conclusion, and the opportunity-cost threshold is sensitive. Promoting `stable + 1.0` after inspecting these same seasons would overfit the policy. Balanced remains the production default.

The simulator uses next-gameweek predictions and post-gameweek historical prices. A rolling 3–6-GW plan using only information available at each deadline needs prospective evaluation.

## Research implications

[OpenFPL](https://arxiv.org/abs/2508.09992) supports prospective testing, position-specific ensembles, public FPL/Understat data and forecasts over one, two and three gameweeks. Position-specific candidates lost on our data; multiweek forecasting still fits the transfer decision horizon.

Research on [prediction and integer optimization](https://arxiv.org/abs/2505.02170) motivates measuring decision quality separately from prediction error and including uncertainty in squad selection. The app enforces FPL rules, while robust scenario optimization remains future work. Scikit-learn documents [quantile models and prediction intervals](https://scikit-learn.org/stable/auto_examples/ensemble/plot_hgbt_regression.html).

The source repository warns that historical `xP` can contain post-match information. It is excluded from model features.

Official documentation records the increase to [five banked transfers in 2024–25](https://www.premierleague.com/en/news/4059225) and the [AFCON replenishment after GW15 in 2025–26](https://www.premierleague.com/en/news/4461660). Both historical rules are encoded; applying a universal five-transfer limit would invalidate the 2023–24 simulation.

## Implementation and next steps

- Reproducible prediction benchmark: `src/nextgen_models.py`.
- Exact budget and squad-selection benchmark: `src/decision_backtest.py`.
- Chronological quantile benchmark: `src/uncertainty_models.py`.
- Profile benchmark: `src/risk_profiles.py`.
- Sequential transfer and automatic-substitution simulator: `src/season_simulator.py`.
- Globally optimal initial two-transfer proposals over 1–3 GW in the decision app.
- Production refit with decision checks: `src/production_models.py`.
- Traceable prediction and decision promotion checks.
- Live model selection restricted to refitted production artifacts.
- Forecasts from the same timestamped snapshot and modelled P(60+ minutes).
- Reuse of raw snapshots when changing models, avoiding 659 new API calls.
- Automatic scoring of frozen predictions when actual results become available.

Collect prospective deadline predictions first. Then extend the sequential simulator to rolling multiweek optimization and calibrate expected minutes and availability against those snapshots.
