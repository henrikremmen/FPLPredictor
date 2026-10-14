import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from understat_features import attach_understat, FIELDS, UNDERSTAT_FEATURES


class UnderstatTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame({field: [1., 9.] for field in FIELDS})
        self.history["id"] = [10, 11]
        self.history["understat_id"] = 7
        self.history["available_at"] = pd.to_datetime(["2024-01-01", "2024-01-03"], utc=True)
        self.ids = pd.DataFrame({"season": ["2023-24"], "player_id": [22], "understat_id": [7]})
        self.rows = pd.DataFrame({"season": ["2023-24"] * 3, "player_id": [22, 22, 99],
            "prediction_cutoff": ["2024-01-01", "2024-01-03", "2024-01-04"], "xG_last5": [42.] * 3})

    def test_strict_cutoff_unmapped_player_and_provider_separation(self):
        result = attach_understat(self.rows, self.history, self.ids)
        self.assertTrue(result.loc[0, UNDERSTAT_FEATURES].isna().all())
        self.assertEqual(result.loc[1, "us_xg_last5"], 1.)
        self.assertTrue(result.loc[2, UNDERSTAT_FEATURES].isna().all())
        np.testing.assert_equal(result.xG_last5.to_numpy(), [42.] * 3)

    def test_future_outcomes_do_not_change_features(self):
        original = attach_understat(self.rows, self.history, self.ids)
        self.history.loc[1, "xG"] = 1000.
        modified = attach_understat(self.rows, self.history, self.ids)
        pd.testing.assert_frame_equal(original, modified)

    def test_ambiguous_identity_fails(self):
        with self.assertRaises(ValueError):
            attach_understat(self.rows, self.history, pd.concat([self.ids, self.ids]))
