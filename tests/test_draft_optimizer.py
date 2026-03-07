"""
Unit tests for the Draft Optimizer module.
"""
import unittest
import sys
import os

import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from draft_optimizer import (
    DraftBoard,
    DraftAdvisor,
    compute_value_scores,
)


def _make_projections(n=20):
    """Build a small projections DataFrame for testing."""
    positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE'] * 3
    rows = []
    for i in range(n):
        pos = positions[i % len(positions)]
        rows.append({
            'player_id': f'p{i}',
            'player_name': f'Player {i}',
            'position': pos,
            'recent_team': ['KC', 'BUF', 'DAL', 'SF'][i % 4],
            'projected_season_points': 300.0 - i * 10,
        })
    return pd.DataFrame(rows)


class TestComputeValueScores(unittest.TestCase):

    def test_adds_model_rank(self):
        proj = _make_projections()
        result = compute_value_scores(proj)
        self.assertIn('model_rank', result.columns)
        self.assertEqual(result.iloc[0]['model_rank'], 1)

    def test_adds_vorp(self):
        proj = _make_projections()
        result = compute_value_scores(proj)
        self.assertIn('vorp', result.columns)

    def test_with_adp(self):
        proj = _make_projections()
        adp = pd.DataFrame({
            'player_name': ['Player 0', 'Player 1', 'Player 2'],
            'adp_rank': [5, 1, 10],
        })
        result = compute_value_scores(proj, adp_df=adp)
        self.assertIn('adp_rank', result.columns)
        self.assertIn('adp_diff', result.columns)
        self.assertIn('value_tier', result.columns)


class TestDraftBoard(unittest.TestCase):

    def _make_board(self):
        proj = _make_projections()
        enriched = compute_value_scores(proj)
        return DraftBoard(enriched, roster_format='standard', n_teams=10)

    def test_initial_available_count(self):
        board = self._make_board()
        self.assertEqual(len(board.available), 20)

    def test_draft_player_removes_from_pool(self):
        board = self._make_board()
        board.draft_player('p0', by_me=True)
        self.assertEqual(len(board.available), 19)
        self.assertEqual(len(board.my_roster), 1)

    def test_draft_by_name(self):
        board = self._make_board()
        result = board.draft_by_name('Player 3', by_me=True)
        self.assertNotEqual(result, {})
        self.assertEqual(len(board.my_roster), 1)

    def test_draft_nonexistent_player(self):
        board = self._make_board()
        result = board.draft_player('nonexistent', by_me=False)
        self.assertEqual(result, {})
        self.assertEqual(len(board.available), 20)

    def test_draft_by_other_team(self):
        board = self._make_board()
        board.draft_player('p5', by_me=False)
        self.assertEqual(len(board.available), 19)
        self.assertEqual(len(board.my_roster), 0)
        self.assertEqual(len(board.drafted_by_others), 1)

    def test_undo_last_pick(self):
        board = self._make_board()
        board.draft_player('p0', by_me=True)
        self.assertEqual(len(board.my_roster), 1)
        if hasattr(board, 'undo_last_pick'):
            board.undo_last_pick()
            self.assertEqual(len(board.my_roster), 0)
            self.assertEqual(len(board.available), 20)


class TestDraftAdvisor(unittest.TestCase):

    def _make_advisor(self):
        proj = _make_projections()
        enriched = compute_value_scores(proj)
        board = DraftBoard(enriched, roster_format='standard', n_teams=10)
        return DraftAdvisor(board)

    def test_best_available(self):
        advisor = self._make_advisor()
        best = advisor.best_available(top_n=5)
        self.assertIsInstance(best, pd.DataFrame)
        self.assertEqual(len(best), 5)

    def test_best_at_position(self):
        advisor = self._make_advisor()
        best_rb = advisor.best_available(top_n=3, positions=['RB'])
        self.assertIsInstance(best_rb, pd.DataFrame)
        self.assertTrue((best_rb['position'] == 'RB').all())

    def test_recommend(self):
        advisor = self._make_advisor()
        recs_df, reasoning = advisor.recommend(top_n=3)
        self.assertIsInstance(recs_df, pd.DataFrame)
        self.assertIsInstance(reasoning, str)
        self.assertGreater(len(recs_df), 0)

    def test_waiver_recommendations(self):
        advisor = self._make_advisor()
        rostered = ['Player 0', 'Player 1', 'Player 2']
        waivers = advisor.waiver_recommendations(rostered, top_n=5)
        self.assertIsInstance(waivers, pd.DataFrame)
        # Should not include rostered players
        waiver_names = waivers['player_name'].tolist()
        for name in rostered:
            self.assertNotIn(name, waiver_names)


if __name__ == '__main__':
    unittest.main()
