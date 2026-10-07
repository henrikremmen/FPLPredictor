# Model review, odds and squad recommendations (September 2026)

## Main finding

The biggest weakness is expected minutes and information that changes close to
the deadline. The points model reacts too slowly to a new role. Odds, expected
lineups and injury/rotation information need timestamps and validation before
being used as model inputs.

Team form already appears in season rates and five-match features. Previously,
recent context was asymmetric: goals scored for the team and goals conceded for
the opponent. The snapshot builder now records goals scored, conceded, points
and match counts over the last five games for both sides.

## The Konsa diagnosis

The pre-GW5 snapshot gave Ezri Konsa 2.0649 points. In that snapshot he was an
Arsenal player with a minutes history of 0, 11, 90 and 90. The minutes model
assigned only 67.39% probability to 60+ minutes, explaining much of the low
forecast. The component model predicted 2.3257 points and only a 14.84%
clean-sheet chance against Brighton because Brighton's early scoring rate was
very high. FPL's `ep_next` was 2.8.

A five-game window reacts slowly to two new starts, while four league matches
produce extreme team rates. Recent form needs shrinkage towards a longer prior
or an odds-market anchor. Shorter role-history features improved 2025/26 but
worsened average chronological validation performance, so they were not promoted.

| Variant | Validation RMSE | Candidate RMSE | 2025/26 RMSE | 2025/26 P(60+) Brier |
|---|---:|---:|---:|---:|
| Production features | **1.91254** | **3.07456** | 1.93061 | 0.08146 |
| Short role history | 1.91308 | 3.07692 | 1.92863 | **0.08112** |
| Symmetric team form | 1.91320 | 3.07668 | 1.93065 | 0.08146 |
| Both | 1.91313 | 3.07663 | **1.92853** | 0.08112 |

## Odds coverage

[The Odds API](https://the-odds-api.com/sports/epl-odds.html) supplies match-result
and total-goals markets through its league endpoint. Event endpoints also offer
`player_goal_scorer_anytime` and `player_assists`, currently mainly through US
bookmakers. Direct clean-sheet odds are not a standard market in this source.
The implementation removes bookmaker margin and fits two Poisson goal rates
to 1X2 and over/under 2.5, deriving team goals and clean-sheet probabilities from
the same match distribution.

Enable `ODDS_PLAYER_PROPS=1` with `ODDS_API_KEY` to capture player props. These
calls use more API credits. Historical odds, including props, require a paid
plan. Until timestamped history exists, props are stored for research rather
than used to overwrite production points.

## Priorities

1. **Expected minutes and XI.** Collect prospective lineup estimates, injuries
   and starting candidates before deadlines. Sportmonks offers an
   [Expected Lineups API](https://www.sportmonks.com/football-api/expected-lineups-api/),
   but it is a costly addition. Evaluate actual 60+ outcomes and information timing.
2. **Market components.** Backtest de-vigged clean-sheet, team-goal, scorer and
   assist probabilities with log loss, Brier score and FPL points. Use a validated
   component or blend, not an arbitrary uplift.
3. **Component model.** Separately model minutes, goals, assists, clean sheets,
   saves, bonus and defensive contributions. It gained 12 points over 66
   validation rounds, but the interval included zero. Continue prospective tests
   under current defensive-contribution rules before promotion.
4. **Bayesian team form.** Shrink three/five-match goal and xG rates towards
   home/away priors. Market or FPL team strength should matter more early in a season.
5. **Workload and set pieces.** Store cup/European/international schedules, rest
   days and penalty/corner order. Sufficient history is required before training.
6. **Decision metrics.** Require improvement in legal squads, XIs and captains,
   not just total RMSE, which is dominated by many zero-minute players.

## Features to challenge

- Test grouped ablations for overlapping points windows and ICT components.
- Compare recent goals/assists with xG/xA; short windows contain finishing noise.
- Ownership, transfer trends and price changes may proxy news, but must come from
  snapshots captured before the deadline.
- Historical FPL `xP` remains excluded because its timing may be post-match.
  Live `ep_next` can be shown as a reference, but needs certified history before training.

Remove features only when a predefined ablation improves calibration and the
decision backtest. Feature importance alone is insufficient.

## Research sources

- [OpenFPL](https://arxiv.org/abs/2508.09992): prospective evaluation,
  position-specific ensembles and separate one-to-three-week predictions.
  Our position-specific candidate was tested and rejected.
- [Dixon and Coles](https://doi.org/10.1111/1467-9876.00065): dynamic Poisson
  football modelling, motivating an explicit match-goal model.
- [Data-driven FPL optimisation](https://arxiv.org/abs/2505.02170): evaluate
  prediction and legal squad optimisation together.
- [Official FPL scoring](https://www.premierleague.com/en/news/2174909): minutes,
  clean sheets, goals, assists, saves and defensive contributions can be modelled
  separately when the data support it.

## Squad recommendations

The **FH / WC squads** page provides a legal 15-player Free Hit squad, XI, bench,
captain and vice-captain for each known Gameweek. Wildcard uses a 0.9 discount
per later round and starts a new exact multiweek plan, including transfers,
captain, bank and hits. This is a rolling plan: current prices and injuries are
held static, so recalculate before each deadline.
