# Product research: next features for FPL Model

Updated 19 September 2026.

## Direction

The app already supports team import, forecasts, squad selection, transfer optimization, multiweek plans, chips, Free Hit/Wildcard squads, price alerts, manager history, mini-leagues and effective ownership. The next step is a decision workbench:

1. Explain expected points per player and fixture.
2. Compare players and holding versus transferring.
3. Let users lock, exclude and plan specific players or moves.
4. Test recommendations against uncertain minutes and model changes.
5. Show material changes since the previous refresh.

These features offer more strategic value than duplicating a full live-score service. Official FPL already provides live leagues, projected bonus, squad views and its price predictor.

## Method and user needs

The review combines official 2026/27 changes, FPL Review/LiveFPL/Fantasy Football Scout features, qualitative Reddit feedback and a code audit. Community comments are not a representative survey, and competitor features are not proof of better outcomes. New features need prospective measurement.

Before deadlines, users need to decide whether to roll, whether a hit is worth four points, who starts and takes C/VC, whether recent news changes the plan, and what today's choice means for later rounds. Community requests emphasize captain/hit decisions, future fixtures on the pitch and expected starting lineups.

Experienced users also need controls: keep a player, exclude a club, change an assumed starting probability, buy someone by GW8, or compare the best plan without a player and its opportunity cost. FPL Review demonstrates editable minutes, locks/exclusions, planned moves and alternative solves.

Live rank, effective ownership, bonus, defensive contributions and mini-league swings remain useful later. Existing app history and official/LiveFPL coverage reduce their immediate priority.

## Current gaps

| Need | Current status | Main gap |
|---|---|---|
| Import and squad correction | Good | No critical gap |
| XI, bench and C/VC | Good | Probabilistic automatic substitutions and vice-captain value |
| Transfers | Good | Forced moves, comparisons and robustness |
| Multiweek plans | Good | Interactive editing, saved drafts and scenarios |
| Chips, Free Hit and Wildcard | Good | Robustness and point decomposition |
| Mini-leagues, EO and rank risk | Good | Probabilistic league simulation |
| Price alerts | Partial | Notifications and the cost of waiting |
| Injuries and minutes | Partial | User assumptions and clear news changes |
| Prediction explanation | Weak | Components are not displayed consistently |
| Player comparison | Missing | Side-by-side and hold-versus-buy comparisons |
| Robustness | Missing | Q10/Q90 exist, but decisions are not stress-tested |
| Accuracy | Internal only | User-facing calibration and accuracy |
| Changes since refresh | Missing | Snapshots are not presented as material differences |
| Live matchday | Missing | Useful, but lower immediate differentiation |

## Prioritized backlog

Value and data readiness use a 1–5 scale. Effort is S/M/L/XL.

| Priority | Feature | Value | Data readiness | Effort | Purpose |
|---|---|---:|---:|---|---|
| P0 | Explanation and player comparison | 5 | 4 | M | Make recommendations understandable |
| P0 | Locks, exclusions and forced future moves | 5 | 5 | M | Make solves fit real plans |
| P0 | Sensitivity and robustness | 5 | 4 | L | Separate stable choices from marginal ones |
| P0 | Deadline changes | 5 | 4 | M | Direct attention to material information |
| P0 | Minutes and starting-probability overrides | 5 | 3 | M | Expose the largest uncertainty |
| P1 | Probabilistic automatic substitutions and VC | 4 | 4 | L | Value bench coverage correctly |
| P1 | Fixture grid and rotation pairs | 4 | 5 | M | Compare upcoming schedules |
| P1 | Saved drafts and plan comparison | 4 | 5 | M | Preserve alternative ideas |
| P1 | Decision log and shadow season | 4 | 5 | M | Evaluate advice available at deadlines |
| P1 | Accuracy and calibration dashboard | 4 | 4 | M | Identify component errors |
| P1 | Probabilistic blank/double scenarios | 4 | 2 | L | Support chips under schedule uncertainty |
| P2 | Local/push/email alerts | 3 | 3 | L | Notify users of material changes |
| P2 | Live rank, bonus, DC and event impact | 3 | 4 | L | Add matchday context |
| P2 | Mini-league Monte Carlo | 3 | 3 | L | Support late-season objectives |
| Not now | Generic AI chat and summaries | 2 | 2 | L | Limited direct decision value |

## P0 specifications

### Player explanation and comparison

Clicking a player opens expected minutes, starting and 60+ probabilities, goal/assist/clean-sheet/save/bonus/DC components, per-gameweek and horizon points, market versus model estimates, Q10/median/Q90, source timestamps and role/form trends.

Comparison includes price and selling price, xPts over 1/3/5 gameweeks, minutes uncertainty, fixtures, point sources, ownership/EO, price direction and holding A versus A → B with free-transfer use, hits and future plans.

Acceptance: components come from the same points engine and sum to the displayed expectation within rounding. Comparisons display the net plan difference after hits.

### Interactive solver

Add controls to multiweek, Free Hit and Wildcard plans: lock owned players, exclude players/clubs, require arrivals or departures by a gameweek, force future moves, cap goalkeeper spending or defensive club exposure, request three-to-five legal alternatives within two points of the optimum, and save named local drafts.

Display opportunity cost, such as “This constraint costs 1.3 expected points over four gameweeks.” Enforce constraints throughout the horizon and distinguish the unconstrained optimum from the user's constrained plan.

### Robustness and sensitivity

Run 20–100 solves varying plausible minutes, rotation, attack/defence strength, point components, future discounting and free-transfer value. Report initial-transfer frequency, Free Hit/Wildcard inclusion frequency, median/P10/P90 gain against holding, robust/close/fragile labels and assumptions that reverse a decision.

Example: “Konsa is retained in 78% of scenarios. Selling becomes preferable if starting probability falls below 62%.” Store the random seed for reproducibility, use at least 20 scenarios and avoid calling a 51% result certain.

### Material changes before deadlines

Compare timestamped snapshots for injury flags, minutes/starting probability, moved fixtures, blanks/doubles, material goal/clean-sheet odds movement, price thresholds, penalty/set-piece roles and changed XI/C/VC/transfer/chip advice. Prediction changes can use a threshold such as 0.5 points.

Show “Since last time” with before/after values, timestamp, source and recommendation impact. Raw odds or ownership noise should not create alerts.

### User assumptions about minutes

Allow temporary overrides for starting probability, minutes if starting, cameo probability, availability and set-piece roles. Recalculate forecasts and plans, label them “Your assumptions”, and provide reset. Timestamp overrides and keep them separate from training truth.

Expected-lineup feeds should remain separate source signals until prospective validation justifies production weight.

## P1 specifications

Probabilistic automatic substitutions should model missing starters, legal formations, bench order and vice-captain activation. Display raw XI xPts and total expectation including substitutions.

A 3–10-GW fixture grid should show opponents, home/away, player xPts, team goals, clean-sheet probability and blanks/doubles. Let users step through gameweeks on the pitch and compare two- or three-player budget rotations.

Saved local drafts should compare Plan A/B, Wildcard now/GW8, total xPts, hits, free transfers used/banked, cash, uncertainty and differing players.

Freeze predictions, components, recommendations, alternatives, user choices and source timestamps before each deadline. Afterwards evaluate P(start), P(60+), clean sheets, goals, assists, DC thresholds and interval coverage. Separate single-match randomness from systematic error.

## Data feasibility

| Feature | Existing data support | Additional work |
|---|---|---|
| Player comparison | Mostly | Consistent per-GW point decomposition |
| Locks/exclusions/forced moves | Yes | Solver constraints and API contracts |
| Sensitivity | Yes | Simulation, seeds and progress reporting |
| Snapshot changes | Yes | Normalization and materiality thresholds |
| Minutes overrides | Partial | Per-GW components and local override storage |
| Predicted lineups | No | Licensed feed, manual input or validated source |
| Automatic substitutions | Partial | Joint starting/cameo scenarios |
| Fixture scenarios | Partial | Cup/TV probabilities and scenario format |
| Push alerts | No | Background jobs and chosen channel; local alerts first |
| Live matchday | Public feed | Polling, caching and score corrections |

Odds remain market signals rather than truth. Lineups and news interpretation require timestamps and validation against actual starters.

## Delivery and measurement

Phase A: point decomposition, player panel, comparisons, sources and uncertainty. Phase B: constraints, future moves, alternatives, opportunity cost and drafts. Phase C: sensitivity, robust inclusion rates, material changes and minutes overrides. Phase D: automatic substitutions, fixture rotations, schedule scenarios and a prospective lineup pilot. Phase E: decision logs, accuracy/calibration, thresholded alerts and limited matchday support if needed.

Measure explanation and constraint usage, choices retained in at least 70% of scenarios, expected net gain and actual decision regret, component calibration, material-change detection, opened/ignored alerts, time from loading a team to an understood decision, and prospective shadow-season performance.

## Sources

- [Official FPL features](https://www.premierleague.com/en/news/4679873).
- [Defensive contributions](https://www.premierleague.com/en/news/4361991).
- [FPL Review overview](https://docs.fplreview.com/getting-started/about-fplreview/).
- [Sensitivity analysis](https://docs.fplreview.com/the-model/solvers/sensitivity-analysis/).
- [Forced decisions](https://docs.fplreview.com/the-model/solvers/forced-decisions/).
- [Expected minutes](https://docs.fplreview.com/the-model/projections/xmins/).
- [Evaluation and automatic substitutions](https://docs.fplreview.com/the-model/solvers/evaluation-score/).
- [LiveFPL](https://www.livefpl.com/).
- [Fantasy Football Scout comparison tool](https://www.fantasyfootballscout.co.uk/how-to-use-the-comparison-tool-in-the-members-area).
- [OpenFPL](https://arxiv.org/abs/2508.09992).
- [Community requests for fixtures and future gameweeks](https://www.reddit.com/r/FantasyPL/comments/16mn1o2/featuresimprovements_to_fpl/).
- [Community discussion of expected lineups](https://www.reddit.com/r/FantasyPL/comments/1mdz513/where_does_everyone_get_their_info_on_predicted/).
- [Community feedback on captain and hit decisions](https://www.reddit.com/r/fplAnalytics/comments/1teqgok/built_an_ios_app_for_fpl_fans_because_i_got_tired/).
