import sys
from pathlib import Path
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from understat_identity import match_evidence, name_key


class IdentityTests(unittest.TestCase):
    def frames(self):
        dates = ["2025-01-01", "2025-01-08", "2025-01-15"]
        return (pd.DataFrame({"kickoff_time": dates, "team": ["Arsenal"] * 3, "minutes": [90, 64, 11]}),
                pd.DataFrame({"date": dates, "team": ["Arsenal"] * 3, "time": [90, 65, 11]}))

    def test_shared_games_and_rounding(self):
        left, right = self.frames()
        self.assertEqual(match_evidence(left, right), (3, 0))
        right.loc[1, "time"] = 0
        self.assertEqual(match_evidence(left, right), (2, 1))

    def test_team_mismatch_is_not_evidence(self):
        left, right = self.frames()
        right["team"] = "Chelsea"
        self.assertEqual(match_evidence(left, right), (0, 0))

    def test_duplicate_matches_are_not_double_counted(self):
        left, right = self.frames()
        self.assertEqual(match_evidence(left, pd.concat([right, right])), (0, 0))

    def test_name_normalization_is_not_fuzzy_matching(self):
        self.assertEqual(name_key("André Onana"), name_key("Andre Onana"))
        self.assertNotEqual(name_key("Amadou Onana"), name_key("Andre Onana"))
