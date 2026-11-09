import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_quality import capture_quality, code_coverage, consequences, fpl_data_freshness, model_card
import pandas as pd


class FplDataFreshnessTest(unittest.TestCase):
    def test_age_stale_and_exported_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual((fpl_data_freshness(root)["checkout"], fpl_data_freshness(root)["stale"]), (False, True))
            snap = root / "fpl-data/snapshots/2026-27/20261023T150710Z_x"
            snap.mkdir(parents=True)
            (snap / "bootstrap.json.gz").write_bytes(b"")
            (snap / "manifest.json").write_text(json.dumps({"status": "complete", "started_at": "2026-10-23T15:07:00+00:00"}))
            gws = root / "fpl-data/data/2026-27/gws"
            gws.mkdir(parents=True)
            for name in ("gw1.csv", "gw7.csv", "merged_gw.csv"):
                (gws / name).write_text("")
            fresh = fpl_data_freshness(root, "2026-10-24T03:07:00Z")
            self.assertEqual((fresh["age_hours"], fresh["stale"], fresh["exported_rounds"]), (12.0, False, [1, 7]))
            self.assertTrue(fpl_data_freshness(root, "2026-11-06T15:07:00Z")["stale"])  # the silent October hole


class CaptureQualityTest(unittest.TestCase):
    def test_odds_coverage_fallback_share_sources_and_consequences(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp)
            (snap / "manifest.json").write_text(json.dumps({
                "started_at": "2026-11-06T10:00:00+00:00", "forecast_at": "2026-11-06T10:05:00+00:00",
                "captured_players": 2, "expected_players": 2,
                "files": {"bootstrap": {"status": 200}, "odds": {"status": 200}, "all_competitions": {"status": 503},
                          "player_1": {"status": 200}}}))
            pd.DataFrame({"GW": [10, 10, 11, 11, 12], "fixture": [1, 1, 2, 3, 4], "planned_fixture": [True] * 5,
                          "market_team_expected_goals": [1.2, None, 1.1, None, None]}).to_csv(
                snap / "horizon_fixture_forecast.csv", index=False)
            quality = capture_quality(snap, "2026-11-07T12:00:00Z")
            self.assertEqual(quality["odds_coverage"], {10: 1.0, 11: 0.5, 12: 0.0})
            self.assertEqual(quality["market_fallback_share"], 0.6)
            self.assertEqual(sorted(quality["sources"]), ["all_competitions", "bootstrap", "odds"])
            notes = consequences({"capture": quality, "missed_locks": [9], "fpl_data": {"stale": True}})
            self.assertEqual(len(notes), 5)
            self.assertTrue(notes[0].startswith("No odds for GW12–12"))
            self.assertIn("GW9", notes[2])
            self.assertIn("all_competitions", notes[-1])
            self.assertEqual(consequences({"capture": {"odds_coverage": {10: 1.0}, "age_hours": 2, "sources": {}}}), [])

    def test_code_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd.DataFrame({"code": [1, 2]}).to_csv(Path(tmp) / "players_raw.csv", index=False)
            self.assertEqual(code_coverage(Path(tmp), [{"code": 1}, {"code": 3}], [Path(tmp)]),
                             {"players": 2, "with_history": 1, "share": 0.5})


class ModelCardTest(unittest.TestCase):
    def test_empty_repository_gives_an_honest_empty_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = model_card(Path(tmp))
            self.assertEqual(card["rounds"], {"shown": 0, "counted_v1": 0, "counted_v2": 0, "needed": 8})
            self.assertEqual(card["leaderboard"], [])
            self.assertIn("pre-registered criterion", card["claim"])
            self.assertTrue(card["limitations"])
            self.assertIn("consequences", card["data_quality"])


if __name__ == "__main__":
    unittest.main()
