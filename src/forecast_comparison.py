"""Compare genuinely frozen pre-deadline forecasts with local official outcomes."""
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fpl_app import _availability_factor


def read_json(path):
    path = Path(path)
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == '.gz'
                      else path.read_text())


def raw_directory(root, capture, manifest):
    # Resolve within this checkout even if the repository was moved.
    source = manifest.get('source_capture')
    return Path(root) / 'data/raw/live_fpl' / Path(source).name if source else capture


def catalog(root):
    rows = []
    for path in sorted((Path(root) / 'data/raw/live_fpl').glob('capture_*/manifest.json')):
        m = read_json(path)
        if m.get('status') != 'complete' or m.get('forecast_status') != 'experimental_frozen':
            continue
        raw = raw_directory(root, path.parent, m)
        bootstrap = read_json(raw / 'bootstrap.json.gz')
        events = {int(e['id']): e for e in bootstrap['events']}
        source = path.parent / 'horizon_forecast.csv'
        if not source.exists():
            source = path.parent / 'forecast.csv'
        forecast = pd.read_csv(source)
        at = pd.Timestamp(m['forecast_at'])
        for (season, gw), group in forecast.groupby(['season', 'GW']):
            event = events.get(int(gw))
            if event is None or at >= pd.Timestamp(event['deadline_time']):
                continue
            if group.player_id.duplicated().any():
                raise ValueError(f'Duplicate player forecasts: {source}, GW{gw}')
            rows.append(dict(season=season, GW=int(gw), snapshot=path.parent.name,
                             forecast_at=at, deadline=pd.Timestamp(event['deadline_time']),
                             model=m.get('model_family', 'legacy'), players=len(group),
                             forecast_file=str(source), raw_directory=str(raw)))
    return pd.DataFrame(rows).sort_values(['season', 'GW', 'forecast_at']).reset_index(drop=True) if rows else pd.DataFrame()


def outcome_source(root, season, gw):
    candidates = []
    for path in (Path(root) / 'data/raw/live_fpl').glob('capture_*/manifest.json'):
        m = read_json(path)
        if m.get('status') != 'complete' or m.get('season') != season or m.get('source_capture'):
            continue
        bootstrap_path = path.parent / 'bootstrap_closing.json.gz'
        if not bootstrap_path.exists():
            bootstrap_path = path.parent / 'bootstrap.json.gz'
        if not bootstrap_path.exists():
            continue
        bootstrap = read_json(bootstrap_path)
        event = next((e for e in bootstrap['events'] if e['id'] == int(gw)), {})
        if event.get('finished') and event.get('data_checked'):
            candidates.append((pd.Timestamp(m['finished_at']), path.parent))
    return max(candidates, key=lambda item: item[0]) if candidates else (None, None)


def compare(root, record):
    """Missing/unfinalized outcomes remain NaN; double-GW totals are summed."""
    forecast = pd.read_csv(record['forecast_file'])
    result = forecast[forecast.season.eq(record['season']) & forecast.GW.eq(record['GW'])].copy()
    bootstrap = read_json(Path(record['raw_directory']) / 'bootstrap.json.gz')
    players = {int(p['id']): p for p in bootstrap['elements']}
    teams = {int(t['id']): t['short_name'] for t in bootstrap.get('teams', [])}
    result['team'] = result.player_id.map(lambda pid: teams.get(players.get(pid, {}).get('team'), '?'))
    result['status_at_forecast'] = result.player_id.map(lambda pid: players.get(pid, {}).get('status'))
    result['news_at_forecast'] = result.player_id.map(lambda pid: players.get(pid, {}).get('news', ''))
    result['availability_at_forecast'] = result.player_id.map(
        lambda pid: _availability_factor(players[pid]) if pid in players else np.nan)
    result['app_prediction'] = result.prediction.clip(lower=0) * result.availability_at_forecast
    observed_at, source = outcome_source(root, record['season'], record['GW'])
    fields = {'actual_points': 'total_points', 'actual_minutes': 'minutes',
              'goals': 'goals_scored', 'assists': 'assists', 'bonus': 'bonus',
              'clean_sheets': 'clean_sheets'}
    actuals = []
    for pid in result.player_id:
        row = dict(player_id=pid, outcome_status='pending' if source is None else 'missing_history')
        row.update({key: np.nan for key in fields})
        path = source / f'player_{pid}.json.gz' if source else None
        if path is not None and path.exists():
            history = read_json(path).get('history')
            if isinstance(history, list):
                games = [g for g in history if g['round'] == int(record['GW'])]
                row.update({key: sum(g[field] for g in games) for key, field in fields.items()})
                row['outcome_status'] = 'final'
        actuals.append(row)
    result = result.merge(pd.DataFrame(actuals), on='player_id', validate='one_to_one')
    result['error'] = result.prediction - result.actual_points
    result['app_error'] = result.app_prediction - result.actual_points
    result['absolute_error'] = result.error.abs()
    result['app_absolute_error'] = result.app_error.abs()
    result.attrs.update(outcome_source=str(source) if source else None,
                        labels_observed_at=str(observed_at) if source else None)
    return result


def metrics(frame, score='prediction'):
    valid = frame.dropna(subset=[score, 'actual_points'])
    error = valid[score] - valid.actual_points
    return dict(players=len(frame), evaluated=len(valid), missing=len(frame)-len(valid),
                MAE=error.abs().mean(), RMSE=np.sqrt((error ** 2).mean()),
                bias=error.mean(), predicted_mean=valid[score].mean(),
                actual_mean=valid.actual_points.mean())
