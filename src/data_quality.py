"""Data quality for the app and the lock banner (plans O1b, O2, O3).

Reads local files only: the ``fpl-data`` checkout (filled by
``src/fpl_collect.py``) and ``data/raw/live_fpl`` captures. Nothing here fetches.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from fpl_collect import GAP_ALERT_HOURS, snapshot_manifests


def fpl_data_freshness(root: Path, now=None) -> dict:
    """Latest fpl-data snapshot and exported rounds; stale after ``GAP_ALERT_HOURS``."""
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    folder = Path(root) / "fpl-data"
    manifests = snapshot_manifests(folder / "snapshots") if folder.exists() else []
    latest = max((pd.Timestamp(m["started_at"]) for m in manifests), default=None)
    exported = sorted(int(p.stem[2:]) for p in (folder / "data").glob("*/gws/gw*.csv") if p.stem[2:].isdigit())
    age = round((now - latest).total_seconds() / 3600, 1) if latest is not None else None
    return {"checkout": folder.exists(), "latest_snapshot_at": latest.isoformat() if latest is not None else None,
            "age_hours": age, "stale": age is None or age > GAP_ALERT_HOURS,
            "exported_rounds": sorted(set(exported)), "alert_hours": GAP_ALERT_HOURS}


ODDS_COLUMN = "market_team_expected_goals"


def capture_quality(snapshot: Path, now=None) -> dict:
    """Sources, odds coverage per forecast GW and market fallback share for one capture."""
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    manifest = json.loads((Path(snapshot) / "manifest.json").read_text())
    sources = {name: {"ok": record.get("status") == 200, "received_at": record.get("received_at")}
               for name, record in manifest.get("files", {}).items() if not name.startswith("player_")}
    result = {"capture": Path(snapshot).name, "forecast_at": manifest.get("forecast_at"),
              "age_hours": round((now - pd.Timestamp(manifest["started_at"])).total_seconds() / 3600, 1),
              "players": [manifest.get("captured_players"), manifest.get("expected_players")],
              "sources": sources, "odds_coverage": {}, "market_fallback_share": None}
    path = Path(snapshot) / "horizon_fixture_forecast.csv"
    if path.exists():
        rows = pd.read_csv(path, usecols=lambda c: c in {"GW", "fixture", "planned_fixture", ODDS_COLUMN})
        rows = rows[rows.planned_fixture.astype(bool)] if "planned_fixture" in rows else rows
        if ODDS_COLUMN in rows:
            per_fixture = rows.groupby(["GW", "fixture"])[ODDS_COLUMN].apply(lambda s: s.notna().any())
            result["odds_coverage"] = {int(gw): round(float(share), 3) for gw, share in per_fixture.groupby(level=0).mean().items()}
            result["market_fallback_share"] = round(float(rows[ODDS_COLUMN].isna().mean()), 3)
    return result


def code_coverage(root: Path, elements: list[dict], history_folders) -> dict:
    """Share of current players found by stable FPL ``code`` in earlier seasons (new signings legitimately miss)."""
    known = set()
    for folder in history_folders:
        path = Path(folder) / "players_raw.csv"
        if path.exists():
            known |= set(pd.read_csv(path, usecols=["code"]).code.dropna().astype(int))
    codes = [int(e["code"]) for e in elements if e.get("code") is not None]
    hits = sum(code in known for code in codes)
    return {"players": len(codes), "with_history": hits, "share": round(hits / len(codes), 3) if codes else None}


def consequences(quality: dict) -> list[str]:
    """Plain-language decision impact of the numbers above."""
    notes = []
    coverage = quality.get("capture", {}).get("odds_coverage", {})
    without = [gw for gw, share in coverage.items() if share < 0.5]
    if without:
        notes.append(f"No odds for GW{min(without)}–{max(without)}: those forecasts use the model without market "
                     "information, so later fixtures can look flatter than they are.")
    if quality.get("fpl_data", {}).get("stale"):
        notes.append("Own data (fpl-data) is stale: challengers and evaluation miss the latest rounds.")
    if quality.get("missed_locks"):
        notes.append(f"Rounds never locked: {', '.join(f'GW{gw}' for gw in quality['missed_locks'])}. "
                     "They cannot count for the model comparison.")
    capture = quality.get("capture", {})
    if capture.get("age_hours") is not None and capture["age_hours"] > 24:
        notes.append("Forecast snapshot is over 24 hours old: refresh before acting on news or prices.")
    if any(not source["ok"] for source in capture.get("sources", {}).values()):
        failed = [name for name, source in capture["sources"].items() if not source["ok"]]
        notes.append(f"Sources missing in the latest snapshot: {', '.join(failed)}.")
    return notes


def report(root: Path, now=None) -> dict:
    """Everything above for the latest capture, plus lock and evaluation status (plan O3)."""
    import prospective_loop
    root = Path(root)
    found = prospective_loop.captures(root)
    snapshot = found[-1][0] if found else None
    events = prospective_loop._gz(snapshot / "bootstrap.json.gz")["events"] if snapshot else []
    elements = prospective_loop._gz(snapshot / "bootstrap.json.gz")["elements"] if snapshot else []
    evaluated = [json.loads(p.read_text()) for p in (root / "artifacts/prospective_eval").glob("*/round.json")]
    history = sorted((root / "data-source/data").glob("20*")) + sorted((root / "fpl-data/data").glob("20*"))
    season = prospective_loop._gz(snapshot / "bootstrap.json.gz")["events"][0]["deadline_time"][:4] if snapshot else None
    history = [folder for folder in history if season is None or not folder.name.startswith(season)]
    quality = {
        "generated_at": pd.Timestamp(now or datetime.now(timezone.utc)).isoformat(),
        "fpl_data": fpl_data_freshness(root, now),
        "capture": capture_quality(snapshot, now) if snapshot else {},
        "code_coverage": code_coverage(root, elements, history),
        "understat": "research only; not used by production forecasts",
        "missed_locks": prospective_loop.status(root, events, now)["missed_locks"] if events else [],
        "last_evaluated_round": max((int(r["GW"]) for r in evaluated if r.get("protocol") == "loop-v1"), default=None),
    }
    quality["consequences"] = consequences(quality)
    return quality


LIMITATIONS = [
    "Forecasts are expected points, not guarantees; one round says little about a model.",
    "Q10–Q90 come from three model quantiles per fixture with assumed tails and independent fixtures.",
    "Odds cover only the next one or two Gameweeks; later fixtures use the model without market data.",
    "Playing-time probabilities are not yet recalibrated (needs six evaluated rounds).",
    "Public team data cannot see unpublished transfers, exact selling prices or chips played this round.",
]


def model_card(root: Path, now=None) -> dict:
    """Plan E4: what the production model is, how it has done in locked rounds, and what it cannot do.

    Reports the leaderboard as it stands; it never claims one model is better
    unless a pre-registered criterion says so.
    """
    import prospective_loop
    root = Path(root)
    board_path = root / "artifacts/prospective_eval/leaderboard.json"
    board = json.loads(board_path.read_text()) if board_path.exists() else {"models": []}
    production = prospective_loop.captures(root)[-1][1] if prospective_loop.captures(root) else {}
    reference = next((m for m in board.get("models", []) if m["model"] == prospective_loop.REFERENCE), {})
    v2 = board.get("criterion_v2", {})
    return {
        "generated_at": board.get("generated_at"),
        "production": {"model_path": production.get("model_path"), "model_family": production.get("model_family"),
                       "caveat": production.get("model_caveat")},
        "rounds": {"shown": reference.get("rounds_shown", 0), "counted_v1": reference.get("rounds_counted", 0),
                   "counted_v2": max((r["rounds"] for r in v2.get("counted", [])), default=0),
                   "needed": prospective_loop.CRITERION["min_rounds"]},
        "leaderboard": [{key: row.get(key) for key in (
            "model", "rounds_shown", "rounds_counted", "team_points_diff_mean", "team_points_diff_ci",
            "weekly_MAE_mean", "weekly_MAE_diff_mean", "brier_60plus_mean", "interval_coverage_mean", "criterion_met")}
            for row in board.get("models", [])],
        "criterion_v2": [{key: row.get(key) for key in ("model", "role", "rounds", "mae_diff_mean", "mae_diff_ci", "criterion_met")}
                         for row in v2.get("counted", [])],
        "calibration": {"brier_60plus": reference.get("brier_60plus_mean"),
                        "interval_coverage": reference.get("interval_coverage_mean"), "interval_nominal": 0.8,
                        "minutes_recalibration": board.get("minutes_calibration")},
        "claim": "No model is declared better until a pre-registered criterion is met.",
        "limitations": LIMITATIONS,
        "data_quality": report(root, now),
    }
