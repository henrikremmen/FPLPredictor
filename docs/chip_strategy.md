# Chip strategy: rules, method and limitations

## Rules enforced by the engine

The documented 2026/27 rules provide two sets of Wildcard, Free Hit, Triple
Captain and Bench Boost, one per season half. The first expires before the GW19
deadline. Only one chip can be played per Gameweek. Free Hit cannot be used in
GW1 or in consecutive Gameweeks.
Source: [Premier League chip rules](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627).

Strategy guides suggest Bench Boost and Triple Captain for suitable double
Gameweeks, Free Hit for major blank/double rounds, and Wildcard for sustained
improvement, potentially followed by Bench Boost. These are heuristics, not
absolute rules. Sources:
[expert plans](https://www.premierleague.com/en/news/4685105) and
[a winner's chip sequence](https://www.premierleague.com/en/news/4672128).

## Calculating points value

Each scenario is compared with a normal plan using the team's estimated free
transfers. A MILP selects a legal 15-player squad, starting XI and captain:

- 2 goalkeepers, 5 defenders, 5 midfielders and 3 forwards.
- Legal formation and no more than three players per club.
- Current bank and individual estimated selling prices.
- One captain selected from the starting XI.

Chip gain is measured against the normal plan:

- **Triple Captain:** one additional copy of the captain's expected points.
- **Bench Boost:** points from the four bench players.
- **Free Hit:** best single-gameweek squad minus the best normal plan.
- **Wildcard:** best permanent squad minus the normal plan over the full window.
- **Wildcard → Bench Boost:** jointly optimised squad for Wildcard now and Bench
  Boost in the following Gameweek.

Conservative thresholds stop small, uncertain gains being labelled **Play**.
The threshold decreases near chip expiry. **Play**, **Consider** and **Hold**
are decision support, not probabilities.

## Horizon limitations

The original chip analysis used a short three-Gameweek window. A finite forecast
cannot establish season-optimal timing: future blanks/doubles, cup results,
injuries and team news remain uncertain. A full-season policy needs scenarios,
explicit uncertainty and a value for waiting. Relevant research includes
[mathematical optimisation for FPL](https://arxiv.org/abs/2505.02170) and
[OpenFPL](https://arxiv.org/abs/2508.09992).

Next steps are genuine deadline forecasts, half-season blank/double scenarios
and prospective calibration of chip thresholds without using outcomes as inputs.
