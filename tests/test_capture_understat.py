import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capture_understat import fetch


class CaptureTests(unittest.TestCase):
    def test_cache_is_reused_and_modified_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            body = b'{"shots": []}'
            (folder / "match_1.json").write_bytes(body)
            (folder / "match_1.meta.json").write_text(json.dumps({"sha256": hashlib.sha256(body).hexdigest()}))
            session = Mock()
            self.assertEqual(fetch(session, folder, "match_1", "getMatchData/1"), {"shots": []})
            session.get.assert_not_called()
            (folder / "match_1.json").write_text('{"shots": [1]}')
            with self.assertRaisesRegex(ValueError, "Changed cached"):
                fetch(session, folder, "match_1", "getMatchData/1")
            session.get.assert_not_called()
