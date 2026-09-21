"""Historical pre-closing EPL odds and leak-safe player-fixture features.

Football-Data publishes two odds sets from 2019/20 onwards.  Columns without
the extra ``C`` are the earlier, pre-closing observations; closing columns are
deliberately excluded because they can be newer than the FPL deadline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
import requests

from external_context import _implied_goal_model, team_key


SEASON_CODES = {
    "2020-21": "2021",
    "2021-22": "2122",
    "2022-23": "2223",
    "2023-24": "2324",
    "2024-25": "2425",
    "2025-26": "2526",
}
SOURCE_URL = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"
ODDS_COLUMNS = ["AvgH", "AvgD", "AvgA", "Avg>2.5", "Avg<2.5"]
MARKET_FEATURES = [
    "market_team_win_probability",
    "market_draw_probability",
    "market_opponent_win_probability",
    "market_over25_probability",
    "market_team_expected_goals",
    "market_opponent_expected_goals",
    "market_clean_sheet_probability",
]


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def download_historical_odds(root: Path, seasons=None) -> dict[str, Path]:
    """Download source bytes once and preserve provenance alongside them."""
    seasons = list(seasons or SEASON_CODES)
    parent = Path(root) / "data" / "raw" / "historical_odds" / "football_data_uk"
    parent.mkdir(parents=True, exist_ok=True)
    result, manifest = {}, {"source": "football-data.co.uk", "files": {}}
    for season in seasons:
        code = SEASON_CODES[season]
        destination = parent / f"E0_{code}.csv"
        url = SOURCE_URL.format(code=code)
        if not destination.exists():
            response = requests.get(url, timeout=(10, 120))
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(dir=parent, delete=False) as handle:
                handle.write(response.content)
                temporary = Path(handle.name)
            temporary.replace(destination)
        body = destination.read_bytes()
        result[season] = destination
        manifest["files"][season] = {
            "url": url,
            "file": destination.name,
            "bytes": len(body),
            "sha256": _sha256(body),
        }
    (parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return result


def _valid_price(value) -> bool:
    return bool(pd.notna(value) and np.isfinite(float(value)) and float(value) > 1)


def normalize_historical_odds(paths: dict[str, Path]) -> pd.DataFrame:
    """Convert pre-closing market averages into fair probabilities and goal rates."""
    rows = []
    for season, path in paths.items():
        raw = pd.read_csv(path)
        missing = set(["Date", "HomeTeam", "AwayTeam", *ODDS_COLUMNS]) - set(raw)
        if missing:
            raise ValueError(f"{season} odds are missing columns: {sorted(missing)}")
        for match in raw.to_dict("records"):
            if not all(_valid_price(match.get(column)) for column in ODDS_COLUMNS):
                continue
            h2h = np.asarray([
                1 / float(match["AvgH"]),
                1 / float(match["AvgD"]),
                1 / float(match["AvgA"]),
            ])
            h2h /= h2h.sum()
            totals = np.asarray([
                1 / float(match["Avg>2.5"]),
                1 / float(match["Avg<2.5"]),
            ])
            totals /= totals.sum()
            probabilities = {
                "market_home_win_probability": float(h2h[0]),
                "market_draw_probability": float(h2h[1]),
                "market_away_win_probability": float(h2h[2]),
                "market_over25_probability": float(totals[0]),
            }
            probabilities.update(_implied_goal_model(probabilities))
            rows.append({
                "season": season,
                "odds_date": pd.to_datetime(match["Date"], dayfirst=True),
                "home_key": team_key(match["HomeTeam"]),
                "away_key": team_key(match["AwayTeam"]),
                **probabilities,
            })
    result = pd.DataFrame(rows)
    if result.duplicated(["season", "home_key", "away_key"]).any():
        raise ValueError("Historical odds contain duplicate season/team fixtures")
    return result


def historical_fixture_map(player_rows: pd.DataFrame) -> pd.DataFrame:
    """Recover one home/away record per FPL fixture from player-level rows."""
    required = {"season", "fixture", "team", "opp_team_name", "was_home", "kickoff_time"}
    missing = required - set(player_rows)
    if missing:
        raise ValueError(f"Player features are missing fixture keys: {sorted(missing)}")
    homes = player_rows[player_rows["was_home"].eq(1)].copy()
    fixtures = homes.groupby(["season", "fixture"], as_index=False).agg(
        home_team=("team", "first"),
        away_team=("opp_team_name", "first"),
        kickoff_time=("kickoff_time", "first"),
        home_variants=("team", "nunique"),
        away_variants=("opp_team_name", "nunique"),
    )
    if fixtures[["home_variants", "away_variants"]].ne(1).any().any():
        raise ValueError("A fixture maps to multiple home or away team names")
    fixtures["home_key"] = fixtures.home_team.map(team_key)
    fixtures["away_key"] = fixtures.away_team.map(team_key)
    return fixtures.drop(columns=["home_variants", "away_variants"])


def attach_historical_market(player_rows: pd.DataFrame,
                             odds: pd.DataFrame) -> pd.DataFrame:
    """Attach team-perspective market features to every player-fixture row."""
    result = player_rows.copy()
    fixtures = historical_fixture_map(result)
    joined = fixtures.merge(
        odds, on=["season", "home_key", "away_key"], how="left",
        validate="one_to_one", indicator=True,
    )
    missing = joined[joined["_merge"].ne("both")]
    if len(missing):
        sample = missing[["season", "home_team", "away_team"]].head(10).to_dict("records")
        raise ValueError(f"No historical odds match for {len(missing)} fixtures: {sample}")
    fixture_columns = [
        "season", "fixture", "market_home_win_probability",
        "market_draw_probability", "market_away_win_probability",
        "market_over25_probability", "market_home_expected_goals",
        "market_away_expected_goals", "market_home_clean_sheet_probability",
        "market_away_clean_sheet_probability",
    ]
    result = result.merge(joined[fixture_columns], on=["season", "fixture"],
                          how="left", validate="many_to_one")
    home = result["was_home"].astype(bool)
    result["market_team_win_probability"] = np.where(
        home, result.market_home_win_probability, result.market_away_win_probability
    )
    result["market_opponent_win_probability"] = np.where(
        home, result.market_away_win_probability, result.market_home_win_probability
    )
    result["market_team_expected_goals"] = np.where(
        home, result.market_home_expected_goals, result.market_away_expected_goals
    )
    result["market_opponent_expected_goals"] = np.where(
        home, result.market_away_expected_goals, result.market_home_expected_goals
    )
    result["market_clean_sheet_probability"] = np.where(
        home, result.market_home_clean_sheet_probability,
        result.market_away_clean_sheet_probability,
    )
    result = result.drop(columns=[
        "market_home_win_probability", "market_away_win_probability",
        "market_home_expected_goals", "market_away_expected_goals",
        "market_home_clean_sheet_probability", "market_away_clean_sheet_probability",
    ])
    if result[MARKET_FEATURES].isna().any().any():
        raise ValueError("Historical market join left missing model features")
    return result

