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
    INJURY_OUT_STATUSES,
    MIN_WEEK,
    apply_qb_starter_floor,
    compute_qb_team_trailing_usage,
    compute_qb_trailing_passing_yards,
    compute_starter_tier_floor,
    get_depth_chart_qb1_by_team,
    get_depth_chart_qb1_ids,
    get_injury_based_replacements,
)

#: Explicit empty injuries frame passed to every v1-only test below so
#: apply_qb_starter_floor() doesn't fall back to loading real Bronze
#: injury data off disk (keeps these tests deterministic/isolated).
_NO_INJURIES = pd.DataFrame(
    columns=["season", "week", "position", "report_status", "gsis_id", "team"]
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


def _weekly_row(player_id, week, passing_yards, position="QB", season=2024, team="CIN"):
    return {
        "player_id": player_id,
        "season": season,
        "week": week,
        "position": position,
        "passing_yards": passing_yards,
        "recent_team": team,
    }


def _injury_row(player_id, week, report_status, position="QB", season=2024, team="CIN"):
    return {
        "season": season,
        "week": week,
        "position": position,
        "report_status": report_status,
        "gsis_id": player_id,
        "team": team,
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
            season=2024, week=12, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
        )
        floor = compute_starter_tier_floor("half_ppr")
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], floor, places=2)
        self.assertAlmostEqual(out.iloc[0]["qb_starter_floor_value"], floor, places=2)
        self.assertEqual(out.iloc[0]["qb_starter_floor_source"], "depth_chart")

    def test_established_starter_with_high_trailing_usage_untouched(self):
        # Trailing 250 yds/gm is well above threshold -> not backup-level.
        proj = self._proj(pts=3.2)  # artificially low, but the gate should not fire
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12), self._weekly(trailing_yards=250, n_games=3),
            season=2024, week=12, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.2, places=2)

    def test_already_above_floor_not_raised(self):
        proj = self._proj(pts=25.0)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12), self._weekly(trailing_yards=34, n_games=2),
            season=2024, week=12, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
        )
        # Flagged (qualifies), but never lowered below its own projection.
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 25.0, places=2)

    def test_not_depth_chart_qb1_untouched(self):
        proj = self._proj(player_id="P_BENCH", pts=3.2)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12, starter_id="P_OTHER"),
            self._weekly(player_id="P_BENCH", trailing_yards=34),
            season=2024, week=12, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.2, places=2)

    def test_non_qb_position_untouched(self):
        proj = self._proj(pos="RB", pts=3.2)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=12), self._weekly(trailing_yards=34),
            season=2024, week=12, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])

    def test_week1_is_noop_regardless_of_signals(self):
        proj = self._proj(pts=3.2)
        out = apply_qb_starter_floor(
            proj, self._depth_chart(week=1), self._weekly(trailing_yards=34),
            season=2024, week=1, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
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
            season=2024, week=12, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
        )
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])

    def test_empty_depth_chart_is_noop_with_provenance_columns(self):
        proj = self._proj(pts=3.2)
        out = apply_qb_starter_floor(
            proj, pd.DataFrame(), self._weekly(trailing_yards=34),
            season=2024, week=12, scoring_format="half_ppr", injuries_df=_NO_INJURIES,
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


class TestComputeQbTeamTrailingUsage(unittest.TestCase):
    def test_ranks_team_qbs_by_trailing_usage(self):
        rows = [
            _weekly_row("P_STARTER", 1, 300, team="CIN"),
            _weekly_row("P_STARTER", 2, 280, team="CIN"),
            _weekly_row("P_BACKUP", 1, 20, team="CIN"),
        ]
        out = compute_qb_team_trailing_usage(pd.DataFrame(rows), season=2024, week=3)
        out = out.set_index("player_id")
        self.assertAlmostEqual(out.loc["P_STARTER", "trailing_passing_yards"], 290.0, places=1)
        self.assertEqual(out.loc["P_STARTER", "recent_team"], "CIN")
        self.assertAlmostEqual(out.loc["P_BACKUP", "trailing_passing_yards"], 20.0, places=1)

    def test_leak_free_current_week_excluded(self):
        rows = [
            _weekly_row("P1", 1, 0, team="CIN"),
            _weekly_row("P1", 5, 999, team="CIN"),  # projected week itself
        ]
        out = compute_qb_team_trailing_usage(pd.DataFrame(rows), season=2024, week=5)
        self.assertAlmostEqual(out.iloc[0]["trailing_passing_yards"], 0.0, places=2)

    def test_missing_recent_team_column_returns_empty(self):
        rows = [
            {
                "player_id": "P1",
                "season": 2024,
                "week": 1,
                "position": "QB",
                "passing_yards": 100,
            }
        ]
        out = compute_qb_team_trailing_usage(pd.DataFrame(rows), season=2024, week=3)
        self.assertTrue(out.empty)
        self.assertEqual(
            list(out.columns),
            ["player_id", "recent_team", "trailing_passing_yards", "trailing_games"],
        )

    def test_empty_input_returns_empty(self):
        out = compute_qb_team_trailing_usage(pd.DataFrame(), season=2024, week=5)
        self.assertTrue(out.empty)


class TestGetDepthChartQb1ByTeam(unittest.TestCase):
    def test_maps_team_to_qb1(self):
        df = pd.DataFrame(
            [
                _depth_chart_row("CIN", 12, 1, "P_STARTER"),
                _depth_chart_row("CIN", 12, 2, "P_BACKUP"),
                _depth_chart_row("NYJ", 12, 1, "P_OTHER"),
            ]
        )
        out = get_depth_chart_qb1_by_team(df, week=12)
        self.assertEqual(out, {"CIN": "P_STARTER", "NYJ": "P_OTHER"})

    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(get_depth_chart_qb1_by_team(pd.DataFrame(), week=12), {})

    def test_missing_columns_returns_empty_dict(self):
        df = pd.DataFrame([{"week": 12, "position": "QB"}])
        self.assertEqual(get_depth_chart_qb1_by_team(df, week=12), {})


class TestGetInjuryBasedReplacements(unittest.TestCase):
    def test_incumbent_out_falls_back_to_trailing_backup_when_depth_chart_stale(self):
        # Mirrors the Browning/CIN-2023 case from the v1 gate report: Burrow
        # (incumbent, high trailing usage) is Out at week 12, but the depth
        # chart still lists him as QB1 (hasn't caught up yet) -> replacement
        # falls back to the team's next-highest-trailing-usage QB.
        weekly = pd.DataFrame(
            [
                _weekly_row("P_BURROW", w, 280, team="CIN") for w in range(1, 11)
            ] + [_weekly_row("P_BROWNING", 11, 68, team="CIN")]
        )
        depth_chart = pd.DataFrame(
            [_depth_chart_row("CIN", 12, 1, "P_BURROW")]  # stale — still Burrow
        )
        injuries = pd.DataFrame(
            [_injury_row("P_BURROW", 12, "Out", team="CIN")]
        )
        out = get_injury_based_replacements(depth_chart, injuries, weekly, season=2024, week=12)
        self.assertEqual(out, {"P_BROWNING"})

    def test_incumbent_out_prefers_depth_chart_when_already_caught_up(self):
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
            + [_weekly_row("P_BACKUP", 3, 40, team="CIN")]
        )
        depth_chart = pd.DataFrame(
            [_depth_chart_row("CIN", 5, 1, "P_BACKUP")]  # already flipped
        )
        injuries = pd.DataFrame([_injury_row("P_STARTER", 5, "Doubtful", team="CIN")])
        out = get_injury_based_replacements(depth_chart, injuries, weekly, season=2024, week=5)
        self.assertEqual(out, {"P_BACKUP"})

    def test_flagged_qb_who_is_not_the_usage_leader_is_ignored(self):
        # P_QB3 is Out but isn't the team's trailing-usage leader (P_STARTER
        # is) -> not a role change, no replacement identified.
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
            + [_weekly_row("P_QB3", 3, 5, team="CIN")]
        )
        depth_chart = pd.DataFrame()
        injuries = pd.DataFrame([_injury_row("P_QB3", 5, "Out", team="CIN")])
        out = get_injury_based_replacements(depth_chart, injuries, weekly, season=2024, week=5)
        self.assertEqual(out, set())

    def test_leak_free_injury_status_scoped_to_exact_week(self):
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
            + [_weekly_row("P_BACKUP", 3, 40, team="CIN")]
        )
        depth_chart = pd.DataFrame()
        # Out status is for week 6, not the projected week 5 -> must not fire.
        injuries = pd.DataFrame([_injury_row("P_STARTER", 6, "Out", team="CIN")])
        out = get_injury_based_replacements(depth_chart, injuries, weekly, season=2024, week=5)
        self.assertEqual(out, set())

    def test_questionable_status_does_not_qualify(self):
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
            + [_weekly_row("P_BACKUP", 3, 40, team="CIN")]
        )
        depth_chart = pd.DataFrame()
        injuries = pd.DataFrame([_injury_row("P_STARTER", 5, "Questionable", team="CIN")])
        out = get_injury_based_replacements(depth_chart, injuries, weekly, season=2024, week=5)
        self.assertEqual(out, set())

    def test_no_backup_available_yields_no_replacement(self):
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
        )
        depth_chart = pd.DataFrame()
        injuries = pd.DataFrame([_injury_row("P_STARTER", 5, "Out", team="CIN")])
        out = get_injury_based_replacements(depth_chart, injuries, weekly, season=2024, week=5)
        self.assertEqual(out, set())

    def test_empty_injuries_returns_empty_set(self):
        out = get_injury_based_replacements(
            pd.DataFrame(), _NO_INJURIES, pd.DataFrame(), season=2024, week=5
        )
        self.assertEqual(out, set())

    def test_ir_status_qualifies(self):
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
            + [_weekly_row("P_BACKUP", 3, 40, team="CIN")]
        )
        depth_chart = pd.DataFrame()
        injuries = pd.DataFrame([_injury_row("P_STARTER", 5, "IR", team="CIN")])
        out = get_injury_based_replacements(depth_chart, injuries, weekly, season=2024, week=5)
        self.assertEqual(out, {"P_BACKUP"})


class TestApplyQbStarterFloorInjuryPath(unittest.TestCase):
    """Integration tests for the v2 injury-based path through
    apply_qb_starter_floor (OR'd with the v1 depth-chart path)."""

    def test_injury_flagged_replacement_gets_floored_when_depth_chart_stale(self):
        proj = pd.DataFrame(
            [{"player_id": "P_BROWNING", "position": "QB", "projected_points": 3.2}]
        )
        weekly = pd.DataFrame(
            [_weekly_row("P_BURROW", w, 280, team="CIN") for w in range(1, 11)]
            + [_weekly_row("P_BROWNING", 11, 68, team="CIN")]
        )
        depth_chart = pd.DataFrame(
            [_depth_chart_row("CIN", 12, 1, "P_BURROW")]  # stale
        )
        injuries = pd.DataFrame([_injury_row("P_BURROW", 12, "Out", team="CIN")])

        out = apply_qb_starter_floor(
            proj, depth_chart, weekly, season=2024, week=12,
            scoring_format="half_ppr", injuries_df=injuries,
        )
        floor = compute_starter_tier_floor("half_ppr")
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], floor, places=2)
        self.assertEqual(out.iloc[0]["qb_starter_floor_source"], "injury")

    def test_v1_and_v2_both_fire_source_is_both(self):
        # Depth chart already lists the backup as QB1 (v1 fires) AND the
        # injury report flags the incumbent Out (v2 also fires on the
        # same replacement row) -> source == "both".
        proj = pd.DataFrame(
            [{"player_id": "P_BACKUP", "position": "QB", "projected_points": 3.2}]
        )
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
            + [_weekly_row("P_BACKUP", 3, 40, team="CIN")]
        )
        depth_chart = pd.DataFrame([_depth_chart_row("CIN", 5, 1, "P_BACKUP")])
        injuries = pd.DataFrame([_injury_row("P_STARTER", 5, "Doubtful", team="CIN")])

        out = apply_qb_starter_floor(
            proj, depth_chart, weekly, season=2024, week=5,
            scoring_format="half_ppr", injuries_df=injuries,
        )
        self.assertTrue(out.iloc[0]["qb_starter_floor_flag"])
        self.assertEqual(out.iloc[0]["qb_starter_floor_source"], "both")

    def test_replacement_with_established_trailing_usage_not_floored(self):
        # Injury path identifies a "replacement" but his own trailing usage
        # is already starter-level (e.g. a co-starter/timeshare) -> the
        # shared backup-level gate keeps this a no-op.
        proj = pd.DataFrame(
            [{"player_id": "P_BACKUP", "position": "QB", "projected_points": 20.0}]
        )
        weekly = pd.DataFrame(
            [_weekly_row("P_STARTER", w, 280, team="CIN") for w in range(1, 4)]
            + [_weekly_row("P_BACKUP", w, 260, team="CIN") for w in range(1, 4)]
        )
        depth_chart = pd.DataFrame()
        injuries = pd.DataFrame([_injury_row("P_STARTER", 5, "Out", team="CIN")])

        out = apply_qb_starter_floor(
            proj, depth_chart, weekly, season=2024, week=5,
            scoring_format="half_ppr", injuries_df=injuries,
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 20.0, places=2)

    def test_week1_is_noop_for_injury_path_too(self):
        proj = pd.DataFrame(
            [{"player_id": "P_BACKUP", "position": "QB", "projected_points": 3.2}]
        )
        weekly = pd.DataFrame([_weekly_row("P_STARTER", 1, 280, team="CIN")])
        depth_chart = pd.DataFrame()
        injuries = pd.DataFrame([_injury_row("P_STARTER", 1, "Out", team="CIN")])
        out = apply_qb_starter_floor(
            proj, depth_chart, weekly, season=2024, week=1,
            scoring_format="half_ppr", injuries_df=injuries,
        )
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])

    def test_default_injuries_df_none_does_not_raise(self):
        # injuries_df omitted entirely -> falls back to load_injury_reports()
        # (real Bronze disk read); must not raise even if the fake player
        # ids obviously won't match anything real.
        proj = pd.DataFrame(
            [{"player_id": "P_NOT_REAL", "position": "QB", "projected_points": 3.2}]
        )
        weekly = pd.DataFrame([_weekly_row("P_NOT_REAL", 1, 30, team="CIN")])
        depth_chart = pd.DataFrame()
        out = apply_qb_starter_floor(
            proj, depth_chart, weekly, season=2024, week=5, scoring_format="half_ppr",
        )
        self.assertIn("qb_starter_floor_flag", out.columns)
        self.assertFalse(out.iloc[0]["qb_starter_floor_flag"])

    def test_injury_out_statuses_includes_task_specified_statuses(self):
        self.assertTrue({"Out", "Doubtful", "IR"}.issubset(INJURY_OUT_STATUSES))


if __name__ == "__main__":
    unittest.main()
