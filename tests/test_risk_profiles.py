from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risk_profiles import profile_predictions


class RiskProfileTests(unittest.TestCase):
    def test_profile_formulas_preserve_expected_prediction_source(self):
        keys = {"season": ["s"], "GW": [1], "fixture": [2], "player_id": [3]}
        oof = pd.DataFrame({
            **keys, "model": ["incumbent_blend"], "prediction": [4.0],
            "position": ["MID"], "minutes_avg5": [90.0], "target_points": [2.0],
            "p_zero_minutes": [float("nan")], "p_1_59_minutes": [float("nan")],
            "p_60plus_minutes": [float("nan")],
        })
        quantiles = pd.DataFrame({**keys, "q10": [1.0], "q90": [9.0]})
        result = profile_predictions(oof, quantiles).set_index("model")
        self.assertAlmostEqual(result.loc["balanced", "prediction"], 4.0)
        self.assertAlmostEqual(result.loc["stable", "prediction"], 3.2)
        self.assertAlmostEqual(result.loc["upside", "prediction"], 5.5)


if __name__ == "__main__":
    unittest.main()
