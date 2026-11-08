"""Pre-registered criterion v2 (plan E1; docs/prospective_criterion_v2_2026-11-06.md).

v1 (team points of each model's own 100m squad) has very low power: the paired
team-point difference has SD ≈ 13 per round. v2 compares forecasts player by
player on a cohort fixed before the deadline, which uses far more of each
round's information. v1 stays unchanged and is still reported.

Everything the cohort needs is in the lock: the reference model's frozen
predictions and probabilities and the squads each model chose. Outcomes come
from the evaluation's ``scored_predictions.csv``.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

CRITERION_V2 = {
    "version": 2, "registered": "2026-11-06T15:30:00+00:00",
    "document": "docs/prospective_criterion_v2_2026-11-06.md",
    "applies_to": "loop-v1 bundles whose lock started after `registered` (GW11 onwards)",
    "primary_challenger": "features_v2_20261106", "reference": "incumbent",
    "min_rounds": 8, "confidence": 0.95, "resamples": 10_000, "seed": 20261106,
    "cohort": {"top_n": 100, "min_appearance_probability": 0.5, "squads": "every locked squad"},
    "primary": "mean paired difference in weekly absolute error on the cohort, rounds resampled as blocks",
    "guard": "mean paired difference in pinball loss (Q10/Q50/Q90) <= 0 when both models have quantiles",
    "multiplicity": "primary challenger at 5 %; every other challenger exploratory with Holm correction",
}
LEVELS = (0.1, 0.5, 0.9)


def cohort(predictions: pd.DataFrame, selections: pd.DataFrame, reference: str = "incumbent") -> set[int]:
    """Players fixed before the deadline: top N by the reference, likely to play, or in any locked squad."""
    rules = CRITERION_V2["cohort"]
    ref = predictions[predictions.model.eq(reference)]
    weekly = ref.groupby("player_id").prediction.sum()
    chosen = set(weekly.nlargest(rules["top_n"]).index)
    if "p_zero_minutes" in ref and ref.p_zero_minutes.notna().any():
        # Probability of at least one appearance over the round's fixtures.
        absent = ref.groupby("player_id").p_zero_minutes.prod()
        chosen |= set(absent[(1 - absent) >= rules["min_appearance_probability"]].index)
    return chosen | set(selections.player_id.astype(int))


def pinball(actual, quantiles: np.ndarray) -> np.ndarray:
    """Mean pinball loss over Q10/Q50/Q90 per row (a three-point CRPS approximation)."""
    actual = np.asarray(actual, float)[:, None]
    tau = np.asarray(LEVELS)[None, :]
    error = actual - quantiles
    return np.mean(np.maximum(tau * error, (tau - 1) * error), axis=1)


def round_metrics(scored: pd.DataFrame, players: set[int]) -> pd.DataFrame:
    """Per model and cohort player: weekly absolute error and pinball loss."""
    rows = scored[scored.player_id.isin(players)]
    keys = ["model", "player_id"]
    weekly = rows.groupby(keys)[["prediction", "target_points"]].sum()
    weekly["abs_error"] = (weekly.prediction - weekly.target_points).abs()
    quantile_columns = [f"prediction_q{int(level * 100)}" for level in LEVELS]
    if set(quantile_columns) <= set(rows):
        # Weekly quantiles for single-fixture rounds; a double Gameweek uses its first
        # fixture's quantiles plus the other fixtures' medians (documented simplification).
        first = rows.sort_values("fixture").groupby(keys)
        q = first[quantile_columns].first()
        extra = first.prediction_q50.sum() - first.prediction_q50.first()
        weekly["pinball"] = pinball(weekly.target_points, q.add(extra, axis=0).to_numpy(float))
        weekly.loc[q.isna().any(axis=1), "pinball"] = np.nan
    return weekly.reset_index()


def load_round(eval_dir: Path, bundle: Path, decisions: Path) -> pd.DataFrame:
    scored = pd.read_csv(next((Path(eval_dir) / "forecasts").glob("*/scored_predictions.csv")))
    predictions = pd.read_csv(Path(bundle) / "predictions.csv")
    selections = pd.read_csv(Path(decisions) / "selections.csv")
    metrics = round_metrics(scored, cohort(predictions, selections))
    return metrics.assign(round=Path(eval_dir).name)


def _bootstrap(per_round: np.ndarray) -> tuple[float, float, np.ndarray]:
    rng = np.random.default_rng(CRITERION_V2["seed"])
    means = rng.choice(per_round, (CRITERION_V2["resamples"], len(per_round)), replace=True).mean(axis=1)
    tail = (1 - CRITERION_V2["confidence"]) / 2 * 100
    return float(np.percentile(means, tail)), float(np.percentile(means, 100 - tail)), means


def summarize(rows: pd.DataFrame) -> list[dict]:
    """Per challenger: paired per-round cohort differences, block-bootstrap CI and Holm-adjusted p."""
    reference = CRITERION_V2["reference"]
    if rows.empty:
        return []
    ref = rows[rows.model.eq(reference)].set_index(["round", "player_id"])
    results = []
    for model, frame in rows[rows.model.ne(reference)].groupby("model"):
        joined = frame.set_index(["round", "player_id"]).join(ref, rsuffix="_ref", how="inner")
        diff = (joined.abs_error - joined.abs_error_ref).groupby(level=0).mean()
        row = {"model": model, "rounds": int(len(diff)), "players_per_round": float(joined.groupby(level=0).size().mean()),
               "mae_diff_mean": float(diff.mean()), "mae_diff_ci": None, "p_one_sided": None,
               "pinball_diff_mean": None}
        if "pinball" in joined and joined[["pinball", "pinball_ref"]].notna().all(axis=1).any():
            both = joined.dropna(subset=["pinball", "pinball_ref"])
            row["pinball_diff_mean"] = float((both.pinball - both.pinball_ref).groupby(level=0).mean().mean())
        if len(diff) >= 2:
            low, high, means = _bootstrap(diff.to_numpy(float))
            row["mae_diff_ci"] = [low, high]
            row["p_one_sided"] = float((means >= 0).mean())  # share of resamples where the challenger is not better
        results.append(row)
    _holm(results)
    for row in results:
        primary = row["model"] == CRITERION_V2["primary_challenger"]
        ci_ok = row["mae_diff_ci"] is not None and row["mae_diff_ci"][1] < 0
        guard = row["pinball_diff_mean"] is None or row["pinball_diff_mean"] <= 0
        enough = row["rounds"] >= CRITERION_V2["min_rounds"]
        row["role"] = "primary" if primary else "exploratory"
        row["criterion_met"] = bool(enough and guard and (ci_ok if primary else
                                    row["p_holm"] is not None and row["p_holm"] < 1 - CRITERION_V2["confidence"]))
    return results


def _holm(results: list[dict]) -> None:
    """Holm step-down over the exploratory challengers' one-sided p-values."""
    explore = sorted((r for r in results if r["model"] != CRITERION_V2["primary_challenger"] and r["p_one_sided"] is not None),
                     key=lambda r: r["p_one_sided"])
    running = 0.0
    for rank, row in enumerate(explore):
        running = max(running, min(1.0, (len(explore) - rank) * row["p_one_sided"]))
        row["p_holm"] = running
    for row in results:
        row.setdefault("p_holm", None)


def rounds_needed(sd_per_round: float, effect: float, power: float = 0.8, confidence: float = 0.95) -> int:
    """Rounds for a one-sided test to detect ``effect`` (same unit as the SD) with the given power."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2) + NormalDist().inv_cdf(power)
    return int(np.ceil((z * sd_per_round / effect) ** 2))


def applies(bundle: Path) -> bool:
    manifest = json.loads((Path(bundle) / "manifest.json").read_text())
    return pd.Timestamp(manifest["started_at"]) >= pd.Timestamp(CRITERION_V2["registered"])


SQUAD_SHAPE = {1: 2, 2: 5, 3: 5, 4: 3}  # FPL element_type -> squad slots
POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def synthetic_squads(elements: list[dict], count: int = 300, seed: int = CRITERION_V2["seed"],
                     budget: int = 1000) -> list[list[int]]:
    """Legal squads (2/5/5/3, ≤3 per club, ≤£100m) drawn in proportion to ownership."""
    rng = np.random.default_rng(seed)
    pool = [e for e in elements if e.get("element_type") in SQUAD_SHAPE and e.get("can_select", True)]
    weight = np.array([max(float(e.get("selected_by_percent") or 0), 0.05) for e in pool])
    squads = []
    while len(squads) < count:
        need, clubs, chosen, cost = dict(SQUAD_SHAPE), {}, [], 0
        for index in rng.choice(len(pool), len(pool), replace=False, p=weight / weight.sum()):
            e = pool[index]
            slots_left = sum(need.values())
            cheapest_rest = 40 * (slots_left - 1)  # keep money for the remaining slots
            if need[e["element_type"]] and clubs.get(e["team"], 0) < 3 and cost + e["now_cost"] + cheapest_rest <= budget:
                need[e["element_type"]] -= 1
                clubs[e["team"]] = clubs.get(e["team"], 0) + 1
                chosen.append(int(e["id"]))
                cost += e["now_cost"]
                if not sum(need.values()):
                    break
        if not sum(need.values()):
            squads.append(chosen)
    return squads


def synthetic_squad_points(predictions: pd.DataFrame, actual: pd.Series, elements: list[dict],
                           squads: list[list[int]]) -> pd.DataFrame:
    """Each model picks XI and captain in every synthetic squad; actual points (captain ×2, no autosubs)."""
    from fpl_app import optimal_lineup
    positions = {int(e["id"]): POSITION_NAMES[e["element_type"]] for e in elements if e.get("element_type") in POSITION_NAMES}
    rows = []
    for model, frame in predictions.groupby("model"):
        weekly = frame.groupby("player_id").prediction.sum()
        for number, squad in enumerate(squads):
            table = pd.DataFrame({"id": squad, "position": [positions[i] for i in squad]})
            table["recommended_points"] = table.id.map(weekly).fillna(0.0)
            lineup = optimal_lineup(table)
            starters = lineup["starters"]
            points = starters.id.map(actual).fillna(0).sum() + starters.loc[starters.role.eq("C"), "id"].map(actual).fillna(0).sum()
            rows.append({"model": model, "squad": number, "points": float(points)})
    return pd.DataFrame(rows)


def synthetic_round(bundle: Path, decisions: Path, eval_dir: Path, count: int = 300) -> pd.DataFrame:
    """Secondary v2 measure for one round: mean synthetic-squad points per model."""
    with gzip.open(Path(decisions) / "bootstrap.json.gz", "rt") as handle:
        elements = json.load(handle)["elements"]
    scored = pd.read_csv(next((Path(eval_dir) / "forecasts").glob("*/scored_predictions.csv")))
    actual = scored.drop_duplicates(["player_id", "fixture"]).groupby("player_id").target_points.sum()
    predictions = pd.read_csv(Path(bundle) / "predictions.csv")
    return synthetic_squad_points(predictions, actual, elements, synthetic_squads(elements, count))
