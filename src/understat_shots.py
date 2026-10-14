"""Normalize captured rosters/shots; keep Understat measures separate from FPL."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import numpy as np

SHOT_FEATURES = ["us_nonpenalty_shots5", "us_central_close_shots5", "us_shot_npxg5",
                 "us_shot_quality5", "us_team_npxg_share5", "us_nonpenalty_shots90_5",
                 "us_shot_history_age_days", "us_shot_observations5"]


def attach_shot_features(rows, history, identities, *, mode):
    """Join either observed pre-cutoff data or explicitly retrospective proxies.

The two modes cannot be confused by a default. Production callers must use
observed mode; historical backfills were not observed before old deadlines.
"""
    if mode not in ["observed", "retrospective"]:
        raise ValueError("Choose observed or retrospective availability")
    if identities.duplicated(["season", "player_id"]).any():
        raise ValueError("Ambiguous player mapping")
    if history.duplicated(["understat_id", "id"]).any():
        raise ValueError("Duplicate player/match history")
    result = rows.merge(identities[["season", "player_id", "understat_id"]],
        on=["season", "player_id"], how="left", validate="many_to_one")
    result["prediction_cutoff"] = pd.to_datetime(result.prediction_cutoff, utc=True, errors="raise")
    history = history.copy()
    history["played_at"] = pd.to_datetime(history.date, utc=True, errors="raise")
    history["available_at"] = (pd.to_datetime(history.observed_at, utc=True, errors="raise")
        if mode == "observed" else history.played_at.dt.normalize() + pd.Timedelta(days=1))
    if result.prediction_cutoff.isna().any() or history.available_at.isna().any() or history.played_at.isna().any():
        raise ValueError("Missing temporal evidence")
    groups = {player: group.sort_values(["played_at", "id"]) for player, group in history.groupby("understat_id")}
    features = np.full((len(result), len(SHOT_FEATURES)), np.nan)
    for (player, cutoff), indices in result.groupby(["understat_id", "prediction_cutoff"]).groups.items():
        if player not in groups:
            continue
        group = groups[player]
        prior = group[group.available_at.lt(cutoff) & group.played_at.lt(cutoff)].tail(5)
        if prior.empty:
            continue
        shots, minutes = prior.nonpenalty_shots.sum(), prior.time.sum()
        npxg, team_npxg = prior.npxG.sum(), prior.team_npxg.sum()
        features[list(indices)] = [shots, prior.central_close_shots.sum(), npxg,
            npxg / shots if shots else np.nan, npxg / team_npxg if team_npxg else np.nan,
            90 * shots / minutes if minutes else np.nan,
            (cutoff - prior.played_at.max()).total_seconds() / 86400, len(prior)]
    result[SHOT_FEATURES] = features
    result["understat_timing_mode"] = mode
    return result


def normalize_match(match: dict, payload: dict, received_at: str) -> pd.DataFrame:
    rows = []
    ids = set()
    for side in ["h", "a"]:
        shots = payload["shots"][side]
        for shot in shots:
            if shot["id"] in ids:
                raise ValueError("Duplicate shot ID")
            ids.add(shot["id"])
            if str(shot["match_id"]) != str(match["id"]):
                raise ValueError("Shot belongs to another match")
            if not (0 <= float(shot["X"]) <= 1 and 0 <= float(shot["Y"]) <= 1
                    and 0 <= float(shot["xG"]) <= 1):
                raise ValueError("Invalid shot coordinates or xG")
        roster = payload["rosters"][side].values()
        roster_ids = {str(player["player_id"]) for player in roster}
        if any(str(shot["player_id"]) not in roster_ids for shot in shots):
            raise ValueError("Shooter missing from match roster")
        team_npxg = sum(float(shot["xG"]) for shot in shots if shot["situation"] != "Penalty")
        for player in roster:
            own = [shot for shot in shots if str(shot["player_id"]) == str(player["player_id"])]
            nonpenalty = [shot for shot in own if shot["situation"] != "Penalty"]
            npxg = sum(float(shot["xG"]) for shot in nonpenalty)
            rows.append({"understat_id": int(player["player_id"]), "id": int(match["id"]),
                "date": match["datetime"], "observed_at": received_at,
                "player_name": player.get("player"),
                "team": match[side]["title"], "position": player["position"],
                "time": float(player["time"]), "shots": len(own), "nonpenalty_shots": len(nonpenalty),
                "xG": sum(float(shot["xG"]) for shot in own), "npxG": npxg,
                "xA": float(player["xA"]), "key_passes": float(player["key_passes"]),
                "xGChain": float(player["xGChain"]), "xGBuildup": float(player["xGBuildup"]),
                "central_close_shots": sum(float(shot["X"]) >= .83 and .25 <= float(shot["Y"]) <= .75 for shot in nonpenalty),
                "team_nonpenalty_shots": sum(shot["situation"] != "Penalty" for shot in shots),
                "team_npxg": team_npxg,
                "npxg_share": npxg / team_npxg if team_npxg > 0 else float("nan"),
                "npxg_per_shot": npxg / len(nonpenalty) if nonpenalty else float("nan")})
    result = pd.DataFrame(rows)
    if result.understat_id.duplicated().any():
        raise ValueError("Duplicate roster player")
    return result


def normalize_capture(folder):
    folder = Path(folder)
    frames = []
    for path in sorted(folder.glob("league_*.json")):
        if path.name.endswith(".meta.json"):
            continue
        league = json.loads(path.read_text())
        for match in league["dates"]:
            if not match["isResult"]:
                continue
            source = folder / f"match_{match['id']}.json"
            meta = json.loads(source.with_suffix(".meta.json").read_text())
            if hashlib.sha256(source.read_bytes()).hexdigest() != meta["sha256"]:
                raise ValueError(f"Changed match response: {source}")
            frames.append(normalize_match(match, json.loads(source.read_text()), meta["received_at"]))
    result = pd.concat(frames, ignore_index=True)
    if result.duplicated(["understat_id", "id"]).any():
        raise ValueError("Duplicate player/match across capture")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("capture")
    parser.add_argument("output")
    args = parser.parse_args()
    frame = normalize_capture(args.capture)
    frame.to_csv(args.output, index=False)
    print(f"Normalized {len(frame)} player matches, {frame.id.nunique()} fixtures")
