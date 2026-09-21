from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from component_models import ComponentPointsModel, FEATURES


class ComponentModelTests(unittest.TestCase):
    def frame(self):
        rng = np.random.default_rng(4)
        count = 240
        frame = pd.DataFrame({
            column: rng.normal(size=count) for column in FEATURES if column != "position"
        })
        frame["position"] = np.resize(["GK", "DEF", "MID", "FWD"], count)
        frame["minutes"] = rng.choice([0, 30, 75, 90], count, p=[.2, .1, .2, .5])
        for target, rate in {
            "goals_scored": .1, "assists": .12, "saves": 1.0, "bonus": .25,
            "yellow_cards": .08, "red_cards": .01, "own_goals": .01,
            "penalties_missed": .01, "penalties_saved": .01, "goals_conceded": .8,
            "defensive_contribution": 3.0,
        }.items():
            frame[target] = rng.poisson(rate, count)
        frame["clean_sheets"] = rng.binomial(1, .25, count)
        return frame

    def test_component_mean_and_distribution_are_finite_and_ordered(self):
        frame = self.frame()
        model = ComponentPointsModel(max_iter=3, leaves=3).fit(frame)
        prediction = model.predict(frame.head(12))
        distribution = model.predict_distribution(frame.head(12), draws=150, seed=1)
        self.assertTrue(np.isfinite(prediction).all())
        self.assertTrue((distribution["q10"] <= distribution["q50"]).all())
        self.assertTrue((distribution["q50"] <= distribution["q90"]).all())
        self.assertTrue(((distribution["p10plus"] >= 0) &
                         (distribution["p10plus"] <= 1)).all())


if __name__ == "__main__":
    unittest.main()
