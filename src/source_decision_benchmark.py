"""Run source challengers through legal static squad/XI/captain selection.

Historical prices and fixture-shifted features are not deadline certified.
This diagnostic does not model transfers, chips or automatic substitutions.
"""
import json
from pathlib import Path

import pandas as pd

from decision_backtest import backtest, cached_market, paired_bootstrap, prepare_predictions


def validate_comparison(frame, models):
    keys = ["season", "GW", "player_id"]
    reference = None
    for model in models:
        rows = frame[frame.model.eq(model)]
        if rows.empty or rows.duplicated(keys).any():
            raise ValueError("Missing model or duplicate weekly player forecasts")
        evidence = rows.set_index(keys)[["actual_points", "position", "team", "value"]].sort_index()
        if reference is None:
            reference = evidence
        elif not evidence.equals(reference):
            raise ValueError("Models do not share identical players, outcomes and market metadata")


def run(root):
    root = Path(root)
    destination = root / "artifacts/model_research"
    predictions = pd.read_csv(destination / "shot_benchmark_predictions.csv")
    keys = ["season", "fixture", "player_id"]
    metadata = pd.read_csv(root / "data/processed/player_fixture_features.csv",
        usecols=keys + ["position"], low_memory=False)
    metadata.position = metadata.position.replace({"GKP": "GK"})
    predictions = predictions.merge(metadata, on=keys, how="left", validate="many_to_one")
    if predictions.position.isna().any():
        raise ValueError("Missing prediction position")
    models = ["market_elo0_shots0", "market_elo0_shots1", "market_elo1_shots0", "market_elo1_shots1"]
    markets = {season: cached_market(root, season) for season in predictions.season.unique()}
    prepared = prepare_predictions(predictions, markets, models, burn_in=5)
    validate_comparison(prepared, models)
    gameweeks, summary, _ = backtest(prepared, models)
    comparisons = [paired_bootstrap(gameweeks, candidate, models[0]) for candidate in models[1:]]
    gameweeks.to_csv(destination / "source_decision_gameweeks.csv", index=False)
    summary.to_csv(destination / "source_decision_summary.csv")
    report = {"production_eligible": False, "status": "retrospective_not_deadline_certified",
        "scope": "independent 100m squad each GW; legal XI, captain, position and club constraints",
        "limitations": ["post-GW prices", "fixture-shifted baseline features", "retrospective external data",
                        "no transfers, chips, autosubs, vice-captain or evolving team value"],
        "burn_in": 5, "comparisons": comparisons}
    (destination / "source_decision_report.json").write_text(json.dumps(report, indent=2))
    print(summary.to_string(), flush=True)
    print(json.dumps(comparisons, indent=2), flush=True)


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[1])
