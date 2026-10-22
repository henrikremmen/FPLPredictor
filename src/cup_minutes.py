"""Player minutes outside the Premier League (plan M8). Research only.

Source: FPL-Core-Insights (https://github.com/olbauday/FPL-Core-Insights), whose
maintainer asks for a link back. By the user's decision of 22 October 2026 the
source is for research and validation only, so challengers that use it are never
production-eligible. Every file is stored with URL, sha256 and fetch time.
Players are matched on FPL's stable ``code``; an ambiguous code fails.

    python src/cup_minutes.py download
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests

SOURCE = "https://github.com/olbauday/FPL-Core-Insights"
LISTING = "https://api.github.com/repos/olbauday/FPL-Core-Insights/contents/data/{season}/By%20Tournament{suffix}"
RAW = "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data/{season}/{path}"
SEASONS = {"2025-26": "2025-2026", "2026-27": "2026-2027"}
EXCLUDED = {"Premier League", "Friendlies"}  # rotation load = competitive matches outside the league
FEATURES = ["non_pl_minutes_7d", "non_pl_minutes_14d", "days_since_non_pl"]
HEADERS = {"User-Agent": "fplmodell-research/1.0"}
ROOT = Path(__file__).resolve().parents[1]


def _get(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=(10, 60))
    time.sleep(0.2)
    return response


def download(root: Path, seasons: dict[str, str] = SEASONS) -> Path:
    """Players plus per-round match and player-match files for every non-league tournament."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path(root) / "data/raw/fpl_core_insights" / stamp
    manifest = {"source": SOURCE, "use": "research and validation only; link back to the source",
                "started_at": datetime.now(timezone.utc).isoformat(), "files": {}}

    def save(season: str, path: str, target: Path, required: bool = True):
        url = RAW.format(season=seasons[season], path=path.replace(" ", "%20"))
        response = _get(url)
        if response.status_code == 404 and not required:
            return
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        manifest["files"][str(target.relative_to(folder))] = {
            "url": url, "sha256": hashlib.sha256(response.content).hexdigest(),
            "received_at": datetime.now(timezone.utc).isoformat()}

    for season, name in seasons.items():
        save(season, "players.csv", folder / season / "players.csv")
        listing = _get(LISTING.format(season=name, suffix=""))
        listing.raise_for_status()
        for tournament in [item["name"] for item in listing.json() if item["name"] not in EXCLUDED]:
            rounds = _get(LISTING.format(season=name, suffix="/" + tournament.replace(" ", "%20")))
            rounds.raise_for_status()
            for gw in [item["name"] for item in rounds.json()]:
                for file in ("matches.csv", "playermatchstats.csv"):
                    save(season, f"By Tournament/{tournament}/{gw}/{file}", folder / season / tournament / gw / file,
                         required=False)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return folder


def latest_download(root: Path) -> Path | None:
    found = sorted((Path(root) / "data/raw/fpl_core_insights").glob("*/manifest.json"))
    return found[-1].parent if found else None


def load_appearances(folder: Path) -> pd.DataFrame:
    """season, code, kickoff, minutes, competition for every finished non-league appearance."""
    rows = []
    for season in SEASONS:
        players_path = Path(folder) / season / "players.csv"
        if not players_path.exists():
            continue
        players = pd.read_csv(players_path, usecols=["player_id", "player_code"])
        if players.player_id.duplicated().any():
            raise ValueError(f"{season}: ambiguous FPL-Core-Insights player ids")
        for stats_path in sorted((Path(folder) / season).glob("*/*/playermatchstats.csv")):
            matches_path = stats_path.with_name("matches.csv")
            if not matches_path.exists():
                continue
            matches = pd.read_csv(matches_path, usecols=["match_id", "kickoff_time", "finished"])
            stats = pd.read_csv(stats_path, usecols=["player_id", "match_id", "minutes_played"])
            joined = (stats.merge(matches[matches.finished.astype(str).str.lower().eq("true")], on="match_id")
                      .merge(players, on="player_id", validate="many_to_one"))
            rows.append(pd.DataFrame({"season": season, "code": joined.player_code, "match_id": joined.match_id,
                                      "kickoff": pd.to_datetime(joined.kickoff_time, utc=True),
                                      "minutes": pd.to_numeric(joined.minutes_played, errors="coerce").fillna(0),
                                      "competition": stats_path.parent.parent.name}))
    columns = ["season", "code", "match_id", "kickoff", "minutes", "competition"]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.concat(rows, ignore_index=True)
    return frame[frame.minutes.gt(0)].drop_duplicates(["code", "match_id"])[columns]


def attach_cup_minutes(rows: pd.DataFrame, appearances: pd.DataFrame, codes: pd.DataFrame,
                       kickoff: pd.Series) -> pd.DataFrame:
    """Add minutes outside the league in the 7 and 14 days before each kickoff, and days since the last one.

    Only appearances that kicked off before the league fixture count. ``codes`` maps
    (season, player_id) to FPL ``code``; players without a code get NaN.
    """
    result = rows.copy()
    key = pd.DataFrame({"row": np.arange(len(rows)), "season": rows.season.to_numpy(),
                        "player_id": rows.player_id.to_numpy(), "kickoff": pd.to_datetime(kickoff, utc=True).to_numpy()})
    key = key.merge(codes[["season", "player_id", "code"]], on=["season", "player_id"], how="left", validate="many_to_one")
    pairs = key.dropna(subset=["code"]).merge(appearances[["code", "kickoff", "minutes"]].rename(columns={"kickoff": "played"}),
                                              on="code")
    before = pairs[pairs.played.lt(pairs.kickoff)]
    days = (before.kickoff - before.played).dt.total_seconds() / 86400
    window = lambda limit: before[days.le(limit)].groupby("row").minutes.sum()
    has_code = key.code.notna().to_numpy()
    for name, values in [("non_pl_minutes_7d", window(7)), ("non_pl_minutes_14d", window(14))]:
        column = values.reindex(np.arange(len(rows))).fillna(0).to_numpy(float)
        result[name] = np.where(has_code, column, np.nan)
    since = days.groupby(before.row).min().reindex(np.arange(len(rows))).to_numpy(float)
    result["days_since_non_pl"] = np.where(has_code, np.nan_to_num(np.minimum(since, 30), nan=30.0), np.nan)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["download"])
    parser.parse_args()
    print(download(ROOT))
