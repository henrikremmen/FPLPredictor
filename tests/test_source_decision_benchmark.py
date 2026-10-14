import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from source_decision_benchmark import validate_comparison


class ComparisonTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame(dict(model=["a", "b"], season=["2025-26"] * 2,
            GW=[6] * 2, player_id=[7] * 2, actual_points=[3] * 2,
            position=["MID"] * 2, team=["Arsenal"] * 2, value=[70] * 2))

    def test_equal_cohort_passes(self):
        validate_comparison(self.frame(), ["a", "b"])

    def test_different_outcomes_or_market_fail(self):
        for column, value in [("player_id", 8), ("actual_points", 4), ("value", 75)]:
            frame = self.frame()
            frame.loc[1, column] = value
            with self.assertRaises(ValueError):
                validate_comparison(frame, ["a", "b"])

    def test_missing_model_fails(self):
        with self.assertRaises(ValueError):
            validate_comparison(self.frame(), ["a", "c"])
