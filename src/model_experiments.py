"""Shared, train-only preprocessing and evaluation for the three model notebooks."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from threadpoolctl import threadpool_limits
import joblib

TARGET = 'target_points'
CORE = ['minutes_last1', 'minutes_avg3', 'minutes_avg5', 'minutes_avg10',
        'games_60plus_last3', 'games_available_last5', 'games_played_season_before',
        'points_avg3', 'points_avg5', 'points_avg10', 'bps_avg5', 'ict_avg5',
        'threat_avg5', 'creativity_avg5', 'influence_avg5', 'position', 'was_home']
ATTACK = ['start_rate5', 'xG90_last5', 'xA90_last5', 'xG_last5', 'xA_last5',
          'goals_last5', 'assists_last5', 'clean_sheet_rate5', 'saves_avg5']
CONTEXT = ['team_goals_for_per_game_before', 'team_goals_against_per_game_before',
           'opp_goals_for_per_game_before', 'opp_goals_against_per_game_before',
           'team_points_per_game_before', 'opp_points_per_game_before',
           'team_goals_scored_last5', 'opp_goals_conceded_last5']
FEATURE_SETS = {'core': CORE, 'football': CORE + ATTACK, 'context': CORE + ATTACK + CONTEXT}
APPROVED_REVIEW = {'position', 'was_home'}

def load_data(root):
    root = Path(root)
    meta = pd.read_csv(root / 'data/processed/feature_metadata.csv')
    assert not meta.feature_name.duplicated().any()
    cols = list(dict.fromkeys(FEATURE_SETS['context'] +
        ['season', 'player_id', 'fixture', 'GW', 'kickoff_time', 'name', 'minutes', TARGET]))
    data = pd.read_csv(root / 'data/processed/player_fixture_features.csv', usecols=cols, low_memory=False)
    assert not data.duplicated(['season', 'player_id', 'fixture']).any()
    status = meta.set_index('feature_name').safe_for_prediction
    for c in FEATURE_SETS['context']:
        assert status[c] == 'SAFE' or (c in APPROVED_REVIEW and status[c] == 'REVIEW'), c
    data['position'] = data.position.replace({'GKP': 'GK'})
    data = data[data.position.isin(['GK', 'DEF', 'MID', 'FWD'])].copy()
    data['kickoff_time'] = pd.to_datetime(data.kickoff_time, utc=True, errors='raise')
    data['was_home'] = data.was_home.astype(str).str.lower().map({'true': 1., 'false': 0., '1': 1., '0': 0.})
    assert data.was_home.notna().all()
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=[TARGET])
    return data.sort_values(['kickoff_time', 'fixture', 'player_id']), meta

def split(data, train_seasons, evaluation_season):
    train = data[data.season.isin(train_seasons)].copy()
    evaluation = data[data.season.eq(evaluation_season)].copy()
    assert len(train) and len(evaluation)
    assert set(train.season) == set(train_seasons)
    assert train.kickoff_time.max() < evaluation.kickoff_time.min()
    return train, evaluation

def build_model(kind, train, columns, parameter):
    # Selection depends only on the current training rows, including during refit.
    usable = [c for c in columns if train[c].nunique(dropna=True) > 1]
    numeric = [c for c in usable if c != 'position']
    categorical = [c for c in usable if c == 'position']
    if kind == 'dummy':
        return DummyRegressor(strategy='mean'), [], []
    assert usable, 'No usable training features'
    if kind == 'ridge':
        num = Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True)),
                        ('scale', StandardScaler())])
        estimator = Ridge(alpha=parameter)
    else:
        assert kind == 'hgb'
        num = 'passthrough'
        estimator = HistGradientBoostingRegressor(max_iter=150, learning_rate=.06,
            max_leaf_nodes=parameter, l2_regularization=5., early_stopping=False, random_state=42)
    prep = ColumnTransformer([
        ('numeric', num, numeric),
        ('position', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical)])
    return Pipeline([('preprocess', prep), ('model', estimator)]), usable, [c for c in columns if c not in usable]

def metrics(y, prediction):
    y, prediction = np.asarray(y), np.asarray(prediction)
    rho = (pd.Series(y).corr(pd.Series(prediction), method='spearman')
           if np.unique(prediction).size > 1 and np.unique(y).size > 1 else np.nan)
    return {'MAE': mean_absolute_error(y, prediction),
            'RMSE': mean_squared_error(y, prediction) ** .5,
            'Spearman': rho, 'bias': float(np.mean(prediction - y)),
            'actual_mean': float(y.mean()), 'predicted_mean': float(prediction.mean())}

def fit_predict(kind, train, evaluation, feature_set, parameter):
    model, cols, dropped = build_model(kind, train, FEATURE_SETS[feature_set], parameter)
    Xtr = train[cols] if cols else np.zeros((len(train), 1))
    Xva = evaluation[cols] if cols else np.zeros((len(evaluation), 1))
    with threadpool_limits(limits=4):
        model.fit(Xtr, train[TARGET])
        prediction = model.predict(Xva)
    return model, cols, dropped, prediction

def search(kind, data):
    # Test labels are never used here. RMSE selects a conditional-mean points model.
    windows = [('2022-23', '2023-24'), ('2023-24',)]
    parameters = {'dummy': [0], 'ridge': [1., 100., 1000.], 'hgb': [7, 15]}[kind]
    sets = ['core'] if kind == 'dummy' else list(FEATURE_SETS)
    results = []
    for seasons in windows:
        tr, va = split(data, seasons, '2024-25')
        for feature_set in sets:
            for parameter in parameters:
                _, cols, dropped, pred = fit_predict(kind, tr, va, feature_set, parameter)
                results.append({'train_seasons': '|'.join(seasons), 'feature_set': feature_set,
                    'parameter': parameter, 'n_features': len(cols), 'dropped': ', '.join(dropped),
                    **metrics(va[TARGET], pred)})
        print(f'{kind}: ferdig med trening {seasons}', flush=True)
    return pd.DataFrame(results).sort_values(['RMSE', 'MAE']).reset_index(drop=True)

def refit(kind, data, best):
    seasons = best['train_seasons'].split('|') + ['2024-25']
    tr, test = split(data, seasons, '2025-26')
    parameter = int(best['parameter']) if kind == 'hgb' else float(best['parameter'])
    model, cols, dropped, prediction = fit_predict(kind, tr, test, best['feature_set'], parameter)
    report = test[['season', 'GW', 'fixture', 'player_id', 'name', 'position', 'minutes', TARGET]].copy()
    report['prediction'] = prediction
    report['error'] = prediction - report[TARGET]
    report['minutes_group'] = pd.cut(report.minutes, [-1, 0, 59, np.inf], labels=['0', '1–59', '60+'])
    return model, cols, dropped, report

def grouped_metrics(report, column):
    return pd.DataFrame([{'group': str(key), 'n': len(group), **metrics(group[TARGET], group.prediction)}
        for key, group in report.groupby(column, observed=True, dropna=False)])

def ranking(report):
    # Sum both fixtures for DGWs before selecting players. This is retrospective:
    # features for the second fixture were not frozen at the FPL deadline.
    weekly = report.groupby(['season', 'GW', 'player_id'], as_index=False)[[TARGET, 'prediction']].sum()
    rows = []
    for (season, gw), group in weekly.groupby(['season', 'GW']):
        for k in [10, 25, 50]:
            top = group.sort_values(['prediction', 'player_id'], ascending=[False, True]).head(k)
            oracle = group.nlargest(k, TARGET)
            rows.append({'season': season, 'GW': gw, 'k': k,
                'selected_mean_points': top[TARGET].mean(),
                'oracle_mean_points': oracle[TARGET].mean(),
                'regret_per_player': oracle[TARGET].mean() - top[TARGET].mean()})
    return pd.DataFrame(rows)

def save_run(root, kind, model, cols, search_results, report):
    # New directory on every run preserves prior experiments.
    import tempfile
    parent = Path(root) / 'artifacts' / 'models'
    parent.mkdir(parents=True, exist_ok=True)
    dest = Path(tempfile.mkdtemp(prefix=kind + '_', dir=parent))
    joblib.dump({'model': model, 'features': cols, 'target': TARGET}, dest / 'model.joblib')
    search_results.to_csv(dest / 'validation.csv', index=False)
    report.to_csv(dest / 'test_predictions.csv', index=False)
    pd.DataFrame([metrics(report[TARGET], report.prediction)]).to_csv(dest / 'test_metrics.csv', index=False)
    import sklearn
    manifest = {'model': kind, 'best_validation': search_results.iloc[0].to_dict(),
                'test_season': '2025-26', 'prediction_time': 'before each fixture, not GW deadline',
                'features': cols, 'sklearn': sklearn.__version__, 'numpy': np.__version__,
                'pandas': pd.__version__, 'seed': 42}
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return dest
