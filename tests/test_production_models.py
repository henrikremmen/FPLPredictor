from pathlib import Path
import sys
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from improved_models import ProductionModel


class ProductionModelTests(unittest.TestCase):
    def test_points_and_probability_components_are_separate(self):
        class Points:
            def predict(self, rows):
                return np.full(len(rows), 4.0)

        class Minutes:
            def probabilities(self, rows):
                return np.tile([0.1, 0.2, 0.7], (len(rows), 1))

        class Quantiles:
            def predict_quantiles(self, rows):
                return np.tile([0.0, 3.0, 8.0], (len(rows), 1))

        model = ProductionModel(Points(), Minutes(), Quantiles())
        rows = pd.DataFrame({"x": [1, 2]})
        self.assertEqual(model.predict(rows).tolist(), [4.0, 4.0])
        self.assertEqual(model.probabilities(rows)[:, 2].tolist(), [0.7, 0.7])
        self.assertEqual(model.quantiles(rows)[:, 2].tolist(), [8.0, 8.0])

    def test_wrapper_has_stable_joblib_round_trip(self):
        # Built-in objects are sufficient here: this test guards the wrapper's
        # module identity, which caused a production artifact to deserialize as
        # __main__.ProductionModel when the builder was run as a script.
        model = ProductionModel({"component": "points"}, {"component": "minutes"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.joblib"
            joblib.dump(model, path)
            loaded = joblib.load(path)
        self.assertIsInstance(loaded, ProductionModel)
        self.assertEqual(loaded.points_model["component"], "points")


if __name__ == "__main__":
    unittest.main()
