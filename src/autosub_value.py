"""P3: what the bench and vice-captain add once players can miss the round.

The XI forecast counts the eleven starters and the captain twice. In FPL a
starter who does not play is replaced by the first legal bench player, and the
vice-captain doubles if the captain does not play. Here each player plays with
his forecast probability of an appearance and, when he plays, scores his
expected points divided by that probability (so his expectation is unchanged).
Every draw is scored with the rule engine the backtests use
(``season_simulator.autosub_score``). The seed is fixed.

ponytail: players miss independently (no shared team news); 300 draws give about
±0.1 point of Monte Carlo error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from season_simulator import autosub_score

DRAWS = 300
SEED = 20261108


def play_probability(players: pd.DataFrame) -> np.ndarray:
    """P(at least one appearance) from the forecast, times FPL availability; 1 when unknown."""
    appear = pd.to_numeric(players.get("expected_appearances"), errors="coerce") if "expected_appearances" in players \
        else pd.Series(np.nan, index=players.index)
    availability = pd.to_numeric(players.get("availability"), errors="coerce").fillna(1.0) \
        if "availability" in players else pd.Series(1.0, index=players.index)
    blank = pd.to_numeric(players.get("planned_fixtures"), errors="coerce").fillna(1).eq(0) \
        if "planned_fixtures" in players else pd.Series(False, index=players.index)
    p = (appear.clip(upper=1).fillna(1.0) * availability).clip(0, 1)
    return np.where(blank, 0.0, p.to_numpy(float))


def lineup_value(lineup: dict, points: str = "recommended_points", draws: int = DRAWS, seed: int = SEED) -> dict:
    """XI forecast versus expectation with autosubs and vice-captain, for an ``optimal_lineup`` result."""
    starters, bench = lineup["starters"].copy(), lineup["bench"].copy()
    xi = float(starters[points].sum() + starters.loc[starters.role.eq("C"), points].sum())
    players = pd.concat([starters, bench], ignore_index=True)
    p = play_probability(players)
    expected = players[points].to_numpy(float)
    if_playing = np.divide(expected, p, out=np.zeros_like(expected), where=p > 0)
    rng = np.random.default_rng(seed)
    plays = rng.random((draws, len(players))) < p
    total = 0.0
    for row in plays:
        players["minutes"] = np.where(row, 90, 0)
        players["actual_points"] = np.where(row, if_playing, 0.0)
        draw = {"starters": players.iloc[:len(starters)], "bench": players.iloc[len(starters):]}
        total += autosub_score(draw)[0]
    with_subs = total / draws
    return {"xi_expected": round(xi, 2), "expected_with_autosubs": round(with_subs, 2),
            "bench_and_vice_value": round(with_subs - xi, 2), "draws": draws,
            "note": "Bench and vice-captain value when starters can miss the round; "
                    "Monte Carlo with the backtests' autosub rules."}
