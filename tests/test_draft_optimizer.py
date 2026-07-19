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

    def test_with_adp_stdev_carries_through_as_adp_stdev(self):
        """Real-ADP stdev (FFC/ESPN via src/adp_sources.py) survives the merge."""
        proj = _make_projections()
        adp = pd.DataFrame({
            'player_name': ['Player 0', 'Player 1', 'Player 2'],
            'adp_rank': [5, 1, 10],
            'stdev': [1.2, 0.5, 3.4],
        })
        result = compute_value_scores(proj, adp_df=adp)
        self.assertIn('adp_stdev', result.columns)
        row0 = result[result['player_name'] == 'Player 0'].iloc[0]
        self.assertAlmostEqual(row0['adp_stdev'], 1.2)

    def test_adp_stdev_column_always_present_even_without_adp(self):
        proj = _make_projections()
        result = compute_value_scores(proj)
        self.assertIn('adp_stdev', result.columns)
        self.assertTrue(result['adp_stdev'].isna().all())


class TestDstNanSafety(unittest.TestCase):
    """DST is ADP-only (not projected by our model) -- board code must never
    crash on a DST row with NaN projected_season_points; it should just
    surface projected_points/vorp as NaN/None rather than raising."""

    def _projections_with_dst(self):
        proj = _make_projections()
        dst_row = pd.DataFrame([{
            'player_id': 'dst1',
            'player_name': 'San Francisco',
            'position': 'DST',
            'recent_team': 'SF',
            'projected_season_points': np.nan,
        }])
        return pd.concat([proj, dst_row], ignore_index=True)

    def test_compute_value_scores_does_not_crash_on_dst_row(self):
        proj = self._projections_with_dst()
        result = compute_value_scores(proj)  # must not raise
        dst = result[result['position'] == 'DST']
        self.assertEqual(len(dst), 1)
        # model_rank must be a valid int (never NaN/crash on .astype(int))
        self.assertIsInstance(int(dst.iloc[0]['model_rank']), int)
        # No projection data exists for DST -> vorp stays NaN, not a crash.
        self.assertTrue(pd.isna(dst.iloc[0]['vorp']))

    def test_dst_row_ranked_by_adp_still_appears(self):
        proj = self._projections_with_dst()
        adp = pd.DataFrame({
            'player_name': ['San Francisco', 'Player 0'],
            'adp_rank': [140, 1],
        })
        result = compute_value_scores(proj, adp_df=adp)
        dst = result[result['player_name'] == 'San Francisco']
        self.assertEqual(len(dst), 1)
        self.assertEqual(dst.iloc[0]['adp_rank'], 140)

    def test_draft_board_and_advisor_do_not_crash_with_dst(self):
        proj = self._projections_with_dst()
        enriched = compute_value_scores(proj)
        board = DraftBoard(enriched, roster_format='standard', n_teams=12)
        advisor = DraftAdvisor(board, scoring_format='half_ppr')
        recs, reasoning = advisor.recommend(top_n=5)  # must not raise
        self.assertIsInstance(reasoning, str)
        # DST must still be draftable off the board without crashing.
        result = board.draft_player('dst1', by_me=True)
        self.assertEqual(result.get('player_name'), 'San Francisco')


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
