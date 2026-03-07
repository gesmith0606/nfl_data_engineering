"""
Unit tests for the Player Analytics module.
"""
import unittest
import sys
import os

import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from player_analytics import (
    compute_usage_metrics,
    compute_rolling_averages,
    compute_implied_team_totals,
)


class TestComputeUsageMetrics(unittest.TestCase):

    def _make_weekly(self):
        """Create minimal weekly DataFrame with 2 players on same team."""
        return pd.DataFrame({
            'season': [2024, 2024],
            'week': [1, 1],
            'player_id': ['p1', 'p2'],
            'player_name': ['Alpha', 'Beta'],
            'recent_team': ['KC', 'KC'],
            'position': ['WR', 'WR'],
            'targets': [8, 4],
            'air_yards': [50, 25],
            'carries': [0, 0],
        })

    def test_target_share_computed(self):
        df = self._make_weekly()
        result = compute_usage_metrics(df)
        self.assertIn('target_share', result.columns)
        p1 = result[result['player_id'] == 'p1'].iloc[0]
        # p1 targets=8, team_targets=12 → 8/12 ≈ 0.667
        self.assertAlmostEqual(p1['target_share'], 8 / 12, places=2)

    def test_carry_share_computed(self):
        df = pd.DataFrame({
            'season': [2024, 2024],
            'week': [1, 1],
            'player_id': ['rb1', 'rb2'],
            'player_name': ['Runner A', 'Runner B'],
            'recent_team': ['BUF', 'BUF'],
            'position': ['RB', 'RB'],
            'targets': [2, 1],
            'air_yards': [5, 3],
            'carries': [15, 10],
        })
        result = compute_usage_metrics(df)
        self.assertIn('carry_share', result.columns)
        rb1 = result[result['player_id'] == 'rb1'].iloc[0]
        self.assertAlmostEqual(rb1['carry_share'], 15 / 25, places=2)


class TestComputeRollingAverages(unittest.TestCase):

    def _make_multi_week(self):
        """Create player with 6 weeks of data."""
        rows = []
        for week in range(1, 7):
            rows.append({
                'season': 2024,
                'week': week,
                'player_id': 'p1',
                'player_name': 'Test Player',
                'recent_team': 'KC',
                'position': 'WR',
                'rushing_yards': 10.0 * week,
                'receiving_yards': 50.0 + week,
                'targets': 6,
                'receptions': 4,
                'carries': 0,
                'passing_yards': 0,
                'passing_tds': 0,
                'interceptions': 0,
                'rushing_tds': 0,
                'receiving_tds': 0,
                'air_yards': 40,
                'target_share': 0.20,
                'carry_share': 0.0,
                'snap_pct': 0.75,
            })
        return pd.DataFrame(rows)

    def test_roll3_column_created(self):
        df = self._make_multi_week()
        result = compute_rolling_averages(df, windows=[3])
        self.assertIn('rushing_yards_roll3', result.columns)

    def test_roll3_value_correct(self):
        df = self._make_multi_week()
        result = compute_rolling_averages(df, windows=[3])
        # shift(1).rolling(3): week 6 uses weeks 3,4,5 values (30,40,50) → avg = 40
        w6 = result[(result['week'] == 6) & (result['player_id'] == 'p1')]
        if not w6.empty and 'rushing_yards_roll3' in w6.columns:
            val = w6.iloc[0]['rushing_yards_roll3']
            self.assertAlmostEqual(val, 40.0, places=0)

    def test_std_column_created(self):
        df = self._make_multi_week()
        result = compute_rolling_averages(df, windows=[3, 6])
        self.assertIn('rushing_yards_std', result.columns)


class TestComputeImpliedTeamTotals(unittest.TestCase):

    def _make_schedule(self):
        return pd.DataFrame({
            'home_team': ['KC', 'BUF'],
            'away_team': ['DET', 'MIA'],
            'total_line': [50.0, 44.0],
            'spread_line': [-6.0, -3.0],
        })

    def test_implied_totals_calculated(self):
        sched = self._make_schedule()
        totals = compute_implied_team_totals(sched)
        # KC home: (50/2) - (-6/2) = 25 + 3 = 28
        self.assertAlmostEqual(totals['KC'], 28.0, places=1)
        # DET away: (50/2) + (-6/2) = 25 - 3 = 22
        self.assertAlmostEqual(totals['DET'], 22.0, places=1)

    def test_missing_total_line(self):
        sched = pd.DataFrame({
            'home_team': ['KC'],
            'away_team': ['DET'],
        })
        totals = compute_implied_team_totals(sched)
        # Defaults to league avg 23.0 for both
        self.assertAlmostEqual(totals['KC'], 23.0, places=1)
        self.assertAlmostEqual(totals['DET'], 23.0, places=1)

    def test_nan_total_line_defaults(self):
        sched = pd.DataFrame({
            'home_team': ['KC'],
            'away_team': ['DET'],
            'total_line': [np.nan],
            'spread_line': [np.nan],
        })
        totals = compute_implied_team_totals(sched)
        self.assertAlmostEqual(totals['KC'], 23.0, places=1)

    def test_empty_schedule(self):
        sched = pd.DataFrame(columns=['home_team', 'away_team'])
        totals = compute_implied_team_totals(sched)
        self.assertEqual(totals, {})


if __name__ == '__main__':
    unittest.main()
