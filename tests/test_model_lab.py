from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from model_lab import CatBoostPoints, LightGBMPoints, LGBMRegressor


class ModelLabTests(unittest.TestCase):
    def test_candidate_models_fit_small_mixed_feature_frame(self):
        rows = []
        positions = ["GK", "DEF", "MID", "FWD"]
        for index in range(80):
            row = {
                "target_points": float(index % 7), "position": positions[index % 4],
                "team_name": f"T{index % 5}", "opp_team_name": f"T{(index + 1) % 5}",
                "player_key": f"P{index % 20}",
            }
            from model_lab import NUMERIC
            row.update({column: float((index + offset) % 11)
                        for offset, column in enumerate(NUMERIC) if column != "position"})
            rows.append(row)
        frame = pd.DataFrame(rows)
        cat = CatBoostPoints(iterations=3, depth=2).fit(frame)
        self.assertEqual(len(cat.predict(frame.head())), 5)
        if LGBMRegressor is not None:
            light = LightGBMPoints(estimators=3, leaves=3).fit(frame)
            self.assertEqual(len(light.predict(frame.head())), 5)


if __name__ == "__main__":
    unittest.main()
