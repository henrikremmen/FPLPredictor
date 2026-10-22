from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import prospective_loop
from challengers import register
from prospective_lock import verify_lock


class ConstantModel:
    """Picklable stand-in: points from a feature, optional offset."""

    def __init__(self, offset=0.0):
        self.offset = offset

    def predict(self, rows):
        return rows["points_avg5"].to_numpy(float) + self.offset


def gz(path: Path, payload) -> dict:
    body = json.dumps(payload).encode()
    path.write_bytes(gzip.compress(body))
    return {"status": 200, "file": path.name, "stored_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "received_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}


def fake_capture(root: Path, deadline: datetime) -> Path:
    """20 clubs x one player per position x 2 = 160 players, one fixture each in GW8."""
    snapshot = root / "data/raw/live_fpl/capture_test"
    snapshot.mkdir(parents=True)
    elements, rows = [], []
    for team in range(1, 21):
        for position in (1, 2, 3, 4, 2, 3, 1, 4):
            pid = len(elements) + 1
            elements.append({"id": pid, "web_name": f"P{pid}", "team": team, "element_type": position,
                             "now_cost": 45, "can_select": True, "ep_next": "2.0"})
            rows.append({"season": "2026-27", "GW": 8, "player_id": pid, "fixture": 100 + (team - 1) // 2,
                         "points_avg5": float(pid % 7), "planned_fixture": True,
                         "prediction": 99.0, "p_zero_minutes": 1.0})
    for element in elements:
        element["code"] = 1000 + element["id"]
    fixtures = [{"id": 100 + i, "kickoff_time": (deadline + timedelta(days=1)).isoformat()} for i in range(10)]
    bootstrap = {"elements": elements, "teams": [{"id": t} for t in range(1, 21)],
                 "events": [{"id": 8, "deadline_time": deadline.isoformat(), "finished": False, "data_checked": False}]}
    model_path = root / "artifacts/models/production_x/model.joblib"
    model_path.parent.mkdir(parents=True)
    joblib.dump({"model": ConstantModel()}, model_path)
    pd.DataFrame(rows).to_csv(snapshot / "horizon_fixture_forecast.csv", index=False)
    manifest = {"status": "complete", "forecast_status": "experimental_frozen", "forecast_horizons": [8],
                "forecast_at": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
                "model_path": str(model_path), "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                "files": {"bootstrap": gz(snapshot / "bootstrap.json.gz", bootstrap),
                          "fixtures": gz(snapshot / "fixtures.json.gz", fixtures)}}
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    return snapshot


class LockTest(unittest.TestCase):
    def test_lock_freezes_incumbent_challengers_and_fpl_benchmark_with_squads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_capture(root, datetime.now(timezone.utc) + timedelta(hours=10))
            challenger = root / "artifacts/challengers/plus_one"
            challenger.mkdir(parents=True)
            joblib.dump({"model": ConstantModel(1.0), "production_eligible": False}, challenger / "model.joblib")
            register(root, "plus_one", "model.joblib", plan_item="test")

            bundle = prospective_loop.lock(root, 8)
            manifest = verify_lock(bundle)
            self.assertEqual(set(manifest["models"]), {"incumbent", "plus_one", "fpl_ep_next"})
            predictions = pd.read_csv(bundle / "predictions.csv")
            by_model = predictions.pivot_table(index="player_id", columns="model", values="prediction")
            np.testing.assert_allclose(by_model.plus_one - by_model.incumbent, 1.0)
            np.testing.assert_allclose(by_model.fpl_ep_next, 2.0)
            self.assertNotIn(99.0, predictions.prediction.to_list())  # capture outputs never leak in
            self.assertFalse(predictions.filter(like="p_").notna().any().any())
            decisions = json.loads((bundle.with_name(bundle.name + "_decisions") / "manifest.json").read_text())
            self.assertEqual({row["model"] for row in decisions["summary"]}, {"incumbent", "plus_one", "fpl_ep_next"})
            self.assertEqual(prospective_loop.evaluate(root), {bundle.name: "pending"})
            with self.assertRaises(ValueError):  # one bundle per round
                prospective_loop.lock(root, 8)

    def test_lock_after_deadline_and_eligible_challenger_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_capture(root, datetime.now(timezone.utc) - timedelta(minutes=1))
            with self.assertRaises(ValueError):
                prospective_loop.lock(root, 8)
            (root / "artifacts/challengers/bad").mkdir(parents=True)
            (root / "artifacts/challengers/bad/challenger.json").write_text(json.dumps(
                {"name": "bad", "model_file": "m", "production_eligible": True}))
            with self.assertRaises(ValueError):
                prospective_loop.registered(root)


class CupMinutesLockTest(unittest.TestCase):
    def test_cup_minutes_reach_rows_and_sources_are_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deadline = datetime.now(timezone.utc) + timedelta(hours=10)
            snapshot = fake_capture(root, deadline)
            cup = root / "data/raw/fpl_core_insights/20261022T000000Z/2026-27"
            (cup / "EFL Cup/GW4").mkdir(parents=True)
            pd.DataFrame({"player_id": [1], "player_code": [1001]}).to_csv(cup / "players.csv", index=False)
            pd.DataFrame({"match_id": ["m"], "kickoff_time": [(deadline - timedelta(days=3)).isoformat()],
                          "finished": [True]}).to_csv(cup / "EFL Cup/GW4/matches.csv", index=False)
            pd.DataFrame({"player_id": [1], "match_id": ["m"], "minutes_played": [75]}).to_csv(
                cup / "EFL Cup/GW4/playermatchstats.csv", index=False)
            received = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            files = {name: {"url": "x", "sha256": "x", "received_at": received}
                     for name in ["2026-27/players.csv", "2026-27/EFL Cup/GW4/matches.csv", "2026-27/EFL Cup/GW4/playermatchstats.csv"]}
            (cup.parent / "manifest.json").write_text(json.dumps({"finished_at": received, "files": files}))
            features = pd.read_csv(snapshot / "horizon_fixture_forecast.csv")
            attached, sources = prospective_loop._attach_cup_minutes(root, snapshot, features[features.GW.eq(8)])
            self.assertEqual(attached.loc[attached.player_id.eq(1), "non_pl_minutes_7d"].tolist(), [75.0])
            self.assertEqual(attached.loc[attached.player_id.eq(2), "non_pl_minutes_7d"].tolist(), [0.0])
            self.assertEqual(len(sources), 3)


class LeaderboardTest(unittest.TestCase):
    def write_round(self, root: Path, name: str, protocol: str, gw: int, gains: dict):
        folder = root / "artifacts/prospective_eval" / name
        (folder / "forecasts/b").mkdir(parents=True)
        (folder / "decisions").mkdir()
        metrics = [{"model": model, "fixture_points": {"MAE": 1.0 - gain / 100, "RMSE": 2.0},
                    "weekly_points": {"MAE": 1.2 - gain / 100, "RMSE": 2.2}} for model, gain in gains.items()]
        (folder / "forecasts/b/report.json").write_text(json.dumps({"metrics": metrics}))
        (folder / "decisions/report.json").write_text(json.dumps({"metrics": [
            {"model": model, "actual_points": 60 + gain, "captain_points_before_doubling": 8} for model, gain in gains.items()]}))
        (folder / "round.json").write_text(json.dumps({"round": name, "protocol": protocol, "GW": gw}))

    def test_criterion_needs_eight_loop_rounds_positive_interval_and_no_worse_mae(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_round(root, "gw7_manual", "manual-2026-10-10", 7, {"incumbent": 0, "better": 9, "worse_mae": 9})
            for gw in range(8, 15):
                self.write_round(root, f"loop_gw{gw}", "loop-v1", gw,
                                 {"incumbent": 0, "better": 2 + gw % 3, "worse_mae": 2 + gw % 3})
            models = {row["model"]: row for row in prospective_loop.leaderboard(root)["models"]}
            self.assertEqual((models["better"]["rounds_shown"], models["better"]["rounds_counted"]), (8, 7))
            self.assertFalse(models["better"]["criterion_met"])  # seven counted rounds

            self.write_round(root, "loop_gw15", "loop-v1", 15, {"incumbent": 0, "better": 3, "worse_mae": 3})
            frame = prospective_loop.round_table(root)
            frame.loc[frame.model.eq("worse_mae"), "weekly_MAE"] += 0.5
            summary = {row["model"]: row for row in prospective_loop.summarize(frame)}
            self.assertTrue(summary["better"]["criterion_met"])
            self.assertGreater(summary["better"]["team_points_diff_ci"][0], 0)
            self.assertFalse(summary["worse_mae"]["criterion_met"])
            self.assertFalse(summary["incumbent"]["criterion_met"])
            self.assertTrue((root / "artifacts/prospective_eval/leaderboard.md").exists())
            self.assertFalse((root / "artifacts/models").exists())  # never touches production


class CalibrationTest(unittest.TestCase):
    def test_isotonic_maps_wait_for_six_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rng = np.random.default_rng(1)
            for gw in range(1, 7):
                folder = root / f"artifacts/prospective_eval/r{gw}"
                (folder / "forecasts/b").mkdir(parents=True)
                (folder / "round.json").write_text(json.dumps({"round": f"r{gw}", "protocol": "loop-v1", "GW": gw}))
                p60 = rng.uniform(0, 1, 200)
                pd.DataFrame({"model": "incumbent", "p_zero_minutes": 1 - p60, "p_60plus_minutes": p60,
                              "minutes": np.where(rng.uniform(size=200) < p60 ** 2, 90, 0)}
                             ).to_csv(folder / "forecasts/b/scored_predictions.csv", index=False)
                if gw == 5:
                    with self.assertRaises(ValueError):
                        prospective_loop.fit_minutes_calibration(root)
            folder = prospective_loop.fit_minutes_calibration(root)
            maps = joblib.load(folder / "calibration.joblib")["maps"]
            self.assertLess(maps["60plus"].predict([0.5])[0], 0.5)  # overconfident input is pulled down
            self.assertFalse(joblib.load(folder / "calibration.joblib")["production_eligible"])


if __name__ == "__main__":
    unittest.main()
