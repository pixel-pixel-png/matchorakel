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

class DataValidationTests(unittest.TestCase):
 def test_invalid_goals_rejected_and_invalid_optional_stats_omitted(self):
  import tempfile
  from pathlib import Path
  from football import load_matches
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'matches.csv'
   for goals in ['-1','1.5','inf']:
    path.write_text(f'Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n01/01/2025,Arsenal,Chelsea,{goals},0,H\n')
    with self.subTest(goals=goals),self.assertRaises(ValueError):load_matches(Path(folder),'PL')
   path.write_text('Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HST,HY\n01/01/2025,Arsenal,Chelsea,2,0,H,inf,-1\n')
   rows=load_matches(Path(folder),'PL');self.assertTrue(pd.isna(rows.iloc[0].HST));self.assertTrue(pd.isna(rows.iloc[0].HY))
 def test_fuzzy_alias_does_not_match_an_english_adjective(self):
  from football import find_teams
  self.assertEqual(find_teams('a real prediction',['real madrid'],'LL'),[])
  self.assertEqual(find_teams('nice thanks',['nice'],'L1'),[])
