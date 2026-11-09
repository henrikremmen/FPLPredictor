"""E3 extended metrics, M10 availability bias and E3 forecast timing."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from availability_bias import summarize as bias_summary
from forecast_timing import bucket, summarize as timing_summary
from prospective_evaluation import extended_metrics


class ExtendedMetricsTest(unittest.TestCase):
    def test_interval_coverage_width_and_bias_strata(self):
        scored = pd.DataFrame({"model": ["m"] * 4, "player_id": [1, 2, 3, 4], "prediction": [2.0, 2.0, 4.0, 4.0],
                               "target_points": [1, 9, 4, -1], "prediction_q10": [0.0] * 4, "prediction_q90": [6.0] * 4})
        strata = pd.DataFrame({"player_id": [1, 2, 3, 4], "position": ["DEF", "DEF", "MID", "MID"],
                               "dc_band": ["<5", "11+", "<5", "<5"]})
        report = extended_metrics(scored, strata)[0]
        self.assertEqual(report["interval_q10_q90"], {"coverage": 0.5, "nominal": 0.8, "below": 0.25, "above": 0.25,
                                                      "mean_width": 6.0})
        self.assertEqual(report["bias_by_position"]["DEF"]["bias"], -3.0)  # (1 + -7) / 2: too low
        self.assertEqual(report["bias_by_position"]["MID"]["rows"], 2)
        self.assertEqual(report["bias_by_dc_band"]["11+"]["se"], None)


class AvailabilityBiasTest(unittest.TestCase):
    def test_flagged_bias_with_and_without_the_app_factor(self):
        rows = pd.DataFrame({"GW": [6, 6, 6], "player_id": [1, 2, 3], "availability": [1.0, 0.5, 0.0],
                             "prediction": [3.0, 2.0, 1.0], "actual": [4.0, 1.0, 0.0]})
        rows["adjusted"] = rows.prediction * rows.availability
        report = bias_summary(rows)
        self.assertEqual(report["flagged"]["n"], 2)
        self.assertEqual(report["flagged"]["bias_model_only"], -1.0)       # ((1-2) + (0-1)) / 2
        self.assertEqual(report["flagged"]["bias_with_app_factor"], 0.0)   # ((1-1) + (0-0)) / 2
        self.assertEqual(sorted(report["flagged_by_availability_pct"]), ["0", "50"])


class ForecastTimingTest(unittest.TestCase):
    def test_buckets_and_latest_capture(self):
        self.assertEqual([bucket(h) for h in (30, 24, 7, 6, 1)], ["T-24h+", "T-6-24h", "T-6-24h", "T-6h", "T-6h"])
        rows = pd.DataFrame({"GW": [8] * 4, "capture": ["a", "a", "b", "b"], "hours_before": [30.0, 30.0, 2.0, 2.0],
                             "bucket": ["T-24h+", "T-24h+", "T-6h", "T-6h"], "player_id": [1, 2, 1, 2],
                             "error": [2.0, -2.0, 1.0, 0.0]})
        report = timing_summary(rows)
        by = {r["bucket"]: r for r in report["by_bucket"]}
        self.assertEqual((by["T-24h+"]["mae"], by["T-6h"]["mae"], by["last"]["mae"]), (2.0, 0.5, 0.5))


if __name__ == "__main__":
    unittest.main()
