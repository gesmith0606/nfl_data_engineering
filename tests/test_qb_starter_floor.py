"""
Unit tests for the QB starter-tier floor (lever #3 from
.planning/CONSENSUS_ERROR_DECOMPOSITION.md finding #3).
"""

import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from qb_starter_floor import (  # noqa: E402
    BACKUP_PASSING_YARDS_THRESHOLD,
    MIN_WEEK,
    apply_qb_starter_floor,
    compute_qb_trailing_passing_yards,
    compute_starter_tier_floor,
    get_depth_chart_qb1_ids,
)


def _depth_chart_row(club, week, depth_team, gsis_id, position="QB", game_type="REG"):
    return {
        "season": 2024,
        "club_code": club,
        "week": float(week),
        "game_type": game_type,
        "depth_team": str(depth_team),
        "position": position,
        "gsis_id": gsis_id,
    }


def _weekly_row(player_id, week, passing_yards, position="QB", season=2024):
    return {
        "player_id": player_id,
        "season": season,
        "week": week,
        "position": position,
        "passing_yards": passing_yards,
    }


class TestComputeStarterTierFloor(unittest.TestCase):
    def test_reuses_starter_baseline_with_haircut(self):
        # _STARTER_BASELINES['QB']: 230 pass_yd, 1.4 pass_td, 0.8 int,
        # 15 rush_yd, 0.1 rush_td -> half_ppr:
        # 230*0.04 + 1.4*4 - 0.8*2 + 15*0.1 + 0.1*6 = 9.2+5.6-1.6+1.5+0.6=15.3
        floor = compute_starter_tier_floor("half_ppr", haircut=1.0)
        self.assertAlmostEqual(floor, 15.3, places=2)

    def test_haircut_scales_floor(self):
        full = compute_starter_tier_floor("half_ppr", haircut=1.0)
        haircut = compute_starter_tier_floor("half_ppr", haircut=0.8)
        self.assertAlmostEqual(haircut, round(full * 0.8, 2), places=2)

    def test_default_haircut_is_0_8(self):
        default = compute_starter_tier_floor("half_ppr")
        explicit = compute_starter_tier_floor("half_ppr", haircut=0.8)
        self.assertAlmostEqual(default, explicit, places=2)


class TestGetDepthChartQb1Ids(unittest.TestCase):
    def test_finds_qb1_for_week(self):
        df = pd.DataFrame(
            [
                _depth_chart_row("CIN", 12, 1, "P_STARTER"),
                _depth_chart_row("CIN", 12, 2, "P_BACKUP"),
            ]
        )
        ids = get_depth_chart_qb1_ids(df, week=12)
        self.assertEqual(ids, {"P_STARTER"})

    def test_ignores_other_weeks(self):
        df = pd.DataFrame(
            [
                _depth_chart_row("CIN", 11, 1, "P_OLD"),
                _depth_chart_row("CIN", 12, 1, "P_NEW"),
            ]
        )
        ids = get_depth_chart_qb1_ids(df, week=12)
        self.assertEqual(ids, {"P_NEW"})

    def test_ignores_non_qb_positions(self):
        df = pd.DataFrame(
            [
                _depth_chart_row("CIN", 12, 1, "P_RB", position="RB"),
                _depth_chart_row("CIN", 12, 1, "P_QB"),
            ]
        )
        ids = get_depth_chart_qb1_ids(df, week=12)
        self.assertEqual(ids, {"P_QB"})

    def test_ignores_non_regular_season(self):
        df = pd.DataFrame(
            [
                _depth_chart_row("CIN", 12, 1, "P_PRE", game_type="PRE"),
            ]
        )
        ids = get_depth_chart_qb1_ids(df, week=12)
        self.assertEqual(ids, set())

    def test_empty_input_returns_empty_set(self):
        self.assertEqual(get_depth_chart_qb1_ids(pd.DataFrame(), week=12), set())

    def test_missing_columns_returns_empty_set(self):
        df = pd.DataFrame([{"week": 12, "position": "QB"}])
        self.assertEqual(get_depth_chart_qb1_ids(df, week=12), set())


class TestComputeQbTrailingPassingYards(unittest.TestCase):
    def test_averages_strictly_prior_weeks(self):
        rows = [
            _weekly_row("P1", 1, 100),
            _weekly_row("P1", 2, 200),
            _weekly_row("P1", 3, 300),  # must NOT be included when week=3
        ]
        out = compute_qb_trailing_passing_yards(pd.DataFrame(rows), season=2024, week=3)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out.iloc[0]["trailing_passing_yards"], 150.0, places=2)
        self.assertEqual(out.iloc[0]["trailing_games"], 2)

    def test_leak_free_current_week_excluded(self):
        # A big current-week game must not leak into the trailing average.
        rows = [
            _weekly_row("P1", 1, 0),
            _weekly_row("P1", 5, 999),  # the projected week itself
        ]
        out = compute_qb_trailing_passing_yards(pd.DataFrame(rows), season=2024, week=5)
        self.assertAlmostEqual(out.iloc[0]["trailing_passing_yards"], 0.0, places=2)

    def test_ignores_other_seasons(self):
        rows = [_weekly_row("P1", 10, 300, season=2023)]
        out = compute_qb_trailing_passing_yards(pd.DataFrame(rows), season=2024, week=5)
        self.assertTrue(out.empty)

    def test_ignores_non_qb(self):
        rows = [_weekly_row("P1", 1, 300, position="RB")]
        out = compute_qb_trailing_passing_yards(pd.DataFrame(rows), season=2024, week=3)
        self.assertTrue(out.empty)

    def test_no_prior_games_returns_empty(self):
        rows = [_weekly_row("P1", 5, 300)]
        out = compute_qb_trailing_passing_yards(pd.DataFrame(rows), season=2024, week=3)
        self.assertTrue(out.empty)

    def test_empty_input_returns_empty_with_columns(self):
        out = compute_qb_trailing_passing_yards(pd.DataFrame(), season=2024, week=5)
        self.assertTrue(out.empty)
        self.assertEqual(
            list(out.columns),
            ["player_id", "trailing_passing_yards", "trailing_games"],
        )


class TestApplyQbStarterFloor(unittest.TestCase):
    @staticmethod
    def _proj(player_id="P_NEW", pos="QB", pts=3.0):
        return pd.DataFrame(
            [{"player_id": player_id, "position": pos, "projected_points": pts}]
        )

    @staticmethod
    def _depth_chart(week=12, starter_id="P_NEW"):
        return pd.DataFrame([_depth_chart_row("CIN", week, 1, starter_id)])

    @staticmethod
    def _weekly(player_id="P_NEW", trailing_yards=30, n_games=2):
        return pd.DataFrame(
            [_weekly_row(player_id, w + 1, trailing_yards) for w in range(n_games)]
        )

    def test_backup_promoted_to_qb1_gets_floored(self):
        # Trailing 34 yds/gm is well below the 92-yd backup threshold.
        proj = self._proj(pts=3.2)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12), self._weekly(trailing_yards=34, n_games=2),
            season=2024, week=12, scoring_format="half_ppr",
        )
        floor = compute_starter_tier_floor("half_ppr")
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], floor, places=2)
        self.assertAlmostEqual(out.iloc[0]["qb_starter_floor_value"], floor, places=2)

    def test_established_starter_with_high_trailing_usage_untouched(self):
        # Trailing 250 yds/gm is well above threshold -> not backup-level.
        proj = self._proj(pts=3.2)  # artificially low, but the gate should not fire
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12), self._weekly(trailing_yards=250, n_games=3),
            season=2024, week=12, scoring_format="half_ppr",
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.2, places=2)

    def test_already_above_floor_not_raised(self):
        proj = self._proj(pts=25.0)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12), self._weekly(trailing_yards=34, n_games=2),
            season=2024, week=12, scoring_format="half_ppr",
        )
        # Flagged (qualifies), but never lowered below its own projection.
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 25.0, places=2)

    def test_not_depth_chart_qb1_untouched(self):
        proj = self._proj(player_id="P_BENCH", pts=3.2)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12, starter_id="P_OTHER"),
            self._weekly(player_id="P_BENCH", trailing_yards=34),
            season=2024, week=12, scoring_format="half_ppr",
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.2, places=2)

    def test_non_qb_position_untouched(self):
        proj = self._proj(pos="RB", pts=3.2)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12), self._weekly(trailing_yards=34),
            season=2024, week=12, scoring_format="half_ppr",
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])

    def test_week1_is_noop_regardless_of_signals(self):
        proj = self._proj(pts=3.2)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=1), self._weekly(trailing_yards=34),
            season=2024, week=1, scoring_format="half_ppr",
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.2, places=2)

    def test_missing_trailing_history_counts_as_backup_level(self):
        # No weekly rows at all for this player -> NaN trailing -> qualifies.
        proj = self._proj(player_id="P_ROOKIE", pts=3.2)
        empty_weekly = pd.DataFrame(
            columns=["player_id", "season", "week", "position", "passing_yards"]
        )
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12, starter_id="P_ROOKIE"), empty_weekly,
            season=2024, week=12, scoring_format="half_ppr",
        )
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])

    def test_empty_depth_chart_is_noop_with_provenance_columns(self):
        proj = self._proj(pts=3.2)
        out = apply_qb_starter_floor(
            proj, pd.DataFrame(), self._weekly(trailing_yards=34),
            season=2024, week=12, scoring_format="half_ppr",
        )
        self.assertIn("qb_starter_floor_flag", out.columns)
        self.assertIn("qb_starter_floor_value", out.columns)
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.2, places=2)

    def test_min_week_constant_is_2(self):
        self.assertEqual(MIN_WEEK, 2)

    def test_threshold_is_backup_scale_of_starter_baseline(self):
        # 230.0 (starter pass_yd baseline) * 0.40 (backup scale) = 92.0
        self.assertAlmostEqual(BACKUP_PASSING_YARDS_THRESHOLD, 92.0, places=1)


if __name__ == "__main__":
    unittest.main()
