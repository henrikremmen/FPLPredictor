from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpl_app import ImportedTeam
from strategy_advisor import _transfer_warnings, build_strategy_advice


def player(player_id, position, points, *, owned=True, ownership=12.0,
           price_change=0.0, projected=0.0, availability=1.0, status="a"):
    return {
        "id": player_id, "name": f"P{player_id}", "position": position,
        "team_id": player_id, "team": f"T{player_id}", "price": 50,
        "selling_price": 50, "recommended_points": float(points),
        "decision_points": float(points), "planned_fixtures": 1,
        "opponent": "OPP (H)", "status": status, "news": "",
        "availability": availability, "selected_by_percent": ownership,
        "price_change_percent": price_change,
        "price_change_projected_percent": projected,
        "price_change_likelihood": 5 if projected > 0 else -5 if projected < 0 else 0,
        "can_select": True, "can_transact": True,
    }


class StrategyAdvisorTests(unittest.TestCase):
    def decision_team(self):
        from test_multiweek_planner import _team
        team = _team()
        team.lineup_squad = team.squad
        return team

    def test_small_bench_upgrade_rolls_and_compares_future_transfers(self):
        team = self.decision_team()
        calls = []
        def planner(_team, **kwargs):
            calls.append(kwargs)
            roll = kwargs.get('force_roll_now', False)
            return {'weeks': [{'transfers_out': [] if roll else ['Player 8'],
                'transfers_in': [] if roll else ['Upgrade'], 'starters': ['Player 9'],
                'projected_points': 50, 'hit': 0}],
                'discounted_objective_points': 100 if roll else 101,
                'global_optimum': True}
        advice = build_strategy_advice(team, planner=planner)
        self.assertEqual(advice['transfer']['decision'], 'ROLL')
        comparison = advice['transfer']['roll_comparison']
        self.assertEqual(comparison['next_gw_lineup_gain'], 0)
        self.assertEqual(comparison['incoming_bench_now'], ['Upgrade'])
        self.assertTrue(calls[-1]['force_roll_now'])

    def test_clear_lineup_upgrade_is_not_suppressed(self):
        team = self.decision_team()
        def planner(_team, **kwargs):
            roll = kwargs.get('force_roll_now', False)
            return {'weeks': [{'transfers_out': [] if roll else ['Player 8'],
                'transfers_in': [] if roll else ['Upgrade'],
                'starters': ['Player 8'] if roll else ['Upgrade'],
                'projected_points': 50 if roll else 56, 'hit': 0}],
                'discounted_objective_points': 100 if roll else 110,
                'global_optimum': True}
        advice = build_strategy_advice(team, planner=planner)
        self.assertEqual(advice['transfer']['decision'], 'TRANSFER')
        self.assertEqual(advice['transfer']['roll_comparison']['displaced_starters'], ['Player 8'])

    def test_large_apparent_gain_without_solver_proof_is_cautious(self):
        team = self.decision_team()
        def planner(_team, **kwargs):
            roll = kwargs.get('force_roll_now', False)
            return {'weeks': [{'transfers_out': [] if roll else ['Player 8'],
                'transfers_in': [] if roll else ['Upgrade'], 'starters': [], 'hit': 0}],
                'discounted_objective_points': 100 if roll else 110,
                'objective_upper_bound': 120, 'global_optimum': False}
        advice = build_strategy_advice(team, planner=planner)
        self.assertEqual(advice['transfer']['decision'], 'ROLL')
        self.assertEqual(advice['transfer']['roll_comparison']['gain_lower_bound'], -10)

    def test_selected_eight_week_horizon_is_not_silently_capped(self):
        team = self.decision_team()
        team.horizon = 8
        team.weekly_market = pd.concat([team.market.assign(forecast_event=i) for i in range(5, 13)])
        def planner(_team, **kwargs):
            self.assertEqual(kwargs['weeks'], 8)
            return {'weeks': [{'transfers_out': [], 'hit': 0}], 'global_optimum': True}
        self.assertEqual(build_strategy_advice(team, planner=planner)['transfer']['horizon'], 8)

    def test_transfer_warnings_surface_model_disagreement_and_solver_status(self):
        row = player(1, "DEF", 2.0, price_change=105, projected=125)
        row["ep_next"] = 2.8
        warnings = _transfer_warnings(pd.DataFrame([row]), ["P1"], [], False)
        self.assertEqual(len(warnings), 3)
        self.assertTrue(any("global optimality" in warning for warning in warnings))
        self.assertTrue(any("FPL's own" in warning for warning in warnings))
        self.assertTrue(any("price rise" in warning for warning in warnings))

    def test_builds_roll_decision_health_captain_and_price_radar(self):
        positions = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
        squad = pd.DataFrame([
            player(index, position, 20 - index,
                   price_change=-90 if index == 1 else 0,
                   projected=-120 if index == 1 else 0,
                   availability=.5 if index == 3 else 1,
                   status="d" if index == 3 else "a")
            for index, position in enumerate(positions, 1)
        ])
        additions = pd.DataFrame([
            player(16, "MID", 11, ownership=5, price_change=95, projected=130),
            player(17, "DEF", 8, ownership=4),
        ])
        market = pd.concat([squad, additions], ignore_index=True)
        weekly = pd.concat([
            market.assign(forecast_event=5),
            market.assign(forecast_event=6),
        ], ignore_index=True)
        chips = {
            chip: {"available": True, "expires_after_gw": 19}
            for chip in ["wildcard", "free_hit", "triple_captain", "bench_boost"]
        }
        team = ImportedTeam(
            1, 4, 5, "Manager", "Team", 5, 2, squad, market,
            "2026-09-20T10:00:00Z", Path("forecast.csv"), horizon=2,
            lineup_squad=squad, weekly_market=weekly, chip_status=chips,
            overall_points=250, overall_rank=1000, team_value=1012,
        )

        def planner(_team, **_kwargs):
            return {
                "weeks": [{
                    "event": 5, "transfers_out": [], "transfers_in": [],
                    "free_transfers_before": 2, "hit": 0, "bank": .5,
                }],
                "global_optimum": True,
            }

        advice = build_strategy_advice(
            team, planner=planner,
            now=datetime(2026, 9, 18, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(advice["transfer"]["decision"], "ROLL")
        self.assertEqual(advice["manager_context"]["team_value"], 101.2)
        self.assertEqual(advice["captain"]["captain"]["name"], "P1")
        self.assertTrue(advice["squad_health"]["flagged_starters"])
        self.assertEqual(advice["price_alerts"]["owned_at_risk"][0]["name"], "P1")
        self.assertEqual(advice["price_alerts"]["targets_rising"][0]["name"], "P16")
        self.assertEqual(advice["watchlists"]["differentials"][0]["name"], "P16")
        self.assertEqual(advice["actions"][0]["category"], "team_news")


if __name__ == "__main__":
    unittest.main()
