from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from challengers import (OPENFPL_FEATURES, TRANSFER_ROUNDS, PositionEnsemble, crowd_features,
                         prior_season_table, register, registered, transfer_features)
from data_contract import ContractError


def players_raw(folder: Path, rows):
    folder.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(folder / "players_raw.csv", index=False)


class SeasonTransferTest(unittest.TestCase):
    def test_prior_season_matched_on_code_and_new_players_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            players_raw(root / "a", [{"id": 1, "code": 10, "minutes": 900, "total_points": 50, "starts": 10,
                                      "expected_goal_involvements": 2.0, "points_per_game": "5.0"},
                                     {"id": 2, "code": 20, "minutes": 100, "total_points": 3, "starts": 1,
                                      "expected_goal_involvements": 0.1, "points_per_game": "1.0"}])
            players_raw(root / "b", [{"id": 7, "code": 10}, {"id": 8, "code": 20}, {"id": 9, "code": 30}])
            table = prior_season_table({"2025-26": root / "a", "2026-27": root / "b"}).set_index("player_id")
            self.assertAlmostEqual(table.loc[7, "prior_pts90"], 5.0)
            self.assertTrue(np.isnan(table.loc[8, "prior_pts90"]))  # under 270 minutes
            self.assertTrue(np.isnan(table.loc[9, "prior_min_share"]))  # new to the league

            players_raw(root / "c", [{"id": 1, "code": 10}, {"id": 2, "code": 10}])
            with self.assertRaises(ContractError):  # ambiguous code fails instead of guessing
                prior_season_table({"2025-26": root / "a", "2026-27": root / "c"})

    def test_weight_fades_to_zero_after_transfer_rounds(self):
        rows = pd.DataFrame({"season": "s", "player_id": [1, 1, 1], "GW": [1, 6, TRANSFER_ROUNDS + 1],
                             "position": "MID"})
        prior = pd.DataFrame({"season": ["s"], "player_id": [1], "prior_pts90": [4.0], "prior_min_share": [.5],
                              "prior_xgi90": [.3], "prior_start_share": [.5], "prior_ppg": [4.0]})
        features = transfer_features(rows, prior, np.zeros(3))
        self.assertEqual(features.weight.tolist(), [1.0, 0.5, 0.0])
        self.assertEqual(features.prior_pts90_w.tolist(), [4.0, 2.0, 0.0])


class CrowdTest(unittest.TestCase):
    def test_history_and_live_fields_share_a_within_round_scale(self):
        history = pd.DataFrame({"season": "s", "GW": [3, 3, 3], "player_id": [1, 2, 3], "position": "FWD",
                                "transfers_balance": [-50, 10, 900], "selected": [5, 50, 500], "value": [60, 60, 61]})
        live = pd.DataFrame({"season": "s", "GW": [8, 8, 8], "player_id": [1, 2, 3], "position": "FWD",
                             "transfers_in_event": [0, 20, 1000], "transfers_out_event": [50, 10, 100],
                             "selected_by_percent": [0.1, 1.0, 10.0], "cost_change_start": [0, 0, 1]})
        a, b = crowd_features(history, np.zeros(3)), crowd_features(live, np.zeros(3))
        np.testing.assert_allclose(a.net_transfers_rank, b.net_transfers_rank)
        np.testing.assert_allclose(a.ownership_rank, b.ownership_rank)
        self.assertEqual(b.price_rise.tolist(), [0.0, 0.0, 1.0])
        later = pd.concat([history, history.assign(GW=4, value=[60, 61, 63])], ignore_index=True)
        self.assertEqual(crowd_features(later, np.zeros(6)).price_rise.tolist()[3:], [0.0, 1.0, 2.0])


class Constant:
    def __init__(self, value):
        self.value = value

    def predict(self, matrix):
        assert list(matrix.columns) == OPENFPL_FEATURES
        return np.full(len(matrix), self.value)


class PositionEnsembleTest(unittest.TestCase):
    def test_averages_forest_and_boosting_per_position_and_derives_features(self):
        columns = set(OPENFPL_FEATURES) | {"market_team_expected_goals", "market_opponent_expected_goals"}
        rows = pd.DataFrame({column: [1.0, 1.0, 1.0] for column in columns})
        rows["was_home"], rows["position"] = [True, False, True], ["GK", "DEF", "FWD"]
        model = PositionEnsemble({"GK": (Constant(1.0), Constant(3.0)), "DEF": (Constant(0.0), Constant(4.0))})
        self.assertEqual(model.predict(rows).tolist(), [2.0, 2.0, 0.0])  # no FWD model -> 0


class RegistryTest(unittest.TestCase):
    def test_only_declared_non_production_challengers_are_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "artifacts/challengers/m1").mkdir(parents=True)
            register(root, "m1", "model.joblib", plan_item="M1")
            self.assertEqual(list(registered(root)), ["m1"])
            self.assertFalse((root / "artifacts/models").exists())


if __name__ == "__main__":
    unittest.main()


class ExtraChallengerTest(unittest.TestCase):
    """K1/K2: features_v3 and minutes_v2 inputs, live deadline features, and the retrospective gate."""

    def test_shrunk_rates_pull_small_samples_to_the_round_average(self):
        from challengers import SHRINK_GAMES, features_v3
        rows = pd.DataFrame({"GW": [5, 5, 5, 6], "position": ["MID"] * 4,
                             "minutes_season_before": [0, 900, 90, 900], "xG_season_before": [0, 3.0, 1.0, 9.0],
                             "xA_season_before": [0, 1.0, 0, 1.0], "xG90_last10": [np.nan, .3, 1.0, .9],
                             "xA90_last10": [np.nan, .1, 0, .1], "start_rate10": [0, 1, .1, 1]})
        out = features_v3(rows, np.zeros(4))
        prior = 4.0 / 11  # GW5 only: (3 + 1) xG over 11 games; GW6 rows never enter it
        self.assertAlmostEqual(out.xG90_shrunk[0], prior)
        self.assertAlmostEqual(out.xG90_shrunk[2], (1.0 + SHRINK_GAMES * prior) / (1 + SHRINK_GAMES))
        self.assertAlmostEqual(out.xG90_shrunk[3], .9)  # alone in GW6: its own rate (9 xG over 10 games) is the prior

    def test_competition_ranks_teammates_per_fixture_on_both_schemas(self):
        from challengers import minutes_v2
        training = pd.DataFrame({"season": "2026-27", "fixture": [1, 1, 1, 2], "team": ["A", "A", "A", "B"],
                                 "position": ["FWD", "FWD", "FWD", "FWD"], "minutes_avg5": [90, 70, 20, 90],
                                 "start_rate5": 1, "start_rate10": 1, "minutes_last1": 90})
        out = minutes_v2(training, np.zeros(4))
        self.assertEqual(out.rank_in_position.tolist(), [1, 2, 3, 1])
        self.assertEqual(out.regulars_in_position.tolist(), [2, 2, 2, 1])
        live = training.drop(columns="team").assign(team_name=["A", "A", "A", "B"])
        self.assertEqual(minutes_v2(live, np.zeros(4)).rank_in_position.tolist(), [1, 2, 3, 1])

    def test_deadline_rows_carry_the_new_windows(self):
        from deadline_features import player_features
        history = pd.DataFrame({"minutes": [90] * 12, "starts": [1] * 10 + [0, 0], "total_points": 2, "bps": 10,
                                "ict_index": 5, "threat": 1, "creativity": 1, "influence": 1, "saves": 0,
                                "clean_sheets": 0, "expected_goals": .5, "expected_assists": .2,
                                "goals_scored": 0, "assists": 0, "bonus": 0})
        out = player_features(history)
        self.assertAlmostEqual(out["xG90_last10"], .5)
        self.assertAlmostEqual(out["start_rate10"], .8)
        self.assertEqual((out["minutes_season_before"], round(out["xG_season_before"], 6)), (1080, 6.0))

    def test_a_correction_that_loses_to_the_base_is_not_registered(self):
        from unittest.mock import patch
        import challengers
        with tempfile.TemporaryDirectory() as tmp:
            root, features = Path(tmp), Path(tmp) / "features"
            features.mkdir()
            keys = {"season": ["2026-27"], "GW": [1], "fixture": [1], "player_id": [1]}
            pd.DataFrame({**keys, "team": ["A"], "start_rate10": [1.0], "defensive_contribution90_last5": [2.0]}).to_csv(features / "player_fixture_features.csv", index=False)
            check = {"rows": 10, "base_MAE": 1.0, "adjusted_MAE": 1.1}
            with patch.object(challengers, "_training_data", return_value=pd.DataFrame(keys)), \
                    patch.object(challengers, "_residual_fit", return_value=(object(), {"retrospective_check": check})):
                result = challengers.train_extra(root, features, "base", "minutes_v2", "minutes_v2_test")
            self.assertFalse(result["registered"])
            self.assertTrue(Path(result["report"]).exists())
            self.assertFalse((root / "artifacts/challengers/minutes_v2_test").exists())
