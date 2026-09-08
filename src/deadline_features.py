"""Pure feature reconstruction from normalized, timestamped archive records.

This module does NOT certify sources. Production callers must pass the source audit.
History tables must retain versions: available_at is the evidence-backed timestamp
of that version, never the date on which today's download took place.
"""
import numpy as np
import pandas as pd
from deadline_audit import utc
from model_experiments import FEATURE_SETS
from improved_models import enrich

def asof(table, cutoff, keys, season):
    d = table[table.season.eq(season)].copy()
    d['available_at'] = d.available_at.map(utc)
    d = d[d.available_at.lt(utc(cutoff))]
    if d.duplicated(keys + ['available_at']).any():
        raise ValueError('Conflicting/duplicate versions at same available_at')
    return d.sort_values('available_at').drop_duplicates(keys, keep='last')

def history_before(history, cutoff, keys, season):
    d = asof(history, cutoff, keys, season)
    # A kickoff alone does not prove that the match had finished.
    d['finished_at'] = d.finished_at.map(utc)
    d = d[d.finished_at.lt(utc(cutoff))]
    # Live API proves completion at capture time, not an exact final-whistle time.
    # Actual kickoff gives chronological match order when fixtures were postponed.
    order = 'kickoff_time' if 'kickoff_time' in d else 'finished_at'
    if order == 'kickoff_time':
        d[order] = d[order].map(utc)
    return d.sort_values([order, 'fixture'])

def player_features(h):
    out = {}
    for window in [3, 5, 10]:
        tail = h.tail(window)
        for raw, prefix in [('minutes', 'minutes'), ('total_points', 'points')]:
            out[f'{prefix}_avg{window}'] = tail[raw].mean()
    for raw, prefix in [('bps', 'bps'), ('ict_index', 'ict'), ('threat', 'threat'),
                        ('creativity', 'creativity'), ('influence', 'influence'), ('saves', 'saves')]:
        out[f'{prefix}_avg5'] = h.tail(5)[raw].mean()
    out['minutes_last1'] = h.minutes.iloc[-1] if len(h) else np.nan
    out['games_available_last5'] = min(5, len(h))
    out['games_played_season_before'] = h.minutes.gt(0).sum() if len(h) else 0
    out['games_60plus_last3'] = h.tail(3).minutes.ge(60).sum() if len(h) else np.nan
    out['start_rate5'] = h.tail(5).starts.mean()
    out['clean_sheet_rate5'] = h.tail(5).clean_sheets.mean()
    for raw, prefix in [('expected_goals', 'xG'), ('expected_assists', 'xA'),
                        ('goals_scored', 'goals'), ('assists', 'assists')]:
        total = h.tail(5)[raw].sum(min_count=1)
        out[f'{prefix}_last5'] = total
        if prefix in ['xG', 'xA']:
            minutes = h.tail(5).minutes.sum(min_count=1)
            out[f'{prefix}90_last5'] = 90 * total / minutes if minutes > 0 else np.nan
    return out

def team_features(h, prefix):
    return {
        f'{prefix}_goals_for_per_game_before': h.goals_for.mean(),
        f'{prefix}_goals_against_per_game_before': h.goals_against.mean(),
        f'{prefix}_points_per_game_before': h.points.mean(),
        **({f'{prefix}_goals_scored_last5': h.tail(5).goals_for.sum(min_count=1)}
           if prefix == 'team' else {f'{prefix}_goals_conceded_last5': h.tail(5).goals_against.sum(min_count=1)})}

def build_round(season, gw, deadline, registry, fixtures, player_history, team_history):
    """Return fixture rows, including one explicit blank row for blank-GW players.

    registry: season, player_id, team, position, name, available_at.
    fixtures: season, fixture, GW, team_h, team_a, was_cancelled, available_at.
    player_history: season, player_id, fixture, finished_at, available_at + raw stats.
    team_history: season, team, fixture, finished_at, available_at, goals_for,
                  goals_against, points. One record per team per fixture/version.
    """
    players = asof(registry, deadline, ['player_id'], season)
    if players.empty:
        raise ValueError('No pre-deadline registry')
    players = players[players.position.isin(['GK', 'DEF', 'MID', 'FWD'])]
    # Select latest version first, THEN event: moves out of a GW must be respected.
    schedule = asof(fixtures, deadline, ['fixture'], season)
    schedule = schedule[schedule.GW.eq(gw) & ~schedule.was_cancelled.astype(bool)]
    ph = history_before(player_history, deadline, ['player_id', 'fixture'], season)
    th = history_before(team_history, deadline, ['team', 'fixture'], season)
    rows = []
    for p in players.itertuples():
        pstats = player_features(ph[ph.player_id.eq(p.player_id)])
        tstats = team_features(th[th.team.eq(p.team)], 'team')
        matches = schedule[schedule.team_h.eq(p.team) | schedule.team_a.eq(p.team)]
        base = {'season': season, 'GW': gw, 'player_id': p.player_id, 'name': p.name,
                'position': p.position, 'deadline': utc(deadline), **pstats, **tstats}
        if matches.empty:
            rows.append({**base, 'fixture': pd.NA, 'planned_fixture': False, 'was_home': np.nan,
                         **team_features(th.iloc[:0], 'opp')})
        for f in matches.itertuples():
            home = f.team_h == p.team
            opponent = f.team_a if home else f.team_h
            rows.append({**base, 'fixture': f.fixture, 'planned_fixture': True, 'was_home': float(home),
                         **team_features(th[th.team.eq(opponent)], 'opp')})
    output = pd.DataFrame(rows)
    assert not output.duplicated(['season', 'GW', 'player_id', 'fixture']).any()
    assert set(FEATURE_SETS['context']).issubset(output.columns)
    return enrich(output)

def aggregate_predictions(rows, prediction, truth):
    """Truth is a separate complete player-GW table, including certified zeros."""
    keys = ['season', 'GW', 'player_id']
    if truth.duplicated(keys).any():
        raise ValueError('Duplicate player-GW truth')
    d = rows.copy()
    d['prediction'] = np.where(d.planned_fixture, prediction, 0.)
    result = d.groupby(keys, as_index=False).agg(prediction=('prediction', 'sum'),
        planned_fixtures=('planned_fixture', 'sum'), position=('position', 'first'),
        minutes_avg5=('minutes_avg5', 'first'))
    result = result.merge(truth[keys + ['target_points']], on=keys, how='left', validate='one_to_one')
    if result.target_points.isna().any():
        raise ValueError('Incomplete ground truth; do not invent zero outcomes')
    return result
