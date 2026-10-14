"""Matched retrospective Elo ablation; no production promotion."""
import json
from itertools import product
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from elo_features import ELO_FEATURES, attach_elo, load_results
from historical_market import SEASON_CODES, attach_historical_market, normalize_historical_odds
from improved_models import EXTRA
from market_models import ALL_MARKET_FEATURES, market_enrich
from model_experiments import FEATURE_SETS, build_model, load_data, metrics


def run(root, include_understat=False):
    root = Path(root)
    data, _ = load_data(root)
    identity = pd.read_csv(root / "data/processed/player_fixture_features.csv",
        usecols=["season", "fixture", "player_id", "team", "opp_team_name"], low_memory=False)
    data = data.merge(identity, on=["season", "fixture", "player_id"], validate="one_to_one")
    data = data[data.season.isin(SEASON_CODES)].copy()
    # Explicit proxy, not a certified historical deadline. Baseline features
    # also remain fixture-shifted; this experiment cannot establish live gains.
    data["prediction_cutoff"] = data.groupby(["season", "GW"]).kickoff_time.transform("min") - pd.Timedelta(minutes=90)
    results = load_results(root)
    data = attach_elo(data, results)
    paths = {season: root / f"data/raw/historical_odds/football_data_uk/E0_{code}.csv"
             for season, code in SEASON_CODES.items()}
    data = market_enrich(attach_historical_market(data, normalize_historical_odds(paths)))
    coverage = {}
    if include_understat:
        from understat_features import attach_understat, identity_map, load_match_history
        history = load_match_history(root)
        data = attach_understat(data, history, identity_map(root))
        coverage = {"revision_audit": history.attrs,
                    "last_match_available_at": str(history.available_at.max()),
                    "mapped_fraction": data.groupby("season").understat_id.apply(lambda s: float(s.notna().mean())).to_dict(),
                    "feature_fraction": data.groupby("season").us_xg_last5.apply(lambda s: float(s.notna().mean())).to_dict()}
    reports = []
    for season in ["2023-24", "2024-25", "2025-26"]:
        train, test = data[data.season.lt(season)], data[data.season.eq(season)]
        for odds, elo, understat in product(
                [False, True], [False, True], [False, True] if include_understat else [False]):
            requested = FEATURE_SETS["context"] + EXTRA + (ALL_MARKET_FEATURES if odds else []) + (ELO_FEATURES if elo else [])
            if understat:
                from understat_features import UNDERSTAT_FEATURES
                requested = requested + UNDERSTAT_FEATURES
            model, columns, _ = build_model("hgb", train, requested, 7)
            with threadpool_limits(limits=4):
                model.fit(train[columns], train.target_points)
                prediction = model.predict(test[columns])
            report = {"season": season, "odds": odds, "elo": elo, "understat": understat,
                "train_rows": len(train), "test_rows": len(test),
                **metrics(test.target_points, prediction)}
            reports.append(report)
            print(json.dumps(report), flush=True)
    destination = root / "artifacts/model_research" / ("source_ablation.json" if include_understat else "elo_benchmark.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"production_eligible": False,
        "status": "retrospective_diagnostic_not_deadline_certified",
        "baseline": "matched hgb7, not deployed ensemble",
        "cutoff": "first observed GW kickoff minus 90 minutes; proxy only",
        "results_count": len(results), "understat_coverage": coverage, "folds": reports}, indent=2))
    return destination


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--understat", action="store_true")
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], include_understat=args.understat)
