"""U19: decision journal. Freeze the advice, its alternatives, your choice and the source
times before the deadline; show what happened once the round is scored.

Entries live next to the shadow season (E2) in
``artifacts/shadow_season/<season>_<team>/journal_gw<N>_<stamp>.json`` and are
never overwritten. A later entry for the same round before its deadline
replaces the earlier one as "your decision"; both stay on file. After FPL
checks the round (fpl-data export), the advised XI and the hold XI are scored
with actual points (captain doubled; no autosubs, so both get the same rule).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from fpl_app import AppError, ImportedTeam, optimal_lineup
from fpl_rules import CAPTAIN_MULTIPLIER
from shadow_season import _write_new, folder

CHOICES = {"follow": "Follow the advice", "roll": "Roll / no transfer", "other": "Something else"}


def season_of(team: ImportedTeam) -> str:
    return str(pd.read_csv(team.forecast_path, nrows=1).season.iloc[0])


def record(root: Path, team: ImportedTeam, strategy: dict, alternatives: list[dict], choice: str,
           note: str = "", now=None) -> Path:
    """Freeze one decision for the team's next round; refused after the deadline."""
    if choice not in CHOICES:
        raise AppError(f"Choice must be one of: {', '.join(CHOICES)}.")
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if not team.deadline or now >= pd.Timestamp(team.deadline):
        raise AppError("The deadline has passed; a journal entry must be made before it.")
    ids = team.market.set_index("name").id.to_dict()
    first = (strategy.get("plan") or {}).get("weeks", [{}])[0]
    hold = optimal_lineup(team.lineup_squad if team.lineup_squad is not None else team.squad)
    entry = {
        "event": team.target_event, "recorded_at": now.isoformat(), "deadline": team.deadline,
        "forecast_at": strategy.get("context", {}).get("forecast_at") or (team.forecast_path.parent.name),
        "player_data_at": team.player_data_at,
        "advice": {"decision": strategy["transfer"]["decision"], "title": strategy["transfer"]["title"],
                   "reason": strategy["transfer"]["reason"], "out": strategy["transfer"]["transfers_out"],
                   "in": strategy["transfer"]["transfers_in"], "captain": strategy["captain"]["captain"]["name"],
                   "starter_ids": first.get("starter_ids", []), "captain_id": ids.get(first.get("captain"))},
        "hold": {"starter_ids": hold["starters"].id.astype(int).tolist(),
                 "captain_id": int(hold["starters"].query("role == 'C'").id.iloc[0])},
        "alternatives": [{key: plan.get(key) for key in ("name", "first_week_out", "first_week_in", "net_points",
                                                         "gain_vs_hold")} for plan in alternatives],
        "choice": {"kind": choice, "label": CHOICES[choice], "note": note[:500]},
    }
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    return _write_new(folder(root, season_of(team), team.entry_id) / f"journal_gw{team.target_event}_{stamp}.json", entry)


def _actual(points: pd.Series, starters: list[int], captain: int | None) -> float | None:
    if not starters:
        return None
    total = float(points.reindex(starters).fillna(0).sum())
    return total + (CAPTAIN_MULTIPLIER - 1) * float(points.get(captain, 0) or 0) if captain else total


def entries(root: Path, season: str, team_id: int) -> list[dict]:
    """All entries, newest first; the last one before each deadline is the decision that counts."""
    base = folder(root, season, team_id)
    found = [json.loads(p.read_text()) | {"file": p.name} for p in sorted(base.glob("journal_gw*.json"))]
    latest = {}
    for entry in found:
        latest[entry["event"]] = entry["file"]
    for entry in found:
        entry["counts"] = latest[entry["event"]] == entry["file"]
        path = Path(root) / "fpl-data/data" / season / "gws" / f"gw{entry['event']}.csv"
        if path.exists():
            points = pd.read_csv(path).groupby("element").total_points.sum()
            advised = _actual(points, entry["advice"]["starter_ids"], entry["advice"]["captain_id"])
            held = _actual(points, entry["hold"]["starter_ids"], entry["hold"]["captain_id"])
            entry["outcome"] = {"advised_xi_points": advised, "hold_xi_points": held,
                                "note": "Actual points of each XI with the captain doubled, before autosubs."}
    return sorted(found, key=lambda e: e["recorded_at"], reverse=True)
