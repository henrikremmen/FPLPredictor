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
import tempfile
import time
import joblib
import numpy as np
import pandas as pd
import requests
from deadline_features import build_round

API = 'https://fantasy.premierleague.com/api/'
POSITIONS = {1:'GK', 2:'DEF', 3:'MID', 4:'FWD'}
RAW_STATS = ['minutes','starts','total_points','bps','ict_index','threat','creativity',
             'influence','saves','clean_sheets','expected_goals','expected_assists',
             'goals_scored','assists']

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

def upcoming(bootstrap):
    return next((e for e in bootstrap['events'] if e.get('is_next')), None)

def roster_signature(bootstrap):
    return sorted((p['id'],p['team'],p['element_type']) for p in bootstrap['elements'])

def normalize(bootstrap, fixtures, histories, records, season):
    at = records['bootstrap']['received_at']
    registry = pd.DataFrame([{'season':season,'player_id':p['id'],'team':p['team'],
        'position':POSITIONS[p['element_type']], 'name':p['web_name'],'available_at':at}
        for p in bootstrap['elements'] if p['element_type'] in POSITIONS])
    fat = records['fixtures']['received_at']
    schedule = pd.DataFrame([{'season':season,'fixture':f['id'],'GW':f['event'],
        'team_h':f['team_h'],'team_a':f['team_a'],'was_cancelled':False,
        'available_at':fat} for f in fixtures])
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

def run(root):
    root=Path(root)
    parent=root/'data/raw/live_fpl'
    parent.mkdir(parents=True,exist_ok=True)
    with (parent/'capture.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another capture is running; skipped.',flush=True)
            return None
        dest=Path(tempfile.mkdtemp(prefix='capture_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_',dir=parent))
        manifest={'started_at':now(),'status':'collecting','files':{},'forecast_status':'not_generated'}
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
                models=list((root/'artifacts/models').glob('improved_*/model.joblib'))
                if models:
                    model_path=max(models,key=lambda p:p.stat().st_mtime)
                    bundle=joblib.load(model_path)  # only locally trained user-owned artifacts
                    registry,schedule,ph,th=normalize(bootstrap,fixtures,histories,manifest['files'],season)
                    rows=build_round(season,target['id'],target['deadline_time'],registry,schedule,ph,th)
                    prediction=bundle['model'].predict(rows)
                    if not np.isfinite(prediction).all():
                        raise ValueError('Nonfinite predictions')
                    if pd.Timestamp(now())>=pd.Timestamp(target['deadline_time']):
                        manifest['forecast_status']='skipped_prediction_crossed_deadline'
                    else:
                        rows['prediction']=np.where(rows.planned_fixture,prediction,0.)
                        forecast=rows.groupby(['season','GW','player_id'],as_index=False).agg(
                            prediction=('prediction','sum'),name=('name','first'),position=('position','first'),
                            planned_fixtures=('planned_fixture','sum'))
                        forecast=forecast.sort_values(['prediction','player_id'],ascending=[False,True])
                        rows.to_csv(dest/'fixture_forecast.csv',index=False)
                        forecast.to_csv(dest/'forecast.csv',index=False)
                        manifest.update(forecast_status='experimental_frozen',forecast_at=now(),
                            model_path=str(model_path.resolve()),model_sha256=digest(model_path.read_bytes()),
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
    run(parser.parse_args().root)
