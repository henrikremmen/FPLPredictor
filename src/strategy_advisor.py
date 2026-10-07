"""Turn forecasts and official FPL context into a weekly manager workflow.

The prediction model answers *how many points?*.  This module answers the
separate manager questions: should I roll, what is urgent, how certain is the
captain call, is the squad resilient, and can a price move block the plan?
It is deliberately read-only and labels price-change data as a guide.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from fpl_app import AppError, ImportedTeam, optimal_lineup
from multiweek_planner import plan_multiweek


def _safe(value: Any, digits: int | None = None) -> Any:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if digits is not None and isinstance(value, (int, float)):
        return round(float(value), digits)
    return value


def _number(row: pd.Series, key: str, default: float = 0.0) -> float:
    value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
    return float(value) if pd.notna(value) else default


def _series(frame: pd.DataFrame, key: str, default: Any) -> pd.Series:
    if key in frame:
        return frame[key]
    return pd.Series(default, index=frame.index)


def _player(row: pd.Series) -> dict:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "position": str(row["position"]),
        "team": str(row["team"]),
        "opponent": str(row.get("opponent", "–")),
        "price": int(row.get("price", 0)),
        "points": _safe(_number(row, "recommended_points"), 2),
        "decision_points": _safe(_number(row, "decision_points", _number(
            row, "recommended_points"
        )), 2),
        "ownership": _safe(_number(row, "selected_by_percent", np.nan), 1),
        "availability": _safe(_number(row, "availability", 1.0), 2),
        "status": str(row.get("status", "a")),
        "news": str(row.get("news", "") or ""),
        "price_change_percent": _safe(_number(row, "price_change_percent", np.nan), 1),
        "price_change_projected_percent": _safe(_number(
            row, "price_change_projected_percent", np.nan
        ), 1),
        "price_change_likelihood": int(_number(row, "price_change_likelihood", 0)),
        "value_score": _safe(
            _number(row, "recommended_points") / max(.1, _number(row, "price") / 10), 2
        ),
    }


def _deadline_context(deadline: str, now: datetime | None = None) -> dict:
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    try:
        target = pd.Timestamp(deadline)
        if target.tzinfo is None:
            target = target.tz_localize("UTC")
    except (TypeError, ValueError):
        return {"deadline": deadline, "hours_remaining": None, "urgency": "unknown"}
    hours = (target - current).total_seconds() / 3600
    urgency = "passed" if hours <= 0 else "now" if hours <= 2 else "today" if hours <= 24 else "open"
    return {
        "deadline": target.isoformat(),
        "hours_remaining": round(hours, 1),
        "urgency": urgency,
    }


def _next_market(team: ImportedTeam) -> pd.DataFrame:
    if team.weekly_market is not None and "forecast_event" in team.weekly_market:
        rows = team.weekly_market[
            team.weekly_market["forecast_event"].astype(int).eq(team.target_event)
        ]
        if not rows.empty:
            return rows.drop_duplicates("id").copy()
    if team.lineup_squad is not None:
        # lineup_squad only contains owned players, so use it only when the
        # full market is unavailable.
        if set(team.market["id"]) == set(team.lineup_squad["id"]):
            return team.lineup_squad.drop_duplicates("id").copy()
    return team.market.drop_duplicates("id").copy()


def _price_alerts(team: ImportedTeam, next_market: pd.DataFrame) -> dict:
    if "price_change_percent" not in next_market:
        return {"available": False, "owned_at_risk": [], "targets_rising": [],
                "caveat": "FPL's Price Change Predictor is not found in this data snapshot."}
    owned_ids = set(team.squad["id"].astype(int))
    frame = next_market.copy()
    frame["_price_now"] = pd.to_numeric(frame["price_change_percent"], errors="coerce")
    frame["_price_next"] = pd.to_numeric(
        _series(frame, "price_change_projected_percent", np.nan), errors="coerce"
    )
    frame["_score"] = pd.to_numeric(frame["recommended_points"], errors="coerce").fillna(0)
    owned = frame[frame["id"].isin(owned_ids)]
    falling = owned[(owned["_price_now"] <= -80) | (owned["_price_next"] <= -100)].sort_values(
        ["_price_next", "_price_now"], ascending=True
    )
    candidates = frame[
        ~frame["id"].isin(owned_ids)
        & _series(frame, "can_transact", True).fillna(True).astype(bool)
        & _series(frame, "status", "a").eq("a")
    ].nlargest(35, "_score")
    rising = candidates[
        (candidates["_price_now"] >= 80) | (candidates["_price_next"] >= 100)
    ].sort_values(["_price_next", "_score"], ascending=[False, False])
    return {
        "available": True,
        "owned_at_risk": [_player(row) for _, row in falling.head(6).iterrows()],
        "targets_rising": [_player(row) for _, row in rising.head(6).iterrows()],
        "caveat": (
            "Official FPL indicator, but still just one forecast. Price changes happen "
            "at midnight UK time; weigh injury risk before making an early transfer."
        ),
    }


def _captain_advice(lineup: dict) -> dict:
    score = lineup["score_column"]
    ranked = lineup["starters"].sort_values([score, "id"], ascending=[False, True]).head(3)
    choices = [_player(row) for _, row in ranked.iterrows()]
    margin = float(lineup["captain_margin"])
    confidence = "strong" if margin >= 1.5 else "medium" if margin >= .5 else "close"
    return {
        "captain": choices[0],
        "vice_captain": choices[1],
        "alternatives": choices,
        "margin": round(margin, 2),
        "confidence": confidence,
        "reason": (
            "Clear model margin; keep the captain unless team news changes expected minutes."
            if confidence == "strong" else
            "Captain choices are close. Use team news and your chosen risk profile as the tiebreaker."
            if confidence == "close" else
            "The model has a moderate advantage, but the latest team news is still important."
        ),
    }


def _squad_health(team: ImportedTeam, lineup: dict) -> dict:
    squad = team.lineup_squad if team.lineup_squad is not None else team.squad
    starters = set(lineup["starters"]["id"].astype(int))
    planned = pd.to_numeric(_series(squad, "planned_fixtures", 1), errors="coerce").fillna(0)
    availability = pd.to_numeric(_series(squad, "availability", 1), errors="coerce").fillna(1)
    selectable = _series(squad, "can_select", True).fillna(True).astype(bool)
    playable = selectable & planned.gt(0) & availability.ge(.75)
    flagged = squad[(~playable) | _series(squad, "status", "a").ne("a")]
    flagged_starters = flagged[flagged["id"].isin(starters)]
    bench = lineup["bench"]
    bench_points = float(pd.to_numeric(bench["recommended_points"], errors="coerce").fillna(0).sum())
    club_counts = squad.groupby(["team_id", "team"]).size().sort_values(ascending=False)
    triple_ups = [str(team_name) for (_, team_name), count in club_counts.items() if count >= 3]
    return {
        "playable_players": int(playable.sum()),
        "flagged_players": [_player(row) for _, row in flagged.iterrows()],
        "flagged_starters": [_player(row) for _, row in flagged_starters.iterrows()],
        "bench_expected_points": round(bench_points, 2),
        "playable_outfield_bench": int((
            bench["position"].ne("GK")
            & pd.to_numeric(_series(bench, "availability", 1), errors="coerce").fillna(1).ge(.75)
        ).sum()),
        "triple_ups": triple_ups,
        "rating": "healthy" if playable.sum() >= 14 else "watch" if playable.sum() >= 12 else "fragile",
    }


def _watchlists(team: ImportedTeam, next_market: pd.DataFrame) -> dict:
    owned = set(team.squad["id"].astype(int))
    candidates = next_market[
        ~next_market["id"].isin(owned)
        & _series(next_market, "can_select", True).fillna(True).astype(bool)
        & _series(next_market, "status", "a").eq("a")
    ].copy()
    score = "decision_points" if "decision_points" in candidates else "recommended_points"
    candidates["_score"] = pd.to_numeric(candidates[score], errors="coerce").fillna(0)
    candidates["_value"] = candidates["_score"] / (
        pd.to_numeric(candidates["price"], errors="coerce").clip(lower=1) / 10
    )
    top = candidates.sort_values(["_score", "_value", "id"], ascending=[False, False, True])
    ownership = pd.to_numeric(_series(candidates, "selected_by_percent", np.nan), errors="coerce")
    differentials = candidates[ownership.lt(10)].sort_values(
        ["_score", "_value", "id"], ascending=[False, False, True]
    )
    value = candidates.sort_values(["_value", "_score", "id"], ascending=[False, False, True])
    return {
        "top_targets": [_player(row) for _, row in top.head(6).iterrows()],
        "differentials": [_player(row) for _, row in differentials.head(6).iterrows()],
        "value": [_player(row) for _, row in value.head(6).iterrows()],
        "caveat": "Low ownership is not value itself; the list is filtered on model points first.",
    }


def _schedule(team: ImportedTeam) -> list[dict]:
    weekly = team.weekly_market
    if weekly is None or "forecast_event" not in weekly:
        weekly = team.market.assign(forecast_event=team.target_event)
    owned = weekly[weekly["id"].isin(set(team.squad["id"].astype(int)))]
    result = []
    for event, group in owned.groupby("forecast_event", sort=True):
        fixtures = pd.to_numeric(_series(group, "planned_fixtures", 1), errors="coerce").fillna(0)
        result.append({
            "event": int(event),
            "blank_players": int(fixtures.eq(0).sum()),
            "double_players": int(fixtures.ge(2).sum()),
        })
    return result


def _transfer_warnings(next_market: pd.DataFrame, outgoing: list[str],
                       incoming: list[str], global_optimum: bool) -> list[str]:
    """Expose conflicting public signals instead of hiding model uncertainty."""
    warnings: list[str] = []
    by_name = next_market.drop_duplicates("name").set_index("name")
    if not global_optimum:
        warnings.append(
            "The solver found a validated legal plan but did not prove global optimality."
        )
    for name in outgoing:
        if name not in by_name.index:
            continue
        row = by_name.loc[name]
        model = _number(row, "recommended_points", np.nan)
        official = _number(row, "ep_next", np.nan)
        if np.isfinite(model) and np.isfinite(official) and official - model >= .5:
            warnings.append(
                f"FPL's own next-gameweek estimate for {name} is {official:.1f}, "
                f"{official - model:.1f} above the model's {model:.1f}."
            )
        price = _number(row, "price_change_projected_percent", np.nan)
        if np.isfinite(price) and price >= 100:
            warnings.append(
                f"{name} is simultaneously estimated at {price:.0f}% against a possible price rise."
            )
    for name in incoming:
        if name not in by_name.index:
            continue
        row = by_name.loc[name]
        availability = _number(row, "availability", 1)
        if availability < .9 or str(row.get("status", "a")) != "a":
            warnings.append(
                f"{name} has reduced availability ({availability:.0%}); check team news."
            )
    return list(dict.fromkeys(warnings))


def build_strategy_advice(
    team: ImportedTeam,
    *,
    planner: Callable[..., dict] = plan_multiweek,
    now: datetime | None = None,
) -> dict:
    """Build a prioritized, explainable weekly decision brief."""
    next_market = _next_market(team)
    lineup_source = team.lineup_squad if team.lineup_squad is not None else team.squad
    lineup = optimal_lineup(lineup_source)
    known_events = (
        sorted(team.weekly_market["forecast_event"].astype(int).unique())
        if team.weekly_market is not None and "forecast_event" in team.weekly_market else
        [team.target_event]
    )
    weeks = min(max(1, team.horizon), len(known_events), 5)
    unrestricted_plan = planner(team, weeks=weeks, discount=.9)
    if not unrestricted_plan.get("weeks"):
        raise AppError("The strategy centre did not have a validated multi-week plan.")
    plan = unrestricted_plan
    hit_guard = {
        "evaluated": False, "avoided": False, "model_gain_after_hit": None,
        "required_uncertainty_buffer": None,
    }
    unrestricted_first = unrestricted_plan["weeks"][0]
    unrestricted_hit = int(unrestricted_first.get("hit", 0))
    if unrestricted_hit:
        no_hit_plan = planner(team, weeks=weeks, discount=.9, allow_hits=False)
        unrestricted_value = float(unrestricted_plan.get("discounted_objective_points", -np.inf))
        no_hit_value = float(no_hit_plan.get("discounted_objective_points", -np.inf))
        gain = unrestricted_value - no_hit_value
        paid_transfers = max(1, unrestricted_hit // 4)
        required_buffer = 2.0 * paid_transfers
        avoid = not np.isfinite(gain) or gain < required_buffer
        if avoid and no_hit_plan.get("weeks"):
            plan = no_hit_plan
        hit_guard = {
            "evaluated": True,
            "avoided": bool(avoid),
            "model_gain_after_hit": round(gain, 2) if np.isfinite(gain) else None,
            "required_uncertainty_buffer": required_buffer,
        }
    first = plan["weeks"][0]
    outgoing = list(first.get("transfers_out", []))
    incoming = list(first.get("transfers_in", []))
    hit = int(first.get("hit", 0))
    if outgoing:
        decision = "HIT" if hit else "TRANSFER"
        title = f"{', '.join(outgoing)} → {', '.join(incoming)}"
        reason = (
            f"Multiweek optimization finds that {len(outgoing)} transfer(s) now gives the best "
            f"sequence over {weeks} GW. The plan includes −{hit}."
            if hit else
            f"Multi-week optimization prefers {len(outgoing)} transfer(s) now rather than rolling."
        )
    else:
        decision = "HOLD" if team.free_transfers >= 5 else "ROLL"
        title = "Keep squad" if decision == "HOLD" else "Roll the free transfer"
        reason = (
            "You have five free transfers, so you cannot bank any more. The model still finds "
            "no better legal change within the known horizon."
            if decision == "HOLD" else
            f"The best validated {weeks}-GW plan makes no change now and retains flexibility."
        )
    if hit_guard["avoided"]:
        measured = hit_guard["model_gain_after_hit"]
        reason += (
            " A more aggressive plan included a hit, but "
            + (f"the additional gain after the hit was only {measured:.2f} " if measured is not None
               else "the added value could not be validated ")
            + f"against the uncertainty buffer of {hit_guard['required_uncertainty_buffer']:.2f}; "
              "It is therefore rejected."
        )
    warnings = _transfer_warnings(
        next_market, outgoing, incoming, bool(plan.get("global_optimum", False))
    )
    confidence = "low" if len(warnings) >= 2 else "medium" if warnings else "high"
    transfer = {
        "decision": decision,
        "title": title,
        "reason": reason,
        "transfers_out": outgoing,
        "transfers_in": incoming,
        "hit": hit,
        "free_transfers_before": int(first.get("free_transfers_before", team.free_transfers)),
        "bank_after": _safe(first.get("bank"), 1),
        "global_optimum": bool(plan.get("global_optimum", False)),
        "horizon": weeks,
        "hit_guard": hit_guard,
        "confidence": confidence,
        "warnings": warnings,
    }
    health = _squad_health(team, lineup)
    captain = _captain_advice(lineup)
    prices = _price_alerts(team, next_market)
    deadline = _deadline_context(team.deadline, now)

    actions: list[dict] = []
    if health["flagged_starters"]:
        names = ", ".join(player["name"] for player in health["flagged_starters"])
        actions.append({
            "priority": 1, "severity": "urgent", "category": "team_news",
            "title": f"Check {names}",
            "detail": "At least one recommended starter is flagged or has a reduced chance of playing.",
            "view": "lineup",
        })
    actions.append({
        "priority": 2, "severity": "decision", "category": "transfer",
        "title": transfer["title"], "detail": transfer["reason"], "view": "plan",
    })
    actions.append({
        "priority": 3, "severity": "decision", "category": "captain",
        "title": f"Captain {captain['captain']['name']}",
        "detail": captain["reason"], "view": "lineup",
    })
    if prices["owned_at_risk"] or prices["targets_rising"]:
        actions.append({
            "priority": 4, "severity": "monitor", "category": "price",
            "title": "Check price changes",
            "detail": (
                f"{len(prices['owned_at_risk'])} owned player(s) near fall and "
                f"{len(prices['targets_rising'])} relevant targets near rise."
            ),
            "view": "strategy",
        })
    actions.append({
        "priority": 5, "severity": "check", "category": "deadline",
        "title": "Make a final team-news check",
        "detail": "Update the forecast after press conferences and any mid-week games.",
        "view": "overview",
    })

    available_chips = [
        chip for chip, status in team.chip_status.items() if status.get("available")
    ]
    expiry = min(
        (int(team.chip_status[chip].get("expires_after_gw", 38)) for chip in available_chips),
        default=None,
    )
    if expiry is not None and expiry - team.target_event <= 3:
        actions.append({
            "priority": 1, "severity": "urgent", "category": "chip",
            "title": f"{len(available_chips)} chip(s) expire after GW{expiry}",
            "detail": "There is no value in saving them beyond expiry; run the chip analysis now.",
            "view": "chips",
        })
    actions.sort(key=lambda item: (item["priority"], item["category"]))

    return {
        "target_event": int(team.target_event),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": transfer["title"],
        "deadline": deadline,
        "manager_context": {
            "overall_points": team.overall_points,
            "overall_rank": team.overall_rank,
            "team_value": _safe(team.team_value / 10 if team.team_value is not None else None, 1),
            "risk_profile": team.risk_profile,
        },
        "transfer": transfer,
        "captain": captain,
        "squad_health": health,
        "price_alerts": prices,
        "watchlists": _watchlists(team, next_market),
        "schedule": _schedule(team),
        "actions": actions,
        "plan": plan,
        "principles": [
            "Roll when the marginal gain is small; free transfers provide more flexibility later.",
            "Evaluate transfers over multiple gameweeks, but recalculate before every deadline.",
            "Use 15 playable players when rotation and bench coverage actually has value.",
            "Build team value early without taking uncompensated injury and benching risk.",
            "Choose differentials because the forecast is good, not just because the ownership is low.",
        ],
        "method": (
            "Exact rule-controlled multi-week plan combined with model score, availability, "
            "Public FPL ownership and the official Price Change Predictor indicator."
        ),
        "caveat": (
            "The app never makes transfers. Free transfers reconstructed from public history are an estimate; "
            "check your balance and the latest team news in FPL before the deadline."
        ),
    }
