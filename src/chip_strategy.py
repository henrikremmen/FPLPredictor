"""Short-horizon, rule-aware FPL chip valuation.

The module measures each chip against the same expected-points forecast and
constraints. It deliberately labels the result as short-horizon guidance: a
three-Gameweek forecast cannot prove globally optimal chip timing for a half
season whose future blanks and doubles are not yet scheduled.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, vstack

from fpl_app import AppError, ImportedTeam, optimal_lineup


CHIP_LABELS = {
    "triple_captain": "Triple Captain",
    "bench_boost": "Bench Boost",
    "free_hit": "Free Hit",
    "wildcard": "Wildcard",
    "wildcard_bench_boost": "Wildcard → Bench Boost",
}
POSITION_COUNTS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
START_LIMITS = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}


@dataclass
class WindowSolution:
    squad_ids: set[int]
    total_points: float
    points_by_event: dict[int, float]
    transfers_needed: int
    squad_names: list[str]


def _expected_view(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["decision_points"] = result["recommended_points"].astype(float)
    return result


def _squad_event_score(frame: pd.DataFrame, squad_ids: set[int],
                       chip: str | None = None) -> dict:
    squad = _expected_view(frame[frame["id"].isin(squad_ids)])
    if len(squad) != 15:
        raise AppError(f"Chipberegningen fant {len(squad)} av 15 spillere.")
    lineup = optimal_lineup(squad)
    captain = lineup["starters"].query("role == 'C'").iloc[0]
    captain_points = float(captain["recommended_points"])
    base = float(lineup["expected_total"])
    bench_points = float(lineup["bench"]["recommended_points"].sum())
    if chip == "triple_captain":
        score = base + captain_points
    elif chip == "bench_boost":
        score = base + bench_points
    else:
        score = base
    return {
        "score": score, "base": base, "captain_points": captain_points,
        "captain": str(captain["name"]), "bench_points": bench_points,
        "bench": lineup["bench"]["name"].astype(str).tolist(),
    }


def _optimize_window(team: ImportedTeam, events: list[int],
                     bench_boost_event: int | None = None,
                     triple_captain_event: int | None = None,
                     max_transfers: int | None = None,
                     discount: float = .9) -> WindowSolution:
    """Optimize a sale-value-budget squad, weekly XI and captain over events."""
    weekly = team.weekly_market
    if weekly is None:
        weekly = team.market.assign(forecast_event=team.target_event)
    frame = team.market.sort_values("id").drop_duplicates("id").reset_index(drop=True)
    ids = frame["id"].astype(int).to_numpy()
    owned = set(team.squad["id"].astype(int))
    owned_mask = np.asarray([player_id in owned for player_id in ids], dtype=float)
    n, periods = len(frame), len(events)
    variables = n * (1 + 2 * periods)
    data: list[float] = []
    row_ids: list[int] = []
    columns: list[int] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(entries: list[tuple[int, float]], lo: float = -np.inf,
            hi: float = np.inf) -> None:
        row = len(lower)
        for column, value in entries:
            if value:
                row_ids.append(row)
                columns.append(column)
                data.append(float(value))
        lower.append(float(lo))
        upper.append(float(hi))

    add([(index, 1) for index in range(n)], 15, 15)
    if max_transfers is not None:
        retained = max(0, 15 - int(max_transfers))
        add([(index, owned_mask[index]) for index in range(n)], lo=retained)
    for position, count in POSITION_COUNTS.items():
        add([(index, 1) for index in range(n)
             if frame.loc[index, "position"] == position], count, count)
    for team_id in sorted(frame["team_id"].unique()):
        add([(index, 1) for index in range(n)
             if frame.loc[index, "team_id"] == team_id], hi=3)

    sale = team.squad.set_index("id")["selling_price"].astype(int).to_dict()
    cash = np.asarray([
        sale[player_id] if player_id in owned else int(frame.loc[index, "price"])
        for index, player_id in enumerate(ids)
    ], dtype=float)
    available_cash = float(team.bank + sum(sale.values()))
    add([(index, value) for index, value in enumerate(cash)], hi=available_cash)

    objective = np.zeros(variables)
    score_by_event: dict[int, np.ndarray] = {}
    for period, event in enumerate(events):
        rows = weekly[weekly["forecast_event"].eq(event)].set_index("id")
        scores = rows["recommended_points"].reindex(ids).fillna(0).to_numpy(float)
        score_by_event[event] = scores
        starter = n * (1 + 2 * period)
        captain = starter + n
        add([(starter + index, 1) for index in range(n)], 11, 11)
        for position, (minimum, maximum) in START_LIMITS.items():
            add([(starter + index, 1) for index in range(n)
                 if frame.loc[index, "position"] == position], minimum, maximum)
        add([(captain + index, 1) for index in range(n)], 1, 1)
        for index in range(n):
            add([(index, -1), (starter + index, 1)], hi=0)
            add([(starter + index, -1), (captain + index, 1)], hi=0)
        weight = discount ** period
        if event == bench_boost_event:
            objective[:n] -= weight * scores
        else:
            objective[starter:starter + n] -= weight * scores
        captain_multiplier = 2 if event == triple_captain_event else 1
        objective[captain:captain + n] -= weight * captain_multiplier * scores

    matrix = csr_matrix((data, (row_ids, columns)), shape=(len(lower), variables))
    result = milp(
        objective, integrality=np.ones(variables, dtype=np.uint8),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)),
        options={"time_limit": 20},
    )
    if not result.success or result.x is None:
        raise AppError(f"Chipoptimeringen feilet: {result.message}")

    primary = csr_matrix(objective.reshape(1, -1))
    tie_matrix = vstack([matrix, primary], format="csr")
    tie_lower = np.concatenate([np.asarray(lower), [-np.inf]])
    tie_upper = np.concatenate([np.asarray(upper), [float(result.fun) + 1e-8]])
    tie_objective = np.zeros(variables)
    tie_objective[:n] = cash + 1e-7 * np.where(owned_mask > 0, -ids, ids)
    tie = milp(
        tie_objective, integrality=np.ones(variables, dtype=np.uint8),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(tie_matrix, tie_lower, tie_upper),
        options={"time_limit": 20},
    )
    if tie.success and tie.x is not None:
        result = tie

    selected = set(ids[result.x[:n] > .5].astype(int))
    points_by_event = {}
    for event in events:
        rows = weekly[weekly["forecast_event"].eq(event)]
        chip = ("bench_boost" if event == bench_boost_event else
                "triple_captain" if event == triple_captain_event else None)
        points_by_event[event] = _squad_event_score(rows, selected, chip)["score"]
    names = frame[frame["id"].isin(selected)].sort_values(
        ["position", "recommended_points"], ascending=[True, False]
    )["name"].astype(str).tolist()
    return WindowSolution(
        squad_ids=selected, total_points=float(sum(points_by_event.values())),
        points_by_event=points_by_event,
        transfers_needed=len(owned - selected), squad_names=names,
    )


def _threshold(chip: str, event: int, expiry: int, window: int = 1) -> float:
    bases = {
        "triple_captain": 8.0,
        "bench_boost": 12.0,
        "free_hit": 10.0,
        "wildcard": max(10.0, 4.0 * window),
        "wildcard_bench_boost": max(20.0, 5.0 * window),
    }
    remaining = max(1, expiry - event + 1)
    urgency = max(.55, min(1.0, remaining / 6))
    return round(bases[chip] * urgency, 2)


def _decision(gain: float, threshold: float, available: bool) -> str:
    if not available:
        return "UNAVAILABLE"
    if gain >= threshold:
        return "PLAY"
    if gain >= .7 * threshold:
        return "CONSIDER"
    return "HOLD"


def recommend_chip_strategy(team: ImportedTeam) -> dict:
    """Value all available chips in the frozen forecast window."""
    weekly = team.weekly_market
    if weekly is None:
        weekly = team.market.assign(forecast_event=team.target_event)
    events = sorted(int(event) for event in weekly["forecast_event"].astype(int).unique())
    owned = set(team.squad["id"].astype(int))
    statuses = team.chip_status or {
        chip: {"available": True, "used_event": None, "half": 1,
               "expires_after_gw": 19, "blocked_consecutive": False}
        for chip in ["wildcard", "free_hit", "triple_captain", "bench_boost"]
    }
    detail_by_event = {}
    context_by_event = {}
    for event in events:
        rows = weekly[weekly["forecast_event"].eq(event)]
        detail = _squad_event_score(rows, owned)
        detail_by_event[event] = detail
        current = rows[rows["id"].isin(owned)]
        doubles = int(current["planned_fixtures"].ge(2).sum()) if "planned_fixtures" in current else 0
        blanks = int(current["planned_fixtures"].eq(0).sum()) if "planned_fixtures" in current else 0
        context_by_event[event] = {"double_players": doubles, "blank_players": blanks}

    candidates: list[dict] = []
    normal_cache: dict[tuple[int, ...], WindowSolution] = {}

    def normal_alternative(window_events: list[int]) -> WindowSolution:
        key = tuple(window_events)
        if key not in normal_cache:
            normal_cache[key] = _optimize_window(
                team, window_events, max_transfers=min(5, max(0, team.free_transfers))
            )
        return normal_cache[key]

    def add(chip: str, event: int, gain: float, projected: float, reason: str,
            transfers: int = 0, squad: list[str] | None = None,
            available: bool | None = None, window: int = 1) -> None:
        status = statuses.get(chip, {})
        is_available = bool(status.get("available", True)) if available is None else available
        expiry = int(status.get("expires_after_gw", 19 if event <= 19 else 38))
        threshold = _threshold(chip, event, expiry, window)
        candidates.append({
            "chip": chip, "label": CHIP_LABELS[chip], "event": int(event),
            "gain": round(float(gain), 2), "projected_points": round(float(projected), 2),
            "threshold": threshold, "decision": _decision(gain, threshold, is_available),
            "available": is_available, "reason": reason,
            "transfers_needed": int(transfers), "squad": squad or [],
            **context_by_event[event],
        })

    for event in events:
        detail = detail_by_event[event]
        context = context_by_event[event]
        suffix = (f" {context['double_players']} av dine spillere dobler."
                  if context["double_players"] else "")
        add(
            "triple_captain", event, detail["captain_points"],
            detail["base"] + detail["captain_points"],
            f"{detail['captain']} gir ett ekstra sett kapteinspoeng.{suffix}",
        )
        add(
            "bench_boost", event, detail["bench_points"],
            detail["base"] + detail["bench_points"],
            f"Benkens fire spillere gir {detail['bench_points']:.2f} ekstra forventede poeng.{suffix}",
        )
        free_hit = _optimize_window(team, [event])
        normal_event = normal_alternative([event])
        fh_gain = free_hit.total_points - normal_event.total_points
        blank_note = (f" Du har {context['blank_players']} blanke spillere."
                      if context["blank_players"] else "")
        add(
            "free_hit", event, fh_gain, free_hit.total_points,
            f"Optimal énrundetropp mot beste plan med {team.free_transfers} gratisbytter.{blank_note}",
            free_hit.transfers_needed, free_hit.squad_names,
        )
        window_events = [candidate for candidate in events if candidate >= event]
        wildcard = _optimize_window(team, window_events)
        normal_window = normal_alternative(window_events)
        wc_gain = wildcard.total_points - normal_window.total_points
        add(
            "wildcard", event, wc_gain, wildcard.total_points,
            f"Permanent optimal tropp over {len(window_events)} kjente Gameweeks; "
            "senere runder er ikke prognostisert.",
            wildcard.transfers_needed, wildcard.squad_names,
            window=len(window_events),
        )

    sequence_status = (
        statuses.get("wildcard", {}).get("available", True)
        and statuses.get("bench_boost", {}).get("available", True)
    )
    for event, boost_event in zip(events, events[1:]):
        window_events = [candidate for candidate in events if candidate >= event]
        sequence = _optimize_window(team, window_events, bench_boost_event=boost_event)
        normal_window = normal_alternative(window_events)
        gain = sequence.total_points - normal_window.total_points
        add(
            "wildcard_bench_boost", event, gain, sequence.total_points,
            f"Wildcard i GW{event}, deretter Bench Boost i GW{boost_event}; "
            "troppen optimeres samlet for sekvensen.",
            sequence.transfers_needed, sequence.squad_names,
            available=bool(sequence_status), window=len(window_events),
        )

    candidate_frame = pd.DataFrame(candidates)
    best_rows = []
    for chip, group in candidate_frame.groupby("chip", sort=False):
        ranked = group.assign(excess=group["gain"] - group["threshold"]).sort_values(
            ["excess", "gain", "event"], ascending=[False, False, True]
        )
        best_rows.append(ranked.iloc[0].drop(labels="excess").to_dict())
    best = sorted(best_rows, key=lambda row: (
        row["decision"] == "PLAY", row["gain"] - row["threshold"], row["gain"]
    ), reverse=True)
    plays = [row for row in best if row["decision"] == "PLAY"]
    if plays:
        chosen = plays[0]
        recommendation = f"{chosen['label']} i GW{chosen['event']}"
        summary = (f"Modellen måler {chosen['gain']:.2f} forventede ekstrapoeng "
                   f"i den kjente horisonten.")
    else:
        recommendation = "Spar chips foreløpig"
        summary = ("Ingen tilgjengelig chip slår den forsiktige bruksterskelen i de "
                   f"neste {len(events)} Gameweekene.")
    return {
        "recommendation": recommendation,
        "summary": summary,
        "target_event": team.target_event,
        "forecast_events": events,
        "horizon_limited": True,
        "chip_status": statuses,
        "best_by_chip": best,
        "candidates": candidates,
        "rules": {
            "sets_per_season": 2, "half_boundary": 19,
            "one_chip_per_gameweek": True,
            "free_hit_not_consecutive": True,
        },
    }
