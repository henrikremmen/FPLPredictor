from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cup_minutes import attach_cup_minutes, load_appearances


class CupMinutesTest(unittest.TestCase):
    def test_counts_only_earlier_appearances_within_window_by_code(self):
        appearances = pd.DataFrame({"code": [10, 10, 10, 20], "minutes": [90, 30, 60, 90],
                                    "kickoff": pd.to_datetime(["2026-10-01", "2026-10-10", "2026-10-20", "2026-10-18"], utc=True)})
        rows = pd.DataFrame({"season": "2026-27", "player_id": [1, 2, 3]})
        codes = pd.DataFrame({"season": "2026-27", "player_id": [1, 2], "code": [10, 20]})
        kickoff = pd.Series(pd.to_datetime(["2026-10-15", "2026-10-18", "2026-10-15"], utc=True))
        result = attach_cup_minutes(rows, appearances, codes, kickoff)
        self.assertEqual(result.non_pl_minutes_7d.tolist()[:2], [30.0, 0.0])  # same-time match does not count
        self.assertEqual(result.non_pl_minutes_14d.tolist()[:2], [120.0, 0.0])
        self.assertEqual(result.days_since_non_pl.tolist()[:2], [5.0, 30.0])
        self.assertTrue(np.isnan(result.non_pl_minutes_7d.iloc[2]))  # no code -> unknown, not zero

    def test_load_joins_finished_matches_to_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "2026-27"
            (folder / "EFL Cup/GW4").mkdir(parents=True)
            pd.DataFrame({"player_id": [5, 6], "player_code": [50, 60]}).to_csv(folder / "players.csv", index=False)
            pd.DataFrame({"match_id": ["a", "b"], "kickoff_time": ["2026-09-23T19:00:00Z", "2026-10-28T19:00:00Z"],
                          "finished": [True, False]}).to_csv(folder / "EFL Cup/GW4/matches.csv", index=False)
            pd.DataFrame({"player_id": [5, 6, 5], "match_id": ["a", "a", "b"], "minutes_played": [90, 0, 90]}
                         ).to_csv(folder / "EFL Cup/GW4/playermatchstats.csv", index=False)
            frame = load_appearances(Path(tmp))
            self.assertEqual(frame[["code", "minutes", "competition"]].values.tolist(), [[50, 90.0, "EFL Cup"]])


if __name__ == "__main__":
    unittest.main()
