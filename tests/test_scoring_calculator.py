"""
Unit tests for the Fantasy Scoring Calculator.
"""
import unittest
import sys
import os

import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from scoring_calculator import (
    calculate_fantasy_points,
    calculate_fantasy_points_df,
    get_scoring_config,
    list_scoring_formats,
)


class TestCalculateFantasyPoints(unittest.TestCase):
    """Test single-player fantasy point calculation."""

    def test_ppr_reception(self):
        """PPR awards 1.0 per reception."""
        pts = calculate_fantasy_points({'receptions': 5}, scoring_format='ppr')
        self.assertAlmostEqual(pts, 5.0)

    def test_half_ppr_reception(self):
        """Half-PPR awards 0.5 per reception."""
        pts = calculate_fantasy_points({'receptions': 6}, scoring_format='half_ppr')
        self.assertAlmostEqual(pts, 3.0)

    def test_standard_no_reception_bonus(self):
        """Standard scoring: receptions worth 0 points."""
        pts = calculate_fantasy_points({'receptions': 10}, scoring_format='standard')
        self.assertAlmostEqual(pts, 0.0)

    def test_rushing_td(self):
        pts = calculate_fantasy_points({'rushing_tds': 2}, scoring_format='half_ppr')
        self.assertAlmostEqual(pts, 12.0)  # 2 * 6.0

    def test_passing_yards(self):
        pts = calculate_fantasy_points({'passing_yards': 300}, scoring_format='ppr')
        self.assertAlmostEqual(pts, 12.0)  # 300 * 0.04

    def test_interception_negative(self):
        pts = calculate_fantasy_points({'interceptions': 2}, scoring_format='ppr')
        self.assertAlmostEqual(pts, -4.0)  # 2 * -2.0

    def test_full_qb_line(self):
        """Full QB stat line."""
        stats = {
            'passing_yards': 275,
            'passing_tds': 2,
            'interceptions': 1,
            'rushing_yards': 30,
        }
        pts = calculate_fantasy_points(stats, scoring_format='half_ppr')
        expected = 275 * 0.04 + 2 * 4.0 + 1 * -2.0 + 30 * 0.1
        self.assertAlmostEqual(pts, round(expected, 2))

    def test_full_rb_line(self):
        """Full RB stat line."""
        stats = {
            'rushing_yards': 85,
            'rushing_tds': 1,
            'receptions': 3,
            'receiving_yards': 25,
        }
        pts = calculate_fantasy_points(stats, scoring_format='ppr')
        expected = 85 * 0.1 + 1 * 6.0 + 3 * 1.0 + 25 * 0.1
        self.assertAlmostEqual(pts, round(expected, 2))

    def test_zero_stats(self):
        pts = calculate_fantasy_points({}, scoring_format='ppr')
        self.assertAlmostEqual(pts, 0.0)

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            calculate_fantasy_points({'rushing_yards': 50}, scoring_format='nonexistent')

    def test_custom_scoring(self):
        custom = {'rush_yd': 0.2, 'rush_td': 10.0}
        pts = calculate_fantasy_points(
            {'rushing_yards': 100, 'rushing_tds': 1},
            scoring_format='custom',
            custom_scoring=custom,
        )
        self.assertAlmostEqual(pts, 30.0)  # 100*0.2 + 1*10


class TestCalculateFantasyPointsDF(unittest.TestCase):
    """Test DataFrame-based fantasy point calculation."""

    def test_basic_df(self):
        df = pd.DataFrame({
            'rushing_yards': [100, 50],
            'rushing_tds': [1, 0],
            'receptions': [3, 5],
        })
        result = calculate_fantasy_points_df(df, scoring_format='ppr')
        self.assertIn('projected_points', result.columns)
        self.assertEqual(len(result), 2)
        # Row 0: 100*0.1 + 1*6.0 + 3*1.0 = 19.0
        self.assertAlmostEqual(result.iloc[0]['projected_points'], 19.0)

    def test_missing_columns_handled(self):
        """Columns not in df should contribute 0 points."""
        df = pd.DataFrame({'rushing_yards': [50]})
        result = calculate_fantasy_points_df(df, scoring_format='standard')
        self.assertAlmostEqual(result.iloc[0]['projected_points'], 5.0)

    def test_custom_output_col(self):
        df = pd.DataFrame({'passing_tds': [3]})
        result = calculate_fantasy_points_df(df, output_col='my_points')
        self.assertIn('my_points', result.columns)


class TestScoringHelpers(unittest.TestCase):

    def test_list_formats(self):
        formats = list_scoring_formats()
        self.assertIn('ppr', formats)
        self.assertIn('half_ppr', formats)
        self.assertIn('standard', formats)

    def test_get_config(self):
        cfg = get_scoring_config('ppr')
        self.assertIn('reception', cfg)
        self.assertEqual(cfg['reception'], 1.0)

    def test_get_config_invalid(self):
        with self.assertRaises(ValueError):
            get_scoring_config('invalid')


if __name__ == '__main__':
    unittest.main()
