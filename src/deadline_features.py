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
from external_context import team_key


DEADLINE_NUMERIC_FIELDS = [
    'chance_of_playing_next_round', 'chance_of_playing_this_round', 'now_cost',
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
    'price_change_percent', 'price_change_hourly_rate',
    'price_change_projected_percent', 'team_strength',
    'team_strength_attack_home', 'team_strength_attack_away',
    'team_strength_defence_home', 'team_strength_defence_away',
    'team_strength_overall_home', 'team_strength_overall_away',
    'non_pl_matches_last7', 'non_pl_matches_last14', 'non_pl_matches_next7',
    'days_since_non_pl_match', 'days_to_non_pl_match',
    'cl_matches_last7', 'cl_matches_last14', 'days_since_cl_match',
]

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
    minutes = h.tail(5).minutes.sum(min_count=1)
    for raw, prefix in [
        ('bonus', 'bonus'), ('clearances_blocks_interceptions', 'CBI'),
        ('tackles', 'tackles'), ('recoveries', 'recoveries'),
        ('defensive_contribution', 'defensive_contribution'),
        ('yellow_cards', 'yellow_cards'),
    ]:
        if raw not in h:
            out[f'{prefix}_last5'] = np.nan
            if raw not in {'yellow_cards'}:
                out[f'{prefix}90_last5'] = np.nan
            continue
        total = h.tail(5)[raw].sum(min_count=1)
        out[f'{prefix}_last5'] = total
        if raw not in {'yellow_cards'}:
            out[f'{prefix}90_last5'] = 90 * total / minutes if minutes > 0 else np.nan
    out['bonus_avg5'] = h.tail(5).bonus.mean() if 'bonus' in h else np.nan
    out['defensive_contribution_rate5'] = (
        h.tail(5).defensive_contribution.gt(0).mean()
        if 'defensive_contribution' in h else np.nan
    )
    return out

def team_features(h, prefix):
    return {
        f'{prefix}_goals_for_per_game_before': h.goals_for.mean(),
        f'{prefix}_goals_against_per_game_before': h.goals_against.mean(),
        f'{prefix}_points_per_game_before': h.points.mean(),
        f'{prefix}_goals_scored_last5': h.tail(5).goals_for.sum(min_count=1),
        f'{prefix}_goals_conceded_last5': h.tail(5).goals_against.sum(min_count=1),
        f'{prefix}_points_last5': h.tail(5).points.sum(min_count=1),
        f'{prefix}_matches_last5': min(5, len(h)),
    }


def deadline_player_features(player, deadline):
    """Convert the pre-deadline registry snapshot into stable scalar features."""
    out = {}
    for field in DEADLINE_NUMERIC_FIELDS:
        out[field] = pd.to_numeric(getattr(player, field, np.nan), errors='coerce')
    status = str(getattr(player, 'status', '') or '')
    out.update(
        status_available=float(status == 'a'),
        status_doubtful=float(status == 'd'),
        status_injured_or_suspended=float(status in {'i', 's', 'u'}),
        price_change_calibrating=float(bool(
            getattr(player, 'price_change_calibrating', False)
        )),
    )
    chance = out['chance_of_playing_next_round']
    if pd.isna(chance) and status == 'a':
        chance = 100.0
    out['chance_of_playing_next_round'] = chance
    cutoff = utc(deadline)
    for source, feature in [
        ('birth_date', 'age_years'), ('team_join_date', 'team_tenure_days'),
        ('news_added', 'news_age_hours'),
    ]:
        value = getattr(player, source, None)
        parsed = pd.to_datetime(value, utc=True, errors='coerce')
        if pd.isna(parsed):
            out[feature] = np.nan
        elif source == 'birth_date':
            out[feature] = (cutoff - parsed).total_seconds() / (365.25 * 86400)
        elif source == 'team_join_date':
            out[feature] = (cutoff - parsed).total_seconds() / 86400
        else:
            out[feature] = max(0.0, (cutoff - parsed).total_seconds() / 3600)
    return out


def workload_features(player_history, team_history, team, deadline, kickoff):
    """Rest and congestion known at the deadline, using completed matches only."""
    cutoff = utc(deadline)
    kickoff = pd.to_datetime(kickoff, utc=True, errors='coerce')
    player_source = (player_history['kickoff_time'] if 'kickoff_time' in player_history
                     else pd.Series(index=player_history.index, dtype='datetime64[ns, UTC]'))
    player_times = pd.to_datetime(player_source, utc=True, errors='coerce')
    team_rows = team_history[team_history.team.eq(team)]
    team_source = (team_rows['kickoff_time'] if 'kickoff_time' in team_rows
                   else pd.Series(index=team_rows.index, dtype='datetime64[ns, UTC]'))
    team_times = pd.to_datetime(team_source, utc=True, errors='coerce')
    player_times = player_times[player_times.lt(cutoff)].dropna()
    team_times = team_times[team_times.lt(cutoff)].dropna()
    reference = kickoff if pd.notna(kickoff) else cutoff
    return {
        'days_until_kickoff': ((reference - cutoff).total_seconds() / 86400
                               if pd.notna(reference) else np.nan),
        'player_rest_days': ((reference - player_times.max()).total_seconds() / 86400
                             if len(player_times) else np.nan),
        'team_rest_days': ((reference - team_times.max()).total_seconds() / 86400
                           if len(team_times) else np.nan),
        'team_matches_last7': int(team_times.ge(reference - pd.Timedelta(days=7)).sum()),
        'team_matches_last14': int(team_times.ge(reference - pd.Timedelta(days=14)).sum()),
    }

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
    team_names = (players.dropna(subset=['team_name']).drop_duplicates('team')
                  .set_index('team')['team_name'].to_dict()
                  if 'team_name' in players else {})
    # Select latest version first, THEN event: moves out of a GW must be respected.
    schedule = asof(fixtures, deadline, ['fixture'], season)
    schedule = schedule[schedule.GW.eq(gw) & ~schedule.was_cancelled.astype(bool)]
    ph = history_before(player_history, deadline, ['player_id', 'fixture'], season)
    th = history_before(team_history, deadline, ['team', 'fixture'], season)
    rows = []
    for p in players.itertuples():
        player_history = ph[ph.player_id.eq(p.player_id)]
        pstats = player_features(player_history)
        tstats = team_features(th[th.team.eq(p.team)], 'team')
        matches = schedule[schedule.team_h.eq(p.team) | schedule.team_a.eq(p.team)]
        base = {'season': season, 'GW': gw, 'player_id': p.player_id, 'name': p.name,
                'player_key': getattr(p, 'player_key', p.name),
                'team_name': getattr(p, 'team_name', team_names.get(p.team)),
                'position': p.position, 'deadline': utc(deadline), **pstats, **tstats,
                **deadline_player_features(p, deadline)}
        if matches.empty:
            rows.append({**base, 'fixture': pd.NA, 'planned_fixture': False, 'was_home': np.nan,
                         **team_features(th.iloc[:0], 'opp')})
        for f in matches.itertuples():
            home = f.team_h == p.team
            opponent = f.team_a if home else f.team_h
            difficulty = (getattr(f, 'team_h_difficulty', np.nan) if home else
                          getattr(f, 'team_a_difficulty', np.nan))
            market_team = (getattr(f, 'market_home_win_probability', np.nan) if home else
                           getattr(f, 'market_away_win_probability', np.nan))
            market_opp = (getattr(f, 'market_away_win_probability', np.nan) if home else
                           getattr(f, 'market_home_win_probability', np.nan))
            market_team_goals = (getattr(f, 'market_home_expected_goals', np.nan) if home else
                                 getattr(f, 'market_away_expected_goals', np.nan))
            market_opp_goals = (getattr(f, 'market_away_expected_goals', np.nan) if home else
                                getattr(f, 'market_home_expected_goals', np.nan))
            market_clean_sheet = (
                getattr(f, 'market_home_clean_sheet_probability', np.nan) if home else
                getattr(f, 'market_away_clean_sheet_probability', np.nan)
            )
            props = getattr(f, 'market_player_props', {})
            props = props if isinstance(props, dict) else {}
            prop_key = team_key(getattr(p, 'player_key', p.name))
            workload = workload_features(
                player_history, th, p.team, deadline, getattr(f, 'kickoff_time', None)
            )
            opponent_features = team_features(th[th.team.eq(opponent)], 'opp')
            matchup = {
                'opp_team_name': team_names.get(opponent),
                'ppg_difference': (tstats['team_points_per_game_before']
                                   - opponent_features['opp_points_per_game_before']),
                'team_attack_vs_opp_defence': (tstats['team_goals_for_per_game_before']
                                               - opponent_features['opp_goals_against_per_game_before']),
                'team_defence_vs_opp_attack': (opponent_features['opp_goals_for_per_game_before']
                                               - tstats['team_goals_against_per_game_before']),
            }
            rows.append({**base, 'fixture': f.fixture, 'planned_fixture': True,
                         'was_home': float(home), 'fixture_difficulty': difficulty,
                         'market_team_win_probability': market_team,
                         'market_opponent_win_probability': market_opp,
                         'market_draw_probability': getattr(f, 'market_draw_probability', np.nan),
                         'market_over25_probability': getattr(f, 'market_over25_probability', np.nan),
                         'market_bookmakers': getattr(f, 'market_bookmakers', np.nan),
                         'market_team_expected_goals': market_team_goals,
                         'market_opponent_expected_goals': market_opp_goals,
                         'market_clean_sheet_probability': market_clean_sheet,
                         'market_player_goal_probability': props.get(f'{prop_key}:goal', np.nan),
                         'market_player_assist_probability': props.get(f'{prop_key}:assist', np.nan),
                         **workload, **matchup, **opponent_features})
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
