"""Historical Champions League workload from football-data.org.

The configured free plan exposes CL seasons from 2023/24 onwards, but not the
other UEFA or English cup competitions.  Feature names therefore say ``cl``
explicitly instead of overstating this as complete non-league workload.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from external_context import team_key


CL_SEASONS = {"2023-24": 2023, "2024-25": 2024, "2025-26": 2025}
CL_WORKLOAD_FEATURES = [
    "cl_matches_last7", "cl_matches_last14", "days_since_cl_match",
]


def _digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def download_historical_cl(root: Path, seasons=None) -> dict[str, Path]:
    root = Path(root)
    load_dotenv(root / ".env")
    api_key = os.getenv("FOOTBALL_DATA_API_KEY")
    if not api_key:
        raise ValueError("FOOTBALL_DATA_API_KEY is not configured")
    seasons = list(seasons or CL_SEASONS)
    parent = root / "data" / "raw" / "historical_workload" / "football_data_org"
    parent.mkdir(parents=True, exist_ok=True)
    result, manifest = {}, {"source": "football-data.org:v4/competitions/CL/matches",
                            "files": {}}
    for season in seasons:
        destination = parent / f"CL_{CL_SEASONS[season]}.json.gz"
        if not destination.exists():
            response = requests.get(
                "https://api.football-data.org/v4/competitions/CL/matches",
                headers={"X-Auth-Token": api_key},
                params={"season": CL_SEASONS[season]}, timeout=(10, 60),
            )
            response.raise_for_status()
            body = response.content
            destination.write_bytes(gzip.compress(body, mtime=0))
        compressed = destination.read_bytes()
        body = gzip.decompress(compressed)
        payload = json.loads(body)
        result[season] = destination
        manifest["files"][season] = {
            "file": destination.name,
            "matches": len(payload.get("matches", [])),
            "sha256": _digest(body),
            "stored_sha256": _digest(compressed),
        }
    (parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return result


def load_cl_events(paths: dict[str, Path]) -> pd.DataFrame:
    rows = []
    for season, path in paths.items():
        payload = json.loads(gzip.decompress(path.read_bytes()))
        for match in payload.get("matches", []):
            kickoff = pd.to_datetime(match.get("utcDate"), utc=True, errors="coerce")
            if pd.isna(kickoff):
                continue
            for side in ["homeTeam", "awayTeam"]:
                team = match.get(side) or {}
                name = team.get("name") or team.get("shortName") or team.get("tla")
                if name:
                    rows.append({
                        "season": season, "team_key": team_key(name),
                        "cl_kickoff": kickoff, "cl_match_id": match.get("id"),
                    })
    result = pd.DataFrame(rows).drop_duplicates(
        ["season", "team_key", "cl_match_id"]
    )
    return result.sort_values(["season", "team_key", "cl_kickoff"])


def attach_cl_workload(player_rows: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    result = player_rows.copy()
    result["_team_key"] = result["team"].map(team_key)
    kickoff = pd.to_datetime(result["kickoff_time"], utc=True, errors="raise")
    grouped = {
        key: group.cl_kickoff.sort_values().to_numpy()
        for key, group in events.groupby(["season", "team_key"])
    }
    values = {feature: [] for feature in CL_WORKLOAD_FEATURES}
    for season, key, current in zip(result.season, result._team_key, kickoff):
        times = grouped.get((season, key), np.asarray([], dtype="datetime64[ns]"))
        # numpy may strip timezone; integer nanoseconds makes comparison stable.
        current_ns = current.value
        past = np.asarray([
            pd.Timestamp(value).value for value in times
            if pd.Timestamp(value).value < current_ns
        ], dtype=np.int64)
        values["cl_matches_last7"].append(int(
            (past >= current_ns - pd.Timedelta(days=7).value).sum()
        ))
        values["cl_matches_last14"].append(int(
            (past >= current_ns - pd.Timedelta(days=14).value).sum()
        ))
        values["days_since_cl_match"].append(
            (current_ns - past.max()) / pd.Timedelta(days=1).value if len(past) else np.nan
        )
    for feature, column in values.items():
        result[feature] = column
    return result.drop(columns="_team_key")

