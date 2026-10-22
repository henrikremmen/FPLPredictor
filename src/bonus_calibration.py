"""Bonus calibration under the 2026/27 BPS rules (plan M3).

BPS changed in 2026/27 (CBI earns 1 BPS per three, not per two; no -1 for being
tackled; saves outside the box removed; big-chance saves added). This measures,
per position, how bonus has moved and whether the component model's expected
bonus still matches outcomes:

* model-free: bonus per 90 played minutes and each position's share of bonus,
  by season;
* calibration: component model v2 trained to 2025-26, tested on 2026-27 GW1-7,
  next to a control trained to 2024-25 and tested on 2025-26 GW1-7 (old rules).

Diagnostic only; nothing is promoted.

    python src/bonus_calibration.py --features data/processed/features_20261022
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from challengers import CURRENT_SEASON, current_season_odds
from component_benchmark import COMPONENT_COLUMNS
from component_models import RICH_FEATURES, CoherentComponentPointsModel
from improved_models import enrich
from market_models import KEYS, load_market_data
from nextgen_models import SEASON_ORDER

ROOT = Path(__file__).resolve().parents[1]
POSITIONS = ["GK", "DEF", "MID", "FWD"]


def bonus_by_position(frame: pd.DataFrame) -> pd.DataFrame:
    """Per season and position: bonus per 90 played minutes and share of all bonus."""
    played = frame[frame.minutes.gt(0)]
    table = played.groupby(["season", "position"]).agg(bonus=("bonus", "sum"), minutes=("minutes", "sum"))
    table["bonus_per90"] = table.bonus / table.minutes * 90
    table["bonus_share"] = table.bonus / table.groupby(level="season").bonus.transform("sum")
    return table.reset_index()


def calibration_by_position(frame: pd.DataFrame) -> pd.DataFrame:
    """Expected vs actual bonus per position; ratio > 1 means the model under-predicts."""
    table = frame.groupby("position").agg(rows=("bonus", "size"), expected=("expected_bonus", "sum"),
                                          actual=("bonus", "sum"))
    table["actual_over_expected"] = table.actual / table.expected
    return table.reindex(POSITIONS).reset_index()


def load(root: Path, features_dir: Path) -> pd.DataFrame:
    data = load_market_data(root, features_dir, seasons=[*SEASON_ORDER, CURRENT_SEASON],
                            extra_odds={CURRENT_SEASON: current_season_odds(root)})
    extra = pd.read_csv(Path(features_dir) / "player_fixture_features.csv", low_memory=False,
                        usecols=lambda c: c in set(COMPONENT_COLUMNS) | set(RICH_FEATURES))
    additions = [c for c in extra if c in KEYS or c not in data]
    return enrich(data.merge(extra[additions], on=KEYS, how="left", validate="one_to_one"))


def run(root: Path, features_dir: Path) -> Path:
    data = load(root, features_dir)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "production_eligible": False,
              "status": "diagnostic", "by_season": bonus_by_position(data[data.season.ge("2023-24")]).to_dict("records")}
    early = data.GW.le(7)
    with threadpool_limits(limits=4):
        for label, test_season, last_train in [("control_2025-26", "2025-26", "2024-25"),
                                               ("rules_2026-27", CURRENT_SEASON, "2025-26")]:
            train = data[data.season.between("2022-23", last_train)]
            test = data[data.season.eq(test_season) & early].copy()
            model = CoherentComponentPointsModel().fit(train)
            test["expected_bonus"] = model.point_contributions(test)["bonus"].to_numpy()
            report[label] = calibration_by_position(test).to_dict("records")
            print(label, json.dumps(report[label]), flush=True)
    destination = root / "artifacts/model_research" / f"bps_calibration_{datetime.now(timezone.utc):%Y%m%d}"
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "report.json").write_text(json.dumps(report, indent=2, default=float))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--features", type=Path, required=True)
    print(run(ROOT, parser.parse_args().features))
