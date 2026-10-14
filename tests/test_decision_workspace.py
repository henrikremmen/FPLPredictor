from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import pandas as pd
from fastapi.testclient import TestClient
os.environ.setdefault("FPL_SESSIONS_DB_PATH", ":memory:")
import api
from decision_workspace import constrained_team, compare_players, context, player_detail, changes_since_previous
from fpl_app import AppError, recommend_transfers, transfer_targets, sell_candidates
from multiweek_planner import plan_multiweek
from chip_strategy import _optimize_window
from test_multiweek_planner import _team


class WorkspaceTests(unittest.TestCase):
    def test_player_detail_shows_dated_return_scenario(self):
        team = _team()
        team.player_data_at = '2026-10-09T12:00:00Z'
        team.market.loc[team.market.id.eq(8), 'news'] = 'Ankle injury - Expected back 18 Oct'
        team.market.loc[team.market.id.eq(8), 'news_added'] = '2026-10-01T12:00:00Z'
        team.market.loc[team.market.id.eq(8), 'availability'] = 0.
        team_id = int(team.market.loc[team.market.id.eq(8), 'team_id'].iloc[0])
        player = {'id': 8, 'team': team_id, 'status': 'i'}
        fixtures = [{'id': 1, 'event': 5, 'team_h': team_id, 'team_a': 999,
                     'kickoff_time': '2026-10-10T15:00Z'},
                    {'id': 2, 'event': 6, 'team_h': team_id, 'team_a': 999,
                     'kickoff_time': '2026-10-20T15:00Z'}]
        with tempfile.TemporaryDirectory() as directory:
            team.forecast_path = Path(directory) / 'forecast.csv'
            pd.DataFrame({'player_id': [8, 8], 'GW': [5, 6], 'fixture': [1, 2],
                          'prediction': [3., 3.]}).to_csv(Path(directory) / 'horizon_fixture_forecast.csv', index=False)
            with patch('decision_workspace.read_gzip_json', side_effect=lambda p:
                       {'elements': [player]} if p.name == 'bootstrap.json.gz' else fixtures):
                detail = player_detail(team, 8)
        self.assertEqual([r['conservative_points'] for r in detail['injury_scenarios']], [0., 0.])
        self.assertEqual([r['reported_return_points'] for r in detail['injury_scenarios']], [0., 3.])

    def test_locks_and_exclusions_reach_all_optimizers(self):
        team = _team()
        locked = constrained_team(team, range(8, 13), [])
        self.assertTrue(recommend_transfers(locked, 1).empty)
        self.assertTrue(recommend_transfers(locked, 3).empty)
        plan = plan_multiweek(locked, weeks=2)
        self.assertTrue(all(set(range(8, 13)).issubset(w['squad_ids']) for w in plan['weeks']))
        excluded = constrained_team(team, [], [16])
        self.assertTrue(recommend_transfers(excluded, 1).empty)
        self.assertTrue(all(16 not in w['squad_ids'] for w in plan_multiweek(excluded, weeks=2)['weeks']))
        chip = _optimize_window(excluded, [5])
        self.assertNotIn(16, chip.squad_ids)
        chip = _optimize_window(locked, [5])
        self.assertTrue(set(range(8, 13)).issubset(chip.squad_ids))
        self.assertEqual(team.locked_ids, set())
        self.assertEqual(team.excluded_ids, set())

    def test_market_suggestions_respect_preferences(self):
        team = constrained_team(_team(), [8], [16])
        self.assertTrue(transfer_targets(team).empty)
        self.assertNotIn(8, set(sell_candidates(team, limit=15).id))
        session = api.STORE.add(_team())
        client = TestClient(api.app)
        response = client.get(f'/api/team/{session}/market?excluded_ids=16')
        self.assertEqual(response.json()['players'], [])
        response = client.get(f'/api/team/{session}/sells?locked_ids=8')
        self.assertNotIn(8, [p['id'] for p in response.json()['players']])

    def test_excluded_owned_player_must_be_sold(self):
        team = constrained_team(_team(), [], [8])
        result = recommend_transfers(team, 1)
        self.assertEqual(result.iloc[0]['out'], 'Player 8')
        plan = plan_multiweek(team, weeks=2)
        self.assertTrue(all(8 not in w['squad_ids'] for w in plan['weeks']))

    def test_conflicts_and_forced_sales_rejected(self):
        with self.assertRaises(AppError): constrained_team(_team(), [8], [8])
        with self.assertRaises(AppError): constrained_team(_team(), [16], [])
        with self.assertRaises(AppError): constrained_team(_team(), [], [999])
        with self.assertRaises(AppError): recommend_transfers(constrained_team(_team(), [8], []), 1, forced_outgoing=[8])

    def test_comparison_accounts_for_hit_once_and_preserves_team(self):
        team = _team()
        team.free_transfers = 0
        before = team.squad.copy(deep=True)
        result = compare_players(team, 8, 16)
        self.assertEqual(len(result['weeks']), 4)
        self.assertEqual(result['hit'], 4)
        self.assertAlmostEqual(result['net_gain'], sum(w['gain'] for w in result['weeks']) - 4)
        self.assertEqual(result['bank_after'], 0)
        pd.testing.assert_frame_equal(team.squad, before)
        with self.assertRaises(AppError): compare_players(team, 1, 16)
        team.market.loc[team.market.id.eq(16), 'price'] = 51
        with self.assertRaises(AppError): compare_players(team, 8, 16)

    def test_revision_tracks_finances_and_scores(self):
        team = _team()
        a = context(team)['revision']
        team.bank += 1
        b = context(team)['revision']
        team.market.loc[0, 'recommended_points'] += 1
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, context(team)['revision'])

    def test_missing_snapshot_and_player_are_explicit(self):
        team = _team()
        detail = player_detail(team, 8)
        self.assertEqual(len(detail['weeks']), 4)
        self.assertEqual(detail['fixtures'], [])
        self.assertIsNone(detail['context']['forecast_at'])
        with self.assertRaises(AppError): player_detail(team, 999)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(changes_since_previous(team, Path(directory))['changes'], [])

    def test_api_requests_do_not_mutate_shared_session(self):
        client = TestClient(api.app)
        team = _team()
        session = api.STORE.add(team)
        response = client.post(f'/api/team/{session}/transfers', json={'number': 1, 'excluded_ids': [16]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['plans'], [])
        self.assertEqual(api.STORE.get(session).excluded_ids, set())
        response = client.post(f'/api/team/{session}/compare', json={'out_id': 8, 'in_id': 16})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(response.json()['net_gain'], 0)
        response = client.post(f'/api/team/{session}/plan', json={'weeks': 1, 'locked_ids': [8], 'excluded_ids': [8]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(client.get(f'/api/team/{session}/players/16').status_code, 200)

    def test_changes_compare_same_horizon_and_ignore_small_point_changes(self):
        team = _team()
        team.squad['news'] = ''
        team.squad['status'] = 'a'
        team.squad['availability'] = 1.0
        team.squad['opponent'] = 'OPP (H)'
        previous = team.squad.copy(deep=True)
        previous.loc[previous.id.eq(8), 'news'] = 'Knock'
        previous.loc[previous.id.eq(8), 'availability'] = .75
        previous.loc[previous.id.eq(8), 'recommended_points'] = 3.0
        previous.loc[previous.id.eq(9), 'recommended_points'] = 3.8
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'data/raw/live_fpl/capture_previous'
            folder.mkdir(parents=True)
            (folder / 'manifest.json').write_text(json.dumps({
                'status': 'complete', 'forecast_status': 'experimental_frozen',
                'season': '2026-27', 'started_at': '2026-10-05T10:00:00Z',
                'forecast_at': '2026-10-05T10:02:00Z'}))
            with patch('decision_workspace.manifest_for', return_value={
                'season': '2026-27', 'started_at': '2026-10-10T09:00:00Z',
                'forecast_at': '2026-10-10T09:02:00Z'}), patch(
                'decision_workspace.read_gzip_json', return_value={}
            ), patch('decision_workspace.build_market', return_value=previous) as market:
                result = changes_since_previous(team, root)
                self.assertEqual([row['id'] for row in result['changes']], [8])
                self.assertEqual(result['changes'][0]['fields']['availability'], {'before': .75, 'after': 1.0})
                self.assertEqual(market.call_args.args[-2:], (5, 4))

    def test_nonselectable_players_cannot_be_bought(self):
        team = _team()
        team.market['can_select'] = True
        team.market.loc[team.market.id.eq(16), 'can_select'] = False
        self.assertTrue(recommend_transfers(team, 1).empty)
        self.assertNotIn(16, plan_multiweek(team, weeks=1)['weeks'][0]['squad_ids'])
        self.assertNotIn(16, _optimize_window(team, [5]).squad_ids)
        with self.assertRaises(AppError): compare_players(team, 8, 16)

    def test_successful_exact_two_and_three_transfer_plans_keep_locked_players(self):
        team = _team()
        extra = team.market.iloc[[2, 7, 12]].copy()
        extra['id'] = [17, 18, 19]
        extra['name'] = ['D upgrade', 'M upgrade', 'F upgrade']
        extra['team_id'] = [7, 8, 9]
        extra['recommended_points'] = [8.0, 9.0, 10.0]
        extra['decision_points'] = extra.recommended_points
        team.market = pd.concat([team.market, extra], ignore_index=True)
        team.weekly_market = pd.concat([team.market.assign(forecast_event=5), team.market.assign(forecast_event=6)])
        team = constrained_team(team, [3, 8, 13], [16])
        for number in [2, 3]:
            plans = recommend_transfers(team, number)
            self.assertFalse(plans.empty)
            for row in plans.itertuples():
                self.assertTrue({'Player 3', 'Player 8', 'Player 13'}.isdisjoint(row.out.split(' + ')))
            self.assertNotIn('Upgrade', plans.iloc[0]['in'].split(' + '))

    def test_refresh_progress_counts_successes_and_reports_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'data/raw/live_fpl/capture_test'
            folder.mkdir(parents=True)
            manifest = {'status': 'collecting', 'expected_players': 3, 'files': {
                'player_1': {'status': 200}, 'player_2': {'status': 500}, 'bootstrap': {'status': 200}}}
            path = folder / 'manifest.json'
            path.write_text(json.dumps(manifest))
            guard = api.RefreshGuard()
            guard._last_started = path.stat().st_mtime - 1
            guard._state = 'running'
            with patch('api.ROOT', root), patch('api.REFRESH_GUARD', guard):
                status = api.forecast_status()
                self.assertEqual(status['captured'], 1)
                self.assertEqual(status['total'], 3)
                self.assertEqual(status['stage'], 'Downloading player histories')
                manifest['captured_players'] = 3
                path.write_text(json.dumps(manifest))
                self.assertEqual(api.forecast_status()['stage'], 'Generating and validating forecasts')

    def test_failed_refresh_reports_failure_and_releases_guard(self):
        guard = api.RefreshGuard(min_interval_seconds=0)
        with patch('api.REFRESH_GUARD', guard), patch('api.refresh_forecast', side_effect=AppError('Source unavailable')):
            with self.assertRaises(AppError): guard.run()
            status = api.forecast_status()
            self.assertEqual(status['state'], 'failed')
            self.assertIn('Source unavailable', status['error'])
            self.assertFalse(guard._busy)


if __name__ == '__main__': unittest.main()
