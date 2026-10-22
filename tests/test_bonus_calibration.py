from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bonus_calibration import bonus_by_position, calibration_by_position


class BonusCalibrationTest(unittest.TestCase):
    def test_rates_shares_and_ratios(self):
        frame = pd.DataFrame({"season": ["a"] * 4, "position": ["DEF", "DEF", "MID", "GK"],
                              "minutes": [90, 0, 90, 90], "bonus": [3, 0, 1, 0],
                              "expected_bonus": [1.5, 0.0, 2.0, 0.5]})
        table = bonus_by_position(frame).set_index("position")
        self.assertEqual(table.loc["DEF", "bonus_per90"], 3.0)  # benched row excluded
        self.assertAlmostEqual(table.bonus_share.sum(), 1.0)
        ratios = calibration_by_position(frame).set_index("position").actual_over_expected
        self.assertEqual((ratios["DEF"], ratios["MID"], ratios["GK"]), (2.0, 0.5, 0.0))
        self.assertTrue(pd.isna(ratios["FWD"]))  # absent position stays unknown


if __name__ == "__main__":
    unittest.main()
