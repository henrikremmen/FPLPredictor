import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from role_models import role_labels, role_metrics


class RoleLabelTests(unittest.TestCase):
    def test_short_start_and_long_substitute_are_not_minutes_bands(self):
        frame = pd.DataFrame({"minutes": [12, 70, 0, 90, 0, 0],
                              "starts": [1, 0, 0, np.nan, np.nan, 1]})
        labels = role_labels(frame)
        self.assertEqual(labels.iloc[:3].tolist(), [2, 1, 0])
        self.assertTrue(labels.iloc[3:5].isna().all())
        self.assertEqual(labels.iloc[5], 2)

    def test_missing_labels_are_excluded_from_scores(self):
        frame = pd.DataFrame({"minutes": [90, 0], "starts": [1, np.nan]})
        result = role_metrics(frame, np.array([[0., 0., 1.], [1., 0., 0.]]))
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["unlabelled"], 1)
        self.assertEqual(result["multiclass_brier"], 0)

    def test_invalid_probabilities_are_rejected(self):
        with self.assertRaises(ValueError):
            role_metrics(pd.DataFrame({"minutes": [90], "starts": [1]}),
                         np.array([[.5, .5, .5]]))
