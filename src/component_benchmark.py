"""Chronological evaluation for the structural probabilistic point model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import joblib
import numpy as np
import pandas as pd

from component_models import ComponentPointsModel, COUNT_TARGETS
from decision_backtest import backtest, cached_market, prepare_predictions
from model_lab import KEYS, load_lab_data
from nextgen_models import fit_incumbent, score_prediction


COMPONENT_COLUMNS = list(dict.fromkeys(
    KEYS + ["clean_sheets", "defensive_contribution"] + COUNT_TARGETS
))


def load_component_data(root: Path) -> pd.DataFrame:
    base = load_lab_data(root)
    components = pd.read_csv(
        root / "data" / "processed" / "player_fixture_features.csv",
        usecols=COMPONENT_COLUMNS, low_memory=False,
    )
    if components.duplicated(KEYS).any():
        raise ValueError("Duplicate component target keys")
    return base.merge(components, on=KEYS, how="left", validate="one_to_one")


def without_defcon_points(data: pd.DataFrame) -> pd.DataFrame:
    """Make the 2025-26 holdout comparable to pre-DEFCON training rules."""
    result = data.copy()
    contribution = pd.to_numeric(result.defensive_contribution, errors="coerce")
    threshold = np.where(result.position.eq("DEF"), 10, np.where(
        result.position.isin(["MID", "FWD"]), 12, 999
    ))
    result["target_points"] = result.target_points - 2 * contribution.ge(threshold)
    return result


def _pinball(actual: np.ndarray, forecast: np.ndarray, quantile: float) -> float:
    error = actual - forecast
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


def distribution_report(model: ComponentPointsModel, data: pd.DataFrame,
                        draws: int = 400, batch_size: int = 1000) -> tuple[dict, pd.DataFrame]:
    """Score calibrated uncertainty without allocating one giant draw matrix."""
    chunks = []
    for start in range(0, len(data), batch_size):
        batch = data.iloc[start:start + batch_size]
        distribution = model.predict_distribution(batch, draws=draws, seed=42 + start)
        frame = batch[KEYS + ["target_points", "minutes_avg5"]].copy()
        for name, values in distribution.items():
            frame[name] = values
        chunks.append(frame)
    predictions = pd.concat(chunks, ignore_index=True)

    def metrics(frame: pd.DataFrame) -> dict:
        actual = frame.target_points.to_numpy(float)
        return {
            "rows": len(frame),
            "mean_RMSE": float(np.sqrt(np.mean((actual - frame["mean"]) ** 2))),
            "q10_q90_coverage": float(((actual >= frame.q10) & (actual <= frame.q90)).mean()),
            "q10_q90_width": float((frame.q90 - frame.q10).mean()),
            "pinball_q10": _pinball(actual, frame.q10.to_numpy(float), .1),
            "pinball_q50": _pinball(actual, frame.q50.to_numpy(float), .5),
            "pinball_q90": _pinball(actual, frame.q90.to_numpy(float), .9),
            "brier_5plus": float(np.mean(((actual >= 5) - frame.p5plus) ** 2)),
            "brier_10plus": float(np.mean(((actual >= 10) - frame.p10plus) ** 2)),
        }

    candidate = predictions[predictions.minutes_avg5.ge(45)]
    return {"all_players": metrics(predictions),
            "minutes_avg5_at_least_45": metrics(candidate)}, predictions


def evaluate(root: Path) -> Path:
    data = load_component_data(root)
    rows, reports = [], []
    for season in ["2023-24", "2024-25"]:
        train = data[data.season.isin([
            value for value in ["2020-21", "2021-22", "2022-23", "2023-24"]
            if value < season
        ])].copy()
        evaluation = data[data.season.eq(season)].copy()
        incumbent_train = train[train.season.isin(["2022-23", "2023-24", "2024-25"])]
        for name, model in [
            ("incumbent", fit_incumbent(incumbent_train)),
            ("component", ComponentPointsModel().fit(train)),
        ]:
            prediction = model.predict(evaluation)
            rows.append({"dataset": "validation", "season": season, "model": name,
                         **score_prediction(evaluation, prediction)})
            report = evaluation[KEYS + ["target_points", "position"]].copy()
            report["dataset"], report["model"], report["prediction"] = (
                "validation", name, prediction
            )
            reports.append(report)
            print(f"Completed {name} -> {season}", flush=True)

    holdout = without_defcon_points(data[data.season.eq("2025-26")])
    train = data[data.season.isin(["2020-21", "2021-22", "2022-23", "2023-24", "2024-25"])]
    holdout_rows = []
    component_holdout_model = None
    for name, model in [
        ("incumbent", fit_incumbent(train[train.season.isin(["2022-23", "2023-24", "2024-25"])])),
        ("component", ComponentPointsModel().fit(train)),
    ]:
        prediction = model.predict(holdout)
        holdout_rows.append({"dataset": "holdout_without_defcon", "season": "2025-26",
                             "model": name, **score_prediction(holdout, prediction)})
        report = holdout[KEYS + ["target_points", "position"]].copy()
        report["dataset"], report["model"], report["prediction"] = (
            "holdout_without_defcon", name, prediction
        )
        reports.append(report)
        if name == "component":
            component_holdout_model = model
        print(f"Completed holdout {name}", flush=True)

    # Refit all component tasks, including 2025-26 DEFCON counts, but never mark
    # the unconfirmed model production-eligible.
    refit = ComponentPointsModel().fit(data[data.season.ne("2026-27")])
    destination = Path(tempfile.mkdtemp(
        prefix="component_", dir=root / "artifacts" / "models"
    ))
    folds = pd.DataFrame(rows)
    metrics = ["RMSE", "MAE", "Spearman", "candidate_RMSE", "top25_actual_mean",
               "captain_actual_mean", "ndcg25"]
    folds.to_csv(destination / "validation_folds.csv", index=False)
    folds.groupby("model")[metrics].mean().to_csv(destination / "validation_summary.csv")
    pd.DataFrame(holdout_rows).set_index("model").to_csv(destination / "holdout_metrics.csv")
    all_predictions = pd.concat(reports, ignore_index=True)
    all_predictions.to_csv(destination / "predictions.csv", index=False)
    calibration, probability_predictions = distribution_report(
        component_holdout_model, holdout
    )
    probability_predictions.to_csv(
        destination / "probabilistic_holdout_predictions.csv", index=False
    )
    (destination / "probabilistic_metrics.json").write_text(
        json.dumps(calibration, indent=2)
    )

    validation_predictions = all_predictions[all_predictions.dataset.eq("validation")]
    seasons = sorted(validation_predictions.season.unique())
    markets = {season: cached_market(root, season) for season in seasons}
    prepared = prepare_predictions(
        validation_predictions, markets, ["incumbent", "component"], burn_in=5
    )
    decision_gameweeks, decision_summary, decision_comparison = backtest(
        prepared, ["incumbent", "component"]
    )
    decision_gameweeks.to_csv(destination / "decision_backtest_gameweeks.csv", index=False)
    decision_summary.to_csv(destination / "decision_backtest_summary.csv")
    (destination / "decision_backtest.json").write_text(json.dumps({
        "models": ["incumbent", "component"], "seasons": seasons,
        "burn_in_gameweeks": 5,
        "paired_component_vs_incumbent": decision_comparison,
        "decision_gate": decision_comparison["mean_points_gain_per_gameweek"] >= 0,
        "scope_caveat": "Static weekly squad/XI/captain selection, not a transfer simulation.",
    }, indent=2))
    joblib.dump({
        "model": refit, "model_family": "structural_component_hgb",
        "production_eligible": False,
    }, destination / "model.joblib")
    settings = {
        "production_eligible": False,
        "reason": "Requires prospective validation under the current DEFCON scoring regime",
        "validation_seasons": ["2023-24", "2024-25"],
        "holdout": "2025-26 with observed DEFCON points removed for rule comparability",
        "components": ["minutes", "clean_sheets", "defensive_contribution"] + COUNT_TARGETS,
        "probabilistic_outputs": ["mean", "q10", "q50", "q90", "p5plus", "p10plus"],
        "probabilistic_metrics": calibration,
        "decision_gate": decision_comparison["mean_points_gain_per_gameweek"] >= 0,
    }
    (destination / "settings.json").write_text(json.dumps(settings, indent=2))
    print("\nValidation\n", folds.groupby("model")[metrics].mean().to_string(), flush=True)
    print("\nHoldout\n", pd.DataFrame(holdout_rows).set_index("model").to_string(), flush=True)
    print("Artifact:", destination, flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    evaluate(parser.parse_args().root)
