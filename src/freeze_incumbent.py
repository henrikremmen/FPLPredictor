"""Recompute and lock the approved model on an earlier snapshot's future rows."""
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

from capture_fpl import score_rows
from prospective_lock import digest, freeze_forecasts, verify_lock


def run(snapshot, destination, event):
    snapshot = Path(snapshot)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    model_path = Path(manifest["model_path"])
    if digest(model_path) != manifest["model_sha256"]:
        raise ValueError("Approved model has changed since source forecast")
    sources = []
    for record in manifest["files"].values():
        if record.get("status") != 200 or not record.get("file"):
            continue
        source = snapshot / record["file"]
        if digest(source) != record["stored_sha256"]:
            raise ValueError(f"Changed snapshot source: {source.name}")
        sources.append({"path": source, "received_at": record["received_at"]})
    with gzip.open(snapshot / "bootstrap.json.gz", "rt") as handle:
        bootstrap = json.load(handle)
    target = next(item for item in bootstrap["events"] if int(item["id"]) == event)
    features_path = snapshot / "horizon_fixture_forecast.csv"
    features = pd.read_csv(features_path)
    features = features[features.GW.eq(event)].copy()
    if features.empty:
        raise ValueError("No feature rows for requested event")
    if features.fixture.isna().any():
        raise ValueError("Blank-round identity convention must be added before locking this event")
    source_cutoff = pd.Timestamp(manifest["forecast_at"])
    if source_cutoff >= pd.Timestamp(target["deadline_time"]):
        raise ValueError("Feature snapshot was not available before requested deadline")
    sources.append({"path": features_path, "received_at": manifest["forecast_at"]})
    sources.append({"path": snapshot / "manifest.json", "received_at": datetime.now(timezone.utc).isoformat()})
    bundle = joblib.load(model_path)
    with threadpool_limits(limits=4):
        predictions = score_rows(bundle["model"], features)
    predictions["model"] = "incumbent"
    predictions["feature_snapshot_at"] = manifest["forecast_at"]
    predictions["training_caveat"] = "historical pre-fixture training; snapshot older than lock"
    freeze_forecasts(predictions, deadline=target["deadline_time"], sources=sources,
        models={"incumbent": model_path}, destination=destination)
    return verify_lock(destination)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("destination")
    parser.add_argument("--event", type=int, required=True)
    args = parser.parse_args()
    result = run(args.snapshot, args.destination, args.event)
    print(json.dumps({key: result[key] for key in ["status", "GW", "rows", "completed_at", "deadline"]}, indent=2))
