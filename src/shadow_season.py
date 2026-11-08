"""Shadow season (plan E2): policies carry a real squad forward round by round.

Every policy starts from the same actual FPL squad (bank, purchase prices, free
transfers) and keeps its own state: holdings, bank, free transfers and chips.
Before a deadline each policy decides from the loop's locked bundle for that
round (frozen predictions on identical rows, pre-deadline prices). After FPL
checks the round it is scored with legal autosubs and vice-captain fallback
(``season_simulator.autosub_score``) against fpl-data outcomes.

Policies: ``hold`` never transfers and rolls free transfers; any model in the
bundle (``incumbent``, challengers) makes the best zero-to-FT plan with
``season_simulator.best_transfer_plan``. No hits and no chips yet; chips are
carried as unused so a later policy can play them.

    python src/shadow_season.py start --team 5139814 --event 10
    python src/shadow_season.py lock --event 10      # before the deadline
    python src/shadow_season.py score --event 10     # after fpl-data exports the round

Results live in ``artifacts/shadow_season/<season>_<team>/``; files are never
overwritten.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from fpl_rules import next_free_transfers
from season_simulator import autosub_score, best_transfer_plan, lineup_for_ids

ROOT = Path(__file__).resolve().parents[1]
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
CHIPS = ["wildcard", "free_hit", "bench_boost", "triple_captain"]


def _write_new(path: Path, payload: dict) -> Path:
    if path.exists():
        raise FileExistsError(f"{path} exists; shadow-season files are never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def folder(root: Path, season: str, team: int) -> Path:
    return Path(root) / "artifacts/shadow_season" / f"{season}_{team}"


def start_state(squad: list[dict], bank: int, free_transfers: int, policies: list[str], event: int,
                source: str) -> dict:
    """Same starting point for every policy. ``squad`` rows: id, name, position, team, purchase_price."""
    holdings = {str(p["id"]): {key: p[key] for key in ("name", "position", "team", "purchase_price")} for p in squad}
    if len(holdings) != 15:
        raise ValueError("A shadow season needs the full 15-player squad")
    return {"first_event": event, "next_event": event, "source": source, "policies": {
        name: {"holdings": holdings, "bank": int(bank), "free_transfers": int(free_transfers),
               "chips": {chip: "available" for chip in CHIPS}, "points": 0.0} for name in policies}}


def bundle_market(bundle: Path, decisions: Path, model: str) -> pd.DataFrame:
    """Pre-deadline prices from the decisions lock plus one model's frozen weekly predictions."""
    with gzip.open(Path(decisions) / "bootstrap.json.gz", "rt") as handle:
        bootstrap = json.load(handle)
    predictions = pd.read_csv(Path(bundle) / "predictions.csv")
    weekly = predictions[predictions.model.eq(model)].groupby("player_id").prediction.sum()
    if weekly.empty:
        raise ValueError(f"{model} is not in {bundle.name}")
    return pd.DataFrame([{"player_id": e["id"], "name": e["web_name"], "team": str(e["team"]),
                          "position": POSITIONS[e["element_type"]], "value": int(e["now_cost"]),
                          "prediction": float(weekly.get(e["id"], 0.0))}
                         for e in bootstrap["elements"] if e["element_type"] in POSITIONS])


def decide(state: dict, market: pd.DataFrame, policy: str) -> dict:
    """One policy's locked decision: transfers within free transfers, then XI, captain, VC and bench."""
    holdings = {int(k): v for k, v in state["holdings"].items()}
    plan = None
    if policy != "hold" and state["free_transfers"] > 0:
        plan = best_transfer_plan(market, holdings, state["bank"], state["free_transfers"])
    moves = plan["moves"] if plan else []
    owned = (set(holdings) - {m["out_id"] for m in moves}) | {m["in_id"] for m in moves}
    lineup = lineup_for_ids(market.copy(), owned)
    return {"policy": policy, "moves": moves, "bank_after": plan["new_bank"] if plan else state["bank"],
            "squad": sorted(owned), "starters": lineup["starters"].id.astype(int).tolist(),
            "captain": int(lineup["starters"].query("role == 'C'").id.iloc[0]),
            "vice_captain": int(lineup["starters"].query("role == 'VC'").id.iloc[0]),
            "bench": lineup["bench"].id.astype(int).tolist(), "projected_points": float(lineup["projected_total"])}


def lock(root: Path, season: str, team: int, event: int, now=None) -> Path:
    """Freeze every policy's decision for ``event`` from the loop's locked bundle, before the deadline."""
    base = folder(root, season, team)
    state = json.loads((base / f"state_gw{event}.json").read_text())
    bundles = sorted((Path(root) / "artifacts/prospective").glob(f"loop_gw{event}_*/manifest.json"))
    if not bundles:
        raise ValueError(f"GW{event} has no locked loop bundle; lock the round first")
    bundle = bundles[0].parent
    decisions = bundle.with_name(bundle.name + "_decisions")
    manifest = json.loads(bundles[0].read_text())
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now >= pd.Timestamp(manifest["deadline"]):
        raise ValueError(f"GW{event} deadline has passed; a shadow decision must be locked before it")
    decisions_by_policy = {}
    for policy, policy_state in state["policies"].items():
        model = "incumbent" if policy == "hold" else policy
        decisions_by_policy[policy] = decide(policy_state, bundle_market(bundle, decisions, model), policy)
    payload = {"event": event, "locked_at": now.isoformat(), "deadline": manifest["deadline"],
               "bundle": bundle.name, "bundle_manifest_sha256": hashlib.sha256(bundles[0].read_bytes()).hexdigest(),
               "decisions": decisions_by_policy}
    return _write_new(base / f"lock_gw{event}.json", payload)


def outcomes(root: Path, season: str, event: int) -> pd.DataFrame:
    path = Path(root) / "fpl-data/data" / season / "gws" / f"gw{event}.csv"
    if not path.exists():
        raise ValueError(f"GW{event} outcomes are not exported yet ({path})")
    rows = pd.read_csv(path)
    return rows.groupby("element").agg(actual_points=("total_points", "sum"), minutes=("minutes", "sum"))


def score_decision(decision: dict, market: pd.DataFrame, result: pd.DataFrame) -> tuple[float, str]:
    """Actual points of a locked XI with legal autosubs and captain → vice fallback."""
    frame = market.merge(result, left_on="player_id", right_index=True, how="left").fillna({"actual_points": 0, "minutes": 0})
    lineup = lineup_for_ids(frame, set(decision["squad"]))
    lineup["starters"]["role"] = ""  # the locked captaincy wins over a recomputed one
    lineup["starters"].loc[lineup["starters"].id.eq(decision["captain"]), "role"] = "C"
    lineup["starters"].loc[lineup["starters"].id.eq(decision["vice_captain"]), "role"] = "VC"
    if sorted(lineup["starters"].id) != sorted(decision["starters"]):
        raise ValueError("Locked XI cannot be rebuilt from the bundle; refusing to score")
    by_id = frame.set_index("player_id")
    bench = by_id.loc[decision["bench"]].reset_index().rename(columns={"player_id": "id"})
    bench["bench_order"] = ["GK", "1", "2", "3"]  # locked order: reserve keeper, then outfield priority
    lineup["bench"] = bench
    return autosub_score(lineup)


def score(root: Path, season: str, team: int, event: int) -> Path:
    """Score the locked round and write the next state (never overwriting)."""
    base = folder(root, season, team)
    locked = json.loads((base / f"lock_gw{event}.json").read_text())
    state = json.loads((base / f"state_gw{event}.json").read_text())
    bundle = Path(root) / "artifacts/prospective" / locked["bundle"]
    decisions_bundle = bundle.with_name(bundle.name + "_decisions")
    result = outcomes(root, season, event)
    market = bundle_market(bundle, decisions_bundle, "incumbent")[["player_id", "name", "team", "position", "value", "prediction"]]
    scores, next_state = {}, {**state, "next_event": event + 1, "policies": {}}
    for policy, decision in locked["decisions"].items():
        points, doubled = score_decision(decision, market, result)
        old = state["policies"][policy]
        holdings = {k: v for k, v in old["holdings"].items() if int(k) not in {m["out_id"] for m in decision["moves"]}}
        by_id = market.set_index("player_id")
        for move in decision["moves"]:
            row = by_id.loc[move["in_id"]]
            holdings[str(move["in_id"])] = {"name": row["name"], "position": row["position"], "team": row["team"],
                                           "purchase_price": int(move["buy_price"])}
        next_state["policies"][policy] = {**old, "holdings": holdings, "bank": decision["bank_after"],
                                          "free_transfers": next_free_transfers(old["free_transfers"], len(decision["moves"])),
                                          "points": old["points"] + points}
        scores[policy] = {"points": points, "doubled": doubled, "transfers": len(decision["moves"]),
                          "season_points": next_state["policies"][policy]["points"]}
    _write_new(base / f"state_gw{event + 1}.json", next_state)
    return _write_new(base / f"score_gw{event}.json", {"event": event, "scores": scores,
                                                       "scoring": "legal autosubs, captain then vice-captain"})


def start(root: Path, team_id: int, event: int, policies: list[str]) -> Path:
    """Start from the public squad the FPL app imports today (purchase prices reconstructed)."""
    from fpl_app import import_team
    team = import_team(str(team_id), root)
    if team.target_event != event:
        raise ValueError(f"The imported squad is for GW{team.target_event}, not GW{event}")
    squad = [{"id": int(r.id), "name": r.name, "position": r.position, "team": str(r.team_id),
              "purchase_price": int(r.purchase_price)} for r in team.squad.itertuples()]
    season = str(pd.read_csv(team.forecast_path, nrows=1).season.iloc[0])
    state = start_state(squad, team.bank, team.free_transfers, policies, event,
                        source=f"public FPL squad for GW{event}, imported {datetime.now(timezone.utc).isoformat()}")
    state["chip_status"] = team.chip_status
    return _write_new(folder(root, season, team_id) / f"state_gw{event}.json", state)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["start", "lock", "score"])
    parser.add_argument("--team", type=int, default=5139814)
    parser.add_argument("--event", type=int, required=True)
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--policies", nargs="*", default=["hold", "incumbent"])
    args = parser.parse_args(argv)
    if args.command == "start":
        path = start(ROOT, args.team, args.event, args.policies)
    elif args.command == "lock":
        path = lock(ROOT, args.season, args.team, args.event)
    else:
        path = score(ROOT, args.season, args.team, args.event)
    print(path.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
