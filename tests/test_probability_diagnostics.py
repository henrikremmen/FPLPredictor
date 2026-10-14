from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from probability_diagnostics import calibration_bins


class CalibrationTests(unittest.TestCase):
    def test_boundaries_and_empty_bins(self):
        bins = calibration_bins([0, .2, .8, 1], [0, 1, 0, 1])
        self.assertEqual([b['rows'] for b in bins], [1, 1, 0, 0, 2])
        self.assertEqual(bins[4]['mean_probability'], .9)
        self.assertEqual(bins[4]['observed_rate'], .5)
        self.assertNotIn('observed_rate', bins[2])

    def test_invalid_inputs_fail(self):
        for p, y in [([1.1], [1]), ([float('nan')], [0]), ([.5], [2]), ([.5], [])]:
            with self.assertRaises(ValueError):
                calibration_bins(p, y)
