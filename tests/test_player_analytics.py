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


class TestRollingSeasonFix(unittest.TestCase):
    """Regression tests for PBP-05: rolling windows must not leak across seasons."""

    def _make_cross_season_data(self):
        """Create 2-season player data: 2023 weeks 16-18 + 2024 weeks 1-3."""
        rows = []
        # Season 2023 weeks 16-18
        for week in [16, 17, 18]:
            rows.append({
                'season': 2023,
                'week': week,
                'player_id': 'p1',
                'player_name': 'Cross Season Player',
                'recent_team': 'KC',
                'position': 'WR',
                'rushing_yards': 100.0,
                'receiving_yards': 80.0,
                'targets': 10,
                'receptions': 7,
                'carries': 5,
                'passing_yards': 0,
                'passing_tds': 0,
                'interceptions': 0,
                'rushing_tds': 1,
                'receiving_tds': 1,
                'air_yards': 50,
                'target_share': 0.30,
                'carry_share': 0.15,
                'snap_pct': 0.90,
            })
        # Season 2024 weeks 1-3
        for week in [1, 2, 3]:
            rows.append({
                'season': 2024,
                'week': week,
                'player_id': 'p1',
                'player_name': 'Cross Season Player',
                'recent_team': 'KC',
                'position': 'WR',
                'rushing_yards': 50.0,
                'receiving_yards': 60.0,
                'targets': 8,
                'receptions': 5,
                'carries': 3,
                'passing_yards': 0,
                'passing_tds': 0,
                'interceptions': 0,
                'rushing_tds': 0,
                'receiving_tds': 0,
                'air_yards': 35,
                'target_share': 0.25,
                'carry_share': 0.10,
                'snap_pct': 0.80,
            })
        return pd.DataFrame(rows)

    def test_roll3_resets_at_season_boundary(self):
        """Roll3 for 2024 week 1 must be NaN -- no data from 2023 should leak."""
        df = self._make_cross_season_data()
        result = compute_rolling_averages(df, windows=[3])
        w1_2024 = result[
            (result['season'] == 2024)
            & (result['week'] == 1)
            & (result['player_id'] == 'p1')
        ]
        self.assertFalse(w1_2024.empty, "2024 week 1 row missing")
        val = w1_2024.iloc[0]['rushing_yards_roll3']
        self.assertTrue(
            pd.isna(val),
            f"roll3 for 2024 week 1 should be NaN (no prior 2024 data), got {val}",
        )

    def test_roll3_week3_uses_only_current_season(self):
        """Roll3 for 2024 week 3 should use only 2024 week 1 data (shift by 1)."""
        df = self._make_cross_season_data()
        result = compute_rolling_averages(df, windows=[3])
        w3_2024 = result[
            (result['season'] == 2024)
            & (result['week'] == 3)
            & (result['player_id'] == 'p1')
        ]
        self.assertFalse(w3_2024.empty, "2024 week 3 row missing")
        # shift(1) on weeks [1,2,3] -> [NaN, w1, w2]
        # rolling(3, min_periods=1) at week 3 -> mean(w1, w2) = mean(50, 50) = 50
        val = w3_2024.iloc[0]['rushing_yards_roll3']
        self.assertAlmostEqual(val, 50.0, places=1,
                               msg=f"Expected 50.0 (only 2024 data), got {val}")

    def test_std_expanding_resets_at_season_boundary(self):
        """STD (season-to-date) expanding average must reset at season boundary."""
        df = self._make_cross_season_data()
        result = compute_rolling_averages(df, windows=[3])
        w1_2024 = result[
            (result['season'] == 2024)
            & (result['week'] == 1)
            & (result['player_id'] == 'p1')
        ]
        self.assertFalse(w1_2024.empty, "2024 week 1 row missing")
        val = w1_2024.iloc[0]['rushing_yards_std']
        self.assertTrue(
            pd.isna(val),
            f"STD for 2024 week 1 should be NaN (no prior season data), got {val}",
        )


if __name__ == '__main__':
    unittest.main()
