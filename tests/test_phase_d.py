"""Phase D: role history (O5), features_v2 (M11), monotone calibration (M12), implied market (M13)."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import role_history
import team_strengths
from challengers import MonotoneShift, features_v2


class RoleHistoryTest(unittest.TestCase):
    def test_versions_only_on_change_and_as_of_never_looks_ahead(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for stamp, order in (("20261001", None), ("20261002", None), ("20261003", 1)):
                folder = root / "data/raw/live_fpl" / f"capture_{stamp}"
                folder.mkdir(parents=True)
                (folder / "bootstrap.json.gz").write_bytes(gzip.compress(json.dumps({"elements": [
                    {"id": 7, "code": 70, "penalties_order": order, "now_cost": 60, "status": "a"}]}).encode()))
                (folder / "manifest.json").write_text(json.dumps({"status": "complete", "season": "2026-27", "files": {
                    "bootstrap": {"received_at": f"2026-10-{stamp[-2:]}T12:00:00+00:00"}}}))
            history = role_history.build(root)
            self.assertEqual(len(history), 2)  # the unchanged 2 October version is dropped
            rows = pd.DataFrame({"season": ["2026-27"] * 3, "player_id": [7] * 3,
                                 "kickoff_time": ["2026-09-30T15:00:00Z", "2026-10-03T12:00:00Z", "2026-10-04T15:00:00Z"]})
            joined = role_history.as_of(history, rows, "kickoff_time")
            self.assertTrue(np.isnan(joined.now_cost.iloc[0]))         # before any snapshot: unknown
            self.assertTrue(np.isnan(joined.penalties_order.iloc[1]))  # same instant is not "before"
            self.assertEqual(joined.penalties_order.iloc[2], 1)


class FeaturesV2Test(unittest.TestCase):
    def test_live_and_training_schemas(self):
        live = pd.DataFrame({"position": ["DEF", "MID"], "now_cost": [45, 80], "penalties_order": [np.nan, 1],
                             "corners_and_indirect_freekicks_order": [1, np.nan], "direct_freekicks_order": [np.nan, 2],
                             "defensive_contribution90_last5": [11.0, 3.0], "defensive_contribution_rate5": [.6, .1]})
        frame = features_v2(live, np.array([2.0, 5.0]))
        self.assertEqual(frame.price.tolist(), [4.5, 8.0])
        self.assertEqual(frame.penalty_first.tolist(), [0.0, 1.0])      # empty order in a bootstrap = no role
        self.assertEqual(frame.set_piece_first.tolist(), [1.0, 0.0])
        training = live.drop(columns="now_cost").assign(price_last1=[4.4, 7.9], role_known=[False, True])
        frame = features_v2(training, np.zeros(2))
        self.assertEqual(frame.penalty_first.tolist(), [-1.0, 1.0])     # no archived bootstrap = unknown
        self.assertEqual(frame.price.tolist(), [4.4, 7.9])


class MonotoneShiftTest(unittest.TestCase):
    def test_isotonic_stretches_a_compressed_top_and_stays_monotone(self):
        base = np.linspace(0, 5, 500)
        actual = np.where(base > 4, base * 1.2, base)  # the top is under-forecast
        for kind in ("isotonic", "linear"):
            shift = MonotoneShift(kind).fit(pd.DataFrame({"base": base}), actual - base)
            adjusted = base + shift.predict(pd.DataFrame({"base": base}))
            self.assertTrue(np.all(np.diff(adjusted) >= -1e-9), kind)
            self.assertGreater(adjusted[-1], base[-1], kind)


class ImpliedMarketTest(unittest.TestCase):
    def rows(self):
        return pd.DataFrame({"fixture": [1, 1, 2, 2], "GW": [10, 10, 12, 12], "planned_fixture": [True] * 4,
                             "team_name": ["Arsenal", "Chelsea", "Arsenal", "Chelsea"],
                             "opp_team_name": ["Chelsea", "Arsenal", "Chelsea", "Arsenal"], "was_home": [1, 0, 0, 1],
                             **{c: [np.nan] * 4 for c in team_strengths.MARKET_COLUMNS},
                             }).assign(market_team_expected_goals=[2.0, 1.0, np.nan, np.nan],
                                       market_opponent_expected_goals=[1.0, 2.0, np.nan, np.nan])

    def test_probabilities_sum_to_one_and_real_odds_are_kept(self):
        rows = self.rows()
        past = pd.DataFrame({"home": ["arsenal", "chelsea"] * 5, "away": ["chelsea", "arsenal"] * 5,
                             "home_rate": [2.0, 1.2] * 5, "away_rate": [0.8, 1.6] * 5, "kind": ["implied"] * 10,
                             "date": pd.Timestamp("2026-10-01", tz="UTC")})
        at = "2026-11-06T12:00:00Z"
        strengths = team_strengths.fit(pd.concat([past, team_strengths.observations_from_rows(rows, at)]), at)
        filled = team_strengths.fill_market(rows, strengths)
        self.assertEqual(filled.market_source.tolist(), ["odds", "odds", "implied", "implied"])
        self.assertEqual(filled.market_team_expected_goals.iloc[:2].tolist(), [2.0, 1.0])  # not overwritten
        implied = filled.iloc[2:]
        total = implied.market_team_win_probability + implied.market_draw_probability + implied.market_opponent_win_probability
        np.testing.assert_allclose(total, 1.0, atol=1e-4)
        np.testing.assert_allclose(implied.market_clean_sheet_probability, np.exp(-implied.market_opponent_expected_goals))
        self.assertGreater(strengths["attack"]["arsenal"], strengths["attack"]["chelsea"])
        self.assertTrue(rows.market_team_expected_goals.iloc[2:].isna().all())  # caller's rows untouched


if __name__ == "__main__":
    unittest.main()
