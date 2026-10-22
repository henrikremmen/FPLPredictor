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
