"""Chronologically evaluate conditional FPL point quantiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_pinball_loss

from decision_backtest import latest_evaluation_artifact
from improved_models import QuantilePointsModel, enrich
from model_experiments import TARGET, load_data, split


QUANTILES = (.1, .5, .9)


def score_fold(train: pd.DataFrame, validation: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    model = QuantilePointsModel().fit(train)
    prediction = model.predict_quantiles(validation)
    baseline = np.column_stack([
        validation["position"].map(train.groupby("position")[TARGET].quantile(level)).fillna(
            train[TARGET].quantile(level)
        ) for level in QUANTILES
    ])
    actual = validation[TARGET].to_numpy(dtype=float)
    candidate = validation["minutes_avg5"].ge(60).to_numpy()
    metrics = {}
    for index, level in enumerate(QUANTILES):
        label = int(level * 100)
        metrics[f"pinball_q{label}"] = mean_pinball_loss(
            actual, prediction[:, index], alpha=level
        )
        metrics[f"baseline_pinball_q{label}"] = mean_pinball_loss(
            actual, baseline[:, index], alpha=level
        )
    inside = (actual >= prediction[:, 0]) & (actual <= prediction[:, 2])
    metrics.update(
        coverage_q10_q90=float(inside.mean()),
        candidate_coverage_q10_q90=float(inside[candidate].mean()),
        mean_interval_width=float(np.mean(prediction[:, 2] - prediction[:, 0])),
        n_validation=int(len(validation)),
        n_candidates=int(candidate.sum()),
    )
    rows = validation[["season", "GW", "fixture", "player_id", TARGET]].copy()
    for index, label in enumerate([10, 50, 90]):
        rows[f"q{label}"] = prediction[:, index]
    return metrics, rows


def evaluate(root: Path, artifact: Path | None = None) -> Path:
    artifact = artifact or latest_evaluation_artifact(root)
    data, _ = load_data(root)
    data = enrich(data)
    folds, predictions = [], []
    for season in ["2023-24", "2024-25"]:
        train_seasons = ["2020-21", "2021-22", "2022-23"]
        if season == "2024-25":
            train_seasons.append("2023-24")
        train, validation = split(data, train_seasons, season)
        metrics, rows = score_fold(train, validation)
        folds.append({"season": season, **metrics})
        predictions.append(rows)
        print(f"Completed quantile fold {season}", flush=True)
    fold_frame = pd.DataFrame(folds)
    test_train, test = split(
        data, ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25"], "2025-26"
    )
    test_metrics, test_predictions = score_fold(test_train, test)
    model_losses = fold_frame[["pinball_q10", "pinball_q50", "pinball_q90"]].mean()
    baseline_losses = fold_frame[[
        "baseline_pinball_q10", "baseline_pinball_q50", "baseline_pinball_q90"
    ]].mean()
    loss_checks = {
        f"q{label}_beats_position_baseline": bool(model_losses.iloc[index] < baseline_losses.iloc[index])
        for index, label in enumerate([10, 50, 90])
    }
    coverage = float(fold_frame["candidate_coverage_q10_q90"].mean())
    checks = {
        **loss_checks,
        "candidate_coverage_at_least_80pct": coverage >= .80,
        "candidate_coverage_below_95pct": coverage <= .95,
        **{
            f"test_q{label}_beats_position_baseline": bool(
                test_metrics[f"pinball_q{label}"] <
                test_metrics[f"baseline_pinball_q{label}"]
            ) for label in [10, 50, 90]
        },
    }
    report = {
        "model_family": "conditional_quantile_hgb_10_50_90",
        "validation_seasons": ["2023-24", "2024-25"],
        "quantiles": list(QUANTILES),
        "baseline": "within-training-season position-specific unconditional quantiles",
        "checks": checks,
        "evaluation_eligible": all(checks.values()),
        "mean_candidate_coverage_q10_q90": coverage,
        "test_season": "2025-26 (previously explored by the project)",
        "test_metrics": test_metrics,
        "interpretation": "Conditional point quantiles, not a guaranteed confidence interval.",
    }
    fold_frame.to_csv(artifact / "uncertainty_validation_folds.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_csv(
        artifact / "uncertainty_validation_predictions.csv", index=False
    )
    test_predictions.to_csv(artifact / "uncertainty_test_predictions.csv", index=False)
    (artifact / "uncertainty_evaluation.json").write_text(json.dumps(report, indent=2))
    print("\n", fold_frame.to_string(index=False), flush=True)
    print("\n", json.dumps(report, indent=2), flush=True)
    print("\nArtifact:", artifact, flush=True)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifact", type=Path)
    arguments = parser.parse_args()
    evaluate(arguments.root, arguments.artifact)
