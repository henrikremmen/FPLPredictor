"""U19: the journal freezes before the deadline, never overwrites, and scores afterwards."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import decision_journal
from test_api import fake_team

STRATEGY = {"transfer": {"decision": "ROLL", "title": "Roll the free transfer", "reason": "Keep flexibility.",
                         "transfers_out": [], "transfers_in": []},
            "captain": {"captain": {"name": "P1"}},
            "plan": {"weeks": [{"starter_ids": [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15], "captain": "P1"}]}}


class JournalTests(unittest.TestCase):
    def test_record_before_deadline_latest_counts_and_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forecast = root / "forecast.csv"
            pd.DataFrame({"season": ["2026-27"], "GW": [5]}).to_csv(forecast, index=False)
            team = replace(fake_team(), forecast_path=forecast, deadline="2026-09-19T10:00:00Z")
            with self.assertRaises(Exception):  # after the deadline
                decision_journal.record(root, team, STRATEGY, [], "follow", now="2026-09-19T10:00:01Z")
            with self.assertRaises(Exception):
                decision_journal.record(root, team, STRATEGY, [], "maybe", now="2026-09-18T10:00:00Z")
            decision_journal.record(root, team, STRATEGY, [{"name": "Hold", "net_points": 50}], "follow",
                                    note="as advised", now="2026-09-18T10:00:00Z")
            decision_journal.record(root, team, STRATEGY, [], "other", now="2026-09-19T09:00:00Z")
            entries = decision_journal.entries(root, "2026-27", team.entry_id)
            self.assertEqual([e["choice"]["kind"] for e in entries], ["other", "follow"])
            self.assertEqual([e["counts"] for e in entries], [True, False])  # the last one before the deadline
            self.assertNotIn("outcome", entries[0])
            gws = root / "fpl-data/data/2026-27/gws"
            gws.mkdir(parents=True)
            pd.DataFrame({"element": range(1, 16), "total_points": [2] * 15}).to_csv(gws / "gw5.csv", index=False)
            outcome = decision_journal.entries(root, "2026-27", team.entry_id)[0]["outcome"]
            self.assertEqual(outcome["advised_xi_points"], 11 * 2 + 2)  # captain doubled
            self.assertEqual(len(list(decision_journal.folder(root, "2026-27", team.entry_id).glob("journal_*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
