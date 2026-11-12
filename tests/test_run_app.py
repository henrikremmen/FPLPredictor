from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_app  # also a compile check of the launcher everyone starts the app with


class CollectWhileRunningTests(unittest.TestCase):
    """D2: own data is collected while the app runs, never on Actions, and a failure never stops the app."""

    def test_skips_without_an_fpl_data_checkout(self):
        run = MagicMock()
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(run_app.collect_once(Path(folder), run=run))
        run.assert_not_called()

    def test_runs_the_collector_on_the_checkout(self):
        run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "fpl-data").mkdir()
            self.assertTrue(run_app.collect_once(Path(folder), run=run))
        command = run.call_args.args[0]
        self.assertEqual(command[-3:], ["--data-root", str(Path(folder) / "fpl-data"), "auto"])
        self.assertTrue(command[1].endswith("src/fpl_collect.py"))

    def test_a_failing_collector_never_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "fpl-data").mkdir()
            self.assertTrue(run_app.collect_once(Path(folder), run=MagicMock(side_effect=subprocess.TimeoutExpired("x", 1))))
            self.assertTrue(run_app.collect_once(Path(folder), run=MagicMock(
                return_value=subprocess.CompletedProcess([], 1, "", "contract failed"))))


if __name__ == "__main__":
    unittest.main()
