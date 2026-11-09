"""P5: plan A/B against holding, your own playing-time assumptions, the tipping point
and robustness across scenarios.

* ``apply_overrides``: "What if he is benched?" A user's chance of playing for a
  player replaces FPL's availability in every optimiser call that carries it.
  Overrides live only in the request (and the browser); they are never stored
  server-side or used for training.
* ``compare_plans``: holding (no transfers), plan A (the solver's best) and plan
  B (the best plan that does not make A's first-week signing) on the same
  horizon, with net expected points, hits, bank and free transfers.
* ``breakpoint``: the chance of playing for one player at which plan A's
  first-week action changes (bisection).
* ``robustness``: each candidate keeps its own first-week action and later plan;
  all are scored on the same sampled scenarios (fixed seed, returned). "Chosen in
  X % of scenarios" depends on how the scenarios are drawn; it is not a chance of
  winning.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from fpl_app import AppError, ImportedTeam, _lineup_total_records, apply_risk_profile
from fpl_rules import HIT_COST
from multiweek_planner import plan_multiweek
from point_distribution import fixture_samples

SCENARIOS = 50
SEED = 20261108


def _override_frame(frame: pd.DataFrame | None, chance: dict[int, float], profile: str) -> pd.DataFrame | None:
    if frame is None or "prediction" not in frame or "availability" not in frame:
        return frame
    result = frame.copy()
    mask = result.id.isin(chance)
    if not mask.any():
        return result
    new = result.loc[mask, "id"].map(chance).astype(float)
    old = result.loc[mask, "availability"].astype(float)
    ratio = np.where(old > 0, new / old.where(old > 0, 1), 0.0)
    result.loc[mask, "availability"] = new.to_numpy()
    result.loc[mask, "recommended_points"] = (result.loc[mask, "prediction"].astype(float) * new).to_numpy()
    for column in ("recommended_q10", "recommended_q50", "recommended_q90"):
        if column in result:  # ponytail: quantiles scaled, not re-mixed; fine for a what-if
            result.loc[mask, column] = result.loc[mask, column].astype(float).to_numpy() * ratio
    return apply_risk_profile(result, profile) if "recommended_q10" in result or profile == "balanced" else result


def apply_overrides(team: ImportedTeam, overrides: list[dict]) -> ImportedTeam:
    """Replace FPL's availability by the user's chance of playing (0–1) for the named players."""
    if not overrides:
        return team
    known = set(team.market.id.astype(int))
    chance = {int(o["player_id"]): float(o["chance"]) for o in overrides}
    if set(chance) - known or any(not 0 <= c <= 1 for c in chance.values()):
        raise AppError("An assumption names an unknown player or a chance outside 0–100 %.")
    profile = team.risk_profile
    weekly = _override_frame(team.weekly_market, chance, profile)
    market = _override_frame(team.market, chance, profile)
    if weekly is not None and team.horizon > 1:  # horizon totals follow the weekly rows
        sums = weekly[weekly.id.isin(chance)].groupby("id").recommended_points.sum()
        market.loc[market.id.isin(sums.index), "recommended_points"] = market.id.map(sums)
        if profile == "balanced":
            market["decision_points"] = market["recommended_points"]
    squad = team.squad.drop(columns=[c for c in ("recommended_points", "decision_points", "availability") if c in team.squad]) \
        .merge(market[["id", "recommended_points", "decision_points", "availability"]], on="id", how="left")
    lineup = _override_frame(team.lineup_squad, chance, profile)
    return replace(team, market=market, weekly_market=weekly, squad=squad, lineup_squad=lineup,
                   scenario_overrides={str(k): v for k, v in sorted(chance.items())})


def _summary(name: str, plan: dict, hold_points: float | None) -> dict:
    first = plan["weeks"][0]
    hits = sum(w["hit"] for w in plan["weeks"])
    return {"name": name, "first_week_out": first["transfers_out"], "first_week_in": first["transfers_in"],
            "net_points": plan["total_projected_points"], "hits": hits, "final_bank": plan["weeks"][-1]["bank"],
            "free_transfers_after": plan["free_transfers_after_horizon"],
            "gain_vs_hold": None if hold_points is None else round(plan["total_projected_points"] - hold_points, 2),
            "global_optimum": plan["global_optimum"], "weeks": plan["weeks"]}


def compare_plans(team: ImportedTeam, weeks: int | None = None) -> list[dict]:
    """Hold, plan A and plan B on the same horizon and inputs."""
    weeks = weeks or team.horizon
    hold = plan_multiweek(team, weeks=weeks, max_weekly_transfers=0)
    best = plan_multiweek(team, weeks=weeks)
    plans = [_summary("Hold", hold, None)]
    plans[0]["gain_vs_hold"] = 0.0
    plans.append(_summary("Plan A", best, hold["total_projected_points"]))
    signings = set(best["weeks"][0]["transfers_in_ids"])
    if signings:
        other = replace(team, excluded_ids=set(team.excluded_ids) | signings)
        try:
            plans.append(_summary("Plan B", plan_multiweek(other, weeks=weeks), hold["total_projected_points"]))
        except AppError:
            pass  # no legal alternative without those signings
    return plans


def _first_action(team: ImportedTeam, weeks: int) -> tuple:
    first = plan_multiweek(team, weeks=weeks)["weeks"][0]
    return tuple(sorted(first["transfers_out_ids"])), tuple(sorted(first["transfers_in_ids"]))


def breakpoint(team: ImportedTeam, player_id: int, weeks: int | None = None, steps: int = 6) -> dict:
    """The chance of playing (for one player) at which plan A's first-week action flips."""
    weeks = weeks or team.horizon
    rows = team.market[team.market.id.eq(player_id)]
    if rows.empty:
        raise AppError("Player not found in the current market.")
    name, current = str(rows.name.iloc[0]), float(rows.availability.iloc[0])
    action = lambda chance: _first_action(apply_overrides(team, [{"player_id": player_id, "chance": chance}]), weeks)
    high, low = action(1.0), action(0.0)
    if high == low:
        return {"player_id": player_id, "name": name, "current_chance": current, "threshold": None,
                "message": f"The first-week action does not depend on {name}'s chance of playing (0–100 %)."}
    lo, hi = 0.0, 1.0
    for _ in range(steps):  # bisection; each step is one plan
        mid = (lo + hi) / 2
        if action(mid) == high:
            hi = mid
        else:
            lo = mid
    names = team.market.set_index("id").name.to_dict()
    readable = lambda a: "hold" if not a[0] else f"sell {', '.join(names[i] for i in a[0])} for {', '.join(names[i] for i in a[1])}"
    return {"player_id": player_id, "name": name, "current_chance": current, "threshold": round(hi, 3),
            "above": readable(high), "below": readable(low),
            "message": f"The plan changes from '{readable(high)}' to '{readable(low)}' if {name}'s chance of playing "
                       f"falls below {hi:.0%} (now {current:.0%}).", "precision": round(hi - lo, 3)}


def robustness(team: ImportedTeam, plans: list[dict], scenarios: int = SCENARIOS, seed: int = SEED) -> dict:
    """Share of sampled scenarios in which each candidate plan scores most (each keeps its own moves)."""
    weekly = team.weekly_market
    events = [w["event"] for w in plans[0]["weeks"]]
    owned = {pid for plan in plans for week in plan["weeks"] for pid in week["squad_ids"]}
    rows = weekly[weekly.forecast_event.isin(events) & weekly.id.isin(owned)] \
        .drop_duplicates(["id", "forecast_event"]).reset_index(drop=True)
    columns = ["recommended_q10", "recommended_q50", "recommended_q90"]
    for column in columns:  # a player without quantiles counts at his expectation in every scenario
        rows[column] = rows[column].fillna(rows.recommended_points) if column in rows else rows.recommended_points
    draws = fixture_samples(*(rows[c].to_numpy(float) for c in columns), draws=scenarios, seed=seed)
    position = rows.position.to_numpy()
    index = {(int(i), int(e)): k for k, (i, e) in enumerate(zip(rows.id, rows.forecast_event))}
    totals = np.zeros((len(plans), scenarios))
    for p, plan in enumerate(plans):
        for week in plan["weeks"]:
            keys = [index.get((pid, week["event"])) for pid in week["squad_ids"]]
            for s in range(scenarios):
                records = [(pid, position[k], draws[k, s]) for pid, k in zip(week["squad_ids"], keys) if k is not None]
                totals[p, s] += _lineup_total_records(records) - HIT_COST * week["paid_transfers"]
    winners = totals.argmax(axis=0)
    return {"scenarios": scenarios, "seed": seed,
            "chosen_share": {plan["name"]: round(float((winners == p).mean()), 3) for p, plan in enumerate(plans)},
            "mean_points": {plan["name"]: round(float(totals[p].mean()), 2) for p, plan in enumerate(plans)},
            "note": "Share of sampled scenarios (each player's points drawn from his Q10–Q90 distribution) in which "
                    "each plan scores most. It depends on how scenarios are drawn; it is not a chance of winning."}
