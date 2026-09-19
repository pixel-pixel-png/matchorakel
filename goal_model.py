"""Målmodell med sammanhängande utfall för resultat och målmarknader."""
import math

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class GoalModel(ClassifierMixin, BaseEstimator):
    def __init__(self, alpha=1.0):
        self.alpha = alpha

    def fit(self, X, y):
        self.home_ = make_pipeline(StandardScaler(), PoissonRegressor(alpha=self.alpha, max_iter=500))
        self.away_ = make_pipeline(StandardScaler(), PoissonRegressor(alpha=self.alpha, max_iter=500))
        self.home_.fit(X, y['home_goals'])
        self.away_.fit(X, y['away_goals'])
        self.classes_ = np.array(['A', 'D', 'H'])
        return self

    @staticmethod
    def matrix(home_rate, away_rate):
        def probabilities(rate):
            rate = max(.05, min(float(rate), 8.0))
            first = [math.exp(-rate) * rate**n / math.factorial(n) for n in range(11)]
            return np.array(first + [max(0., 1 - sum(first))])
        joint = np.outer(probabilities(home_rate), probabilities(away_rate))
        return joint / joint.sum()

    def _matrices(self, X):
        return [self.matrix(h, a) for h, a in zip(self.home_.predict(X), self.away_.predict(X))]

    def predict_proba(self, X):
        return np.array([[float(np.triu(matrix, 1).sum()), float(np.trace(matrix)),
                          float(np.tril(matrix, -1).sum())] for matrix in self._matrices(X)])

    def goal_markets(self, X):
        results = []
        for matrix in self._matrices(X):
            total = np.add.outer(np.arange(12), np.arange(12))
            results.append({'over_2_5': float(matrix[total >= 3].sum()),
                            'over_1_5': float(matrix[total >= 2].sum()),
                            'both_score': float(matrix[1:, 1:].sum())})
        return results
