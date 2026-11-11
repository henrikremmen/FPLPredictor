import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import copy_check as cc  # noqa: E402
import top_managers as tm  # noqa: E402

TEMPLATE = list(range(1, 13))  # owned by nearly everyone


def rounds(squads, buys=None, chips=None):
    """{gw: squad} -> compact rounds; buys/chips keyed by gw."""
    return {g: {"squad": s, "buys": (buys or {}).get(g, []), "chip": (chips or {}).get(g)}
            for g, s in squads.items()}


def weight(g, p):
    return 0.05 if p in TEMPLATE else 4.0  # template players are almost free to share


def surprise(g, p):
    return 0.3 if p in TEMPLATE else 2.5


class MeasureTests(unittest.TestCase):
    def test_rare_shared_players_count_more_than_template(self):
        me = rounds({1: TEMPLATE + [50, 51, 52]})
        rare_twin = rounds({1: TEMPLATE + [50, 51, 52]})
        template_only = rounds({1: TEMPLATE + [60, 61, 62]})
        self.assertEqual(cc.overlap(me, rare_twin, weight)[0], 1.0)
        self.assertLess(cc.overlap(me, template_only, weight)[0], 0.05)

    def test_buys_are_net_squad_changes_and_a_free_hit_return_is_not_a_buy(self):
        week = lambda g, squad, chip=None: {"event": g, "chip": chip, "picks": [{"id": p} for p in squad]}
        timeline = {"weeks": [week(1, [1, 2, 3]), week(2, [1, 2, 4], "wildcard"), week(3, [7, 8, 9], "freehit"),
                              week(4, [1, 2, 4]), week(5, [1, 5, 4])]}
        rows = cc.compact(timeline, {2, 3, 4, 5})
        self.assertEqual([rows[g]["buys"] for g in (2, 3, 4, 5)], [[4], [7, 8, 9], [], [5]])
        self.assertNotIn(1, rows)  # unfinished rounds are left out

    def test_same_buys_in_the_same_round_only(self):
        f = rounds({1: TEMPLATE, 2: TEMPLATE}, buys={1: [50], 2: [51]})
        c = rounds({1: TEMPLATE, 2: TEMPLATE}, buys={1: [50], 2: [52]})
        self.assertEqual(cc.same_buys(f, c), [(1, 50)])

    def test_follows_means_one_round_later(self):
        leader = rounds({1: TEMPLATE, 2: TEMPLATE}, buys={1: [50, 51], 2: [51]})
        follower = rounds({1: TEMPLATE, 2: TEMPLATE}, buys={2: [50, 51]})
        self.assertEqual(cc.follows(follower, leader), [(2, 50)])  # 51 was also bought in round 2

    def test_same_chips_and_labels(self):
        a = rounds({1: TEMPLATE, 2: TEMPLATE}, chips={1: "bboost", 2: "3xc"})
        b = rounds({1: TEMPLATE, 2: TEMPLATE}, chips={1: "bboost", 2: "wildcard"})
        self.assertEqual(cc.same_chips(a, b), [(1, "bboost")])
        self.assertEqual(cc.percentile(5, [1, 2, 3, 9]), 75.0)
        self.assertEqual([cc.label(x) for x in (96, 85, 50)], ["Strong", "Some", "Normal"])


def season(rare, n=6):
    """Six rounds of template plus three rotating rare players, buying one rare player a round."""
    squads = {g: TEMPLATE + [rare[(g + k) % len(rare)] for k in range(3)] for g in range(1, n + 1)}
    return rounds(squads, {g: [squads[g][-1]] for g in range(2, n + 1)})


class ReportTests(unittest.TestCase):
    def setUp(self):
        creator = season([100, 101, 102, 103, 104, 105])
        self.entries = {
            1: creator,                                   # the creator
            10: {g: dict(r, squad=list(r["squad"]), buys=list(r["buys"])) for g, r in creator.items()},
            11: season([300, 301, 302, 303, 304, 305]),   # an independent friend
        }
        self.baseline = []
        for b in range(500, 540):                          # 40 independent managers
            self.entries[b] = season([1000 + b * 10 + i for i in range(6)])
            self.baseline.append(b)

    def test_the_copier_is_strong_and_the_independent_friend_normal(self):
        members = [{"entry": 10, "name": "Copier", "team_name": "A"},
                   {"entry": 11, "name": "Own ideas", "team_name": "B"}]
        rep = cc.build_report({"id": 7, "name": "Mini"}, members, {1: "Creator"}, self.entries,
                              self.baseline, weight, surprise, lambda g, p: 0.4, {100: "Rare"})
        copier, own = rep["members"]
        self.assertEqual(copier["closest"]["name"], "Creator")
        self.assertEqual(copier["signal"]["label"], "Strong")
        self.assertEqual(copier["overlap"], 1.0)
        self.assertEqual(copier["same_buys"], 5)
        self.assertTrue(copier["evidence"])
        self.assertEqual(own["signal"]["label"], "Normal")
        self.assertEqual(rep["friends"]["scores"][0][0], None)
        self.assertEqual(rep["baseline_size"], 40)


class CollectTests(unittest.TestCase):
    def test_collect_writes_a_league_report_and_report_reads_it(self):
        elements = [{"id": i, "code": i, "first_name": "F", "second_name": f"S{i}", "web_name": f"P{i}",
                     "team": 1 + i % 20, "element_type": 1 + i % 4, "now_cost": 50, "status": "a",
                     "selected_by_percent": "10.0"} for i in range(1, 601)]
        boot = {"total_players": 1000, "elements": elements, "teams": [{"id": i} for i in range(1, 21)],
                "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z", "finished": True,
                            "data_checked": True, "is_current": True, "is_next": False}]}
        row = lambda e: {"entry": e, "rank": e, "rank_sort": e, "total": 100, "event_total": 50,
                         "player_name": f"M{e}", "entry_name": f"T{e}"}
        payloads = {
            tm.API + "bootstrap-static/": boot,
            tm.API + "entry/10/": {"leagues": {"classic": [{"id": 7, "name": "Mini", "league_type": "x"},
                                                           {"id": 314, "name": "Overall", "league_type": "s"}]}},
            tm.API + "leagues-classic/7/standings/": {"standings": {"results": [row(10), row(11)]}},
            tm.API + f"leagues-classic/{tm.OVERALL_LEAGUE}/standings/?page_standings=1":
                {"standings": {"results": [row(e) for e in range(500, 503)]}},
        }
        for p in range(1, 601):
            payloads[f"{tm.API}element-summary/{p}/"] = {"history": [{"round": 1, "selected": 100, "transfers_in": 5}]}
        fake_timeline = lambda self, e, cache: {"weeks": [{"event": 1, "chip": None, "transfers": [],
                                                          "picks": [{"id": e % 500 + i} for i in range(15)]}]}

        class Fake(tm.Fetcher):
            def get(self, url, *, text=False):
                if url not in payloads:
                    raise tm.CollectError(f"{url}: HTTP 404", 404)
                return payloads[url]

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(cc, "BASELINE_TOP_PAGE", 1), patch.object(cc, "BASELINE_PAGES", 1), \
                patch.object(cc.AnalyticsService, "timeline", fake_timeline), \
                patch.dict(cc.CREATORS, {"2026-27": {41: "Tuber"}}):
            reports = cc.collect(Path(tmp), 10, fetcher=Fake())
            self.assertEqual([r["league"]["name"] for r in reports], ["Mini"])
            self.assertEqual(len(reports[0]["members"]), 2)
            self.assertEqual(reports[0]["baseline_size"], 3)
            self.assertTrue((Path(tmp) / "data/local/copy_check/2026-27/baseline.json").exists())
            stored = cc.report(Path(tmp), 10)
            self.assertTrue(stored["available"])
            self.assertTrue(stored["members"][0]["is_you"])
            self.assertEqual(stored["leagues"], [{"id": 7, "name": "Mini"}])
            self.assertFalse(cc.report(Path(tmp), 999)["available"])


if __name__ == "__main__":
    unittest.main()
