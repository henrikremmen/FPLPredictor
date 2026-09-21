"""Chronological CatBoost/LightGBM benchmark with richer safe FPL features.

This lab never promotes a model.  It writes validation and holdout evidence for
the existing production gate, including FPL-facing ranking metrics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from catboost import CatBoostRegressor
import numpy as np
import pandas as pd

try:
    from lightgbm import LGBMRegressor
    LIGHTGBM_ERROR = None
except (ImportError, OSError) as exc:  # macOS requires libomp outside pip
    LGBMRegressor = None
    LIGHTGBM_ERROR = str(exc)

from improved_models import EXTRA, enrich
from model_experiments import FEATURE_SETS, TARGET
from nextgen_models import fit_incumbent, score_prediction


KEYS = ["season", "GW", "fixture", "player_id"]
CATEGORICAL = ["position", "team_name", "opp_team_name", "player_key"]
RICH_NUMERIC = [
    "bonus_avg5", "CBI90_last5", "tackles90_last5", "recoveries90_last5",
    "defensive_contribution_rate5", "defensive_contribution90_last5",
    "yellow_cards_last5", "ppg_difference", "team_attack_vs_opp_defence",
    "team_defence_vs_opp_attack",
]
NUMERIC = list(dict.fromkeys(FEATURE_SETS["context"] + EXTRA + RICH_NUMERIC))


def load_lab_data(root: Path) -> pd.DataFrame:
    path = root / "data" / "processed" / "player_fixture_features.csv"
    header = pd.read_csv(path, nrows=0).columns
    requested = list(dict.fromkeys(
        KEYS + ["kickoff_time", "name", "team", "opp_team_name", "position",
                "minutes", TARGET] + FEATURE_SETS["context"] + RICH_NUMERIC
    ))
    missing = sorted(set(requested) - set(header))
    if missing:
        raise ValueError(f"Feature dataset is missing: {missing}")
    data = pd.read_csv(path, usecols=requested, low_memory=False)
    data = data.rename(columns={"team": "team_name", "name": "player_key"})
    data["position"] = data.position.replace({"GKP": "GK"})
    data = data[data.position.isin(["GK", "DEF", "MID", "FWD"])].copy()
    data["kickoff_time"] = pd.to_datetime(data.kickoff_time, utc=True, errors="raise")
    data["was_home"] = data.was_home.astype(str).str.lower().map(
        {"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0}
    )
    data = enrich(data.replace([np.inf, -np.inf], np.nan).dropna(subset=[TARGET]))
    for column in CATEGORICAL:
        data[column] = data[column].fillna("UNKNOWN").astype(str)
    return data.sort_values(["kickoff_time", "fixture", "player_id"]).reset_index(drop=True)


class CatBoostPoints:
    def __init__(self, iterations=500, depth=7, include_player=True):
        self.iterations, self.depth, self.include_player = iterations, depth, include_player

    @property
    def columns(self):
        categories = CATEGORICAL if self.include_player else CATEGORICAL[:-1]
        return [column for column in NUMERIC if column != "position"] + categories

    def fit(self, data):
        self.model = CatBoostRegressor(
            iterations=self.iterations, depth=self.depth, learning_rate=.035,
            loss_function="RMSE", l2_leaf_reg=12, random_seed=42,
            verbose=False, allow_writing_files=False, thread_count=4,
        )
        categories = [index for index, name in enumerate(self.columns)
                      if name in CATEGORICAL]
        self.model.fit(data[self.columns], data[TARGET], cat_features=categories)
        return self

    def predict(self, data):
        return self.model.predict(data[self.columns])


class LightGBMPoints:
    def __init__(self, estimators=600, leaves=15):
        self.estimators, self.leaves = estimators, leaves
        self.columns = [column for column in NUMERIC if column != "position"] + CATEGORICAL[:-1]

    def _view(self, data):
        frame = data[self.columns].copy()
        for column in CATEGORICAL[:-1]:
            frame[column] = frame[column].astype("category")
        return frame

    def fit(self, data):
        if LGBMRegressor is None:
            raise RuntimeError(f"LightGBM is unavailable: {LIGHTGBM_ERROR}")
        self.category_levels = {
            column: data[column].astype("category").cat.categories
            for column in CATEGORICAL[:-1]
        }
        frame = data[self.columns].copy()
        for column, levels in self.category_levels.items():
            frame[column] = pd.Categorical(frame[column], categories=levels)
        self.model = LGBMRegressor(
            objective="regression_l2", n_estimators=self.estimators,
            learning_rate=.025, num_leaves=self.leaves, min_child_samples=80,
            subsample=.85, colsample_bytree=.85, reg_lambda=12,
            random_state=42, n_jobs=4, verbosity=-1,
        )
        self.model.fit(frame, data[TARGET], categorical_feature=CATEGORICAL[:-1])
        return self

    def predict(self, data):
        frame = data[self.columns].copy()
        for column, levels in self.category_levels.items():
            frame[column] = pd.Categorical(frame[column], categories=levels)
        return self.model.predict(frame)


CANDIDATES = {
    "incumbent": ("2022-23", fit_incumbent),
    "catboost_rich": ("2020-21", lambda data: CatBoostPoints().fit(data)),
    "catboost_no_player": ("2020-21", lambda data: CatBoostPoints(include_player=False).fit(data)),
    # A deliberately small chronological search: enough to test whether more
    # training and shallower trees generalise, without tuning on the holdout.
    "catboost_long_shallow": (
        "2020-21", lambda data: CatBoostPoints(
            iterations=800, depth=6, include_player=False
        ).fit(data)
    ),
}
if LGBMRegressor is not None:
    CANDIDATES["lightgbm_rich"] = (
        "2020-21", lambda data: LightGBMPoints().fit(data)
    )
SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def before(start: str, validation: str) -> list[str]:
    return SEASONS[SEASONS.index(start):SEASONS.index(validation)]


def evaluate(root: Path) -> Path:
    data = load_lab_data(root)
    rows, predictions = [], []
    for validation in ["2023-24", "2024-25"]:
        evaluation = data[data.season.eq(validation)].copy()
        for name, (start, factory) in CANDIDATES.items():
            train = data[data.season.isin(before(start, validation))].copy()
            model = factory(train)
            prediction = model.predict(evaluation)
            rows.append({"dataset": "validation", "season": validation, "model": name,
                         "training_rows": len(train), **score_prediction(evaluation, prediction)})
            report = evaluation[KEYS + [TARGET]].copy()
            report["model"], report["prediction"] = name, prediction
            predictions.append(report)
            print(f"Completed {name} -> {validation}", flush=True)

    folds = pd.DataFrame(rows)
    metrics = ["RMSE", "MAE", "Spearman", "candidate_RMSE", "top25_actual_mean",
               "captain_actual_mean", "ndcg25"]
    summary = folds.groupby("model")[metrics].mean().sort_values(
        ["candidate_RMSE", "RMSE"]
    )
    winner = str(summary.index[0])
    test = data[data.season.eq("2025-26")].copy()
    test_rows = []
    for name in list(dict.fromkeys(["incumbent", winner])):
        start, factory = CANDIDATES[name]
        train = data[data.season.isin(before(start, "2025-26"))].copy()
        model = factory(train)
        prediction = model.predict(test)
        test_rows.append({"dataset": "holdout", "season": "2025-26", "model": name,
                          "training_rows": len(train), **score_prediction(test, prediction)})
        report = test[KEYS + [TARGET]].copy()
        report["model"], report["prediction"] = name, prediction
        predictions.append(report)
        print(f"Completed holdout {name}", flush=True)

    destination = Path(tempfile.mkdtemp(
        prefix="model_lab_", dir=root / "artifacts" / "models"
    ))
    folds.to_csv(destination / "validation_folds.csv", index=False)
    summary.to_csv(destination / "validation_summary.csv")
    pd.DataFrame(test_rows).set_index("model").to_csv(destination / "holdout_metrics.csv")
    pd.concat(predictions, ignore_index=True).to_csv(destination / "predictions.csv", index=False)
    settings = {
        "winner_by_validation_candidate_RMSE": winner,
        "production_eligible": False,
        "reason": "Research benchmark only; must pass constrained rolling decision gate",
        "validation_seasons": ["2023-24", "2024-25"],
        "holdout": "2025-26 (previously explored)",
        "features": NUMERIC + CATEGORICAL,
        "search_space": {
            "catboost_rich": {"iterations": 500, "depth": 7, "include_player": True},
            "catboost_no_player": {"iterations": 500, "depth": 7, "include_player": False},
            "catboost_long_shallow": {
                "iterations": 800, "depth": 6, "include_player": False,
            },
            "lightgbm_rich": {"estimators": 600, "leaves": 15},
        },
        "seed": 42,
        "lightgbm_error": LIGHTGBM_ERROR,
    }
    (destination / "settings.json").write_text(json.dumps(settings, indent=2))
    print("\nValidation\n", summary.to_string(), flush=True)
    print("\nHoldout\n", pd.DataFrame(test_rows).set_index("model").to_string(), flush=True)
    print("Artifact:", destination, flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    evaluate(parser.parse_args().root)
