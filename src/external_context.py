"""Pure normalization for optional odds and non-league schedule sources."""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import poisson


ALIASES = {
    "manchesterunited": "manutd",
    "manchesterunitedfc": "manutd",
    "manunited": "manutd",
    "manchestercity": "mancity",
    "manchestercityfc": "mancity",
    "tottenhamhotspur": "spurs",
    "tottenhamhotspurfc": "spurs",
    "tottenham": "spurs",
    "sheffieldunited": "sheffieldutd",
    "nottinghamforest": "nottmforest",
    "nottinghamforestfc": "nottmforest",
    "brightonhovealbion": "brighton",
    "brightonandhovealbion": "brighton",
    "brightonhovealbionfc": "brighton",
    "wolverhamptonwanderers": "wolves",
    "wolverhamptonwanderersfc": "wolves",
    "westhamunited": "westham",
    "westhamunitedfc": "westham",
    "newcastleunited": "newcastle",
    "newcastleunitedfc": "newcastle",
    "leedsunited": "leeds",
    "leedsunitedfc": "leeds",
    "sunderlandafc": "sunderland",
    "crystalpalacefc": "crystalpalace",
    "afcbournemouth": "bournemouth",
}


def team_key(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", "and")
    key = re.sub(r"[^a-z0-9]", "", text)
    return ALIASES.get(key, key.removesuffix("fc"))


def fpl_team_lookup(bootstrap: dict) -> dict[str, int]:
    result = {}
    for team in bootstrap.get("teams", []):
        for value in [team.get("name"), team.get("short_name")]:
            if value:
                result[team_key(value)] = int(team["id"])
    return result


def _team_id(team: dict, lookup: dict[str, int]) -> int | None:
    for field in ["name", "shortName", "tla"]:
        key = team_key(team.get(field))
        if key in lookup:
            return lookup[key]
    return None


def cross_competition_features(bootstrap: dict, payload: dict | None,
                               observed_at) -> dict[int, dict]:
    """Aggregate non-PL workload known at the snapshot timestamp."""
    lookup = fpl_team_lookup(bootstrap)
    current = pd.Timestamp(observed_at)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    events: dict[int, list[pd.Timestamp]] = {int(t["id"]): [] for t in bootstrap.get("teams", [])}
    cl_events: dict[int, list[pd.Timestamp]] = {
        int(t["id"]): [] for t in bootstrap.get("teams", [])
    }
    for match in (payload or {}).get("matches", []):
        competition = (match.get("competition") or {}).get("code")
        if competition in {"PL", "ENGLAND_PL"}:
            continue
        kickoff = pd.to_datetime(match.get("utcDate"), utc=True, errors="coerce")
        if pd.isna(kickoff):
            continue
        for side in ["homeTeam", "awayTeam"]:
            team_id = _team_id(match.get(side) or {}, lookup)
            if team_id is not None:
                events.setdefault(team_id, []).append(kickoff)
                if competition == "CL":
                    cl_events.setdefault(team_id, []).append(kickoff)
    features = {}
    for team_id, times in events.items():
        past = [value for value in times if value < current]
        future = [value for value in times if value >= current]
        cl_past = [value for value in cl_events.get(team_id, []) if value < current]
        features[team_id] = {
            "non_pl_matches_last7": sum(value >= current - pd.Timedelta(days=7) for value in past),
            "non_pl_matches_last14": sum(value >= current - pd.Timedelta(days=14) for value in past),
            "non_pl_matches_next7": sum(value <= current + pd.Timedelta(days=7) for value in future),
            "days_since_non_pl_match": (
                (current - max(past)).total_seconds() / 86400 if past else np.nan
            ),
            "days_to_non_pl_match": (
                (min(future) - current).total_seconds() / 86400 if future else np.nan
            ),
            "cl_matches_last7": sum(
                value >= current - pd.Timedelta(days=7) for value in cl_past
            ),
            "cl_matches_last14": sum(
                value >= current - pd.Timedelta(days=14) for value in cl_past
            ),
            "days_since_cl_match": (
                (current - max(cl_past)).total_seconds() / 86400 if cl_past else np.nan
            ),
        }
    return features


def _market_probabilities(event: dict) -> dict:
    h2h, totals, bookmaker_count = [], [], 0
    home_key, away_key = team_key(event.get("home_team")), team_key(event.get("away_team"))
    for bookmaker in event.get("bookmakers", []):
        bookmaker_count += 1
        for market in bookmaker.get("markets", []):
            outcomes = market.get("outcomes", [])
            if market.get("key") == "h2h":
                raw = {}
                for outcome in outcomes:
                    key = team_key(outcome.get("name"))
                    if key == home_key:
                        raw["home"] = 1 / float(outcome["price"])
                    elif key == away_key:
                        raw["away"] = 1 / float(outcome["price"])
                    elif str(outcome.get("name", "")).lower() == "draw":
                        raw["draw"] = 1 / float(outcome["price"])
                if len(raw) == 3:
                    total = sum(raw.values())
                    h2h.append({key: value / total for key, value in raw.items()})
            elif market.get("key") == "totals":
                raw = {str(outcome.get("name", "")).lower(): 1 / float(outcome["price"])
                       for outcome in outcomes if float(outcome.get("point", 0)) == 2.5}
                if {"over", "under"}.issubset(raw):
                    totals.append(raw["over"] / (raw["over"] + raw["under"]))
    result = {
        "market_home_win_probability": np.mean([row["home"] for row in h2h]) if h2h else np.nan,
        "market_draw_probability": np.mean([row["draw"] for row in h2h]) if h2h else np.nan,
        "market_away_win_probability": np.mean([row["away"] for row in h2h]) if h2h else np.nan,
        "market_over25_probability": np.mean(totals) if totals else np.nan,
        "market_bookmakers": bookmaker_count,
    }
    result.update(_implied_goal_model(result))
    return result


def _poisson_outcomes(home_goals: float, away_goals: float) -> dict[str, float]:
    """Return 1X2 and O2.5 probabilities for independent Poisson goal rates."""
    values = np.arange(0, 13)
    home = poisson.pmf(values, home_goals)
    away = poisson.pmf(values, away_goals)
    score = np.outer(home, away)
    return {
        "home": float(np.tril(score, -1).sum()),
        "draw": float(np.trace(score)),
        "away": float(np.triu(score, 1).sum()),
        "over25": float(sum(
            score[i, j] for i in range(len(values)) for j in range(len(values))
            if i + j >= 3
        )),
    }


def _implied_goal_model(probabilities: dict) -> dict[str, float]:
    """Fit two goal rates to de-vigged 1X2 and total-goals consensus.

    The two rates make clean-sheet probabilities internally consistent with
    the same market view used for win and scoring expectations. They are not
    treated as observed outcomes or silently substituted for model features.
    """
    targets = {
        "home": probabilities.get("market_home_win_probability"),
        "draw": probabilities.get("market_draw_probability"),
        "away": probabilities.get("market_away_win_probability"),
        "over25": probabilities.get("market_over25_probability"),
    }
    available = {key: float(value) for key, value in targets.items() if np.isfinite(value)}
    if len(available) < 2:
        return {
            "market_home_expected_goals": np.nan,
            "market_away_expected_goals": np.nan,
            "market_home_clean_sheet_probability": np.nan,
            "market_away_clean_sheet_probability": np.nan,
        }

    def residual(log_rates):
        estimated = _poisson_outcomes(*np.exp(log_rates))
        return np.asarray([estimated[key] - value for key, value in available.items()])

    fit = least_squares(
        residual, np.log([1.55, 1.20]), bounds=(np.log(.05), np.log(6.0)),
        max_nfev=200,
    )
    home_goals, away_goals = np.exp(fit.x)
    return {
        "market_home_expected_goals": float(home_goals),
        "market_away_expected_goals": float(away_goals),
        "market_home_clean_sheet_probability": float(np.exp(-away_goals)),
        "market_away_clean_sheet_probability": float(np.exp(-home_goals)),
    }


def add_odds_to_schedule(schedule: pd.DataFrame, bootstrap: dict,
                         payload: list | None) -> pd.DataFrame:
    """Join de-vigged bookmaker consensus to the matching FPL fixture."""
    result = schedule.copy()
    columns = [
        "market_home_win_probability", "market_draw_probability",
        "market_away_win_probability", "market_over25_probability", "market_bookmakers",
        "market_home_expected_goals", "market_away_expected_goals",
        "market_home_clean_sheet_probability", "market_away_clean_sheet_probability",
    ]
    for column in columns:
        result[column] = np.nan
    result["odds_event_id"] = None
    lookup = fpl_team_lookup(bootstrap)
    for event in payload or []:
        home = lookup.get(team_key(event.get("home_team")))
        away = lookup.get(team_key(event.get("away_team")))
        kickoff = pd.to_datetime(event.get("commence_time"), utc=True, errors="coerce")
        if home is None or away is None or pd.isna(kickoff):
            continue
        schedule_time = pd.to_datetime(result["kickoff_time"], utc=True, errors="coerce")
        mask = (result.team_h.eq(home) & result.team_a.eq(away)
                & schedule_time.sub(kickoff).abs().le(pd.Timedelta(hours=12)))
        if mask.sum() != 1:
            continue
        probabilities = _market_probabilities(event)
        for column, value in probabilities.items():
            result.loc[mask, column] = value
        result.loc[mask, "odds_event_id"] = str(event.get("id", ""))
    return result


def _binary_prop_probability(market: dict) -> dict[str, float]:
    """De-vig Yes/No or Over/Under 0.5 player props by player name."""
    grouped: dict[str, dict[str, float]] = {}
    for outcome in market.get("outcomes", []):
        description = outcome.get("description") or outcome.get("player")
        if not description:
            continue
        name = team_key(description)
        side = str(outcome.get("name", "")).lower()
        if side in {"yes", "over"}:
            label = "yes"
        elif side in {"no", "under"}:
            label = "no"
        else:
            continue
        if side in {"over", "under"} and float(outcome.get("point", .5)) != .5:
            continue
        price = float(outcome.get("price", 0))
        if price > 1:
            grouped.setdefault(name, {})[label] = 1 / price
    result = {}
    for name, raw in grouped.items():
        if {"yes", "no"}.issubset(raw):
            result[name] = raw["yes"] / (raw["yes"] + raw["no"])
    return result


def player_prop_probabilities(payload: list | None) -> dict[str, dict[str, float]]:
    """Aggregate bookmaker consensus for anytime goal and 0.5 assist props."""
    samples: dict[str, dict[str, list[float]]] = {}
    for event in payload or []:
        fixture_key = str(event.get("id", ""))
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                key = market.get("key")
                if key not in {"player_goal_scorer_anytime", "player_assists"}:
                    continue
                label = "goal" if key == "player_goal_scorer_anytime" else "assist"
                for player, value in _binary_prop_probability(market).items():
                    samples.setdefault(fixture_key, {}).setdefault(
                        f"{player}:{label}", []
                    ).append(value)
    result: dict[str, dict[str, float]] = {}
    for fixture_key, values in samples.items():
        result[fixture_key] = {
            label: float(np.mean(observations))
            for label, observations in values.items()
        }
    return result


def add_player_props_to_schedule(schedule: pd.DataFrame, payload: list | None) -> pd.DataFrame:
    """Attach per-player prop maps to schedule rows using provider event ids."""
    result = schedule.copy()
    prop_maps = player_prop_probabilities(payload)
    result["market_player_props"] = [
        prop_maps.get(str(value), {}) for value in result.get("odds_event_id", pd.Series(index=result.index))
    ]
    return result


def enrich_registry_with_workload(registry: pd.DataFrame, bootstrap: dict,
                                  payload: dict | None, observed_at) -> pd.DataFrame:
    result = registry.copy()
    features = cross_competition_features(bootstrap, payload, observed_at)
    names = [
        "non_pl_matches_last7", "non_pl_matches_last14", "non_pl_matches_next7",
        "days_since_non_pl_match", "days_to_non_pl_match",
        "cl_matches_last7", "cl_matches_last14", "days_since_cl_match",
    ]
    for name in names:
        result[name] = result.team.map(lambda team: features.get(int(team), {}).get(name, np.nan))
    return result
