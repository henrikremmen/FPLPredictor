import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("FPL_SESSIONS_DB_PATH", ":memory:")

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
        payload = self.client.get("/api/health").json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("uptime_seconds", payload)
        self.assertIn("active_sessions", payload)
        response = self.client.options("/api/health", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"],
                         "http://localhost:5173")

    def test_import_update_and_get_team(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "api.ROOT", Path(temporary)
        ), patch("api.import_team", return_value=fake_team()):
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

    def test_session_survives_in_memory_eviction(self):
        """A session dropped from the in-memory cache (e.g. an API restart)
        must be rebuildable from the durable registry alone."""
        with tempfile.TemporaryDirectory() as temporary, patch(
            "api.ROOT", Path(temporary)
        ), patch("api.import_team", return_value=fake_team()) as mock_import:
            response = self.client.post("/api/team/import", json={
                "reference": "1", "horizon": 1, "risk_profile": "balanced",
            })
            session = response.json()["session_id"]
            mock_import.reset_mock()

            with api.STORE._lock:
                del api.STORE._teams[session]

            response = self.client.get(f"/api/team/{session}")
            self.assertEqual(response.status_code, 200)
            mock_import.assert_called_once_with(
                "1", Path(temporary), horizon=1, risk_profile="balanced",
            )
            self.assertIn(session, api.STORE._teams)

    def test_refresh_guard_rejects_rapid_repeat_calls(self):
        guard = api.RefreshGuard(min_interval_seconds=60)
        with patch("api.refresh_forecast"):
            guard.run()
            with self.assertRaises(api.HTTPException) as failure:
                guard.run()
        self.assertEqual(failure.exception.status_code, 429)

    def test_manual_squad_endpoint_updates_every_team_view(self):
        team = fake_team()
        incoming = pd.DataFrame([player(99, "MID", 12)])
        team.market = pd.concat([team.market, incoming], ignore_index=True)
        incoming_weekly = incoming.copy()
        incoming_weekly["forecast_event"] = 5
        team.weekly_market = pd.concat(
            [team.weekly_market, incoming_weekly], ignore_index=True
        )
        session = api.STORE.add(team)
        with tempfile.TemporaryDirectory() as temporary, patch(
            "api.ROOT", Path(temporary)
        ):
            options = self.client.get(f"/api/team/{session}/squad-options")
            self.assertEqual(options.status_code, 200)
            response = self.client.patch(f"/api/team/{session}/squad", json={
                "mode": "synchronize",
                "changes": [{"out_id": 12, "in_id": 99}],
                "bank": 7,
                "free_transfers": 0,
            })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["squad_source"], "manual_override")
        self.assertEqual(body["bank"], 7)
        self.assertEqual(body["free_transfers"], 0)
        self.assertIn(99, {row["id"] for row in body["squad"]})
        lineup_ids = {row["id"] for row in body["lineup"]["starters"] + body["lineup"]["bench"]}
        self.assertIn(99, lineup_ids)
        self.assertNotIn(12, lineup_ids)

    def test_analytics_endpoint_passes_event_and_league(self):
        session = api.STORE.add(fake_team())
        expected = {"selected_event": 3, "selected_league_id": 99}
        with patch.object(api.ANALYTICS, "build", return_value=expected) as build:
            response = self.client.get(
                f"/api/team/{session}/analytics?event=3&league_id=99"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        build.assert_called_once_with(api.STORE.get(session), event=3, league_id=99)

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

    def test_transfer_endpoint_passes_selected_sales(self):
        session = api.STORE.add(fake_team())
        plan = pd.DataFrame([{
            "out": "P12", "in": "P99", "cost": 5.0, "money_left": 0.5,
            "lineup_gain": 2.0, "expected_gain": 2.0, "hit": 0,
            "net_gain": 2.0, "expected_net_gain": 2.0,
            "projected_total": 60.0, "is_global_optimum": True,
        }])
        with patch("api.recommend_transfers", return_value=plan) as recommend:
            response = self.client.post(
                f"/api/team/{session}/transfers",
                json={"number": 1, "outgoing_ids": [12]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outgoing_ids"], [12])
        recommend.assert_called_once_with(
            api.STORE.get(session), number=1, forced_outgoing=[12]
        )

    def test_multiweek_plan_endpoint(self):
        session = api.STORE.add(fake_team())
        payload = {
            "weeks": [{"event": 5, "captain": "P1"}],
            "total_projected_points": 50.0,
            "discounted_objective_points": 50.0,
            "discount": .9,
            "global_optimum": True,
            "caveat": "Static prices",
        }
        with patch("api.plan_multiweek", return_value=payload) as planner:
            response = self.client.post(
                f"/api/team/{session}/plan", json={"weeks": 1, "discount": .9}
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["global_optimum"])
        planner.assert_called_once()
        self.assertEqual(
            self.client.post(f"/api/team/{session}/plan", json={"weeks": 9}).status_code,
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

    def test_recommended_squads_endpoint(self):
        session = api.STORE.add(fake_team())
        payload = {"forecast_events": [np.int64(5)], "free_hit_by_event": [],
                   "wildcard": {"squad": []}}
        with patch("api.recommend_squads", return_value=payload):
            response = self.client.post(f"/api/team/{session}/recommended-squads")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["forecast_events"], [5])

    def test_strategy_endpoint(self):
        session = api.STORE.add(fake_team())
        payload = {
            "headline": "Rull gratisbyttet",
            "target_event": np.int64(5),
            "actions": [],
        }
        with patch("api.build_strategy_advice", return_value=payload):
            response = self.client.post(f"/api/team/{session}/strategy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["headline"], "Rull gratisbyttet")
        self.assertEqual(response.json()["target_event"], 5)


if __name__ == "__main__":
    unittest.main()
