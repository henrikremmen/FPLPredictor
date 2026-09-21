import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from historical_market import (
    MARKET_FEATURES,
    attach_historical_market,
    normalize_historical_odds,
)
from market_models import MarketFallbackBlend
from historical_workload import attach_cl_workload


class HistoricalMarketTests(unittest.TestCase):
    def test_preclosing_odds_are_devigged_and_joined_from_team_perspective(self):
        raw = pd.DataFrame([{
            "Date": "01/09/2024", "HomeTeam": "Arsenal", "AwayTeam": "Aston Villa",
            "AvgH": 1.5, "AvgD": 4.5, "AvgA": 7.0,
            "Avg>2.5": 1.8, "Avg<2.5": 2.1,
            # Closing prices must not be consumed.
            "AvgCH": 9.0, "AvgCD": 9.0, "AvgCA": 1.1,
        }])
        players = pd.DataFrame([
            {"season": "2024-25", "fixture": 1, "player_id": 10,
             "team": "Arsenal", "opp_team_name": "Aston Villa", "was_home": 1.0,
             "kickoff_time": "2024-09-01T15:00:00Z"},
            {"season": "2024-25", "fixture": 1, "player_id": 20,
             "team": "Aston Villa", "opp_team_name": "Arsenal", "was_home": 0.0,
             "kickoff_time": "2024-09-01T15:00:00Z"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "odds.csv"
            raw.to_csv(path, index=False)
            odds = normalize_historical_odds({"2024-25": path})
            result = attach_historical_market(players, odds).set_index("player_id")
        probabilities = odds.iloc[0][[
            "market_home_win_probability", "market_draw_probability",
            "market_away_win_probability",
        ]].sum()
        self.assertAlmostEqual(float(probabilities), 1.0)
        self.assertGreater(result.loc[10, "market_team_win_probability"], .5)
        self.assertLess(result.loc[20, "market_team_win_probability"], .2)
        self.assertGreater(result.loc[10, "market_clean_sheet_probability"], 0)
        self.assertFalse(result[MARKET_FEATURES].isna().any().any())

    def test_blend_falls_back_to_baseline_when_market_is_missing(self):
        class Model:
            def __init__(self, values):
                self.values = np.asarray(values, dtype=float)

            def predict(self, data):
                return self.values

        data = pd.DataFrame({
            "market_team_expected_goals": [1.5, np.nan],
            "market_opponent_expected_goals": [1.0, np.nan],
            "market_clean_sheet_probability": [.37, np.nan],
            # Minimal columns required by improved_models.enrich.
            "minutes_avg3": [80, 80], "minutes_avg10": [70, 70],
            "points_avg3": [5, 5], "points_avg10": [4, 4],
            "games_available_last5": [5, 5], "xG_last5": [1, 1],
            "xA_last5": [1, 1], "games_60plus_last3": [3, 3],
            "team_goals_for_per_game_before": [2, 2],
            "opp_goals_against_per_game_before": [1, 1],
            "team_goals_against_per_game_before": [1, 1],
            "opp_goals_for_per_game_before": [1, 1],
        })
        model = MarketFallbackBlend(Model([2, 4]), Model([6, 8]), .5)
        np.testing.assert_allclose(model.predict(data), [4, 4])

    def test_historical_cl_workload_uses_only_matches_before_kickoff(self):
        players = pd.DataFrame([{
            "season": "2024-25", "team": "Arsenal",
            "kickoff_time": "2024-09-20T15:00:00Z",
        }])
        events = pd.DataFrame([
            {"season": "2024-25", "team_key": "arsenal", "cl_match_id": 1,
             "cl_kickoff": pd.Timestamp("2024-09-18T19:00:00Z")},
            {"season": "2024-25", "team_key": "arsenal", "cl_match_id": 2,
             "cl_kickoff": pd.Timestamp("2024-09-24T19:00:00Z")},
        ])
        result = attach_cl_workload(players, events).iloc[0]
        self.assertEqual(result.cl_matches_last7, 1)
        self.assertEqual(result.cl_matches_last14, 1)
        self.assertAlmostEqual(result.days_since_cl_match, 44 / 24)


if __name__ == "__main__":
    unittest.main()
