"""Build a decision-guarded production model from evaluated components."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import joblib
from improved_models import PointsModel, ProductionModel, QuantilePointsModel, enrich
from model_experiments import load_data
from nextgen_models import CANDIDATES, SEASON_ORDER


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_evaluation(root: Path) -> Path:
    candidates = []
    for report_path in root.glob("artifacts/models/nextgen_*/decision_backtest.json"):
        settings_path = report_path.parent / "settings.json"
        if not settings_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text())
            settings = json.loads(settings_path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if settings.get("production_eligible") is True and "decision_gate" in report:
            candidates.append(report_path.parent)
    if not candidates:
        raise FileNotFoundError("No point- and decision-evaluated nextgen artifact")
    return max(candidates, key=lambda path: (path / "decision_backtest.json").stat().st_mtime)


def build(root: Path, evaluation: Path | None = None) -> Path:
    root = Path(root)
    evaluation = evaluation or latest_evaluation(root)
    settings_path = evaluation / "settings.json"
    decision_path = evaluation / "decision_backtest.json"
    settings = json.loads(settings_path.read_text())
    decision = json.loads(decision_path.read_text())
    uncertainty_path = evaluation / "uncertainty_evaluation.json"
    uncertainty_report = (
        json.loads(uncertainty_path.read_text()) if uncertainty_path.exists() else {}
    )
    winner = str(settings["winner"])
    points_family = winner if decision["deployment_eligible"] else "incumbent_blend"

    data, _ = load_data(root)
    data = enrich(data)
    point_start = CANDIDATES[points_family]["start"]
    point_seasons = SEASON_ORDER[SEASON_ORDER.index(point_start):]
    probability_seasons = SEASON_ORDER[SEASON_ORDER.index("2020-21"):]
    point_train = data[data["season"].isin(point_seasons)]
    probability_train = data[data["season"].isin(probability_seasons)]
    if point_train.empty or probability_train.empty:
        raise ValueError("No completed-season rows available for production refit")

    points_model = CANDIDATES[points_family]["factory"](point_train)
    if points_family == "long_history_mixture_15":
        probability_model = points_model
    else:
        probability_model = PointsModel(
            "mixture", 7, True, classifier_leaves=15
        ).fit(probability_train)
    uncertainty_model = None
    if uncertainty_report.get("evaluation_eligible") is True:
        uncertainty_model = QuantilePointsModel().fit(probability_train)
    model = ProductionModel(points_model, probability_model, uncertainty_model)

    parent = root / "artifacts/models"
    parent.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="production_", dir=parent))
    family = (points_family if points_family == "long_history_mixture_15" else
              f"{points_family}+minutes_mixture_15")
    if uncertainty_model is not None:
        family += "+quantile_hgb"
    bundle = {
        "model": model,
        "model_family": family,
        "points_model_family": points_family,
        "probability_model_family": "long_history_mixture_15",
        "uncertainty_model_family": (
            "conditional_quantile_hgb_10_50_90" if uncertainty_model is not None else None
        ),
        "production_eligible": True,
    }
    joblib.dump(bundle, destination / "model.joblib")
    production_settings = {
        "production_eligible": True,
        "points_model_family": points_family,
        "probability_model_family": "long_history_mixture_15",
        "uncertainty_model_family": (
            "conditional_quantile_hgb_10_50_90" if uncertainty_model is not None else None
        ),
        "selection_reason": (
            "candidate passed constrained decision gate" if decision["deployment_eligible"] else
            "candidate failed constrained decision gate; guarded fallback to incumbent"
        ),
        "point_training_seasons": point_seasons,
        "probability_training_seasons": probability_seasons,
        "uncertainty_training_seasons": probability_seasons if uncertainty_model is not None else [],
        "point_training_rows": int(len(point_train)),
        "probability_training_rows": int(len(probability_train)),
        "uncertainty_training_rows": (
            int(len(probability_train)) if uncertainty_model is not None else 0
        ),
        "evaluation_artifact": str(evaluation.resolve()),
        "evaluation_settings_sha256": _sha256(settings_path),
        "decision_backtest_sha256": _sha256(decision_path),
        "uncertainty_evaluation_sha256": (
            _sha256(uncertainty_path) if uncertainty_path.exists() else None
        ),
        "decision_gate": bool(decision["decision_gate"]),
        "candidate": winner,
    }
    (destination / "settings.json").write_text(json.dumps(production_settings, indent=2))
    print(json.dumps(production_settings, indent=2), flush=True)
    print("Production artifact:", destination, flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--evaluation", type=Path)
    arguments = parser.parse_args()
    build(arguments.root, arguments.evaluation)
