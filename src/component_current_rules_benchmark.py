"""Diagnostic current-rule comparison after learning early 2025/26 DEFCON.

Historical features/odds are not deadline-certified. This is a chronological
development split, not an untouched holdout or a production promotion gate.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from component_benchmark import COMPONENT_COLUMNS
from component_models import CoherentComponentPointsModel
from improved_models import EXTRA
from market_models import ALL_MARKET_FEATURES
from model_experiments import FEATURE_SETS, build_model
from model_lab import KEYS
from nextgen_models import fit_incumbent, score_prediction
from shot_benchmark import load_source_training_data


def run_decisions(root):
    from decision_backtest import backtest, cached_market, paired_bootstrap, prepare_predictions
    from source_decision_benchmark import validate_comparison
    root = Path(root)
    dest = root / 'artifacts/model_research/component_current_rules'
    predictions = pd.read_csv(dest / 'predictions.csv')
    models = ['market_reference', 'component_v2']
    markets = {season: cached_market(root, season) for season in predictions.season.unique()}
    prepared = prepare_predictions(predictions, markets, models, burn_in=0)
    validate_comparison(prepared, models)
    gameweeks, summary, _ = backtest(prepared, models)
    comparison = paired_bootstrap(gameweeks, models[1], models[0])
    gameweeks.to_csv(dest / 'decision_gameweeks.csv', index=False)
    summary.to_csv(dest / 'decision_summary.csv')
    report = {'production_eligible': False, 'status': 'retrospective_diagnostic',
              'scope': 'Independent legal 100m squad, XI and captain per gameweek',
              'limitations': ['Post-gameweek prices', 'Not deadline-certified',
                             'No transfers, autosubs, vice-captain or chips'],
              'comparison': comparison}
    (dest / 'decision_report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print(summary.to_string(), flush=True)
    print(json.dumps(comparison), flush=True)


def run(root):
    root = Path(root)
    data = load_source_training_data(root)
    targets = pd.read_csv(root / 'data/processed/player_fixture_features.csv',
                          usecols=COMPONENT_COLUMNS, low_memory=False)
    additions = [c for c in targets if c in KEYS or c not in data]
    data = data.merge(targets[additions], on=KEYS, validate='one_to_one')
    # Leave GW19 out: training results must precede the first test kickoff,
    # including rearranged matches from otherwise earlier numbered rounds.
    test = data[data.season.eq('2025-26') & data.GW.ge(20)].copy()
    cutoff = test.kickoff_time.min() - pd.Timedelta(days=1)
    train = data[(data.season.lt('2025-26') |
                  (data.season.eq('2025-26') & data.GW.le(18))) &
                 data.kickoff_time.lt(cutoff)].copy()
    assert len(test) and len(train)
    reports, predictions = [], []
    with threadpool_limits(limits=4):
        fallback = fit_incumbent(train[train.season.ge('2022-23')])
        columns = FEATURE_SETS['context'] + EXTRA + ALL_MARKET_FEATURES
        market, columns, _ = build_model('hgb', train, columns, 7)
        market.fit(train[columns], train.target_points)
        covered = test[['market_team_expected_goals', 'market_opponent_expected_goals',
                        'market_clean_sheet_probability']].notna().all(axis=1)
        values = np.where(covered, market.predict(test[columns]), fallback.predict(test))
        print('Market reference fitted', flush=True)
        component = CoherentComponentPointsModel().fit(train)
        assert component.has_defcon, 'Current-rule comparison requires DEFCON training'
        for name, prediction in [('market_reference', values),
                                 ('component_v2', component.predict(test))]:
            report = {'model': name, **score_prediction(test, prediction)}
            report = {key: None if isinstance(value, float) and not np.isfinite(value)
                      else value for key, value in report.items()}
            reports.append(report)
            frame = test[KEYS + ['target_points', 'position']].copy()
            frame['model'], frame['prediction'] = name, prediction
            predictions.append(frame)
            print(json.dumps(report), flush=True)
        contributions = component.point_contributions(test)
    dest = root / 'artifacts/model_research/component_current_rules'
    dest.mkdir(parents=True, exist_ok=False)
    pd.concat(predictions).to_csv(dest / 'predictions.csv', index=False)
    pd.concat([test[KEYS].reset_index(drop=True), contributions.reset_index(drop=True)],
              axis=1).to_csv(dest / 'contributions.csv', index=False)
    report = {'production_eligible': False, 'status': 'retrospective_diagnostic',
              'train_rows': len(train), 'test_rows': len(test),
              'train_cutoff_exclusive': str(cutoff), 'test_season': '2025-26',
              'test_gw_min': 20, 'training_current_season_gw_max': 18,
              'defcon_enabled': bool(component.has_defcon),
              'caveat': 'Fixture-shifted features and historical odds lack predeadline certification; no promotion.',
              'metrics': reports}
    (dest / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decisions-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.decisions_only:
        run(root)
    run_decisions(root)
