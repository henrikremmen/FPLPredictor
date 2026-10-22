"""Build the expanded player-fixture table (plan D2).

Replaces ``notebooks/build_expanded_dataset.ipynb`` with the same logic. Reads
vaastav seasons from ``data-source/data`` and own seasons from
``fpl-data/data``; an own season replaces the vaastav copy of the same season.
Own seasons must pass the data contract (D3) first. Output goes to
``data/processed/``, never into the third-party checkout.

    python src/build_dataset.py
    python src/build_dataset.py --own-data ''   # vaastav only (notebook inputs)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data_contract import validate_gameweeks


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_NAME = "cleaned_merged_seasons_team_aggregated_expanded.csv"
AGGREGATE_COLUMNS = [
    "points", "team_goals_scored", "team_goals_conceded", "team_goals_diff",
    "points_before_match", "team_goals_scored_before_match",
    "team_goals_conceded_before_match", "team_goals_diff_before_match",
]


def season_dirs(*roots: Path | None) -> dict[str, Path]:
    """Season folders with ``gws/merged_gw.csv``; later roots win for the same season."""
    found = {}
    for root in roots:
        if root is None or not root.exists():
            continue
        for path in root.iterdir():
            if path.is_dir() and path.name[:4].isdigit() and (path / "gws" / "merged_gw.csv").exists():
                found[path.name] = path
    return dict(sorted(found.items()))


def _read(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def _team_names(seasons: dict[str, Path], master: pd.DataFrame | None, id_column: str,
                name_column: str, with_master: bool) -> pd.DataFrame:
    frames = []
    for season, path in seasons.items():
        if (path / "teams.csv").exists():
            names = pd.read_csv(path / "teams.csv", usecols=["id", "name"]).rename(
                columns={"id": id_column, "name": name_column})
            names["season_x"] = season
            frames.append(names)
    if with_master and master is not None:
        frames.append(master[["season", "team", "team_name"]].rename(
            columns={"season": "season_x", "team": id_column, "team_name": name_column}))
    return pd.concat(frames, ignore_index=True).drop_duplicates(["season_x", id_column])


def build_expanded(seasons: dict[str, Path], master_path: Path | None) -> pd.DataFrame:
    """The notebook's steps 2–6: combine, own team, opponent names, team statistics."""
    master = pd.read_csv(master_path) if master_path is not None and master_path.exists() else None
    frames = []
    for season, path in seasons.items():
        season_data = _read(path / "gws" / "merged_gw.csv")
        season_data["season_x"] = season
        if "GW" not in season_data.columns and "round" in season_data.columns:
            season_data["GW"] = season_data["round"]
        frames.append(season_data)
    all_seasons = pd.concat(frames, ignore_index=True, sort=False)
    all_seasons["kickoff_time"] = pd.to_datetime(all_seasons["kickoff_time"], errors="coerce", utc=True)

    # Identical rows and postponed fixtures recorded on both dates: keep the last.
    key = ["season_x", "element", "fixture"]
    all_seasons = (all_seasons.sort_values(key + ["kickoff_time"], na_position="first")
                   .drop_duplicates(key, keep="last").reset_index(drop=True))

    # Older seasons omit the player's own team: it is the other team in the fixture.
    participants = all_seasons[["season_x", "fixture", "opponent_team"]].drop_duplicates()
    own = participants.merge(participants, on=["season_x", "fixture"], suffixes=("", "_other"))
    own = own.loc[own["opponent_team"].ne(own["opponent_team_other"]),
                  ["season_x", "fixture", "opponent_team", "opponent_team_other"]].rename(
        columns={"opponent_team_other": "derived_team_id"}).drop_duplicates(
        ["season_x", "fixture", "opponent_team"])
    all_seasons = all_seasons.merge(own, on=["season_x", "fixture", "opponent_team"], how="left",
                                    validate="many_to_one")
    own_names = _team_names(seasons, master, "derived_team_id", "derived_team_name", True)
    all_seasons = all_seasons.merge(own_names, on=["season_x", "derived_team_id"], how="left",
                                    validate="many_to_one")
    if "team" not in all_seasons.columns:
        all_seasons["team"] = all_seasons["derived_team_name"]
    else:
        all_seasons["team"] = all_seasons["team"].fillna(all_seasons["derived_team_name"])
    all_seasons = all_seasons.drop(columns=["derived_team_name"])
    if "position" in all_seasons.columns:
        all_seasons["position"] = all_seasons.groupby("name")["position"].transform(
            lambda values: values.ffill().bfill())

    # Opponent names; master list is the fallback for seasons without teams.csv.
    all_seasons = all_seasons.drop(columns=["opp_team_name"], errors="ignore")
    if any((path / "teams.csv").exists() for path in seasons.values()):
        all_seasons = all_seasons.merge(
            _team_names(seasons, None, "opponent_team", "opp_team_name", False),
            on=["season_x", "opponent_team"], how="left")
    if master is not None:
        fallback = master[["season", "team", "team_name"]].rename(columns={
            "season": "season_x", "team": "opponent_team", "team_name": "fallback_name",
        }).drop_duplicates(["season_x", "opponent_team"])
        all_seasons = all_seasons.merge(fallback, on=["season_x", "opponent_team"], how="left")
        all_seasons["opp_team_name"] = all_seasons["opp_team_name"].fillna(all_seasons["fallback_name"])
        all_seasons = all_seasons.drop(columns="fallback_name")

    # One row per team and fixture, so double Gameweeks count both matches.
    required = {"season_x", "team", "fixture", "GW", "kickoff_time", "was_home", "team_h_score", "team_a_score"}
    missing = required.difference(all_seasons.columns)
    if missing:
        raise ValueError(f"Missing columns for team aggregation: {sorted(missing)}")
    matches = all_seasons[list(required)].drop_duplicates(["season_x", "team", "fixture"]).copy()
    for column in ["team_h_score", "team_a_score"]:
        matches[column] = pd.to_numeric(matches[column], errors="coerce")
    matches["team_goals_scored_match"] = matches["team_h_score"].where(matches["was_home"], matches["team_a_score"])
    matches["team_goals_conceded_match"] = matches["team_a_score"].where(matches["was_home"], matches["team_h_score"])
    played = matches["team_goals_scored_match"].notna() & matches["team_goals_conceded_match"].notna()
    won = matches["team_goals_scored_match"] > matches["team_goals_conceded_match"]
    drawn = matches["team_goals_scored_match"] == matches["team_goals_conceded_match"]
    matches["points_match"] = float("nan")
    matches.loc[played, "points_match"] = 0.0
    matches.loc[played & drawn, "points_match"] = 1.0
    matches.loc[played & won, "points_match"] = 3.0
    matches["points_match"] = pd.to_numeric(matches["points_match"], errors="coerce")
    matches = matches.sort_values(["season_x", "team", "kickoff_time", "fixture"]).reset_index(drop=True)
    groups = [matches["season_x"], matches["team"]]
    matches["points"] = matches["points_match"].fillna(0.0).groupby(groups).cumsum()
    for name in ("scored", "conceded"):
        matches[f"team_goals_{name}"] = pd.to_numeric(
            matches[f"team_goals_{name}_match"], errors="coerce").fillna(0.0).groupby(groups).cumsum()
    matches["team_goals_diff"] = matches["team_goals_scored"] - matches["team_goals_conceded"]
    # *_before_match uses only earlier results and is safe for prediction.
    for source in ["points", "team_goals_scored", "team_goals_conceded", "team_goals_diff"]:
        matches[f"{source}_before_match"] = matches.groupby(["season_x", "team"], sort=False)[source].shift(1).fillna(0)

    all_seasons = all_seasons.drop(columns=AGGREGATE_COLUMNS, errors="ignore")
    expanded = all_seasons.merge(matches[["season_x", "team", "fixture"] + AGGREGATE_COLUMNS],
                                 on=["season_x", "team", "fixture"], how="left", validate="many_to_one")
    if "value" in expanded.columns:
        expanded["price_m"] = pd.to_numeric(expanded["value"], errors="coerce") / 10
    return expanded.sort_values(["season_x", "GW", "kickoff_time", "team", "name"]).reset_index(drop=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vaastav-data", type=Path, default=ROOT / "data-source" / "data")
    parser.add_argument("--own-data", type=Path, default=ROOT / "fpl-data" / "data",
                        help="own seasons in the same format; '' disables")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / OUTPUT_NAME)
    args = parser.parse_args(argv)
    own_root = args.own_data if str(args.own_data) not in {"", "."} else None
    for season, path in season_dirs(own_root).items():
        validate_gameweeks(pd.read_csv(path / "gws" / "merged_gw.csv"), pd.read_csv(path / "fixtures.csv"))
        print(f"{season}: own export passes the data contract")
    seasons = season_dirs(args.vaastav_data, own_root)
    expanded = build_expanded(seasons, args.vaastav_data / "master_team_list.csv")
    duplicates = int(expanded.duplicated(["season_x", "element", "fixture"], keep=False).sum())
    if duplicates:
        raise SystemExit(f"{duplicates} duplicate season/player/fixture rows")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    expanded.to_csv(args.output, index=False)
    report = expanded.groupby("season_x").agg(rows=("name", "size"), gameweeks=("GW", "nunique"))
    print(report.to_string())
    print(f"Saved {len(expanded):,} rows from {', '.join(f'{s}={p.parent.parent.name}' for s, p in seasons.items())}"
          f"\nto {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
