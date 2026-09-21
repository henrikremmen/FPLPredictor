import unittest
from pathlib import Path

import pandas as pd

from fpl_app import ImportedTeam
from manager_analytics import AnalyticsService


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, endpoint):
        self.calls.append(endpoint)
        if endpoint not in self.payloads:
            from fpl_app import AppError
            raise AppError(f"missing {endpoint}")
        return self.payloads[endpoint]


def picks(elements, captain=1, points=60, total=60):
    return {
        "entry_history": {"event": 1, "points": points, "total_points": total},
        "picks": [{
            "element": player_id, "position": index,
            "multiplier": 2 if player_id == captain else (1 if index <= 11 else 0),
            "is_captain": player_id == captain, "is_vice_captain": False,
            "element_type": 1 if index <= 2 else 2 if index <= 7 else 3 if index <= 12 else 4,
        } for index, player_id in enumerate(elements, 1)],
    }


class ManagerAnalyticsTests(unittest.TestCase):
    def setUp(self):
        positions = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
        market = pd.DataFrame([{
            "id": index, "name": f"P{index}", "position": position,
            "team": f"T{index}", "team_id": index, "price": 50,
            "selling_price": 50, "recommended_points": 20 - index / 10,
            "decision_points": 20 - index / 10, "status": "a", "opponent": "X (H)",
            "selected_by_percent": 5.0,
        } for index, position in enumerate(positions + ["MID"], 1)])
        squad = market.iloc[:15].copy()
        self.team = ImportedTeam(
            1, 2, 3, "Manager", "Team", 0, 1, squad, market,
            "deadline", Path("forecast.csv"), horizon=1, lineup_squad=squad.copy(),
            overall_points=60, overall_rank=100,
        )
        elements = [{
            "id": index, "web_name": f"P{index}", "team": index,
            "element_type": 1 if index <= 2 else 2 if index <= 7 else 3 if index <= 12 else 4,
            "selected_by_percent": "5.0",
        } for index in range(1, 17)]
        live = {"elements": [{
            "id": index,
            "stats": {"total_points": 10 if index in {1, 16} else 2, "minutes": 90},
        } for index in range(1, 17)]}
        own_history = {"current": [
            {"event": 1, "points": 60, "total_points": 60, "rank": 100,
             "overall_rank": 100, "bank": 0, "value": 1000,
             "event_transfers": 0, "event_transfers_cost": 0, "points_on_bench": 4},
            {"event": 2, "points": 0, "total_points": 60, "rank": None,
             "overall_rank": 100, "bank": 0, "value": 1000,
             "event_transfers": 0, "event_transfers_cost": 0, "points_on_bench": 0},
        ], "chips": []}
        rival_history = {"current": [
            {"event": 1, "points": 55, "total_points": 55},
            {"event": 2, "points": 0, "total_points": 55},
        ], "chips": []}
        own_gw1 = picks(list(range(1, 16)), captain=1)
        rival_players = list(range(1, 16))
        rival_players[1] = 16
        rival_gw1 = picks(rival_players, captain=16, points=55, total=55)
        own_gw2 = picks(list(range(1, 16)), captain=1, points=0, total=60)
        rival_gw2 = picks(rival_players, captain=16, points=0, total=55)
        self.payloads = {
            "entry/1/": {"name": "Team", "player_first_name": "Test",
                         "player_last_name": "Manager", "leagues": {"classic": [
                             {"id": 99, "name": "Mini", "league_type": "x"},
                         ]}},
            "entry/1/history/": own_history,
            "entry/1/transfers/": [],
            "bootstrap-static/": {
                "events": [
                    {"id": 1, "finished": True, "average_entry_score": 50, "ranked_count": 1000},
                    {"id": 2, "finished": False, "average_entry_score": 0, "ranked_count": 1000},
                ],
                "elements": elements,
                "teams": [{"id": index, "short_name": f"T{index}"} for index in range(1, 17)],
            },
            "leagues-classic/99/standings/?page_standings=1": {
                "league": {"id": 99, "name": "Mini"},
                "standings": {"has_next": False, "results": [
                    {"entry": 1, "entry_name": "Team", "player_name": "You",
                     "rank": 1, "last_rank": 1, "event_total": 0, "total": 60},
                    {"entry": 2, "entry_name": "Rival", "player_name": "Them",
                     "rank": 2, "last_rank": 2, "event_total": 0, "total": 55},
                ]},
            },
            "entry/1/event/1/picks/": own_gw1,
            "entry/2/event/1/picks/": rival_gw1,
            "entry/1/event/2/picks/": own_gw2,
            "entry/2/event/2/picks/": rival_gw2,
            "entry/2/history/": rival_history,
            "event/1/live/": live,
        }

    def test_builds_season_gameweek_league_and_decision_analysis(self):
        result = AnalyticsService(FakeClient(self.payloads)).build(self.team)
        self.assertEqual(result["selected_event"], 1)
        self.assertEqual(result["summary"]["points_vs_global_average"], 10.0)
        self.assertEqual(result["summary"]["overall_rank"], 100)
        self.assertEqual(result["league"]["your_rank"], 1)
        self.assertEqual(result["league"]["member_count"], 2)
        self.assertEqual(result["league"]["mode"], "protect")
        self.assertEqual(result["league"]["development"][0]["gap_to_leader"], 0)
        self.assertTrue(result["gameweek"]["top_gains"])
        self.assertTrue(result["gameweek"]["top_losses"])
        self.assertEqual(result["gameweek"]["top_losses"][0]["name"], "P16")
        self.assertIn("differentials", result["decisions"])
        self.assertIn("captain_matrix", result["decisions"])

    def test_cache_avoids_duplicate_public_requests(self):
        client = FakeClient({"bootstrap-static/": {"events": []}})
        service = AnalyticsService(client)
        self.assertEqual(service.get("bootstrap-static/"), {"events": []})
        self.assertEqual(service.get("bootstrap-static/"), {"events": []})
        self.assertEqual(client.calls, ["bootstrap-static/"])


if __name__ == "__main__":
    unittest.main()
