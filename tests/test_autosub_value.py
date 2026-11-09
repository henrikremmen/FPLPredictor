from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autosub_value import lineup_value
from fpl_app import optimal_lineup


def squad(appearances):
    positions = ["GK", "GK"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    points = [5, 1] + [4, 4, 4, 4, 1] + [6, 5, 5, 5, 1] + [8, 7, 1]
    return pd.DataFrame({"id": range(1, 16), "name": [f"P{i}" for i in range(1, 16)], "position": positions,
                         "recommended_points": [float(p) for p in points], "expected_appearances": appearances,
                         "availability": 1.0, "planned_fixtures": 1})


class AutosubValueTest(unittest.TestCase):
    """P3: bench and vice-captain value from the backtests' autosub rules."""

    def test_everyone_plays_means_no_bench_value(self):
        value = lineup_value(optimal_lineup(squad([1.0] * 15)), draws=50)
        self.assertEqual(value["xi_expected"], value["expected_with_autosubs"])
        self.assertEqual(value["bench_and_vice_value"], 0)

    def test_absent_captain_hands_the_armband_to_the_vice(self):
        appearances = [1.0] * 15
        appearances[12] = 0.0  # P13, the 8-point forward the forecast makes captain, will not play
        lineup = optimal_lineup(squad(appearances))
        self.assertEqual(lineup["starters"].query("role == 'C'").id.iloc[0], 13)
        value = lineup_value(lineup, draws=20)
        # The XI forecast counts his 8 twice; under the rules the vice (7) doubles and a 1-point bench player comes in.
        self.assertEqual(value["bench_and_vice_value"], -16 + 7 + 1)


if __name__ == "__main__":
    unittest.main()
