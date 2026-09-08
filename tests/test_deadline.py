import gzip
import json
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from deadline_audit import sha256, verify_bootstrap, utc
from deadline_features import build_round, aggregate_predictions
from deadline_evaluation import decision_report, paired_bootstrap

class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.season = '2024-25'
        self.deadline = '2024-09-01T10:00:00Z'
        pre = '2024-08-31T10:00:00Z'
        self.registry = pd.DataFrame([{'season': self.season, 'player_id': i,
            'team': i, 'position': 'MID', 'name': f'p{i}', 'available_at': pre} for i in [1, 2, 3]])
        self.fixtures = pd.DataFrame([{'season': self.season, 'fixture': i,
            'GW': 3, 'team_h': 1, 'team_a': 2, 'was_cancelled': False,
            'available_at': pre} for i in [10, 11]])
        stats = {s: 1. for s in ['starts', 'total_points', 'bps', 'ict_index', 'threat',
            'creativity', 'influence', 'saves', 'clean_sheets', 'expected_goals',
            'expected_assists', 'goals_scored', 'assists']}
        self.history = pd.DataFrame([{'season': self.season, 'player_id': 1, 'fixture': 1,
            'finished_at': pre, 'available_at': pre, 'minutes': 90., **stats}])
        self.teams = pd.DataFrame([{'season': self.season, 'team': i, 'fixture': 1,
            'available_at': pre, 'finished_at': pre, 'goals_for': i, 'goals_against': 0,
            'points': 3} for i in [1, 2]])

    def build(self):
        return build_round(self.season, 3, self.deadline, self.registry,
                           self.fixtures, self.history, self.teams)

    def test_double_blank_and_new_player(self):
        d = self.build()
        self.assertEqual(len(d), 5)
        self.assertEqual(d[d.player_id.eq(1)].points_avg5.nunique(), 1)
        self.assertTrue(d[d.player_id.eq(2)].minutes_last1.isna().all())
        self.assertFalse(d[d.player_id.eq(3)].planned_fixture.any())
        truth = pd.DataFrame({'season': [self.season]*3, 'GW': [3]*3,
            'player_id': [1,2,3], 'target_points': [5,2,0]})
        result = aggregate_predictions(d, np.ones(len(d)), truth)
        self.assertEqual(result.prediction.tolist(), [2., 2., 0.])
        with self.assertRaises(ValueError):
            aggregate_predictions(d, np.ones(len(d)), pd.concat([truth, truth.iloc[:1]]))
        with self.assertRaises(ValueError):
            aggregate_predictions(d, np.ones(len(d)), truth.iloc[:2])

    def test_future_outcomes_and_corrections_do_not_change_features(self):
        before = self.build()
        future = self.history.copy()
        future['fixture'] = 10  # first match of the DGW
        future['available_at'] = '2024-09-02T12:00:00Z'
        future['finished_at'] = '2024-09-02T11:00:00Z'
        future['total_points'] = 1000
        correction = self.history.copy()
        correction['available_at'] = self.deadline  # equality must be excluded too
        correction['total_points'] = 999
        self.history = pd.concat([self.history, future, correction])
        pd.testing.assert_frame_equal(before, self.build())

    def test_schedule_changes_and_transfer(self):
        before = self.build()
        moved = self.fixtures.iloc[:1].copy()
        moved['GW'] = 4
        moved['available_at'] = self.deadline
        self.fixtures = pd.concat([self.fixtures, moved])
        pd.testing.assert_frame_equal(before, self.build())
        self.fixtures.loc[self.fixtures.GW.eq(4), 'available_at'] = '2024-09-01T09:00:00Z'
        self.assertEqual(self.build().planned_fixture.sum(), 2)
        transfer = self.registry.iloc[:1].copy()
        transfer['team'] = 3
        transfer['available_at'] = '2024-09-01T09:30:00Z'
        self.registry = pd.concat([self.registry, transfer])
        self.assertFalse(self.build().query('player_id == 1').planned_fixture.any())

    def test_missing_registry_and_timezone(self):
        self.registry['available_at'] = self.deadline
        with self.assertRaises(ValueError):
            self.build()
        with self.assertRaises(ValueError):
            utc('2024-09-01 10:00')
        self.assertEqual(utc('2024-09-01T12:00:00+02:00'), utc(self.deadline))

    def test_archive_hash_and_timing(self):
        payload = {'events': [{'id': 3, 'deadline_time': self.deadline, 'is_next': True}],
                   'elements': [{'id':1, 'team':1, 'element_type':3}], 'teams':[{'id':1}]}
        raw = json.dumps(payload).encode()
        manifest = {'files':[{'endpoint':'/bootstrap-static/', 'sha256':sha256(raw)}],
            'captured_at':'2024-09-01T09:00:00Z', 'event':3, 'event_deadline':self.deadline,
            'backfill':{'season':self.season, 'source':'https://web.archive.org/web/example',
                        'wayback_timestamp':'20240901090000'}}
        self.assertTrue(verify_bootstrap(manifest,gzip.compress(raw),self.season,3)['bootstrap_verified'])
        manifest['captured_at'] = self.deadline
        manifest['backfill']['wayback_timestamp'] = '20240901100000'
        self.assertFalse(verify_bootstrap(manifest,gzip.compress(raw),self.season,3)['bootstrap_verified'])

    def test_captain_tie_break_and_same_universe(self):
        rows=[]
        for method in ['form','hgb','ensemble']:
            for i in [2,1]:
                rows.append({'method':method,'season':self.season,'GW':3,'player_id':i,
                    'position':'MID','planned_fixtures':1,'minutes_avg5':90,
                    'prediction':2.,'target_points':float(i)})
        d=pd.DataFrame(rows)
        _, _, captains=decision_report(d)
        self.assertTrue(captains.player_id.eq(1).all())
        self.assertTrue(captains.gain_vs_form.eq(0).all())
        self.assertTrue(paired_bootstrap(d, draws=10).MSE_gain.eq(0).all())
        with self.assertRaises(ValueError):
            paired_bootstrap(d.iloc[:-1], draws=10)

if __name__ == '__main__':
    unittest.main()
