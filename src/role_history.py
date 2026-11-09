"""O5: penalty/set-piece roles, defensive contributions and price over time.

FPL's bootstrap only shows the current role. Every bootstrap we have archived
(app captures in ``data/raw/live_fpl`` and fpl-data snapshots) is read, and a
row is kept whenever a tracked field changes for a player, stamped with the
time we received it. ``as_of`` joins the latest version known before a cutoff
(a deadline or kickoff), so training never sees a later role.

    python src/role_history.py --output data/processed/role_history_20261106.csv
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["penalties_order", "corners_and_indirect_freekicks_order", "direct_freekicks_order",
          "defensive_contribution_per_90", "now_cost", "status"]


def bootstraps(root: Path):
    """(received_at, season, bootstrap path) for every complete archived snapshot."""
    root = Path(root)
    for manifest_path in [*root.glob("data/raw/live_fpl/capture_*/manifest.json"),
                          *root.glob("fpl-data/snapshots/*/*/manifest.json")]:
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        record = manifest.get("files", {}).get("bootstrap", {})
        path = manifest_path.parent / "bootstrap.json.gz"
        if manifest.get("status") == "complete" and record.get("received_at") and path.exists():
            yield record["received_at"], manifest.get("season"), path


def build(root: Path) -> pd.DataFrame:
    frames = []
    for received_at, season, path in bootstraps(root):
        elements = json.loads(gzip.decompress(path.read_bytes()))["elements"]
        frame = pd.DataFrame([{"player_id": e["id"], "code": e.get("code"), **{f: e.get(f) for f in FIELDS}}
                              for e in elements])
        frames.append(frame.assign(season=season, observed_at=pd.Timestamp(received_at)))
    if not frames:
        return pd.DataFrame(columns=["season", "player_id", "code", "observed_at", *FIELDS])
    rows = pd.concat(frames, ignore_index=True).sort_values(["season", "player_id", "observed_at"])
    for field in FIELDS[:-1]:
        rows[field] = pd.to_numeric(rows[field], errors="coerce")
    def differs(values):  # NaN equals NaN here: an empty order that stays empty is no change
        previous = values.shift()
        same = values.eq(previous) | (values.isna() & previous.isna())
        same.iloc[:1] = False  # a player's first version is always kept
        return (~same).astype(int)
    changed = rows.groupby(["season", "player_id"])[FIELDS].transform(differs).any(axis=1)
    return rows[changed].reset_index(drop=True)[["season", "player_id", "code", "observed_at", *FIELDS]]


def as_of(history: pd.DataFrame, rows: pd.DataFrame, time_column: str) -> pd.DataFrame:
    """Each row gets the latest history version observed strictly before ``rows[time_column]``."""
    left = rows.reset_index().assign(_cutoff=pd.to_datetime(rows[time_column], utc=True).to_numpy())
    right = history.assign(_cutoff=pd.to_datetime(history.observed_at, utc=True)).sort_values("_cutoff")
    merged = pd.merge_asof(left.sort_values("_cutoff"), right[["season", "player_id", "_cutoff", *FIELDS]],
                           on="_cutoff", by=["season", "player_id"], direction="backward", allow_exact_matches=False,
                           suffixes=("", "_asof"))
    return merged.set_index("index").sort_index().drop(columns="_cutoff")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    history = build(ROOT)
    if args.output.exists():
        raise FileExistsError(args.output)
    history.to_csv(args.output, index=False)
    changes = history.groupby(["season", "player_id"]).size()
    print(f"{len(history)} versions, {len(changes)} players, {int((changes > 1).sum())} with changes; "
          f"{history.observed_at.min()} – {history.observed_at.max()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
