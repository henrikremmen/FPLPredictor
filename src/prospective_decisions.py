"""Score preselected squads; never optimize again after observing results."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from decision_backtest import POSITIONS, START_LIMITS
from prospective_evaluation import KEYS, outcomes_from_snapshot
from prospective_lock import digest, utc


def score_selections(selections, forecasts, truth):
    if truth.duplicated(KEYS).any() or not np.isfinite(truth.target_points.to_numpy(float)).all():
        raise ValueError("Duplicate or invalid outcomes")
    # Require outcomes for the exact planned fixtures of every selected player;
    # summing whatever outcomes happen to exist would hide an unfinished DGW.
    chosen_keys = selections[["model", "season", "GW", "player_id"]]
    expected = forecasts[["model", *KEYS]].drop_duplicates().merge(chosen_keys,
        on=["model", "season", "GW", "player_id"], validate="many_to_one")
    needed = chosen_keys.merge(expected[["model", "season", "GW", "player_id"]].drop_duplicates(),
        how="left", indicator=True)
    if needed._merge.ne("both").any():
        raise ValueError("Selected player has no frozen fixture forecast")
    outcomes = expected.merge(truth[KEYS + ["target_points"]], on=KEYS, how="left", validate="many_to_one")
    if outcomes.target_points.isna().any():
        raise ValueError("Missing selected-player fixture outcome")
    weekly = outcomes.groupby(["model", "season", "GW", "player_id"], as_index=False).target_points.sum()
    scored = selections.merge(weekly, on=["model", "season", "GW", "player_id"], validate="one_to_one")
    reports = []
    for (model, season, gw), group in scored.groupby(["model", "season", "GW"]):
        if (len(group) != 15 or group.player_id.nunique() != 15 or group.value.sum() > 1000
                or group.position.value_counts().to_dict() != POSITIONS or group.groupby("team").size().max() > 3):
            raise ValueError("Locked squad violates selection rules")
        if not group.starter.isin([True, False]).all() or not group.captain.isin([True, False]).all():
            raise ValueError("Invalid selection flags")
        starters, captain = group[group.starter.astype(bool)], group[group.captain.astype(bool)]
        if len(starters) != 11 or len(captain) != 1 or not captain.starter.all():
            raise ValueError("Invalid locked XI or captain")
        for position, (minimum, maximum) in START_LIMITS.items():
            if not minimum <= starters.position.eq(position).sum() <= maximum:
                raise ValueError("Invalid locked formation")
        reports.append({"model": model, "season": season, "GW": int(gw),
            "actual_points": float(starters.target_points.sum() + captain.target_points.iloc[0]),
            "captain_points_before_doubling": float(captain.target_points.iloc[0]),
            "bench_points_not_counted": float(group.loc[~group.starter.astype(bool), "target_points"].sum())})
    return reports, scored


def evaluate_decisions(bundle, snapshot, destination, *, provisional=False):
    bundle, snapshot, destination = Path(bundle), Path(snapshot), Path(destination)
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest["status"] != "locked" or utc(manifest["completed_at"]) >= utc(manifest["deadline"]):
        raise ValueError("Decisions were not locked before deadline")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or digest(bundle / name) != expected:
            raise ValueError("Changed locked decision evidence")
    truth = outcomes_from_snapshot(manifest, snapshot, provisional=provisional)
    forecasts = pd.concat([pd.read_csv(bundle / name) for name in manifest["files"]
                           if name.startswith("forecast_")], ignore_index=True)
    reports, scored = score_selections(pd.read_csv(bundle / "selections.csv"), forecasts, truth)
    destination.mkdir(parents=True, exist_ok=False)
    scored.to_csv(destination / "scored_selections.csv", index=False)
    report = {"bundle_manifest_sha256": digest(bundle / "manifest.json"),
        "outcome_manifest_sha256": digest(snapshot / "manifest.json"), "metrics": reports,
        "scope": manifest["scope"], "production_eligible": False,
        "evaluation_mode": 'provisional' if provisional else 'final'}
    (destination / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    parser.add_argument("snapshot")
    parser.add_argument("destination")
    parser.add_argument('--provisional', action='store_true')
    args = parser.parse_args()
    evaluate_decisions(args.bundle, args.snapshot, args.destination, provisional=args.provisional)
