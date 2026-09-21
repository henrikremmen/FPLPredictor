"""Interactive, read-only FPL decision helper built on this project's forecasts.

The app imports a public FPL entry URL, joins the squad to the newest frozen
model forecast and recommends a legal lineup and transfers. It never logs in
to FPL and never writes changes to a manager's team.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import combinations, product
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable

import numpy as np
import pandas as pd
import requests
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, vstack


API = "https://fantasy.premierleague.com/api/"
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POSITION_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
SQUAD_POSITION_COUNTS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
ENTRY_PATTERN = re.compile(r"(?:^|/)entry/(\d+)(?:/event/(\d+))?/?(?:[?#].*)?$")


class AppError(RuntimeError):
    """An expected problem that can be shown directly to the user."""


def parse_entry_reference(value: str) -> tuple[int, int | None]:
    """Accept a numeric entry ID or an FPL entry URL."""
    value = value.strip()
    if value.isdigit():
        return int(value), None
    match = ENTRY_PATTERN.search(value)
    if not match:
        raise AppError("Ugyldig lagreferanse. Lim inn en FPL-lenke eller et numerisk lag-ID.")
    return int(match.group(1)), int(match.group(2)) if match.group(2) else None


def selling_price(purchase_price: int, current_price: int) -> int:
    """FPL selling price in tenths of a million."""
    if current_price < purchase_price:
        return current_price
    return purchase_price + (current_price - purchase_price) // 2


def estimate_free_transfers(history: dict, through_event: int, started_event: int = 1) -> int:
    """Estimate public free-transfer balance for the next event.

    The authenticated FPL endpoint is the only authoritative source. Wildcard
    and Free Hit weeks are treated as preserving the incoming balance.
    """
    rows = {int(row["event"]): row for row in history.get("current", [])}
    chips = {int(row["event"]): row.get("name") for row in history.get("chips", [])}
    available = 1
    for event in range(started_event + 1, through_event + 1):
        used = int(rows.get(event, {}).get("event_transfers", 0))
        chip = str(chips.get(event, "")).lower()
        if chip in {"wildcard", "freehit", "free_hit"}:
            # The current week's allocation activates the chip; previously
            # banked transfers are retained, so the entering balance is the
            # balance shown again in the following Gameweek.
            continue
        available = min(5, max(0, available - used) + 1)
    return available


def chip_inventory(history: dict, target_event: int) -> dict[str, dict]:
    """Return public chip availability for the half containing target_event."""
    aliases = {
        "wildcard": "wildcard", "freehit": "free_hit",
        "3xc": "triple_captain", "triplecaptain": "triple_captain",
        "bboost": "bench_boost", "benchboost": "bench_boost",
    }
    half = 1 if target_event <= 19 else 2
    start, end = (1, 19) if half == 1 else (20, 38)
    used: dict[str, int] = {}
    all_free_hit_events = []
    for row in history.get("chips", []):
        event = int(row.get("event", 0))
        normalized = str(row.get("name", "")).lower().replace("-", "").replace("_", "")
        chip = aliases.get(normalized)
        if chip == "free_hit":
            all_free_hit_events.append(event)
        if chip is not None and start <= event <= end:
            used[chip] = event
    result = {}
    for chip in ["wildcard", "free_hit", "triple_captain", "bench_boost"]:
        blocked_consecutive = chip == "free_hit" and target_event - 1 in all_free_hit_events
        used_event = used.get(chip)
        result[chip] = {
            "available": (used_event is None and not blocked_consecutive and
                          not (target_event == 1 and chip in {"wildcard", "free_hit"})),
            "used_event": used_event,
            "blocked_consecutive": blocked_consecutive,
            "half": half,
            "expires_after_gw": end,
        }
    return result


class FPLClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "fplmodell-readonly-app/1.0"})

    def get(self, endpoint: str):
        try:
            response = self.session.get(API + endpoint, timeout=(8, 30))
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AppError(f"Kunne ikke hente FPL-data ({endpoint}): {exc}") from exc

    def initial_prices(self, player_ids: Iterable[int], started_event: int) -> dict[int, int]:
        """Approximate initial acquisition price from public player history."""
        ids = sorted(set(int(x) for x in player_ids))

        def one(player_id: int) -> tuple[int, int | None]:
            summary = self.get(f"element-summary/{player_id}/")
            row = next((h for h in summary.get("history", [])
                        if int(h.get("round", -1)) == started_event), None)
            return player_id, int(row["value"]) if row and row.get("value") is not None else None

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(one, ids))
        return {player_id: price for player_id, price in results if price is not None}


@dataclass
class ImportedTeam:
    entry_id: int
    event: int
    target_event: int
    manager_name: str
    team_name: str
    bank: int
    free_transfers: int
    squad: pd.DataFrame
    market: pd.DataFrame
    deadline: str
    forecast_path: Path
    horizon: int = 1
    lineup_squad: pd.DataFrame | None = None
    weekly_market: pd.DataFrame | None = None
    risk_profile: str = "balanced"
    chip_status: dict[str, dict] = field(default_factory=dict)
    overall_points: int | None = None
    overall_rank: int | None = None
    team_value: int | None = None
    squad_source: str = "fpl_public"
    manual_changes: list[dict] = field(default_factory=list)


def latest_forecast(root: Path, target_event: int) -> Path:
    candidates = sorted(
        root.glob("data/raw/live_fpl/capture_*/forecast.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            manifest = json.loads((path.parent / "manifest.json").read_text())
            if manifest.get("forecast_status") != "experimental_frozen":
                continue
            events = pd.read_csv(path, usecols=["GW"])["GW"].dropna().astype(int).unique()
        except (OSError, ValueError, KeyError, json.JSONDecodeError, pd.errors.EmptyDataError):
            continue
        if events.tolist() == [target_event]:
            return path
    raise AppError(
        f"Fant ingen modellprognose for GW{target_event}. "
        "Oppdater prognosen først (--refresh i terminalappen)."
    )


def _availability_factor(player: dict) -> float:
    chance = player.get("chance_of_playing_next_round")
    if chance is not None:
        return min(1.0, max(0.0, float(chance) / 100.0))
    return 1.0 if player.get("status", "a") == "a" else 0.75


def _opponents(fixtures: list[dict], teams: dict[int, str], events: list[int]) -> dict[int, str]:
    result: dict[int, list[str]] = {}
    for fixture in fixtures:
        event = fixture.get("event")
        if event not in events:
            continue
        home, away = int(fixture["team_h"]), int(fixture["team_a"])
        prefix = f"GW{event}:" if len(events) > 1 else ""
        result.setdefault(home, []).append(f"{prefix}{teams[away]} (H)")
        result.setdefault(away, []).append(f"{prefix}{teams[home]} (B)")
    return {team: " + ".join(names) for team, names in result.items()}


def build_market(bootstrap: dict, fixtures: list[dict], forecast_path: Path,
                 target_event: int, horizon: int = 1) -> pd.DataFrame:
    events = list(range(target_event, target_event + horizon))
    horizon_path = forecast_path.parent / "horizon_forecast.csv"
    source = horizon_path if horizon_path.exists() else forecast_path
    forecasts = pd.read_csv(source)
    if "GW" in forecasts:
        forecasts = forecasts[forecasts["GW"].isin(events)]
    if horizon > 1 or source == horizon_path:
        if source == forecast_path and horizon > 1:
            raise AppError("Flerukersprognosen mangler. Kjør appen med --refresh først.")
        if forecasts["GW"].nunique() < horizon:
            raise AppError(f"Prognosen inneholder ikke alle {horizon} ønskede Gameweeks.")
    optional = [column for column in [
        "expected_60plus_appearances", "expected_appearances",
        "prediction_q10", "prediction_q50", "prediction_q90",
        "market_clean_sheet_probability", "market_team_expected_goals",
        "market_player_goal_probability", "market_player_assist_probability",
    ]
                if column in forecasts]
    forecasts = forecasts.groupby("player_id", as_index=False).agg(**{
        "prediction": ("prediction", "sum"),
        "planned_fixtures": ("planned_fixtures", "sum"),
        **{column: (
            column,
            (lambda values: values.sum(min_count=1))
            if column.startswith("market_") else "sum",
        ) for column in optional},
    }).rename(columns={"player_id": "id"})
    forecasts["id"] = forecasts["id"].astype(int)
    team_names = {int(team["id"]): team["short_name"] for team in bootstrap["teams"]}
    opponents = _opponents(fixtures, team_names, events)
    rows = []
    for player in bootstrap["elements"]:
        if int(player.get("element_type", 0)) not in POSITIONS:
            continue
        projections = player.get("price_change_projections") or []
        next_projection = next(
            (item for item in projections if int(item.get("offset", -1)) == 0),
            projections[0] if projections else {},
        )

        def numeric(key: str, default=np.nan):
            value = player.get(key)
            try:
                return float(value) if value not in (None, "") else default
            except (TypeError, ValueError):
                return default

        rows.append({
            "id": int(player["id"]),
            "name": player["web_name"],
            "position": POSITIONS[int(player["element_type"])],
            "team_id": int(player["team"]),
            "team": team_names[int(player["team"])],
            "price": int(player["now_cost"]),
            "status": player.get("status", "a"),
            "news": player.get("news", "") or "",
            "availability": _availability_factor(player),
            "opponent": opponents.get(int(player["team"]), "Blank"),
            # Official public manager context. These are decision-support
            # fields, never substituted for the model's expected points.
            "selected_by_percent": numeric("selected_by_percent"),
            "transfers_in_event": int(player.get("transfers_in_event") or 0),
            "transfers_out_event": int(player.get("transfers_out_event") or 0),
            "cost_change_event": int(player.get("cost_change_event") or 0),
            "cost_change_start": int(player.get("cost_change_start") or 0),
            "price_change_percent": numeric("price_change_percent"),
            "price_change_projected_percent": (
                float(next_projection["projected_percent"])
                if next_projection.get("projected_percent") not in (None, "") else np.nan
            ),
            "price_change_likelihood": int(next_projection.get("likelihood") or 0),
            "price_change_calibrating": bool(player.get("price_change_calibrating", False)),
            "price_change_locked_until": player.get("price_change_locked_until"),
            "defensive_contribution_per_90": numeric("defensive_contribution_per_90"),
            "penalties_order": numeric("penalties_order"),
            "corners_and_indirect_freekicks_order": numeric(
                "corners_and_indirect_freekicks_order"
            ),
            "direct_freekicks_order": numeric("direct_freekicks_order"),
            "form": numeric("form"),
            "ep_next": numeric("ep_next"),
            "points_per_game": numeric("points_per_game"),
            "value_form": numeric("value_form"),
            "total_points": int(player.get("total_points") or 0),
            "can_select": bool(player.get("can_select", True)),
            "can_transact": bool(player.get("can_transact", True)),
        })
    market = pd.DataFrame(rows).merge(forecasts, on="id", how="left", validate="one_to_one")
    market["prediction"] = market["prediction"].fillna(0.0).clip(lower=0.0)
    market["planned_fixtures"] = market["planned_fixtures"].fillna(0).astype(int)
    for column in ["expected_60plus_appearances", "expected_appearances",
                   "prediction_q10", "prediction_q50", "prediction_q90",
                   "market_clean_sheet_probability", "market_team_expected_goals",
                   "market_player_goal_probability", "market_player_assist_probability"]:
        if column not in market:
            market[column] = np.nan
    market["recommended_points"] = market["prediction"] * market["availability"]
    for label in [10, 50, 90]:
        market[f"recommended_q{label}"] = (
            market[f"prediction_q{label}"] * market["availability"]
        )
    market["point_range_q10_q90"] = [
        f"{low:.1f}–{high:.1f}" if pd.notna(low) and pd.notna(high) else "–"
        for low, high in zip(market["recommended_q10"], market["recommended_q90"])
    ]
    return market


def apply_risk_profile(market: pd.DataFrame, profile: str) -> pd.DataFrame:
    """Attach the score used for decisions while preserving expected points.

    Stable/upside are transparent utility heuristics, not expected-point estimates.
    Stable penalises wide Q10–Q90 ranges; upside blends the mean with Q90.
    """
    if profile not in {"balanced", "stable", "upside"}:
        raise AppError("Risikoprofil må være balanced, stable eller upside.")
    result = market.copy()
    if profile == "balanced":
        result["decision_points"] = result["recommended_points"]
        return result
    required = ["recommended_q10", "recommended_q90"]
    if any(column not in result or result[column].isna().any() for column in required):
        raise AppError("Valgt risikoprofil krever en prognose med Q10–Q90.")
    if profile == "stable":
        width = result["recommended_q90"] - result["recommended_q10"]
        result["decision_points"] = result["recommended_points"] - .1 * width
    else:
        result["decision_points"] = (
            .7 * result["recommended_points"] + .3 * result["recommended_q90"]
        )
    return result


def acquisition_prices(client: FPLClient, entry_id: int, event: int,
                       started_event: int, current_ids: set[int],
                       current_prices: dict[int, int]) -> tuple[dict[int, int], bool]:
    """Reconstruct acquisition prices from initial picks and public transfers."""
    initial = client.get(f"entry/{entry_id}/event/{started_event}/picks/")
    initial_ids = {int(row["element"]) for row in initial["picks"]}
    transfers = sorted(
        (row for row in client.get(f"entry/{entry_id}/transfers/")
         if int(row["event"]) <= event),
        key=lambda row: (int(row["event"]), row.get("time", "")),
    )
    holdings: dict[int, int | None] = {player_id: None for player_id in initial_ids}
    for row in transfers:
        holdings.pop(int(row["element_out"]), None)
        holdings[int(row["element_in"])] = int(row["element_in_cost"])

    missing_initial = [player_id for player_id in current_ids
                       if player_id in initial_ids and holdings.get(player_id) is None]
    exact = True
    if missing_initial:
        try:
            holdings.update(client.initial_prices(missing_initial, started_event))
        except AppError:
            exact = False
    prices = {}
    for player_id in current_ids:
        price = holdings.get(player_id)
        if price is None:
            price = current_prices[player_id]
            exact = False
        prices[player_id] = int(price)
    return prices, exact


def import_team(reference: str, root: Path, client: FPLClient | None = None,
                horizon: int = 1, risk_profile: str = "balanced") -> ImportedTeam:
    client = client or FPLClient()
    if not 1 <= horizon <= 8:
        raise AppError("Prognosehorisonten må være mellom 1 og 8 Gameweeks.")
    entry_id, requested_event = parse_entry_reference(reference)
    entry = client.get(f"entry/{entry_id}/")
    bootstrap = client.get("bootstrap-static/")
    fixtures = client.get("fixtures/")
    history = client.get(f"entry/{entry_id}/history/")
    current_event = int(entry.get("current_event") or 0)
    event = requested_event or current_event
    if event <= 0:
        raise AppError("Laget har ingen ferdig eller aktiv Gameweek å importere ennå.")
    picks = client.get(f"entry/{entry_id}/event/{event}/picks/")
    target = next((row for row in bootstrap["events"] if row.get("is_next")), None)
    if target is None:
        raise AppError("FPL har ikke publisert en neste Gameweek ennå.")
    target_event = int(target["id"])
    forecast_path = latest_forecast(root, target_event)
    market = apply_risk_profile(
        build_market(bootstrap, fixtures, forecast_path, target_event, horizon), risk_profile
    )
    next_market = market if horizon == 1 else apply_risk_profile(build_market(
        bootstrap, fixtures, forecast_path, target_event, 1
    ), risk_profile)
    weekly_frames = []
    for forecast_event in range(target_event, target_event + horizon):
        frame = apply_risk_profile(
            build_market(bootstrap, fixtures, forecast_path, forecast_event, 1), risk_profile
        )
        frame["forecast_event"] = forecast_event
        weekly_frames.append(frame)
    weekly_market = pd.concat(weekly_frames, ignore_index=True)
    current_ids = {int(row["element"]) for row in picks["picks"]}
    current_prices = market.set_index("id")["price"].astype(int).to_dict()
    purchase, price_exact = acquisition_prices(
        client, entry_id, event, int(entry.get("started_event", 1)), current_ids, current_prices
    )

    pick_frame = pd.DataFrame(picks["picks"]).rename(columns={
        "element": "id", "position": "pick_position", "element_type": "pick_element_type"
    })
    def squad_for(player_market: pd.DataFrame) -> pd.DataFrame:
        result = pick_frame.merge(player_market, on="id", how="left", validate="one_to_one")
        if result["name"].isna().any():
            raise AppError("Minst én spiller i laget finnes ikke lenger i dagens FPL-register.")
        result["purchase_price"] = result["id"].map(purchase).astype(int)
        result["selling_price"] = [
            selling_price(int(purchase[player_id]), int(current_prices[player_id]))
            for player_id in result["id"]
        ]
        result["price_is_estimate"] = not price_exact
        return result.sort_values("pick_position").reset_index(drop=True)

    squad = squad_for(market)
    lineup_squad = squad if horizon == 1 else squad_for(next_market)
    entry_history = picks.get("entry_history", {})
    bank = int(entry_history.get("bank", 0))
    manager = " ".join(filter(None, [entry.get("player_first_name"), entry.get("player_last_name")]))
    return ImportedTeam(
        entry_id=entry_id,
        event=event,
        target_event=target_event,
        manager_name=manager or f"Lag {entry_id}",
        team_name=entry.get("name", f"Lag {entry_id}"),
        bank=bank,
        free_transfers=estimate_free_transfers(
            history, current_event, int(entry.get("started_event", 1))
        ),
        squad=squad.reset_index(drop=True),
        market=market,
        deadline=target["deadline_time"],
        forecast_path=forecast_path,
        horizon=horizon,
        lineup_squad=lineup_squad,
        weekly_market=weekly_market,
        risk_profile=risk_profile,
        chip_status=chip_inventory(history, target_event),
        overall_points=(int(entry_history["total_points"])
                        if entry_history.get("total_points") is not None else None),
        overall_rank=(int(entry_history["overall_rank"])
                      if entry_history.get("overall_rank") is not None else None),
        team_value=(int(entry_history["value"])
                    if entry_history.get("value") is not None else None),
    )


def _validate_holdings(market: pd.DataFrame, player_ids: list[int]) -> pd.DataFrame:
    if len(player_ids) != 15 or len(set(player_ids)) != 15:
        raise AppError("Troppen må inneholde 15 unike spillere.")
    selected = market[market["id"].isin(player_ids)].copy()
    if len(selected) != 15:
        missing = sorted(set(player_ids) - set(selected["id"].astype(int)))
        raise AppError(f"Spillere finnes ikke i dagens marked: {missing}")
    counts = selected["position"].value_counts().to_dict()
    if counts != SQUAD_POSITION_COUNTS:
        raise AppError(
            "Troppen må ha 2 keepere, 5 forsvarere, 5 midtbanespillere og 3 spisser."
        )
    clubs = selected["team_id"].astype(int).value_counts()
    if len(clubs) and int(clubs.max()) > 3:
        raise AppError("Troppen kan ha maksimalt tre spillere fra samme klubb.")
    return selected


def _frame_for_holdings(template: pd.DataFrame, market: pd.DataFrame,
                        holdings: list[dict]) -> pd.DataFrame:
    """Build an owned-squad frame while preserving FPL pick-slot metadata."""
    by_id = market.drop_duplicates("id").set_index("id")
    template_slots = {
        position: list(group.sort_values(
            "pick_position" if "pick_position" in group else "id"
        ).to_dict("records"))
        for position, group in template.groupby("position", sort=False)
    }
    slot_index = Counter()
    rows = []
    for holding in holdings:
        player_id = int(holding["id"])
        if player_id not in by_id.index:
            raise AppError(f"Spiller {player_id} finnes ikke i dagens prognose.")
        market_row = by_id.loc[player_id]
        if isinstance(market_row, pd.DataFrame):
            market_row = market_row.iloc[0]
        row = market_row.to_dict()
        row["id"] = player_id
        position = str(row["position"])
        templates = template_slots.get(position, [])
        index = slot_index[position]
        slot_index[position] += 1
        template_row = templates[index] if index < len(templates) else {}
        for column in [
            "pick_position", "pick_element_type", "multiplier",
            "is_captain", "is_vice_captain",
        ]:
            if column in template_row:
                row[column] = template_row[column]
        purchase = int(holding.get("purchase_price", row["price"]))
        current = int(row["price"])
        row.update(
            purchase_price=purchase,
            selling_price=selling_price(purchase, current),
            price_is_estimate=bool(holding.get("price_is_estimate", False)),
        )
        rows.append(row)
    result = pd.DataFrame(rows)
    if "pick_position" in result:
        result = result.sort_values("pick_position")
    else:
        result["_position_order"] = result.position.map(POSITION_ORDER)
        result = result.sort_values(["_position_order", "id"]).drop(
            columns="_position_order"
        )
    return result.reset_index(drop=True)


def set_team_holdings(team: ImportedTeam, holdings: list[dict]) -> None:
    """Replace ownership while keeping every forecast view internally aligned."""
    player_ids = [int(row["id"]) for row in holdings]
    _validate_holdings(team.market, player_ids)
    new_squad = _frame_for_holdings(team.squad, team.market, holdings)
    if team.weekly_market is not None:
        lineup_market = team.weekly_market[
            team.weekly_market["forecast_event"].eq(team.target_event)
        ].drop(columns="forecast_event")
    else:
        lineup_market = team.market
    template = team.lineup_squad if team.lineup_squad is not None else new_squad
    new_lineup_squad = _frame_for_holdings(template, lineup_market, holdings)
    team.squad = new_squad
    team.lineup_squad = new_lineup_squad
    team.team_value = int(team.squad["selling_price"].sum() + team.bank)


def apply_manual_squad_changes(team: ImportedTeam, changes: list[dict], mode: str,
                               bank: int | None = None,
                               free_transfers: int | None = None) -> dict:
    """Synchronize completed FPL moves or apply new simulated session moves."""
    if mode not in {"synchronize", "apply_transfers"}:
        raise AppError("Ukjent korrigeringsmodus.")
    if not changes:
        raise AppError("Velg minst ett spillerbytte.")
    if len(changes) > 5:
        raise AppError("Maksimalt fem spillerbytter kan lagres samtidig.")
    squad = team.squad.set_index("id", drop=False)
    market = team.market.drop_duplicates("id").set_index("id", drop=False)
    outgoing = [int(change["out_id"]) for change in changes]
    incoming = [int(change["in_id"]) for change in changes]
    if len(set(outgoing)) != len(outgoing) or len(set(incoming)) != len(incoming):
        raise AppError("Samme spiller kan ikke brukes i flere bytter.")
    owned = set(squad.index.astype(int))
    if not set(outgoing).issubset(owned):
        raise AppError("Minst én spiller som skal ut er ikke i troppen.")
    if set(incoming) & owned:
        raise AppError("Minst én spiller som skal inn er allerede i troppen.")
    if not set(incoming).issubset(set(market.index.astype(int))):
        raise AppError("Minst én spiller som skal inn finnes ikke i markedet.")
    for out_id, in_id in zip(outgoing, incoming):
        if squad.loc[out_id, "position"] != market.loc[in_id, "position"]:
            raise AppError("Hvert bytte må være mellom spillere i samme posisjon.")
        if "can_select" in market and not bool(market.loc[in_id, "can_select"]):
            raise AppError(f"{market.loc[in_id, 'name']} kan ikke velges i FPL nå.")

    sales = sum(int(squad.loc[player_id, "selling_price"]) for player_id in outgoing)
    purchases = sum(int(market.loc[player_id, "price"]) for player_id in incoming)
    calculated_bank = int(team.bank + sales - purchases)
    if mode == "apply_transfers" and calculated_bank < 0:
        raise AppError("Byttene er ikke innenfor tilgjengelig budsjett.")

    holdings = []
    incoming_by_out = dict(zip(outgoing, incoming))
    for row in team.squad.to_dict("records"):
        player_id = int(row["id"])
        if player_id in incoming_by_out:
            new_id = incoming_by_out[player_id]
            holdings.append({
                "id": new_id,
                "purchase_price": int(market.loc[new_id, "price"]),
                "price_is_estimate": False,
            })
        else:
            holdings.append({
                "id": player_id,
                "purchase_price": int(row.get("purchase_price", row["price"])),
                "price_is_estimate": bool(row.get("price_is_estimate", False)),
            })

    before_bank = int(team.bank)
    before_free = int(team.free_transfers)
    if mode == "synchronize":
        if bank is None or free_transfers is None:
            raise AppError("Oppgi faktisk bank og gjenværende gratisbytter etter byttene.")
        new_bank = int(bank)
        new_free_transfers = int(free_transfers)
        hit = 0
    else:
        new_bank = calculated_bank
        new_free_transfers = max(0, before_free - len(changes))
        hit = max(0, len(changes) - before_free) * 4
    if new_bank < 0:
        raise AppError("Banken kan ikke være negativ.")
    if not 0 <= new_free_transfers <= 5:
        raise AppError("Gratisbytter må være mellom 0 og 5.")

    set_team_holdings(team, holdings)
    team.bank = new_bank
    team.free_transfers = new_free_transfers
    team.team_value = int(team.squad["selling_price"].sum() + team.bank)
    recorded = [{
        "out_id": out_id, "out": str(squad.loc[out_id, "name"]),
        "in_id": in_id, "in": str(market.loc[in_id, "name"]),
    } for out_id, in_id in zip(outgoing, incoming)]
    team.squad_source = "manual_override"
    team.manual_changes.extend(recorded)
    return {
        "mode": mode, "changes": recorded, "bank_before": before_bank,
        "bank_after": team.bank, "free_transfers_before": before_free,
        "free_transfers_after": team.free_transfers, "hit": hit,
    }


def _override_path(root: Path, entry_id: int) -> Path:
    return Path(root) / "data" / "local" / "team_overrides" / f"{entry_id}.json"


def save_team_override(root: Path, team: ImportedTeam) -> Path:
    path = _override_path(root, team.entry_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "entry_id": team.entry_id,
        "target_event": team.target_event,
        "bank": team.bank,
        "free_transfers": team.free_transfers,
        "squad_source": team.squad_source,
        "manual_changes": team.manual_changes,
        "holdings": [{
            "id": int(row.id), "purchase_price": int(row.purchase_price),
            "price_is_estimate": bool(getattr(row, "price_is_estimate", False)),
        } for row in team.squad.itertuples()],
    }
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)
    return path


def load_team_override(root: Path, team: ImportedTeam) -> bool:
    path = _override_path(root, team.entry_id)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text())
        if int(payload.get("target_event", -1)) != team.target_event:
            return False
        set_team_holdings(team, payload["holdings"])
        team.bank = int(payload["bank"])
        team.free_transfers = int(payload["free_transfers"])
        team.squad_source = "manual_override"
        team.manual_changes = list(payload.get("manual_changes", []))
        team.team_value = int(team.squad["selling_price"].sum() + team.bank)
        return True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AppError(f"Lagret lagkorrigering er ugyldig: {exc}") from exc


def clear_team_override(root: Path, entry_id: int) -> None:
    path = _override_path(root, entry_id)
    if path.exists():
        path.unlink()


def optimal_lineup(squad: pd.DataFrame) -> dict:
    """Maximise next-GW recommended points under FPL formation rules."""
    if len(squad) != 15:
        raise AppError(f"Forventet 15 spillere, fant {len(squad)}.")
    keepers = squad[squad["position"].eq("GK")]
    outfield = squad[~squad["position"].eq("GK")]
    if len(keepers) != 2:
        raise AppError("Troppen har ikke nøyaktig to keepere.")
    score_column = "decision_points" if "decision_points" in squad else "recommended_points"
    goalkeeper = keepers.sort_values([score_column, "id"], ascending=[False, True]).iloc[0]
    ranked = {
        position: group.sort_values([score_column, "id"], ascending=[False, True])
        for position, group in outfield.groupby("position")
    }
    best_ids, best_score = None, -np.inf
    # Choosing the best N players independently per position is exact for each
    # formation, so only the eight legal formations need evaluation.
    for defenders in range(3, 6):
        for midfielders in range(2, 6):
            forwards = 10 - defenders - midfielders
            if not 1 <= forwards <= 3:
                continue
            chosen = pd.concat([
                ranked.get("DEF", outfield.iloc[:0]).head(defenders),
                ranked.get("MID", outfield.iloc[:0]).head(midfielders),
                ranked.get("FWD", outfield.iloc[:0]).head(forwards),
            ])
            if len(chosen) != 10:
                continue
            score = float(chosen[score_column].sum())
            ids = tuple(sorted(chosen["id"].astype(int)))
            if score > best_score or (score == best_score and (best_ids is None or ids < best_ids)):
                best_ids, best_score = ids, score
    if best_ids is None:
        raise AppError("Fant ingen lovlig startellever i troppen.")
    starters = squad[squad["id"].isin([int(goalkeeper["id"]), *best_ids])].copy()
    starters = starters.sort_values(
        ["position", score_column, "id"],
        key=lambda col: col.map(POSITION_ORDER) if col.name == "position" else col,
        ascending=[True, False, True],
    )
    captain_order = starters.sort_values([score_column, "id"], ascending=[False, True])
    captain_id, vice_id = int(captain_order.iloc[0]["id"]), int(captain_order.iloc[1]["id"])
    starters["role"] = ""
    starters.loc[starters["id"].eq(captain_id), "role"] = "C"
    starters.loc[starters["id"].eq(vice_id), "role"] = "VC"
    bench = squad[~squad["id"].isin(starters["id"])].copy()
    reserve_gk = bench[bench["position"].eq("GK")]
    reserve_outfield = bench[~bench["position"].eq("GK")].sort_values(
        [score_column, "id"], ascending=[False, True]
    )
    bench = pd.concat([reserve_gk, reserve_outfield], ignore_index=True)
    bench["bench_order"] = ["GK", "1", "2", "3"]
    counts = starters["position"].value_counts()
    formation = f"{counts.get('DEF', 0)}-{counts.get('MID', 0)}-{counts.get('FWD', 0)}"
    total = float(starters[score_column].sum() +
                  starters.loc[starters["id"].eq(captain_id), score_column].iloc[0])
    expected_total = float(starters["recommended_points"].sum() +
                           starters.loc[starters["id"].eq(captain_id),
                                        "recommended_points"].iloc[0])
    captain_margin = float(captain_order.iloc[0][score_column] -
                           captain_order.iloc[1][score_column])
    return {"starters": starters, "bench": bench, "formation": formation,
            "captain_id": captain_id, "vice_id": vice_id, "projected_total": total,
            "expected_total": expected_total, "captain_margin": captain_margin,
            "score_column": score_column}


def _lineup_total_records(records: Iterable[tuple[int, str, float]]) -> float:
    """Fast exact lineup score used inside the transfer search."""
    grouped: dict[str, list[tuple[int, float]]] = {position: [] for position in POSITION_ORDER}
    for player_id, position, value in records:
        grouped[position].append((int(player_id), float(value)))
    for values in grouped.values():
        values.sort(key=lambda row: (-row[1], row[0]))
    if not grouped["GK"]:
        return -np.inf
    best = -np.inf
    for defenders in range(3, 6):
        for midfielders in range(2, 6):
            forwards = 10 - defenders - midfielders
            if not 1 <= forwards <= 3:
                continue
            selected = (grouped["GK"][:1] + grouped["DEF"][:defenders] +
                        grouped["MID"][:midfielders] + grouped["FWD"][:forwards])
            if len(selected) != 11:
                continue
            values = [row[1] for row in selected]
            best = max(best, sum(values) + max(values))
    return best


def _exact_transfer_plan(team: ImportedTeam, weekly_source: pd.DataFrame,
                         score_column: str, baseline: float,
                         expected_baseline: float, number: int,
                         forced_outgoing: tuple[int, ...] = ()) -> dict | None:
    """Return the globally optimal exact-N transfer plan over the horizon."""
    frame = team.market.sort_values("id").drop_duplicates("id").reset_index(drop=True)
    ids = frame["id"].astype(int).to_numpy()
    owned = set(team.squad["id"].astype(int))
    owned_mask = np.asarray([player_id in owned for player_id in ids], dtype=float)
    events = sorted(weekly_source["forecast_event"].astype(int).unique())
    n, periods = len(frame), len(events)
    total_variables = n * (1 + 2 * periods)
    data: list[float] = []
    row_indices: list[int] = []
    column_indices: list[int] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(entries: list[tuple[int, float]], lo: float = -np.inf,
            hi: float = np.inf) -> None:
        row = len(lower)
        for column, value in entries:
            if value:
                row_indices.append(row)
                column_indices.append(column)
                data.append(float(value))
        lower.append(float(lo))
        upper.append(float(hi))

    add([(index, 1) for index in range(n)], 15, 15)
    retained = 15 - number
    add([(index, owned_mask[index]) for index in range(n)], retained, retained)
    index_by_id = {int(player_id): index for index, player_id in enumerate(ids)}
    for player_id in forced_outgoing:
        add([(index_by_id[player_id], 1)], 0, 0)
    for position, count in {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}.items():
        add([(index, 1) for index in range(n)
             if frame.loc[index, "position"] == position], count, count)
    for team_id in sorted(frame["team_id"].unique()):
        add([(index, 1) for index in range(n)
             if frame.loc[index, "team_id"] == team_id], hi=3)

    sale_by_id = team.squad.set_index("id")["selling_price"].astype(int).to_dict()
    cash_coefficients = [
        sale_by_id[player_id] if player_id in owned else int(frame.loc[index, "price"])
        for index, player_id in enumerate(ids)
    ]
    cash_available = int(team.bank + sum(sale_by_id.values()))
    add([(index, value) for index, value in enumerate(cash_coefficients)],
        hi=cash_available)

    position_limits = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
    decision_scores: dict[int, np.ndarray] = {}
    expected_scores: dict[int, np.ndarray] = {}
    for period, event in enumerate(events):
        event_rows = weekly_source[weekly_source["forecast_event"].eq(event)].set_index("id")
        decision_scores[event] = event_rows[score_column].reindex(ids).fillna(0).to_numpy(float)
        expected_scores[event] = event_rows["recommended_points"].reindex(ids).fillna(0).to_numpy(float)
        starter_offset = n * (1 + 2 * period)
        captain_offset = starter_offset + n
        add([(starter_offset + index, 1) for index in range(n)], 11, 11)
        for position, (minimum, maximum) in position_limits.items():
            add([(starter_offset + index, 1) for index in range(n)
                 if frame.loc[index, "position"] == position], minimum, maximum)
        add([(captain_offset + index, 1) for index in range(n)], 1, 1)
        for index in range(n):
            add([(index, -1), (starter_offset + index, 1)], hi=0)
            add([(starter_offset + index, -1), (captain_offset + index, 1)], hi=0)

    matrix = csr_matrix(
        (data, (row_indices, column_indices)),
        shape=(len(lower), total_variables),
    )
    objective = np.zeros(total_variables)
    for period, event in enumerate(events):
        starter_offset = n * (1 + 2 * period)
        captain_offset = starter_offset + n
        objective[starter_offset:starter_offset + n] = -decision_scores[event]
        objective[captain_offset:captain_offset + n] = -decision_scores[event]
    result = milp(
        objective,
        integrality=np.ones(total_variables, dtype=np.uint8),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)),
        options={"time_limit": 20},
    )
    if result.status == 2:
        return None
    if not result.success or result.x is None:
        raise AppError(f"Eksakt {number}-bytteoptimering feilet: {result.message}")

    primary_row = csr_matrix(objective.reshape(1, -1))
    secondary_matrix = vstack([matrix, primary_row], format="csr")
    secondary_lower = np.concatenate([np.asarray(lower), [-np.inf]])
    secondary_upper = np.concatenate([np.asarray(upper), [float(result.fun) + 1e-8]])
    cash_objective = np.zeros(total_variables)
    cash_objective[:n] = np.asarray(cash_coefficients, dtype=float)
    cash_objective[:n] += 1e-7 * np.where(owned_mask > 0, -ids, ids)
    secondary = milp(
        cash_objective,
        integrality=np.ones(total_variables, dtype=np.uint8),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(
            secondary_matrix, secondary_lower, secondary_upper
        ),
        options={"time_limit": 20},
    )
    if secondary.success and secondary.x is not None:
        result = secondary

    selected = set(ids[result.x[:n] > .5].astype(int))
    outgoing = tuple(sorted(owned - selected))
    incoming = tuple(sorted(selected - owned))
    if len(outgoing) != number or len(incoming) != number:
        raise AppError(f"Eksakt optimering ga ikke {number} bytter.")
    market_by_id = frame.set_index("id")
    squad_by_id = team.squad.set_index("id")
    new_total = sum(_lineup_total_records(
        record for player_id, record in lookup.items() if player_id in selected
    ) for lookup in {
        event: {
            int(player_id): (int(player_id), str(market_by_id.loc[player_id, "position"]), score)
            for player_id, score in zip(ids, decision_scores[event])
        }
        for event in events
    }.values())
    expected_total = sum(_lineup_total_records(
        (int(player_id), str(market_by_id.loc[player_id, "position"]), score)
        for player_id, score in zip(ids, expected_scores[event]) if player_id in selected
    ) for event in events)
    cost = sum(int(market_by_id.loc[player_id, "price"]) for player_id in incoming)
    budget = team.bank + sum(int(squad_by_id.loc[player_id, "selling_price"])
                             for player_id in outgoing)
    hit = max(0, number - team.free_transfers) * 4
    return {
        "out": " + ".join(str(squad_by_id.loc[x, "name"]) for x in outgoing),
        "in": " + ".join(str(market_by_id.loc[x, "name"]) for x in incoming),
        "cost": cost / 10,
        "money_left": (budget - cost) / 10,
        "lineup_gain": new_total - baseline,
        "expected_gain": expected_total - expected_baseline,
        "hit": hit,
        "net_gain": new_total - baseline - hit,
        "expected_net_gain": expected_total - expected_baseline - hit,
        "projected_total": new_total - hit,
        "is_global_optimum": True,
        "_plan_key": (outgoing, incoming),
    }


def recommend_transfers(team: ImportedTeam, number: int = 1, limit: int = 8,
                        candidate_pool: int = 14,
                        forced_outgoing: Iterable[int] | None = None) -> pd.DataFrame:
    """Rank legal transfer plans by lineup gain over the horizon.

    One-transfer search is exhaustive. For two transfers, the global optimum
    is supplemented with shortlist alternatives. Three-to-five transfers use
    the exact joint MILP and return its global optimum.
    """
    if number not in range(1, 6):
        raise AppError("Antall bytter må være mellom ett og fem.")
    squad, market = team.squad, team.market
    owned = set(squad["id"].astype(int))
    raw_forced = tuple(int(player_id) for player_id in (forced_outgoing or ()))
    forced = tuple(dict.fromkeys(raw_forced))
    if len(forced) != len(raw_forced):
        raise AppError("Samme spiller kan ikke velges flere ganger.")
    if forced and len(forced) != number:
        raise AppError("Antall valgte spillere må være likt antall bytter.")
    unknown = set(forced) - owned
    if unknown:
        raise AppError("Alle valgte spillere må finnes i den aktive troppen.")
    weekly_source = team.weekly_market if team.weekly_market is not None else market.assign(
        forecast_event=team.target_event
    )
    score_column = ("decision_points" if "decision_points" in weekly_source
                    else "recommended_points")
    def records_for(column: str) -> dict[int, dict[int, tuple[int, str, float]]]:
        return {
            int(event): {
                int(row.id): (int(row.id), str(row.position), float(getattr(row, column)))
                for row in group.itertuples()
            }
            for event, group in weekly_source.groupby("forecast_event")
        }
    weekly_records = records_for(score_column)
    expected_records = records_for("recommended_points")
    baseline = sum(_lineup_total_records(
        record for player_id, record in lookup.items() if player_id in owned
    ) for lookup in weekly_records.values())
    expected_baseline = sum(_lineup_total_records(
        record for player_id, record in lookup.items() if player_id in owned
    ) for lookup in expected_records.values())
    if number >= 3:
        exact_plan = _exact_transfer_plan(
            team, weekly_source, score_column, baseline, expected_baseline, number,
            forced,
        )
        if exact_plan is None:
            return pd.DataFrame(columns=[
                "out", "in", "cost", "money_left", "lineup_gain",
                "expected_gain", "hit", "net_gain", "expected_net_gain",
                "projected_total", "is_global_optimum",
            ])
        return pd.DataFrame([exact_plan]).drop(columns="_plan_key")
    available = market[~market["id"].isin(owned)].copy()
    pools = {}
    for position, group in available.groupby("position"):
        ranked = group.sort_values(["recommended_points", "price", "id"],
                                   ascending=[False, True, True])
        if number == 1:
            pools[position] = ranked
            continue
        diversity = max(4, candidate_pool // 2)
        cheapest = group.sort_values(["price", "recommended_points", "id"],
                                     ascending=[True, False, True]).head(diversity)
        club_best = ranked.groupby("team_id", sort=False).head(1).head(diversity)
        keep_ids = pd.concat([
            ranked.head(candidate_pool)["id"], cheapest["id"], club_best["id"]
        ]).drop_duplicates()
        pools[position] = ranked[ranked["id"].isin(keep_ids)]
    if forced:
        outgoing_sets = [forced]
    elif number == 1:
        outgoing_sets = [(int(row.id),) for row in squad.itertuples()]
    else:
        outgoing_sets = [
            tuple(int(x) for x in pair)
            for pair in combinations(squad["id"].astype(int), 2)
        ]
    by_id = squad.set_index("id")
    market_by_id = market.set_index("id")
    club_counts = Counter(int(team_id) for team_id in squad["team_id"])
    results, seen = [], set()
    for outgoing in outgoing_sets:
        positions = [by_id.loc[player_id, "position"] for player_id in outgoing]
        if any(position not in pools for position in positions):
            continue
        budget = team.bank + sum(int(by_id.loc[player_id, "selling_price"]) for player_id in outgoing)
        if number == 1:
            incoming_options = ((int(player_id),) for player_id in pools[positions[0]]["id"])
        elif positions[0] == positions[1]:
            incoming_options = combinations(pools[positions[0]]["id"].astype(int), 2)
        else:
            incoming_options = product(pools[positions[0]]["id"].astype(int),
                                       pools[positions[1]]["id"].astype(int))
        for incoming_raw in incoming_options:
            incoming = tuple(int(x) for x in incoming_raw)
            key = (tuple(sorted(outgoing)), tuple(sorted(incoming)))
            if key in seen or len(set(incoming)) != number:
                continue
            seen.add(key)
            cost = sum(int(market_by_id.loc[player_id, "price"]) for player_id in incoming)
            if cost > budget:
                continue
            proposed_clubs = club_counts.copy()
            for player_id in outgoing:
                proposed_clubs[int(by_id.loc[player_id, "team_id"])] -= 1
            for player_id in incoming:
                proposed_clubs[int(market_by_id.loc[player_id, "team_id"])] += 1
            if any(count > 3 for count in proposed_clubs.values()):
                continue
            proposed_ids = (owned - set(outgoing)) | set(incoming)
            new_total = sum(_lineup_total_records(
                record for player_id, record in lookup.items() if player_id in proposed_ids
            ) for lookup in weekly_records.values())
            expected_total = sum(_lineup_total_records(
                record for player_id, record in lookup.items() if player_id in proposed_ids
            ) for lookup in expected_records.values())
            gain = new_total - baseline
            expected_gain = expected_total - expected_baseline
            hit = max(0, number - team.free_transfers) * 4
            results.append({
                "out": " + ".join(str(by_id.loc[x, "name"]) for x in outgoing),
                "in": " + ".join(str(market_by_id.loc[x, "name"]) for x in incoming),
                "cost": cost / 10,
                "money_left": (budget - cost) / 10,
                "lineup_gain": gain,
                "expected_gain": expected_gain,
                "hit": hit,
                "net_gain": gain - hit,
                "expected_net_gain": expected_gain - hit,
                "projected_total": new_total - hit,
                "is_global_optimum": number == 1,
                "_plan_key": (tuple(sorted(outgoing)), tuple(sorted(incoming))),
            })
    if number == 2:
        exact_plan = _exact_transfer_plan(
            team, weekly_source, score_column, baseline, expected_baseline, number,
            forced,
        )
        if exact_plan is not None:
            results.append(exact_plan)
    if not results:
        return pd.DataFrame(columns=["out", "in", "cost", "money_left", "lineup_gain",
                                     "expected_gain", "hit", "net_gain", "expected_net_gain",
                                     "projected_total", "is_global_optimum"])
    ranked = pd.DataFrame(results).sort_values(
        ["net_gain", "lineup_gain", "is_global_optimum", "money_left", "in"],
        ascending=[False, False, False, False, True],
    ).drop_duplicates("_plan_key").head(limit).reset_index(drop=True)
    return ranked.drop(columns="_plan_key")


def transfer_targets(team: ImportedTeam, position: str | None = None,
                     max_price: int | None = None, limit: int = 12) -> pd.DataFrame:
    targets = team.market[~team.market["id"].isin(team.squad["id"])].copy()
    if position:
        targets = targets[targets["position"].eq(position.upper())]
    if max_price is not None:
        targets = targets[targets["price"].le(max_price)]
    score_column = "decision_points" if "decision_points" in targets else "recommended_points"
    return targets.sort_values(
        [score_column, "price", "id"], ascending=[False, True, True]
    ).head(limit)


def sell_candidates(team: ImportedTeam, limit: int = 8) -> pd.DataFrame:
    score_column = ("decision_points" if "decision_points" in team.squad
                    else "recommended_points")
    return team.squad.sort_values(
        [score_column, "selling_price", "id"], ascending=[True, False, True]
    ).head(limit)


def money(value: int | float) -> str:
    return f"£{float(value) / 10:.1f}m"


def points(value: float) -> str:
    return f"{float(value):.2f}"


def print_table(frame: pd.DataFrame, columns: list[tuple[str, str, object]]) -> None:
    if frame.empty:
        print("Ingen gyldige forslag funnet.")
        return
    shown = pd.DataFrame()
    for source, title, formatter in columns:
        shown[title] = frame[source].map(formatter) if formatter else frame[source].astype(str)
    print(shown.to_string(index=False))


def show_overview(team: ImportedTeam) -> None:
    estimate = " (estimat fra offentlig historikk)"
    print(f"\n{team.manager_name} – {team.team_name} | importert fra GW{team.event}")
    target_label = (f"GW{team.target_event}" if team.horizon == 1 else
                    f"GW{team.target_event}–{team.target_event + team.horizon - 1}")
    print(f"Modellmål: {target_label} | neste frist {team.deadline}")
    print(f"Risikoprofil: {team.risk_profile}")
    print(f"Bank: {money(team.bank)} | gratisbytter: ca. {team.free_transfers}{estimate}")
    print(f"Prognose: {team.forecast_path}")
    columns = [
        ("position", "Pos", None), ("name", "Spiller", None), ("team", "Lag", None),
        ("opponent", "Motstander", None), ("selling_price", "Salgspris*", money),
        ("recommended_points", "Anb. poeng", points),
    ]
    if team.risk_profile != "balanced":
        columns.append(("decision_points", "Profilscore", points))
    if "recommended_q10" in team.squad and team.squad["recommended_q10"].notna().any():
        columns.append(("point_range_q10_q90", "Q10–Q90*", None))
    if team.squad["expected_60plus_appearances"].notna().any():
        title = "P(60+)" if team.horizon == 1 else "Forv. 60+"
        formatter = ((lambda x: f"{100 * x:.0f}%") if team.horizon == 1 else points)
        columns.append(("expected_60plus_appearances", title, formatter))
    columns.append(("status", "Status", None))
    score_column = ("decision_points" if "decision_points" in team.squad
                    else "recommended_points")
    print_table(team.squad.sort_values(["position", score_column],
                                      key=lambda col: col.map(POSITION_ORDER) if col.name == "position" else col,
                                      ascending=[True, False]), columns)
    print("* estimert fra offentlig kjøpshistorikk og FPLs salgsprisregel")
    if "recommended_q10" in team.squad and team.squad["recommended_q10"].notna().any():
        print("* Q10–Q90 er modellkvantiler, ikke et garantert konfidensintervall")


def show_lineup(team: ImportedTeam) -> None:
    lineup = optimal_lineup(team.lineup_squad if team.lineup_squad is not None else team.squad)
    print(f"\nAnbefalt startellever GW{team.target_event}: {lineup['formation']}")
    columns = [
        ("position", "Pos", None), ("name", "Spiller", None), ("team", "Lag", None),
        ("opponent", "Motstander", None), ("recommended_points", "Anb. poeng", points),
    ]
    if team.risk_profile != "balanced":
        columns.append(("decision_points", "Profilscore", points))
    if ("expected_60plus_appearances" in lineup["starters"] and
            lineup["starters"]["expected_60plus_appearances"].notna().any()):
        columns.append(("expected_60plus_appearances", "P(60+)", lambda x: f"{100 * x:.0f}%"))
    if ("recommended_q10" in lineup["starters"] and
            lineup["starters"]["recommended_q10"].notna().any()):
        columns.append(("point_range_q10_q90", "Q10–Q90", None))
    columns.append(("role", "Rolle", None))
    print_table(lineup["starters"], columns)
    print(f"Forventet startellever inkl. kapteinsdobling: {lineup['expected_total']:.2f}")
    if team.risk_profile != "balanced":
        print(f"{team.risk_profile}-profilscore inkl. kaptein: {lineup['projected_total']:.2f}")
        print("Profilscore er en eksplorativ nyttefunksjon, ikke forventede FPL-poeng.")
    if lineup["captain_margin"] < 0.5:
        unit = "poeng" if team.risk_profile == "balanced" else "profilpoeng"
        print(f"Kapteinvalget har lav modellmargin ({lineup['captain_margin']:.2f} {unit}); "
              "behandle C/VC som et usikkert valg.")
    print("\nBenk (keeper, deretter innbytterrekkefølge):")
    bench_columns = [
        ("bench_order", "Rekkefølge", None), ("position", "Pos", None),
        ("name", "Spiller", None), ("recommended_points", "Anb. poeng", points),
    ]
    if team.risk_profile != "balanced":
        bench_columns.append(("decision_points", "Profilscore", points))
    if ("expected_60plus_appearances" in lineup["bench"] and
            lineup["bench"]["expected_60plus_appearances"].notna().any()):
        bench_columns.append(
            ("expected_60plus_appearances", "P(60+)", lambda x: f"{100 * x:.0f}%")
        )
    if ("recommended_q10" in lineup["bench"] and
            lineup["bench"]["recommended_q10"].notna().any()):
        bench_columns.append(("point_range_q10_q90", "Q10–Q90", None))
    print_table(lineup["bench"], bench_columns)


def show_transfers(team: ImportedTeam, number: int = 1) -> None:
    suggestions = recommend_transfers(team, number=number)
    print(f"\nBeste lovlige forslag med {number} bytte{'r' if number > 1 else ''}:")
    columns = [
        ("out", "Selg", None), ("in", "Kjøp", None), ("cost", "Kjøpspris", lambda x: f"£{x:.1f}m"),
        ("money_left", "Rest", lambda x: f"£{x:.1f}m"),
    ]
    if team.risk_profile == "balanced":
        gain_label = "GW-gevinst" if team.horizon == 1 else "Horisontgevinst"
        columns.append(("lineup_gain", gain_label, points))
    else:
        columns.extend([
            ("expected_gain", "Forv. gevinst", points),
            ("lineup_gain", "Profilgevinst", points),
        ])
    columns.extend([
        ("hit", "Hit", lambda x: str(int(x))), ("net_gain", "Netto", points),
    ])
    print_table(suggestions, columns)
    if not suggestions.empty and suggestions.iloc[0]["net_gain"] <= 0:
        print("Modellen foretrekker å spare byttet: ingen plan har positiv netto profilgevinst.")
    else:
        label = "neste Gameweek" if team.horizon == 1 else f"de neste {team.horizon} Gameweekene"
        print(f"Merk: rangeringen summerer {label}; den modellerer ikke prisendringer senere i perioden.")
        if team.risk_profile != "balanced":
            print("Profilgevinst er en eksplorativ nytteverdi, ikke forventede FPL-poeng.")
        if number >= 2:
            print(f"Første {number}-bytteforslag er globalt optimalt under modellscore og valgte Gameweeks.")
            if number == 2:
                print("De øvrige forslagene kommer fra en bred, modellrangert kandidatliste.")


def show_multiweek(team: ImportedTeam) -> None:
    from multiweek_planner import plan_multiweek

    result = plan_multiweek(team, weeks=team.horizon)
    print(f'\nGlobal flerukersplan: {result["total_projected_points"]:.2f} modellpoeng')
    for week in result["weeks"]:
        outgoing = ", ".join(week["transfers_out"]) or "ingen"
        incoming = ", ".join(week["transfers_in"]) or "ingen"
        print(
            f'GW{week["event"]} | {week["formation"]} | '
            f'{week["projected_points"]:.2f} | UT: {outgoing} | INN: {incoming} | '
            f'C: {week["captain"]} | bank £{week["bank"]:.1f}m | hit {week["hit"]}'
        )
        print("  XI: " + ", ".join(week["starters"]))
    print(result["caveat"])


def show_targets(team: ImportedTeam, position: str | None = None,
                 max_price: int | None = None) -> None:
    print("\nBeste kjøpskandidater etter anbefalte poeng:")
    targets = transfer_targets(team, position, max_price)
    columns = [
        ("position", "Pos", None), ("name", "Spiller", None), ("team", "Lag", None),
        ("opponent", "Motstander", None), ("price", "Pris", money),
        ("recommended_points", "Anb. poeng", points),
    ]
    if team.risk_profile != "balanced":
        columns.append(("decision_points", "Profilscore", points))
    if targets["expected_60plus_appearances"].notna().any():
        title = "P(60+)" if team.horizon == 1 else "Forv. 60+"
        formatter = ((lambda x: f"{100 * x:.0f}%") if team.horizon == 1 else points)
        columns.append(("expected_60plus_appearances", title, formatter))
    if "recommended_q10" in targets and targets["recommended_q10"].notna().any():
        columns.append(("point_range_q10_q90", "Q10–Q90", None))
    columns.append(("status", "Status", None))
    print_table(targets, columns)


def show_sells(team: ImportedTeam) -> None:
    print("\nSalgskandidater (lavest neste-GW-prognose først):")
    columns = [
        ("position", "Pos", None), ("name", "Spiller", None),
        ("selling_price", "Salgspris*", money), ("recommended_points", "Anb. poeng", points),
    ]
    if team.risk_profile != "balanced":
        columns.append(("decision_points", "Profilscore", points))
    columns.extend([("opponent", "Motstander", None), ("status", "Status", None)])
    print_table(sell_candidates(team), columns)
    print("* estimert fra offentlig kjøpshistorikk og FPLs salgsprisregel")


def interactive(team: ImportedTeam) -> None:
    actions = {
        "1": ("Vis laget", lambda: show_overview(team)),
        "2": ("Anbefal startellever, kaptein og benk", lambda: show_lineup(team)),
        "3": ("Anbefal ett bytte", lambda: show_transfers(team, 1)),
        "4": ("Anbefal to bytter", lambda: show_transfers(team, 2)),
        "5": ("Vis kjøpskandidater", lambda: show_targets(team)),
        "6": ("Vis salgskandidater", lambda: show_sells(team)),
        "7": ("Lag global flerukersplan", lambda: show_multiweek(team)),
    }
    show_overview(team)
    while True:
        print("\nHva vil du gjøre?")
        for key, (label, _) in actions.items():
            print(f"  {key}. {label}")
        print("  q. Avslutt")
        choice = input("> ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            return
        action = actions.get(choice)
        print("Ugyldig valg.") if action is None else action[1]()


def refresh_forecast(root: Path) -> None:
    from capture_fpl import run
    path = run(root)
    if path is None:
        raise AppError("Oppdateringen ble hoppet over fordi en annen innhenting kjører.")
    try:
        manifest = json.loads((path / "manifest.json").read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AppError("Oppdateringen mangler et gyldig manifest.") from exc
    if manifest.get("status") != "complete":
        detail = manifest.get("error", "ukjent feil")
        raise AppError(f"Oppdateringen feilet: {detail}")
    if manifest.get("forecast_status") != "experimental_frozen":
        status = manifest.get("forecast_status", "ukjent status")
        raise AppError(f"Snapshot ble hentet, men ingen gyldig prognose ble laget ({status}).")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("team", help="FPL-lenke eller numerisk lag-ID")
    parser.add_argument("--action", choices=["interactive", "overview", "lineup", "transfers", "plan", "targets", "sells"],
                        default="interactive")
    parser.add_argument("--max-transfers", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--position", choices=list(POSITION_ORDER))
    parser.add_argument("--max-price", type=float, help="Maks kjøpspris i millioner")
    parser.add_argument("--horizon", type=int, choices=range(1, 9), default=1,
                        help="Gameweeks som summeres for kjøp/salg (standard: 1)")
    parser.add_argument("--risk-profile", choices=["balanced", "stable", "upside"],
                        default="balanced",
                        help="Beslutningsprofil: forventning, nedside eller oppside")
    parser.add_argument("--refresh", action="store_true", help="Hent ferske data og lag prognose først")
    parser.add_argument("--root", type=Path, default=root, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.refresh:
            refresh_forecast(args.root)
        team = import_team(
            args.team, args.root, horizon=args.horizon, risk_profile=args.risk_profile
        )
        actions = {
            "overview": lambda: show_overview(team),
            "lineup": lambda: show_lineup(team),
            "transfers": lambda: show_transfers(team, args.max_transfers),
            "plan": lambda: show_multiweek(team),
            "targets": lambda: show_targets(
                team, args.position, round(args.max_price * 10) if args.max_price is not None else None
            ),
            "sells": lambda: show_sells(team),
            "interactive": lambda: interactive(team),
        }
        actions[args.action]()
        return 0
    except (AppError, KeyboardInterrupt) as exc:
        print(f"Feil: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
