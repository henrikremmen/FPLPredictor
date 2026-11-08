"""P5: assumptions, plan A/B against holding, the tipping point and robustness."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenarios import apply_overrides, breakpoint, compare_plans, robustness
from test_multiweek_planner import _team


def team():
    base = _team()
    with_columns = lambda f: f.assign(prediction=f.recommended_points, availability=1.0,
                                      recommended_q10=0.0, recommended_q50=f.recommended_points,
                                      recommended_q90=f.recommended_points * 2)
    return replace(base, market=with_columns(base.market), weekly_market=with_columns(base.weekly_market), horizon=2)


class ScenarioTests(unittest.TestCase):
    def test_assumption_replaces_availability_everywhere_and_is_in_the_cache_key(self):
        from result_cache import cache_key
        base = team()
        doubt = apply_overrides(base, [{"player_id": 16, "chance": 0.25}])
        self.assertEqual(doubt.weekly_market.set_index(["id", "forecast_event"]).recommended_points[(16, 5)], 2.5)
        self.assertEqual(doubt.scenario_overrides, {"16": 0.25})
        self.assertNotEqual(cache_key(base, "plan"), cache_key(doubt, "plan"))
        self.assertEqual(base.weekly_market.set_index(["id", "forecast_event"]).recommended_points[(16, 5)], 10.0)
        with self.assertRaises(Exception):
            apply_overrides(base, [{"player_id": 999, "chance": 0.5}])

    def test_hold_plan_a_and_b_on_the_same_inputs(self):
        plans = compare_plans(team(), weeks=2)
        names = [p["name"] for p in plans]
        self.assertEqual(names[:2], ["Hold", "Plan A"])
        self.assertEqual(plans[0]["first_week_in"], [])
        self.assertIn("Upgrade", plans[1]["first_week_in"])
        self.assertGreater(plans[1]["gain_vs_hold"], 0)
        if len(plans) == 3:
            self.assertNotIn("Upgrade", plans[2]["first_week_in"])
        shares = robustness(team(), plans, scenarios=20, seed=7)
        self.assertEqual(shares, robustness(team(), plans, scenarios=20, seed=7))  # the seed reproduces it
        self.assertAlmostEqual(sum(shares["chosen_share"].values()), 1.0, places=6)
        self.assertEqual(shares["seed"], 7)

    def test_tipping_point_for_the_signing(self):
        result = breakpoint(team(), 16, weeks=2, steps=7)
        self.assertIsNotNone(result["threshold"])
        self.assertTrue(0 < result["threshold"] < 1)
        self.assertIn("Upgrade", result["above"])
        self.assertEqual(result["below"], "hold")
        self.assertIn("falls below", result["message"])


if __name__ == "__main__":
    unittest.main()
