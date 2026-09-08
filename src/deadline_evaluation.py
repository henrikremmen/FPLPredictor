"""Locked model evaluation on audited deadline features; no source substitution."""
import numpy as np
import pandas as pd
from improved_models import PointsModel, Blend
from model_experiments import metrics
from deadline_features import aggregate_predictions
from deadline_audit import utc

METHODS = ['form', 'hgb', 'ensemble']

def evaluate_fold(train, evaluation, truth):
    """Training labels are per planned fixture; evaluation truth is per player-GW.

    Caller must provide audit-approved rounds and label availability timestamps.
    Blank rows never train a fixture model; all registered players are evaluated.
    """
    if not train.audit_approved.all() or not evaluation.audit_approved.all():
        raise ValueError('Unaudited data cannot be evaluated')
    if train.empty or evaluation.empty:
        raise ValueError('Missing approved training/evaluation rows')
    train = train[train.planned_fixture].copy()
    cutoff = evaluation.deadline.map(utc).min()
    if not train.deadline.map(utc).lt(cutoff).all():
        raise ValueError('Train/evaluation chronology overlaps')
    if not train.labels_available_at.map(utc).lt(cutoff).all():
        raise ValueError('Training outcomes were unavailable at evaluation start')
    if train[['target_points', 'minutes']].isna().any().any():
        raise ValueError('Missing training labels')
    means = train.groupby('position').target_points.mean()
    fallback = evaluation.position.map(means).fillna(train.target_points.mean())
    form = evaluation.points_avg5.fillna(fallback).to_numpy()
    ridge = PointsModel('ridge', 7, False).fit(train)
    hgb = PointsModel('hgb', 7, False).fit(train)
    extended = PointsModel('hgb', 7, True).fit(train)
    mixture = PointsModel('mixture', 7, True).fit(train)
    ensemble = Blend([ridge, extended, mixture])
    models = {'hgb': hgb, 'ensemble': ensemble, 'form': {'position_means': means,
              'global_mean': train.target_points.mean()}}
    predictions = {'form': form, 'hgb': hgb.predict(evaluation), 'ensemble': ensemble.predict(evaluation)}
    tables = []
    for method, pred in predictions.items():
        report = aggregate_predictions(evaluation, pred, truth)
        report['method'] = method
        tables.append(report)
    result = pd.concat(tables, ignore_index=True)
    sizes = result.groupby('method').size()
    assert sizes.nunique() == 1
    return models, result

def decision_report(predictions):
    """Round-level metrics, rankings and captain: deterministic ID tie breaking."""
    scores, rankings, captains = [], [], []
    for (method, season, gw), g in predictions.groupby(['method', 'season', 'GW']):
        base = {'method': method, 'season': season, 'GW': gw}
        for segment, group in [('all', g), ('historical_60plus', g[g.minutes_avg5.ge(60)])]:
            if len(group):
                scores.append({**base, 'segment': segment, 'n': len(group),
                    **metrics(group.target_points, group.prediction)})
        for position in ['all', 'GK', 'DEF', 'MID', 'FWD']:
            group = g if position == 'all' else g[g.position.eq(position)]
            for k in [10, 25, 50]:
                top = group.sort_values(['prediction', 'player_id'], ascending=[False, True]).head(k)
                rankings.append({**base, 'position': position, 'k': k, 'n_selected': len(top),
                                 'actual_mean': top.target_points.mean()})
        candidates = g[g.planned_fixtures.gt(0)].sort_values(['prediction', 'player_id'], ascending=[False, True])
        if len(candidates):
            c = candidates.iloc[0]
            captains.append({**base, 'player_id': c.player_id, 'points': c.target_points,
                             'doubled_points': 2*c.target_points})
    captains = pd.DataFrame(captains)
    if not captains.empty:
        baseline = captains[captains.method.eq('form')][['season', 'GW', 'doubled_points']].rename(
            columns={'doubled_points': 'form_doubled_points'})
        captains = captains.merge(baseline, on=['season', 'GW'], validate='many_to_one')
        captains['gain_vs_form'] = captains.doubled_points - captains.form_doubled_points
    return pd.DataFrame(scores), pd.DataFrame(rankings), captains

def paired_bootstrap(predictions, draws=2000):
    """Paired MSE improvement vs form, resampling whole gameweeks."""
    keys = ['season', 'GW', 'player_id']
    baseline = predictions[predictions.method.eq('form')].set_index(keys)
    rows = []
    for method in ['hgb', 'ensemble']:
        other = predictions[predictions.method.eq(method)].set_index(keys)
        if set(other.index) != set(baseline.index):
            raise ValueError('Different evaluation universes')
        other = other.reindex(baseline.index)
        gain = (baseline.prediction-baseline.target_points)**2 - (other.prediction-other.target_points)**2
        blocks = gain.groupby(level=['season', 'GW']).agg(['sum', 'count'])
        rng = np.random.default_rng(42)
        sample = rng.integers(0, len(blocks), (draws, len(blocks)))
        values = blocks['sum'].to_numpy()[sample].sum(axis=1)/blocks['count'].to_numpy()[sample].sum(axis=1)
        rows.append({'method': method, 'MSE_gain': gain.mean(),
                     'low_95': np.quantile(values, .025), 'high_95': np.quantile(values, .975)})
    return pd.DataFrame(rows)
