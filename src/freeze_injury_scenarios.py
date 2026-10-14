"""Freeze static-flag and dated-return point adjustments for future evaluation."""
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import joblib
import pandas as pd

from availability_forecast import AvailabilityScenarioModel, availability_scenarios
from prospective_lock import freeze_forecasts, verify_lock


def run(reference, destination):
    reference, destination = Path(reference), Path(destination)
    manifest = verify_lock(reference)
    def source(name):
        entry = next(e for e in manifest["files"] if Path(e.get("original_path", "")).name == name)
        with gzip.open(reference / entry["file"], "rt") as handle:
            return json.load(handle), entry["received_at"]
    bootstrap, observed = source("bootstrap.json.gz")
    fixtures, _ = source("fixtures.json.gz")
    next_event = next(int(e["id"]) for e in bootstrap["events"] if e.get("is_next"))
    profile = pd.concat([availability_scenarios(p, fixtures, observed, next_event)
        for p in bootstrap["elements"] if p["element_type"] in [1, 2, 3, 4]], ignore_index=True)
    original = pd.read_csv(reference / "predictions.csv")
    keys = ["season", "GW", "player_id", "fixture"]
    rows = original[keys + ["prediction"]].merge(profile, on=["GW", "player_id", "fixture"], validate="one_to_one", how="left")
    output = destination.with_name(destination.name + "_inputs")
    output.mkdir(parents=True, exist_ok=False)
    rows.to_csv(output / "scenario_inputs.csv", index=False)
    predictions = [original]
    models = {"incumbent": reference / manifest["models"]["incumbent"]}
    for scenario in ["conservative", "reported_return"]:
        model = AvailabilityScenarioModel(scenario)
        name = "availability_" + scenario
        report = rows[keys].copy()
        report["model"], report["prediction"] = name, model.predict(rows)
        predictions.append(report)
        models[name] = output / f"{name}.joblib"
        joblib.dump({"model": model, "calibrated": False, "production_eligible": False}, models[name])
    sources = [{"path": reference / e["file"], "received_at": e.get("received_at", manifest["completed_at"])}
        for e in manifest["files"] if e["kind"] != "model"]
    sources.append({"path": output / "scenario_inputs.csv", "received_at": datetime.now(timezone.utc).isoformat()})
    lock = freeze_forecasts(pd.concat(predictions, ignore_index=True), deadline=manifest["deadline"],
        sources=sources, models=models, destination=destination)
    verify_lock(destination)
    print(json.dumps({"GW": lock["GW"], "rows": lock["rows"], "completed_at": lock["completed_at"],
        "changed_players": int(rows.loc[rows.conservative_factor.ne(rows.reported_return_factor), "player_id"].nunique())}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("destination")
    args = parser.parse_args()
    run(args.reference, args.destination)
