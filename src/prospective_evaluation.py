"""Evaluate immutable forecasts only against complete, verified FPL outcomes."""
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from model_experiments import metrics
from prospective_lock import digest, utc, verify_lock
from role_models import role_metrics
from probability_diagnostics import calibration_bins

KEYS = ["season", "GW", "player_id", "fixture"]


def score_predictions(predictions, truth):
    # Frozen feature rows may contain season-to-date minutes/starts. These are
    # inputs, never evaluation labels, and must not collide with actual outcomes.
    output_columns = KEYS + ["model", "prediction"] + [
        column for column in predictions if column.startswith(("p_", "prediction_q", "points_"))]
    predictions = predictions[list(dict.fromkeys(output_columns))].copy()
    if truth.duplicated(KEYS).any():
        raise ValueError("Duplicate outcome keys")
    if truth[["target_points", "minutes"]].isna().any().any():
        raise ValueError("Missing outcomes cannot be replaced by zero")
    joined = predictions.merge(truth, on=KEYS, how="left", validate="many_to_one", indicator=True)
    if joined._merge.ne("both").any():
        raise ValueError("Not every frozen player/fixture has an observed outcome")
    reports = []
    for name, frame in joined.groupby("model"):
        report = {"model": name, "rows": len(frame), "fixture_points": metrics(frame.target_points, frame.prediction)}
        weekly = frame.groupby(["season", "GW", "player_id"])[["target_points", "prediction"]].sum()
        report["weekly_points"] = metrics(weekly.target_points, weekly.prediction)
        # These strata use observed minutes for diagnosis, never as model inputs.
        # Signed bias is prediction minus outcome: positive means overprediction.
        bands = np.where(frame.minutes.eq(0), "absent",
                         np.where(frame.minutes.lt(60), "1_59_minutes", "60plus_minutes"))
        report["points_by_observed_minutes"] = {}
        for band in ["absent", "1_59_minutes", "60plus_minutes"]:
            subset = frame.loc[bands == band]
            if subset.empty:
                report["points_by_observed_minutes"][band] = {"rows": 0}
                continue
            report["points_by_observed_minutes"][band] = {
                "rows": len(subset),
                "mean_prediction": float(subset.prediction.mean()),
                "mean_actual": float(subset.target_points.mean()),
                "bias": float((subset.prediction - subset.target_points).mean()),
                **metrics(subset.target_points, subset.prediction),
            }
        for columns, label in [(["p_absent", "p_cameo", "p_start"], "role"),
                               (["p_zero_minutes", "p_1_59_minutes", "p_60plus_minutes"], "minutes")]:
            present = [column for column in columns if column in frame]
            if not present or frame[present].isna().all().all():
                continue
            if len(present) != 3 or frame[columns].isna().any().any():
                raise ValueError("Incomplete frozen probability distribution")
            probabilities = frame[columns].to_numpy(float)
            if (not np.isfinite(probabilities).all() or (probabilities < 0).any()
                    or not np.allclose(probabilities.sum(axis=1), 1)):
                raise ValueError("Invalid frozen probabilities")
            if label == "role":
                report[label] = role_metrics(frame, probabilities)
            else:
                actual = np.where(frame.minutes.eq(0), 0, np.where(frame.minutes.lt(60), 1, 2))
                report[label] = {"log_loss": float(log_loss(actual, probabilities, labels=[0, 1, 2])),
                    "brier_appearance": float(np.mean((1 - probabilities[:, 0] - frame.minutes.gt(0)) ** 2)),
                    "brier_60plus": float(np.mean((probabilities[:, 2] - frame.minutes.ge(60)) ** 2))}
                report[label]["calibration"] = {
                    "appearance": calibration_bins(1 - probabilities[:, 0], frame.minutes.gt(0)),
                    "60plus": calibration_bins(probabilities[:, 2], frame.minutes.ge(60)),
                }
        reports.append(report)
    return reports, joined.drop(columns="_merge")


def read_verified(snapshot, manifest, key):
    entry = manifest["files"][key]
    path = snapshot / entry["file"]
    if entry["status"] != 200 or digest(path) != entry["stored_sha256"]:
        raise ValueError(f"Unverified outcome source: {key}")
    with gzip.open(path, "rt") as handle:
        return json.load(handle), utc(entry["received_at"])


def outcomes_from_snapshot(lock, snapshot):
    snapshot = Path(snapshot)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if manifest.get("status") != "complete" or manifest["season"] != lock["season"]:
        raise ValueError("Wrong season or incomplete outcome snapshot")
    bootstrap, observed = read_verified(snapshot, manifest, "bootstrap")
    event = next(e for e in bootstrap["events"] if int(e["id"]) == lock["GW"])
    if observed <= utc(lock["deadline"]) or not event.get("finished") or not event.get("data_checked"):
        raise ValueError("Gameweek outcomes are not final and checked yet")
    fixtures, _ = read_verified(snapshot, manifest, "fixtures")
    finished = {int(f["id"]) for f in fixtures if f.get("finished") is True}
    rows = []
    for key in manifest["files"]:
        if not key.startswith("player_") or not key[7:].isdigit():
            continue
        player, received = read_verified(snapshot, manifest, key)
        if received <= utc(lock["deadline"]):
            raise ValueError("Player outcomes predate gameweek deadline")
        for match in player["history"]:
            if match["round"] != lock["GW"]:
                continue
            if int(match["fixture"]) not in finished:
                raise ValueError("Unfinished match in outcome history")
            rows.append({"season": lock["season"], "GW": lock["GW"], "player_id": int(key[7:]),
                "fixture": int(match["fixture"]), "target_points": match["total_points"],
                "minutes": match["minutes"], "starts": match.get("starts"),
                "outcome_observed_at": str(received)})
    return pd.DataFrame(rows)


def evaluate(bundle, snapshot, destination):
    bundle, snapshot, destination = Path(bundle), Path(snapshot), Path(destination)
    lock = verify_lock(bundle)
    truth = outcomes_from_snapshot(lock, snapshot)
    predictions = pd.read_csv(bundle / "predictions.csv")
    reports, joined = score_predictions(predictions, truth)
    destination.mkdir(parents=True, exist_ok=False)
    joined.to_csv(destination / "scored_predictions.csv", index=False)
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return None if isinstance(value, float) and not np.isfinite(value) else value
    report = {"bundle": str(bundle), "bundle_manifest_sha256": digest(bundle / "manifest.json"),
        "outcome_snapshot": str(snapshot), "outcome_manifest_sha256": digest(snapshot / "manifest.json"),
        "production_eligible": False, "metrics": reports}
    (destination / "report.json").write_text(json.dumps(clean(report), indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    parser.add_argument("snapshot")
    parser.add_argument("destination")
    args = parser.parse_args()
    evaluate(args.bundle, args.snapshot, args.destination)
