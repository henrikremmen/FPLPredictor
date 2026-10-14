"""Fit and lock source challengers on the incumbent's already pinned GW rows."""
from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import pandas as pd

from elo_features import ELO_FEATURES, attach_elo, load_results
from prospective_lock import freeze_forecasts, verify_lock
from shot_benchmark import load_source_training_data
from source_challengers import SourceChallenger
from understat_shots import SHOT_FEATURES, attach_shot_features


def run(root, reference, destination):
    root, reference, destination = Path(root), Path(reference), Path(destination)
    manifest = verify_lock(reference)
    observed = datetime.now(timezone.utc).isoformat()
    data = load_source_training_data(root)
    incumbent_path = reference / manifest["models"]["incumbent"]
    incumbent = joblib.load(incumbent_path)["model"]
    live = pd.read_csv(reference / "predictions.csv").copy()
    live["prediction_cutoff"] = observed
    live["team"] = live.team_name
    live = attach_elo(live, load_results(root))
    research = root / "artifacts/model_research"
    live = attach_shot_features(live, pd.read_csv(research / "understat_shot_history.csv"),
        pd.read_csv(research / "understat_identities.csv"), mode="observed")
    training_output = destination.with_name(destination.name + "_training")
    training_output.mkdir(parents=True, exist_ok=False)
    features_path = training_output / "forecast_features.csv"
    live.to_csv(features_path, index=False)
    reports = [pd.read_csv(reference / "predictions.csv")]
    models = {"incumbent": incumbent_path}
    for name, extra in [("understat", SHOT_FEATURES), ("elo", ELO_FEATURES),
                        ("understat_elo", SHOT_FEATURES + ELO_FEATURES)]:
        challenger = SourceChallenger(incumbent, extra).fit(data)
        model_path = training_output / f"{name}.joblib"
        joblib.dump({"model": challenger, "production_eligible": False}, model_path)
        models[name] = model_path
        report = live[["season", "GW", "player_id", "fixture"]].copy()
        report["model"], report["prediction"] = name, challenger.predict(live)
        reports.append(report)
        print(f"Fitted {name}", flush=True)
    sources = [{"path": reference / entry["file"], "received_at": entry.get("received_at", manifest["completed_at"])}
        for entry in manifest["files"] if entry["kind"] != "model"]
    consumed = [research / "understat_shot_history.csv", research / "understat_identities.csv",
        root / "data/processed/player_fixture_features.csv"]
    consumed += list((root / "data-source/data").glob("*/fixtures.csv"))
    consumed += list((root / "data-source/data").glob("*/teams.csv"))
    consumed += list((root / "data/raw/historical_odds/football_data_uk").glob("*.csv"))
    sources += [{"path": path, "received_at": observed} for path in consumed]
    sources.append({"path": features_path, "received_at": datetime.now(timezone.utc).isoformat()})
    result = freeze_forecasts(pd.concat(reports, ignore_index=True), deadline=manifest["deadline"],
        sources=sources, models=models, destination=destination)
    verify_lock(destination)
    print(json.dumps({"rows": result["rows"], "GW": result["GW"], "completed_at": result["completed_at"],
                      "shot_feature_coverage": float(live.us_shot_observations5.notna().mean())}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("destination")
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.reference, args.destination)
