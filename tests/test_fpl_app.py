from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpl_app import (
    AppError,
    ImportedTeam,
    estimate_free_transfers,
    optimal_lineup,
    parse_entry_reference,
    recommend_transfers,
    refresh_forecast,
    selling_price,
    build_market,
    apply_risk_profile,
    chip_inventory,
)


def player(player_id, name, position, team, points, price=50, selling=None):
    return {
        "id": player_id,
        "name": name,
        "position": position,
        "team_id": team,
        "team": f"T{team}",
        "price": price,
        "selling_price": price if selling is None else selling,
        "purchase_price": price,
        "recommended_points": float(points),
        "prediction": float(points),
        "availability": 1.0,
        "planned_fixtures": 1,
        "status": "a",
        "news": "",
        "opponent": "T20 (H)",
    }


class FPLAppTests(unittest.TestCase):
    def test_multiweek_market_sums_frozen_forecasts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            path = parent / 'forecast.csv'
            pd.DataFrame({'GW':[5], 'player_id':[1], 'prediction':[2.0],
                          'planned_fixtures':[1], 'prediction_q10':[0.0],
                          'prediction_q50':[2.0], 'prediction_q90':[6.0]}).to_csv(path,index=False)
            pd.DataFrame({'GW':[5,6], 'player_id':[1,1], 'prediction':[2.0,3.0],
                          'planned_fixtures':[1,1], 'prediction_q10':[0.0,0.0],
                          'prediction_q50':[2.0,3.0], 'prediction_q90':[6.0,7.0]
                          }).to_csv(parent/'horizon_forecast.csv',index=False)
            bootstrap={'teams':[{'id':1,'short_name':'AAA'},{'id':2,'short_name':'BBB'}],
                       'elements':[{'id':1,'web_name':'One','element_type':3,'team':1,
                                    'now_cost':50,'status':'a','news':'',
                                    'chance_of_playing_next_round':None}]}
            fixtures=[{'event':5,'team_h':1,'team_a':2},{'event':6,'team_h':2,'team_a':1}]
            market=build_market(bootstrap,fixtures,path,5,horizon=2)
            self.assertEqual(market.prediction.iloc[0],5.0)
            self.assertEqual(market.planned_fixtures.iloc[0],2)
            self.assertIn('GW6:',market.opponent.iloc[0])
            self.assertEqual(market.point_range_q10_q90.iloc[0], '0.0–13.0')

    def setUp(self):
        specs = [
            (1, "GK1", "GK", 1, 4), (2, "GK2", "GK", 2, 2),
            (3, "D1", "DEF", 3, 6), (4, "D2", "DEF", 4, 5),
            (5, "D3", "DEF", 5, 4), (6, "D4", "DEF", 6, 1),
            (7, "D5", "DEF", 7, 0),
            (8, "M1", "MID", 8, 10), (9, "M2", "MID", 9, 9),
            (10, "M3", "MID", 10, 8), (11, "M4", "MID", 11, 7),
            (12, "M5", "MID", 12, 3),
            (13, "F1", "FWD", 13, 8), (14, "F2", "FWD", 14, 7),
            (15, "F3", "FWD", 15, 2),
        ]
        self.squad = pd.DataFrame(player(*spec) for spec in specs)
        additions = [
            player(16, "M6", "MID", 16, 12, price=55),
            player(17, "D6", "DEF", 3, 9, price=55),
            player(18, "F4", "FWD", 16, 9, price=55),
        ]
        self.market = pd.concat([self.squad, pd.DataFrame(additions)], ignore_index=True)
        self.team = ImportedTeam(1, 4, 5, "Manager", "Team", 5, 2,
                                 self.squad, self.market, "deadline", Path("forecast.csv"))

    def test_parse_reference(self):
        self.assertEqual(parse_entry_reference(
            "https://fantasy.premierleague.com/en/entry/5139814/event/4"
        ), (5139814, 4))
        self.assertEqual(parse_entry_reference("5139814"), (5139814, None))
        with self.assertRaises(AppError):
            parse_entry_reference("not-a-team")

    def test_selling_price_rule(self):
        self.assertEqual(selling_price(50, 54), 52)
        self.assertEqual(selling_price(50, 53), 51)
        self.assertEqual(selling_price(50, 47), 47)

    def test_free_transfer_estimate(self):
        history = {"current": [
            {"event": 1, "event_transfers": 0},
            {"event": 2, "event_transfers": 0},
            {"event": 3, "event_transfers": 0},
            {"event": 4, "event_transfers": 2},
        ], "chips": []}
        self.assertEqual(estimate_free_transfers(history, 4), 2)

    def test_chip_inventory_resets_by_half_and_blocks_consecutive_free_hit(self):
        history = {"chips": [
            {"name": "wildcard", "event": 6},
            {"name": "freehit", "event": 19},
        ]}
        first_half = chip_inventory(history, 10)
        self.assertFalse(first_half["wildcard"]["available"])
        second_half = chip_inventory(history, 20)
        self.assertTrue(second_half["wildcard"]["available"])
        self.assertFalse(second_half["free_hit"]["available"])
        self.assertTrue(second_half["free_hit"]["blocked_consecutive"])

    def test_lineup_is_legal_and_captain_is_best(self):
        result = optimal_lineup(self.squad)
        counts = result["starters"]["position"].value_counts()
        self.assertEqual(len(result["starters"]), 11)
        self.assertGreaterEqual(counts["DEF"], 3)
        self.assertGreaterEqual(counts["MID"], 2)
        self.assertGreaterEqual(counts["FWD"], 1)
        captain = result["starters"].query("role == 'C'").iloc[0]
        self.assertEqual(captain["name"], "M1")
        self.assertEqual(result["bench"]["bench_order"].tolist(), ["GK", "1", "2", "3"])

    def test_risk_profile_changes_decision_score_without_changing_expectation(self):
        market = pd.DataFrame({
            "recommended_points": [4.0, 4.0],
            "recommended_q10": [0.0, 2.0],
            "recommended_q90": [10.0, 6.0],
        })
        stable = apply_risk_profile(market, "stable")
        upside = apply_risk_profile(market, "upside")
        self.assertEqual(stable["recommended_points"].tolist(), [4.0, 4.0])
        self.assertGreater(stable.decision_points.iloc[1], stable.decision_points.iloc[0])
        self.assertGreater(upside.decision_points.iloc[0], upside.decision_points.iloc[1])

    def test_lineup_uses_profile_score_for_captain(self):
        squad = self.squad.copy()
        squad["decision_points"] = squad["recommended_points"]
        squad.loc[squad["name"].eq("M2"), "decision_points"] = 20.0
        result = optimal_lineup(squad)
        self.assertEqual(result["starters"].query("role == 'C'").iloc[0]["name"], "M2")
        self.assertNotEqual(result["projected_total"], result["expected_total"])

    def test_transfer_plan_respects_position_budget_and_club_limit(self):
        suggestions = recommend_transfers(self.team, number=1)
        self.assertFalse(suggestions.empty)
        best = suggestions.iloc[0]
        self.assertEqual(best["out"], "M5")
        self.assertEqual(best["in"], "M6")
        self.assertEqual(best["hit"], 0)
        # D6 can only replace one of the three existing T3 defenders.
        crowded = self.squad.copy()
        crowded.loc[crowded["id"].isin([4, 5]), "team_id"] = 3
        crowded.loc[crowded["id"].isin([4, 5]), "team"] = "T3"
        team = ImportedTeam(1, 4, 5, "Manager", "Team", 5, 2, crowded,
                            self.market, "deadline", Path("forecast.csv"))
        d6_plans = recommend_transfers(team, 1).query("`in` == 'D6'")
        self.assertTrue(d6_plans["out"].isin(["D1", "D2", "D3"]).all())

    def test_one_transfer_search_is_exhaustive_even_with_tiny_pool_setting(self):
        market = pd.concat([
            self.market,
            pd.DataFrame([player(19, "Premium", "MID", 17, 30, price=100)]),
        ], ignore_index=True)
        team = ImportedTeam(1, 4, 5, "Manager", "Team", 5, 2,
                            self.squad, market, "deadline", Path("forecast.csv"))
        suggestions = recommend_transfers(team, number=1, candidate_pool=1)
        self.assertFalse(suggestions.empty)
        self.assertEqual(suggestions.iloc[0]["in"], "M6")

    def test_best_two_transfer_plan_is_globally_optimized(self):
        self.team.bank = 15
        suggestions = recommend_transfers(self.team, number=2, candidate_pool=1)
        self.assertFalse(suggestions.empty)
        self.assertTrue(bool(suggestions.iloc[0]["is_global_optimum"]))
        self.assertEqual(len(suggestions.iloc[0]["out"].split(" + ")), 2)
        self.assertEqual(len(suggestions.iloc[0]["in"].split(" + ")), 2)

    def test_no_affordable_two_transfer_plan_returns_empty(self):
        suggestions = recommend_transfers(self.team, number=2)
        self.assertTrue(suggestions.empty)

    def test_exact_optimizer_supports_five_transfers_and_hits(self):
        additions = pd.DataFrame([
            player(20, "GK3", "GK", 18, 6, price=50),
            player(21, "D7", "DEF", 19, 8, price=50),
        ])
        market = pd.concat([self.market, additions], ignore_index=True)
        team = ImportedTeam(
            1, 4, 5, "Manager", "Team", 100, 2,
            self.squad, market, "deadline", Path("forecast.csv"),
        )
        suggestions = recommend_transfers(team, number=5)
        self.assertEqual(len(suggestions), 1)
        best = suggestions.iloc[0]
        self.assertEqual(len(best["out"].split(" + ")), 5)
        self.assertEqual(len(best["in"].split(" + ")), 5)
        self.assertEqual(best["hit"], 12)
        self.assertTrue(bool(best["is_global_optimum"]))

    def test_refresh_rejects_failed_capture_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)
            (capture / "manifest.json").write_text(
                '{"status":"failed","forecast_status":"not_generated","error":"API down"}'
            )
            with patch("capture_fpl.run", return_value=capture):
                with self.assertRaisesRegex(AppError, "API down"):
                    refresh_forecast(Path(temporary))

    def test_refresh_accepts_complete_frozen_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)
            (capture / "manifest.json").write_text(
                '{"status":"complete","forecast_status":"experimental_frozen"}'
            )
            with patch("capture_fpl.run", return_value=capture):
                refresh_forecast(Path(temporary))


if __name__ == "__main__":
    unittest.main()
