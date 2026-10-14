from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from source_challengers import SourceChallenger


class Constant:
    kind = "hgb"
    def __init__(self, value):
        self.value = value
    def predict(self, data):
        return np.full(len(data), self.value)


class ChallengerTests(unittest.TestCase):
    def test_sources_affect_no_odds_branch_without_replacing_other_parts(self):
        incumbent = SimpleNamespace(points_model=SimpleNamespace(baseline=SimpleNamespace(
            models=[Constant(3), Constant(99), Constant(6)])))
        challenger = SourceChallenger(incumbent, [])
        challenger.fallback_hgb, challenger.market = Constant(9), Constant(11)
        challenger.fallback_columns = challenger.market_columns = ["x"]
        data = pd.DataFrame(dict(x=[1, 1], market_team_expected_goals=[np.nan, 2.],
            market_opponent_expected_goals=[np.nan, 1.], market_clean_sheet_probability=[np.nan, .4]))
        with patch("source_challengers.market_enrich", side_effect=lambda x: x):
            np.testing.assert_array_equal(challenger.predict(data), [6., 11.])
