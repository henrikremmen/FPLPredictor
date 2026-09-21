from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpl_app import ImportedTeam
from multiweek_planner import plan_multiweek


def _team() -> ImportedTeam:
    positions = ["GK", "GK", *("DEF" for _ in range(5)),
                 *("MID" for _ in range(5)), *("FWD" for _ in range(3))]
    rows = []
    for index, position in enumerate(positions, start=1):
        rows.append({
            "id": index,
            "name": f"Player {index}",
            "position": position,
            "team_id": (index - 1) // 3 + 1,
            "team": f"T{(index - 1) // 3 + 1}",
            "price": 50,
            "recommended_points": 4.0,
            "decision_points": 4.0,
        })
    # A legal, same-price midfielder from a sixth club is substantially better.
    rows.append({
        "id": 16, "name": "Upgrade", "position": "MID", "team_id": 6,
        "team": "T6", "price": 50, "recommended_points": 10.0,
        "decision_points": 10.0,
    })
    market = pd.DataFrame(rows)
    squad = market.iloc[:15].copy()
    squad["selling_price"] = 50
    weekly = []
    for event in range(5, 9):
        frame = market.copy()
        frame["forecast_event"] = event
        weekly.append(frame)
    return ImportedTeam(
        entry_id=1, event=4, target_event=5, manager_name="Manager",
        team_name="Test", bank=0, free_transfers=1, squad=squad,
        market=market, deadline="", forecast_path=Path("forecast.csv"),
        horizon=4, weekly_market=pd.concat(weekly, ignore_index=True),
    )


class MultiweekPlannerTests(unittest.TestCase):
    def test_finds_upgrade_and_rolls_free_transfers(self):
        result = plan_multiweek(_team(), weeks=4)

        self.assertEqual(len(result["weeks"]), 4)
        self.assertEqual(result["weeks"][0]["transfers_in"], ["Upgrade"])
        self.assertEqual(len(result["weeks"][0]["transfers_out"]), 1)
        self.assertEqual(result["weeks"][0]["paid_transfers"], 0)
        self.assertTrue(all(week["paid_transfers"] == 0 for week in result["weeks"]))
        self.assertTrue(result["global_optimum"])

    def test_can_forbid_points_hits_for_conservative_comparison(self):
        team = _team()
        team.free_transfers = 0
        result = plan_multiweek(team, weeks=1, allow_hits=False)
        self.assertFalse(result["allow_hits"])
        self.assertEqual(result["weeks"][0]["paid_transfers"], 0)
        self.assertEqual(result["weeks"][0]["transfers_in"], [])


if __name__ == "__main__":
    unittest.main()
