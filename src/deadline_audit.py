"""Archive evidence acquisition and fail-closed deadline coverage audit.

Run: python src/deadline_audit.py
Raw evidence is pinned to repository commits; downloaded_at is NOT available_at.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import tempfile
import requests
import pandas as pd

SEASONS = ['2022-23', '2023-24', '2024-25', '2025-26']
REPO = 'beeradb/FPL-Armband'

def utc(value):
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError('Timestamp must have a timezone')
    return t.tz_convert('UTC')

def sha256(body):
    return hashlib.sha256(body).hexdigest()

def fetch(url, directory):
    """Store raw successful responses and sidecars; failures remain evidence too."""
    key = hashlib.sha256(url.encode()).hexdigest()
    path = Path(directory) / (key + '.raw')
    sidecar = path.with_suffix('.json')
    if path.exists() and sidecar.exists():
        record = json.loads(sidecar.read_text())
        body = path.read_bytes()
        if sha256(body) != record['sha256']:
            raise ValueError(f'Cached evidence checksum mismatch: {path}')
        return body, record
    record = {'url': url, 'downloaded_at': datetime.now(timezone.utc).isoformat(),
              'available_at': None, 'path': str(path.resolve())}
    try:
        response = requests.get(url, timeout=(10, 45), headers={'User-Agent': 'fplmodell-deadline-audit'})
        record['status'] = response.status_code
        body = response.content
        record['sha256'] = sha256(body)
        path.write_bytes(body)
        if not response.ok:
            record['error'] = f'HTTP {response.status_code}'
    except requests.RequestException as exc:
        body = b''
        record['error'] = str(exc)
    sidecar.write_text(json.dumps(record, indent=2))
    return body, record

def verify_bootstrap(manifest, compressed, season, gw):
    """Verify upstream digest and independent payload timing, not folder names."""
    result = {'bootstrap_verified': False, 'deadline': None, 'captured_at': None,
              'players': 0, 'archive_source': None, 'reason': ''}
    try:
        raw = gzip.decompress(compressed)
        entry = next(x for x in manifest['files'] if x['endpoint'] == '/bootstrap-static/')
        if sha256(raw) != entry['sha256']:
            raise ValueError('bootstrap checksum mismatch')
        backfill = manifest['backfill']
        if backfill['season'] != season:
            raise ValueError('wrong archive season')
        if not backfill['source'].startswith('https://web.archive.org/web/'):
            raise ValueError('missing archive provenance')
        captured = utc(manifest['captured_at'])
        archive_time = pd.to_datetime(backfill['wayback_timestamp'], format='%Y%m%d%H%M%S', utc=True)
        if captured != archive_time:
            raise ValueError('archive and manifest timestamps differ')
        payload = json.loads(raw)
        event = next(e for e in payload['events'] if e['id'] == gw)
        deadline = utc(event['deadline_time'])
        if utc(manifest['event_deadline']) != deadline or manifest['event'] != gw:
            raise ValueError('manifest and payload deadline/event differ')
        if not captured < deadline:
            raise ValueError('snapshot is at or after deadline')
        if event.get('finished') or event.get('is_current') or event.get('data_checked'):
            raise ValueError('payload indicates deadline has passed')
        advanced = [e['id'] for e in payload['events'] if e.get('is_next')]
        if advanced and max(advanced) > gw:
            raise ValueError('payload has advanced to a later gameweek')
        players = payload['elements']
        ids = [p['id'] for p in players]
        teams = {t['id'] for t in payload['teams']}
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('empty or duplicate player registry')
        if any(p.get('team') not in teams or p.get('element_type') not in [1, 2, 3, 4, 5] for p in players):
            raise ValueError('invalid player position/team')
        result.update(bootstrap_verified=True, deadline=deadline.isoformat(),
            captured_at=captured.isoformat(), players=len(ids), archive_source=backfill['source'],
            snapshot_age_hours=(deadline-captured).total_seconds()/3600)
    except (ValueError, KeyError, StopIteration, TypeError, OSError) as exc:
        result['reason'] = f'bootstrap rejected: {exc}'
    return result

def acquire(root):
    root = Path(root)
    parent = root / 'data' / 'raw' / 'deadline_audit'
    parent.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='audit_', dir=parent))
    evidence = run / 'evidence'
    evidence.mkdir()
    # Evaluate independent sources, retaining their documentation and API responses.
    sources = [
        'https://raw.githubusercontent.com/Randdalf/fplcache/master/README.md',
        'https://raw.githubusercontent.com/Randdalf/fplcache/master/cache.py',
        'https://api.github.com/repos/Randdalf/fplcache/contents/cache',
        'https://raw.githubusercontent.com/TopMarx/fpl/main/README.md',
        'https://api.github.com/repos/TopMarx/fpl/contents/data',
        'https://raw.githubusercontent.com/TopMarx/fpl/main/data/2025/fetch-manifest.json',
        'https://raw.githubusercontent.com/TopMarx/fpl/main/data/2026/fetch-manifest.json',
        'https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/README.md',
    ]
    for url in sources:
        fetch(url, evidence)
    body, record = fetch(f'https://api.github.com/repos/{REPO}/commits/main', evidence)
    if 'error' in record:
        commit = None
    else:
        commit = json.loads(body)['sha']
    base = f'https://raw.githubusercontent.com/{REPO}/{commit}'
    if commit:
        fetch(base + '/docs/backfill.md', evidence)
    tasks = []
    for season in SEASONS:
        entries = []
        if commit:
            body, record = fetch(f'https://api.github.com/repos/{REPO}/contents/data/captures/{season}?ref={commit}', evidence)
            if 'error' not in record:
                entries = [x['name'] for x in json.loads(body) if x['type'] == 'dir' and x['name'].startswith('GW')]
            fetch(base + f'/data/captures/{season}/deadlines.json', evidence)
        for gw in range(1, 39):
            tasks.append((season, gw, [e for e in entries if e.startswith(f'GW{gw:02d}-')]))

    def audit_task(task):
        season, gw, folders = task
        candidates = []
        manifest_paths = []
        for folder in folders:
            prefix = base + f'/data/captures/{season}/{folder}'
            body, info = fetch(prefix + '/manifest.json', evidence)
            if 'error' in info:
                continue
            manifest_paths.append(info['path'])
            manifest = json.loads(body)
            blob, info = fetch(prefix + '/bootstrap-static.json.gz', evidence)
            if 'error' not in info:
                result = verify_bootstrap(manifest, blob, season, gw)
                # Backfill manifests only prove bootstrap, not history or fixtures.
                result['manifest_endpoints'] = '|'.join(x['endpoint'] for x in manifest.get('files', []))
                candidates.append(result)
        valid = [x for x in candidates if x['bootstrap_verified']]
        selected = max(valid, key=lambda x: x['captured_at']) if valid else {}
        reasons = []
        if not valid:
            reasons.append('no_verified_pre_deadline_bootstrap')
            reasons.extend(x['reason'] for x in candidates)
        reasons.extend(['no_verified_pre_deadline_fixture_snapshot',
                        'no_verified_asof_player_and_team_match_history'])
        return {'season': season, 'GW': gw, 'approved': False,
            'deadline_verified': bool(valid), 'registry_verified': bool(valid),
            'fixtures_verified': False, 'history_verified': False,
            **selected, 'excluded_reason': '; '.join(reasons),
            'manifest_paths': '|'.join(manifest_paths)}

    with ThreadPoolExecutor(max_workers=6) as executor:
        rows = list(executor.map(audit_task, tasks))
    coverage = pd.DataFrame(rows).sort_values(['season', 'GW'])
    coverage.to_csv(run / 'coverage.csv', index=False)
    settings = {'repository': REPO, 'commit': commit, 'seasons': SEASONS,
        'policy': 'strict pre-deadline evidence; no end-of-season feature substitution',
        'status': 'DATA_REPORT_ONLY', 'approved_gameweeks': int(coverage.approved.sum()),
        'note': 'Fixture/history coverage is not established by bootstrap payloads. '
                'This is coverage of inspected sources, not proof that no other archives exist.'}
    (run / 'settings.json').write_text(json.dumps(settings, indent=2))
    print(run, flush=True)
    print(coverage.groupby('season')[['deadline_verified', 'registry_verified', 'approved']].sum(), flush=True)
    return run

def latest(root):
    runs = list((Path(root) / 'data/raw/deadline_audit').glob('audit_*/coverage.csv'))
    if not runs:
        raise FileNotFoundError('Run python src/deadline_audit.py to acquire source evidence first.')
    return max(runs, key=lambda p: p.stat().st_mtime).parent

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    acquire(parser.parse_args().root)
