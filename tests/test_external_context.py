from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from external_context import (
    add_odds_to_schedule, add_player_props_to_schedule,
    cross_competition_features, team_key,
)


BOOTSTRAP = {"teams": [
    {"id": 1, "name": "Man Utd", "short_name": "MUN"},
    {"id": 2, "name": "Spurs", "short_name": "TOT"},
]}


class ExternalContextTests(unittest.TestCase):
    def test_team_aliases_and_cross_competition_workload(self):
        self.assertEqual(team_key("Manchester United FC"), "manutd")
        payload = {"matches": [
            {"competition": {"code": "CL"}, "utcDate": "2026-09-15T19:00:00Z",
             "homeTeam": {"name": "Manchester United FC"},
             "awayTeam": {"name": "Tottenham Hotspur FC"}},
            {"competition": {"code": "PL"}, "utcDate": "2026-09-14T19:00:00Z",
             "homeTeam": {"name": "Manchester United FC"},
             "awayTeam": {"name": "Tottenham Hotspur FC"}},
        ]}
        result = cross_competition_features(BOOTSTRAP, payload, "2026-09-16T12:00:00Z")
        self.assertEqual(result[1]["non_pl_matches_last7"], 1)
        self.assertEqual(result[2]["non_pl_matches_last7"], 1)
        self.assertEqual(result[1]["cl_matches_last7"], 1)
        self.assertEqual(result[2]["cl_matches_last14"], 1)
        self.assertAlmostEqual(result[1]["days_since_cl_match"], 17 / 24)

    def test_odds_are_devigged_and_joined_by_fixture(self):
        schedule = pd.DataFrame([{
            "fixture": 9, "team_h": 1, "team_a": 2,
            "kickoff_time": "2026-09-20T15:00:00Z",
        }])
        payload = [{
            "id": "event-9",
            "home_team": "Manchester United", "away_team": "Tottenham Hotspur",
            "commence_time": "2026-09-20T15:00:00Z",
            "bookmakers": [{"markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Manchester United", "price": 2.0},
                    {"name": "Draw", "price": 4.0},
                    {"name": "Tottenham Hotspur", "price": 4.0},
                ]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "point": 2.5, "price": 1.8},
                    {"name": "Under", "point": 2.5, "price": 2.2},
                ]},
            ]}],
        }]
        result = add_odds_to_schedule(schedule, BOOTSTRAP, payload)
        self.assertAlmostEqual(result.iloc[0].market_home_win_probability, .5)
        self.assertAlmostEqual(
            result.iloc[0].market_home_win_probability
            + result.iloc[0].market_draw_probability
            + result.iloc[0].market_away_win_probability, 1.0,
        )
        self.assertGreater(result.iloc[0].market_over25_probability, .5)
        self.assertGreater(result.iloc[0].market_home_expected_goals,
                           result.iloc[0].market_away_expected_goals)
        self.assertGreater(result.iloc[0].market_home_clean_sheet_probability, 0)

        props = [{
            "id": "event-9", "bookmakers": [{"markets": [
                {"key": "player_goal_scorer_anytime", "outcomes": [
                    {"description": "Test Player", "name": "Yes", "price": 2.0},
                    {"description": "Test Player", "name": "No", "price": 2.0},
                ]},
                {"key": "player_assists", "outcomes": [
                    {"description": "Test Player", "name": "Over", "point": .5,
                     "price": 3.0},
                    {"description": "Test Player", "name": "Under", "point": .5,
                     "price": 1.5},
                ]},
            ]}],
        }]
        enriched = add_player_props_to_schedule(result, props)
        values = enriched.iloc[0].market_player_props
        self.assertAlmostEqual(values["testplayer:goal"], .5)
        self.assertAlmostEqual(values["testplayer:assist"], 1 / 3)


if __name__ == "__main__":
    unittest.main()
