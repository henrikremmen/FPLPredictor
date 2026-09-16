from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import api
from fpl_app import ImportedTeam


def player(player_id, position, points):
    return {
        "id": player_id, "name": f"P{player_id}", "position": position,
        "team_id": player_id, "team": f"T{player_id}", "price": 50,
        "selling_price": 50, "purchase_price": 50,
        "recommended_points": float(points), "decision_points": float(points),
        "planned_fixtures": 1, "opponent": "OPP (H)", "status": "a",
    }


def fake_team() -> ImportedTeam:
    positions = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    squad = pd.DataFrame([
        player(index, position, 20 - index)
        for index, position in enumerate(positions, 1)
    ])
    weekly = squad.copy()
    weekly["forecast_event"] = 5
    status = {
        chip: {"available": True, "used_event": None, "half": 1,
               "expires_after_gw": 19, "blocked_consecutive": False}
        for chip in ["wildcard", "free_hit", "triple_captain", "bench_boost"]
    }
    return ImportedTeam(
        1, 4, 5, "Manager", "Team", 5, 2, squad, squad,
        "2026-09-19T10:00:00Z", Path("forecast.csv"), horizon=1,
        lineup_squad=squad, weekly_market=weekly, chip_status=status,
    )


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_health_and_explicit_local_cors(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        response = self.client.options("/api/health", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"],
                         "http://localhost:5173")

    def test_import_update_and_get_team(self):
        with patch("api.import_team", return_value=fake_team()):
            response = self.client.post("/api/team/import", json={
                "reference": "1", "horizon": 1, "risk_profile": "balanced",
            })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["lineup"]["formation"], "5-4-1")
        session = body["session_id"]
        updated = self.client.patch(f"/api/team/{session}/settings", json={
            "bank": 17, "free_transfers": 5,
        }).json()
        self.assertEqual(updated["bank"], 17)
        self.assertEqual(updated["free_transfers"], 5)
        self.assertEqual(self.client.get(f"/api/team/{session}").status_code, 200)

    def test_transfer_endpoint_accepts_one_to_five_only(self):
        session = api.STORE.add(fake_team())
        plan = pd.DataFrame([{
            "out": "A + B + C + D + E", "in": "F + G + H + I + J",
            "cost": 25.0, "money_left": 0.5, "lineup_gain": 8.0,
            "expected_gain": 8.0, "hit": 12, "net_gain": -4.0,
            "expected_net_gain": -4.0, "projected_total": 60.0,
            "is_global_optimum": True,
        }])
        with patch("api.recommend_transfers", return_value=plan) as recommend:
            response = self.client.post(
                f"/api/team/{session}/transfers", json={"number": 5}
            )
        self.assertEqual(response.status_code, 200)
        recommend.assert_called_once()
        self.assertTrue(response.json()["global_optimum"])
        self.assertEqual(
            self.client.post(f"/api/team/{session}/transfers", json={"number": 6}).status_code,
            422,
        )

    def test_chip_endpoint_returns_strategy(self):
        session = api.STORE.add(fake_team())
        payload = {
            "recommendation": "Spar chips foreløpig", "best_by_chip": [],
            "forecast_events": [np.int64(5)],
        }
        with patch("api.recommend_chip_strategy", return_value=payload):
            response = self.client.post(f"/api/team/{session}/chips")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendation"], "Spar chips foreløpig")
        self.assertEqual(response.json()["forecast_events"], [5])


if __name__ == "__main__":
    unittest.main()
