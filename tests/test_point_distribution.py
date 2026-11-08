from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from point_distribution import fixture_samples, mixture_quantiles, player_quantiles, sum_by_group


class SyntheticF16Test(unittest.TestCase):
    """The two exact examples from research_2026-11-06 / finding F16."""

    def test_availability_is_a_mixture_not_a_scaling(self):
        # 10 points if available, otherwise 0; 50 % available. Mean 5, but Q90 is 10.
        q10, q50, q90 = mixture_quantiles(np.full((1, 1000), 10.0), [0.5])[0]
        self.assertEqual((q10, q90), (0.0, 10.0))
        self.assertNotEqual(q90, 0.5 * 10)  # what the app did before (F16)
        rows = pd.DataFrame({"player_id": [1], "prediction_q10": [10.0], "prediction_q50": [10.0], "prediction_q90": [10.0]})
        exact = player_quantiles(rows, pd.Series({1: 0.5})).iloc[0]
        self.assertEqual((exact.recommended_q10, exact.recommended_q90, exact.prediction_q90), (0.0, 10.0, 10.0))

    def test_quantile_of_a_sum_is_not_the_sum_of_quantiles(self):
        # Two independent fixtures, 10 points with 20 % probability each, else 0.
        rng = np.random.default_rng(1)
        draws = np.where(rng.random((2, 20000)) < 0.2, 10.0, 0.0)
        per_fixture = np.quantile(draws, 0.9, axis=1, method="inverted_cdf")
        self.assertEqual(per_fixture.tolist(), [10.0, 10.0])  # sum of quantiles would be 20
        _, totals = sum_by_group(draws, [7, 7])
        self.assertEqual(mixture_quantiles(totals, [1.0])[0, 2], 10.0)  # P(total = 20) = 4 % < 10 %


class FixtureDistributionTest(unittest.TestCase):
    def test_single_fixture_reproduces_its_quantiles(self):
        samples = fixture_samples([1.0, 0.0], [2.0, 2.0], [11.5, 6.0])
        q = np.quantile(samples, [0.1, 0.5, 0.9], axis=1).T
        np.testing.assert_allclose(q, [[1, 2, 11.5], [0, 2, 6]], atol=0.05)

    def test_player_totals_and_mixture(self):
        rows = pd.DataFrame({"player_id": [1, 1, 2], "prediction_q10": [1, 1, 1],
                             "prediction_q50": [2, 2, 2], "prediction_q90": [10, 10, 10]})
        result = player_quantiles(rows, pd.Series({1: 1.0, 2: 0.5})).set_index("player_id")
        two, one = result.loc[1], result.loc[2]
        self.assertLess(two.prediction_q90, 20.0)          # not the summed 10 + 10
        self.assertGreater(two.prediction_q90, 10.0)       # but above one fixture's Q90
        self.assertAlmostEqual(one.prediction_q90, 10.0, delta=0.05)
        self.assertEqual(one.recommended_q10, 0.0)         # half the time he is out
        self.assertAlmostEqual(one.recommended_q90, one.prediction_q90 * 0 + np.quantile(
            fixture_samples([1], [2], [10])[0], 0.8), delta=0.05)  # Q90 of mixture = Q80 when a = 0.5
        self.assertEqual(two.recommended_q90, two.prediction_q90)  # fully available: unchanged

    def test_zero_availability_and_negative_points(self):
        draws = np.array([[-1.0] * 100 + [5.0] * 900])
        self.assertEqual(mixture_quantiles(draws, [0.0]).tolist(), [[0.0, 0.0, 0.0]])
        low, mid, high = mixture_quantiles(draws, [0.5])[0]
        self.assertEqual((low, mid, high), (0.0, 0.0, 5.0))  # 5 % below zero, 50 % at zero
        self.assertEqual(mixture_quantiles(draws, [1.0])[0, 0], -1.0)  # 10 % below zero, no extra mass


if __name__ == "__main__":
    unittest.main()
