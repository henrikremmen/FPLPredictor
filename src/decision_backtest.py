"""Backtest forecast models through the actual constrained FPL selection task.

This diagnostic joins chronological out-of-fold predictions to historical FPL
prices and clubs, then solves a mixed-integer squad, lineup and captain problem
for every gameweek.  It complements point-error metrics; it does not simulate
transfers, price changes within a gameweek, autosubs or chips.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
import requests
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, eye, hstack, vstack


POSITIONS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
START_LIMITS = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
RAW_URL = (
    "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
    "master/data/{season}/gws/merged_gw.csv"
)


def latest_evaluation_artifact(root: Path) -> Path:
    candidates = []
    for settings_path in root.glob("artifacts/models/nextgen_*/settings.json"):
        try:
            settings = json.loads(settings_path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if settings.get("production_eligible") is True:
            model_path = settings_path.parent / "model.joblib"
            prediction_path = settings_path.parent / "validation_predictions.csv"
            if model_path.exists() and prediction_path.exists():
                candidates.append(settings_path.parent)
    if not candidates:
        raise FileNotFoundError("No production-eligible nextgen artifact with OOF predictions")
    return max(candidates, key=lambda path: (path / "model.joblib").stat().st_mtime)


def cached_market(root: Path, season: str) -> pd.DataFrame:
    """Download and cache the source CSV, preserving the source bytes."""
    destination = root / "data/raw/decision_backtest" / f"merged_gw_{season}.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        response = requests.get(RAW_URL.format(season=season), timeout=(10, 120))
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            handle.write(response.content)
            temporary = Path(handle.name)
        temporary.replace(destination)
    columns = [
        "element", "name", "team", "position", "value", "GW", "kickoff_time", "minutes"
    ]
    raw = pd.read_csv(destination, usecols=columns)
    raw = raw[raw["position"].isin(POSITIONS)].copy()  # 2024-25 also contains managers
    raw["kickoff_time"] = pd.to_datetime(raw["kickoff_time"], utc=True, errors="coerce")
    raw = raw.sort_values(["GW", "kickoff_time", "element"])
    market = raw.groupby(["GW", "element"], as_index=False).agg(
        name=("name", "first"), team=("team", "first"),
        position=("position", "first"), value=("value", "first"),
        minutes=("minutes", "sum"),
    ).rename(columns={"element": "player_id"})
    if market[["team", "position", "value"]].isna().any().any():
        raise ValueError(f"Incomplete historical market metadata for {season}")
    return market


def _constraint_matrix(players: pd.DataFrame) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
    """Build constraints for [squad, starter, captain] binary variables."""
    n = len(players)
    global_rows, lower, upper = [], [], []

    def add(squad=None, starter=None, captain=None, lo=-np.inf, hi=np.inf):
        row = np.zeros(3 * n)
        if squad is not None:
            row[:n] = squad
        if starter is not None:
            row[n:2 * n] = starter
        if captain is not None:
            row[2 * n:] = captain
        global_rows.append(row)
        lower.append(lo)
        upper.append(hi)

    add(squad=np.ones(n), lo=15, hi=15)
    for position, count in POSITIONS.items():
        mask = players["position"].eq(position).to_numpy(dtype=float)
        add(squad=mask, lo=count, hi=count)
    add(squad=players["value"].to_numpy(dtype=float), hi=1000)
    for team in sorted(players["team"].unique()):
        add(squad=players["team"].eq(team).to_numpy(dtype=float), hi=3)
    add(starter=np.ones(n), lo=11, hi=11)
    for position, (minimum, maximum) in START_LIMITS.items():
        mask = players["position"].eq(position).to_numpy(dtype=float)
        add(starter=mask, lo=minimum, hi=maximum)
    add(captain=np.ones(n), lo=1, hi=1)

    identity = eye(n, format="csr")
    zero = csr_matrix((n, n))
    starter_requires_squad = hstack([-identity, identity, zero], format="csr")
    captain_requires_start = hstack([zero, -identity, identity], format="csr")
    matrix = vstack([
        csr_matrix(np.asarray(global_rows)), starter_requires_squad, captain_requires_start
    ], format="csr")
    lower = np.concatenate([np.asarray(lower), np.full(2 * n, -np.inf)])
    upper = np.concatenate([np.asarray(upper), np.zeros(2 * n)])
    return matrix, lower, upper


def optimize_squad(players: pd.DataFrame, score_column: str = "prediction",
                   bench_weight: float = 0.0) -> dict:
    """Return the exact optimal squad, legal XI and captain for one gameweek."""
    required = {"player_id", "name", "team", "position", "value", score_column}
    missing = required - set(players)
    if missing:
        raise ValueError(f"Missing optimizer columns: {sorted(missing)}")
    frame = players.dropna(subset=list(required)).sort_values("player_id").reset_index(drop=True)
    if not set(POSITIONS).issubset(frame["position"].unique()):
        raise ValueError("Player market is missing at least one FPL position")
    matrix, lower, upper = _constraint_matrix(frame)
    n = len(frame)
    scores = frame[score_column].to_numpy(dtype=float)
    objective = np.zeros(3 * n)
    objective[:n] = -bench_weight * scores
    objective[n:2 * n] = -(1 - bench_weight) * scores
    objective[2 * n:] = -scores
    result = milp(
        objective,
        integrality=np.ones(3 * n, dtype=np.uint8),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": 20},
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"FPL optimizer failed: {result.message}")
    squad = frame[result.x[:n] > 0.5].copy()
    starters = frame[result.x[n:2 * n] > 0.5].copy()
    captain = frame[result.x[2 * n:] > 0.5].copy()
    if len(squad) != 15 or len(starters) != 11 or len(captain) != 1:
        raise RuntimeError("Optimizer returned an invalid integral selection")
    return {"squad": squad, "starters": starters, "captain": captain.iloc[0],
            "objective": float(-result.fun)}


def prepare_predictions(oof: pd.DataFrame, markets: dict[str, pd.DataFrame],
                        models: list[str], burn_in: int) -> pd.DataFrame:
    selected = oof[oof["model"].isin(models) & oof["GW"].gt(burn_in)].copy()
    weekly = selected.groupby(
        ["model", "season", "GW", "player_id"], as_index=False
    ).agg(prediction=("prediction", "sum"), actual_points=("target_points", "sum"),
          position=("position", "first"))
    joined = []
    for season, group in weekly.groupby("season"):
        market = markets[season].copy()
        merged = group.merge(market, on=["GW", "player_id"], how="inner",
                             suffixes=("_prediction", ""), validate="many_to_one")
        mismatch = merged["position_prediction"].ne(merged["position"])
        if mismatch.any():
            raise ValueError(f"Position mismatch in historical market for {season}")
        if len(merged) != len(group):
            raise ValueError(f"Could not join every prediction to market metadata for {season}")
        joined.append(merged.drop(columns="position_prediction"))
    return pd.concat(joined, ignore_index=True)


def backtest(prepared: pd.DataFrame, models: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rows = []
    for (season, gameweek), all_models in prepared.groupby(["season", "GW"], sort=True):
        actual_market = all_models[all_models["model"].eq(models[0])]
        oracle = optimize_squad(actual_market, "actual_points")
        oracle_score = float(oracle["starters"]["actual_points"].sum() +
                             oracle["captain"]["actual_points"])
        for model in models:
            market = all_models[all_models["model"].eq(model)]
            chosen = optimize_squad(market, "prediction")
            actual_score = float(chosen["starters"]["actual_points"].sum() +
                                 chosen["captain"]["actual_points"])
            rows.append({
                "season": season, "GW": int(gameweek), "model": model,
                "predicted_points": chosen["objective"], "actual_points": actual_score,
                "oracle_points": oracle_score, "regret": oracle_score - actual_score,
                "squad_cost": int(chosen["squad"]["value"].sum()),
                "captain": str(chosen["captain"]["name"]),
                "captain_id": int(chosen["captain"]["player_id"]),
                "starter_ids": ";".join(map(str, sorted(chosen["starters"]["player_id"]))),
            })
    gameweeks = pd.DataFrame(rows)
    summary = gameweeks.groupby("model").agg(
        gameweeks=("GW", "size"), total_actual_points=("actual_points", "sum"),
        mean_actual_points=("actual_points", "mean"),
        mean_predicted_points=("predicted_points", "mean"),
        mean_oracle_points=("oracle_points", "mean"), mean_regret=("regret", "mean"),
        mean_squad_cost=("squad_cost", "mean"),
    ).sort_values("mean_actual_points", ascending=False)
    bootstrap = paired_bootstrap(gameweeks, models[-1], models[0])
    return gameweeks, summary, bootstrap


def paired_bootstrap(gameweeks: pd.DataFrame, candidate: str, reference: str,
                     draws: int = 5000) -> dict:
    pivot = gameweeks.pivot(index=["season", "GW"], columns="model", values="actual_points")
    differences = (pivot[candidate] - pivot[reference]).to_numpy(dtype=float)
    rng = np.random.default_rng(42)
    samples = differences[rng.integers(0, len(differences), size=(draws, len(differences)))].mean(axis=1)
    return {
        "candidate": candidate, "reference": reference, "gameweeks": len(differences),
        "mean_points_gain_per_gameweek": float(differences.mean()),
        "total_points_gain": float(differences.sum()),
        "low_95": float(np.quantile(samples, 0.025)),
        "high_95": float(np.quantile(samples, 0.975)),
        "candidate_better_gameweeks": int((differences > 0).sum()),
        "candidate_worse_gameweeks": int((differences < 0).sum()),
        "same_gameweeks": int((differences == 0).sum()),
    }


def run(root: Path, artifact: Path | None = None, burn_in: int = 5,
        models: list[str] | None = None) -> Path:
    artifact = artifact or latest_evaluation_artifact(root)
    oof = pd.read_csv(artifact / "validation_predictions.csv")
    evaluation_settings = json.loads((artifact / "settings.json").read_text())
    winner = str(evaluation_settings["winner"])
    if models is None:
        models = list(dict.fromkeys([
            "incumbent_blend", "long_history_mixture", winner
        ]))
    available = set(oof["model"].unique())
    missing = set(models) - available
    if missing:
        raise ValueError(f"Models missing from OOF predictions: {sorted(missing)}")
    seasons = sorted(oof.loc[oof["model"].isin(models), "season"].unique())
    markets = {season: cached_market(root, season) for season in seasons}
    prepared = prepare_predictions(oof, markets, models, burn_in)
    gameweeks, summary, bootstrap = backtest(prepared, models)
    gameweeks.to_csv(artifact / "decision_backtest_gameweeks.csv", index=False)
    summary.to_csv(artifact / "decision_backtest_summary.csv")
    by_season = gameweeks.groupby(["season", "model"]).agg(
        gameweeks=("GW", "size"), total_actual_points=("actual_points", "sum"),
        mean_actual_points=("actual_points", "mean"), mean_regret=("regret", "mean"),
    ).reset_index()
    by_season.to_csv(artifact / "decision_backtest_by_season.csv", index=False)
    decision_gate = bool(bootstrap["mean_points_gain_per_gameweek"] >= 0)
    report = {
        "models": models, "seasons": seasons, "burn_in_gameweeks": burn_in,
        "optimizer": "exact scipy.optimize.milp: squad, XI, captain, budget, position, club",
        "price_caveat": "Historical value is scraped after the GW and is not certified deadline price.",
        "scope_caveat": "Static weekly selection; no transfers, autosubs, chips or dynamic team value.",
        "paired_candidate_vs_incumbent": bootstrap,
        "decision_gate": decision_gate,
        "deployment_eligible": bool(
            evaluation_settings.get("production_eligible") is True and decision_gate
        ),
    }
    (artifact / "decision_backtest.json").write_text(json.dumps(report, indent=2))
    print("\nConstrained decision backtest:\n", summary.to_string(), flush=True)
    print("\nPaired candidate comparison:\n", json.dumps(bootstrap, indent=2), flush=True)
    print("\nArtifact:", artifact, flush=True)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--burn-in", type=int, default=5)
    arguments = parser.parse_args()
    run(arguments.root, arguments.artifact, arguments.burn_in)
