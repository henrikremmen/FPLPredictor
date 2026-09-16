"""Chronological comparison of direct, playing-time mixture and blended models."""
import json
import tempfile
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.metrics import log_loss
from threadpoolctl import threadpool_limits
from model_experiments import TARGET, FEATURE_SETS, build_model, metrics, split

EXTRA = ['minutes_trend', 'points_trend', 'xG_per_observation', 'xA_per_observation',
         'recent_60_rate', 'attack_matchup', 'defence_matchup']

def enrich(data):
    d = data.copy()
    d['minutes_trend'] = d.minutes_avg3 - d.minutes_avg10
    d['points_trend'] = d.points_avg3 - d.points_avg10
    denominator = d.games_available_last5.replace(0, np.nan)
    d['xG_per_observation'] = d.xG_last5 / denominator
    d['xA_per_observation'] = d.xA_last5 / denominator
    d['recent_60_rate'] = d.games_60plus_last3 / d.games_available_last5.clip(upper=3).replace(0, np.nan)
    d['attack_matchup'] = (d.team_goals_for_per_game_before + d.opp_goals_against_per_game_before) / 2
    d['defence_matchup'] = (d.team_goals_against_per_game_before + d.opp_goals_for_per_game_before) / 2
    return d.replace([np.inf, -np.inf], np.nan)

def minutes_class(d):
    assert d.minutes.notna().all()
    return np.where(d.minutes.eq(0), 0, np.where(d.minutes.lt(60), 1, 2))

class PointsModel:
    """Serializable direct model or soft mixture: sum P(minutes band|X)*E(points|band,X)."""
    def __init__(self, kind='hgb', leaves=7, extended=False, classifier_leaves=7):
        self.kind, self.leaves, self.extended = kind, leaves, extended
        self.classifier_leaves = classifier_leaves

    def fit(self, train):
        cols = FEATURE_SETS['context'] + (EXTRA if self.extended else [])
        base, self.cols, self.dropped = build_model(
            'ridge' if self.kind == 'ridge' else 'hgb', train, cols,
            100. if self.kind == 'ridge' else self.leaves)
        with threadpool_limits(limits=4):
            if self.kind != 'mixture':
                self.direct = base.fit(train[self.cols], train[TARGET])
            else:
                self.prep = base.named_steps['preprocess']
                X = self.prep.fit_transform(train[self.cols])
                bands = minutes_class(train)
                self.classifier = (HistGradientBoostingClassifier(max_iter=120,
                    max_leaf_nodes=self.classifier_leaves,
                    learning_rate=.06, l2_regularization=10., early_stopping=False, random_state=42)
                    if len(np.unique(bands)) > 1 else DummyClassifier(strategy='prior'))
                self.classifier.fit(X, bands)
                self.experts = {}
                for band in self.classifier.classes_:
                    mask = bands == band
                    # Zero-minute outcomes are nearly constant. Use their training mean.
                    estimator = (DummyRegressor(strategy='mean') if band == 0 or mask.sum() < 50 else
                        HistGradientBoostingRegressor(max_iter=120, max_leaf_nodes=self.leaves,
                            learning_rate=.06, l2_regularization=10., early_stopping=False, random_state=42))
                    self.experts[int(band)] = estimator.fit(X[mask], train.loc[mask, TARGET])
        return self

    def predict(self, data):
        with threadpool_limits(limits=4):
            if self.kind != 'mixture':
                return self.direct.predict(data[self.cols])
            X = self.prep.transform(data[self.cols])
            probabilities = self.classifier.predict_proba(X)
            return sum(probabilities[:, j] * self.experts[int(b)].predict(X)
                       for j, b in enumerate(self.classifier.classes_))

    def probabilities(self, data):
        if self.kind != 'mixture':
            return None
        with threadpool_limits(limits=4):
            raw = self.classifier.predict_proba(self.prep.transform(data[self.cols]))
        out = np.zeros((len(data), 3))
        out[:, self.classifier.classes_.astype(int)] = raw
        return out

class Blend:
    def __init__(self, models):
        self.models = models

    def predict(self, data):
        return np.mean([m.predict(data) for m in self.models], axis=0)

class ProductionModel:
    """Use separately evaluated components for points and minutes uncertainty."""
    def __init__(self, points_model, probability_model, uncertainty_model=None):
        self.points_model = points_model
        self.probability_model = probability_model
        self.uncertainty_model = uncertainty_model

    def predict(self, data):
        return self.points_model.predict(data)

    def probabilities(self, data):
        return self.probability_model.probabilities(data)

    def quantiles(self, data):
        model = getattr(self, 'uncertainty_model', None)
        return model.predict_quantiles(data) if model is not None else None

class QuantilePointsModel:
    """Conditional point quantiles using the production context features."""
    def __init__(self, quantiles=(.1, .5, .9), leaves=15, extended=True):
        self.quantile_levels = tuple(float(q) for q in quantiles)
        self.leaves, self.extended = leaves, extended

    def fit(self, train):
        cols = FEATURE_SETS['context'] + (EXTRA if self.extended else [])
        base, self.cols, self.dropped = build_model('hgb', train, cols, self.leaves)
        self.prep = base.named_steps['preprocess']
        X = self.prep.fit_transform(train[self.cols])
        self.models = []
        with threadpool_limits(limits=4):
            for quantile in self.quantile_levels:
                model = HistGradientBoostingRegressor(
                    loss='quantile', quantile=quantile, max_iter=120,
                    max_leaf_nodes=self.leaves, learning_rate=.06,
                    l2_regularization=10., early_stopping=False, random_state=42)
                self.models.append(model.fit(X, train[TARGET]))
        return self

    def predict_quantiles(self, data):
        X = self.prep.transform(data[self.cols])
        with threadpool_limits(limits=4):
            raw = np.column_stack([model.predict(X) for model in self.models])
        # Finite samples can produce crossing quantile estimates. Sorting is the
        # standard monotonic repair and preserves the predicted set per row.
        return np.sort(raw, axis=1)

CONFIGS = {
    'ridge_reference': ('ridge', 7, False),
    'hgb_reference': ('hgb', 7, False),
    'hgb_extended7': ('hgb', 7, True),
    'hgb_extended15': ('hgb', 15, True),
    'minutes_mixture': ('mixture', 7, True),
}
BLENDS = {'blend_ridge_hgb': ['ridge_reference', 'hgb_extended7'],
          'blend_direct_minutes': ['hgb_extended7', 'minutes_mixture'],
          'blend_three': ['ridge_reference', 'hgb_extended7', 'minutes_mixture']}

def compare(data):
    results, outputs, classifier_results = [], [], []
    for validation_season, train_seasons in [('2023-24', ['2022-23']),
            ('2024-25', ['2022-23', '2023-24'])]:
        train, val = split(data, train_seasons, validation_season)
        preds = {}
        for name, config in CONFIGS.items():
            model = PointsModel(*config).fit(train)
            preds[name] = model.predict(val)
            if name == 'minutes_mixture':
                probability = model.probabilities(val)
                classifier_results.append({'season': validation_season,
                    'log_loss': log_loss(minutes_class(val), probability, labels=[0, 1, 2]),
                    'brier_60plus': np.mean((probability[:, 2] - (minutes_class(val) == 2))**2)})
        for name, components in BLENDS.items():
            preds[name] = np.mean([preds[c] for c in components], axis=0)
        for name, prediction in preds.items():
            eligible = val.minutes_avg5.ge(60)  # strictly historical cohort, not observed minutes
            results.append({'model': name, 'season': validation_season, 'n': len(val),
                'candidate_RMSE': metrics(val.loc[eligible, TARGET], prediction[eligible])['RMSE'],
                **metrics(val[TARGET], prediction)})
            report = val[['season', 'GW', 'fixture', 'player_id', 'position', 'minutes', TARGET]].copy()
            report['prediction'], report['model'] = prediction, name
            outputs.append(report)
        print('Completed validation:', validation_season, flush=True)
    folds = pd.DataFrame(results)
    # Equal weight per season, selected on validation only.
    summary = folds.groupby('model')[['RMSE', 'MAE', 'Spearman', 'candidate_RMSE']].mean().sort_values('RMSE')
    return folds, summary, pd.concat(outputs, ignore_index=True), pd.DataFrame(classifier_results)

def bootstrap_gain(oof, candidate, reference='hgb_reference'):
    """Paired gameweek-block bootstrap of MSE gain; descriptive after selection."""
    keys = ['season', 'GW', 'fixture', 'player_id']
    a = oof[oof.model.eq(candidate)].set_index(keys)
    b = oof[oof.model.eq(reference)].set_index(keys).reindex(a.index)
    gains = ((b.prediction - b[TARGET])**2 - (a.prediction - a[TARGET])**2)
    blocks = gains.groupby(level=['season', 'GW']).agg(['sum', 'count'])
    rng = np.random.default_rng(42)
    draws = rng.integers(0, len(blocks), size=(2000, len(blocks)))
    samples = blocks['sum'].to_numpy()[draws].sum(axis=1) / blocks['count'].to_numpy()[draws].sum(axis=1)
    return {'MSE_gain': gains.mean(), 'low_95': np.quantile(samples, .025),
            'high_95': np.quantile(samples, .975)}

def final_run(root, data, folds, summary, oof, classifier_results):
    winner = str(summary.index[0])
    train, test = split(data, ['2022-23', '2023-24', '2024-25'], '2025-26')
    names = BLENDS.get(winner, [winner])
    fitted = [PointsModel(*CONFIGS[name]).fit(train) for name in names]
    model = fitted[0] if len(fitted) == 1 else Blend(fitted)
    prediction = model.predict(test)
    baseline = PointsModel(*CONFIGS['hgb_reference']).fit(train).predict(test)
    report = test[['season', 'GW', 'fixture', 'player_id', 'name', 'position', 'minutes', TARGET]].copy()
    report['prediction'], report['reference_prediction'] = prediction, baseline
    report['error'] = prediction - report[TARGET]
    report['minutes_group'] = pd.cut(report.minutes, [-1, 0, 59, np.inf], labels=['0', '1–59', '60+'])
    parent = Path(root) / 'artifacts' / 'models'
    parent.mkdir(parents=True, exist_ok=True)
    dest = Path(tempfile.mkdtemp(prefix='improved_', dir=parent))
    folds.to_csv(dest / 'validation_folds.csv', index=False)
    summary.to_csv(dest / 'validation_summary.csv')
    oof.to_csv(dest / 'validation_predictions.csv', index=False)
    classifier_results.to_csv(dest / 'minutes_validation.csv', index=False)
    report.to_csv(dest / 'test_predictions.csv', index=False)
    scores = pd.DataFrame([{'model': winner, **metrics(test[TARGET], prediction)},
                           {'model': 'hgb_reference', **metrics(test[TARGET], baseline)}])
    scores.to_csv(dest / 'test_metrics.csv', index=False)
    joblib.dump({'model': model, 'raw_features': FEATURE_SETS['context'],
                 'preprocessing': 'Call improved_models.enrich before predict'}, dest / 'model.joblib')
    (dest / 'settings.json').write_text(json.dumps({'winner': winner,
        'selection': 'mean seasonal validation RMSE, 2023-24 and 2024-25',
        'test': '2025-26, previously explored', 'timing': 'pre-fixture, not deadline',
        'configs': CONFIGS, 'blends': BLENDS, 'seed': 42}, indent=2))
    return dest, scores, report
