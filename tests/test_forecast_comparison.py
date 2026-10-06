import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from forecast_comparison import catalog, compare, metrics


class ForecastComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.before = self.root / 'data/raw/live_fpl/capture_before'
        self.after = self.before.parent / 'capture_after'
        self.before.mkdir(parents=True)
        self.after.mkdir()
        self.event = dict(id=4, deadline_time='2026-09-12T12:30:00Z', finished=False, data_checked=False)
        self.bootstrap = dict(events=[self.event], teams=[dict(id=1, short_name='ARS')], elements=[
            dict(id=i, team=1, status='d', news='Doubt', chance_of_playing_next_round=50)
            for i in [1, 2, 3]])
        self.write(self.before / 'bootstrap.json.gz', self.bootstrap)
        self.write(self.before / 'manifest.json', dict(status='complete', forecast_status='experimental_frozen',
            season='2026-27', forecast_at='2026-09-11T12:00:00Z', finished_at='2026-09-11T12:00:00Z'))
        pd.DataFrame(dict(season=['2026-27']*3, GW=[4]*3, player_id=[1,2,3],
            prediction=[6.,2.,1.], name=['One','Two','Three'], position=['MID']*3,
            planned_fixtures=[2,1,1])).to_csv(self.before / 'forecast.csv', index=False)
        self.write(self.after / 'manifest.json', dict(status='complete', season='2026-27',
            forecast_status='not_generated', finished_at='2026-09-15T12:00:00Z'))
        self.event.update(finished=True, data_checked=True)
        self.write(self.after / 'bootstrap.json.gz', self.bootstrap)
        fields = dict(minutes=90, goals_scored=1, assists=0, bonus=2, clean_sheets=0)
        self.write(self.after / 'player_1.json.gz', dict(history=[
            dict(round=4, total_points=7, **fields), dict(round=4, total_points=5, **fields),
            dict(round=3, total_points=20, **fields)]))
        self.write(self.after / 'player_2.json.gz', dict(history=[]))

    def write(self, path, data):
        body = json.dumps(data).encode()
        path.write_bytes(gzip.compress(body) if path.suffix == '.gz' else body)

    def test_double_round_missing_history_and_historical_flags(self):
        result = compare(self.root, catalog(self.root).iloc[0]).set_index('player_id')
        self.assertEqual(result.loc[1, 'actual_points'], 12)
        self.assertEqual(result.loc[1, 'actual_minutes'], 180)
        self.assertEqual(result.loc[1, 'app_prediction'], 3)
        self.assertEqual(result.loc[2, 'actual_points'], 0)
        self.assertTrue(pd.isna(result.loc[3, 'actual_points']))
        self.assertEqual(metrics(result)['evaluated'], 2)
        self.assertEqual(metrics(result)['MAE'], 4)

    def test_unchecked_round_is_pending_not_zero(self):
        self.event['data_checked'] = False
        self.write(self.after / 'bootstrap.json.gz', self.bootstrap)
        result = compare(self.root, catalog(self.root).iloc[0])
        self.assertTrue(result.actual_points.isna().all())
        self.assertTrue(result.outcome_status.eq('pending').all())
        self.assertEqual(metrics(result)['evaluated'], 0)

    def test_forecast_at_deadline_is_excluded(self):
        path = self.before / 'manifest.json'
        m = json.loads(path.read_text())
        m['forecast_at'] = self.event['deadline_time']
        self.write(path, m)
        self.assertTrue(catalog(self.root).empty)


if __name__ == '__main__':
    unittest.main()
