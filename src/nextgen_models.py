"""Reproducible next-generation model benchmark and guarded promotion.

The benchmark keeps the existing chronological protocol, adds decision-facing
metrics, and compares the incumbent ensemble with longer-history, position-wise,
and tree-ensemble alternatives. A candidate advances to the separate constrained
decision gate only when it improves both ordinary error and FPL candidate
metrics on validation and the already-explored holdout. Evaluation artifacts
are not selected directly for live forecasts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

from improved_models import Blend, EXTRA, PointsModel, enrich, minutes_class
from model_experiments import FEATURE_SETS, TARGET, load_data, metrics, split


SEASON_ORDER = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
KEYS = ["season", "GW", "fixture", "player_id"]


class PositionWiseModel:
    """Fit an independent points model for each FPL position."""

    def __init__(self, kind: str = "mixture", leaves: int = 7, extended: bool = True):
        self.kind, self.leaves, self.extended = kind, leaves, extended

    def fit(self, data: pd.DataFrame):
        self.models = {
            position: PointsModel(self.kind, self.leaves, self.extended).fit(group)
            for position, group in data.groupby("position")
        }
        return self

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        result = np.full(len(data), np.nan)
        for position, model in self.models.items():
            mask = data["position"].eq(position).to_numpy()
            result[mask] = model.predict(data.loc[mask])
        if not np.isfinite(result).all():
            raise ValueError("Position model could not score every row")
        return result


class ExtraTreesPointsModel:
    """Non-boosted tree ensemble benchmark using the production feature set."""

    def __init__(self, trees: int = 200, min_leaf: int = 30):
        self.trees, self.min_leaf = trees, min_leaf

    def fit(self, data: pd.DataFrame):
        self.cols = FEATURE_SETS["context"] + EXTRA
        numeric = [column for column in self.cols if column != "position"]
        prep = ColumnTransformer([
            ("numeric", SimpleImputer(strategy="median", add_indicator=True), numeric),
            ("position", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["position"]),
        ])
        self.model = Pipeline([
            ("preprocess", prep),
            ("model", ExtraTreesRegressor(
                n_estimators=self.trees,
                min_samples_leaf=self.min_leaf,
                max_features=1.0,
                n_jobs=4,
                random_state=42,
            )),
        ])
        with threadpool_limits(limits=4):
            self.model.fit(data[self.cols], data[TARGET])
        return self

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        with threadpool_limits(limits=4):
            return self.model.predict(data[self.cols])


def incumbent_model() -> Blend:
    return Blend([
        PointsModel("ridge", 7, False),
        PointsModel("hgb", 7, True),
        PointsModel("mixture", 7, True),
    ])


def fit_incumbent(train: pd.DataFrame) -> Blend:
    model = incumbent_model()
    model.models = [part.fit(train) for part in model.models]
    return model


CANDIDATES = {
    "incumbent_blend": {"start": "2022-23", "factory": fit_incumbent},
    "long_history_mixture": {
        "start": "2020-21", "factory": lambda data: PointsModel("mixture", 7, True).fit(data)
    },
    "long_history_mixture_15": {
        "start": "2020-21",
        "factory": lambda data: PointsModel(
            "mixture", 7, True, classifier_leaves=15
        ).fit(data),
    },
    "long_history_hgb": {
        "start": "2020-21", "factory": lambda data: PointsModel("hgb", 7, False).fit(data)
    },
    "long_history_ridge": {
        "start": "2020-21", "factory": lambda data: PointsModel("ridge", 7, False).fit(data)
    },
    "position_mixture": {
        "start": "2022-23", "factory": lambda data: PositionWiseModel().fit(data)
    },
    "extra_trees": {
        "start": "2022-23", "factory": lambda data: ExtraTreesPointsModel().fit(data)
    },
}


def training_seasons(start: str, before: str) -> list[str]:
    start_index, end_index = SEASON_ORDER.index(start), SEASON_ORDER.index(before)
    return SEASON_ORDER[start_index:end_index]


def _ndcg(actual: np.ndarray, prediction: np.ndarray, k: int = 25) -> float:
    relevance = np.clip(np.asarray(actual, dtype=float), 0, None)
    prediction = np.asarray(prediction, dtype=float)
    k = min(k, len(relevance))
    if not k or relevance.sum() == 0:
        return np.nan
    discount = 1 / np.log2(np.arange(2, k + 2))
    chosen = np.argsort(-prediction, kind="stable")[:k]
    ideal = np.argsort(-relevance, kind="stable")[:k]
    denominator = float(np.sum(relevance[ideal] * discount))
    return float(np.sum(relevance[chosen] * discount) / denominator) if denominator else np.nan


def decision_metrics(data: pd.DataFrame, prediction: np.ndarray) -> dict[str, float]:
    """Evaluate the actual candidate-selection task, not only row error."""
    rows = data[["season", "GW", "player_id", TARGET, "minutes_avg5"]].copy()
    rows["prediction"] = prediction
    weekly = rows.groupby(["season", "GW", "player_id"], as_index=False).agg(
        target_points=(TARGET, "sum"),
        prediction=("prediction", "sum"),
        minutes_avg5=("minutes_avg5", "first"),
    )
    top_values, captains, ndcgs = [], [], []
    for _, group in weekly.groupby(["season", "GW"]):
        candidates = group[group["minutes_avg5"].ge(60)].sort_values(
            ["prediction", "player_id"], ascending=[False, True]
        )
        if candidates.empty:
            continue
        top_values.append(float(candidates.head(25)[TARGET].mean()))
        captains.append(float(candidates.iloc[0][TARGET]))
        ndcgs.append(_ndcg(candidates[TARGET].to_numpy(), candidates["prediction"].to_numpy()))
    return {
        "top25_actual_mean": float(np.nanmean(top_values)),
        "captain_actual_mean": float(np.nanmean(captains)),
        "ndcg25": float(np.nanmean(ndcgs)),
        "decision_gameweeks": len(top_values),
    }


def probability_metrics(data: pd.DataFrame, probability: np.ndarray | None) -> dict[str, float]:
    if probability is None:
        return {"minutes_log_loss": np.nan, "brier_60plus": np.nan,
                "brier_appearance": np.nan, "ece_60plus": np.nan}
    actual = minutes_class(data)
    p60 = probability[:, 2]
    played = probability[:, 1] + probability[:, 2]
    bins = pd.cut(p60, np.linspace(0, 1, 11), include_lowest=True, labels=False)
    calibration = pd.DataFrame({"bin": bins, "predicted": p60, "actual": actual == 2})
    grouped = calibration.groupby("bin", observed=True).agg(
        predicted=("predicted", "mean"), actual=("actual", "mean"), n=("actual", "size"))
    ece = np.average((grouped.predicted - grouped.actual).abs(), weights=grouped.n)
    return {
        "minutes_log_loss": log_loss(actual, probability, labels=[0, 1, 2]),
        "brier_60plus": float(np.mean((p60 - (actual == 2)) ** 2)),
        "brier_appearance": float(np.mean((played - (actual > 0)) ** 2)),
        "ece_60plus": float(ece),
    }


def score_prediction(data: pd.DataFrame, prediction: np.ndarray,
                     probability: np.ndarray | None = None) -> dict[str, float]:
    eligible = data["minutes_avg5"].ge(60)
    high_return = data[TARGET].ge(5)  # diagnostic cohort only; never used at inference
    return {
        **metrics(data[TARGET], prediction),
        "candidate_RMSE": metrics(data.loc[eligible, TARGET], prediction[eligible])["RMSE"],
        "high_return_RMSE": metrics(data.loc[high_return, TARGET], prediction[high_return])["RMSE"],
        **decision_metrics(data, prediction),
        **probability_metrics(data, probability),
    }


def model_probabilities(model, data: pd.DataFrame) -> np.ndarray | None:
    """Return mixture probabilities; direct regressors expose no classifier."""
    method = getattr(model, "probabilities", None)
    if method is None:
        return None
    return method(data)


def compare(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    folds, predictions = [], []
    for validation_season in ["2023-24", "2024-25"]:
        for name, config in CANDIDATES.items():
            seasons = training_seasons(config["start"], validation_season)
            train, validation = split(data, seasons, validation_season)
            started = time.monotonic()
            model = config["factory"](train)
            prediction = model.predict(validation)
            probability = model_probabilities(model, validation)
            folds.append({
                "model": name,
                "season": validation_season,
                "history_start": config["start"],
                "n_train": len(train),
                "n_validation": len(validation),
                "seconds": time.monotonic() - started,
                **score_prediction(validation, prediction, probability),
            })
            report = validation[KEYS + ["position", "minutes_avg5", TARGET]].copy()
            report["model"], report["prediction"] = name, prediction
            for index, column in enumerate(["p_zero_minutes", "p_1_59_minutes", "p_60plus_minutes"]):
                report[column] = probability[:, index] if probability is not None else np.nan
            predictions.append(report)
            print(f"Completed {name}: {validation_season}", flush=True)
    fold_frame = pd.DataFrame(folds)
    summary = fold_frame.groupby("model").agg(
        history_start=("history_start", "first"),
        RMSE=("RMSE", "mean"),
        MAE=("MAE", "mean"),
        Spearman=("Spearman", "mean"),
        candidate_RMSE=("candidate_RMSE", "mean"),
        high_return_RMSE=("high_return_RMSE", "mean"),
        top25_actual_mean=("top25_actual_mean", "mean"),
        captain_actual_mean=("captain_actual_mean", "mean"),
        ndcg25=("ndcg25", "mean"),
        minutes_log_loss=("minutes_log_loss", "mean"),
        brier_60plus=("brier_60plus", "mean"),
        brier_appearance=("brier_appearance", "mean"),
        ece_60plus=("ece_60plus", "mean"),
        seconds=("seconds", "sum"),
    ).sort_values(["RMSE", "candidate_RMSE"])
    return fold_frame, summary, pd.concat(predictions, ignore_index=True)


def paired_gameweek_bootstrap(predictions: pd.DataFrame, candidate: str,
                              reference: str = "incumbent_blend", draws: int = 4000) -> dict:
    index = KEYS
    incumbent = predictions[predictions.model.eq(reference)].set_index(index)
    challenger = predictions[predictions.model.eq(candidate)].set_index(index).reindex(incumbent.index)
    if challenger["prediction"].isna().any():
        raise ValueError("Candidate and incumbent evaluation rows differ")
    gain = ((incumbent.prediction - incumbent[TARGET]) ** 2 -
            (challenger.prediction - challenger[TARGET]) ** 2)
    blocks = gain.groupby(level=["season", "GW"]).agg(["sum", "count"])
    rng = np.random.default_rng(42)
    sampled = rng.integers(0, len(blocks), size=(draws, len(blocks)))
    values = (blocks["sum"].to_numpy()[sampled].sum(axis=1) /
              blocks["count"].to_numpy()[sampled].sum(axis=1))
    return {
        "MSE_gain": float(gain.mean()),
        "low_95": float(np.quantile(values, 0.025)),
        "high_95": float(np.quantile(values, 0.975)),
        "blocks": len(blocks),
    }


def promotion_decision(validation: pd.DataFrame, test: pd.DataFrame,
                       candidate: str, reference: str = "incumbent_blend") -> tuple[bool, dict]:
    v_candidate, v_reference = validation.loc[candidate], validation.loc[reference]
    t_candidate, t_reference = test.loc[candidate], test.loc[reference]
    checks = {
        "validation_RMSE": bool(v_candidate.RMSE < v_reference.RMSE),
        "validation_candidate_RMSE": bool(v_candidate.candidate_RMSE < v_reference.candidate_RMSE),
        "validation_top25": bool(v_candidate.top25_actual_mean >= v_reference.top25_actual_mean),
        "test_RMSE": bool(t_candidate.RMSE <= t_reference.RMSE),
        "test_candidate_RMSE": bool(t_candidate.candidate_RMSE <= t_reference.candidate_RMSE),
        "test_top25": bool(t_candidate.top25_actual_mean >= t_reference.top25_actual_mean),
    }
    probability_reference = "long_history_mixture"
    if (candidate != probability_reference and probability_reference in validation.index and
            probability_reference in test.index and "minutes_log_loss" in validation):
        checks["validation_minutes_log_loss"] = bool(
            v_candidate.minutes_log_loss <= validation.loc[probability_reference].minutes_log_loss
        )
        checks["test_minutes_log_loss"] = bool(
            t_candidate.minutes_log_loss <= test.loc[probability_reference].minutes_log_loss
        )
    return all(checks.values()), checks


def final_run(root: Path, data: pd.DataFrame, folds: pd.DataFrame,
              summary: pd.DataFrame, oof: pd.DataFrame) -> tuple[Path, pd.DataFrame, dict]:
    winner = str(summary.index[0])
    test_rows, test_predictions, fitted = [], [], {}
    for name in list(dict.fromkeys(["incumbent_blend", "long_history_mixture", winner])):
        if name in fitted:
            continue
        config = CANDIDATES[name]
        train, test = split(data, training_seasons(config["start"], "2025-26"), "2025-26")
        model = config["factory"](train)
        prediction = model.predict(test)
        probability = model_probabilities(model, test)
        fitted[name] = model
        test_rows.append({"model": name, **score_prediction(test, prediction, probability)})
        report = test[KEYS + ["name", "position", "minutes_avg5", TARGET]].copy()
        report["model"], report["prediction"] = name, prediction
        for index, column in enumerate(["p_zero_minutes", "p_1_59_minutes", "p_60plus_minutes"]):
            report[column] = probability[:, index] if probability is not None else np.nan
        test_predictions.append(report)
    test_scores = pd.DataFrame(test_rows).set_index("model")
    promoted, checks = promotion_decision(summary, test_scores, winner)
    bootstrap = paired_gameweek_bootstrap(oof, winner)

    parent = root / "artifacts" / "models"
    parent.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="nextgen_", dir=parent))
    folds.to_csv(destination / "validation_folds.csv", index=False)
    summary.to_csv(destination / "validation_summary.csv")
    oof.to_csv(destination / "validation_predictions.csv", index=False)
    test_scores.to_csv(destination / "test_metrics.csv")
    test_prediction_frame = pd.concat(test_predictions, ignore_index=True)
    test_prediction_frame.to_csv(
        destination / "test_predictions.csv", index=False
    )
    calibration_source = pd.concat([
        oof.assign(dataset="validation"), test_prediction_frame.assign(dataset="test")
    ], ignore_index=True)
    calibration_source = calibration_source[
        calibration_source.model.eq(winner) & calibration_source.p_60plus_minutes.notna()
    ].copy()
    calibration_source["probability_bin"] = pd.cut(
        calibration_source.p_60plus_minutes, np.linspace(0, 1, 11), include_lowest=True
    )
    # Target minutes are not retained in compact OOF reports; reconstruct the
    # observed class from the source data using the unique fixture keys.
    actual_minutes = data.set_index(KEYS)["minutes"]
    calibration_source["observed_60plus"] = (
        calibration_source.set_index(KEYS).index.map(actual_minutes).to_numpy() >= 60
    )
    calibration = calibration_source.groupby(
        ["dataset", "probability_bin"], observed=True, as_index=False
    ).agg(mean_probability=("p_60plus_minutes", "mean"),
          observed_60plus=("observed_60plus", "mean"), n=("player_id", "size"))
    calibration.to_csv(destination / "minutes_calibration.csv", index=False)
    bundle = {
        "model": fitted[winner],
        "raw_features": FEATURE_SETS["context"],
        "preprocessing": "Call improved_models.enrich before predict",
        "model_family": winner,
        "history_start": CANDIDATES[winner]["start"],
        "production_eligible": promoted,
        "eligibility_scope": "eligible for constrained decision gate; requires production refit",
    }
    joblib.dump(bundle, destination / "model.joblib")
    settings = {
        "winner": winner,
        "incumbent": "incumbent_blend",
        "selection": "lowest mean seasonal validation RMSE; decision metrics are promotion gates",
        "validation_seasons": ["2023-24", "2024-25"],
        "test_season": "2025-26 (previously explored; not a pristine confirmation set)",
        "production_eligible": promoted,
        "eligibility_scope": "eligible for constrained decision gate; requires production refit",
        "promotion_checks": checks,
        "paired_validation_bootstrap": bootstrap,
        "timing": "pre-fixture historical features; not a certified FPL-deadline backtest",
        "candidate_definition": "minutes_avg5 >= 60 using historical information only",
        "probability_metrics": "multiclass log-loss, Brier and 10-bin expected calibration error",
        "seed": 42,
    }
    (destination / "settings.json").write_text(json.dumps(settings, indent=2))
    return destination, test_scores, settings


def run(root: Path) -> Path:
    data, _ = load_data(root)
    data = enrich(data)
    folds, summary, oof = compare(data)
    destination, test_scores, settings = final_run(root, data, folds, summary, oof)
    print("\nValidation summary:\n", summary.to_string(), flush=True)
    print("\nTest summary:\n", test_scores.to_string(), flush=True)
    print("\nPromotion:\n", json.dumps(settings["promotion_checks"], indent=2), flush=True)
    print("Artifact:", destination, flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    run(parser.parse_args().root)
