import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import shadow_season

SHAPE = [1] * 3 + [2] * 7 + [3] * 7 + [4] * 4  # element types; 21 players over 7 clubs


def world(root: Path, event=10, deadline="2026-11-06T18:30:00Z"):
    elements = [{"id": i + 1, "web_name": f"P{i + 1}", "team": i % 7 + 1, "element_type": t, "now_cost": 50}
                for i, t in enumerate(SHAPE)]
    bundle = root / "artifacts/prospective" / f"loop_gw{event}_20261106T140930Z"
    decisions = bundle.with_name(bundle.name + "_decisions")
    for folder in (bundle, decisions):
        folder.mkdir(parents=True)
    (bundle / "manifest.json").write_text(json.dumps({"deadline": deadline, "GW": event}))
    with gzip.open(decisions / "bootstrap.json.gz", "wt") as handle:
        json.dump({"elements": elements}, handle)
    # The incumbent likes player 21 (a forward not owned); hold keeps the squad.
    pd.DataFrame([{"model": "incumbent", "player_id": e["id"], "fixture": 1,
                   "prediction": 10.0 if e["id"] == 21 else float(e["id"] % 5)} for e in elements]).to_csv(
        bundle / "predictions.csv", index=False)
    squad = [{"id": i, "name": f"P{i}", "position": shadow_season.POSITIONS[SHAPE[i - 1]], "team": str((i - 1) % 7 + 1),
              "purchase_price": 50} for i in (1, 2, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 18, 19, 20)]
    return elements, squad


class ShadowSeasonTest(unittest.TestCase):
    def test_lock_and_score_one_round_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            elements, squad = world(root)
            state = shadow_season.start_state(squad, bank=5, free_transfers=1, policies=["hold", "incumbent"],
                                              event=10, source="test")
            base = shadow_season.folder(root, "2026-27", 1)
            shadow_season._write_new(base / "state_gw10.json", state)
            with self.assertRaises(ValueError):  # after the deadline nothing is locked
                shadow_season.lock(root, "2026-27", 1, 10, now="2026-11-06T18:31:00Z")
            locked = json.loads(shadow_season.lock(root, "2026-27", 1, 10, now="2026-11-06T15:00:00Z").read_text())
            self.assertEqual(locked["decisions"]["hold"]["moves"], [])
            self.assertEqual([m["in_id"] for m in locked["decisions"]["incumbent"]["moves"]], [21])
            with self.assertRaises(FileExistsError):  # one lock per round
                shadow_season.lock(root, "2026-27", 1, 10, now="2026-11-06T15:01:00Z")

            captain = locked["decisions"]["hold"]["captain"]
            vice = locked["decisions"]["hold"]["vice_captain"]
            outcome = pd.DataFrame([{"element": e["id"], "total_points": 2, "minutes": 90} for e in elements])
            outcome.loc[outcome.element.eq(captain), ["total_points", "minutes"]] = [0, 0]  # captain absent
            outcome.loc[outcome.element.eq(vice), "total_points"] = 7
            gws = root / "fpl-data/data/2026-27/gws"
            gws.mkdir(parents=True)
            outcome.to_csv(gws / "gw10.csv", index=False)

            scores = json.loads(shadow_season.score(root, "2026-27", 1, 10).read_text())["scores"]
            # hold: 10 starters play (9 × 2 + vice 7) + an autosub (2) + vice doubled (7) = 34
            self.assertEqual(scores["hold"]["points"], 34.0)
            self.assertEqual(scores["hold"]["doubled"], f"P{vice}")
            following = json.loads((base / "state_gw11.json").read_text())["policies"]
            self.assertEqual(following["hold"]["free_transfers"], 2)       # rolled
            self.assertEqual(following["incumbent"]["free_transfers"], 1)  # used one, gained one
            self.assertIn("21", following["incumbent"]["holdings"])
            self.assertEqual(following["incumbent"]["holdings"]["21"]["purchase_price"], 50)


if __name__ == "__main__":
    unittest.main()
