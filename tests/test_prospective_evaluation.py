from pathlib import Path
import sys
import unittest
import tempfile
import json
import gzip
import hashlib

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prospective_evaluation import score_predictions, outcomes_from_snapshot


class EvaluationTests(unittest.TestCase):
    def test_provisional_is_explicit_and_requires_all_finished_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            manifest = {'season': '2026-27', 'status': 'complete', 'files': {}}
            def write(key, value):
                filename = key + '.json.gz'
                raw = gzip.compress(json.dumps(value).encode())
                (path / filename).write_bytes(raw)
                manifest['files'][key] = {'file': filename, 'status': 200,
                    'stored_sha256': hashlib.sha256(raw).hexdigest(), 'received_at': '2026-10-20T12:00:00Z'}
                (path / 'manifest.json').write_text(json.dumps(manifest))
            write('bootstrap', {'events': [{'id': 7, 'finished': False, 'data_checked': False}]})
            write('fixtures', [{'id': 10, 'event': 7, 'finished': True}])
            write('player_1', {'history': [{'round': 7, 'fixture': 10, 'total_points': 5,
                                          'minutes': 90, 'starts': 1}]})
            lock = {'GW': 7, 'season': '2026-27', 'deadline': '2026-10-17T10:00:00Z'}
            with self.assertRaisesRegex(ValueError, 'not final'):
                outcomes_from_snapshot(lock, path)
            self.assertEqual(outcomes_from_snapshot(lock, path, provisional=True).target_points.iloc[0], 5)
            write('fixtures', [{'id': 10, 'event': 7, 'finished': True},
                               {'id': 11, 'event': 7, 'finished': False}])
            with self.assertRaisesRegex(ValueError, 'every gameweek fixture'):
                outcomes_from_snapshot(lock, path, provisional=True)

    def frames(self):
        keys = dict(season=["2026-27"] * 3, GW=[7] * 3, player_id=[1, 2, 3], fixture=[10] * 3)
        pred = pd.DataFrame({**keys, "model": ["test"] * 3, "prediction": [0., 2., 6.],
            "p_absent": [1., 0., 0.], "p_cameo": [0., 1., 0.], "p_start": [0., 0., 1.]})
        truth = pd.DataFrame({**keys, "target_points": [0., 2., 6.], "minutes": [0, 70, 12], "starts": [0, 0, 1]})
        return pred, truth

    def test_role_scores_use_starts_not_sixty_minutes(self):
        pred, truth = self.frames()
        pred["minutes"], pred["starts"] = 999, 99
        reports, _ = score_predictions(pred, truth)
        self.assertEqual(reports[0]["fixture_points"]["RMSE"], 0)
        self.assertEqual(reports[0]["role"]["multiclass_brier"], 0)

    def test_missing_outcome_is_not_a_zero(self):
        pred, truth = self.frames()
        with self.assertRaisesRegex(ValueError, "Not every"):
            score_predictions(pred, truth.iloc[:2])

    def test_diagnostics_use_observed_minutes_and_signed_bias(self):
        pred, truth = self.frames()
        pred["minutes"] = 90  # Frozen inputs must not define outcome strata.
        pred["prediction"] = [2., 1., 9.]
        reports, _ = score_predictions(pred, truth)
        bands = reports[0]["points_by_observed_minutes"]
        self.assertEqual(bands["absent"]["bias"], 2.)
        self.assertEqual(bands["60plus_minutes"]["bias"], -1.)
        self.assertEqual(bands["1_59_minutes"]["bias"], 3.)
        self.assertEqual(sum(b["rows"] for b in bands.values()), 3)

    def test_empty_observed_band_has_no_invented_metrics(self):
        pred, truth = self.frames()
        truth["minutes"] = 90
        reports, _ = score_predictions(pred, truth)
        self.assertEqual(reports[0]["points_by_observed_minutes"]["absent"], {"rows": 0})

    def test_duplicate_outcomes_and_invalid_probabilities_fail(self):
        pred, truth = self.frames()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            score_predictions(pred, pd.concat([truth, truth]))
        pred.loc[0, "p_start"] = .5
        with self.assertRaisesRegex(ValueError, "Invalid frozen"):
            score_predictions(pred, truth)
