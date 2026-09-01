"""Build a leakage-aware player-fixture feature table for FPL modelling.

Run from the repository root with::

    python src/build_features.py

The script preserves every column from the aggregated source, standardises two
names (``season_x`` -> ``season`` and ``element`` -> ``player_id``), and adds
features calculated from fixtures strictly before the current fixture.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


WINDOWS = (3, 5, 10)
PLAYER_KEYS = ["season", "player_id"]


@dataclass(frozen=True)
class FeatureInfo:
    """Metadata describing one output column."""

    feature_name: str
    source_column: str
    feature_group: str
    transformation: str
    timing: str
    safe_for_prediction: str
    notes: str = ""


class FeatureStore:
    """Collect engineered columns and their metadata before one final concat."""

    def __init__(self, index: pd.Index) -> None:
        self.index = index
        self.values: dict[str, pd.Series] = {}
        self.metadata: list[FeatureInfo] = []

    def add(
        self,
        name: str,
        values: pd.Series | np.ndarray | float,
        *,
        source: str,
        group: str,
        transformation: str,
        timing: str = "HISTORICAL_SHIFTED",
        safety: str = "SAFE",
        notes: str = "",
    ) -> None:
        """Register one feature, rejecting accidental duplicate names."""
        if name in self.values:
            raise ValueError(f"Feature already exists: {name}")
        if isinstance(values, pd.Series):
            series = values.reindex(self.index)
        else:
            series = pd.Series(values, index=self.index)
        self.values[name] = series
        self.metadata.append(
            FeatureInfo(name, source, group, transformation, timing, safety, notes)
        )

    def frame(self) -> pd.DataFrame:
        """Materialise all engineered features in one DataFrame."""
        return pd.DataFrame(self.values, index=self.index)


def parse_args() -> argparse.Namespace:
    """Parse command-line paths while keeping repo-root defaults."""
    repo_root = Path(__file__).resolve().parents[1]
    default_source = (
        repo_root
        / "data-source"
        / "data"
        / "cleaned_merged_seasons_team_aggregated_expanded.csv"
    )
    default_output = repo_root / "data" / "processed"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=default_source)
    parser.add_argument("--output-dir", type=Path, default=default_output)
    return parser.parse_args()


def load_data(path: Path) -> pd.DataFrame:
    """Load the actual aggregated source without altering it."""
    if not path.exists():
        raise FileNotFoundError(
            f"Aggregated source not found: {path}\n"
            "Run notebooks/build_expanded_dataset.ipynb first."
        )
    return pd.read_csv(path, low_memory=False)


def inspect_source_data(df: pd.DataFrame, path: Path) -> None:
    """Print source facts needed to audit the modelling unit."""
    required = {
        "season_x",
        "element",
        "fixture",
        "GW",
        "kickoff_time",
        "team",
        "derived_team_id",
        "opponent_team",
        "minutes",
        "total_points",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Source is missing required columns: {sorted(missing)}")

    duplicates = int(df.duplicated(["season_x", "element", "fixture"]).sum())
    dgw = (
        df.groupby(["season_x", "element", "GW"], dropna=False)["fixture"]
        .nunique()
        .gt(1)
        .sum()
    )
    parsed = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
    print(f"Source: {path}")
    print(f"Source shape: {df.shape[0]:,} rows x {df.shape[1]} columns")
    print(f"Seasons: {sorted(df['season_x'].dropna().unique())}")
    print(f"Duplicate season/player/fixture rows: {duplicates:,}")
    print(f"Player-GW groups containing multiple fixtures: {int(dgw):,}")
    print(f"Unparseable kickoff timestamps: {int(parsed.isna().sum()):,}")


def clean_and_standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise identifiers, dtypes, and ordering without dropping columns."""
    out = df.rename(columns={"season_x": "season", "element": "player_id"}).copy()
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], errors="coerce", utc=True)
    out["fixture"] = pd.to_numeric(out["fixture"], errors="raise")
    out["player_id"] = pd.to_numeric(out["player_id"], errors="raise")
    out["GW"] = pd.to_numeric(out["GW"], errors="coerce")
    out = out.sort_values(
        ["season", "player_id", "kickoff_time", "fixture"], kind="stable"
    ).reset_index(drop=True)
    out["target_points"] = pd.to_numeric(out["total_points"], errors="coerce")
    return out


def numeric(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric view of a raw column without mutating the raw values."""
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide while returning NaN for zero/unknown denominators and no infinity."""
    denominator = pd.to_numeric(denominator, errors="coerce")
    result = pd.to_numeric(numerator, errors="coerce") / denominator.where(
        denominator.ne(0)
    )
    return result.replace([np.inf, -np.inf], np.nan)


def shifted(df: pd.DataFrame, series: pd.Series, periods: int = 1) -> pd.Series:
    """Shift a series within player-season groups."""
    return series.groupby(
        [df["season"], df["player_id"]], sort=False, dropna=False
    ).shift(periods)


def rolling_prior(
    df: pd.DataFrame, series: pd.Series, window: int, aggregation: str
) -> pd.Series:
    """Calculate a rolling statistic from prior player fixtures only."""
    prior = shifted(df, series)
    roller = prior.groupby(
        [df["season"], df["player_id"]], sort=False, dropna=False
    ).rolling(window, min_periods=1)
    result = getattr(roller, aggregation)()
    return result.reset_index(level=[0, 1], drop=True).reindex(df.index)


def expanding_prior(df: pd.DataFrame, series: pd.Series, aggregation: str) -> pd.Series:
    """Calculate a season-to-date statistic using only prior fixtures."""
    prior = shifted(df, series)
    expander = prior.groupby(
        [df["season"], df["player_id"]], sort=False, dropna=False
    ).expanding(min_periods=1)
    result = getattr(expander, aggregation)()
    return result.reset_index(level=[0, 1], drop=True).reindex(df.index)


def add_sample_size_and_playing_time(
    df: pd.DataFrame, store: FeatureStore
) -> dict[int, pd.Series]:
    """Add availability, minutes, starts, and playing-time reliability features."""
    minutes = numeric(df, "minutes")
    starts = numeric(df, "starts")
    observation_number = df.groupby(PLAYER_KEYS, sort=False).cumcount()
    minutes_windows: dict[int, pd.Series] = {}

    store.add(
        "minutes_last1",
        shifted(df, minutes),
        source="minutes",
        group="playing_time",
        transformation="shift(1)",
    )
    for window in WINDOWS:
        games_available = observation_number.clip(upper=window).astype("int16")
        minutes_sum = rolling_prior(df, minutes, window, "sum")
        starts_sum = rolling_prior(df, starts, window, "sum")
        minutes_windows[window] = minutes_sum
        store.add(
            f"games_available_last{window}",
            games_available,
            source="fixture",
            group="sample_size",
            transformation=f"count of prior fixture observations, capped at {window}",
        )
        store.add(
            f"minutes_last{window}", minutes_sum, source="minutes", group="playing_time",
            transformation=f"shift(1), rolling({window}).sum(min_periods=1)",
        )
        store.add(
            f"minutes_avg{window}", safe_divide(minutes_sum, games_available),
            source="minutes", group="playing_time",
            transformation=f"minutes_last{window} / games_available_last{window}",
        )
        store.add(
            f"starts_last{window}", starts_sum, source="starts", group="playing_time",
            transformation=f"shift(1), rolling({window}).sum(min_periods=1)",
        )
        store.add(
            f"start_rate{window}", safe_divide(starts_sum, games_available),
            source="starts,fixture", group="playing_time",
            transformation=f"starts_last{window} / games_available_last{window}",
        )
        for threshold in (60, 80):
            flag = minutes.ge(threshold).astype("int8")
            store.add(
                f"games_{threshold}plus_last{window}",
                rolling_prior(df, flag, window, "sum"),
                source="minutes", group="playing_time",
                transformation=f"shift(1), rolling({window}).sum(minutes >= {threshold})",
            )

    games_played = minutes.gt(0).astype("int8")
    store.add(
        "games_played_season_before",
        expanding_prior(df, games_played, "sum").fillna(0),
        source="minutes", group="sample_size",
        transformation="shift(1), season expanding sum(minutes > 0)",
    )
    store.add(
        "minutes_season_before", expanding_prior(df, minutes, "sum").fillna(0),
        source="minutes", group="playing_time",
        transformation="shift(1), season expanding sum",
    )
    starts_season = expanding_prior(df, starts, "sum")
    store.add(
        "starts_season_before", starts_season, source="starts", group="playing_time",
        transformation="shift(1), season expanding sum",
    )
    store.add(
        "start_rate_season_before",
        safe_divide(starts_season, observation_number),
        source="starts,fixture", group="playing_time",
        transformation="starts_season_before / prior fixture observations",
    )
    return minutes_windows


def add_rolling_stat_features(
    df: pd.DataFrame,
    store: FeatureStore,
    specs: dict[str, tuple[str, str]],
    *,
    averages: Iterable[str] = (),
    season_totals: Iterable[str] = (),
) -> None:
    """Add shifted rolling sums, optional averages, and season-to-date totals."""
    average_set = set(averages)
    season_set = set(season_totals)
    for source, (alias, group) in specs.items():
        values = numeric(df, source)
        for window in WINDOWS:
            total = rolling_prior(df, values, window, "sum")
            store.add(
                f"{alias}_last{window}", total, source=source, group=group,
                transformation=f"shift(1), rolling({window}).sum(min_periods=1)",
            )
            if source in average_set:
                available = store.values[f"games_available_last{window}"]
                store.add(
                    f"{alias}_avg{window}", safe_divide(total, available),
                    source=source, group=group,
                    transformation=f"{alias}_last{window} / games_available_last{window}",
                )
        if source in season_set:
            store.add(
                f"{alias}_season_before", expanding_prior(df, values, "sum").fillna(0),
                source=source, group=group,
                transformation="shift(1), season expanding sum",
            )


def add_per90_features(
    df: pd.DataFrame,
    store: FeatureStore,
    specs: dict[str, tuple[str, str]],
    minutes_windows: dict[int, pd.Series],
) -> None:
    """Add ratio-of-window-sums per-90 features, never mean of match ratios."""
    for source, (alias, group) in specs.items():
        values = numeric(df, source)
        for window in WINDOWS:
            total_name = f"{alias}_last{window}"
            total = store.values.get(total_name)
            if total is None:
                total = rolling_prior(df, values, window, "sum")
            per90 = safe_divide(total * 90.0, minutes_windows[window])
            store.add(
                f"{alias}90_last{window}", per90, source=f"{source},minutes",
                group=group,
                transformation=f"90 * sum(prior {window} {source}) / sum(prior {window} minutes)",
            )


def add_attacking_and_fpl_features(
    df: pd.DataFrame, store: FeatureStore, minutes_windows: dict[int, pd.Series]
) -> None:
    """Add attacking, FPL-output, market, xP, and finishing features."""
    specs = {
        "goals_scored": ("goals", "attacking"),
        "assists": ("assists", "attacking"),
        "expected_goals": ("xG", "attacking"),
        "expected_assists": ("xA", "attacking"),
        "expected_goal_involvements": ("xGI", "attacking"),
        "big_chances_created": ("big_chances_created", "attacking"),
        "big_chances_missed": ("big_chances_missed", "attacking"),
        "key_passes": ("key_passes", "attacking"),
        "target_missed": ("target_missed", "attacking"),
        "open_play_crosses": ("crosses", "attacking"),
        "dribbles": ("dribbles", "attacking"),
        "offside": ("offsides", "attacking"),
        "threat": ("threat", "ict"),
        "creativity": ("creativity", "ict"),
        "influence": ("influence", "ict"),
        "ict_index": ("ict", "ict"),
        "total_points": ("points", "fpl_performance"),
        "bonus": ("bonus", "fpl_performance"),
        "bps": ("bps", "fpl_performance"),
    }
    add_rolling_stat_features(
        df,
        store,
        specs,
        averages={"threat", "creativity", "influence", "ict_index", "total_points", "bonus", "bps"},
        season_totals=set(specs),
    )
    per90_sources = {
        key: specs[key]
        for key in [
            "goals_scored", "assists", "expected_goals", "expected_assists",
            "expected_goal_involvements", "key_passes", "big_chances_created",
            "threat", "creativity", "influence", "ict_index", "total_points",
            "bonus", "bps",
        ]
    }
    add_per90_features(df, store, per90_sources, minutes_windows)

    for window in WINDOWS:
        goals = store.values[f"goals_last{window}"]
        assists = store.values[f"assists_last{window}"]
        xg = store.values[f"xG_last{window}"]
        xa = store.values[f"xA_last{window}"]
        xgi = store.values[f"xGI_last{window}"]
        missed = store.values[f"target_missed_last{window}"]
        store.add(
            f"goals_minus_xG_last{window}", goals - xg,
            source="goals_scored,expected_goals", group="finishing",
            transformation=f"goals_last{window} - xG_last{window}",
        )
        store.add(
            f"assists_minus_xA_last{window}", assists - xa,
            source="assists,expected_assists", group="finishing",
            transformation=f"assists_last{window} - xA_last{window}",
        )
        store.add(
            f"xGI_minus_returns_last{window}", xgi - goals - assists,
            source="expected_goal_involvements,goals_scored,assists", group="finishing",
            transformation=f"xGI_last{window} - goals_last{window} - assists_last{window}",
        )
        store.add(
            f"goal_conversion_proxy_last{window}", safe_divide(goals, goals + missed),
            source="goals_scored,target_missed", group="finishing",
            transformation="goals / (goals + target_missed); proxy, not true shot conversion",
            notes="target_missed is not a complete shots denominator",
        )

    uncertain = {
        "selected": "selected",
        "transfers_in": "transfers_in",
        "transfers_out": "transfers_out",
        "transfers_balance": "transfer_balance",
        "value": "price",
    }
    for source, alias in uncertain.items():
        values = numeric(df, source)
        last1 = shifted(df, values)
        store.add(
            f"{alias}_last1", last1, source=source, group="market",
            transformation="shift(1)", safety="REVIEW",
            notes="FPL snapshot collection timing is not guaranteed pre-deadline",
        )
        store.add(
            f"{alias}_change", values - last1, source=source, group="market",
            transformation=f"current {source} - shifted {source}", timing="UNKNOWN",
            safety="REVIEW", notes="Uses current-row snapshot with uncertain timing",
        )
        for window in WINDOWS:
            store.add(
                f"{alias}_last{window}", rolling_prior(df, values, window, "sum"),
                source=source, group="market",
                transformation=f"shift(1), rolling({window}).sum(min_periods=1)",
                safety="REVIEW", notes="Historical snapshot timing remains uncertain",
            )

    xp = numeric(df, "xP")
    store.add(
        "xP_last1", shifted(df, xp), source="xP", group="fpl_expected_points",
        transformation="shift(1)", safety="REVIEW",
        notes="Repository README warns xP may have been recorded post-match",
    )
    for window in WINDOWS:
        store.add(
            f"xP_avg{window}", rolling_prior(df, xp, window, "mean"),
            source="xP", group="fpl_expected_points",
            transformation=f"shift(1), rolling({window}).mean(min_periods=1)",
            safety="REVIEW", notes="Shifted but source collection timing is uncertain",
        )


def add_defensive_goalkeeper_passing_features(
    df: pd.DataFrame, store: FeatureStore, minutes_windows: dict[int, pd.Series]
) -> None:
    """Add defensive, discipline, goalkeeper, passing, rare, and manager history."""
    specs = {
        "clean_sheets": ("clean_sheets", "defensive"),
        "clearances_blocks_interceptions": ("CBI", "defensive"),
        "tackles": ("tackles", "defensive"),
        "tackled": ("tackled", "defensive"),
        "recoveries": ("recoveries", "defensive"),
        "goals_conceded": ("goals_conceded", "defensive"),
        "errors_leading_to_goal": ("errors_leading_to_goal", "defensive"),
        "errors_leading_to_goal_attempt": ("errors_leading_to_goal_attempt", "defensive"),
        "penalties_conceded": ("penalties_conceded", "discipline"),
        "defensive_contribution": ("defensive_contribution", "defensive"),
        "fouls": ("fouls", "discipline"),
        "yellow_cards": ("yellow_cards", "discipline"),
        "red_cards": ("red_cards", "discipline"),
        "own_goals": ("own_goals", "discipline"),
        "penalties_missed": ("penalties_missed", "discipline"),
        "saves": ("saves", "goalkeeper"),
        "penalties_saved": ("penalties_saved", "goalkeeper"),
        "attempted_passes": ("attempted_passes", "passing"),
        "completed_passes": ("completed_passes", "passing"),
        "winning_goals": ("winning_goals", "rare_events"),
        "loaned_in": ("loaned_in", "rare_events"),
        "loaned_out": ("loaned_out", "rare_events"),
        "mng_clean_sheets": ("mng_clean_sheets", "manager"),
        "mng_draw": ("mng_draw", "manager"),
        "mng_goals_scored": ("mng_goals_scored", "manager"),
        "mng_loss": ("mng_loss", "manager"),
        "mng_underdog_draw": ("mng_underdog_draw", "manager"),
        "mng_underdog_win": ("mng_underdog_win", "manager"),
        "mng_win": ("mng_win", "manager"),
    }
    add_rolling_stat_features(
        df,
        store,
        specs,
        averages={"saves", "defensive_contribution"},
        season_totals=set(specs),
    )
    per90_keys = [
        "clearances_blocks_interceptions", "tackles", "recoveries", "goals_conceded",
        "fouls", "saves", "attempted_passes", "completed_passes", "defensive_contribution",
    ]
    add_per90_features(df, store, {key: specs[key] for key in per90_keys}, minutes_windows)

    for window in WINDOWS:
        available = store.values[f"games_available_last{window}"]
        store.add(
            f"clean_sheet_rate{window}",
            safe_divide(store.values[f"clean_sheets_last{window}"], available),
            source="clean_sheets,fixture", group="defensive",
            transformation=f"clean_sheets_last{window} / games_available_last{window}",
        )
        attempted = store.values[f"attempted_passes_last{window}"]
        completed = store.values[f"completed_passes_last{window}"]
        store.add(
            f"pass_completion_last{window}", safe_divide(completed, attempted),
            source="completed_passes,attempted_passes", group="passing",
            transformation="sum(completed passes) / sum(attempted passes)",
        )
        positive = numeric(df, "defensive_contribution").gt(0).astype("int8")
        store.add(
            f"defensive_contribution_rate{window}",
            safe_divide(rolling_prior(df, positive, window, "sum"), available),
            source="defensive_contribution,fixture", group="defensive",
            transformation=f"prior fixtures with defensive_contribution > 0 / available prior {window}",
            notes="Rate of positive recorded values; the source stores a match-level FPL API count",
        )


def build_team_history(df: pd.DataFrame) -> pd.DataFrame:
    """Create one leakage-safe team row per actual fixture."""
    columns = [
        "season", "derived_team_id", "opponent_team", "fixture", "kickoff_time",
        "was_home", "team_h_score", "team_a_score",
    ]
    team = df[columns].drop_duplicates(["season", "derived_team_id", "fixture"]).copy()
    team = team.sort_values(
        ["season", "derived_team_id", "kickoff_time", "fixture"], kind="stable"
    ).reset_index(drop=True)
    home_score = pd.to_numeric(team["team_h_score"], errors="coerce")
    away_score = pd.to_numeric(team["team_a_score"], errors="coerce")
    is_home = team["was_home"].astype(bool)
    team["goals_for_match"] = home_score.where(is_home, away_score)
    team["goals_against_match"] = away_score.where(is_home, home_score)
    played = team["goals_for_match"].notna() & team["goals_against_match"].notna()
    team["points_match"] = np.where(
        ~played,
        np.nan,
        np.select(
            [team["goals_for_match"].gt(team["goals_against_match"]),
             team["goals_for_match"].eq(team["goals_against_match"])],
            [3.0, 1.0],
            default=0.0,
        ),
    )
    keys = [team["season"], team["derived_team_id"]]
    team["team_games_played_before"] = team.groupby(
        ["season", "derived_team_id"], sort=False
    ).cumcount()

    for source, prefix in [
        ("points_match", "team_points"),
        ("goals_for_match", "team_goals_scored"),
        ("goals_against_match", "team_goals_conceded"),
    ]:
        values = pd.to_numeric(team[source], errors="coerce")
        prior = values.groupby(keys, sort=False).shift(1)
        for window in WINDOWS:
            rolled = prior.groupby(keys, sort=False).rolling(window, min_periods=1).sum()
            team[f"{prefix}_last{window}"] = rolled.reset_index(
                level=[0, 1], drop=True
            ).reindex(team.index)

    team["team_goal_diff_last3"] = (
        team["team_goals_scored_last3"] - team["team_goals_conceded_last3"]
    )
    team["team_goal_diff_last5"] = (
        team["team_goals_scored_last5"] - team["team_goals_conceded_last5"]
    )
    team["team_goal_diff_last10"] = (
        team["team_goals_scored_last10"] - team["team_goals_conceded_last10"]
    )

    games = team["team_games_played_before"]
    points_before = numeric(team, "points_match").fillna(0).groupby(keys).cumsum() - numeric(team, "points_match").fillna(0)
    goals_for_before = numeric(team, "goals_for_match").fillna(0).groupby(keys).cumsum() - numeric(team, "goals_for_match").fillna(0)
    goals_against_before = numeric(team, "goals_against_match").fillna(0).groupby(keys).cumsum() - numeric(team, "goals_against_match").fillna(0)
    team["team_points_per_game_before"] = safe_divide(points_before, games)
    team["team_goals_for_per_game_before"] = safe_divide(goals_for_before, games)
    team["team_goals_against_per_game_before"] = safe_divide(goals_against_before, games)
    team["team_goal_difference_per_game_before"] = safe_divide(
        goals_for_before - goals_against_before, games
    )

    for venue_name, venue_flag in [("home", True), ("away", False)]:
        indicator = is_home.eq(venue_flag).astype("int8")
        venue_games = indicator.groupby(keys).cumsum() - indicator
        venue_for = (team["goals_for_match"].fillna(0) * indicator)
        venue_against = (team["goals_against_match"].fillna(0) * indicator)
        venue_for_before = venue_for.groupby(keys).cumsum() - venue_for
        venue_against_before = venue_against.groupby(keys).cumsum() - venue_against
        team[f"team_{venue_name}_games_before"] = venue_games
        team[f"team_{venue_name}_goals_for_pg_before"] = safe_divide(
            venue_for_before, venue_games
        )
        team[f"team_{venue_name}_goals_against_pg_before"] = safe_divide(
            venue_against_before, venue_games
        )
    return team


def add_team_opponent_and_matchup_features(
    df: pd.DataFrame, team_history: pd.DataFrame
) -> tuple[pd.DataFrame, list[FeatureInfo]]:
    """Join own/opponent pre-match team form and create simple matchup deltas."""
    keys = ["season", "derived_team_id", "fixture"]
    base = {
        "season", "derived_team_id", "opponent_team", "fixture", "kickoff_time",
        "was_home", "team_h_score", "team_a_score", "goals_for_match",
        "goals_against_match", "points_match",
    }
    feature_columns = [column for column in team_history.columns if column not in base]
    own = team_history[keys + feature_columns]
    out = df.merge(own, on=keys, how="left", validate="many_to_one")

    opponent = team_history[["season", "derived_team_id", "fixture"] + feature_columns].copy()
    opponent = opponent.rename(columns={"derived_team_id": "opponent_team"})
    opponent = opponent.rename(
        columns={column: column.replace("team_", "opp_", 1) for column in feature_columns}
    )
    out = out.merge(
        opponent, on=["season", "opponent_team", "fixture"], how="left",
        validate="many_to_one",
    )

    out["ppg_difference"] = (
        out["team_points_per_game_before"] - out["opp_points_per_game_before"]
    )
    out["goal_difference_per_game_difference"] = (
        out["team_goal_difference_per_game_before"]
        - out["opp_goal_difference_per_game_before"]
    )
    out["team_attack_vs_opp_defence"] = (
        out["team_goals_for_per_game_before"]
        - out["opp_goals_against_per_game_before"]
    )
    out["team_defence_vs_opp_attack"] = (
        out["opp_goals_for_per_game_before"]
        - out["team_goals_against_per_game_before"]
    )
    for window in (3, 5):
        out[f"recent_form_difference_{window}"] = (
            out[f"team_points_last{window}"] - out[f"opp_points_last{window}"]
        )
    out["recent_goal_difference_5"] = (
        out["team_goal_diff_last5"] - out["opp_goal_diff_last5"]
    )

    metadata: list[FeatureInfo] = []
    for column in feature_columns:
        metadata.append(
            FeatureInfo(
                column, "team fixture outcomes", "team", "prior actual team fixtures",
                "PRE_MATCH", "SAFE", "Built at one team-fixture row before player join",
            )
        )
        opponent_name = column.replace("team_", "opp_", 1)
        metadata.append(
            FeatureInfo(
                opponent_name, "opponent fixture outcomes", "opponent",
                "opponent corresponding pre-match team row", "PRE_MATCH", "SAFE",
                "Joined by season + opponent_team + fixture",
            )
        )
    for column, note in {
        "ppg_difference": "team PPG - opponent PPG",
        "goal_difference_per_game_difference": "team goal-difference PG - opponent",
        "team_attack_vs_opp_defence": "team goals-for PG - opponent goals-against PG",
        "team_defence_vs_opp_attack": "opponent goals-for PG - team goals-against PG",
        "recent_form_difference_3": "team points last3 - opponent points last3",
        "recent_form_difference_5": "team points last5 - opponent points last5",
        "recent_goal_difference_5": "team goal difference last5 - opponent last5",
    }.items():
        metadata.append(
            FeatureInfo(column, "team and opponent features", "matchup", note, "PRE_MATCH", "SAFE")
        )
    return out, metadata


def raw_feature_metadata(columns: Iterable[str]) -> list[FeatureInfo]:
    """Classify every preserved raw/source column by timing and prediction safety."""
    identifiers = {
        "season", "player_id", "fixture", "GW", "round", "name", "id", "position",
        "team", "derived_team_id", "opponent_team", "opp_team_name", "kickoff_time",
        "kickoff_time_formatted", "was_home",
    }
    known_pre_match = {
        "points_before_match", "team_goals_scored_before_match",
        "team_goals_conceded_before_match", "team_goals_diff_before_match",
    }
    unknown_timing = {
        "selected", "transfers_in", "transfers_out", "transfers_balance", "value",
        "price_m", "modified",
    }
    xp = {"xP"}
    post_match = {
        "assists", "attempted_passes", "big_chances_created", "big_chances_missed",
        "bonus", "bps", "clean_sheets", "clearances_blocks_interceptions",
        "completed_passes", "creativity", "dribbles", "ea_index",
        "errors_leading_to_goal", "errors_leading_to_goal_attempt", "fouls",
        "goals_conceded", "goals_scored", "ict_index", "influence", "key_passes",
        "loaned_in", "loaned_out", "minutes", "offside", "open_play_crosses",
        "own_goals", "penalties_conceded", "penalties_missed", "penalties_saved",
        "recoveries", "red_cards", "saves", "starts", "tackled", "tackles",
        "target_missed", "team_a_score", "team_h_score", "threat", "total_points",
        "winning_goals", "yellow_cards", "expected_assists",
        "expected_goal_involvements", "expected_goals", "expected_goals_conceded",
        "defensive_contribution", "points", "team_goals_scored",
        "team_goals_conceded", "team_goals_diff", "mng_clean_sheets", "mng_draw",
        "mng_goals_scored", "mng_loss", "mng_underdog_draw", "mng_underdog_win",
        "mng_win",
    }
    rows: list[FeatureInfo] = []
    for column in columns:
        original_source = {"season": "season_x", "player_id": "element"}.get(
            column, column
        )
        if column == "target_points":
            rows.append(FeatureInfo(column, "total_points", "target", "copy", "POST_MATCH", "UNSAFE_LEAKAGE", "Model target"))
        elif column in identifiers:
            rename_note = (
                f"Renamed from {original_source}; " if original_source != column else ""
            )
            rows.append(FeatureInfo(column, original_source, "identifier_metadata", "raw/renamed", "IDENTIFIER", "REVIEW", rename_note + "Use for grouping, joins, or reporting; not as an unexamined numeric feature"))
        elif column in known_pre_match:
            rows.append(FeatureInfo(column, column, "team", "raw pre-match cumulative", "PRE_MATCH", "SAFE", "Validated against prior team fixture in expanded source"))
        elif column in xp:
            rows.append(FeatureInfo(column, column, "fpl_expected_points", "raw", "UNKNOWN", "UNSAFE_LEAKAGE", "README warns scraper may record ep_this after the match"))
        elif column in unknown_timing:
            rows.append(FeatureInfo(column, column, "market", "raw snapshot", "UNKNOWN", "REVIEW", "Exact pre/post-deadline collection timing is not guaranteed"))
        elif column in post_match:
            note = "Current fixture outcome; preserve but never use directly as predictor"
            if column.startswith("mng_"):
                note = "Assistant Manager scoring component in 2024/25; match-result-derived"
            if column == "defensive_contribution":
                note = "FPL API match-level defensive-contribution count, present from 2025/26"
            rows.append(FeatureInfo(column, column, "current_fixture_outcome", "raw", "POST_MATCH", "UNSAFE_LEAKAGE", note))
        else:
            rows.append(FeatureInfo(column, column, "raw_other", "raw", "UNKNOWN", "REVIEW", "Preserved; timing/meaning needs review before modelling"))
    return rows


def build_feature_metadata(
    raw_columns: Iterable[str],
    engineered: list[FeatureInfo],
    team_metadata: list[FeatureInfo],
) -> pd.DataFrame:
    """Build one auditable metadata row for every output column."""
    rows = raw_feature_metadata(raw_columns) + engineered + team_metadata
    metadata = pd.DataFrame([row.__dict__ for row in rows])
    if metadata["feature_name"].duplicated().any():
        duplicates = metadata.loc[metadata["feature_name"].duplicated(), "feature_name"]
        raise AssertionError(f"Duplicate metadata rows: {duplicates.tolist()}")
    return metadata


def validate_features(
    source: pd.DataFrame,
    output: pd.DataFrame,
    engineered_columns: list[str],
    team_history: pd.DataFrame,
) -> None:
    """Run chronology, leakage-shift, DGW, opponent, and numerical checks."""
    assert len(source) == len(output), "Feature joins changed row count"
    assert not output.duplicated(["season", "player_id", "fixture"]).any()
    assert output["target_points"].equals(pd.to_numeric(output["total_points"], errors="coerce"))
    expected_order = output.sort_values(
        ["season", "player_id", "kickoff_time", "fixture"], kind="stable"
    ).index
    assert expected_order.equals(output.index), "Rows are not chronologically sorted"

    for column in engineered_columns:
        if pd.api.types.is_numeric_dtype(output[column]):
            assert not np.isinf(output[column].to_numpy(dtype="float64", na_value=np.nan)).any(), (
                f"Infinite values in {column}"
            )

    first_rows = output.groupby(PLAYER_KEYS, sort=False).head(1)
    assert first_rows["games_available_last3"].eq(0).all()
    assert first_rows["points_last3"].isna().all(), "Player rolling features crossed season boundary"

    candidates = output.groupby(PLAYER_KEYS, sort=False).filter(lambda group: len(group) >= 6)
    checked = 0
    for _, group in candidates.groupby(PLAYER_KEYS, sort=False):
        row = group.iloc[5]
        manual = pd.to_numeric(group.iloc[2:5]["total_points"], errors="coerce").sum()
        assert np.isclose(row["points_last3"], manual, equal_nan=True)
        checked += 1
        if checked == 2:
            break
    assert checked == 2, "Could not manually validate two players"

    zero_minute = pd.to_numeric(output["minutes"], errors="coerce").eq(0)
    assert zero_minute.any(), "Zero-minute fixture observations were lost"
    dgw = output.groupby(["season", "player_id", "GW"])["fixture"].nunique()
    assert dgw.gt(1).any(), "No Double Gameweek player-fixture rows found"

    expected_team_games = team_history.groupby(
        ["season", "derived_team_id"], sort=False
    ).cumcount()
    assert team_history["team_games_played_before"].equals(expected_team_games)
    opponent_check = output.loc[output["opp_games_played_before"].notna()].iloc[0]
    matching = team_history.loc[
        team_history["season"].eq(opponent_check["season"])
        & team_history["derived_team_id"].eq(opponent_check["opponent_team"])
        & team_history["fixture"].eq(opponent_check["fixture"])
    ]
    assert len(matching) == 1
    assert np.isclose(
        opponent_check["opp_games_played_before"],
        matching.iloc[0]["team_games_played_before"],
    )

    print("Validation passed:")
    print("  chronological player-season ordering")
    print("  unique player x fixture rows")
    print("  target equality")
    print("  no infinite engineered values")
    print("  rolling reset and two manual last3 checks")
    print("  zero-minute observations and Double Gameweeks retained")
    print("  team games-before and opponent pre-match join")


def save_outputs(
    output: pd.DataFrame, metadata: pd.DataFrame, output_dir: Path
) -> tuple[Path, Path]:
    """Write reproducible processed outputs without touching source data."""
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_path = output_dir / "player_fixture_features.csv"
    metadata_path = output_dir / "feature_metadata.csv"
    output.to_csv(feature_path, index=False)
    metadata.to_csv(metadata_path, index=False)
    return feature_path, metadata_path


def main() -> None:
    """Execute the complete feature pipeline."""
    args = parse_args()
    raw = load_data(args.source)
    inspect_source_data(raw, args.source)
    source_column_count = len(raw.columns)
    cleaned = clean_and_standardize_columns(raw)

    store = FeatureStore(cleaned.index)
    minutes_windows = add_sample_size_and_playing_time(cleaned, store)
    add_attacking_and_fpl_features(cleaned, store, minutes_windows)
    add_defensive_goalkeeper_passing_features(cleaned, store, minutes_windows)
    player_features = store.frame()
    featured = pd.concat([cleaned, player_features], axis=1)

    team_history = build_team_history(cleaned)
    featured, team_metadata = add_team_opponent_and_matchup_features(
        featured, team_history
    )
    engineered_columns = list(store.values) + [row.feature_name for row in team_metadata]
    metadata = build_feature_metadata(
        cleaned.columns, store.metadata, team_metadata
    )
    if set(featured.columns) != set(metadata["feature_name"]):
        missing_metadata = set(featured.columns).difference(metadata["feature_name"])
        raise AssertionError(f"Columns without metadata: {sorted(missing_metadata)}")

    validate_features(raw, featured, engineered_columns, team_history)
    feature_path, metadata_path = save_outputs(featured, metadata, args.output_dir)

    missing = featured.isna().sum().sort_values(ascending=False).head(20)
    print("\nTop 20 columns by missing values:")
    print(missing.to_string())
    print("\nBuild summary:")
    print(f"  source columns preserved/renamed: {source_column_count}")
    print(f"  engineered features: {len(engineered_columns)}")
    print(f"  output shape: {featured.shape[0]:,} rows x {featured.shape[1]} columns")
    print(f"  seasonal player IDs: {featured.groupby(PLAYER_KEYS).ngroups:,}")
    print(f"  unique fixture IDs within season: {featured.groupby(['season', 'fixture']).ngroups:,}")
    print(f"  feature groups: {sorted(metadata['feature_group'].unique())}")
    print(f"  features: {feature_path}")
    print(f"  metadata: {metadata_path}")


if __name__ == "__main__":
    main()
