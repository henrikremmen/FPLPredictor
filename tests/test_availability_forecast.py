import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from availability_forecast import AvailabilityScenarioModel, availability_scenarios, reported_return
import pandas as pd


class AvailabilityTests(unittest.TestCase):
    def test_scenario_adjustment_and_invalid_factor(self):
        rows = pd.DataFrame({'prediction': [4., 6.], 'reported_return_factor': [0., 1.]})
        model = AvailabilityScenarioModel('reported_return')
        self.assertEqual(model.predict(rows).tolist(), [0., 6.])
        rows.loc[0, 'reported_return_factor'] = 1.5
        with self.assertRaises(ValueError):
            model.predict(rows)

    def setUp(self):
        self.player = dict(id=7, team=1, status="i", chance_of_playing_next_round=0,
            news="Ankle injury - Expected back 18 Oct", news_added="2026-10-01T12:00:00Z")
        self.fixtures = [dict(id=i, event=gw, team_h=1, team_a=2, kickoff_time=date)
            for i, gw, date in [(1, 6, "2026-10-10T15:00Z"),
                                (2, 7, "2026-10-17T15:00Z"),
                                (3, 7, "2026-10-20T15:00Z")]]

    def test_return_between_double_gameweek_fixtures(self):
        frame = availability_scenarios(self.player, self.fixtures, "2026-10-09T12:00Z", 6)
        self.assertEqual(frame.reported_return_factor.tolist(), [0., 0., 1.])
        self.assertEqual(frame.conservative_factor.tolist(), [0., 0., 0.])
        self.assertFalse(frame.calibrated.any())

    def test_unknown_or_stale_return_does_not_imply_recovery(self):
        self.player["news"] = "Unknown return date"
        self.assertIsNone(reported_return(self.player, "2026-10-09T12:00Z"))
        self.player["news"] = "Expected back 8 Oct"
        self.assertIsNone(reported_return(self.player, "2026-10-09T12:00Z"))

    def test_future_news_is_not_used(self):
        self.assertIsNone(reported_return(self.player, "2026-09-30T12:00Z"))

    def test_new_year_resolved_from_news(self):
        self.player.update(news="Expected back 3 Jan", news_added="2026-12-27T12:00Z")
        self.assertEqual(reported_return(self.player, "2026-12-28T12:00Z").year, 2027)
