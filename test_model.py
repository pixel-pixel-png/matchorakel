import unittest

import numpy as np
import pandas as pd

from football import build_dataset, feature_row
from goal_model import GoalModel


class ModelTests(unittest.TestCase):
    def test_goal_matrix_probabilities_are_consistent(self):
        matrix = GoalModel.matrix(2.3, 0.8)
        self.assertAlmostEqual(float(matrix.sum()), 1.0)
        self.assertGreater(float(np.tril(matrix, -1).sum()), float(np.triu(matrix, 1).sum()))
        self.assertGreater(float(matrix[1:, 1:].sum()), 0)

    def test_elo_uses_only_previous_dates(self):
        dates = pd.to_datetime(['2025-08-01', '2025-08-08', '2025-08-15', '2025-08-22',
                                '2025-08-29', '2025-09-05', '2025-09-05'])
        matches = pd.DataFrame([
            {'Date': date, 'HomeTeam': 'home', 'AwayTeam': 'away', 'FTHG': 3,
             'FTAG': 0, 'FTR': 'H'} for date in dates
        ])
        dataset, history, venues, ratings, last_played = build_dataset(matches)
        self.assertEqual(len(dataset), 2)
        self.assertAlmostEqual(dataset.iloc[0].home_elo, dataset.iloc[1].home_elo)
        self.assertEqual(dataset.iloc[0].home_rest_days, 7)
        self.assertGreater(ratings['home'], ratings['away'])
        future = feature_row('home', 'away', history, venues, ratings, last_played, '2025-09-12')
        self.assertEqual(future['home_rest_days'], 7)


if __name__ == '__main__':
    unittest.main()
