import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from freeze_component_challengers import live_start_features


class PinnedStartTests(unittest.TestCase):
    def test_unfinished_fixture_cannot_enter_start_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {
                "fixtures.json.gz": [{"id": 1, "finished": True}, {"id": 2, "finished": False}],
                "player_7.json.gz": {"history": [
                    {"fixture": 1, "kickoff_time": "2026-09-01T12:00Z", "starts": 1},
                    {"fixture": 2, "kickoff_time": "2026-10-20T12:00Z", "starts": 0}]}}
            files = []
            for index, (name, payload) in enumerate(payloads.items()):
                filename = f"source_{index}.bin"
                with gzip.open(root / filename, "wt") as handle:
                    json.dump(payload, handle)
                files.append({"file": filename, "original_path": name})
            result = live_start_features(root, {"files": files}, pd.DataFrame({"player_id": [7]}))
            self.assertEqual(result.start_rate3.iloc[0], 1.)
            self.assertEqual(result.start_rate10.iloc[0], 1.)
            self.assertEqual(result.starts_season_before.iloc[0], 1.)
