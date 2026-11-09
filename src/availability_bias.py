"""M10: is injury risk counted twice? Measurement only; production is untouched.

The model already predicts P(0 minutes) from its features; the app then
multiplies by FPL's availability (``chance_of_playing_next_round`` or 0.75 for a
flag without a percentage). For every Gameweek with a pre-deadline capture and
an exported outcome (fpl-data), compare bias (actual − forecast) for flagged
players with and without that factor. Any new policy becomes a challenger in
the prospective loop, like ``availability_*`` today.

    python src/availability_bias.py --from-event 6 --output artifacts/m10_availability_bias_20261106
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fpl_app import _availability_factor
from prospective_loop import _gz, forecast_capture

ROOT = Path(__file__).resolve().parents[1]
SEASON = "2026-27"


def gameweek_rows(root: Path, event: int) -> pd.DataFrame | None:
    """Pre-deadline forecasts, FPL availability and the outcome for one Gameweek."""
    found = forecast_capture(root, event)
    outcome = Path(root) / "fpl-data/data" / SEASON / "gws" / f"gw{event}.csv"
    if found is None or not outcome.exists():
        return None
    snapshot, manifest = found
    forecast = pd.read_csv(snapshot / "horizon_forecast.csv")
    forecast = forecast[forecast.GW.eq(event)][["player_id", "prediction"]]
    elements = _gz(snapshot / "bootstrap.json.gz")["elements"]
    availability = pd.DataFrame({"player_id": [e["id"] for e in elements],
                                 "availability": [_availability_factor(e) for e in elements],
                                 "chance": [e.get("chance_of_playing_next_round") for e in elements]})
    actual = pd.read_csv(outcome).groupby("element").total_points.sum().rename("actual")
    rows = forecast.merge(availability, on="player_id", how="inner")
    rows["actual"] = rows.player_id.map(actual).fillna(0.0)
    rows["adjusted"] = rows.prediction * rows.availability
    return rows.assign(GW=event, forecast_at=manifest["forecast_at"])


def summarize(rows: pd.DataFrame) -> dict:
    def stats(frame):
        if frame.empty:
            return {"n": 0}
        raw, adjusted = frame.actual - frame.prediction, frame.actual - frame.adjusted
        se = lambda x: float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else None
        return {"n": int(len(frame)), "actual_mean": float(frame.actual.mean()),
                "bias_model_only": float(raw.mean()), "bias_model_only_se": se(raw),
                "bias_with_app_factor": float(adjusted.mean()), "bias_with_app_factor_se": se(adjusted),
                "mae_model_only": float(raw.abs().mean()), "mae_with_app_factor": float(adjusted.abs().mean())}
    flagged = rows[rows.availability.lt(1)]
    buckets = {str(int(round(a * 100))): stats(group) for a, group in flagged.groupby("availability")}
    return {"all": stats(rows), "flagged": stats(flagged), "flagged_by_availability_pct": buckets,
            "by_gameweek": {int(gw): stats(group[group.availability.lt(1)]) for gw, group in rows.groupby("GW")}}


def run(root: Path, first: int, last: int) -> tuple[dict, pd.DataFrame]:
    frames = [frame for event in range(first, last + 1) if (frame := gameweek_rows(root, event)) is not None]
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    report = {"events": sorted(rows.GW.unique().tolist()) if len(rows) else [], "season": SEASON,
              "note": "bias = actual − forecast; positive means the forecast is too low",
              **(summarize(rows) if len(rows) else {})}
    return report, rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-event", type=int, default=6)
    parser.add_argument("--to-event", type=int, default=38)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report, rows = run(ROOT, args.from_event, args.to_event)
    args.output.mkdir(parents=True, exist_ok=False)
    rows.to_csv(args.output / "rows.csv", index=False)
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in report if k in ("events", "all", "flagged", "flagged_by_availability_pct")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
