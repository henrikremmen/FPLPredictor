"""Separate-provider Understat features with explicit identity and time joins.

Historical files have match dates, not capture timestamps. Next-day availability
is a research proxy only. Identity bridges use published mappings and stable FPL
codes; ambiguous links fail rather than being resolved with fuzzy names.
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd

UNDERSTAT_FEATURES = ["us_minutes_last5", "us_shots_last5", "us_xg_last5",
    "us_npxg_last5", "us_xa_last5", "us_key_passes_last5", "us_xgchain_last5",
    "us_xgbuildup_last5", "us_xg_per_shot5", "us_npxg90_last5",
    "us_xa90_last5", "us_observations5"]
FIELDS = {"time": "minutes", "shots": "shots", "xG": "xg", "npxG": "npxg",
          "xA": "xa", "key_passes": "key_passes", "xGChain": "xgchain",
          "xGBuildup": "xgbuildup"}


def identity_map(root: Path) -> pd.DataFrame:
    parent = Path(root) / "data-source/data"
    bridges = []
    players = []
    for path in sorted(parent.glob("*/players_raw.csv")):
        raw = pd.read_csv(path, usecols=["id", "code"])
        if raw.id.duplicated().any() or raw.code.duplicated().any():
            raise ValueError(f"Ambiguous player identities: {path}")
        raw["season"] = path.parent.name
        players.append(raw)
        mapping_path = path.parent / "id_dict.csv"
        if not mapping_path.exists():
            continue
        mapping = pd.read_csv(mapping_path)
        mapping.columns = mapping.columns.str.strip()
        joined = mapping.merge(raw, left_on="FPL_ID", right_on="id", validate="many_to_one")
        bridges.append(joined[["Understat_ID", "code"]])
    if not bridges:
        raise ValueError("No explicit Understat/FPL identity bridge")
    bridge = pd.concat(bridges).drop_duplicates()
    if bridge.Understat_ID.duplicated().any() or bridge.code.duplicated().any():
        raise ValueError("Conflicting stable identity bridges require review")
    return pd.concat(players).merge(bridge, on="code", how="inner", validate="many_to_one").rename(
        columns={"id": "player_id", "Understat_ID": "understat_id"})


def load_match_history(root: Path) -> pd.DataFrame:
    records = []
    for path in sorted((Path(root) / "data-source/data").glob("*/understat/*.csv")):
        match = re.search(r"_(\d+)\.csv$", path.name)
        if not match or path.name.startswith("understat_"):
            continue
        frame = pd.read_csv(path)
        if not {"id", "date", *FIELDS}.issubset(frame):
            raise ValueError(f"Unexpected Understat schema: {path}")
        frame = frame[["id", "date", *FIELDS]].copy()
        frame["understat_id"] = int(match.group(1))
        frame["source_file"] = str(path.relative_to(root))
        records.append(frame)
    if not records:
        raise ValueError("No individual Understat match histories")
    history = pd.concat(records, ignore_index=True)
    history["available_at"] = pd.to_datetime(history.date, utc=True).dt.normalize() + pd.Timedelta(days=1)
    for field in FIELDS:
        history[field] = pd.to_numeric(history[field], errors="raise")
    # Files copied across seasons may contain overlapping career histories.
    keys = ["understat_id", "id"]
    conflicts = history.groupby(keys)[["date", *FIELDS]].nunique(dropna=False).gt(1).any(axis=1)
    dates_conflict = history.groupby(keys).date.nunique().gt(1)
    if dates_conflict.any():
        rejected = dates_conflict[dates_conflict].index
        history = history.loc[~pd.MultiIndex.from_frame(history[keys]).isin(rejected)]
    # Prefer the earliest local season archive deterministically. This avoids
    # silently replacing old values with later revisions, but still does not
    # certify that the earliest archive existed before the historical deadline.
    result = history.drop_duplicates(keys, keep="first").sort_values(["understat_id", "available_at", "id"])
    result.attrs["revised_match_records"] = int(conflicts.sum())
    result.attrs["quarantined_date_conflicts"] = int(dates_conflict.sum())
    result.attrs["revision_policy"] = "earliest local season archive; retrospective only"
    return result


def attach_understat(rows: pd.DataFrame, history: pd.DataFrame, identities: pd.DataFrame) -> pd.DataFrame:
    if identities.duplicated(["season", "player_id"]).any():
        raise ValueError("Ambiguous season/player mapping")
    result = rows.merge(identities[["season", "player_id", "understat_id"]],
                        on=["season", "player_id"], how="left", validate="many_to_one")
    cutoffs = pd.to_datetime(result.prediction_cutoff, utc=True, errors="raise")
    if cutoffs.isna().any():
        raise ValueError("Missing prediction cutoff")
    output = np.full((len(result), len(UNDERSTAT_FEATURES)), np.nan)
    histories = {}
    for player, group in history.groupby("understat_id"):
        group = group.sort_values(["available_at", "id"])
        values = group[list(FIELDS)].rolling(5, min_periods=1).sum()
        values.columns = [f"us_{name}_last5" for name in FIELDS.values()]
        values["us_xg_per_shot5"] = values.us_xg_last5 / values.us_shots_last5.replace(0, np.nan)
        values["us_npxg90_last5"] = 90 * values.us_npxg_last5 / values.us_minutes_last5.replace(0, np.nan)
        values["us_xa90_last5"] = 90 * values.us_xa_last5 / values.us_minutes_last5.replace(0, np.nan)
        values["us_observations5"] = np.minimum(np.arange(len(group)) + 1, 5)
        histories[player] = (pd.to_datetime(group.available_at, utc=True).astype("int64").to_numpy(),
                             values[UNDERSTAT_FEATURES].to_numpy())
    cutoff_ns = cutoffs.astype("int64").to_numpy()
    for player, indices in result.groupby("understat_id").groups.items():
        if player not in histories:
            continue
        times, values = histories[player]
        indices = np.asarray(indices)
        positions = np.searchsorted(times, cutoff_ns[indices], side="left") - 1
        valid = positions >= 0
        output[indices[valid]] = values[positions[valid]]
    result[UNDERSTAT_FEATURES] = output
    return result
