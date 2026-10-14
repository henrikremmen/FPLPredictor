import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from understat_shots import normalize_match, attach_shot_features, SHOT_FEATURES


class ShotTests(unittest.TestCase):
    def test_historical_backfill_is_not_available_before_capture(self):
        match, payload = self.data()
        history = normalize_match(match, payload, "2026-10-05T12:00Z")
        rows = pd.DataFrame({"season": ["2026-27"] * 2, "player_id": [7, 7],
                             "prediction_cutoff": ["2026-10-03T12:00Z", "2026-10-06T12:00Z"]})
        identities = pd.DataFrame({"season": ["2026-27"], "player_id": [7], "understat_id": [1]})
        observed = attach_shot_features(rows, history, identities, mode="observed")
        self.assertTrue(observed.loc[0, SHOT_FEATURES].isna().all())
        self.assertEqual(observed.loc[1, "us_nonpenalty_shots5"], 1)
        retrospective = attach_shot_features(rows, history, identities, mode="retrospective")
        self.assertEqual(retrospective.loc[0, "us_nonpenalty_shots5"], 1)

    def data(self):
        match = dict(id=10, datetime="2026-10-01 15:00:00", h={"title": "Arsenal"}, a={"title": "Chelsea"})
        player = dict(player_id="1", position="FWD", time="90", xA=".2", key_passes="1", xGChain=".5", xGBuildup=".1")
        shots = [dict(id=str(i), match_id="10", player_id="1", X=".9", Y=".5", xG=xg, situation=situation)
                 for i, xg, situation in [(1, ".8", "Penalty"), (2, ".2", "OpenPlay")]]
        return match, {"rosters": {"h": {"1": player}, "a": {}}, "shots": {"h": shots, "a": []}}

    def test_penalties_excluded_from_shots_quality_and_share(self):
        match, payload = self.data()
        row = normalize_match(match, payload, "2026-10-02T00:00Z").iloc[0]
        self.assertEqual(row.shots, 2)
        self.assertEqual(row.nonpenalty_shots, 1)
        self.assertAlmostEqual(row.npxG, .2)
        self.assertAlmostEqual(row.npxg_per_shot, .2)
        self.assertEqual(row.central_close_shots, 1)
        self.assertEqual(row.npxg_share, 1)
        self.assertEqual(row.observed_at, "2026-10-02T00:00Z")

    def test_wrong_match_and_duplicate_shots_fail(self):
        match, payload = self.data()
        payload["shots"]["h"][0]["match_id"] = "11"
        with self.assertRaises(ValueError):
            normalize_match(match, payload, "2026-10-02T00:00Z")
        match, payload = self.data()
        payload["shots"]["h"].append(payload["shots"]["h"][0])
        with self.assertRaises(ValueError):
            normalize_match(match, payload, "2026-10-02T00:00Z")
