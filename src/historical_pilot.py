"""Bounded DGW25 source investigation; never promote commit dates to capture times."""
from pathlib import Path
import io
import json
import tempfile
import pandas as pd
from deadline_audit import fetch, latest

def investigate(root):
    root = Path(root)
    coverage = pd.read_csv(latest(root) / 'coverage.csv')
    row = coverage[(coverage.season == '2024-25') & (coverage.GW == 25)].iloc[0]
    deadline = row.deadline
    parent = root / 'data/raw/historical_pilot'
    parent.mkdir(parents=True, exist_ok=True)
    dest = Path(tempfile.mkdtemp(prefix='dgw25_', dir=parent))
    repo = 'vaastav/Fantasy-Premier-League'
    paths = ['data/2024-25/fixtures.csv', 'data/2024-25/gws/merged_gw.csv']
    results = []
    for path in paths:
        url = (f'https://api.github.com/repos/{repo}/commits?path={path}'
               '&until=2025-02-14T18:30:00Z&per_page=1')
        body, record = fetch(url, dest)
        if 'error' in record or not json.loads(body):
            results.append({'path': path, 'error': record.get('error', 'no commit')})
            continue
        commit = json.loads(body)[0]
        sha = commit['sha']
        body, detail_record = fetch(f'https://api.github.com/repos/{repo}/commits/{sha}', dest)
        detail = json.loads(body)
        body, source = fetch(f'https://raw.githubusercontent.com/{repo}/{sha}/{path}', dest)
        try:
            table = pd.read_csv(io.BytesIO(body), low_memory=False)
        except pd.errors.ParserError as exc:
            results.append({'path': path, 'commit': sha, 'source':source['url'],
                            'sha256':source['sha256'], 'schema_error':str(exc)})
            # Retain a single-GW file for inspecting the upstream schema change.
            fetch(f'https://raw.githubusercontent.com/{repo}/{sha}/data/2024-25/gws/gw24.csv',dest)
            continue
        evidence = {'path': path, 'commit': sha, 'commit_time': commit['commit']['committer']['date'],
                    'verification': detail['commit']['verification'], 'rows': len(table),
                    'source': source['url'], 'sha256': source['sha256']}
        if path.endswith('fixtures.csv'):
            fixtures = table[table.event.eq(25)]
            evidence['planned_GW25_fixtures'] = len(fixtures)
            evidence['teams_with_multiple_fixtures'] = pd.concat(
                [fixtures.team_h, fixtures.team_a]).value_counts().loc[lambda x: x > 1].to_dict()
            fixtures.to_csv(dest / 'candidate_gw25_fixtures.csv', index=False)
        else:
            timestamps = pd.to_datetime(table.kickoff_time, utc=True)
            evidence['latest_observed_kickoff'] = timestamps.max().isoformat()
            evidence['rows_kicking_off_at_or_after_deadline'] = int(timestamps.ge(pd.Timestamp(deadline)).sum())
            evidence['last_gw'] = int(table.GW.max())
        results.append(evidence)
        for source_path in ['global_scraper.py', 'getters.py']:
            fetch(f'https://raw.githubusercontent.com/{repo}/{sha}/{source_path}', dest)
        fetch(f'https://api.github.com/repos/{repo}/contents/.github/workflows?ref={sha}', dest)
    report = {'season': '2024-25', 'GW': 25, 'deadline': deadline,
              'candidate_sources': results, 'approved': False,
              'conclusion': 'Plausible historical versions found. Unsigned Git dates and scraper code '
                            'do not independently timestamp these exact API responses. No per-payload '
                            'capture manifest or retained workflow evidence established; strict audit remains blocked.'}
    (dest / 'report.json').write_text(json.dumps(report, indent=2, default=int))
    print(dest)
    print(json.dumps(report, indent=2, default=int))
    return dest

if __name__ == '__main__':
    investigate(Path(__file__).resolve().parents[1])
