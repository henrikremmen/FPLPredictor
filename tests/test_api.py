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

os.environ["FPL_API_TOKEN"] = ""  # the tests run without the API token, whatever .env says
import api
from fpl_app import AppError, ImportedTeam
from session_store import SessionRegistry


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


def team_with_spare_mid() -> ImportedTeam:
    """fake_team() plus an unowned midfielder (99) to swap in for player 12."""
    team = fake_team()
    incoming = pd.DataFrame([player(99, "MID", 12)])
    team.market = pd.concat([team.market, incoming], ignore_index=True)
    team.weekly_market = pd.concat([team.weekly_market, incoming.assign(forecast_event=5)], ignore_index=True)
    return team


SWAP = {"mode": "synchronize", "changes": [{"out_id": 12, "in_id": 99}], "bank": 7, "free_transfers": 0}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        api.RESULTS = api.ResultCache()  # T3 cache: every test starts cold
        warm = patch.object(api, "_warm")  # no background solves while endpoints are mocked
        warm.start()
        self.addCleanup(warm.stop)

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
            self.assertEqual(self.client.get(f"/api/team/{session}").status_code, 200)
        self.assertEqual(updated["bank"], 17)
        self.assertEqual(updated["free_transfers"], 5)

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

    def test_top_manager_endpoints(self):
        session = api.STORE.add(fake_team())
        client = TestClient(api.app)
        with tempfile.TemporaryDirectory() as temporary, patch("api.ROOT", Path(temporary)):
            response = client.get(f"/api/team/{session}/top-managers?cohort=legacy")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"available": False, "cohort": "legacy"})
        self.assertEqual(client.get(f"/api/team/{session}/top-managers?cohort=top10").status_code, 422)
        with tempfile.TemporaryDirectory() as temporary, patch("api.ROOT", Path(temporary)):
            self.assertEqual(client.get(f"/api/team/{session}/copy-check").json(), {"available": False})
        guard = api.RefreshGuard(min_interval_seconds=0, label="top-manager update")
        with patch("api.TOP_GUARD", guard), patch("api.top_managers.collect") as top, \
                patch("api.copy_check.collect") as copies:
            self.assertEqual(client.post(f"/api/team/{session}/top-managers/refresh").json(), {"status": "complete"})
            self.assertEqual(client.get("/api/top-managers/status").json()["state"], "complete")
        top.assert_called_once()
        copies.assert_called_once_with(api.ROOT, api.STORE.get(session).entry_id)

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

    def test_a_correction_from_another_session_is_not_overwritten(self):
        team = team_with_spare_mid()
        with tempfile.TemporaryDirectory() as temporary, patch("api.ROOT", Path(temporary)):
            phone, web = api.STORE.add(team), api.STORE.add(team)
            self.assertEqual(self.client.patch(f"/api/team/{phone}/squad", json=SWAP).status_code, 200)
            body = self.client.patch(f"/api/team/{web}/settings", json={"bank": 9, "free_transfers": 1}).json()
            again = self.client.get(f"/api/team/{phone}").json()
        for payload in (body, again):
            self.assertIn(99, {row["id"] for row in payload["squad"]})
            self.assertEqual(payload["bank"], 9)
        self.assertNotIn(99, set(team.squad["id"]))  # the stored team itself was never changed

    def test_reset_keeps_the_correction_when_fpl_is_down(self):
        team = team_with_spare_mid()
        with tempfile.TemporaryDirectory() as temporary, patch("api.ROOT", Path(temporary)):
            session = api.STORE.add(team)
            self.client.patch(f"/api/team/{session}/squad", json=SWAP)
            with patch("api.import_team", side_effect=AppError("FPL is down")):
                response = self.client.post(f"/api/team/{session}/squad/reset")
            self.assertEqual(response.status_code, 400)
            self.assertIsNotNone(api.override_mtime(Path(temporary), team.entry_id))

    def test_only_the_newest_teams_stay_in_memory(self):
        registry = SessionRegistry(Path("."), db_path=":memory:")
        store = api.TeamStore(registry, max_teams=2)
        first = store.add(fake_team())
        store.add(fake_team())
        store.add(fake_team())
        self.assertEqual(len(store), 2)
        with patch("api.import_team", return_value=fake_team()) as rebuild:
            store.get(first)  # evicted, so rebuilt from the registry
        rebuild.assert_called_once()

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
        with patch("api.plan_with_context", return_value=payload) as planner:
            response = self.client.post(
                f"/api/team/{session}/plan", json={"weeks": 1, "discount": .9}
            )
            chips = self.client.post(f"/api/team/{session}/plan", json={
                "weeks": 1, "chips": True, "bench_weights": [0, .1, .05, 0],
                "requirements": [{"kind": "own_by", "player_id": 3, "event": 5}]})
            missing = self.client.post(f"/api/team/{session}/plan", json={"requirements": [{"kind": "max_club", "limit": 2}]})
            bad = self.client.post(f"/api/team/{session}/plan", json={"bench_weights": [0, 2, 0, 0]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["global_optimum"])
        self.assertEqual(planner.call_count, 2)
        self.assertEqual(chips.status_code, 200)
        last = planner.call_args
        self.assertEqual((last.kwargs["chips"], last.kwargs["requirements"]),
                         (True, ({"kind": "own_by", "player_id": 3, "event": 5},)))
        self.assertEqual(last.args[0].bench_weights, (0, .1, .05, 0))
        self.assertEqual((missing.status_code, bad.status_code), (422, 422))
        self.assertEqual(
            self.client.post(f"/api/team/{session}/plan", json={"weeks": 9}).status_code,
            422,
        )

    def test_chip_endpoint_returns_strategy(self):
        session = api.STORE.add(fake_team())
        payload = {
            "recommendation": "Save chips for now", "best_by_chip": [],
            "forecast_events": [np.int64(5)],
        }
        with patch("api.recommend_chip_strategy", return_value=payload):
            response = self.client.post(f"/api/team/{session}/chips")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendation"], "Save chips for now")
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
            "headline": "Roll the free transfer",
            "target_event": np.int64(5),
            "actions": [],
        }
        with patch("api.build_strategy_advice", return_value=payload):
            response = self.client.post(f"/api/team/{session}/strategy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["headline"], "Roll the free transfer")
        self.assertEqual(response.json()["target_event"], 5)


if __name__ == "__main__":
    unittest.main()


class LoopEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_lock_runs_in_background_and_rejects_locked_or_closed_window(self):
        import threading
        release = threading.Event()
        job = api.LoopJob(run=lambda: release.wait(5) and {"locked": "loop_gw10_x"})
        base = {"event": 10, "window_open": True, "locked": False}
        with patch.object(api, "LOOP_JOB", job), patch.object(api.prospective_loop, "status", return_value=base), \
                patch.object(api, "fpl_data_freshness", return_value={}):
            started = self.client.post("/api/loop/lock")
            self.assertEqual(started.json()["job"]["state"], "running")
            self.assertEqual(self.client.post("/api/loop/lock").status_code, 409)  # no overlap
            release.set()
            for _ in range(100):
                if job.snapshot()["state"] != "running":
                    break
                threading.Event().wait(.02)
            self.assertEqual(self.client.get("/api/loop/status").json()["job"]["result"], {"locked": "loop_gw10_x"})
        for state, detail in (({**base, "locked": True}, "already locked"), ({**base, "window_open": False}, "not open")):
            with patch.object(api.prospective_loop, "status", return_value=state), \
                    patch.object(api, "fpl_data_freshness", return_value={}):
                response = self.client.post("/api/loop/lock")
                self.assertEqual(response.status_code, 409)
                self.assertIn(detail, response.json()["detail"])

    def test_failed_loop_is_reported(self):
        def boom():
            raise ValueError("No capture with frozen GW10 forecasts before the deadline")
        job = api.LoopJob(run=boom)
        job.start()
        for _ in range(100):
            if job.snapshot()["state"] != "running":
                break
            __import__("time").sleep(.02)
        self.assertEqual(job.snapshot()["state"], "failed")
        self.assertIn("No capture", job.snapshot()["error"])


class ResultCacheTests(unittest.TestCase):
    """T3: a cached answer only under an identical key; any input change is a new key."""

    def test_key_changes_with_every_input_and_hits_repeat(self):
        from dataclasses import replace
        from result_cache import ResultCache, cache_key
        team = fake_team()
        base = cache_key(team, "plan", weeks=4)
        self.assertEqual(base, cache_key(fake_team(), "plan", weeks=4))
        variants = [cache_key(team, "plan", weeks=5), cache_key(team, "strategy"),
                    cache_key(replace(team, bank=team.bank + 1), "plan", weeks=4),
                    cache_key(replace(team, free_transfers=team.free_transfers + 1), "plan", weeks=4),
                    cache_key(replace(team, horizon=3), "plan", weeks=4),
                    cache_key(replace(team, locked_ids={1}), "plan", weeks=4),
                    cache_key(replace(team, bench_weights=(0, 0, 0, 0)), "plan", weeks=4)]
        self.assertEqual(len(set(variants + [base])), len(variants) + 1)
        cache, calls = ResultCache(max_entries=2), []
        work = lambda: calls.append(1) or {"x": len(calls)}
        self.assertEqual(cache.compute("a", work), ({"x": 1}, False))
        self.assertEqual(cache.compute("a", work), ({"x": 1}, True))
        cache.compute("b", work), cache.compute("c", work)
        self.assertIsNone(cache.get("a"))  # oldest dropped
        cache.warm([("d", lambda: {"x": 9}), ("e", lambda: 1 / 0)]).join()
        self.assertEqual(cache.get("d")["result"], {"x": 9})
        self.assertIsNone(cache.get("e"))  # failures are left for the page to report



class FixtureTickerTests(unittest.TestCase):
    """U16: per Gameweek opponent, expected points and 60+ chance; blanks are explicit."""

    def test_squad_and_market_rows(self):
        from decision_workspace import fixture_ticker
        team = fake_team()
        weekly = team.weekly_market.copy()
        later = weekly.assign(forecast_event=6, planned_fixtures=2, opponent="A (H) + B (A)")
        later = later[~later.id.eq(3)]  # player 3 has no GW6 fixture
        team.weekly_market = pd.concat([weekly, later], ignore_index=True)
        team.market = team.market.assign(can_select=True)
        result = fixture_ticker(team, "squad")
        self.assertEqual(result["events"], [5, 6])
        three = next(p for p in result["players"] if p["id"] == 3)
        self.assertEqual(three["weeks"][1], {"event": 6, "fixtures": 0, "opponent": "Blank", "xp": 0.0, "p60": None})
        one = next(p for p in result["players"] if p["id"] == 1)
        self.assertEqual(one["weeks"][1]["fixtures"], 2)
        self.assertTrue(all(p["owned"] for p in result["players"]))
        self.assertEqual(fixture_ticker(team, "market")["players"], [])  # everyone in this market is owned


class TokenAuthTests(unittest.TestCase):
    def test_a_set_token_guards_every_route_but_health(self):
        client = TestClient(api.app)
        with patch("api.API_TOKEN", "s3cret"):
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.get("/api/team/missing").status_code, 401)
            self.assertEqual(client.get("/api/team/missing", headers={"Authorization": "Bearer wrong"}).status_code, 401)
            self.assertEqual(client.get("/api/team/missing", headers={"Authorization": "Bearer s3cret"}).status_code, 404)

    def test_no_token_leaves_the_local_api_open(self):
        self.assertEqual(TestClient(api.app).get("/api/team/missing").status_code, 404)

    def test_listening_on_every_network_needs_a_token(self):
        with self.assertRaises(RuntimeError):
            api._require_token_when_exposed("0.0.0.0", "")
        api._require_token_when_exposed("0.0.0.0", "s3cret")
        api._require_token_when_exposed("127.0.0.1", "")
