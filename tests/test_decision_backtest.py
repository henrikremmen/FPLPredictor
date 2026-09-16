from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_backtest import optimize_squad


class DecisionBacktestTests(unittest.TestCase):
    def test_optimizer_enforces_full_fpl_squad_and_lineup(self):
        positions = ["GK"] * 3 + ["DEF"] * 7 + ["MID"] * 7 + ["FWD"] * 5
        rows = []
        for player_id, position in enumerate(positions, 1):
            rows.append({
                "player_id": player_id, "name": f"P{player_id}",
                "team": f"T{1 + (player_id - 1) % 8}", "position": position,
                "value": 50, "prediction": float(30 - player_id),
                "actual_points": float(player_id % 10),
            })
        result = optimize_squad(pd.DataFrame(rows))
        squad, starters, captain = result["squad"], result["starters"], result["captain"]
        self.assertEqual(len(squad), 15)
        self.assertEqual(squad["position"].value_counts().to_dict(),
                         {"MID": 5, "DEF": 5, "FWD": 3, "GK": 2})
        self.assertLessEqual(squad.groupby("team").size().max(), 3)
        self.assertLessEqual(squad["value"].sum(), 1000)
        self.assertEqual(len(starters), 11)
        counts = starters["position"].value_counts()
        self.assertEqual(counts["GK"], 1)
        self.assertTrue(3 <= counts["DEF"] <= 5)
        self.assertTrue(2 <= counts["MID"] <= 5)
        self.assertTrue(1 <= counts["FWD"] <= 3)
        self.assertIn(int(captain["player_id"]), starters["player_id"].tolist())


if __name__ == "__main__":
    unittest.main()
