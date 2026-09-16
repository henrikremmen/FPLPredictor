from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chip_strategy import recommend_chip_strategy
from fpl_app import ImportedTeam


def player(player_id, name, position, team, points, price=50):
    return {
        "id": player_id, "name": name, "position": position,
        "team_id": team, "team": f"T{team}", "price": price,
        "selling_price": price, "purchase_price": price,
        "recommended_points": float(points), "decision_points": float(points),
        "planned_fixtures": 1, "opponent": "T20 (H)", "status": "a",
    }


class ChipStrategyTests(unittest.TestCase):
    def setUp(self):
        specs = [
            (1, "GK1", "GK", 1, 4), (2, "GK2", "GK", 2, 2),
            (3, "D1", "DEF", 3, 6), (4, "D2", "DEF", 4, 5),
            (5, "D3", "DEF", 5, 4), (6, "D4", "DEF", 6, 1),
            (7, "D5", "DEF", 7, 0),
            (8, "M1", "MID", 8, 10), (9, "M2", "MID", 9, 9),
            (10, "M3", "MID", 10, 8), (11, "M4", "MID", 11, 7),
            (12, "M5", "MID", 12, 3),
            (13, "F1", "FWD", 13, 8), (14, "F2", "FWD", 14, 7),
            (15, "F3", "FWD", 15, 2),
        ]
        self.squad = pd.DataFrame(player(*spec) for spec in specs)
        additions = pd.DataFrame([
            player(16, "M6", "MID", 16, 12, 50),
            player(17, "D6", "DEF", 17, 9, 50),
            player(18, "F4", "FWD", 18, 10, 50),
        ])
        market = pd.concat([self.squad, additions], ignore_index=True)
        weekly = []
        for event, multiplier in [(5, 1.0), (6, .9)]:
            frame = market.copy()
            frame["recommended_points"] *= multiplier
            frame["decision_points"] = frame["recommended_points"]
            frame["forecast_event"] = event
            if event == 6:
                frame.loc[frame["id"].eq(8), "planned_fixtures"] = 2
            weekly.append(frame)
        statuses = {
            chip: {"available": True, "used_event": None, "half": 1,
                   "expires_after_gw": 19, "blocked_consecutive": False}
            for chip in ["wildcard", "free_hit", "triple_captain", "bench_boost"]
        }
        self.team = ImportedTeam(
            1, 4, 5, "Manager", "Team", 0, 2, self.squad, market,
            "deadline", Path("forecast.csv"), horizon=2,
            weekly_market=pd.concat(weekly, ignore_index=True),
            risk_profile="balanced", chip_status=statuses,
        )

    def test_strategy_values_all_chips_and_sequence(self):
        result = recommend_chip_strategy(self.team)
        labels = {row["chip"] for row in result["best_by_chip"]}
        self.assertEqual(labels, {
            "triple_captain", "bench_boost", "free_hit", "wildcard",
            "wildcard_bench_boost",
        })
        triple = next(row for row in result["candidates"]
                      if row["chip"] == "triple_captain" and row["event"] == 5)
        self.assertEqual(triple["gain"], 10.0)
        self.assertIn(result["recommendation"], [
            "Triple Captain i GW5", "Triple Captain i GW6",
            "Wildcard i GW5", "Wildcard → Bench Boost i GW5",
            "Spar chips foreløpig",
        ])
        self.assertTrue(result["horizon_limited"])

    def test_used_chip_is_never_recommended_to_play(self):
        self.team.chip_status["triple_captain"]["available"] = False
        result = recommend_chip_strategy(self.team)
        triple = next(row for row in result["best_by_chip"]
                      if row["chip"] == "triple_captain")
        self.assertEqual(triple["decision"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
