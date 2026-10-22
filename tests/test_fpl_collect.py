from pathlib import Path
import gzip
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fpl_collect
from data_contract import ContractError, diff_rows, map_codes, validate_gameweeks, validate_price_moves
from fpl_collect import auto, due_phases, export, load_xp

TEAMS = (1, 2, 3, 4)
FIXTURES = [  # (id, event, home, away, home score, away score)
    (1, 1, 1, 2, 2, 1), (2, 1, 3, 4, 0, 0),
    (3, 2, 2, 1, 1, 1), (4, 2, 4, 3, 1, 0),
]
KICKOFF = {1: "2026-08-22T14:00:00Z", 2: "2026-08-29T14:00:00Z"}
DEADLINE = {1: "2026-08-21T17:30:00Z", 2: "2026-08-28T17:30:00Z", 3: "2026-09-04T17:30:00Z"}


def element(pid, team):
    return {"id": pid, "code": 1000 + pid, "first_name": f"P{pid}", "second_name": "X",
            "web_name": f"P{pid}", "team": team, "element_type": 2 + pid % 3, "now_cost": 50,
            "status": "a", "total_points": 10, "ep_next": "3.5", **{c: 0 for c in fpl_collect.CLEANED_COLUMNS
                                                                    if c not in {"first_name", "second_name", "element_type", "now_cost", "total_points"}}}


def world(score_override=None):
    """Four clubs with twelve players each (eleven start) over two finished Gameweeks."""
    elements = [element(team * 100 + k, team) for team in TEAMS for k in range(12)]
    fixtures = [{"id": f, "event": e, "kickoff_time": KICKOFF[e], "team_h": h, "team_a": a,
                 "finished": True, "team_h_score": hs, "team_a_score": as_, "stats": []}
                for f, e, h, a, hs, as_ in FIXTURES]
    summaries = {}
    for el in elements:
        history = []
        for fixture in fixtures:
            if el["team"] not in (fixture["team_h"], fixture["team_a"]):
                continue
            home = el["team"] == fixture["team_h"]
            scored = fixture["team_h_score"] if home else fixture["team_a_score"]
            k = el["id"] % 100
            history.append({
                "element": el["id"], "fixture": fixture["id"], "round": fixture["event"],
                "opponent_team": fixture["team_a"] if home else fixture["team_h"], "was_home": home,
                "kickoff_time": fixture["kickoff_time"], "team_h_score": fixture["team_h_score"],
                "team_a_score": fixture["team_a_score"], "minutes": 90 if k < 11 else 0,
                "starts": int(k < 11), "goals_scored": int(k < scored), "own_goals": 0,
                "total_points": 2, "value": 50, "expected_goals": "0.10",
            })
        summaries[el["id"]] = {"history": history, "history_past": [{"season_name": "2025/26", "total_points": 5}],
                               "fixtures": []}
    if score_override:
        summaries[100]["history"][0].update(score_override)
    bootstrap = {"elements": elements, "teams": [{"id": t, "name": f"Club {t}"} for t in range(1, 21)],
                 "events": [{"id": e, "deadline_time": DEADLINE[e], "finished": e < 3,
                             "data_checked": e < 3, "is_current": e == 2, "is_next": e == 3} for e in (1, 2, 3)]}
    return bootstrap, fixtures, summaries


def fake_api(bootstrap, fixtures, summaries, calls):
    def capture(endpoint, directory, name):
        calls.append(endpoint)
        if endpoint == "bootstrap-static/":
            data = bootstrap
        elif endpoint == "fixtures/":
            data = fixtures
        elif endpoint.startswith("element-summary/"):
            data = summaries[int(endpoint.split("/")[1])]
        else:
            data = {"elements": []}
        body = json.dumps(data).encode()
        (directory / f"{name}.json.gz").write_bytes(gzip.compress(body))
        return data, {"endpoint": endpoint, "started_at": "2026-09-01T00:00:00+00:00", "bytes": len(body)}
    return capture


SMALL = patch.multiple("data_contract", PLAYER_RANGE=(1, 1000), GAMEWEEK_PLAYER_RANGE=(1, 1000))


class DataContractTest(unittest.TestCase):
    def rows(self):
        bootstrap, fixtures, summaries = world()
        return fpl_collect.gameweek_rows(bootstrap, fixtures, summaries, {}, [1, 2]), fixtures

    @SMALL
    def test_valid_season_and_new_midseason_player_pass(self):
        rows, fixtures = self.rows()
        late = rows[(rows["element"] == 111) & (rows["GW"] == 2)].assign(element=999, starts=0, minutes=0)
        validate_gameweeks(pd.concat([rows, late]), fixtures)

    @SMALL
    def test_each_contract_rule_fails(self):
        rows, fixtures = self.rows()
        broken = {
            "duplicate": pd.concat([rows, rows.head(1)]),
            "starts": rows.assign(starts=rows["starts"].where(rows["element"] != 100, 0)),
            "goals": rows.assign(goals_scored=rows["goals_scored"].where(rows["element"] != 105, 1)),
            "minutes": rows.assign(minutes=rows["minutes"].where(rows["element"] != 100, 130)),
            "kickoff": rows.assign(kickoff_time=rows["kickoff_time"].where(rows["element"] != 100, "")),
            "price": rows.assign(value=rows["value"].where((rows["element"] != 100) | (rows["GW"] == 1), 58)),
            "team missing": rows[rows["element"] // 100 != 4],
        }
        for label, frame in broken.items():
            with self.subTest(label), self.assertRaises(ContractError):
                validate_gameweeks(frame, fixtures)

    def test_price_moves_at_most_one_tenth_per_day(self):
        before = {"elements": [{"id": 1, "now_cost": 50}]}
        validate_price_moves(before, {"elements": [{"id": 1, "now_cost": 51}]}, 0.5)
        with self.assertRaises(ContractError):
            validate_price_moves(before, {"elements": [{"id": 1, "now_cost": 52}]}, 1.0)

    def test_code_mapping_is_one_to_one_or_fails(self):
        previous = pd.DataFrame({"id": [1, 2], "code": [10, 20]})
        mapped = map_codes(previous, pd.DataFrame({"id": [7, 8], "code": [20, 30]}))
        self.assertEqual(mapped.set_index("code")["id_current"].dropna().to_dict(), {20: 7, 30: 8})
        with self.assertRaises(ContractError):
            map_codes(previous, pd.DataFrame({"id": [7, 8], "code": [20, 20]}))

    def test_diff_rows_reports_changed_cells_and_rows(self):
        old = pd.DataFrame({"element": ["1", "2"], "fixture": ["5", "5"], "total_points": ["2", "6"]})
        new = pd.DataFrame({"element": ["1", "3"], "fixture": ["5", "5"], "total_points": ["3", "1"]})
        changes = diff_rows(old, new)
        self.assertEqual(changes[changes["element"] == "1"][["old", "new"]].values.tolist(), [["2", "3"]])
        self.assertEqual(len(changes), 3)


class ScheduleTest(unittest.TestCase):
    def test_daily_after_price_changes_and_checkpoint_once(self):
        bootstrap = {"events": [{"id": 8, "is_next": True, "deadline_time": "2026-10-23T17:30:00Z"}]}
        self.assertEqual(due_phases(bootstrap, [], "2026-10-22T02:00:00Z"), [])
        self.assertEqual(due_phases(bootstrap, [], "2026-10-22T03:00:00Z"), ["daily"])
        done = [{"capture_phases": ["daily"], "started_at": "2026-10-22T03:00:00+00:00", "target_event": {"id": 8}}]
        self.assertEqual(due_phases(bootstrap, done, "2026-10-22T20:00:00Z"), ["24h"])
        done.append({"capture_phases": ["24h"], "started_at": "2026-10-22T20:00:00+00:00", "target_event": {"id": 8}})
        self.assertEqual(due_phases(bootstrap, done, "2026-10-22T21:00:00Z"), [])
        self.assertEqual(due_phases(bootstrap, done, "2026-10-23T12:00:00Z"), ["daily", "6h"])


class ExportTest(unittest.TestCase):
    def run_export(self, root, payloads, calls=None):
        with SMALL, patch.object(fpl_collect, "REQUEST_INTERVAL", 0), \
                patch.object(fpl_collect, "capture_endpoint", fake_api(*payloads, calls if calls is not None else [])):
            return export(root)

    def test_export_writes_vaastav_files_and_logs_corrections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            result = self.run_export(root, world(), calls)
            season = root / "data" / "2026-27"
            self.assertEqual(result["events"], [1, 2])
            self.assertEqual(len([c for c in calls if c.startswith("element-summary/")]), 48)
            self.assertIn("event/2/live/", calls)
            gw1 = pd.read_csv(season / "gws" / "gw1.csv")
            self.assertEqual(list(gw1.columns[:4]), ["name", "position", "team", "xP"])
            self.assertIn("code", gw1.columns)
            self.assertEqual(gw1.groupby(["fixture", "team"])["starts"].sum().unique().tolist(), [11])
            merged = pd.read_csv(season / "gws" / "merged_gw.csv")
            self.assertEqual(sorted(merged["GW"].unique()), [1, 2])
            for name in ("players_raw", "cleaned_players", "player_idlist", "fixtures", "teams", "history_past"):
                self.assertTrue((season / f"{name}.csv").exists(), name)
            manifest = json.loads(next((season / "raw").glob("export_*/manifest.json")).read_text())
            self.assertEqual(manifest["new_events"], [1, 2])

            unchanged = (season / "gws" / "gw2.csv").read_text()
            self.run_export(root, world(score_override={"total_points": 9}))
            self.assertEqual((season / "gws" / "gw2.csv").read_text(), unchanged)
            corrections = pd.read_csv(season / "corrections.csv")
            self.assertEqual(corrections[["GW", "element", "column", "old", "new"]].values.tolist(),
                             [[1, 100, "total_points", 2, 9]])

    def test_auto_takes_one_daily_snapshot_and_exports_pending_rounds(self):
        with tempfile.TemporaryDirectory() as tmp, SMALL, patch.object(fpl_collect, "REQUEST_INTERVAL", 0), \
                patch.object(fpl_collect, "capture_endpoint", fake_api(*world(), [])):
            root = Path(tmp)
            first = auto(root, observed_at="2026-09-01T03:00:00Z")
            second = auto(root, observed_at="2026-09-01T04:00:00Z")
            self.assertEqual(first["export"]["events"], [1, 2])
            self.assertEqual(second, {"light_snapshot": None, "export": None})
            manifest = json.loads((Path(first["light_snapshot"]) / "manifest.json").read_text())
            self.assertEqual(manifest["capture_phases"], ["daily"])
            self.assertEqual(sorted(manifest["files"]), ["bootstrap", "event_status", "fixtures", "set_piece_notes"])
            self.assertEqual(len(list((root / "snapshots").glob("*/*/manifest.json"))), 1)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["data", "snapshots"])

    def test_contract_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ContractError):
                self.run_export(Path(tmp), world(score_override={"minutes": 130}))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_xp_from_latest_pre_deadline_snapshot_and_existing_rounds_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, started, ep in (("a", "2026-10-15T08:00:00+00:00", "4.0"),
                                      ("b", "2026-10-16T08:00:00+00:00", "5.0"),
                                      ("c", "2026-10-18T08:00:00+00:00", "9.0")):
                folder = root / "snaps" / name
                folder.mkdir(parents=True)
                (folder / "bootstrap.json.gz").write_bytes(gzip.compress(json.dumps(
                    {"elements": [{"id": 1, "ep_next": ep}]}).encode()))
                (folder / "manifest.json").write_text(json.dumps({
                    "status": "complete", "started_at": started,
                    "target_event": {"id": 7, "deadline_time": "2026-10-17T10:00:00Z"}}))
            self.assertEqual(load_xp([root / "snaps"])[7], {1: "5.0"})
            (root / "season" / "gws").mkdir(parents=True)
            pd.DataFrame({"element": [1], "xP": ["4.2"]}).to_csv(root / "season" / "gws" / "gw7.csv", index=False)
            self.assertEqual(load_xp([root / "snaps"], root / "season")[7], {1: "4.2"})


class CollectorCopyTest(unittest.TestCase):
    def test_fpl_data_copies_match_source(self):
        copies = ROOT / "fpl-data" / "collector"
        if not copies.exists():
            self.skipTest("fpl-data checkout not present")
        for name in ("fpl_collect.py", "data_contract.py"):
            self.assertEqual((copies / name).read_text(), (ROOT / "src" / name).read_text(),
                             f"Copy src/{name} to fpl-data/collector/")


if __name__ == "__main__":
    unittest.main()
