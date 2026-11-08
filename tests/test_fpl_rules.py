"""T4: FPL rule boundaries, and every engine using the same rules."""
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fpl_rules
from fpl_rules import chip_half, hit_cost, legal_formation, next_free_transfers, selling_price


class RuleBoundaryTests(unittest.TestCase):
    def test_selling_price_rounds_the_half_rise_down_and_passes_falls_on(self):
        self.assertEqual(selling_price(50, 51), 50)  # +0.1m rise: half is 0.05, rounded down
        self.assertEqual(selling_price(50, 52), 51)
        self.assertEqual(selling_price(50, 53), 51)
        self.assertEqual(selling_price(50, 48), 48)  # a fall is passed on in full
        self.assertEqual(selling_price(50, 50), 50)

    def test_free_transfers_roll_cap_and_chip_weeks(self):
        self.assertEqual(next_free_transfers(1, 0), 2)
        self.assertEqual(next_free_transfers(5, 0), 5)        # capped at five
        self.assertEqual(next_free_transfers(2, 3), 1)        # a hit leaves none, then one more
        self.assertEqual(next_free_transfers(4, 9, "wildcard"), 5)  # saved transfers survive a Wildcard
        self.assertEqual(next_free_transfers(3, 15, "free_hit"), 4)

    def test_hits_only_beyond_free_transfers_and_never_on_wildcard(self):
        self.assertEqual([hit_cost(1, 1), hit_cost(2, 1), hit_cost(4, 2)], [0, 4, 8])
        self.assertEqual(hit_cost(10, 1, "wildcard"), 0)

    def test_chip_halves_switch_after_gw19(self):
        self.assertEqual((chip_half(19), chip_half(20)), ((1, 19), (20, 38)))

    def test_formations(self):
        self.assertTrue(legal_formation({"GK": 1, "DEF": 3, "MID": 5, "FWD": 2}))
        self.assertFalse(legal_formation({"GK": 1, "DEF": 2, "MID": 5, "FWD": 3}))  # two defenders
        self.assertFalse(legal_formation({"GK": 2, "DEF": 3, "MID": 4, "FWD": 2}))  # two keepers in an XI
        self.assertTrue(legal_formation({"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}, players=15))  # Bench Boost


class SharedRulesTests(unittest.TestCase):
    def test_engines_import_the_same_rules(self):
        import chip_strategy, decision_backtest, fpl_app, fpl_collect, multiweek_planner
        self.assertIs(multiweek_planner.POSITION_COUNTS, fpl_rules.SQUAD_SHAPE)
        self.assertIs(multiweek_planner.START_LIMITS, fpl_rules.START_LIMITS)
        self.assertIs(chip_strategy.START_LIMITS, fpl_rules.START_LIMITS)
        self.assertIs(decision_backtest.POSITIONS, fpl_rules.SQUAD_SHAPE)
        self.assertIs(fpl_app.selling_price, fpl_rules.selling_price)
        self.assertEqual(fpl_collect.RULES_VERSION, fpl_rules.RULES_VERSION)  # standalone copy in fpl-data

    def test_autosubs_respect_formation_and_keeper_rules(self):
        from season_simulator import autosub_score
        positions = ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"]
        starters = pd.DataFrame({"id": range(11), "name": [f"S{i}" for i in range(11)], "position": positions,
                                 "minutes": 90, "actual_points": 2.0, "role": ["C", "VC"] + [""] * 9})
        bench = pd.DataFrame({"id": range(11, 15), "name": ["B-GK", "B-MID", "B-FWD", "B-DEF"],
                              "position": ["GK", "MID", "FWD", "DEF"], "minutes": 90,
                              "actual_points": [5.0, 7.0, 6.0, 1.0], "bench_order": ["GK", "1", "2", "3"]})
        starters.loc[1, "minutes"] = 0  # a defender misses: only a defender keeps three at the back
        score, _ = autosub_score({"starters": starters, "bench": bench})
        self.assertEqual(score, 10 * 2.0 + 1.0 + 2.0)  # B-DEF comes on (not the better MID), captain doubled
        starters.loc[1, "minutes"], starters.loc[0, "minutes"] = 90, 0  # the keeper misses: only the bench keeper
        score, doubled = autosub_score({"starters": starters, "bench": bench})
        self.assertEqual((score, doubled), (10 * 2.0 + 5.0 + 2.0, "S1"))  # captain S0 absent: vice doubles


if __name__ == "__main__":
    unittest.main()
