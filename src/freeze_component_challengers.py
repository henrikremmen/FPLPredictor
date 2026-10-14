"""Lock start/cameo/absence and component challengers beside a pinned reference."""
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from component_benchmark import load_component_data
from component_models import CoherentComponentPointsModel
from prospective_lock import freeze_forecasts, verify_lock
from role_models import RoleModel


def live_start_features(reference, manifest, rows):
    result = rows.copy()
    players = {}
    fixtures = None
    for entry in manifest["files"]:
        name = Path(entry.get("original_path", "")).name
        if name == "fixtures.json.gz":
            with gzip.open(reference / entry["file"], "rt") as handle:
                fixtures = json.load(handle)
        if name.startswith("player_") and name.endswith(".json.gz"):
            with gzip.open(reference / entry["file"], "rt") as handle:
                players[int(name.split("_")[1].split(".")[0])] = json.load(handle)
    if fixtures is None:
        raise ValueError("Missing pinned fixture status")
    completed = {int(f["id"]) for f in fixtures if f.get("finished") is True}
    features = {}
    for player_id in result.player_id.unique():
        if player_id not in players:
            raise ValueError("Missing pinned player history")
        history = pd.DataFrame(players[player_id]["history"])
        if history.empty:
            features[player_id] = [np.nan, np.nan, np.nan]
            continue
        history = history[history.fixture.isin(completed)].sort_values(["kickoff_time", "fixture"])
        starts = pd.to_numeric(history.starts, errors="coerce")
        features[player_id] = [starts.tail(3).mean(), starts.tail(10).mean(), starts.sum(min_count=1)]
    for index, name in enumerate(["start_rate3", "start_rate10", "starts_season_before"]):
        result[name] = result.player_id.map(lambda player: features[player][index])
    return result


def run(root, reference, destination):
    root, reference, destination = Path(root), Path(reference), Path(destination)
    manifest = verify_lock(reference)
    training = load_component_data(root)
    training = training[training.season.ge("2020-21") & training.season.le("2025-26")].copy()
    target_path = root / "data/processed/player_fixture_features.csv"
    labels = pd.read_csv(target_path, usecols=["season", "fixture", "player_id", "starts",
        "start_rate3", "start_rate10", "starts_season_before"], low_memory=False)
    training = training.merge(labels, on=["season", "fixture", "player_id"], validate="one_to_one")
    live = live_start_features(reference, manifest, pd.read_csv(reference / "predictions.csv"))
    output = destination.with_name(destination.name + "_training")
    output.mkdir(parents=True, exist_ok=False)
    with threadpool_limits(limits=4):
        role = RoleModel().fit(training[training.season.ge("2022-23")])
        probabilities = role.probabilities(live)
        role_report = live[["season", "GW", "player_id", "fixture", "prediction"]].copy()
        role_report["model"] = "role_probabilities"
        for index, name in enumerate(["p_absent", "p_cameo", "p_start"]):
            role_report[name] = probabilities[:, index]
        joblib.dump({"role_model": role, "points_reference": "incumbent",
            "point_prediction": "unchanged incumbent", "production_eligible": False}, output / "role.joblib")
        print("Role probabilities fitted", flush=True)
        component = CoherentComponentPointsModel().fit(training)
        component_report = live[["season", "GW", "player_id", "fixture"]].copy()
        component_report["prediction"] = component.predict(live)
        component_report["model"] = "component_v2"
        values = component.predict_components(live)["minutes_probability"]
        component_report["p_zero_minutes"], component_report["p_1_59_minutes"] = values[:, 0], values[:, 1]
        component_report["p_60plus_minutes"] = values[:, 2:].sum(axis=1)
        contributions = component.point_contributions(live).add_prefix("points_")
        component_report = pd.concat([component_report.reset_index(drop=True), contributions.reset_index(drop=True)], axis=1)
        joblib.dump({"model": component, "production_eligible": False}, output / "component.joblib")
        print(f"Component model fitted; defensive contributions enabled={component.has_defcon}", flush=True)
    feature_path = output / "forecast_features.csv"
    live.to_csv(feature_path, index=False)
    sources = [{"path": reference / entry["file"], "received_at": entry.get("received_at", manifest["completed_at"])}
        for entry in manifest["files"] if entry["kind"] != "model"]
    observed = datetime.now(timezone.utc).isoformat()
    sources.extend([{"path": target_path, "received_at": observed}, {"path": feature_path, "received_at": observed}])
    result = freeze_forecasts(pd.concat([pd.read_csv(reference / "predictions.csv"), role_report, component_report], ignore_index=True),
        deadline=manifest["deadline"], sources=sources,
        models={"incumbent": reference / manifest["models"]["incumbent"],
                "role_probabilities": output / "role.joblib", "component_v2": output / "component.joblib"},
        destination=destination)
    verify_lock(destination)
    print(json.dumps({"rows": result["rows"], "GW": result["GW"], "completed_at": result["completed_at"]}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("destination")
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.reference, args.destination)
