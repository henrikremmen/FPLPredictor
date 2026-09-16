"""Evaluate optional point-quantile utility profiles under FPL constraints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from decision_backtest import (
    backtest,
    cached_market,
    latest_evaluation_artifact,
    paired_bootstrap,
    prepare_predictions,
)


KEYS = ["season", "GW", "fixture", "player_id"]
PROFILES = ["balanced", "stable", "upside"]


def profile_predictions(oof: pd.DataFrame, quantiles: pd.DataFrame) -> pd.DataFrame:
    incumbent = oof[oof["model"].eq("incumbent_blend")].merge(
        quantiles[KEYS + ["q10", "q90"]], on=KEYS, validate="one_to_one"
    )
    formulas = {
        "balanced": incumbent["prediction"],
        "stable": incumbent["prediction"] - .1 * (incumbent["q90"] - incumbent["q10"]),
        "upside": .7 * incumbent["prediction"] + .3 * incumbent["q90"],
    }
    frames = []
    for profile, score in formulas.items():
        frame = incumbent.copy()
        frame["model"] = profile
        frame["prediction"] = score
        frames.append(frame[oof.columns])
    return pd.concat(frames, ignore_index=True)


def evaluate(root: Path, artifact: Path | None = None, burn_in: int = 5) -> Path:
    artifact = artifact or latest_evaluation_artifact(root)
    oof = pd.read_csv(artifact / "validation_predictions.csv")
    quantiles = pd.read_csv(artifact / "uncertainty_validation_predictions.csv")
    profiles = profile_predictions(oof, quantiles)
    seasons = sorted(profiles["season"].unique())
    markets = {season: cached_market(root, season) for season in seasons}
    prepared = prepare_predictions(profiles, markets, PROFILES, burn_in)
    gameweeks, summary, _ = backtest(prepared, PROFILES)
    by_season = gameweeks.groupby(["season", "model"]).agg(
        total_actual_points=("actual_points", "sum"),
        mean_actual_points=("actual_points", "mean"),
        score_std=("actual_points", "std"),
    ).reset_index()
    distribution = gameweeks.groupby("model")["actual_points"].agg(
        mean="mean", std="std", p10=lambda values: values.quantile(.1),
        p25=lambda values: values.quantile(.25), p90=lambda values: values.quantile(.9),
    )
    comparisons = {
        profile: paired_bootstrap(gameweeks, profile, "balanced")
        for profile in ["stable", "upside"]
    }
    season_pivot = by_season.pivot(
        index="season", columns="model", values="total_actual_points"
    )
    checks = {
        profile: {
            "combined_points_at_least_balanced": bool(
                summary.loc[profile, "total_actual_points"] >=
                summary.loc["balanced", "total_actual_points"]
            ),
            "points_at_least_balanced_in_each_season": bool(
                (season_pivot[profile] >= season_pivot["balanced"]).all()
            ),
        }
        for profile in ["stable", "upside"]
    }
    test_oof_path = artifact / "test_predictions.csv"
    test_quantile_path = artifact / "uncertainty_test_predictions.csv"
    test_summary = pd.DataFrame()
    test_by_season = pd.DataFrame()
    test_comparisons = {}
    if test_oof_path.exists() and test_quantile_path.exists():
        test_profiles = profile_predictions(
            pd.read_csv(test_oof_path), pd.read_csv(test_quantile_path)
        )
        test_seasons = sorted(test_profiles["season"].unique())
        test_markets = {season: cached_market(root, season) for season in test_seasons}
        test_prepared = prepare_predictions(test_profiles, test_markets, PROFILES, burn_in)
        test_gameweeks, test_summary, _ = backtest(test_prepared, PROFILES)
        test_by_season = test_gameweeks.groupby(["season", "model"]).agg(
            total_actual_points=("actual_points", "sum"),
            mean_actual_points=("actual_points", "mean"),
            score_std=("actual_points", "std"),
        ).reset_index()
        test_comparisons = {
            profile: paired_bootstrap(test_gameweeks, profile, "balanced")
            for profile in ["stable", "upside"]
        }
        test_gameweeks.to_csv(artifact / "risk_profile_test_gameweeks.csv", index=False)
        test_summary.to_csv(artifact / "risk_profile_test_summary.csv")
        test_by_season.to_csv(artifact / "risk_profile_test_by_season.csv", index=False)
        for profile in ["stable", "upside"]:
            checks[profile]["test_points_at_least_balanced"] = bool(
                test_summary.loc[profile, "total_actual_points"] >=
                test_summary.loc["balanced", "total_actual_points"]
            )
    report = {
        "profiles": {
            "balanced": "expected points",
            "stable": "expected points - 0.1 * (Q90 - Q10)",
            "upside": "0.7 * expected points + 0.3 * Q90",
        },
        "seasons": seasons,
        "burn_in_gameweeks": burn_in,
        "checks": checks,
        "comparisons_vs_balanced": comparisons,
        "test_confirmation": {
            "season": "2025-26 (not pristine at project level; new for profile formulas)",
            "comparisons_vs_balanced": test_comparisons,
        },
        "caveat": (
            "Exploratory static weekly selection on the same two validation seasons; "
            "profiles are optional utilities, not new expected-point estimates."
        ),
    }
    gameweeks.to_csv(artifact / "risk_profile_gameweeks.csv", index=False)
    summary.to_csv(artifact / "risk_profile_summary.csv")
    by_season.to_csv(artifact / "risk_profile_by_season.csv", index=False)
    distribution.to_csv(artifact / "risk_profile_distribution.csv")
    (artifact / "risk_profile_evaluation.json").write_text(json.dumps(report, indent=2))
    print("\nRisk-profile summary:\n", summary.to_string(), flush=True)
    print("\nBy season:\n", by_season.to_string(index=False), flush=True)
    print("\nDistribution:\n", distribution.to_string(), flush=True)
    if not test_summary.empty:
        print("\n2025-26 profile confirmation:\n", test_summary.to_string(), flush=True)
    print("\n", json.dumps(report, indent=2), flush=True)
    print("\nArtifact:", artifact, flush=True)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--burn-in", type=int, default=5)
    arguments = parser.parse_args()
    evaluate(arguments.root, arguments.artifact, arguments.burn_in)
