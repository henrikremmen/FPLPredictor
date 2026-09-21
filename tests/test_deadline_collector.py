from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadline_collector import checkpoint_for, completed_phases


class DeadlineCollectorTests(unittest.TestCase):
    def test_checkpoint_buckets_do_not_backfill_missed_windows(self):
        now = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
        self.assertIsNone(checkpoint_for(now + timedelta(hours=25), now))
        self.assertEqual(checkpoint_for(now + timedelta(hours=20), now), "24h")
        self.assertEqual(checkpoint_for(now + timedelta(hours=5), now), "6h")
        self.assertEqual(checkpoint_for(now + timedelta(minutes=45), now), "1h")
        self.assertIsNone(checkpoint_for(now - timedelta(seconds=1), now))

    def test_completed_phases_only_accepts_complete_matching_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "data" / "raw" / "live_fpl"
            for name, payload in {
                "a": {"status": "complete", "target_event": {"id": 5}, "capture_phase": "24h"},
                "b": {"status": "failed", "target_event": {"id": 5}, "capture_phase": "6h"},
                "c": {"status": "complete", "target_event": {"id": 6}, "capture_phase": "1h"},
            }.items():
                path = parent / f"capture_{name}"
                path.mkdir(parents=True)
                (path / "manifest.json").write_text(json.dumps(payload))
            self.assertEqual(completed_phases(root, 5), {"24h"})


if __name__ == "__main__":
    unittest.main()
