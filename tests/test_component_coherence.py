import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from component_models import CoherentComponentPointsModel, COUNT_TARGETS


class FixedComponents(CoherentComponentPointsModel):
    has_defcon = True

    def predict_components(self, data):
        n = len(data)
        result = {name: np.full(n, .1) for name in COUNT_TARGETS}
        result.update(minutes_probability=np.tile([.3, .3, .2, .2], (n, 1)),
                      clean_sheet_probability=np.full(n, .2),
                      saves=np.full(n, 2.), bonus=np.full(n, 1.5),
                      goals_conceded=np.full(n, 2.), defensive_contribution=np.full(n, 8.))
        return result


class ComponentCoherenceTests(unittest.TestCase):
    def test_missing_training_labels_are_not_converted_to_zero(self):
        with self.assertRaisesRegex(ValueError, "minutes"):
            CoherentComponentPointsModel().fit(pd.DataFrame({"minutes": [np.nan]}))

    def test_no_appearance_cannot_generate_scoring_events(self):
        model = FixedComponents()
        old = model.predict_components
        def components(data):
            c = old(data)
            c["minutes_probability"][:] = [1, 0, 0, 0]
            return c
        model.predict_components = components
        data = pd.DataFrame({"position": ["GK", "DEF"]})
        np.testing.assert_array_equal(model.predict(data), [0., 0.])
        np.testing.assert_array_equal(model.predict_distribution(data, draws=1000)["mean"], [0., 0.])

    def test_analytic_contributions_match_monte_carlo(self):
        data = pd.DataFrame({"position": ["GK", "DEF", "MID", "FWD"]})
        model = FixedComponents()
        contributions = model.point_contributions(data)
        np.testing.assert_allclose(contributions.sum(axis=1), model.predict(data))
        samples = model.predict_distribution(data, draws=150000, seed=42)
        np.testing.assert_allclose(model.predict(data), samples["mean"], atol=.045, rtol=0)
        self.assertTrue((contributions.bonus <= 3 * .7).all())

    def test_conceded_deduction_applies_below_sixty_minutes(self):
        model = FixedComponents()
        old = model.predict_components
        def components(data):
            c = old(data)
            c["minutes_probability"][:] = [0, 1, 0, 0]
            return c
        model.predict_components = components
        data = pd.DataFrame({"position": ["DEF"]})
        self.assertLess(model.point_contributions(data).goals_conceded.iloc[0], 0)
        np.testing.assert_allclose(model.predict(data),
            model.predict_distribution(data, draws=150000)["mean"], atol=.045, rtol=0)
