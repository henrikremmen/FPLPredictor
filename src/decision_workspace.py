"""Read-only player research and reproducible decision context for the web app."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pandas as pd

from fpl_app import AppError, ImportedTeam, build_market, apply_risk_profile, optimal_lineup, _validate_holdings
from capture_fpl import read_gzip_json
from availability_forecast import availability_scenarios


def change_horizon(team: ImportedTeam, horizon: int) -> ImportedTeam:
    """Rebuild forecasts locally while retaining the exact active holdings."""
    if not 1 <= horizon <= 8:
        raise AppError('Horizon must be between one and eight gameweeks.')
    raw = Path(manifest_for(team).get('source_capture', team.forecast_path.parent))
    try:
        bootstrap = read_gzip_json(raw / 'bootstrap.json.gz')
        fixtures = read_gzip_json(raw / 'fixtures.json.gz')
        frames = []
        for event in range(team.target_event, team.target_event + horizon):
            frame = apply_risk_profile(build_market(bootstrap, fixtures, team.forecast_path, event, 1), team.risk_profile)
            frame['forecast_event'] = event
            frames.append(frame)
        market = apply_risk_profile(build_market(bootstrap, fixtures, team.forecast_path,
                                                 team.target_event, horizon), team.risk_profile)
    except (OSError, ValueError, KeyError) as exc:
        raise AppError('The saved forecast cannot provide this horizon. Refresh the forecast first.') from exc

    def holdings(values):
        # Purchase/selling prices, manual picks and squad order belong to the
        # active session, not the forecast snapshot.
        columns = ['id'] + [c for c in team.squad if c not in team.market and c != 'id']
        for column in ['purchase_price', 'selling_price', 'price_is_estimate', 'pick_position']:
            if column in team.squad and column not in columns:
                columns.append(column)
        metadata = team.squad[columns]
        result = metadata.merge(values.drop(columns=[c for c in columns if c != 'id' and c in values]),
                                on='id', how='left', validate='one_to_one')
        if result['name'].isna().any():
            raise AppError('The forecast is missing a player in your active squad.')
        return result

    return replace(team, horizon=horizon, market=market, squad=holdings(market),
                   lineup_squad=holdings(frames[0]), weekly_market=pd.concat(frames, ignore_index=True))


def constrained_team(team: ImportedTeam, locked_ids=(), excluded_ids=()) -> ImportedTeam:
    locked, excluded = set(locked_ids), set(excluded_ids)
    known = set(team.market.id.astype(int))
    if (locked | excluded) - known:
        raise AppError('Some selected players are no longer in this market. Update your preferences.')
    if locked & excluded:
        raise AppError('A player cannot be both locked and excluded.')
    if locked - set(team.squad.id.astype(int)):
        raise AppError('Only owned players can be locked. Update your preferences after a squad change.')
    if team.locked_ids == locked and team.excluded_ids == excluded:
        return team
    return replace(team, locked_ids=locked, excluded_ids=excluded)


def manifest_for(team: ImportedTeam) -> dict:
    try:
        return json.loads(team.forecast_path.with_name('manifest.json').read_text())
    except (OSError, ValueError):
        return {}


def context(team: ImportedTeam) -> dict:
    manifest = manifest_for(team)
    inputs = {
        'forecast': str(team.forecast_path), 'forecast_at': manifest.get('forecast_at'),
        'model': manifest.get('model_sha256'), 'entry': team.entry_id,
        'event': team.target_event, 'horizon': team.horizon, 'risk': team.risk_profile,
        'bank': team.bank, 'free_transfers': team.free_transfers, 'chips': team.chip_status,
        'squad': sorted((int(r.id), int(r.selling_price)) for r in team.squad.itertuples()),
        # The import can have fresher availability/prices than the frozen model.
        'market': team.market.sort_values('id').to_json(orient='records'),
    }
    return {
        'revision': hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20],
        'forecast_at': manifest.get('forecast_at'),
        'observed_at': manifest.get('started_at'),
        'player_data_at': team.player_data_at,
        'model_family': manifest.get('model_family'),
        'source_url': 'https://fantasy.premierleague.com/api/bootstrap-static/',
    }


def player_detail(team: ImportedTeam, player_id: int) -> dict:
    rows = team.market[team.market.id.eq(player_id)]
    if rows.empty:
        raise AppError('Player not found in the current market.')
    weekly = team.weekly_market
    by_week = [] if weekly is None else json.loads(
        weekly[weekly.id.eq(player_id)].sort_values('forecast_event').to_json(orient='records'))
    fixtures = []
    path = team.forecast_path.with_name('horizon_fixture_forecast.csv')
    if path.exists():
        frame = pd.read_csv(path)
        frame = frame[frame.player_id.eq(player_id) & frame.GW.between(
            team.target_event, team.target_event + team.horizon - 1)]
        columns = [c for c in ['GW', 'fixture', 'kickoff_time', 'planned_fixture',
            'p_zero_minutes', 'p_1_59_minutes', 'p_60plus_minutes', 'prediction',
            'prediction_q10', 'prediction_q50', 'prediction_q90'] if c in frame]
        fixtures = json.loads(frame[columns].to_json(orient='records'))
    manifest = manifest_for(team)
    raw = Path(manifest.get('source_capture', team.forecast_path.parent))
    news_added = rows.iloc[0].get('news_added')
    injury_scenarios = []
    try:
        bootstrap = read_gzip_json(raw / 'bootstrap.json.gz')
        snapshot_news_added = next((p.get('news_added') for p in bootstrap['elements'] if p['id'] == player_id), None)
        if 'news_added' not in rows:
            news_added = snapshot_news_added
        snapshot_player = next((p for p in bootstrap['elements'] if p['id'] == player_id), None)
        if snapshot_player is not None and fixtures:
            current = rows.iloc[0]
            player = {**snapshot_player, 'news': current.get('news', ''), 'news_added': news_added,
                'status': current.get('status', 'a'),
                'team': int(current.get('team_id', snapshot_player['team'])),
                'chance_of_playing_next_round': float(current.get('availability', 1.)) * 100}
            observed = team.player_data_at or manifest.get('started_at')
            scenario = availability_scenarios(player, read_gzip_json(raw / 'fixtures.json.gz'),
                observed, team.target_event)
            if not scenario.empty and scenario.reported_return.notna().any():
                comparison = pd.DataFrame(fixtures)[['GW', 'fixture', 'prediction']].merge(
                    scenario, on=['GW', 'fixture'], validate='one_to_one')
                comparison['conservative_points'] = comparison.prediction * comparison.conservative_factor
                comparison['reported_return_points'] = comparison.prediction * comparison.reported_return_factor
                injury_scenarios = json.loads(comparison[['GW', 'fixture', 'kickoff_time', 'reported_return',
                    'conservative_points', 'reported_return_points']].to_json(orient='records', date_format='iso'))
    except (OSError, ValueError, KeyError):
        pass
    return {'player': json.loads(rows.to_json(orient='records'))[0], 'weeks': by_week,
            'fixtures': fixtures, 'context': context(team), 'news_added': news_added,
            'injury_scenarios': injury_scenarios,
            'minutes_note': 'Minutes are predicted as 0, 1–59 or 60+. Exact expected minutes and start probability are not available.',
            'uncertainty_note': 'Fixture quantiles are model estimates before the availability adjustment. Summed multiweek quantiles are not a calibrated interval.'}


def changes_since_previous(team: ImportedTeam, root: Path) -> dict:
    current = manifest_for(team)
    stamp = current.get('started_at')
    result = {'previous_at': None, 'current_at': current.get('forecast_at'), 'changes': [],
              'message': 'No comparable earlier snapshot is available.'}
    if not stamp:
        return result
    candidates = []
    for path in (Path(root) / 'data/raw/live_fpl').glob('capture_*/manifest.json'):
        try:
            old = json.loads(path.read_text())
            if (old.get('status') == 'complete' and old.get('forecast_status') == 'experimental_frozen'
                and old.get('season') == current.get('season') and old['started_at'] < stamp):
                candidates.append((old['started_at'], path.parent, old))
        except (OSError, ValueError, KeyError):
            continue
    for _, folder, old in sorted(candidates, reverse=True):
        try:
            raw = Path(old.get('source_capture', folder))
            previous = build_market(read_gzip_json(raw / 'bootstrap.json.gz'),
                read_gzip_json(raw / 'fixtures.json.gz'), folder / 'forecast.csv', team.target_event, team.horizon)
        except (OSError, ValueError, KeyError, AppError):
            continue
        previous = previous.set_index('id')
        changes = []
        for row in team.squad.to_dict('records'):
            if row['id'] not in previous.index:
                continue
            before = previous.loc[row['id']]
            fields = {}
            for field in ['news', 'status', 'availability', 'price', 'opponent', 'recommended_points']:
                a, b = before.get(field), row.get(field)
                if field == 'recommended_points':
                    different = a is not None and b is not None and abs(float(a) - float(b)) >= .5
                else:
                    different = a != b
                if different:
                    fields[field] = {'before': a, 'after': b}
            if fields:
                changes.append({'id': row['id'], 'name': row['name'], 'fields': fields})
        result.update(previous_at=old.get('forecast_at'), changes=changes,
                      message='Changes to your current squad over the same forecast horizon. Point changes below 0.5 are omitted.')
        return result
    return result


def compare_players(team: ImportedTeam, out_id: int, in_id: int) -> dict:
    owned = set(team.squad.id.astype(int))
    if out_id not in owned or in_id in owned:
        raise AppError('Choose an owned player to sell and an unowned player to buy.')
    if out_id in team.locked_ids or in_id in team.excluded_ids:
        raise AppError('This transfer conflicts with your player preferences.')
    market = team.market.set_index('id')
    if in_id not in market.index:
        raise AppError('Incoming player is not in this market.')
    outgoing = team.squad.set_index('id').loc[out_id]
    incoming = market.loc[in_id]
    if outgoing.position != incoming.position:
        raise AppError('The players must have the same position.')
    if not bool(incoming.get('can_select', True)):
        raise AppError('The incoming player cannot be selected in FPL.')
    selected = (owned - {out_id}) | {in_id}
    if selected & team.excluded_ids:
        raise AppError("This transfer would keep an excluded player. Adjust your preferences or choose another plan.")
    _validate_holdings(team.market, sorted(selected))
    bank = int(team.bank + outgoing.selling_price - incoming.price)
    if bank < 0:
        raise AppError(f'This transfer needs another £{-bank / 10:.1f}m.')
    hit = 4 if team.free_transfers == 0 else 0
    weekly = team.weekly_market
    if weekly is None:
        weekly = team.market.assign(forecast_event=team.target_event)
    weeks = []
    for event, frame in weekly.groupby('forecast_event'):
        hold = optimal_lineup(frame[frame.id.isin(owned)])
        buy = optimal_lineup(frame[frame.id.isin(selected)])
        weeks.append({'event': int(event), 'hold': hold['expected_total'], 'buy': buy['expected_total'],
                      'gain': buy['expected_total'] - hold['expected_total'],
                      'out_points': float(frame.set_index('id').loc[out_id, 'recommended_points']),
                      'in_points': float(frame.set_index('id').loc[in_id, 'recommended_points'])})
    hold = sum(w['hold'] for w in weeks)
    buy = sum(w['buy'] for w in weeks)
    return {'out_id': out_id, 'in_id': in_id, 'out': str(outgoing['name']), 'in': str(incoming['name']),
            'hold_points': hold, 'buy_points': buy, 'hit': hit, 'net_gain': buy - hold - hit,
            'bank_after': bank, 'weeks': weeks, 'context': context(team),
            'players': {'outgoing': json.loads(team.squad[team.squad.id.eq(out_id)].to_json(orient='records'))[0],
                        'incoming': json.loads(team.market[team.market.id.eq(in_id)].to_json(orient='records'))[0]},
            'caveat': 'Expected XI + captain points, with lineups selected using your risk profile. No future transfers, price changes or free-transfer opportunity value are assumed.'}
