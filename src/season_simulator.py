"""Sequential, chip-free FPL transfer simulation for forecast comparisons.

The simulator starts every strategy from the same balanced GW6 squad, applies
the historical rolling-free-transfer limits, tracks acquisition price and
bank, and scores captain fallback plus formation-valid autosubs. It remains a
deliberately myopic baseline: no hits, chips or future-horizon knowledge.
"""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, vstack

from decision_backtest import (
    _constraint_matrix,
    cached_market,
    latest_evaluation_artifact,
    optimize_squad,
    prepare_predictions,
)
from fpl_app import _lineup_total_records, optimal_lineup, selling_price
from risk_profiles import PROFILES, profile_predictions


def lineup_for_ids(market: pd.DataFrame, player_ids: set[int]) -> dict:
    squad = market[market["player_id"].isin(player_ids)].copy()
    if len(squad) != 15:
        raise ValueError(f"Squad has {len(squad)} players in current market, expected 15")
    squad = squad.rename(columns={"player_id": "id", "prediction": "decision_points"})
    squad["recommended_points"] = squad["decision_points"]
    return optimal_lineup(squad)


def autosub_score(lineup: dict) -> tuple[float, str]:
    """Score a historical XI with vice-captain fallback and legal autosubs."""
    starters = lineup["starters"].copy()
    bench = lineup["bench"].copy()
    played = starters["minutes"].gt(0)
    selected_ids = set(starters.loc[played, "id"].astype(int))

    starting_gk = starters[starters["position"].eq("GK")].iloc[0]
    if starting_gk["minutes"] <= 0:
        bench_gk = bench[bench["position"].eq("GK")].iloc[0]
        if bench_gk["minutes"] > 0:
            selected_ids.add(int(bench_gk["id"]))

    active_outfield = starters[~starters["position"].eq("GK") & played]
    missing = 10 - len(active_outfield)
    bench_outfield = bench[~bench["position"].eq("GK")].sort_values("bench_order")
    playable = bench_outfield[bench_outfield["minutes"].gt(0)]
    choices = []
    indices = list(range(len(playable)))
    for count in range(min(missing, len(playable)), -1, -1):
        for subset in combinations(indices, count):
            added = playable.iloc[list(subset)] if subset else playable.iloc[:0]
            final = pd.concat([active_outfield, added])
            counts = final["position"].value_counts()
            legal = (counts.get("DEF", 0) >= 3 and counts.get("MID", 0) >= 2 and
                     counts.get("FWD", 0) >= 1 and counts.get("DEF", 0) <= 5 and
                     counts.get("MID", 0) <= 5 and counts.get("FWD", 0) <= 3)
            if legal:
                # Lexicographic inclusion gives priority to bench slot 1, then 2, then 3.
                priority = tuple(1 if index in subset else 0 for index in indices)
                choices.append((count, priority, added))
        if choices:
            break
    if choices:
        added = max(choices, key=lambda item: (item[0], item[1]))[2]
        selected_ids.update(added["id"].astype(int))

    all_players = pd.concat([starters, bench], ignore_index=True).set_index("id")
    score = float(all_players.loc[list(selected_ids), "actual_points"].sum())
    captain = starters[starters["role"].eq("C")].iloc[0]
    vice = starters[starters["role"].eq("VC")].iloc[0]
    doubled = "none"
    if captain["minutes"] > 0:
        score += float(captain["actual_points"])
        doubled = str(captain["name"])
    elif vice["minutes"] > 0:
        score += float(vice["actual_points"])
        doubled = str(vice["name"])
    return score, doubled


def _complete_squad_market(market: pd.DataFrame, holdings: dict[int, dict]) -> pd.DataFrame:
    """Retain zero-projection placeholders for players who left the registry."""
    result = market.copy()
    present = set(result["player_id"].astype(int))
    missing = set(holdings) - present
    if missing:
        rows = []
        for player_id in missing:
            held = holdings[player_id]
            rows.append({
                "player_id": player_id, "name": held["name"], "team": held["team"],
                "position": held["position"], "value": held["last_price"],
                "prediction": 0.0, "actual_points": 0.0, "minutes": 0,
            })
        result = pd.concat([result, pd.DataFrame(rows)], ignore_index=True)
    return result


def best_free_transfer(market: pd.DataFrame, holdings: dict[int, dict], bank: int,
                       minimum_gain: float = 0.0,
                       excluded_ids: set[int] | None = None) -> dict | None:
    excluded_ids = excluded_ids or set()
    owned = set(holdings)
    records = {
        int(row.player_id): (int(row.player_id), str(row.position), float(row.prediction))
        for row in market.itertuples()
    }
    baseline = _lineup_total_records(records[player_id] for player_id in owned)
    by_id = market.set_index("player_id")
    club_counts = Counter(holdings[player_id]["team"] for player_id in owned)
    best = None
    for player_out in sorted(owned):
        if player_out in excluded_ids:
            continue
        held = holdings[player_out]
        current_price = int(by_id.loc[player_out, "value"])
        sale = selling_price(int(held["purchase_price"]), current_price)
        budget = bank + sale
        candidates = market[
            market["position"].eq(held["position"])
            & ~market["player_id"].isin(owned)
            & market["value"].le(budget)
            & ~market["player_id"].isin(excluded_ids)
        ]
        for incoming in candidates.itertuples():
            counts = club_counts.copy()
            counts[held["team"]] -= 1
            counts[str(incoming.team)] += 1
            if counts[str(incoming.team)] > 3:
                continue
            proposed = (owned - {player_out}) | {int(incoming.player_id)}
            total = _lineup_total_records(records[player_id] for player_id in proposed)
            plan = {
                "out_id": player_out, "out": held["name"],
                "in_id": int(incoming.player_id), "in": str(incoming.name),
                "gain": float(total - baseline), "sale_price": sale,
                "buy_price": int(incoming.value), "new_bank": budget - int(incoming.value),
            }
            key = (plan["gain"], plan["new_bank"], -plan["in_id"], -plan["out_id"])
            if best is None or key > best[0]:
                best = (key, plan)
    return best[1] if best is not None and best[1]["gain"] > minimum_gain else None


def best_transfer_plan(market: pd.DataFrame, holdings: dict[int, dict], bank: int,
                       maximum_transfers: int,
                       minimum_gain: float = 0.0) -> dict | None:
    """Solve the best zero-to-N free-transfer plan exactly for one gameweek.

    The MILP selects the final 15, legal XI and captain in one problem. The
    cash constraint values retained players at their current selling price and
    new players at market price. ``minimum_gain`` is an opportunity cost per
    transfer, so a two-transfer move must improve the projected lineup by more
    than twice that threshold.
    """
    if maximum_transfers < 1:
        return None
    frame = market.sort_values("player_id").reset_index(drop=True).copy()
    owned = set(holdings)
    owned_mask = frame["player_id"].isin(owned).to_numpy(dtype=float)
    if int(owned_mask.sum()) != 15:
        raise ValueError("Every held player must be present in the transfer market")

    # The static squad builder has a £100m current-price cap. A live squad may
    # legitimately be worth more after price rises, so transfers instead use
    # the cash-flow row below (selling values for held players, market prices
    # for new players).
    constraint_frame = frame.copy()
    constraint_frame["value"] = 0
    matrix, lower, upper = _constraint_matrix(constraint_frame)
    n = len(frame)
    sale_values = np.zeros(n)
    for index, row in enumerate(frame.itertuples()):
        player_id = int(row.player_id)
        if player_id in owned:
            sale_values[index] = selling_price(
                int(holdings[player_id]["purchase_price"]), int(row.value)
            )

    cash_row = np.zeros(3 * n)
    cash_row[:n] = np.where(
        owned_mask > 0, sale_values, frame["value"].to_numpy(dtype=float)
    )
    cash_available = float(bank + sale_values.sum())
    retained_row = np.zeros(3 * n)
    retained_row[:n] = owned_mask
    matrix = vstack(
        [matrix, csr_matrix(np.vstack([cash_row, retained_row]))], format="csr"
    )
    lower = np.concatenate([lower, [-np.inf, 15 - maximum_transfers]])
    upper = np.concatenate([upper, [cash_available, np.inf]])

    scores = frame["prediction"].to_numpy(dtype=float)
    primary_objective = np.zeros(3 * n)
    primary_objective[n:2 * n] = -scores
    primary_objective[2 * n:] = -scores
    transfer_cost = max(float(minimum_gain), 1e-6)
    primary_objective[:n] -= transfer_cost * owned_mask
    result = milp(
        primary_objective,
        integrality=np.ones(3 * n, dtype=np.uint8),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": 20},
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"Transfer optimizer failed: {result.message}")

    # Several bench sales can produce the same XI and captain score. Preserve
    # future flexibility by maximizing remaining bank in a second solve while
    # constraining the primary objective to its optimum.
    primary_row = csr_matrix(primary_objective.reshape(1, -1))
    secondary_matrix = vstack([matrix, primary_row], format="csr")
    secondary_lower = np.concatenate([lower, [-np.inf]])
    secondary_upper = np.concatenate([upper, [float(result.fun) + 1e-8]])
    cash_objective = np.zeros(3 * n)
    cash_objective[:n] = cash_row[:n]
    player_ids = frame["player_id"].to_numpy(dtype=float)
    # Prices are integer tenths, so this sub-cent coefficient cannot outweigh
    # one unit of bank. It only makes otherwise identical plans reproducible.
    cash_objective[:n] += 1e-7 * np.where(
        owned_mask > 0, -player_ids, player_ids
    )
    secondary = milp(
        cash_objective,
        integrality=np.ones(3 * n, dtype=np.uint8),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(
            secondary_matrix, secondary_lower, secondary_upper
        ),
        options={"time_limit": 20},
    )
    if secondary.success and secondary.x is not None:
        result = secondary

    selected = set(frame.loc[result.x[:n] > .5, "player_id"].astype(int))
    outgoing_ids = sorted(owned - selected)
    incoming_ids = sorted(selected - owned)
    if len(outgoing_ids) != len(incoming_ids):
        raise RuntimeError("Transfer optimizer returned unequal ins and outs")
    if not outgoing_ids:
        return None

    records = {
        int(row.player_id): (int(row.player_id), str(row.position), float(row.prediction))
        for row in frame.itertuples()
    }
    baseline = _lineup_total_records(records[player_id] for player_id in owned)
    projected = _lineup_total_records(records[player_id] for player_id in selected)
    gain = float(projected - baseline)
    if gain <= transfer_cost * len(outgoing_ids) + 1e-8:
        return None

    by_id = frame.set_index("player_id")
    row_number = {int(row.player_id): index for index, row in enumerate(frame.itertuples())}
    moves = []
    for position in sorted(frame["position"].unique()):
        position_out = [player_id for player_id in outgoing_ids
                        if holdings[player_id]["position"] == position]
        position_in = [player_id for player_id in incoming_ids
                       if str(by_id.loc[player_id, "position"]) == position]
        if len(position_out) != len(position_in):
            raise RuntimeError("Transfer optimizer changed positional squad counts")
        for player_out, player_in in zip(position_out, position_in):
            moves.append({
                "out_id": player_out, "out": holdings[player_out]["name"],
                "in_id": player_in, "in": str(by_id.loc[player_in, "name"]),
                "sale_price": int(sale_values[row_number[player_out]]),
                "buy_price": int(by_id.loc[player_in, "value"]),
            })
    new_bank = int(
        bank + sum(move["sale_price"] for move in moves)
        - sum(move["buy_price"] for move in moves)
    )
    return {"moves": moves, "gain": gain, "new_bank": new_bank}


def historical_transfer_cap(season: str) -> int:
    return 2 if season == "2023-24" else 5


def next_free_transfer_balance(season: str, gameweek: int, remaining: int,
                               cap: int) -> int:
    """Apply the historical roll rule and the 2025-26 AFCON GW16 top-up."""
    if season == "2025-26" and gameweek == 15:
        return min(cap, 5)
    return min(cap, remaining + 1)


def simulate_strategy(prepared: pd.DataFrame, profile: str, initial_ids: set[int],
                      initial_bank: int, minimum_gain: float = 0.0,
                      transfer_cap: int = 1) -> pd.DataFrame:
    holdings: dict[int, dict] = {}
    first_market = prepared[prepared["GW"].eq(prepared["GW"].min())]
    first_by_id = first_market.set_index("player_id")
    for player_id in initial_ids:
        row = first_by_id.loc[player_id]
        holdings[player_id] = {
            "purchase_price": int(row["value"]), "last_price": int(row["value"]),
            "position": str(row["position"]), "team": str(row["team"]),
            "name": str(row["name"]),
        }
    bank = int(initial_bank)
    free_transfers = 0  # Initial GW squad is freshly optimised; GW7 starts with one FT.
    season = str(prepared["season"].iloc[0])
    rows = []
    for index, (gameweek, raw_market) in enumerate(prepared.groupby("GW", sort=True)):
        market = _complete_squad_market(raw_market, holdings)
        by_id = market.set_index("player_id")
        for player_id, held in holdings.items():
            if player_id in by_id.index:
                current = by_id.loc[player_id]
                held.update(last_price=int(current["value"]), team=str(current["team"]),
                            name=str(current["name"]))
        available_before = free_transfers
        transfers, transfer_gain = [], 0.0
        if index > 0:
            plan = best_transfer_plan(
                market, holdings, bank, free_transfers, minimum_gain
            )
            if plan is not None:
                for transfer in plan["moves"]:
                    holdings.pop(transfer["out_id"])
                    incoming = by_id.loc[transfer["in_id"]]
                    holdings[transfer["in_id"]] = {
                        "purchase_price": int(incoming["value"]),
                        "last_price": int(incoming["value"]),
                        "position": str(incoming["position"]),
                        "team": str(incoming["team"]),
                        "name": str(incoming["name"]),
                    }
                transfers = plan["moves"]
                transfer_gain = float(plan["gain"])
                bank = int(plan["new_bank"])
                free_transfers -= len(transfers)
        lineup = lineup_for_ids(market, set(holdings))
        actual_score, doubled = autosub_score(lineup)
        current_prices = market.set_index("player_id")["value"]
        rows.append({
            "season": season, "GW": int(gameweek),
            "profile": profile, "actual_points": actual_score,
            "projected_points": float(lineup["projected_total"]),
            "transfer_out": " + ".join(plan["out"] for plan in transfers),
            "transfer_in": " + ".join(plan["in"] for plan in transfers),
            "transfer_gain": transfer_gain,
            "transfers_used": len(transfers),
            "free_transfers_before": available_before,
            "bank": bank,
            "market_team_value": int(sum(current_prices.get(pid, held["last_price"])
                                         for pid, held in holdings.items())),
            "captain": str(lineup["starters"].query("role == 'C'").iloc[0]["name"]),
            "doubled_player": doubled,
        })
        free_transfers = next_free_transfer_balance(
            season, int(gameweek), free_transfers, transfer_cap
        )
        rows[-1]["free_transfers_after"] = free_transfers
    return pd.DataFrame(rows)


def simulate(root: Path, artifact: Path | None = None, burn_in: int = 5,
             minimum_gain: float = 0.0, transfer_policy: str = "historical") -> Path:
    if transfer_policy not in {"one", "historical"}:
        raise ValueError("transfer_policy must be one or historical")
    artifact = artifact or latest_evaluation_artifact(root)
    profiles = profile_predictions(
        pd.read_csv(artifact / "validation_predictions.csv"),
        pd.read_csv(artifact / "uncertainty_validation_predictions.csv"),
    )
    test_profiles = profile_predictions(
        pd.read_csv(artifact / "test_predictions.csv"),
        pd.read_csv(artifact / "uncertainty_test_predictions.csv"),
    )
    profiles = pd.concat([profiles, test_profiles], ignore_index=True)
    results = []
    for season, season_profiles in profiles.groupby("season", sort=True):
        market_meta = cached_market(root, season)
        prepared = prepare_predictions(
            season_profiles, {season: market_meta}, PROFILES, burn_in
        )
        first_gw = int(prepared["GW"].min())
        balanced_first = prepared[
            prepared["model"].eq("balanced") & prepared["GW"].eq(first_gw)
        ]
        initial = optimize_squad(balanced_first, "prediction", bench_weight=.1)["squad"]
        initial_ids = set(initial["player_id"].astype(int))
        initial_bank = 1000 - int(initial["value"].sum())
        cap = 1 if transfer_policy == "one" else historical_transfer_cap(str(season))
        for profile in PROFILES:
            strategy = prepared[prepared["model"].eq(profile)].rename(
                columns={"position_prediction": "source_position"}
            )
            results.append(simulate_strategy(
                strategy, profile, initial_ids, initial_bank, minimum_gain,
                transfer_cap=cap,
            ))
    gameweeks = pd.concat(results, ignore_index=True)
    summary = gameweeks.groupby(["season", "profile"]).agg(
        gameweeks=("GW", "size"), total_points=("actual_points", "sum"),
        mean_points=("actual_points", "mean"), score_std=("actual_points", "std"),
        transfers=("transfers_used", "sum"),
        rolled_gameweeks=("free_transfers_after", lambda values: int(values.gt(1).sum())),
        final_bank=("bank", "last"), final_market_team_value=("market_team_value", "last"),
    ).reset_index()
    balanced_by_season = summary.loc[
        summary["profile"].eq("balanced"), ["season", "total_points"]
    ].set_index("season")["total_points"]
    summary["vs_balanced"] = summary.apply(
        lambda row: row["total_points"] - balanced_by_season.loc[row["season"]], axis=1
    )
    totals = summary.groupby("profile").agg(
        seasons=("season", "size"), total_points=("total_points", "sum"),
        mean_season_points=("total_points", "mean"), total_transfers=("transfers", "sum"),
    ).sort_values("total_points", ascending=False)
    totals["vs_balanced"] = totals["total_points"] - totals.loc["balanced", "total_points"]
    report = {
        "start": f"shared balanced squad at GW{burn_in + 1}",
        "transfer_policy": transfer_policy,
        "historical_caps": "2023-24: 2; 2024-25 onward: 5; 2025-26 GW16 AFCON top-up",
        "multi_transfer_search": "exact joint MILP for squad, XI, captain and 0..N transfers",
        "minimum_projected_gain": minimum_gain,
        "autosubs": "captain fallback and formation-valid bench priority",
        "caveat": "Myopic one-GW forecasts and post-GW historical prices; no chips.",
    }
    suffix = str(minimum_gain).replace("-", "neg").replace(".", "_")
    stem = f"sequential_transfer_{transfer_policy}_min_gain_{suffix}"
    gameweeks.to_csv(artifact / f"{stem}_gameweeks.csv", index=False)
    summary.to_csv(artifact / f"{stem}_by_season.csv", index=False)
    totals.to_csv(artifact / f"{stem}_summary.csv")
    (artifact / f"{stem}.json").write_text(json.dumps(report, indent=2))
    print("\nSequential transfer simulation:\n", summary.to_string(index=False), flush=True)
    print("\nCombined:\n", totals.to_string(), flush=True)
    print("\nArtifact:", artifact, flush=True)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--burn-in", type=int, default=5)
    parser.add_argument("--minimum-gain", type=float, default=0.0)
    parser.add_argument("--transfer-policy", choices=["one", "historical"],
                        default="historical")
    arguments = parser.parse_args()
    simulate(arguments.root, arguments.artifact, arguments.burn_in,
             arguments.minimum_gain, arguments.transfer_policy)
