"""Fresh shot/Elo additions to the deployed market-point architecture.

All models refit before 2025/26. Historical availability is retrospective;
this is not a certified deadline backtest or a new untouched holdout.
"""
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from elo_features import ELO_FEATURES, attach_elo, load_results
from historical_market import SEASON_CODES, attach_historical_market, normalize_historical_odds
from improved_models import EXTRA
from market_models import ALL_MARKET_FEATURES, market_enrich
from model_experiments import FEATURE_SETS, build_model, load_data
from nextgen_models import fit_incumbent, score_prediction
from understat_shots import SHOT_FEATURES, attach_shot_features


def load_source_training_data(root):
    root = Path(root)
    destination = root / "artifacts/model_research"
    data, _ = load_data(root)
    identity = pd.read_csv(root / "data/processed/player_fixture_features.csv",
        usecols=["season", "fixture", "player_id", "team", "opp_team_name"], low_memory=False)
    data = data.merge(identity, on=["season", "fixture", "player_id"], validate="one_to_one")
    data = data[data.season.isin(SEASON_CODES)].copy()
    data["prediction_cutoff"] = data.groupby(["season", "GW"]).kickoff_time.transform("min") - pd.Timedelta(minutes=90)
    data = attach_elo(data, load_results(root))
    paths = {season: root / f"data/raw/historical_odds/football_data_uk/E0_{code}.csv"
             for season, code in SEASON_CODES.items()}
    data = market_enrich(attach_historical_market(data, normalize_historical_odds(paths)))
    data = attach_shot_features(data, pd.read_csv(destination / "understat_shot_history.csv"),
        pd.read_csv(destination / "understat_identities.csv"), mode="retrospective")
    return data


def run(root):
    root = Path(root)
    destination = root / "artifacts/model_research"
    data = load_source_training_data(root)
    train, test = data[data.season.lt("2025-26")], data[data.season.eq("2025-26")]
    with threadpool_limits(limits=4):
        incumbent = fit_incumbent(train[train.season.ge("2022-23")])
        fallback = incumbent.predict(test)
    available = test[["market_team_expected_goals", "market_opponent_expected_goals", "market_clean_sheet_probability"]].notna().all(axis=1)
    reports, predictions = [], []
    for elo, shots in product([False, True], repeat=2):
        columns = FEATURE_SETS["context"] + EXTRA + ALL_MARKET_FEATURES + (ELO_FEATURES if elo else []) + (SHOT_FEATURES if shots else [])
        model, columns, _ = build_model("hgb", train, columns, 7)
        with threadpool_limits(limits=4):
            model.fit(train[columns], train.target_points)
            prediction = np.where(available, model.predict(test[columns]), fallback)
        name = f"market_elo{int(elo)}_shots{int(shots)}"
        report = {"model": name, **score_prediction(test, prediction)}
        report = {key: None if isinstance(value, float) and not np.isfinite(value) else value
                  for key, value in report.items()}
        reports.append(report)
        frame = test[["season", "GW", "fixture", "player_id", "target_points"]].copy()
        frame["model"], frame["prediction"] = name, prediction
        predictions.append(frame)
        print(json.dumps(report), flush=True)
    pd.concat(predictions).to_csv(destination / "shot_benchmark_predictions.csv", index=False)
    (destination / "shot_benchmark.json").write_text(json.dumps({
        "production_eligible": False, "status": "retrospective_not_deadline_certified",
        "test_season": "2025-26", "odds_coverage": float(available.mean()),
        "shot_coverage_by_season": data.groupby("season").us_shot_observations5.apply(lambda x:float(x.notna().mean())).to_dict(),
        "baseline": "market_hgb with 2022+ incumbent fallback, matching production point architecture",
        "folds": reports}, indent=2))


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[1])
