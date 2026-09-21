"""Structural and probabilistic FPL point model.

Instead of learning total points as one noisy target, the model predicts
minutes and each scoring event separately, applies the current FPL rules, and
can Monte-Carlo sample the resulting point distribution.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder

from improved_models import EXTRA
from model_experiments import FEATURE_SETS


RICH_FEATURES = [
    "bonus_avg5", "CBI90_last5", "tackles90_last5", "recoveries90_last5",
    "defensive_contribution_rate5", "defensive_contribution90_last5",
    "yellow_cards_last5", "ppg_difference", "team_attack_vs_opp_defence",
    "team_defence_vs_opp_attack",
]
FEATURES = list(dict.fromkeys(FEATURE_SETS["context"] + EXTRA + RICH_FEATURES))
COUNT_TARGETS = [
    "goals_scored", "assists", "saves", "bonus", "yellow_cards", "red_cards",
    "own_goals", "penalties_missed", "penalties_saved", "goals_conceded",
]
GOAL_POINTS = {"GK": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}
CLEAN_SHEET_POINTS = {"GK": 4.0, "DEF": 4.0, "MID": 1.0, "FWD": 0.0}


def _minutes_class(minutes) -> np.ndarray:
    values = np.asarray(minutes, dtype=float)
    return np.select(
        [values <= 0, values < 60, values < 90], [0, 1, 2], default=3
    ).astype(int)


def _poisson_floor_mean(rate: np.ndarray, divisor: int, maximum: int = 50) -> np.ndarray:
    rate = np.clip(np.asarray(rate, dtype=float), 0, 30)
    values = np.arange(maximum + 1)
    probabilities = poisson.pmf(values[None, :], rate[:, None])
    return (probabilities * (values // divisor)[None, :]).sum(axis=1)


class ComponentPointsModel:
    """Serializable shared-preprocessor ensemble for individual FPL events."""

    def __init__(self, max_iter=140, leaves=9):
        self.max_iter, self.leaves = int(max_iter), int(leaves)

    def fit(self, data: pd.DataFrame):
        self.columns = [column for column in FEATURES if column in data]
        numeric = [column for column in self.columns if column != "position"]
        self.preprocessor = ColumnTransformer([
            ("numeric", SimpleImputer(
                strategy="median", add_indicator=True, keep_empty_features=True
            ), numeric),
            ("position", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
             ["position"]),
        ])
        transformed = self.preprocessor.fit_transform(data[self.columns])
        minute_target = _minutes_class(data["minutes"])
        self.minutes_model = self._classifier(minute_target, multiclass=True)
        self.minutes_model.fit(transformed, minute_target)
        self.count_models = {}
        for index, target in enumerate(COUNT_TARGETS):
            values = pd.to_numeric(data[target], errors="coerce").fillna(0).clip(lower=0)
            model = self._count_model(values, seed=100 + index)
            self.count_models[target] = model.fit(transformed, values)
        clean = pd.to_numeric(data["clean_sheets"], errors="coerce").fillna(0).gt(0).astype(int)
        self.clean_sheet_model = self._classifier(clean, multiclass=False)
        self.clean_sheet_model.fit(transformed, clean)
        defcon = pd.to_numeric(data.get("defensive_contribution"), errors="coerce")
        mask = defcon.notna()
        if mask.sum() >= 500 and defcon[mask].sum() > 0:
            self.defcon_model = self._count_model(defcon[mask], seed=220)
            self.defcon_model.fit(transformed[mask.to_numpy()], defcon[mask])
            self.has_defcon = True
        else:
            self.defcon_model = DummyRegressor(strategy="constant", constant=0).fit(
                transformed[:1], [0]
            )
            self.has_defcon = False
        return self

    def _count_model(self, target, seed):
        if len(target) < 100 or float(np.sum(target)) < 10:
            return DummyRegressor(strategy="mean")
        return HistGradientBoostingRegressor(
            loss="poisson", max_iter=self.max_iter, max_leaf_nodes=self.leaves,
            learning_rate=.055, min_samples_leaf=50, l2_regularization=12,
            early_stopping=False, random_state=seed,
        )

    def _classifier(self, target, multiclass):
        if np.unique(target).size < 2:
            return DummyClassifier(strategy="prior")
        return HistGradientBoostingClassifier(
            loss="log_loss", max_iter=self.max_iter, max_leaf_nodes=self.leaves,
            learning_rate=.055, min_samples_leaf=50, l2_regularization=12,
            early_stopping=False, random_state=42 if multiclass else 43,
        )

    def _transform(self, data):
        return self.preprocessor.transform(data[self.columns])

    @staticmethod
    def _complete_probabilities(model, transformed, classes) -> np.ndarray:
        raw = model.predict_proba(transformed)
        result = np.zeros((len(transformed), len(classes)))
        known = np.asarray(model.classes_, dtype=int)
        result[:, known] = raw
        return result

    def predict_components(self, data: pd.DataFrame) -> dict[str, np.ndarray]:
        transformed = self._transform(data)
        components = {
            "minutes_probability": self._complete_probabilities(
                self.minutes_model, transformed, [0, 1, 2, 3]
            ),
            "clean_sheet_probability": self._complete_probabilities(
                self.clean_sheet_model, transformed, [0, 1]
            )[:, 1],
        }
        for target, model in self.count_models.items():
            components[target] = np.clip(model.predict(transformed), 0, None)
        components["defensive_contribution"] = np.clip(
            self.defcon_model.predict(transformed), 0, None
        )
        return components

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        c = self.predict_components(data)
        positions = data["position"].astype(str).to_numpy()
        minute_probability = c["minutes_probability"]
        points = (minute_probability[:, 1:].sum(axis=1)
                  + minute_probability[:, 2:].sum(axis=1))
        points += c["goals_scored"] * np.asarray([GOAL_POINTS.get(p, 4) for p in positions])
        points += 3 * c["assists"]
        points += c["clean_sheet_probability"] * np.asarray(
            [CLEAN_SHEET_POINTS.get(p, 0) for p in positions]
        )
        points += _poisson_floor_mean(c["saves"], 3)
        points += c["bonus"] + 5 * c["penalties_saved"]
        points -= c["yellow_cards"] + 3 * c["red_cards"]
        points -= 2 * c["own_goals"] + 2 * c["penalties_missed"]
        defender = np.isin(positions, ["GK", "DEF"])
        points -= defender * _poisson_floor_mean(c["goals_conceded"], 2)
        if self.has_defcon:
            threshold = np.where(positions == "DEF", 10, np.where(
                np.isin(positions, ["MID", "FWD"]), 12, 999
            ))
            points += 2 * poisson.sf(threshold - 1, c["defensive_contribution"])
        return points

    def predict_distribution(self, data: pd.DataFrame, draws=2000, seed=42) -> dict:
        """Monte-Carlo FPL points with minutes-gated scoring events."""
        c = self.predict_components(data)
        rng = np.random.default_rng(seed)
        n = len(data)
        probabilities = c["minutes_probability"]
        uniforms = rng.random((draws, n))
        minutes_class = (uniforms[..., None] > np.cumsum(probabilities, axis=1)[None, :, :]).sum(axis=2)
        played, sixty = minutes_class > 0, minutes_class >= 2
        p_play = np.clip(probabilities[:, 1:].sum(axis=1), .03, 1)
        p_sixty = np.clip(probabilities[:, 2:].sum(axis=1), .03, 1)

        def sample_count(name):
            conditional = np.clip(c[name] / p_play, 0, 30)
            return rng.poisson(conditional[None, :], size=(draws, n)) * played

        goals, assists = sample_count("goals_scored"), sample_count("assists")
        saves, bonus = sample_count("saves"), np.minimum(3, sample_count("bonus"))
        yellow, red = sample_count("yellow_cards"), sample_count("red_cards")
        own, missed = sample_count("own_goals"), sample_count("penalties_missed")
        saved, conceded = sample_count("penalties_saved"), sample_count("goals_conceded")
        cs_probability = np.clip(c["clean_sheet_probability"] / p_sixty, 0, 1)
        clean = (rng.random((draws, n)) < cs_probability[None, :]) & sixty
        positions = data["position"].astype(str).to_numpy()
        result = played.astype(float) + sixty.astype(float)
        result += goals * np.asarray([GOAL_POINTS.get(p, 4) for p in positions])[None, :]
        result += 3 * assists + clean * np.asarray(
            [CLEAN_SHEET_POINTS.get(p, 0) for p in positions]
        )[None, :]
        result += saves // 3 + bonus + 5 * saved
        result -= yellow + 3 * red + 2 * own + 2 * missed
        result -= (conceded // 2) * np.isin(positions, ["GK", "DEF"])[None, :] * sixty
        if self.has_defcon:
            defcon = sample_count("defensive_contribution")
            threshold = np.where(positions == "DEF", 10, np.where(
                np.isin(positions, ["MID", "FWD"]), 12, 999
            ))
            result += 2 * (defcon >= threshold[None, :])
        return {
            "mean": result.mean(axis=0), "q10": np.quantile(result, .1, axis=0),
            "q50": np.quantile(result, .5, axis=0), "q90": np.quantile(result, .9, axis=0),
            "p5plus": (result >= 5).mean(axis=0), "p10plus": (result >= 10).mean(axis=0),
        }
