# Research: improving the app as an FPL manager

Updated 18 September 2026. Player prediction, decision optimization and the weekly workflow need separate evaluation. Low RMSE alone does not establish good FPL management.

## Priorities

Optimize decisions over time: compare rolling, transferring and taking hits; replan across multiple gameweeks; account for uncertain minutes and injuries; explain captain margins; show official price alerts; compare chips against alternatives and their future value; and provide a prioritized deadline checklist.

The implemented strategy centre covers transfer banking, multiweek plans, captain margins, price alerts and deadline checks, with partial support for uncertainty and chip comparisons.

## Research and implications

### Patience and banked transfers

2025/26 winner Erik Ibsen took no hits, made no transfers in 15 of 38 gameweeks and banked transfers for coordinated changes. This supports requiring clear margins before recommending hits, without proving that hits are always wrong. [Champion interview](https://www.premierleague.com/en/news/4671784).

Rolling must be a genuine optimization alternative. The strategy centre compares a hit plan against a no-hit plan and requires 2.0 additional model points per paid transfer after subtracting the four-point hit. Flexibility matters around injuries, fixture changes and premium-player moves.

### Multiweek planning

The winner planned premium changes in gameweek blocks. Research on around a million managers associates stronger performance with planning and consistent decisions; OpenFPL evaluates prospective forecasts over one to three rounds. Sources: [skill study](https://arxiv.org/abs/2009.01206), [OpenFPL](https://arxiv.org/abs/2508.09992), [champion transfer strategy](https://www.premierleague.com/en/news/4671982/fpl-champion-how-to-build-the-perfect-squad-and-make-the-best-transfers).

Use a practical three-to-five-GW horizon, discount later weeks and recalculate after deadlines, injuries, price changes and fixture changes. Show scenario stability rather than treating a deterministic plan as certain.

### Bench flexibility and its cost

Ibsen prioritized 15 playable players and used six formations, but also benched many points. Measure playable coverage, expected bench points and whether the first substitute can cover an uncertain starter. Wildcard bench strength should reflect possible Bench Boost use. Otherwise, compare money tied up on the bench with the improvement it could buy in the starting XI.

### Captain points and rank risk

The winner captained Haaland in 22 of 38 rounds while using differentials elsewhere. Effective ownership explains the rank exposure of opposing a popular captain. Sources: [captain and chip strategy](https://www.premierleague.com/ar/news/4672128/fpl-champion-how-to-pick-your-captain-and-maximise-your-chips), [FPL glossary](https://www.premierleague.com/en/news/2683145), [GW5 captain analysis](https://www.premierleague.com/en/news/4720208).

Show the top three options and their margins. Expected points remains the default objective; ownership describes risk and must not inflate predictions. Future rank objectives should use explicit user choices to chase or protect a position, with remaining gameweeks and rival data.

### Price changes

Team value can be useful early, but chasing £0.1m can cost points through injury or rotation risk. The 2026/27 official Price Change Predictor indicates threshold progress; values above 100% do not guarantee a price change. Sources: [official predictor](https://www.premierleague.com/en/news/4680462), [champion transfer strategy](https://www.premierleague.com/en/news/4671982/fpl-champion-how-to-build-the-perfect-squad-and-make-the-best-transfers), [skill study](https://arxiv.org/abs/2009.01206).

Use `price_change_percent`, projected changes and transfer flow from the FPL snapshot. Flag owned players approaching falls and relevant targets approaching rises. Account for purchase and selling prices, and balance early moves against midweek fixtures, uncertain minutes and pending news.

### Chips and option value

In 2026/27, each season half has Wildcard, Free Hit, Triple Captain and Bench Boost. First-half chips expire at the GW19 deadline. Blank and double gameweeks offer opportunities, but strong single-gameweek opportunities also matter. Experts' GW6 Wildcard/GW7 Bench Boost plans were not unanimous on 18 September. Evaluate the user's squad rather than copying one calendar. Sources: [chip rules](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627), [chip opportunities](https://www.premierleague.com/en/news/4362085), [expert plans](https://www.premierleague.com/en/news/4685105).

Chip gain is the best chip plan minus the best legal normal plan. Wildcard evaluation spans multiple rounds and future transfers. Bench Boost evaluates four actual substitutes, minutes and budget cost. Triple Captain needs both upside and minutes confidence. Free Hit depends on the permanent squad's actual blanks and weak fixtures.

### Deadline information

The deadline is 90 minutes before the first match. Press conferences, injury flags, midweek workload and expected lineups can change minutes more than small prediction differences. [Managing your FPL team](https://www.premierleague.com/en/news/2174899).

Prioritize flagged starters, refresh after relevant press conferences and fixtures, and display timestamps and changes. Expected-lineup feeds need timestamped prospective validation before influencing production predictions.

### Defensive contributions

Defenders earn two points at ten CBIT actions; midfielders and forwards need 12 CBIRT actions. The award is capped at two points per match. Sources: [scoring explanation](https://www.premierleague.com/en/news/4361991), [2026/27 leaders](https://www.premierleague.com/en/news/4713244).

Model the probability of reaching the threshold, using role, opponent and expected match conditions. Explain expected points through minutes, clean sheets, goals, assists, bonus, saves and defensive contributions.

## Implemented functionality

- React strategy centre with exact multiweek roll-versus-transfer choices.
- Separate no-hit comparison and an uncertainty buffer.
- Prioritized deadline checklist and squad health: playable players, flagged starters, bench coverage and club concentration.
- Captain margins, vice-captain and three alternatives.
- Official price indicators for owned fall candidates and relevant targets.
- Watchlists for highest predictions, under-10% ownership and points per £m.
- Known blanks/doubles, total points, overall rank and squad value.

## Next priorities

1. Scenario optimization across minutes, injuries and fixture outcomes, showing which transfers remain useful.
2. Consistent expected-point decomposition.
3. Optional authenticated state for authoritative cash, free transfers and purchase prices, without executing transfers.
4. Expected lineups and material news changes since the last snapshot.
5. Explicit probabilistic blank/double scenarios from cup and European schedules.
6. User-selected mini-league and rank objectives.
7. Pre-deadline advice, user-choice and outcome logs.
8. Opt-in local, email or push alerts with materiality thresholds.

Later work includes live automatic substitutions, bonus and defensive contributions; mini-league simulations; player locks/exclusions; planned-transfer calendars with replanning; and risk preferences based on explicit choices rather than short-term results.

## Data-source roles

| Source | Use | Limitation |
|---|---|---|
| Public FPL API | Prices, ownership, status, defensive contributions, set pieces and price indicators | Free transfers are not authoritative without authentication |
| Pre-deadline FPL snapshots | Prospective training and evaluation | Evidence must establish availability before the deadline |
| Betting markets | Team goals, clean sheets, goals and assists | Remove bookmaker margin and check coverage |
| Understat/OpenFPL-style data | xG/xA, shots and player form | Handle role and league changes cautiously |
| Expected lineups | Starting and minutes probabilities | Provider-dependent; needs validation |
| Official team news | Injuries, suspensions and coach statements | Structure text without overstating certainty |
| Cup/UEFA schedules | Blank/double scenarios and workload | Future schedules may be probabilistic |

Avoid treating three or four matches as stable skill, adding ownership to expected points, buying players solely for low ownership, chasing prices while ignoring risk, assuming any double-gameweek player beats a strong single-gameweek player, or promoting plausible features without prospective baseline comparisons. Claim global optimality only when the solver proves it.

## Evaluation

Measure net transfer points against holding, hit gains and losses, banked-transfer value, captain regret against feasible pre-deadline choices, chip gain against normal plans, price changes that block plans, recommendation stability 24/6/1 hours before the deadline, and calibration of minutes, clean sheets, goals, assists and defensive contributions.

Evaluate a full season using only information available at each deadline. The key test is a locked prospective shadow season: record recommendations before deadlines and preserve them after results arrive.
