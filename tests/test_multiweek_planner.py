from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpl_app import ImportedTeam
from multiweek_planner import plan_multiweek


def _team() -> ImportedTeam:
    positions = ["GK", "GK", *("DEF" for _ in range(5)),
                 *("MID" for _ in range(5)), *("FWD" for _ in range(3))]
    rows = []
    for index, position in enumerate(positions, start=1):
        rows.append({
            "id": index,
            "name": f"Player {index}",
            "position": position,
            "team_id": (index - 1) // 3 + 1,
            "team": f"T{(index - 1) // 3 + 1}",
            "price": 50,
            "recommended_points": 4.0,
            "decision_points": 4.0,
        })
    # A legal, same-price midfielder from a sixth club is substantially better.
    rows.append({
        "id": 16, "name": "Upgrade", "position": "MID", "team_id": 6,
        "team": "T6", "price": 50, "recommended_points": 10.0,
        "decision_points": 10.0,
    })
    market = pd.DataFrame(rows)
    squad = market.iloc[:15].copy()
    squad["selling_price"] = 50
    weekly = []
    for event in range(5, 9):
        frame = market.copy()
        frame["forecast_event"] = event
        weekly.append(frame)
    return ImportedTeam(
        entry_id=1, event=4, target_event=5, manager_name="Manager",
        team_name="Test", bank=0, free_transfers=1, squad=squad,
        market=market, deadline="", forecast_path=Path("forecast.csv"),
        horizon=4, weekly_market=pd.concat(weekly, ignore_index=True),
    )


class MultiweekPlannerTests(unittest.TestCase):
    def test_roll_can_unlock_two_complementary_transfers_next_week(self):
        team = _team()
        team.market.loc[team.market.id.eq(16), 'price'] = 45
        defender = team.market.iloc[0].copy()
        defender.update({'id': 17, 'name': 'Defensive upgrade', 'position': 'DEF',
                         'team_id': 7, 'price': 55, 'recommended_points': 4., 'decision_points': 4.})
        team.market = pd.concat([team.market, defender.to_frame().T], ignore_index=True)
        rows = []
        for event in [5, 6]:
            frame = team.market.copy()
            frame['forecast_event'] = event
            frame['recommended_points'] = 4.
            frame['decision_points'] = 4.
            if event == 6:
                frame.loc[frame.id.isin([16, 17]), ['recommended_points', 'decision_points']] = 10.
            rows.append(frame)
        team.weekly_market = pd.concat(rows, ignore_index=True)
        result = plan_multiweek(team, weeks=2, force_roll_now=True, allow_hits=False)
        self.assertEqual(result['weeks'][0]['transfers_in'], [])
        self.assertEqual(set(result['weeks'][1]['transfers_in_ids']), {16, 17})
        self.assertEqual(result['weeks'][1]['free_transfers_before'], 2)
        self.assertEqual(result['weeks'][1]['hit'], 0)

    def test_roll_now_allows_a_later_transfer(self):
        result = plan_multiweek(_team(), weeks=3, force_roll_now=True)
        self.assertEqual(result['weeks'][0]['transfers_in'], [])
        self.assertIn('Upgrade', result['weeks'][1]['transfers_in'])
        self.assertEqual(result['weeks'][1]['free_transfers_before'], 2)

    def test_small_gain_is_outweighed_by_retained_transfer(self):
        team = _team()
        team.weekly_market.loc[team.weekly_market.id.eq(16), ['recommended_points', 'decision_points']] = 4.5
        result = plan_multiweek(team, weeks=1)
        self.assertEqual(result['weeks'][0]['transfers_in'], [])
        self.assertEqual(result['free_transfers_after_horizon'], 2)

    def test_transfer_at_five_free_transfers_does_not_lose_reserve(self):
        team = _team()
        team.free_transfers = 5
        team.weekly_market.loc[team.weekly_market.id.eq(16), ['recommended_points', 'decision_points']] = 4.5
        result = plan_multiweek(team, weeks=1)
        self.assertEqual(result['weeks'][0]['transfers_in'], ['Upgrade'])
        self.assertEqual(result['free_transfers_after_horizon'], 5)

    def test_finds_upgrade_and_rolls_free_transfers(self):
        result = plan_multiweek(_team(), weeks=4)

        self.assertEqual(len(result["weeks"]), 4)
        self.assertEqual(result["weeks"][0]["transfers_in"], ["Upgrade"])
        self.assertEqual(len(result["weeks"][0]["transfers_out"]), 1)
        self.assertEqual(result["weeks"][0]["paid_transfers"], 0)
        self.assertTrue(all(week["paid_transfers"] == 0 for week in result["weeks"]))
        self.assertTrue(result["global_optimum"])

    def test_can_forbid_points_hits_for_conservative_comparison(self):
        team = _team()
        team.free_transfers = 0
        result = plan_multiweek(team, weeks=1, allow_hits=False)
        self.assertFalse(result["allow_hits"])
        self.assertEqual(result["weeks"][0]["paid_transfers"], 0)
        self.assertEqual(result["weeks"][0]["transfers_in"], [])


if __name__ == "__main__":
    unittest.main()


class BenchWeightTests(unittest.TestCase):
    """P1: the bench has a small value in FPL bench order; it never buys points for the XI."""

    def test_bench_order_and_value(self):
        from dataclasses import replace
        team = _team()
        weekly = team.weekly_market.copy()
        weekly.loc[weekly.id.eq(15), ["recommended_points", "decision_points"]] = 3.0  # weakest forward
        team = replace(team, weekly_market=weekly, horizon=1)
        plan = plan_multiweek(team, weeks=1, allow_hits=False)
        week = plan["weeks"][0]
        self.assertEqual(len(week["bench_ids"]), 4)
        self.assertEqual(team.market.set_index("id").loc[week["bench_ids"][0], "position"], "GK")
        self.assertNotIn(week["bench_ids"][0], week["starter_ids"])
        self.assertEqual(plan["bench_weights"], [0.03, 0.12, 0.06, 0.03])
        self.assertGreater(week["bench_value"], 0)
        off = plan_multiweek(replace(team, bench_weights=(0, 0, 0, 0)), weeks=1, allow_hits=False)
        self.assertEqual(off["weeks"][0]["bench_value"], 0)
        self.assertEqual(off["weeks"][0]["projected_points"], week["projected_points"])  # XI score unchanged

    def test_lineup_total_with_bench(self):
        from fpl_app import _lineup_total_records
        records = [(1, "GK", 5), (2, "GK", 2)] + [(10 + i, "DEF", 4 - i * .1) for i in range(5)] + \
                  [(20 + i, "MID", 5 - i * .1) for i in range(5)] + [(30 + i, "FWD", 6 - i) for i in range(3)]
        plain = _lineup_total_records(records)
        weighted = _lineup_total_records(records, (0.1, 0.5, 0.25, 0.1))
        self.assertGreater(weighted, plain)
        self.assertLess(weighted - plain, 0.1 * 2 + 0.5 * 5 + 0.25 * 5 + 0.1 * 5)


def _chip_team(expires=19, star_event=6, star_points=12.0):
    from dataclasses import replace
    team = _team()
    weekly = team.weekly_market.copy()
    star = weekly.id.eq(1 + 12) & weekly.forecast_event.eq(star_event)  # a forward with a huge week
    weekly.loc[star, ["recommended_points", "decision_points"]] = star_points
    status = {chip: {"available": True, "expires_after_gw": expires} for chip in
              ("bench_boost", "triple_captain", "free_hit", "wildcard")}
    return replace(team, weekly_market=weekly, chip_status=status, horizon=4)


class ChipPlanTests(unittest.TestCase):
    """P2: chips inside the multiweek MILP."""

    def test_triple_captain_on_the_big_week_and_one_chip_per_week(self):
        plan = plan_multiweek(_chip_team(), weeks=4, chips=True, allow_hits=False)
        chips = {w["event"]: w["chip"] for w in plan["weeks"] if w["chip"]}
        self.assertEqual(chips.get(6), "triple_captain")
        self.assertLessEqual(max(list(chips.values()).count(c) for c in chips.values()), 1)  # each chip once
        self.assertEqual(len(chips), len(set(chips)))  # at most one chip per Gameweek
        week6 = next(w for w in plan["weeks"] if w["event"] == 6)
        self.assertEqual(week6["captain"], "Player 13")

    def test_chips_expire_after_their_last_gameweek(self):
        plan = plan_multiweek(_chip_team(expires=5), weeks=4, chips=True, allow_hits=False)
        self.assertTrue(all(w["chip"] is None for w in plan["weeks"] if w["event"] > 5))

    def test_chips_off_by_default_and_calendar_prices_the_alternative(self):
        from multiweek_planner import plan_with_context
        team = _chip_team()
        self.assertTrue(all(w["chip"] is None for w in plan_multiweek(team, weeks=4, allow_hits=False)["weeks"]))
        context = plan_with_context(team, chips=True, weeks=4, allow_hits=False)
        entry = next(c for c in context["chip_calendar"] if c["chip"] == "triple_captain")
        self.assertEqual(entry["event"], 6)
        self.assertGreater(entry["gain_over_alternative"], 0)  # 12 vs the next best captain week


class RequirementTests(unittest.TestCase):
    """P4: future requirements are hard constraints with an opportunity cost."""

    def test_own_by_and_sell_in_with_cost(self):
        from multiweek_planner import plan_with_context
        team = _team()
        plan = plan_with_context(team, weeks=3, allow_hits=False,
                                 requirements=({"kind": "sell_in", "player_id": 8, "event": 6},))
        week6 = next(w for w in plan["weeks"] if w["event"] == 6)
        self.assertIn(8, week6["transfers_out_ids"])
        self.assertNotIn(8, week6["squad_ids"])
        self.assertGreaterEqual(plan["requirement_costs"][0]["cost"], 0)
        bought = plan_with_context(team, weeks=3, allow_hits=False,
                                   requirements=({"kind": "own_by", "player_id": 16, "event": 5},))
        self.assertIn(16, bought["weeks"][0]["squad_ids"])

    def test_club_and_position_limits_and_unknown_requirement(self):
        team = _team()
        plan = plan_multiweek(team, weeks=2, allow_hits=False,
                              requirements=({"kind": "max_position", "position": "FWD", "limit": 1},))
        positions = team.market.set_index("id").position
        self.assertTrue(all(sum(positions[i] == "FWD" for i in w["starter_ids"]) <= 1 for w in plan["weeks"]))
        with self.assertRaises(Exception):
            plan_multiweek(team, weeks=2, requirements=({"kind": "teleport"},))


class BenchBoostTests(unittest.TestCase):
    def test_bench_boost_plays_all_fifteen(self):
        from dataclasses import replace
        team = _chip_team(star_points=4.0)
        weekly = team.weekly_market.copy()
        big = weekly.forecast_event.eq(7)  # a double Gameweek for everyone: the bench is worth most here
        weekly.loc[big, ["recommended_points", "decision_points"]] *= 3
        plan = plan_multiweek(replace(team, weekly_market=weekly), weeks=4, chips=True, allow_hits=False)
        week7 = next(w for w in plan["weeks"] if w["event"] == 7)
        self.assertEqual(week7["chip"], "bench_boost")
        self.assertEqual(len(week7["starter_ids"]), 15)
        self.assertEqual(week7["bench"], [])
