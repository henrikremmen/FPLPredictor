"""Capture public FPL data and freeze experimental forecasts before deadline.

One new directory per run. No credentials, transfers or FPL account writes.
The existing ensemble is experimental: trained on fixture-time historical data.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import argparse
import fcntl
import gzip
import hashlib
import json
import os
import tempfile
import time
import joblib
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from deadline_features import build_round
from external_context import (
    add_odds_to_schedule,
    add_player_props_to_schedule,
    enrich_registry_with_workload,
)

API = 'https://fantasy.premierleague.com/api/'
POSITIONS = {1:'GK', 2:'DEF', 3:'MID', 4:'FWD'}
RAW_STATS = ['minutes','starts','total_points','bps','ict_index','threat','creativity',
             'influence','saves','clean_sheets','expected_goals','expected_assists',
             'expected_goal_involvements','expected_goals_conceded',
             'goals_scored','assists','bonus','clearances_blocks_interceptions',
             'defensive_contribution','recoveries','tackles','yellow_cards','red_cards']

# Values published in bootstrap-static before the deadline.  Text is retained
# in the immutable raw JSON; the normalized table only contains model-friendly
# scalar values and timestamps.
DEADLINE_PLAYER_FIELDS = [
    'birth_date', 'team_join_date', 'status', 'chance_of_playing_next_round',
    'chance_of_playing_this_round', 'news_added', 'now_cost',
    'selected_by_percent', 'transfers_in', 'transfers_out',
    'transfers_in_event', 'transfers_out_event',
    'cost_change_event', 'cost_change_start',
    'form', 'points_per_game', 'ep_next', 'value_form', 'value_season',
    'total_points', 'minutes', 'starts', 'starts_per_90',
    'ict_index_rank', 'influence_rank', 'creativity_rank', 'threat_rank',
    'penalties_order', 'corners_and_indirect_freekicks_order',
    'direct_freekicks_order', 'defensive_contribution_per_90',
    'expected_goals_per_90', 'expected_assists_per_90',
    'expected_goal_involvements_per_90', 'expected_goals_conceded_per_90',
    'price_change_percent', 'price_change_hourly_rate', 'price_change_calibrating',
]
TEAM_STRENGTH_FIELDS = [
    'strength', 'strength_attack_home', 'strength_attack_away',
    'strength_defence_home', 'strength_defence_away',
    'strength_overall_home', 'strength_overall_away',
]

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def capture_endpoint(endpoint, directory, name):
    record = {'endpoint': endpoint, 'url': API+endpoint, 'started_at': now()}
    for attempt in range(3):
        try:
            r = requests.get(record['url'], timeout=(10, 35),
                headers={'User-Agent':'fplmodell-snapshot/1.0', 'Cache-Control':'no-cache'})
            record.update(received_at=now(), status=r.status_code,
                http_date=r.headers.get('Date'), age=r.headers.get('Age'))
            if r.status_code in [429, 500, 502, 503, 504] and attempt < 2:
                try:
                    delay = float(r.headers.get('Retry-After', 2**(attempt+1)))
                except ValueError:
                    delay = 5
                if delay > 30:
                    r.raise_for_status()  # defer long rate limits to a future run
                time.sleep(max(1, delay))
                continue
            r.raise_for_status()
            body = r.content
            data = r.json()
            path = directory / (name + '.json.gz')
            path.write_bytes(gzip.compress(body, mtime=0))
            record.update(file=path.name, sha256=digest(body), bytes=len(body),
                          stored_sha256=digest(path.read_bytes()))
            return data, record
        except (requests.RequestException, ValueError) as exc:
            record['error'] = str(exc)
            if attempt == 2 or record.get('status') == 429:
                return None, record
            time.sleep(attempt+1)
    return None, record


def capture_external_json(url, directory, name, *, headers=None, params=None,
                          public_endpoint=None):
    """Capture an optional external source without persisting credentials."""
    record = {
        'endpoint': public_endpoint or url, 'started_at': now(),
        'optional': True,
    }
    try:
        response = requests.get(
            url, headers=headers or {}, params=params or {}, timeout=(10, 35)
        )
        record.update(received_at=now(), status=response.status_code,
                      http_date=response.headers.get('Date'))
        response.raise_for_status()
        body = response.content
        payload = response.json()
        path = directory / (name + '.json.gz')
        path.write_bytes(gzip.compress(body, mtime=0))
        record.update(file=path.name, sha256=digest(body), bytes=len(body),
                      stored_sha256=digest(path.read_bytes()))
        return payload, record
    except (requests.RequestException, ValueError) as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
        return None, record


def capture_football_data_matches(directory, api_key, date_from, date_to):
    """Capture a long match window in the API's maximum ten-day chunks."""
    started = now()
    start = pd.Timestamp(date_from).normalize()
    final_exclusive = pd.Timestamp(date_to).normalize() + pd.Timedelta(days=1)
    matches: dict[int, dict] = {}
    windows, errors = [], []
    cursor = start
    while cursor < final_exclusive:
        end = min(cursor + pd.Timedelta(days=10), final_exclusive)
        params = {
            'dateFrom': cursor.date().isoformat(),
            # football-data v4 treats dateTo as exclusive.
            'dateTo': end.date().isoformat(),
        }
        try:
            response = requests.get(
                'https://api.football-data.org/v4/matches',
                headers={'X-Auth-Token': api_key}, params=params, timeout=(10, 35),
            )
            response.raise_for_status()
            payload = response.json()
            captured = payload.get('matches', [])
            for match in captured:
                match_id = match.get('id')
                if match_id is not None:
                    matches[int(match_id)] = match
            windows.append({
                **params, 'status': response.status_code, 'matches': len(captured),
            })
        except (requests.RequestException, ValueError) as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            errors.append({
                **params, 'status': status,
                'error': f'{type(exc).__name__}: {exc}',
            })
        cursor = end

    combined = {
        'filters': {'dateFrom': start.date().isoformat(),
                    'dateTo': final_exclusive.date().isoformat()},
        'resultSet': {'count': len(matches)},
        'matches': list(matches.values()),
    }
    body = json.dumps(combined, separators=(',', ':'), sort_keys=True).encode()
    path = directory / 'all_competitions.json.gz'
    path.write_bytes(gzip.compress(body, mtime=0))
    record = {
        'endpoint': 'football-data.org:v4/matches', 'optional': True,
        'started_at': started, 'received_at': now(),
        'status': 'complete' if not errors else 'partial',
        'windows_requested': len(windows) + len(errors),
        'windows_captured': len(windows), 'matches_captured': len(matches),
        'windows': windows, 'errors': errors,
        'file': path.name, 'sha256': digest(body), 'bytes': len(body),
        'stored_sha256': digest(path.read_bytes()),
    }
    # A completely failed optional source remains unavailable to feature code,
    # while its diagnostic record is still preserved in the manifest.
    return (combined if windows else None), record


def capture_player_props(events, directory, api_key):
    """Capture optional event-level goal and assist odds without storing the key."""
    started = now()
    payload, errors = [], []
    for event in events or []:
        event_id = str(event.get('id', ''))
        if not event_id:
            continue
        url = ('https://api.the-odds-api.com/v4/sports/soccer_epl/events/'
               f'{event_id}/odds/')
        try:
            response = requests.get(url, params={
                'apiKey': api_key, 'regions': 'us',
                'markets': 'player_goal_scorer_anytime,player_assists',
                'oddsFormat': 'decimal', 'dateFormat': 'iso',
            }, timeout=(10, 35))
            response.raise_for_status()
            payload.append(response.json())
        except (requests.RequestException, ValueError) as exc:
            errors.append({'event_id': event_id, 'error': f'{type(exc).__name__}: {exc}'})
    body = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
    path = directory / 'player_props.json.gz'
    path.write_bytes(gzip.compress(body, mtime=0))
    record = {
        'endpoint': 'the-odds-api:v4/event-odds:player-props',
        'optional': True, 'started_at': started, 'received_at': now(),
        'status': 'complete' if not errors else 'partial',
        'events_requested': len(events or []), 'events_captured': len(payload),
        'errors': errors, 'file': path.name, 'sha256': digest(body),
        'bytes': len(body), 'stored_sha256': digest(path.read_bytes()),
    }
    return payload, record


def capture_optional_context(root, directory, target):
    """Freeze official context plus opt-in odds and cross-competition schedules."""
    payloads, records = {}, {}
    for endpoint, name in [
        ('event-status/', 'event_status'),
        ('team/set-piece-notes/', 'set_piece_notes'),
    ]:
        payloads[name], records[name] = capture_endpoint(endpoint, directory, name)

    odds_key = os.getenv('ODDS_API_KEY')
    if odds_key:
        payloads['odds'], records['odds'] = capture_external_json(
            'https://api.the-odds-api.com/v4/sports/soccer_epl/odds/',
            directory, 'odds',
            params={
                'apiKey': odds_key, 'regions': 'uk,eu',
                'markets': 'h2h,totals', 'oddsFormat': 'decimal',
                'dateFormat': 'iso',
            },
            public_endpoint='the-odds-api:v4/sports/soccer_epl/odds',
        )
        include_props = os.getenv('ODDS_PLAYER_PROPS', '').strip().lower() in {
            '1', 'true', 'yes', 'on'
        }
        if include_props and payloads.get('odds'):
            payloads['player_props'], records['player_props'] = capture_player_props(
                payloads['odds'], directory, odds_key
            )
        else:
            records['player_props'] = {
                'optional': True, 'status': 'skipped',
                'reason': ('ODDS_PLAYER_PROPS is not enabled' if not include_props
                           else 'No matching odds events were returned'),
            }
    else:
        records['odds'] = {
            'optional': True, 'status': 'skipped',
            'reason': 'ODDS_API_KEY is not configured',
        }
        records['player_props'] = {
            'optional': True, 'status': 'skipped',
            'reason': 'ODDS_API_KEY is not configured',
        }

    football_key = os.getenv('FOOTBALL_DATA_API_KEY')
    if football_key and target is not None:
        deadline = pd.Timestamp(target['deadline_time'])
        date_from = (deadline - pd.Timedelta(days=14)).date().isoformat()
        date_to = (deadline + pd.Timedelta(days=45)).date().isoformat()
        payloads['all_competitions'], records['all_competitions'] = (
            capture_football_data_matches(
                directory, football_key, date_from, date_to,
            )
        )
    else:
        records['all_competitions'] = {
            'optional': True, 'status': 'skipped',
            'reason': ('FOOTBALL_DATA_API_KEY is not configured'
                       if not football_key else 'No future FPL deadline'),
        }
    return payloads, records

def upcoming(bootstrap):
    return next((e for e in bootstrap['events'] if e.get('is_next')), None)

def roster_signature(bootstrap):
    return sorted((p['id'],p['team'],p['element_type']) for p in bootstrap['elements'])

def normalize(bootstrap, fixtures, histories, records, season, optional=None):
    at = records['bootstrap']['received_at']
    teams = {int(team['id']): team for team in bootstrap.get('teams', [])}
    registry_rows = []
    for player in bootstrap['elements']:
        if player['element_type'] not in POSITIONS:
            continue
        team = teams.get(int(player['team']), {})
        projection = player.get('price_change_projections') or []
        projected = next((row.get('projected_percent') for row in projection
                          if row.get('offset') == 0), np.nan)
        row = {
            'season': season, 'player_id': player['id'], 'team': player['team'],
            'position': POSITIONS[player['element_type']], 'name': player['web_name'],
            'player_key': f"{player.get('first_name', '')}_{player.get('second_name', '')}".strip('_'),
            'team_name': team.get('name'),
            'available_at': at, 'price_change_projected_percent': projected,
        }
        row.update({field: player.get(field) for field in DEADLINE_PLAYER_FIELDS})
        row.update({f'team_{field}': team.get(field) for field in TEAM_STRENGTH_FIELDS})
        registry_rows.append(row)
    registry = pd.DataFrame(registry_rows)
    optional = optional or {}
    registry = enrich_registry_with_workload(
        registry, bootstrap, optional.get('all_competitions'), at
    )
    fat = records['fixtures']['received_at']
    schedule = pd.DataFrame([{'season':season,'fixture':f['id'],'GW':f['event'],
        'team_h':f['team_h'],'team_a':f['team_a'],'was_cancelled':False,
        'kickoff_time':f.get('kickoff_time'),
        'team_h_difficulty':f.get('team_h_difficulty'),
        'team_a_difficulty':f.get('team_a_difficulty'),
        'available_at':fat} for f in fixtures])
    schedule = add_odds_to_schedule(schedule, bootstrap, optional.get('odds'))
    schedule = add_player_props_to_schedule(schedule, optional.get('player_props'))
    finished = {f['id']:f for f in fixtures if f.get('finished') and
                f.get('team_h_score') is not None and f.get('team_a_score') is not None}
    teams=[]
    for f in finished.values():
        for side, other in [('h','a'),('a','h')]:
            gf, ga = f['team_'+side+'_score'], f['team_'+other+'_score']
            teams.append({'season':season,'team':f['team_'+side],'fixture':f['id'],
                'finished_at':fat, 'kickoff_time':f['kickoff_time'], 'available_at':fat,
                'goals_for':gf,'goals_against':ga,'points':3 if gf>ga else 1 if gf==ga else 0})
    players=[]
    for pid, payload in histories.items():
        hat = records[f'player_{pid}']['received_at']
        for h in payload['history']:
            if h['fixture'] not in finished:
                continue
            players.append({'season':season,'player_id':pid,'fixture':h['fixture'],
                'kickoff_time':h['kickoff_time'], 'finished_at':fat,'available_at':hat,
                **{s:pd.to_numeric(h.get(s,np.nan), errors='coerce') for s in RAW_STATS}})
    ph = pd.DataFrame(players, columns=['season','player_id','fixture','kickoff_time',
                                      'finished_at','available_at']+RAW_STATS)
    th = pd.DataFrame(teams, columns=['season','team','fixture','kickoff_time','finished_at',
                                    'available_at','goals_for','goals_against','points'])
    return registry,schedule,ph,th

def score_previous(parent, dest, bootstrap, histories, season, observed_at):
    checked = {e['id'] for e in bootstrap['events'] if e.get('finished') and e.get('data_checked')}
    rows=[]
    for path in sorted(parent.glob('capture_*/forecast.csv')):
        old_manifest=json.loads((path.parent/'manifest.json').read_text())
        if old_manifest.get('forecast_status')!='experimental_frozen':
            continue
        old = pd.read_csv(path)
        if old.empty or set(old.season) != {season} or int(old.GW.iloc[0]) not in checked:
            continue
        if not set(old.player_id).issubset(histories):
            continue
        gw = int(old.GW.iloc[0])
        for p in old.itertuples():
            actual = sum(h['total_points'] for h in histories[p.player_id]['history'] if h['round']==gw)
            rows.append({'forecast_path':str(path),'season':season,'GW':gw,'player_id':p.player_id,
                'prediction':p.prediction,'actual_points':actual,'labels_observed_at':observed_at})
    if rows:
        pd.DataFrame(rows).to_csv(dest/'observed_outcomes.csv', index=False)
    return len(rows)

def select_model_path(root):
    """Select a refitted production model, with legacy fallback."""
    parent = Path(root) / 'artifacts/models'
    candidates = list(parent.glob('improved_*/model.joblib'))
    for path in parent.glob('production_*/model.joblib'):
        try:
            settings = json.loads((path.parent / 'settings.json').read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if settings.get('production_eligible') is True:
            candidates.append(path)
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None

def score_rows(model, rows):
    """Attach expected points, playing-time probabilities and point quantiles."""
    result = rows.copy()
    prediction = model.predict(result)
    if not np.isfinite(prediction).all():
        raise ValueError('Nonfinite predictions')
    result['prediction'] = np.where(result.planned_fixture, prediction, 0.)
    probability_method = getattr(model, 'probabilities', None)
    probability = probability_method(result) if callable(probability_method) else None
    if probability is not None:
        if probability.shape != (len(result), 3) or not np.isfinite(probability).all():
            raise ValueError('Invalid playing-time probabilities')
        result['p_zero_minutes'] = np.where(result.planned_fixture, probability[:, 0], 1.)
        result['p_1_59_minutes'] = np.where(result.planned_fixture, probability[:, 1], 0.)
        result['p_60plus_minutes'] = np.where(result.planned_fixture, probability[:, 2], 0.)
    quantile_method = getattr(model, 'quantiles', None)
    quantiles = quantile_method(result) if callable(quantile_method) else None
    if quantiles is not None:
        if quantiles.shape != (len(result), 3) or not np.isfinite(quantiles).all():
            raise ValueError('Invalid point quantiles')
        for index, label in enumerate([10, 50, 90]):
            result[f'prediction_q{label}'] = np.where(
                result.planned_fixture, quantiles[:, index], 0.)
    return result

def aggregate_forecast(rows):
    aggregations = {
        'prediction': ('prediction', 'sum'), 'name': ('name', 'first'),
        'position': ('position', 'first'), 'planned_fixtures': ('planned_fixture', 'sum')}
    if 'p_60plus_minutes' in rows:
        aggregations.update(expected_60plus_appearances=('p_60plus_minutes', 'sum'))
    for column in [
        'market_clean_sheet_probability', 'market_team_expected_goals',
        'market_player_goal_probability', 'market_player_assist_probability',
    ]:
        if column in rows:
            aggregations[column] = (column, lambda values: values.sum(min_count=1))
    for label in [10, 50, 90]:
        column = f'prediction_q{label}'
        if column in rows:
            aggregations[column] = (column, 'sum')
    forecast = rows.groupby(['season','GW','player_id'],as_index=False).agg(**aggregations)
    if 'p_60plus_minutes' in rows:
        played = rows.assign(p_played=rows.p_1_59_minutes + rows.p_60plus_minutes)
        appearances = played.groupby(['season','GW','player_id']).p_played.sum()
        keys = pd.MultiIndex.from_frame(forecast[['season','GW','player_id']])
        forecast['expected_appearances'] = appearances.reindex(keys).to_numpy()
    return forecast.sort_values(['GW','prediction','player_id'],ascending=[True,False,True])

def read_gzip_json(path):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def read_optional_context(directory):
    result = {}
    for key, filename in [
        ('event_status', 'event_status.json.gz'),
        ('set_piece_notes', 'set_piece_notes.json.gz'),
        ('odds', 'odds.json.gz'),
        ('player_props', 'player_props.json.gz'),
        ('all_competitions', 'all_competitions.json.gz'),
    ]:
        path = Path(directory) / filename
        if path.exists():
            result[key] = read_gzip_json(path)
    return result

def rescore_latest(root):
    """Create a new forecast from the latest complete raw snapshot, without API calls."""
    started_at = now()
    root = Path(root)
    parent = root/'data/raw/live_fpl'
    sources = []
    for path in parent.glob('capture_*/manifest.json'):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if (manifest.get('status') == 'complete' and
                (path.parent/'bootstrap.json.gz').exists() and
                (path.parent/'fixtures.json.gz').exists()):
            sources.append(path.parent)
    if not sources:
        raise FileNotFoundError('No complete raw live snapshot to rescore')
    source = max(sources,key=lambda path:path.stat().st_mtime)
    source_manifest = json.loads((source/'manifest.json').read_text())
    bootstrap = read_gzip_json(source/'bootstrap.json.gz')
    fixtures = read_gzip_json(source/'fixtures.json.gz')
    histories = {int(player['id']):read_gzip_json(source/f"player_{player['id']}.json.gz")
                 for player in bootstrap['elements'] if (source/f"player_{player['id']}.json.gz").exists()}
    expected = {int(player['id']) for player in bootstrap['elements'] if player['element_type'] in POSITIONS}
    if set(histories) != expected:
        raise ValueError('Latest raw snapshot is incomplete')
    target = upcoming(bootstrap)
    if target is None or pd.Timestamp(now()) >= pd.Timestamp(target['deadline_time']):
        raise ValueError('Latest raw snapshot has no future stable deadline')
    model_path = select_model_path(root)
    if model_path is None:
        raise FileNotFoundError('No production-eligible local model')
    bundle = joblib.load(model_path)
    season = source_manifest['season']
    registry,schedule,ph,th = normalize(
        bootstrap,fixtures,histories,source_manifest['files'],season,
        read_optional_context(source))
    horizon_events = [event for event in bootstrap['events']
        if target['id'] <= event['id'] <= target['id']+7 and
        pd.Timestamp(now()) < pd.Timestamp(event['deadline_time'])]
    horizon_rows=[]
    for event in horizon_events:
        rows=build_round(season,event['id'],event['deadline_time'],registry,schedule,ph,th)
        horizon_rows.append(score_rows(bundle['model'],rows))
    horizon_fixture=pd.concat(horizon_rows,ignore_index=True)
    horizon=aggregate_forecast(horizon_fixture)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dest=Path(tempfile.mkdtemp(prefix=f'capture_{stamp}_rescore_',dir=parent))
    first_rows=horizon_fixture[horizon_fixture.GW.eq(target['id'])]
    aggregate_forecast(first_rows).to_csv(dest/'forecast.csv',index=False)
    first_rows.to_csv(dest/'fixture_forecast.csv',index=False)
    horizon.to_csv(dest/'horizon_forecast.csv',index=False)
    horizon_fixture.to_csv(dest/'horizon_fixture_forecast.csv',index=False)
    manifest={'started_at':started_at,'finished_at':now(),'status':'complete',
        'forecast_status':'experimental_frozen','season':season,'target_event':target,
        'forecast_at':now(),'forecast_horizons':[int(event['id']) for event in horizon_events],
        'model_path':str(model_path.resolve()),'model_sha256':digest(model_path.read_bytes()),
        'model_family':bundle.get('model_family','legacy_improved_blend'),
        'source_capture':str(source.resolve()),
        'source_manifest_sha256':digest((source/'manifest.json').read_bytes()),
        'model_caveat':'Rescored from an earlier raw snapshot; trained on pre-fixture features.'}
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='target_event'},indent=2),flush=True)
    print('Rescore directory:',dest,flush=True)
    return dest

def run(root, capture_phase='manual'):
    root=Path(root)
    load_dotenv(root / '.env')
    parent=root/'data/raw/live_fpl'
    parent.mkdir(parents=True,exist_ok=True)
    with (parent/'capture.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another capture is running; skipped.',flush=True)
            return None
        dest=Path(tempfile.mkdtemp(prefix='capture_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_',dir=parent))
        manifest={'started_at':now(),'status':'collecting','files':{},
                  'forecast_status':'not_generated','capture_phase':capture_phase}
        def save():
            (dest/'manifest.json').write_text(json.dumps(manifest,indent=2))
        save()
        try:
            bootstrap,bmeta=capture_endpoint('bootstrap-static/',dest,'bootstrap')
            fixtures,fmeta=capture_endpoint('fixtures/',dest,'fixtures')
            manifest['files'].update(bootstrap=bmeta,fixtures=fmeta)
            if bootstrap is None or fixtures is None:
                raise ValueError('Core API capture failed')
            target=upcoming(bootstrap)
            optional, optional_records = capture_optional_context(root, dest, target)
            manifest['files'].update(optional_records)
            manifest['optional_sources'] = {
                key: bool(value is not None) for key, value in optional.items()
            }
            first_year=pd.Timestamp(bootstrap['events'][0]['deadline_time']).year
            season=f'{first_year}-{str(first_year+1)[-2:]}'
            manifest.update(season=season,target_event=target)
            ids=[p['id'] for p in bootstrap['elements'] if p['element_type'] in POSITIONS]
            histories={}
            def capture_player(pid):
                time.sleep(.25)  # bounded four-worker request rate
                payload,meta=capture_endpoint(f'element-summary/{pid}/',dest,f'player_{pid}')
                return pid,payload,meta
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures=[pool.submit(capture_player,pid) for pid in ids]
                for i,future in enumerate(as_completed(futures),1):
                    pid,payload,meta=future.result()
                    manifest['files'][f'player_{pid}']=meta
                    if payload is not None and isinstance(payload.get('history'),list):
                        histories[pid]=payload
                    if i%100==0:
                        print(f'Captured {i}/{len(ids)} players',flush=True)
                        save()
            closing,cmeta=capture_endpoint('bootstrap-static/',dest,'bootstrap_closing')
            manifest['files']['bootstrap_closing']=cmeta
            manifest.update(expected_players=len(ids),captured_players=len(histories))
            if closing is None or len(histories)!=len(ids):
                raise ValueError('Incomplete snapshot: at least one API request failed')
            if roster_signature(bootstrap)!=roster_signature(closing):
                raise ValueError('Registry changed during capture; retry next run')
            manifest['status']='complete'
            manifest['outcome_rows']=score_previous(parent,dest,closing,histories,season,now())
            closing_target=upcoming(closing)
            stable = (target is not None and closing_target is not None and
                      (target['id'],target['deadline_time']) ==
                      (closing_target['id'],closing_target['deadline_time']))
            if not stable or pd.Timestamp(now())>=pd.Timestamp(target['deadline_time']):
                manifest['forecast_status']='skipped_no_stable_future_deadline'
            else:
                manifest['forecast_status']='no_model'
                model_path=select_model_path(root)
                if model_path is not None:
                    bundle=joblib.load(model_path)  # only locally trained user-owned artifacts
                    registry,schedule,ph,th=normalize(
                        bootstrap,fixtures,histories,manifest['files'],season,optional)
                    rows=build_round(season,target['id'],target['deadline_time'],registry,schedule,ph,th)
                    rows=score_rows(bundle['model'],rows)
                    if pd.Timestamp(now())>=pd.Timestamp(target['deadline_time']):
                        manifest['forecast_status']='skipped_prediction_crossed_deadline'
                    else:
                        forecast=aggregate_forecast(rows)
                        rows.to_csv(dest/'fixture_forecast.csv',index=False)
                        forecast.to_csv(dest/'forecast.csv',index=False)
                        horizon_events = [event for event in closing['events']
                            if target['id'] <= event['id'] <= target['id'] + 7 and
                            pd.Timestamp(now()) < pd.Timestamp(event['deadline_time'])]
                        horizon_rows = []
                        for event in horizon_events:
                            event_rows = build_round(season,event['id'],event['deadline_time'],
                                registry,schedule,ph,th)
                            horizon_rows.append(score_rows(bundle['model'],event_rows))
                        horizon_fixture = pd.concat(horizon_rows,ignore_index=True)
                        horizon = aggregate_forecast(horizon_fixture)
                        horizon_fixture.to_csv(dest/'horizon_fixture_forecast.csv',index=False)
                        horizon.to_csv(dest/'horizon_forecast.csv',index=False)
                        manifest.update(forecast_status='experimental_frozen',forecast_at=now(),
                            model_path=str(model_path.resolve()),model_sha256=digest(model_path.read_bytes()),
                            model_family=bundle.get('model_family', 'legacy_improved_blend'),
                            forecast_horizons=[int(event['id']) for event in horizon_events],
                            model_caveat='Trained on historical fixture-time features, not verified deadline features.')
                        if pd.Timestamp(manifest['forecast_at'])>=pd.Timestamp(target['deadline_time']):
                            manifest['forecast_status']='invalid_written_after_deadline'
        except Exception as exc:
            manifest['status']='failed'
            manifest['error']=f'{type(exc).__name__}: {exc}'
        finally:
            manifest['finished_at']=now()
            save()
            print(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2),flush=True)
            print('Capture directory:',dest,flush=True)
        return dest

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--rescore-latest',action='store_true',
                        help='Reuse latest complete raw snapshot with the newest eligible model')
    parser.add_argument('--phase', default='manual',
                        choices=['manual', '24h', '6h', '1h'],
                        help='Deadline checkpoint label stored in the manifest')
    args=parser.parse_args()
    rescore_latest(args.root) if args.rescore_latest else run(args.root, args.phase)
