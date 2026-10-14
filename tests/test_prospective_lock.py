from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prospective_lock import freeze_forecasts, verify_lock


class LockTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame(dict(model=["a", "b"], season=["2098-99"] * 2,
            GW=[1, 1], player_id=[7, 7], fixture=[10, 10], prediction=[3., 4.]))

    def test_copied_evidence_tampering_and_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, model = root / "raw.json", root / "model.joblib"
            source.write_text('{}'); model.write_bytes(b'test artifact')
            args = dict(deadline="2099-01-01T00:00Z", sources=[dict(path=source, received_at="2020-01-01T00:00Z")],
                models={"a": model, "b": model}, destination=root / "locked")
            freeze_forecasts(self.frame(), **args)
            source.write_text('changed original')
            verify_lock(root / "locked")
            with self.assertRaises(FileExistsError):
                freeze_forecasts(self.frame(), **args)
            (root / "locked/predictions.csv").write_text('modified')
            with self.assertRaisesRegex(ValueError, "Changed locked"):
                verify_lock(root / "locked")

    def test_past_deadline_and_unequal_cohorts_fail(self):
        with self.assertRaisesRegex(ValueError, "at or after"):
            freeze_forecasts(self.frame(), deadline="2000-01-01T00:00Z", sources=[], models={}, destination="unused")
        frame = self.frame(); frame.loc[1, "player_id"] = 9
        with self.assertRaisesRegex(ValueError, "cohorts differ"):
            freeze_forecasts(frame, deadline="2099-01-01T00:00Z", sources=[],
                models={"a": "unused", "b": "unused"}, destination="unused")
