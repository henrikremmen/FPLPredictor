from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nextgen_models import (
    _ndcg,
    decision_metrics,
    promotion_decision,
    training_seasons,
)


class NextGenModelTests(unittest.TestCase):
    def test_training_window_is_chronological(self):
        self.assertEqual(training_seasons("2020-21", "2023-24"),
                         ["2020-21", "2021-22", "2022-23"])
        self.assertEqual(training_seasons("2022-23", "2024-25"),
                         ["2022-23", "2023-24"])

    def test_ndcg_rewards_correct_ranking(self):
        actual = np.array([10.0, 5.0, 0.0])
        self.assertAlmostEqual(_ndcg(actual, actual, 3), 1.0)
        self.assertLess(_ndcg(actual, actual[::-1], 3), 1.0)

    def test_decision_metrics_aggregate_double_gameweek(self):
        rows = pd.DataFrame({
            "season": ["s"] * 4,
            "GW": [1] * 4,
            "player_id": [1, 1, 2, 3],
            "target_points": [3.0, 4.0, 6.0, 20.0],
            "minutes_avg5": [90.0, 90.0, 90.0, 0.0],
        })
        result = decision_metrics(rows, np.array([2.0, 3.0, 4.0, 100.0]))
        self.assertEqual(result["captain_actual_mean"], 7.0)
        self.assertEqual(result["decision_gameweeks"], 1)

    def test_promotion_requires_every_gate(self):
        columns = ["RMSE", "candidate_RMSE", "top25_actual_mean"]
        validation = pd.DataFrame([[2.0, 3.0, 4.0], [1.9, 2.9, 4.1]],
                                  index=["incumbent_blend", "new"], columns=columns)
        test = pd.DataFrame([[2.1, 3.1, 4.0], [2.0, 3.0, 4.2]],
                            index=["incumbent_blend", "new"], columns=columns)
        promoted, checks = promotion_decision(validation, test, "new")
        self.assertTrue(promoted)
        self.assertTrue(all(checks.values()))
        test.loc["new", "top25_actual_mean"] = 3.9
        self.assertFalse(promotion_decision(validation, test, "new")[0])

    def test_probability_gate_can_reject_candidate(self):
        columns = ["RMSE", "candidate_RMSE", "top25_actual_mean", "minutes_log_loss"]
        validation = pd.DataFrame(
            [[2.0, 3.0, 4.0, np.nan], [1.95, 2.95, 4.05, .45], [1.9, 2.9, 4.1, .50]],
            index=["incumbent_blend", "long_history_mixture", "new"], columns=columns)
        test = validation.copy()
        promoted, checks = promotion_decision(validation, test, "new")
        self.assertFalse(promoted)
        self.assertFalse(checks["validation_minutes_log_loss"])


if __name__ == "__main__":
    unittest.main()
