import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from elo_features import attach_elo, ELO_FEATURES


class EloTests(unittest.TestCase):
    def setUp(self):
        self.results = pd.DataFrame([dict(match_id="1", available_at="2024-01-02Z".replace("Z", "T00:00Z"),
            home="Arsenal", away="Chelsea", home_goals=2, away_goals=0)])
        self.rows = pd.DataFrame(dict(prediction_cutoff=["2024-01-02T00:00Z", "2024-01-03T00:00Z"],
            team=["Arsenal"] * 2, opp_team_name=["Chelsea"] * 2, was_home=[True] * 2))

    def test_strict_cutoff_and_no_future_result_leak(self):
        original = attach_elo(self.rows, self.results)
        changed = self.results.assign(home_goals=0, away_goals=3)
        modified = attach_elo(self.rows, changed)
        pd.testing.assert_series_equal(original.iloc[0][ELO_FEATURES], modified.iloc[0][ELO_FEATURES])
        self.assertEqual(original.elo_team_games.iloc[0], 0)
        self.assertGreater(original.elo_team.iloc[1], 1500)
        self.assertLess(modified.elo_team.iloc[1], 1500)
        self.assertAlmostEqual(original.elo_team.iloc[1] + original.elo_opponent.iloc[1], 3000)

    def test_query_order_does_not_change_values(self):
        forward = attach_elo(self.rows, self.results)
        backward = attach_elo(self.rows.iloc[::-1], self.results).sort_index()
        pd.testing.assert_frame_equal(forward, backward)

    def test_duplicate_results_fail(self):
        with self.assertRaises(ValueError):
            attach_elo(self.rows, pd.concat([self.results, self.results]))
