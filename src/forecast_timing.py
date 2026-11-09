"""E3: does newer pre-deadline information improve forecasts? T-24h+ vs T-6–24h vs ≤6h.

For each Gameweek with an exported outcome (fpl-data), every capture that
forecast it before the deadline is scored on the same players (those present
in all of them), as the app uses it: model points × FPL availability. Captures
made for an earlier round also count, labelled by hours before this deadline.

    python src/forecast_timing.py --output artifacts/e3_forecast_timing_20261106
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from fpl_app import _availability_factor
from prospective_loop import _deadline, _gz, captures
from prospective_lock import utc

ROOT = Path(__file__).resolve().parents[1]
SEASON = "2026-27"


def bucket(hours: float) -> str:
    return "T-24h+" if hours > 24 else "T-6-24h" if hours > 6 else "T-6h"


def timing_rows(root: Path, event: int) -> pd.DataFrame:
    outcome = Path(root) / "fpl-data/data" / SEASON / "gws" / f"gw{event}.csv"
    if not outcome.exists():
        return pd.DataFrame()
    actual = pd.read_csv(outcome).groupby("element").total_points.sum()
    frames = []
    for snapshot, manifest in captures(root):
        if manifest.get("season") != SEASON or event not in manifest.get("forecast_horizons", []):
            continue
        deadline = utc(_deadline(snapshot, event))
        hours = (deadline - utc(manifest["forecast_at"])).total_seconds() / 3600
        if hours <= 0 or not (snapshot / "horizon_forecast.csv").exists():
            continue
        forecast = pd.read_csv(snapshot / "horizon_forecast.csv")
        forecast = forecast[forecast.GW.eq(event)][["player_id", "prediction"]]
        availability = {e["id"]: _availability_factor(e) for e in _gz(snapshot / "bootstrap.json.gz")["elements"]}
        forecast["forecast"] = forecast.prediction * forecast.player_id.map(availability).fillna(1.0)
        frames.append(forecast.assign(capture=snapshot.name, hours_before=round(hours, 1), bucket=bucket(hours)))
    if not frames:
        return pd.DataFrame()
    rows = pd.concat(frames, ignore_index=True)
    common = rows.groupby("player_id").capture.nunique().eq(rows.capture.nunique())
    rows = rows[rows.player_id.isin(common[common].index)].copy()
    rows["actual"] = rows.player_id.map(actual).fillna(0.0)
    rows["error"] = rows.forecast - rows.actual
    return rows.assign(GW=event)


def summarize(rows: pd.DataFrame) -> dict:
    per_capture = rows.groupby(["GW", "capture", "hours_before", "bucket"]).agg(
        players=("player_id", "size"), mae=("error", lambda e: e.abs().mean()), bias=("error", "mean")).reset_index()
    latest = per_capture.loc[per_capture.groupby("GW").hours_before.idxmin()].assign(bucket="last")
    by_bucket = (pd.concat([per_capture, latest]).groupby("bucket")
                 .agg(rounds=("GW", "nunique"), captures=("capture", "size"), mae=("mae", "mean"), bias=("bias", "mean")))
    return {"per_capture": per_capture.to_dict("records"), "by_bucket": by_bucket.reset_index().to_dict("records"),
            "note": "bias = forecast − actual; same players within a round; rounds differ by bucket"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = pd.concat([timing_rows(ROOT, event) for event in range(1, 39)], ignore_index=True)
    report = summarize(rows) if len(rows) else {"per_capture": [], "by_bucket": []}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, default=str))
    print(pd.DataFrame(report["by_bucket"]).to_string(index=False))
    print(pd.DataFrame(report["per_capture"]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
