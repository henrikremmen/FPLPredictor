import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import top_managers as tm  # noqa: E402
from data_contract import ContractError  # noqa: E402
from fpl_app import ImportedTeam  # noqa: E402

API = tm.API


class FakeFetcher(tm.Fetcher):
    def __init__(self, payloads):
        super().__init__()
        self.payloads = payloads
        self.calls = []

    def get(self, url, *, text=False):
        self.calls.append(url)
        if url not in self.payloads:
            raise tm.CollectError(f"{url}: HTTP 404", 404)
        return self.payloads[url]


def picks(elements, captain, total, chip=None, cost=0):
    return {
        "active_chip": chip,
        "entry_history": {"event": 1, "points": 70, "total_points": total,
                          "event_transfers_cost": cost, "bank": 5, "value": 1000,
                          "overall_rank": 1},
        "picks": [{"element": e, "multiplier": 2 if e == captain else int(i < 11),
                   "is_captain": e == captain} for i, e in enumerate(elements)],
    }


def bootstrap(total_players=10_000):
    return {
        "total_players": total_players,
        "elements": [{"id": i, "code": i, "first_name": "F", "second_name": f"S{i}",
                      "web_name": f"P{i}", "team": 1 + i % 20, "element_type": 1 + i % 4,
                      "now_cost": 50, "status": "a"} for i in range(1, 601)],
        "teams": [{"id": i} for i in range(1, 21)],
        "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": True,
                    "data_checked": True, "is_current": True, "is_next": False}],
    }


def standings(page):
    return {"standings": {"has_next": True, "results": [
        {"entry": rank, "rank": rank, "rank_sort": rank, "total": 1000 - rank,
         "event_total": 70, "player_name": f"M{rank}", "entry_name": f"T{rank}"}
        for rank in range((page - 1) * 50 + 1, page * 50 + 1)]}}


def past(ranks):
    return [{"season_name": f"20{10 + i}/{11 + i}", "rank": r} for i, r in enumerate(ranks)]


class HelperTests(unittest.TestCase):
    def test_legacy_score_weights_recent_seasons_and_needs_five(self):
        self.assertIsNone(tm.legacy_score(past([100] * 4)))
        flat = tm.legacy_score(past([1000] * 5))
        self.assertEqual(flat["legacy_score"], 3.0)
        self.assertEqual(flat["typical_rank"], 1000)
        recent_good = tm.legacy_score(past([10_000] * 4 + [10]))  # newest season last
        recent_bad = tm.legacy_score(past([10] + [10_000] * 4))
        self.assertLess(recent_good["legacy_score"], recent_bad["legacy_score"])
        self.assertEqual(recent_good["top10k_seasons"], 5)

    def test_seed_ids_keeps_table_order_without_duplicates(self):
        html = ('<a href="https://fantasy.premierleague.com/entry/48683/history">A</a>'
                '<a href="https://fantasy.premierleague.com/entry/7/history">B</a>'
                '<a href="https://fantasy.premierleague.com/entry/48683/event/3">A</a>')
        self.assertEqual(tm.seed_ids(html), [48683, 7])

    def test_sample_pages_are_unique_inside_cutoff_and_reproducible(self):
        pages = tm.sample_pages(2257, "2026-27", 10)
        self.assertEqual(len(pages), 40)
        self.assertEqual(len(set(pages)), 40)
        self.assertTrue(all(1 <= p <= 2257 for p in pages))
        self.assertEqual(pages, tm.sample_pages(2257, "2026-27", 10))
        self.assertNotEqual(pages, tm.sample_pages(2257, "2026-27", 11))
        self.assertEqual(tm.sample_pages(3, "2026-27", 10), [1, 2, 3])

    def test_match_percent(self):
        team = {i: 1 for i in range(11)} | {11: 0, 12: 0, 13: 0, 14: 0}
        self.assertEqual(tm.match_percent(team, team), 100.0)
        self.assertEqual(tm.match_percent({1: 1}, {2: 1}), 0.0)
        self.assertEqual(tm.match_percent({1: 2, 2: 1}, {1: 1, 2: 1}), 66.7)  # captain counts double

    def test_validate_picks_rejects_short_squad(self):
        payload = picks(list(range(1, 15)), 1, 500)
        with self.assertRaises(ContractError):
            tm.validate_picks(payload, 5)

    def test_fetcher_retries_after_429_and_skips_404(self):
        ok, limited, missing = Mock(status_code=200), Mock(status_code=429), Mock(status_code=404)
        ok.json.return_value = {"fine": True}
        limited.headers = {"Retry-After": "0"}
        missing.headers = {}
        session = Mock(headers={})
        session.get.side_effect = [limited, ok, missing]
        fetcher = tm.Fetcher(session, rate=1000)
        with patch.object(tm.time, "sleep"):
            self.assertEqual(fetcher.get("u1"), {"fine": True})
            self.assertEqual(fetcher.many(["u2"]), {})
        self.assertEqual(session.get.call_count, 3)


class CollectTests(unittest.TestCase):
    def payloads(self):
        squad = list(range(1, 16))
        data = {API + "bootstrap-static/": bootstrap()}
        url = f"{API}leagues-classic/{tm.OVERALL_LEAGUE}/standings/?page_standings={{}}"
        data[url.format(1)], data[url.format(2)] = standings(1), standings(2)
        for entry in range(1, 101):
            data[f"{API}entry/{entry}/event/1/picks/"] = picks(squad, 1 + entry % 3, 1000 - entry)
            data[f"{API}entry/{entry}/history/"] = {"current": [{"event": 1}], "past": [], "chips": []}
            data[f"{API}entry/{entry}/transfers/"] = [{"event": 1, "element_out": 16, "element_in": 1}]
        data[tm.SEED_URL.format(1)] = " ".join(
            f"fantasy.premierleague.com/entry/{e}/history" for e in (9001, 9002, 9003))
        data[tm.SEED_URL.format(2)] = data[tm.SEED_URL.format(3)] = ""
        data[f"{API}entry/9001/history/"] = {"current": [{"event": 1}], "past": past([50] * 6),
                                              "chips": [{"name": "wildcard", "event": 1}]}
        data[f"{API}entry/9002/history/"] = {"current": [{"event": 1}], "past": past([50] * 4), "chips": []}
        data[f"{API}entry/9003/history/"] = {"current": [], "past": past([10] * 8), "chips": []}
        data[f"{API}entry/9001/"] = {"player_first_name": "Leg", "player_last_name": "End", "name": "Old"}
        data[f"{API}entry/9001/event/1/picks/"] = picks(squad, 2, 900, chip="wildcard", cost=4)
        data[f"{API}entry/9001/transfers/"] = []
        return data

    def test_collect_writes_every_cohort_and_skips_a_finished_gameweek(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fetcher = FakeFetcher(self.payloads())
            snap = tm.collect(root, fetcher=fetcher)
            self.assertEqual(snap["season"], "2026-27")
            self.assertEqual(snap["cohorts"]["top100"]["size"], 100)
            self.assertEqual(snap["cohorts"]["top1pct"]["size"], 100)  # 1% of 10,000; pages 1-2
            self.assertEqual(snap["cohorts"]["top1pct"]["population"], 100)
            self.assertEqual(snap["cutoffs"], {"top100_total": 900, "top1pct_rank": 100,
                                               "top1pct_total": 900})
            legacy = snap["cohorts"]["legacy"]
            self.assertEqual([m["entry"] for m in legacy["managers"]], [9001])  # 9002: 4 seasons, 9003: inactive
            self.assertEqual(legacy["managers"][0]["name"], "Leg End")
            self.assertEqual(legacy["chips"], {"wildcard": 100.0})
            self.assertEqual(legacy["average_hits"], 4.0)
            self.assertEqual(snap["cohorts"]["top100"]["managers"][0]["transfers"], [[16, 1]])
            self.assertTrue((root / "data/local/top_managers/2026-27/gw01.json").exists())
            self.assertTrue((root / "data/local/top_managers/2026-27/legacy.json").exists())

            again = FakeFetcher(self.payloads())
            tm.collect(root, fetcher=again)
            self.assertEqual(again.calls, [API + "bootstrap-static/"])

    def test_youtubers_cohort_follows_the_creator_list(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(tm.CREATORS, {"2026-27": {9001: "Tuber"}}):
            snap = tm.collect(Path(tmp), fetcher=FakeFetcher(self.payloads()))
        tubers = snap["cohorts"]["youtubers"]
        self.assertEqual(tubers["size"], 1)
        self.assertEqual(tubers["managers"][0]["name"], "Tuber")
        self.assertEqual(tubers["chips"], {"wildcard": 100.0})

    def test_compare_reports_gap_match_and_moves(self):
        positions = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
        market = pd.DataFrame([{
            "id": i, "name": f"P{i}", "position": pos, "team": "T", "team_id": i, "price": 50,
            "selling_price": 50, "recommended_points": 5.0, "decision_points": 5.0,
            "status": "a", "opponent": "X (H)", "selected_by_percent": 5.0,
        } for i, pos in enumerate(positions + ["MID"], 1)])
        team = ImportedTeam(1, 1, 2, "Me", "Mine", 0, 1, market.iloc[:15].copy(), market,
                            "deadline", Path("f.csv"), lineup_squad=market.iloc[:15].copy(),
                            overall_points=850, overall_rank=5000)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tm.collect(root, fetcher=FakeFetcher(self.payloads()))
            result = tm.compare(team, "top100", root)
            self.assertTrue(result["available"])
            self.assertEqual(result["catch_up"]["gap"], 50)
            self.assertEqual(result["catch_up"]["per_gameweek"], round(50 / 37, 1))
            self.assertEqual(len(result["managers"]), 100)
            self.assertEqual(result["managers"][0]["shared"], 15)
            self.assertEqual(result["moves"]["bought"][0]["name"], "P1")
            self.assertEqual(result["moves"]["bought"][0]["share"], 100.0)
            self.assertTrue(0 <= result["match"]["cohort"] <= 100)
            sample = tm.compare(team, "top1pct", root)
            self.assertEqual(sample["meta"]["margin_pp"], 9.8)  # 100 managers
            self.assertFalse(tm.compare(team, "legacy", Path(tmp) / "empty")["available"])


if __name__ == "__main__":
    unittest.main()
