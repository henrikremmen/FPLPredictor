from pathlib import Path
import json
import sys
import tempfile
import unittest
import unittest.mock

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import criterion_v2
from criterion_v2 import CRITERION_V2, applies, cohort, pinball, rounds_needed, summarize, synthetic_squads


class CohortTest(unittest.TestCase):
    def test_cohort_uses_only_frozen_information(self):
        predictions = pd.DataFrame({"model": ["incumbent"] * 4 + ["other"], "player_id": [1, 2, 3, 3, 4],
                                    "prediction": [5.0, 0.1, 0.1, 0.1, 9.0],
                                    "p_zero_minutes": [0.1, 0.9, 0.6, 0.6, 0.0]})
        selections = pd.DataFrame({"player_id": [2]})
        with unittest.mock.patch.dict(CRITERION_V2["cohort"], {"top_n": 1}):
            players = cohort(predictions, selections)
        # 1: top by the reference; 3: two fixtures, P(appear) = 1 − 0.36 ≥ 0.5; 2: in a squad; 4 only in another model
        self.assertEqual(players, {1, 2, 3})


class MetricsTest(unittest.TestCase):
    def test_pinball_is_zero_at_a_point_and_grows_outside(self):
        self.assertEqual(pinball([2.0], np.array([[2.0, 2.0, 2.0]]))[0], 0.0)
        self.assertAlmostEqual(pinball([10.0], np.array([[0.0, 1.0, 4.0]]))[0], (1.0 + 4.5 + 5.4) / 3)

    def test_primary_needs_eight_rounds_negative_interval_and_guard(self):
        rows = []
        for r in range(8):
            for player in range(20):
                base = 1.0 + 0.1 * ((player + r) % 5)
                rows += [{"round": r, "player_id": player, "model": "incumbent", "abs_error": base, "pinball": 0.5},
                         {"round": r, "player_id": player, "model": CRITERION_V2["primary_challenger"],
                          "abs_error": base - 0.05 - 0.01 * (r % 3), "pinball": 0.49},
                         {"round": r, "player_id": player, "model": "noise", "abs_error": base + (0.02 if r % 2 else -0.02),
                          "pinball": 0.5}]
        result = {row["model"]: row for row in summarize(pd.DataFrame(rows))}
        primary = result[CRITERION_V2["primary_challenger"]]
        self.assertEqual((primary["role"], primary["rounds"], primary["criterion_met"]), ("primary", 8, True))
        self.assertLess(primary["mae_diff_ci"][1], 0)
        self.assertFalse(result["noise"]["criterion_met"])
        self.assertIsNotNone(result["noise"]["p_holm"])
        seven = pd.DataFrame([r for r in rows if r["round"] < 7])
        self.assertFalse({r["model"]: r for r in summarize(seven)}[CRITERION_V2["primary_challenger"]]["criterion_met"])

    def test_power_and_registration(self):
        self.assertEqual(rounds_needed(0.032, 0.032), 8)
        self.assertEqual(rounds_needed(13, 2), 332)  # v1: team points, SD 13
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "manifest.json").write_text(json.dumps({"started_at": "2026-11-06 14:09:30+00:00"}))
            self.assertFalse(applies(Path(tmp)))  # GW10 was locked before v2
            (Path(tmp) / "manifest.json").write_text(json.dumps({"started_at": "2026-11-20 06:00:00+00:00"}))
            self.assertTrue(applies(Path(tmp)))


class SyntheticSquadTest(unittest.TestCase):
    def test_squads_are_legal_and_reproducible(self):
        elements = [{"id": i, "element_type": 1 + i % 4, "team": i % 20, "now_cost": 45 + i % 50,
                     "selected_by_percent": str(i % 30), "can_select": True} for i in range(400)]
        squads = synthetic_squads(elements, count=20)
        self.assertEqual(squads, synthetic_squads(elements, count=20))
        by_id = {e["id"]: e for e in elements}
        for squad in squads:
            types = [by_id[i]["element_type"] for i in squad]
            self.assertEqual([types.count(t) for t in (1, 2, 3, 4)], [2, 5, 5, 3])
            self.assertLessEqual(max(pd.Series([by_id[i]["team"] for i in squad]).value_counts()), 3)
            self.assertLessEqual(sum(by_id[i]["now_cost"] for i in squad), 1000)
            self.assertEqual(len(set(squad)), 15)


if __name__ == "__main__":
    unittest.main()
