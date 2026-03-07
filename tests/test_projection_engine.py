"""
Unit tests for the Projection Engine.
"""
import unittest
import sys
import os

import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from projection_engine import (
    get_bye_teams,
    _rookie_baseline,
    _determine_usage_role,
    _vegas_multiplier,
    _weighted_baseline,
    _usage_multiplier,
    apply_injury_adjustments,
    INJURY_MULTIPLIERS,
)


class TestGetByeTeams(unittest.TestCase):

    def _make_schedule(self):
        return pd.DataFrame({
            'week': [1, 1, 1, 2, 2],
            'home_team': ['KC', 'BUF', 'DAL', 'KC', 'DAL'],
            'away_team': ['DET', 'MIA', 'NYG', 'BUF', 'MIA'],
        })

    def test_bye_teams_identified(self):
        sched = self._make_schedule()
        # Week 2: KC, BUF, DAL, MIA play. DET, NYG are on bye.
        byes = get_bye_teams(sched, week=2)
        self.assertIn('DET', byes)
        self.assertIn('NYG', byes)
        self.assertNotIn('KC', byes)

    def test_no_byes_when_all_play(self):
        sched = self._make_schedule()
        byes = get_bye_teams(sched, week=1)
        self.assertEqual(len(byes), 0)

    def test_empty_schedule(self):
        byes = get_bye_teams(pd.DataFrame(), week=5)
        self.assertEqual(len(byes), 0)

    def test_missing_columns(self):
        df = pd.DataFrame({'week': [1], 'home_team': ['KC']})
        byes = get_bye_teams(df, week=1)
        self.assertEqual(len(byes), 0)

    def test_nonexistent_week(self):
        sched = self._make_schedule()
        byes = get_bye_teams(sched, week=99)
        self.assertEqual(len(byes), 0)


class TestRookieBaseline(unittest.TestCase):

    def test_starter_baseline(self):
        baseline = _rookie_baseline('RB', 'starter')
        self.assertIn('rushing_yards', baseline)
        self.assertEqual(baseline['rushing_yards'], 55.0)

    def test_backup_scaled(self):
        baseline = _rookie_baseline('WR', 'backup')
        self.assertAlmostEqual(baseline['receiving_yards'], 60.0 * 0.40)

    def test_unknown_scaled(self):
        baseline = _rookie_baseline('QB', 'unknown')
        self.assertAlmostEqual(baseline['passing_yards'], 230.0 * 0.25)

    def test_invalid_position(self):
        baseline = _rookie_baseline('K', 'starter')
        self.assertEqual(baseline, {})


class TestDetermineUsageRole(unittest.TestCase):

    def test_starter_by_snap(self):
        row = pd.Series({'snap_pct_std': 0.75})
        self.assertEqual(_determine_usage_role(row), 'starter')

    def test_backup_by_snap(self):
        row = pd.Series({'snap_pct_std': 0.45})
        self.assertEqual(_determine_usage_role(row), 'backup')

    def test_unknown_low_snap(self):
        row = pd.Series({'snap_pct_std': 0.10})
        self.assertEqual(_determine_usage_role(row), 'unknown')

    def test_starter_by_target_share(self):
        row = pd.Series({'target_share_std': 0.20})
        self.assertEqual(_determine_usage_role(row), 'starter')

    def test_no_data_unknown(self):
        row = pd.Series({'some_other_col': 1.0})
        self.assertEqual(_determine_usage_role(row), 'unknown')


class TestVegasMultiplier(unittest.TestCase):

    def test_neutral_when_at_average(self):
        mult = _vegas_multiplier('KC', {'KC': 23.0}, 'QB')
        self.assertAlmostEqual(mult, 1.0)

    def test_high_implied_capped(self):
        mult = _vegas_multiplier('KC', {'KC': 35.0}, 'QB')
        self.assertAlmostEqual(mult, 1.20)

    def test_low_implied_floored(self):
        mult = _vegas_multiplier('KC', {'KC': 10.0}, 'QB')
        self.assertAlmostEqual(mult, 0.80)

    def test_missing_team_defaults(self):
        mult = _vegas_multiplier('XYZ', {'KC': 30.0}, 'WR')
        self.assertAlmostEqual(mult, 1.0)

    def test_rb_run_heavy_bonus(self):
        spread = {'KC': -10.0}
        mult = _vegas_multiplier('KC', {'KC': 18.0}, 'RB', spread_by_team=spread)
        # base: 18/23 ≈ 0.7826 → clipped to 0.80, then * 1.05 = 0.84
        self.assertAlmostEqual(mult, round(0.80 * 1.05, 4))

    def test_rb_no_bonus_when_not_favorite(self):
        spread = {'KC': 3.0}
        mult = _vegas_multiplier('KC', {'KC': 18.0}, 'RB', spread_by_team=spread)
        # base clipped to 0.80, no bonus because spread > -7
        self.assertAlmostEqual(mult, 0.80)


class TestWeightedBaseline(unittest.TestCase):

    def test_blends_windows(self):
        df = pd.DataFrame({
            'rushing_yards_roll3': [100.0],
            'rushing_yards_roll6': [80.0],
            'rushing_yards_std': [90.0],
        })
        result = _weighted_baseline(df, 'rushing_yards')
        from projection_engine import RECENCY_WEIGHTS
        expected = (100 * RECENCY_WEIGHTS['roll3'] + 80 * RECENCY_WEIGHTS['roll6'] + 90 * RECENCY_WEIGHTS['std']) / 1.0
        self.assertAlmostEqual(result.iloc[0], expected)

    def test_missing_columns_fallback(self):
        df = pd.DataFrame({'rushing_yards_roll3': [60.0]})
        result = _weighted_baseline(df, 'rushing_yards')
        self.assertAlmostEqual(result.iloc[0], 60.0)


class TestApplyInjuryAdjustments(unittest.TestCase):

    def _make_projections(self):
        return pd.DataFrame({
            'player_name': ['Player A', 'Player B', 'Player C'],
            'position': ['RB', 'WR', 'QB'],
            'projected_points': [15.0, 12.0, 20.0],
            'proj_rushing_yards': [80.0, 0.0, 10.0],
            'proj_season': [2024, 2024, 2024],
            'proj_week': [5, 5, 5],
        })

    def test_out_player_zeroed(self):
        proj = self._make_projections()
        injuries = pd.DataFrame({
            'player_name': ['Player A'],
            'report_status': ['Out'],
        })
        result = apply_injury_adjustments(proj, injuries)
        a_row = result[result['player_name'] == 'Player A'].iloc[0]
        self.assertEqual(a_row['projected_points'], 0.0)
        self.assertEqual(a_row['injury_multiplier'], 0.0)
        self.assertEqual(a_row['injury_status'], 'Out')

    def test_questionable_reduced(self):
        proj = self._make_projections()
        injuries = pd.DataFrame({
            'player_name': ['Player B'],
            'report_status': ['Questionable'],
        })
        result = apply_injury_adjustments(proj, injuries)
        b_row = result[result['player_name'] == 'Player B'].iloc[0]
        self.assertAlmostEqual(b_row['projected_points'], 12.0 * 0.85)
        self.assertAlmostEqual(b_row['injury_multiplier'], 0.85)

    def test_healthy_player_unchanged(self):
        proj = self._make_projections()
        injuries = pd.DataFrame({
            'player_name': ['Player A'],
            'report_status': ['Out'],
        })
        result = apply_injury_adjustments(proj, injuries)
        c_row = result[result['player_name'] == 'Player C'].iloc[0]
        self.assertAlmostEqual(c_row['projected_points'], 20.0)
        self.assertEqual(c_row['injury_status'], 'Active')

    def test_empty_injuries(self):
        proj = self._make_projections()
        result = apply_injury_adjustments(proj, pd.DataFrame())
        self.assertTrue((result['injury_multiplier'] == 1.0).all())

    def test_none_injuries(self):
        proj = self._make_projections()
        result = apply_injury_adjustments(proj, None)
        self.assertTrue((result['injury_multiplier'] == 1.0).all())


if __name__ == '__main__':
    unittest.main()
