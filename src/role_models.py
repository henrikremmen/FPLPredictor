"""Research challenger for actual starts, substitute appearances and absence.

Minutes bands are not starting-lineup labels. Missing starts remain unlabelled;
they are never imputed as substitute appearances or inferred from 60 minutes.
This model is deliberately separate from the approved production artifact.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss
from threadpoolctl import threadpool_limits

from model_experiments import FEATURE_SETS, build_model

ROLE_NAMES = ("absent", "cameo", "start")


def role_labels(frame: pd.DataFrame) -> pd.Series:
    minutes = pd.to_numeric(frame["minutes"], errors="coerce")
    starts = pd.to_numeric(frame["starts"], errors="coerce")
    valid = minutes.between(0, 130) & starts.isin([0, 1])
    # A recorded start can have zero rounded minutes. Preserve that evidence.
    labels = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    labels.loc[valid & starts.eq(1)] = 2
    labels.loc[valid & starts.eq(0) & minutes.gt(0)] = 1
    labels.loc[valid & starts.eq(0) & minutes.eq(0)] = 0
    return labels


class RoleModel:
    def __init__(self, max_iter: int = 120):
        self.max_iter = max_iter

    def fit(self, train: pd.DataFrame):
        labels = role_labels(train)
        known = labels.notna()
        if not known.any():
            raise ValueError("No observed starting-lineup labels")
        train = train.loc[known]
        labels = labels.loc[known].astype(int)
        requested = list(dict.fromkeys(FEATURE_SETS["context"] + [
            "start_rate3", "start_rate5", "start_rate10", "starts_season_before",
        ]))
        requested = [column for column in requested if column in train]
        base, self.columns, self.dropped = build_model("hgb", train, requested, 7)
        self.preprocess = base.named_steps["preprocess"]
        with threadpool_limits(limits=4):
            values = self.preprocess.fit_transform(train[self.columns])
            self.estimator = (DummyClassifier(strategy="prior") if labels.nunique() == 1 else
                HistGradientBoostingClassifier(max_iter=self.max_iter, max_leaf_nodes=7,
                    learning_rate=.06, l2_regularization=10, early_stopping=False,
                    random_state=42))
            self.estimator.fit(values, labels)
        self.training_rows = len(train)
        return self

    def probabilities(self, frame: pd.DataFrame) -> np.ndarray:
        with threadpool_limits(limits=4):
            values = self.preprocess.transform(frame[self.columns])
            raw = self.estimator.predict_proba(values)
        result = np.zeros((len(frame), 3))
        result[:, self.estimator.classes_.astype(int)] = raw
        return result


def role_metrics(frame: pd.DataFrame, probabilities: np.ndarray) -> dict:
    probabilities = np.asarray(probabilities)
    if probabilities.shape != (len(frame), 3):
        raise ValueError("Expected absent/cameo/start probabilities for every row")
    if (not np.isfinite(probabilities).all() or (probabilities < 0).any()
            or not np.allclose(probabilities.sum(axis=1), 1)):
        raise ValueError("Invalid role probability distribution")
    labels = role_labels(frame)
    known = labels.notna()
    if not known.any():
        return {"n": 0, "unlabelled": len(frame)}
    actual = labels.loc[known].astype(int).to_numpy()
    predicted = probabilities[known.to_numpy()]
    onehot = np.eye(3)[actual]
    return {"n": int(known.sum()), "unlabelled": int((~known).sum()),
            "log_loss": float(log_loss(actual, predicted, labels=[0, 1, 2])),
            "multiclass_brier": float(np.mean(np.sum((predicted - onehot) ** 2, axis=1))),
            **{f"brier_{name}": float(np.mean((predicted[:, i] - onehot[:, i]) ** 2))
               for i, name in enumerate(ROLE_NAMES)}}


def run_benchmark(root):
    import json
    from pathlib import Path
    root = Path(root)
    columns = list(dict.fromkeys(["season", "minutes", "starts", "start_rate3",
        "start_rate5", "start_rate10", "starts_season_before"] + FEATURE_SETS["context"]))
    data = pd.read_csv(root / "data/processed/player_fixture_features.csv",
                       usecols=columns, low_memory=False)
    data["was_home"] = data["was_home"].astype(str).str.lower().map(
        {"true": 1., "false": 0., "1": 1., "0": 0., "1.0": 1., "0.0": 0.})
    results = []
    for season in ["2023-24", "2024-25", "2025-26"]:
        train = data[data.season.ge("2022-23") & data.season.lt(season)]
        test = data[data.season.eq(season)]
        model = RoleModel().fit(train)
        result = {"season": season, "training_rows": model.training_rows,
                  **role_metrics(test, model.probabilities(test))}
        labels = role_labels(train).dropna().astype(int)
        prior = np.bincount(labels, minlength=3) / len(labels)
        result["training_prior_baseline"] = role_metrics(test, np.tile(prior, (len(test), 1)))
        results.append(result)
        print(json.dumps(result), flush=True)
    destination = root / "artifacts/model_research/role_benchmark.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({
        "status": "retrospective_diagnostic_not_deadline_certified",
        "production_eligible": False, "folds": results}, indent=2))
    return destination


if __name__ == "__main__":
    from pathlib import Path
    run_benchmark(Path(__file__).resolve().parents[1])
