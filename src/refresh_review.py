"""Export an auditable availability list and app scores from a frozen capture.

No network calls, model refitting or changes to the immutable input snapshot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from capture_fpl import read_gzip_json
from fpl_app import build_market


def review(root: Path, capture: Path, output: Path) -> dict:
    manifest = json.loads((capture / 'manifest.json').read_text())
    if (manifest.get('status') != 'complete' or
            manifest.get('forecast_status') != 'experimental_frozen'):
        raise ValueError('Review requires a complete, valid forecast')
    raw = Path(manifest.get('source_capture', capture))
    bootstrap = read_gzip_json(raw / 'bootstrap.json.gz')
    fixtures = read_gzip_json(raw / 'fixtures.json.gz')
    target = int(manifest['target_event']['id'])
    horizon = pd.read_csv(capture / 'horizon_forecast.csv')
    players = {int(p['id']): p for p in bootstrap['elements']
               if p['element_type'] in (1, 2, 3, 4)}
    markets = []
    for event, frame in horizon.groupby('GW'):
        if set(frame.player_id) != set(players) or frame.player_id.duplicated().any():
            raise ValueError(f'Incomplete or duplicated player coverage in GW{event}')
        market = build_market(bootstrap, fixtures, capture / 'forecast.csv', int(event))
        if not np.isfinite(market[['prediction', 'recommended_points']]).all().all():
            raise ValueError('Nonfinite forecast')
        if not market.loc[market.availability.eq(0), 'recommended_points'].eq(0).all():
            raise ValueError('Unavailable player has a nonzero recommendation')
        market.insert(0, 'GW', int(event))
        markets.append(market)
    scored = pd.concat(markets, ignore_index=True)
    current = scored[scored.GW.eq(target)].copy()
    if current.empty:
        raise ValueError('Target event missing from horizon')
    current['chance_of_playing_next_round'] = current.id.map(
        lambda pid: players[pid].get('chance_of_playing_next_round'))
    current['news_added'] = current.id.map(lambda pid: players[pid].get('news_added'))
    current['observed_at'] = manifest.get('started_at')
    current['source_url'] = 'https://fantasy.premierleague.com/api/bootstrap-static/'
    # Include suspensions/unavailability, but keep the official status category.
    flagged = current[current.status.ne('a') | current.availability.lt(1)].copy()
    flagged = flagged.sort_values(['selected_by_percent', 'id'], ascending=[False, True])

    previous = []
    for path in (root / 'data/raw/live_fpl').glob('capture_*/manifest.json'):
        try:
            old = json.loads(path.read_text())
            if (old.get('status') == 'complete' and
                    old.get('forecast_status') == 'experimental_frozen' and
                    old.get('season') == manifest.get('season') and
                    pd.Timestamp(old['started_at']) < pd.Timestamp(manifest['started_at'])):
                previous.append((pd.Timestamp(old['started_at']), path.parent, old))
        except (OSError, ValueError, KeyError):
            continue
    previous_capture = None
    changes = pd.DataFrame()
    if previous:
        _, previous_capture, old = max(previous, key=lambda item: item[0])
        old_raw = Path(old.get('source_capture', previous_capture))
        old_bootstrap = read_gzip_json(old_raw / 'bootstrap.json.gz')
        old_fixtures = read_gzip_json(old_raw / 'fixtures.json.gz')
        old_horizon = pd.read_csv(previous_capture / 'horizon_forecast.csv')
        if target in set(old_horizon.GW):
            old_market = build_market(old_bootstrap, old_fixtures,
                                      previous_capture / 'forecast.csv', target)
            fields = ['id', 'status', 'news', 'availability', 'price',
                      'prediction', 'recommended_points']
            changes = current.merge(old_market[fields], on='id', how='left',
                                    suffixes=('', '_previous'), validate='one_to_one')
            for field in ['price', 'prediction', 'recommended_points']:
                changes[field + '_change'] = changes[field] - changes[field + '_previous']
            changes['availability_changed'] = changes.availability.ne(changes.availability_previous)
            changes['news_changed'] = changes.news.ne(changes.news_previous)

    output.mkdir(parents=True, exist_ok=True)
    scored.to_csv(output / 'app_forecasts_by_gameweek.csv', index=False)
    flagged.to_csv(output / 'availability.csv', index=False)
    if not changes.empty:
        changes.to_csv(output / 'changes.csv', index=False)
    summary = {
        'capture': str(capture.resolve()), 'previous_capture': (
            str(previous_capture.resolve()) if previous_capture else None),
        'forecast_at': manifest['forecast_at'], 'target_event': target,
        'deadline': manifest['target_event']['deadline_time'],
        'players': len(current), 'forecast_rows': len(scored),
        'horizons': sorted(int(gw) for gw in horizon.GW.unique()),
        'status_counts': current.status.value_counts().to_dict(),
        'availability_changes': int(changes.availability_changed.sum()) if not changes.empty else None,
        'price_changes': int(changes.price_change.ne(0).sum()) if not changes.empty else None,
        'model_family': manifest.get('model_family'),
        'optional_sources': manifest.get('optional_sources'),
        'caveat': 'App availability multipliers are current FPL flags, not calibrated injury probabilities. '
                  'The app applies the same current multiplier across future gameweeks; recovery dates '
                  'and individual international minutes are not modelled.',
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(review(args.root, args.capture, args.output), indent=2))
