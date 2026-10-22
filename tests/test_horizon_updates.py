from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_multiweek_planner import _team
from decision_workspace import change_horizon
from fpl_app import AppError
import api


class HorizonTests(unittest.TestCase):
    def prepared(self):
        team = _team()
        team.bank = 13
        team.free_transfers = 3
        team.squad['purchase_price'] = 47
        team.squad['selling_price'] = 48
        team.locked_ids = {8}
        team.squad_source = 'manual_override'
        return team

    def test_horizon_rebuild_retains_holdings_finances_and_prices_without_network(self):
        team = self.prepared()
        def market(_bootstrap, _fixtures, _path, _event, horizon):
            result = team.market.copy()
            result['recommended_points'] *= horizon
            return result
        with patch('decision_workspace.read_gzip_json', return_value={}), patch(
                'decision_workspace.build_market', side_effect=market):
            updated = change_horizon(team, 8)
        self.assertEqual(updated.horizon, 8)
        self.assertEqual(updated.weekly_market.forecast_event.nunique(), 8)
        self.assertEqual(updated.bank, 13)
        self.assertEqual(updated.free_transfers, 3)
        self.assertEqual(updated.locked_ids, {8})
        self.assertEqual(updated.squad_source, 'manual_override')
        self.assertEqual(updated.squad.id.tolist(), team.squad.id.tolist())
        self.assertTrue(updated.squad.selling_price.eq(48).all())
        self.assertTrue(updated.squad.purchase_price.eq(47).all())
        self.assertEqual(updated.lineup_squad.recommended_points.iloc[0], 4.)
        self.assertEqual(updated.squad.recommended_points.iloc[0], 32.)
        self.assertEqual(team.horizon, 4)

    def test_failed_rebuild_does_not_mutate_session_or_persist_horizon(self):
        team = self.prepared()
        session = api.STORE.add(team)
        with patch('api.change_horizon', side_effect=AppError('Missing saved forecast')):
            response = TestClient(api.app).patch(f'/api/team/{session}/horizon', json={'horizon': 8})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(api.STORE.get(session).horizon, 4)
        self.assertEqual(api.STORE._registry.get(session).horizon, 4)

    def test_success_persists_same_session_and_rejects_invalid_horizon(self):
        team = self.prepared()
        session = api.STORE.add(team)
        with patch('decision_workspace.read_gzip_json', return_value={}), patch(
                'decision_workspace.build_market', return_value=team.market):
            response = TestClient(api.app).patch(f'/api/team/{session}/horizon', json={'horizon': 2})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['session_id'], session)
        self.assertEqual(response.json()['bank'], 13)
        self.assertEqual(api.STORE._registry.get(session).horizon, 2)
        response = TestClient(api.app).patch(f'/api/team/{session}/horizon', json={'horizon': 9})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(api.STORE.get(session).horizon, 2)
