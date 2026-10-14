"""Isolate the v2 scoring correction using identical fitted component models."""
import json
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from component_benchmark import load_component_data, without_defcon_points
from component_models import ComponentPointsModel, CoherentComponentPointsModel
from model_experiments import metrics


def run(root):
    root = Path(root)
    data = load_component_data(root)
    reports = []
    contributions = []
    for season in ["2023-24", "2024-25", "2025-26"]:
        train = data[data.season.ge("2020-21") & data.season.lt(season)]
        test = data[data.season.eq(season)].copy()
        if season == "2025-26":
            test = without_defcon_points(test)
        with threadpool_limits(limits=4):
            old = ComponentPointsModel().fit(train)
            challenger = CoherentComponentPointsModel()
            challenger.__dict__.update(old.__dict__)
            for name, model in [("component_v1", old), ("component_v2", challenger)]:
                report = {"season": season, "model": name, "rows": len(test),
                          **metrics(test.target_points, model.predict(test))}
                reports.append(report)
                print(json.dumps(report), flush=True)
            frame = challenger.point_contributions(test)
        frame["position"] = test.position
        by_position = frame.groupby("position").mean().reset_index()
        by_position["season"] = season
        contributions.append(by_position)
    destination = root / "artifacts/model_research"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "component_coherence.json").write_text(json.dumps({
        "production_eligible": False, "status": "retrospective_diagnostic_not_deadline_certified",
        "test_2025_26": "defensive contribution points removed to match training-era rules",
        "scope": "v1 vs v2 scoring with identical fitted components, not incumbent comparison",
        "folds": reports}, indent=2))
    pd.concat(contributions).to_csv(destination / "component_contributions.csv", index=False)


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[1])
