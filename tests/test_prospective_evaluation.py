from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prospective_evaluation import score_predictions


class EvaluationTests(unittest.TestCase):
    def frames(self):
        keys = dict(season=["2026-27"] * 3, GW=[7] * 3, player_id=[1, 2, 3], fixture=[10] * 3)
        pred = pd.DataFrame({**keys, "model": ["test"] * 3, "prediction": [0., 2., 6.],
            "p_absent": [1., 0., 0.], "p_cameo": [0., 1., 0.], "p_start": [0., 0., 1.]})
        truth = pd.DataFrame({**keys, "target_points": [0., 2., 6.], "minutes": [0, 70, 12], "starts": [0, 0, 1]})
        return pred, truth

    def test_role_scores_use_starts_not_sixty_minutes(self):
        pred, truth = self.frames()
        pred["minutes"], pred["starts"] = 999, 99
        reports, _ = score_predictions(pred, truth)
        self.assertEqual(reports[0]["fixture_points"]["RMSE"], 0)
        self.assertEqual(reports[0]["role"]["multiclass_brier"], 0)

    def test_missing_outcome_is_not_a_zero(self):
        pred, truth = self.frames()
        with self.assertRaisesRegex(ValueError, "Not every"):
            score_predictions(pred, truth.iloc[:2])

    def test_diagnostics_use_observed_minutes_and_signed_bias(self):
        pred, truth = self.frames()
        pred["minutes"] = 90  # Frozen inputs must not define outcome strata.
        pred["prediction"] = [2., 1., 9.]
        reports, _ = score_predictions(pred, truth)
        bands = reports[0]["points_by_observed_minutes"]
        self.assertEqual(bands["absent"]["bias"], 2.)
        self.assertEqual(bands["60plus_minutes"]["bias"], -1.)
        self.assertEqual(bands["1_59_minutes"]["bias"], 3.)
        self.assertEqual(sum(b["rows"] for b in bands.values()), 3)

    def test_empty_observed_band_has_no_invented_metrics(self):
        pred, truth = self.frames()
        truth["minutes"] = 90
        reports, _ = score_predictions(pred, truth)
        self.assertEqual(reports[0]["points_by_observed_minutes"]["absent"], {"rows": 0})

    def test_duplicate_outcomes_and_invalid_probabilities_fail(self):
        pred, truth = self.frames()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            score_predictions(pred, pd.concat([truth, truth]))
        pred.loc[0, "p_start"] = .5
        with self.assertRaisesRegex(ValueError, "Invalid frozen"):
            score_predictions(pred, truth)
