# Transfer flexibility and horizon controls — 16 October 2026

The old Strategy Centre silently capped planning at five weeks and treated
any feasible first-week transfer as a recommendation. It could recommend a
small improvement without comparing it with rolling now and retaining the
ability to make multiple transfers later. The Transfers page solves a
different problem: exactly the selected transfer count now, holding the
resulting squad over the horizon. Its positive gain is not a decision to act.

## Research and decisions

- [Official FPL FAQ](https://www.premierleague.com/en/news/4661030) explains
  free-transfer rollover and substitution rules. An injured reserve does not
  automatically require a transfer; lineup impact and usable cover matter.
- [Open FPL Solver settings](https://github.com/solioanalytics/open-fpl-solver/blob/main/data/comprehensive_settings.json)
  provide an eight-week horizon, 0.9 decay, a 1.5-point FT value, optional
  diminishing FT values, bench weights and forecast randomization. These are
  optimizer settings, not empirical evidence of an optimal FT value.
- Our planner now assigns 1.5 planning-score points per FT retained at the
  horizon's end, discounted to today. Actual projected FPL points remain
  separate. This is an explicit policy assumption.
- Strategy compares its feasible candidate with a separate solve constrained
  to no transfers in the first week, allowing later transfers in both solves.
  Thus rolling can enable two moves next week or further accumulation.
- Acting now must establish a gain of at least two planning-score points per
  bankable FT spent. At five FTs, the first FT would overflow on a roll and
  incurs no such margin. Paid-transfer comparisons retain the existing hit
  guard. The two-point margin is a cautious product policy, not a calibrated
  uncertainty interval or a statistically optimal rule.
- Solver objective bounds are used: a candidate's feasible score must beat
  the roll branch's upper bound by the margin. An inferior roll incumbent
  from an incomplete solve cannot manufacture a confident transfer signal.
- The strategy shows immediate XI/captain gain, the proposed incoming
  starters, displaced starters, bench-only buys and next-week FT counts.

## Team 10867210

Using the 16 October snapshot and the active local squad override, over eight
weeks, Schade to Gomez adds 0.63 next-GW XI/captain points. Gomez displaces
Barry in this run. Its feasible planning-score advantage over rolling is
0.29; the solver-derived lower bound is −0.08. Rolling leaves two FTs next
week, compared with one if transferring now. The recommendation is ROLL.
The full report is `artifacts/planning_20261016/team_10867210_strategy.json`.
These values depend on the snapshot, active holdings, finances and horizon.

## Horizon interaction

`PATCH /api/team/{session_id}/horizon` rebuilds markets from the saved forecast
without downloading/reimporting the public team. It preserves active squad,
purchase/selling prices, bank, FTs, manual overrides, profile and preferences.
It updates the durable session pointer only on success. Missing horizons
leave the prior session intact and request a forecast refresh.

A global selector is available above every page and in the sidebar. A change
retains the current page and automatically recalculates existing strategy
advice. Other retained results are marked outdated. Older in-flight strategy
responses cannot overwrite advice for newer inputs. Strategy honours all
selected one-to-eight weeks; the five-week cap is removed.

## Limits and next research

Future prices and injury flags are still static within each solve. The new
reserve value and caution margin approximate flexibility, not future injury
probabilities. Autosubs and vice-captain fallback are not simulated. Genuine
scenario planning would branch future availability and forecasts, allow
different later actions per branch, and require identical first-week actions
across branches; this needs calibrated transition data and separate backtests.
Bench value should then come from legal autosub scenarios rather than adding
all bench points or giving an injured reserve automatic priority.

Validation: 152 backend tests passed, frontend production build passed, and
seven workspace browser tests passed, including changing horizon on Strategy
Centre, preserving constraints, recalculating, and retaining the previous
horizon/advice on failure. A live local horizon change for this team retained
holdings, finances and selling prices.
