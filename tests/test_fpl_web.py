from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl_app import ImportedTeam
from fpl_web import DEFAULT_TEAM, player_table, transfer_table


def player(player_id: int, name: str, position: str, points: float) -> dict:
    return {
        "id": player_id, "name": name, "position": position,
        "team": "AAA", "opponent": "BBB (H)", "selling_price": 55,
        "price": 56, "recommended_points": points,
        "decision_points": points - .2, "expected_60plus_appearances": .75,
        "point_range_q10_q90": "0.0–8.0", "status": "a",
    }


class FPLWebTests(unittest.TestCase):
    def setUp(self):
        self.squad = pd.DataFrame([
            player(1, "Keeper", "GK", 4.0),
            player(2, "Defender", "DEF", 5.0),
        ])
        self.team = ImportedTeam(
            entry_id=1, event=4, target_event=5, manager_name="Manager",
            team_name="Team", bank=10, free_transfers=2,
            squad=self.squad, market=self.squad, deadline="2026-09-19T10:00:00Z",
            forecast_path=Path("forecast.csv"), horizon=1,
            risk_profile="stable",
        )

    def test_player_table_formats_model_data_without_mutating_source(self):
        shown = player_table(self.squad, self.team, "selling_price")
        self.assertEqual(shown.iloc[0]["Spiller"], "Keeper")
        self.assertEqual(shown.iloc[0]["Pris (£m)"], 5.5)
        self.assertEqual(shown.iloc[0]["P(60+)"], 75.0)
        self.assertIn("Profilscore", shown)
        self.assertNotIn("_position_order", self.squad)

    def test_transfer_table_marks_exact_plan(self):
        raw = pd.DataFrame([{
            "out": "Old", "in": "New", "cost": 6.2, "money_left": .3,
            "lineup_gain": 2.5, "expected_gain": 2.7, "hit": 0,
            "net_gain": 2.5, "is_global_optimum": True,
        }])
        shown = transfer_table(raw, self.team)
        self.assertEqual(shown.iloc[0]["Globalt optimum"], "Ja")
        self.assertEqual(shown.iloc[0]["Profilgevinst"], 2.5)

    def test_streamlit_empty_state_smoke(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(ROOT / "src" / "fpl_web.py"))
        app.run(timeout=15)
        self.assertFalse(app.exception)
        self.assertEqual(app.sidebar.text_input[0].value, DEFAULT_TEAM)
        self.assertGreaterEqual(len(app.sidebar.button), 2)


if __name__ == "__main__":
    unittest.main()
