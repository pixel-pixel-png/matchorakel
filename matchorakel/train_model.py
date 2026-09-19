"""Träna och granska en egen modell per liga med tidsordnade perioder."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from football import FEATURES, EXTENDED_FEATURES, RICH_FEATURES, LEAGUES, ODDS, build_dataset, build_event_history, known_teams, load_matches
from goal_model import GoalModel

ROOT = Path(__file__).resolve().parent
LABELS = ('H', 'D', 'A')


def models():
    logistic = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    forest = lambda: RandomForestClassifier(n_estimators=220, min_samples_leaf=5, random_state=42, n_jobs=-1)
    return {
        'Klassfrekvens': DummyClassifier(strategy='prior'),
        'Lika sannolikhet': DummyClassifier(strategy='uniform', random_state=42),
        'Logistisk regression': logistic(),
        'Random Forest': forest(),
        'Kombinerad modell': VotingClassifier(
            estimators=[('logistic', logistic()), ('forest', forest())], voting='soft'),
        'Poissonmål': GoalModel(),
    }


def candidate_specs():
    return {
        f'{name} · form': (name, FEATURES)
        for name in ('Logistisk regression', 'Random Forest', 'Kombinerad modell', 'Poissonmål')
    } | {
        f'{name} · form + hemmaplan': (name, EXTENDED_FEATURES)
        for name in ('Logistisk regression', 'Random Forest', 'Kombinerad modell', 'Poissonmål')
    } | {
        f'{name} · form + hemmaplan + lagstyrka + vila': (name, RICH_FEATURES)
        for name in ('Logistisk regression', 'Random Forest', 'Kombinerad modell', 'Poissonmål')
    }


def fit_model(model, samples, names):
    target = samples[['home_goals', 'away_goals']] if isinstance(model, GoalModel) else samples.outcome
    model.fit(samples[names], target)
    return model


def market_scores(model, samples, names):
    predictions = model.goal_markets(samples[names])
    result = {}
    targets = {'over_2_5': (samples.home_goals + samples.away_goals >= 3).to_numpy(),
               'over_1_5': (samples.home_goals + samples.away_goals >= 2).to_numpy(),
               'both_score': ((samples.home_goals > 0) & (samples.away_goals > 0)).to_numpy()}
    for market, actual in targets.items():
        probability = np.clip([row[market] for row in predictions], 1e-9, 1 - 1e-9)
        result[market] = round(float(np.mean((probability - actual) ** 2)), 4)
    return result


def probability_scores(y, probability):
    actual = np.column_stack([(y.to_numpy() == label).astype(float) for label in LABELS])
    predicted = np.array(LABELS)[probability.argmax(axis=1)]
    picked = probability[np.arange(len(y)), actual.argmax(axis=1)]
    return {
        'accuracy': round(float(accuracy_score(y, predicted)), 4),
        'log_loss': round(float(-np.log(np.clip(picked, 1e-15, 1)).mean()), 4),
        'brier': round(float(np.mean(np.sum((probability - actual) ** 2, axis=1))), 4),
    }


def scores(model, sample, feature_names=FEATURES):
    raw = model.predict_proba(sample[feature_names])
    by_label = {label: raw[:, i] for i, label in enumerate(model.classes_)}
    probability = np.column_stack([by_label[label] for label in LABELS])
    return probability_scores(sample.outcome, probability), probability, np.array(LABELS)[probability.argmax(axis=1)]


def split_by_date(samples):
    dates = sorted(samples.date.unique())
    if len(dates) < 30:
        raise ValueError('För få olika matchdagar för tre tidsperioder.')
    cut1, cut2 = dates[int(.6 * len(dates))], dates[int(.8 * len(dates))]
    train = samples[samples.date < cut1]
    validation = samples[(samples.date >= cut1) & (samples.date < cut2)]
    test = samples[samples.date >= cut2]
    if min(len(train), len(validation), len(test)) < 30:
        raise ValueError('För få matcher i en av de tre tidsperioderna.')
    if set(train.outcome) != set(LABELS):
        raise ValueError('Träningsperioden behöver innehålla H, D och A.')
    return train, validation, test


def span(frame):
    return {'first': str(frame.date.min().date()), 'last': str(frame.date.max().date()), 'matches': len(frame)}


def train_league(league):
    meta = LEAGUES[league]
    matches = load_matches(ROOT / meta['folder'], league)
    samples, history, venue_history, ratings, last_played = build_dataset(matches)
    if len(samples) < 150:
        raise ValueError('För få matcher med fem tidigare resultat för båda lagen. Hämta fler säsonger.')
    train, validation, test = split_by_date(samples)
    validation_metrics = {}
    for name, model in models().items():
        if name not in ('Klassfrekvens', 'Lika sannolikhet'):
            continue
        fit_model(model, train, FEATURES)
        validation_metrics[name] = scores(model, validation)[0]
    candidates = candidate_specs()
    for name, (method, feature_names) in candidates.items():
        model = models()[method]
        fit_model(model, train, feature_names)
        validation_metrics[name] = scores(model, validation, feature_names)[0]

    # Endast valideringsperioden bestämmer modellvalet.
    selected = min(candidates, key=lambda name: validation_metrics[name]['log_loss'])
    selected_method, selected_features = candidates[selected]
    development = pd.concat([train, validation], ignore_index=True)
    evaluated = {}
    for name in ('Klassfrekvens', 'Lika sannolikhet', selected):
        method, feature_names = candidates[name] if name == selected else (name, FEATURES)
        model = models()[method]
        fit_model(model, development, feature_names)
        evaluated[name] = (model, *scores(model, test, feature_names))
    selected_model, selected_scores, probabilities, predictions = evaluated[selected]
    goal_features = RICH_FEATURES
    goal_validation_model = fit_model(GoalModel(), train, goal_features)
    goal_validation = market_scores(goal_validation_model, validation, goal_features)
    baseline_validation = {}
    # Baslinjen mäts på valideringsmatcherna med träningsperiodens frekvens.
    for name in goal_validation:
        train_rate = {'over_2_5': ((train.home_goals + train.away_goals) >= 3).mean(),
                      'over_1_5': ((train.home_goals + train.away_goals) >= 2).mean(),
                      'both_score': ((train.home_goals > 0) & (train.away_goals > 0)).mean()}[name]
        observed = {'over_2_5': ((validation.home_goals + validation.away_goals) >= 3).to_numpy(),
                    'over_1_5': ((validation.home_goals + validation.away_goals) >= 2).to_numpy(),
                    'both_score': ((validation.home_goals > 0) & (validation.away_goals > 0)).to_numpy()}[name]
        baseline_validation[name] = round(float(np.mean((observed - train_rate)**2)), 4)
    allowed_markets = {name: goal_validation[name] < baseline_validation[name] for name in goal_validation}
    goal_test_model = fit_model(GoalModel(), development, goal_features)
    goal_test = market_scores(goal_test_model, test, goal_features)
    confusion = confusion_matrix(test.outcome, predictions, labels=LABELS)
    recall = {label: round(float(confusion[i, i] / confusion[i].sum()), 4)
              if confusion[i].sum() else None for i, label in enumerate(LABELS)}

    folder = ROOT / 'artifacts'
    folder.mkdir(exist_ok=True)
    rows = test[['date', 'home', 'away', 'outcome']].copy()
    rows['predicted'] = predictions
    for i, label in enumerate(LABELS):
        rows[f'prob_{label}'] = probabilities[:, i].round(5)

    odds_benchmark = None
    if set(ODDS).issubset(test.columns):
        odds = test[list(ODDS)].to_numpy(dtype=float)
        valid = np.isfinite(odds).all(axis=1) & (odds > 1).all(axis=1)
        if valid.sum() >= 20:
            implied = 1 / odds[valid]
            implied /= implied.sum(axis=1, keepdims=True)  # ta bort inbyggd marginal
            market = implied[:, [0, 1, 2]]  # AvgH, AvgD, AvgA = LABELS
            subset = test.iloc[np.flatnonzero(valid)]
            odds_benchmark = {
                'matches': len(subset),
                'market': probability_scores(subset.outcome, market),
                'selected_model_same_matches': probability_scores(subset.outcome, probabilities[valid]),
                'method': 'Normaliserade 1/AvgH, 1/AvgD, 1/AvgA på testmatcher med alla tre odds.',
            }
            for i, label in enumerate(LABELS):
                rows[f'market_prob_{label}'] = np.nan
                rows.loc[valid, f'market_prob_{label}'] = market[:, i].round(5)
    rows.to_csv(folder / f'test_predictions_{league}.csv', index=False)

    report = {
        'league': meta['name'], 'source': 'football-data.co.uk',
        'source_matches': len(matches), 'usable_matches': len(samples),
        'periods': {'train': span(train), 'validation': span(validation), 'test': span(test)},
        'selected_model': selected, 'selection_metric': 'validation log_loss',
        'selected_features': selected_features,
        'validation': validation_metrics,
        'test': {name: values[1] for name, values in evaluated.items()},
        'odds_benchmark': odds_benchmark,
        'goal_markets': {'validation_brier': goal_validation,
                         'validation_baseline_brier': baseline_validation,
                         'test_brier': goal_test, 'enabled': allowed_markets},
        'test_confusion': {'labels': list(LABELS), 'matrix': confusion.tolist(), 'recall': recall},
        'latest_result': str(matches.Date.max().date()),
        'limitations': [
            'Sannolikheter har inte kalibrerats separat.',
            'En tidigare version av projektet använde senare matcher vid modellval; betrakta inte denna omkörning av samma data som ett helt nytt, blindat experiment.',
            'Säsongerna löper vidare utan att lagens form nollställs.',
        ],
    }
    (folder / f'evaluation_{league}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    # Slutversionen för webbsidan tränas på samtliga kända matcher efter testet.
    deployed = models()[selected_method]
    fit_model(deployed, samples, selected_features)
    deployed_goal = fit_model(GoalModel(), samples, goal_features)
    joblib.dump({
        'model': deployed, 'history': dict(history), 'teams': known_teams(matches),
        'last_match': str(matches.Date.max().date()), 'model_name': selected,
        'league': league, 'feature_names': selected_features,
        'venue_history': {venue: dict(rows) for venue, rows in venue_history.items()},
        'event_history': build_event_history(matches),
        'ratings': ratings, 'last_played': {key: str(date.date()) for key, date in last_played.items()},
        'goal_model': deployed_goal, 'goal_features': goal_features,
        'goal_market_enabled': allowed_markets,
    }, folder / f'model_{league}.joblib')
    return report


def main():
    success = 0
    for league, meta in LEAGUES.items():
        try:
            report = train_league(league)
        except ValueError as exc:
            print(f'{meta["name"]}: {exc}')
            continue
        success += 1
        print(f'\n{meta["name"]}: {report["source_matches"]} matcher, '
              f'{report["usable_matches"]} användbara. Vald modell: {report["selected_model"]}.')
        print('Senare testperiod:', report['periods']['test']['first'], '–', report['periods']['test']['last'])
        for name, metrics in report['test'].items():
            print(f'  {name}: rätt {metrics["accuracy"]:.1%}, log loss {metrics["log_loss"]:.4f}, Brier {metrics["brier"]:.4f}')
        print(f'Detaljer: artifacts/evaluation_{league}.json')
    if not success:
        raise SystemExit('Ingen liga kunde tränas. Kontrollera ligamapparna i data/.')


if __name__ == '__main__':
    main()
