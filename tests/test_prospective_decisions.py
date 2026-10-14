from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prospective_decisions import score_selections


class DecisionEvaluationTests(unittest.TestCase):
    def data(self):
        position = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
        chosen = pd.DataFrame(dict(player_id=range(15), position=position, team=[i % 5 for i in range(15)],
            value=[50] * 15, starter=[i not in [1, 6, 11, 14] for i in range(15)],
            captain=[i == 0 for i in range(15)], model=["test"] * 15, season=["2026-27"] * 15, GW=[7] * 15))
        forecasts = chosen[["model", "season", "GW", "player_id"]].assign(fixture=10)
        truth = forecasts.drop(columns="model").assign(target_points=2.)
        truth.loc[1, "target_points"] = 100  # tempting bench player must stay benched
        return chosen, forecasts, truth

    def test_captain_doubled_and_bench_unchanged(self):
        reports, _ = score_selections(*self.data())
        self.assertEqual(reports[0]["actual_points"], 24)
        self.assertEqual(reports[0]["bench_points_not_counted"], 106)

    def test_missing_second_fixture_cannot_be_silently_ignored(self):
        chosen, forecasts, truth = self.data()
        forecasts = pd.concat([forecasts, forecasts.iloc[[0]].assign(fixture=11)])
        with self.assertRaisesRegex(ValueError, "Missing selected"):
            score_selections(chosen, forecasts, truth)

    def test_unselected_captain_fails(self):
        chosen, forecasts, truth = self.data()
        chosen["captain"] = chosen.player_id.eq(1)
        with self.assertRaisesRegex(ValueError, "captain"):
            score_selections(chosen, forecasts, truth)
