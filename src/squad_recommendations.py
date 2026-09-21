"""Standalone Free Hit and Wildcard squads with a forward transfer roadmap."""

from __future__ import annotations

from dataclasses import replace
import json

import pandas as pd

from chip_strategy import _expected_view, _optimize_window
from fpl_app import AppError, ImportedTeam, optimal_lineup
from multiweek_planner import plan_multiweek


def _player_records(frame: pd.DataFrame) -> list[dict]:
    columns = [
        "id", "name", "position", "team", "opponent", "price",
        "recommended_points", "expected_60plus_appearances",
        "market_clean_sheet_probability", "market_team_expected_goals",
        "market_player_goal_probability", "market_player_assist_probability",
        "role", "bench_order",
    ]
    available = [column for column in columns if column in frame]
    return json.loads(frame[available].to_json(orient="records"))


def _selection(team: ImportedTeam, squad_ids: set[int], event: int) -> dict:
    weekly = team.weekly_market
    if weekly is None:
        weekly = team.market.assign(forecast_event=team.target_event)
    event_rows = weekly[weekly.forecast_event.eq(event)]
    squad = _expected_view(event_rows[event_rows.id.isin(squad_ids)])
    if len(squad) != 15:
        raise AppError(f"Lagforslaget fant {len(squad)} av 15 spillere i GW{event}.")
    lineup = optimal_lineup(squad)
    starters = lineup["starters"].copy()
    bench = lineup["bench"].copy()
    owned = set(team.squad.id.astype(int))
    sale = team.squad.set_index("id").selling_price.astype(int).to_dict()
    prices = team.market.set_index("id").price.astype(int).to_dict()
    effective_cost = sum(
        sale[player_id] if player_id in owned else prices[player_id]
        for player_id in squad_ids
    )
    available_cash = int(team.bank + sum(sale.values()))
    return {
        "event": int(event),
        "formation": lineup["formation"],
        "projected_points": round(float(lineup["expected_total"]), 2),
        "captain": str(starters.loc[starters.role.eq("C"), "name"].iloc[0]),
        "vice_captain": str(starters.loc[starters.role.eq("VC"), "name"].iloc[0]),
        "starters": _player_records(starters),
        "bench": _player_records(bench),
        "squad": _player_records(pd.concat([starters, bench], ignore_index=True)),
        "effective_cost": round(effective_cost / 10, 1),
        "money_left": round((available_cash - effective_cost) / 10, 1),
    }


def _wildcard_roadmap(team: ImportedTeam, squad_ids: set[int], events: list[int]) -> dict:
    """Plan ordinary post-Wildcard transfers from the optimized initial squad."""
    if len(events) <= 1:
        return {"weeks": [], "total_projected_points": 0.0,
                "caveat": "Ingen senere Gameweeks finnes i den frosne prognosen."}
    owned = set(team.squad.id.astype(int))
    current_sale = team.squad.set_index("id").selling_price.astype(int).to_dict()
    selected = team.market[team.market.id.isin(squad_ids)].copy()
    selected["selling_price"] = [
        current_sale[int(player_id)] if int(player_id) in owned else int(price)
        for player_id, price in zip(selected.id, selected.price)
    ]
    selected["purchase_price"] = selected["selling_price"]
    selected["price_is_estimate"] = True
    available_cash = int(team.bank + sum(current_sale.values()))
    spent = int(selected.selling_price.sum())
    future_weekly = team.weekly_market[
        team.weekly_market.forecast_event.isin(events[1:])
    ].copy()
    virtual = replace(
        team,
        target_event=events[1],
        bank=max(0, available_cash - spent),
        squad=selected.reset_index(drop=True),
        lineup_squad=selected.reset_index(drop=True),
        weekly_market=future_weekly,
        horizon=len(events) - 1,
    )
    return plan_multiweek(virtual, weeks=len(events) - 1, discount=.9)


def recommend_squads(team: ImportedTeam) -> dict:
    """Return an optimal Free Hit for every known GW and one long-view Wildcard."""
    weekly = team.weekly_market
    if weekly is None:
        weekly = team.market.assign(forecast_event=team.target_event)
    events = sorted(int(value) for value in weekly.forecast_event.unique())
    if not events:
        raise AppError("Ingen komplette Gameweek-prognoser er tilgjengelige.")

    free_hits = []
    for event in events:
        solution = _optimize_window(team, [event], discount=1.0)
        free_hits.append({
            **_selection(team, solution.squad_ids, event),
            "transfers_needed": solution.transfers_needed,
        })

    wildcard_solution = _optimize_window(team, events, discount=.9)
    wildcard = {
        **_selection(team, wildcard_solution.squad_ids, events[0]),
        "horizon_events": events,
        "horizon_points_before_future_transfers": round(
            wildcard_solution.total_points, 2
        ),
        "discount": .9,
        "transfers_needed": wildcard_solution.transfers_needed,
        "roadmap": _wildcard_roadmap(team, wildcard_solution.squad_ids, events),
    }
    return {
        "forecast_events": events,
        "free_hit_by_event": free_hits,
        "wildcard": wildcard,
        "method": (
            "Eksakt FPL-lovlig optimering. Free Hit maksimerer én runde; Wildcard "
            "vekter nærmeste runde høyest og får en ny optimal bytteplan etterpå."
        ),
        "caveat": (
            "Forslagene bruker frosne forventede poeng, dagens priser og dagens "
            "skadeinformasjon. Kjør på nytt før hver deadline."
        ),
    }
