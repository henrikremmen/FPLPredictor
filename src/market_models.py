"""Train, compare and guard a bookmaker-informed FPL points model.

The deployed baseline and the market model remain separate.  The ensemble uses
the baseline for fixtures without odds, which keeps long-horizon forecasts and
API outages usable.  Model selection is chronological and 2025/26 is held out
until after the candidate has been selected on earlier seasons.
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

from decision_backtest import backtest, cached_market, prepare_predictions
from historical_market import (
    MARKET_FEATURES,
    SEASON_CODES,
    attach_historical_market,
    download_historical_odds,
    normalize_historical_odds,
)
from historical_workload import (
    CL_SEASONS, CL_WORKLOAD_FEATURES,
    attach_cl_workload,
    download_historical_cl,
    load_cl_events,
)
from improved_models import EXTRA, PointsModel, ProductionModel, QuantilePointsModel, enrich
from model_experiments import FEATURE_SETS, TARGET, build_model, load_data, split
from nextgen_models import (
    KEYS,
    decision_metrics,
    fit_incumbent,
    paired_gameweek_bootstrap,
    score_prediction,
)


SEASON_ORDER = list(SEASON_CODES)
VALIDATION_SEASONS = ["2023-24", "2024-25"]
TEST_SEASON = "2025-26"
DERIVED_MARKET_FEATURES = [
    "market_attack_delta",
    "market_defence_delta",
    "market_goal_environment",
]
ALL_MARKET_FEATURES = MARKET_FEATURES + DERIVED_MARKET_FEATURES


def market_enrich(data: pd.DataFrame) -> pd.DataFrame:
    result = enrich(data)
    historical_attack = (
        result["team_goals_for_per_game_before"]
        + result["opp_goals_against_per_game_before"]
    ) / 2
    historical_defence = (
        result["team_goals_against_per_game_before"]
        + result["opp_goals_for_per_game_before"]
    ) / 2
    result["market_attack_delta"] = result["market_team_expected_goals"] - historical_attack
    result["market_defence_delta"] = (
        result["market_opponent_expected_goals"] - historical_defence
    )
    result["market_goal_environment"] = (
        result["market_team_expected_goals"]
        + result["market_opponent_expected_goals"]
    )
    return result.replace([np.inf, -np.inf], np.nan)


class MarketPointsModel:
    """Direct points regressor with the production features plus market context."""

    def __init__(self, kind: str = "hgb", leaves: int = 7,
                 include_workload: bool = False):
        self.kind, self.leaves = kind, int(leaves)
        self.include_workload = bool(include_workload)

    def fit(self, data: pd.DataFrame):
        frame = market_enrich(data)
        requested = list(dict.fromkeys(
            FEATURE_SETS["context"] + EXTRA + ALL_MARKET_FEATURES
            + (CL_WORKLOAD_FEATURES if self.include_workload else [])
        ))
        parameter = 100.0 if self.kind == "ridge" else self.leaves
        self.model, self.cols, self.dropped = build_model(
            self.kind, frame, requested, parameter
        )
        self.model.fit(frame[self.cols], frame[TARGET])
        return self

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        frame = market_enrich(data)
        return np.asarray(self.model.predict(frame[self.cols]), dtype=float)


class MarketFallbackBlend:
    """Blend market and baseline predictions only where market data exists."""

    def __init__(self, baseline, market, market_weight: float = 0.5):
        self.baseline = baseline
        self.market = market
        self.market_weight = float(market_weight)

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        baseline = np.asarray(self.baseline.predict(enrich(data)), dtype=float)
        required = [
            "market_team_expected_goals", "market_opponent_expected_goals",
            "market_clean_sheet_probability",
        ]
        available = data[required].notna().all(axis=1).to_numpy()
        if not available.any():
            return baseline
        market_prediction = np.asarray(self.market.predict(data), dtype=float)
        result = baseline.copy()
        weight = self.market_weight
        result[available] = (
            (1 - weight) * baseline[available] + weight * market_prediction[available]
        )
        return result


def _baseline_long(data: pd.DataFrame):
    return PointsModel("hgb", 7, True).fit(enrich(data))


def _market_hgb(data: pd.DataFrame):
    return MarketPointsModel("hgb", 7).fit(data)


def _market_ridge(data: pd.DataFrame):
    return MarketPointsModel("ridge", 7).fit(data)


def _market_blend(data: pd.DataFrame, weight: float):
    return MarketFallbackBlend(_baseline_long(data), _market_hgb(data), weight)


MODEL_FACTORIES = {
    "incumbent_blend": lambda data: fit_incumbent(enrich(data)),
    "baseline_long_hgb": _baseline_long,
    "market_hgb": _market_hgb,
    "market_ridge": _market_ridge,
    "market_blend_25": lambda data: _market_blend(data, .25),
    "market_blend_50": lambda data: _market_blend(data, .50),
    "market_blend_75": lambda data: _market_blend(data, .75),
}
MARKET_CANDIDATES = [
    "market_hgb", "market_ridge", "market_blend_25",
    "market_blend_50", "market_blend_75",
]


def load_market_data(root: Path) -> pd.DataFrame:
    base, _ = load_data(root)
    path = Path(root) / "data" / "processed" / "player_fixture_features.csv"
    identity = pd.read_csv(
        path,
        usecols=KEYS + ["team", "opp_team_name"],
        low_memory=False,
    )
    base = base.merge(identity, on=KEYS, how="left", validate="one_to_one")
    base = base[base.season.isin(SEASON_ORDER)].copy()
    paths = download_historical_odds(root, SEASON_ORDER)
    odds = normalize_historical_odds(paths)
    result = attach_historical_market(base, odds)
    cl_paths = download_historical_cl(root)
    result = attach_cl_workload(result, load_cl_events(cl_paths))
    if result.duplicated(KEYS).any():
        raise ValueError("Market training rows are not unique")
    return result.sort_values(["kickoff_time", "fixture", "player_id"]).reset_index(drop=True)


def _training_rows(data: pd.DataFrame, validation_season: str) -> pd.DataFrame:
    index = SEASON_ORDER.index(validation_season)
    return data[data.season.isin(SEASON_ORDER[:index])]


def compare(data: pd.DataFrame):
    folds, predictions = [], []
    for validation_season in VALIDATION_SEASONS:
        train = _training_rows(data, validation_season)
        validation = data[data.season.eq(validation_season)]
        for name, factory in MODEL_FACTORIES.items():
            started = time.monotonic()
            model = factory(train)
            prediction = model.predict(market_enrich(validation))
            folds.append({
                "model": name,
                "season": validation_season,
                "n_train": len(train),
                "n_validation": len(validation),
                "seconds": time.monotonic() - started,
                **score_prediction(validation, prediction),
            })
            report = validation[KEYS + ["position", "minutes_avg5", TARGET]].copy()
            report["model"], report["prediction"] = name, prediction
            predictions.append(report)
            print(f"Completed {name}: {validation_season}", flush=True)
    fold_frame = pd.DataFrame(folds)
    summary = fold_frame.groupby("model").agg(
        RMSE=("RMSE", "mean"), MAE=("MAE", "mean"),
        Spearman=("Spearman", "mean"),
        candidate_RMSE=("candidate_RMSE", "mean"),
        high_return_RMSE=("high_return_RMSE", "mean"),
        top25_actual_mean=("top25_actual_mean", "mean"),
        captain_actual_mean=("captain_actual_mean", "mean"),
        ndcg25=("ndcg25", "mean"), seconds=("seconds", "sum"),
    ).sort_values(["RMSE", "candidate_RMSE"])
    return fold_frame, summary, pd.concat(predictions, ignore_index=True)


def compare_workload(data: pd.DataFrame):
    """Bounded test of the shorter and incomplete Champions League history."""
    rows = []
    for season, train_seasons in [
        ("2024-25", ["2023-24"]),
        ("2025-26", ["2023-24", "2024-25"]),
    ]:
        train = data[data.season.isin(train_seasons)]
        evaluation = data[data.season.eq(season)]
        for name, model in [
            ("market_short_hgb", MarketPointsModel("hgb", 7, False)),
            ("market_cl_workload_hgb", MarketPointsModel("hgb", 7, True)),
        ]:
            model.fit(train)
            prediction = model.predict(evaluation)
            rows.append({
                "model": name, "season": season,
                "n_train": len(train), "n_evaluation": len(evaluation),
                **score_prediction(evaluation, prediction),
            })
            print(f"Completed workload test {name}: {season}", flush=True)
    return pd.DataFrame(rows)


def evaluate_test(data: pd.DataFrame, names: list[str]):
    train = data[data.season.ne(TEST_SEASON)]
    test = data[data.season.eq(TEST_SEASON)]
    rows, reports, models = [], [], {}
    for name in names:
        model = MODEL_FACTORIES[name](train)
        prediction = model.predict(market_enrich(test))
        models[name] = model
        rows.append({"model": name, **score_prediction(test, prediction)})
        report = test[KEYS + ["name", "position", "minutes_avg5", TARGET]].copy()
        report["model"], report["prediction"] = name, prediction
        reports.append(report)
        print(f"Completed holdout {name}: {TEST_SEASON}", flush=True)
    return pd.DataFrame(rows).set_index("model"), pd.concat(reports), models


def _gate(summary: pd.DataFrame, test: pd.DataFrame, decision: dict,
          candidate: str) -> tuple[bool, dict]:
    checks = {}
    for reference in ["incumbent_blend", "baseline_long_hgb"]:
        checks.update({
            f"validation_RMSE_vs_{reference}": bool(
                summary.loc[candidate, "RMSE"] < summary.loc[reference, "RMSE"]
            ),
            f"validation_candidate_RMSE_vs_{reference}": bool(
                summary.loc[candidate, "candidate_RMSE"]
                < summary.loc[reference, "candidate_RMSE"]
            ),
            f"test_RMSE_vs_{reference}": bool(
                test.loc[candidate, "RMSE"] <= test.loc[reference, "RMSE"]
            ),
            f"test_candidate_RMSE_vs_{reference}": bool(
                test.loc[candidate, "candidate_RMSE"]
                <= test.loc[reference, "candidate_RMSE"]
            ),
        })
    checks["validation_top25_vs_incumbent"] = bool(
        summary.loc[candidate, "top25_actual_mean"]
        >= summary.loc["incumbent_blend", "top25_actual_mean"]
    )
    checks["test_top25_vs_incumbent"] = bool(
        test.loc[candidate, "top25_actual_mean"]
        >= test.loc["incumbent_blend", "top25_actual_mean"]
    )
    checks["decision_points_vs_incumbent"] = bool(
        decision["mean_points_gain_per_gameweek"] >= 0
    )
    return all(checks.values()), checks


def _production_model(data: pd.DataFrame, candidate: str):
    complete = data[data.season.ne("2026-27")]
    incumbent_rows = complete[complete.season.isin(SEASON_ORDER[2:])]
    incumbent = fit_incumbent(enrich(incumbent_rows))
    if candidate == "market_hgb":
        points_model = MarketFallbackBlend(
            incumbent, _market_hgb(complete), 1.0
        )
    elif candidate == "market_ridge":
        points_model = MarketFallbackBlend(
            incumbent, _market_ridge(complete), 1.0
        )
    else:
        points_model = MODEL_FACTORIES[candidate](complete)
    enriched = enrich(complete)
    probability_model = PointsModel(
        "mixture", 7, True, classifier_leaves=15
    ).fit(enriched)
    uncertainty_model = QuantilePointsModel().fit(enriched)
    return ProductionModel(points_model, probability_model, uncertainty_model)


def build_production_artifact(root: Path, data: pd.DataFrame, candidate: str,
                              settings: dict, evaluation: Path) -> Path:
    """Refit the accepted components on every completed historical season."""
    parent = Path(root) / "artifacts" / "models"
    model = _production_model(data, candidate)
    production = Path(tempfile.mkdtemp(prefix="production_market_", dir=parent))
    joblib.dump({
        "model": model,
        "model_family": candidate + "+market_fallback+minutes_mixture_15+quantile_hgb",
        "points_model_family": candidate,
        "production_eligible": True,
    }, production / "model.joblib")
    production_settings = {
        **settings,
        "production_eligible": True,
        "market_fallback": "incumbent_blend per fixture when market odds are missing",
        "evaluation_artifact": str(evaluation.resolve()),
        "point_training_rows": int(len(data[data.season.ne("2026-27")])),
    }
    (production / "settings.json").write_text(json.dumps(production_settings, indent=2))
    return production


def run(root: Path) -> Path:
    root = Path(root)
    data = load_market_data(root)
    folds, summary, oof = compare(data)
    workload = compare_workload(data)
    candidate = str(summary.loc[MARKET_CANDIDATES].sort_values(
        ["RMSE", "candidate_RMSE"]
    ).index[0])
    test_names = list(dict.fromkeys([
        "incumbent_blend", "baseline_long_hgb", candidate
    ]))
    test, test_predictions, _ = evaluate_test(data, test_names)
    bootstrap = paired_gameweek_bootstrap(oof, candidate, "incumbent_blend")

    decision_oof = oof[oof.model.isin(["incumbent_blend", candidate])]
    seasons = sorted(decision_oof.season.unique())
    markets = {season: cached_market(root, season) for season in seasons}
    prepared = prepare_predictions(
        decision_oof, markets, ["incumbent_blend", candidate], burn_in=5
    )
    decision_gameweeks, decision_summary, decision = backtest(
        prepared, ["incumbent_blend", candidate]
    )
    eligible, checks = _gate(summary, test, decision, candidate)

    parent = root / "artifacts" / "models"
    parent.mkdir(parents=True, exist_ok=True)
    artifact = Path(tempfile.mkdtemp(prefix="market_", dir=parent))
    folds.to_csv(artifact / "validation_folds.csv", index=False)
    summary.to_csv(artifact / "validation_summary.csv")
    oof.to_csv(artifact / "validation_predictions.csv", index=False)
    test.to_csv(artifact / "test_metrics.csv")
    test_predictions.to_csv(artifact / "test_predictions.csv", index=False)
    decision_gameweeks.to_csv(artifact / "decision_backtest_gameweeks.csv", index=False)
    decision_summary.to_csv(artifact / "decision_backtest_summary.csv")
    workload.to_csv(artifact / "workload_comparison.csv", index=False)
    workload_pivot = workload.pivot(index="season", columns="model", values="RMSE")
    workload_improves_rmse = bool((
        workload_pivot["market_cl_workload_hgb"]
        < workload_pivot["market_short_hgb"]
    ).all())
    settings = {
        "candidate": candidate,
        "market_source": "football-data.co.uk pre-closing market averages",
        "market_features": ALL_MARKET_FEATURES,
        "training_seasons": SEASON_ORDER[:-1],
        "validation_seasons": VALIDATION_SEASONS,
        "test_season": TEST_SEASON,
        "historical_api_status": "The Odds API historical endpoint unavailable on free plan",
        "paired_validation_bootstrap": bootstrap,
        "paired_decision_backtest": decision,
        "promotion_checks": checks,
        "production_eligible": eligible,
        "cl_workload_research": {
            "available_seasons": list(CL_SEASONS),
            "competitions_covered": ["UEFA Champions League"],
            "missing_competitions": [
                "UEFA Europa League", "UEFA Conference League",
                "FA Cup", "EFL Cup",
            ],
            "improves_rmse_every_evaluation_season": workload_improves_rmse,
            "production_enabled": False,
        },
        "leakage_control": "pre-closing columns only; closing C columns excluded",
    }
    (artifact / "settings.json").write_text(json.dumps(settings, indent=2))

    if eligible:
        production = build_production_artifact(
            root, data, candidate, settings, artifact
        )
        settings["production_artifact"] = str(production.resolve())
        (artifact / "settings.json").write_text(json.dumps(settings, indent=2))

    print("\nValidation:\n", summary.to_string(), flush=True)
    print("\nHoldout:\n", test.to_string(), flush=True)
    print("\nDecision:\n", decision_summary.to_string(), flush=True)
    print("\nGate:\n", json.dumps(checks, indent=2), flush=True)
    print("Artifact:", artifact, flush=True)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    # Import the canonical module before training so joblib records
    # ``market_models.ClassName`` rather than an unloadable ``__main__`` class.
    from market_models import run as canonical_run
    canonical_run(arguments.root)
