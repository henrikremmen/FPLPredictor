from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpl_app import optimal_lineup
from season_simulator import (
    autosub_score,
    best_transfer_plan,
    historical_transfer_cap,
    next_free_transfer_balance,
)


def row(player_id, position, prediction, points, minutes):
    return {
        "id": player_id, "name": f"P{player_id}", "position": position,
        "recommended_points": prediction, "decision_points": prediction,
        "actual_points": points, "minutes": minutes,
    }


class SeasonSimulatorTests(unittest.TestCase):
    def test_joint_optimizer_finds_funding_transfer_pair(self):
        positions = (["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3)
        market_rows = [{
            "player_id": player_id,
            "name": f"P{player_id}",
            "team": f"T{player_id}",
            "position": position,
            "value": 50,
            "prediction": 5.0,
        } for player_id, position in enumerate(positions, 1)]
        market_rows.extend([
            {"player_id": 16, "name": "Premium", "team": "T16",
             "position": "MID", "value": 60, "prediction": 20.0},
            {"player_id": 17, "name": "Enabler", "team": "T17",
             "position": "MID", "value": 40, "prediction": 0.0},
        ])
        market = pd.DataFrame(market_rows)
        holdings = {
            row["player_id"]: {
                "purchase_price": 50, "position": row["position"],
                "team": row["team"], "name": row["name"],
            }
            for row in market_rows[:15]
        }
        self.assertIsNone(best_transfer_plan(market, holdings, 0, 1, 0.0))
        plan = best_transfer_plan(market, holdings, 0, 2, 0.0)
        self.assertIsNotNone(plan)
        self.assertEqual({move["in_id"] for move in plan["moves"]}, {16, 17})
        self.assertEqual(plan["new_bank"], 0)
        self.assertGreater(plan["gain"], 0)

    def test_optimizer_does_not_force_sale_after_price_rises(self):
        positions = (["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3)
        rows = [{
            "player_id": player_id, "name": f"P{player_id}",
            "team": f"T{player_id}", "position": position,
            "value": 70, "prediction": 5.0,
        } for player_id, position in enumerate(positions, 1)]
        holdings = {
            row["player_id"]: {
                "purchase_price": 50, "position": row["position"],
                "team": row["team"], "name": row["name"],
            }
            for row in rows
        }
        self.assertIsNone(
            best_transfer_plan(pd.DataFrame(rows), holdings, 0, 1, 0.0)
        )

    def test_historical_free_transfer_rules(self):
        self.assertEqual(historical_transfer_cap("2023-24"), 2)
        self.assertEqual(historical_transfer_cap("2024-25"), 5)
        self.assertEqual(next_free_transfer_balance("2023-24", 10, 1, 2), 2)
        self.assertEqual(next_free_transfer_balance("2023-24", 10, 2, 2), 2)
        self.assertEqual(next_free_transfer_balance("2025-26", 15, 0, 5), 5)
        self.assertEqual(next_free_transfer_balance("2025-26", 15, 0, 1), 1)

    def test_captain_fallback_and_legal_autosub(self):
        players = [
            row(1, "GK", 5, 0, 0), row(2, "GK", 1, 4, 90),
            row(3, "DEF", 9, 0, 0), row(4, "DEF", 8, 2, 90),
            row(5, "DEF", 7, 3, 90), row(6, "DEF", 2, 6, 90),
            row(7, "DEF", 1, 1, 90),
            row(8, "MID", 12, 0, 0), row(9, "MID", 11, 8, 90),
            row(10, "MID", 10, 7, 90), row(11, "MID", 6, 5, 90),
            row(12, "MID", 1, 1, 90),
            row(13, "FWD", 10, 9, 90), row(14, "FWD", 5, 4, 90),
            row(15, "FWD", 1, 2, 90),
        ]
        lineup = optimal_lineup(pd.DataFrame(players))
        score, doubled = autosub_score(lineup)
        # Captain P8 did not play, so vice P9 is doubled; reserve GK and the
        # highest-priority legal outfield substitute enter the XI.
        self.assertEqual(doubled, "P9")
        self.assertGreater(score, lineup["starters"]["actual_points"].sum())


if __name__ == "__main__":
    unittest.main()
