#!/usr/bin/env python3
"""Tests for game-level differential feature assembly.

Validates that assemble_game_features() produces correctly structured
game-level rows with home-away differential columns, proper temporal lag,
early-season NaN handling, and label exclusion from feature columns.
"""

import glob
import os
import sys

import numpy as np
import pandas as pd
import pytest

# Project src/ on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feature_engineering import (
    assemble_game_features,
    assemble_multiyear_features,
    get_feature_columns,
    _compute_momentum_features,
    _compute_player_team_features,
    _compute_ep_team_features,
    _herfindahl,
    _share_weighted_avg,
    _PLAYER_TEAM_STAT_COLS,
    _EP_TEAM_STAT_COLS,
)
from config import LABEL_COLUMNS

SILVER_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "silver")
BRONZE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "bronze")


def _silver_data_available(season: int) -> bool:
    """Check if Silver team data is available for the given season."""
    sources = [
        "teams/pbp_metrics",
        "teams/tendencies",
        "teams/sos",
        "teams/situational",
        "teams/pbp_derived",
        "teams/game_context",
        "teams/referee_tendencies",
        "teams/playoff_context",
    ]
    for subdir in sources:
        pattern = os.path.join(SILVER_DIR, subdir, f"season={season}", "*.parquet")
        if not glob.glob(pattern):
            return False
    # Also need Bronze schedules
    sched_pattern = os.path.join(
        BRONZE_DIR, "schedules", f"season={season}", "*.parquet"
    )
    if not glob.glob(sched_pattern):
        return False
    return True


class TestFeatureEngineering:
    """Test game-level differential feature assembly."""

    @pytest.fixture(autouse=True)
    def _skip_if_data_missing(self):
        """Skip tests if Silver/Bronze data is not available for 2024."""
        if not _silver_data_available(2024):
            pytest.skip("Silver/Bronze data for 2024 not available locally")

    @pytest.fixture
    def game_df(self):
        """Assemble game features for 2024 once per test class."""
        return assemble_game_features(2024)

    def test_differential_features(self, game_df):
        """Assembled DataFrame has >= 80 columns starting with 'diff_'."""
        diff_cols = [c for c in game_df.columns if c.startswith("diff_")]
        assert (
            len(diff_cols) >= 80
        ), f"Expected >= 80 diff_ columns, got {len(diff_cols)}"

    def test_reg_games_only(self, game_df):
        """Only regular season games (game_type == 'REG') are included."""
        assert (
            game_df["game_type"] == "REG"
        ).all(), "Expected all rows to have game_type == 'REG'"

    def test_actual_margin(self, game_df):
        """actual_margin = home_score - away_score."""
        expected = game_df["home_score"] - game_df["away_score"]
        pd.testing.assert_series_equal(
            game_df["actual_margin"], expected, check_names=False
        )

    def test_actual_total(self, game_df):
        """actual_total = home_score + away_score."""
        expected = game_df["home_score"] + game_df["away_score"]
        pd.testing.assert_series_equal(
            game_df["actual_total"], expected, check_names=False
        )

    def test_label_columns_excluded(self, game_df):
        """get_feature_columns() never returns label columns."""
        feature_cols = get_feature_columns(game_df)
        for label in LABEL_COLUMNS:
            assert (
                label not in feature_cols
            ), f"Label column '{label}' found in feature columns"

    def test_row_count(self, game_df):
        """Regular season produces ~272 rows (256-285 range)."""
        assert (
            256 <= len(game_df) <= 285
        ), f"Expected 256-285 REG game rows, got {len(game_df)}"

    def test_early_season_nan(self, game_df):
        """Week 1 games have NaN in rolling features but do not crash."""
        # The DataFrame exists (didn't crash) and has Week 1 games
        week1 = game_df[game_df["week"] == 1]
        assert len(week1) > 0, "Expected Week 1 games in output"
        # Rolling columns may have NaN for Week 1 — that's expected
        # Just verify the assembly didn't crash

    def test_wins_losses_filled(self, game_df):
        """Week 1 wins/losses are filled with 0 (not NaN)."""
        week1 = game_df[game_df["week"] == 1]
        # Check both home and away wins columns
        win_cols = [
            c for c in game_df.columns if "wins" in c.lower() and c.startswith("diff_")
        ]
        # Also check the source wins columns if present
        for suffix in ["_home", "_away"]:
            col = f"wins{suffix}"
            if col in game_df.columns:
                assert (
                    week1[col].notna().all()
                ), f"Expected {col} to be non-null for Week 1"
                assert (week1[col] == 0).all(), (
                    f"Expected {col} == 0 for Week 1, got: " f"{week1[col].unique()}"
                )

    def test_temporal_lag(self, game_df):
        """No feature column contains future game scores or spread results."""
        feature_cols = get_feature_columns(game_df)
        # Feature columns should not include any raw score columns
        forbidden = {
            "home_score",
            "away_score",
            "actual_margin",
            "actual_total",
            "result",
            "spread_line",
            "total_line",
        }
        overlap = set(feature_cols) & forbidden
        assert len(overlap) == 0, f"Feature columns contain forbidden labels: {overlap}"

    def test_identifier_columns_excluded(self, game_df):
        """get_feature_columns() excludes identifier columns."""
        feature_cols = get_feature_columns(game_df)
        identifiers = {"game_id", "season", "week", "game_type"}
        for ident in identifiers:
            assert (
                ident not in feature_cols
            ), f"Identifier '{ident}' found in feature columns"

    def test_game_id_unique(self, game_df):
        """Each game_id appears exactly once (one row per game)."""
        assert game_df[
            "game_id"
        ].is_unique, "Expected unique game_id values (one row per game)"


class TestMomentumFeatures:
    """Test momentum/streak feature computation."""

    @pytest.fixture
    def schedule_df(self):
        """Synthetic 5-week schedule for 2 teams (TeamA home, TeamB away)."""
        # TeamA wins weeks 1-3, loses weeks 4-5
        # result > 0 means home team won
        return pd.DataFrame(
            {
                "game_id": [f"2023_0{w}_TeamA_TeamB" for w in range(1, 6)],
                "season": [2023] * 5,
                "week": [1, 2, 3, 4, 5],
                "game_type": ["REG"] * 5,
                "home_team": ["TeamA"] * 5,
                "away_team": ["TeamB"] * 5,
                "result": [7.0, 3.0, 10.0, -6.0, -3.0],  # home margin
                "spread_line": [-3.0, -1.0, -7.0, 2.0, 1.0],  # neg = home favored
                "home_score": [24, 20, 31, 14, 17],
                "away_score": [17, 17, 21, 20, 20],
            }
        )

    def test_returns_expected_columns(self, schedule_df, monkeypatch):
        """_compute_momentum_features returns correct columns."""
        monkeypatch.setattr(
            "feature_engineering._read_bronze_schedules",
            lambda season: schedule_df,
        )
        result = _compute_momentum_features(2023)
        expected_cols = {
            "game_id",
            "season",
            "week",
            "team",
            "win_streak",
            "ats_cover_sum3",
            "ats_margin_avg3",
        }
        assert expected_cols.issubset(
            set(result.columns)
        ), f"Missing columns: {expected_cols - set(result.columns)}"

    def test_win_streak_positive_consecutive(self, schedule_df, monkeypatch):
        """win_streak is positive for consecutive wins (TeamA home)."""
        monkeypatch.setattr(
            "feature_engineering._read_bronze_schedules",
            lambda season: schedule_df,
        )
        result = _compute_momentum_features(2023)
        team_a = result[result["team"] == "TeamA"].sort_values("week")
        # win_streak is shifted -- week 1 has no prior data
        # After shift(1): wk1=NaN, wk2=1win, wk3=2wins, wk4=3wins, wk5=-1loss
        streaks = team_a["win_streak"].tolist()
        # Week 2 should show 1 (one prior win)
        assert pd.isna(streaks[0]) or streaks[0] == 0, "Week 1 should be NaN or 0"
        assert streaks[1] == 1.0, f"Week 2 streak should be 1, got {streaks[1]}"
        assert streaks[2] == 2.0, f"Week 3 streak should be 2, got {streaks[2]}"
        assert streaks[3] == 3.0, f"Week 4 streak should be 3, got {streaks[3]}"

    def test_win_streak_negative_losses(self, schedule_df, monkeypatch):
        """win_streak goes negative for consecutive losses (TeamB is away loser)."""
        monkeypatch.setattr(
            "feature_engineering._read_bronze_schedules",
            lambda season: schedule_df,
        )
        result = _compute_momentum_features(2023)
        team_b = result[result["team"] == "TeamB"].sort_values("week")
        streaks = team_b["win_streak"].tolist()
        # TeamB loses weeks 1-3, wins 4-5
        # After shift(1): wk1=NaN, wk2=-1, wk3=-2, wk4=-3, wk5=1
        assert streaks[1] == -1.0, f"Week 2 streak should be -1, got {streaks[1]}"
        assert streaks[2] == -2.0, f"Week 3 streak should be -2, got {streaks[2]}"
        assert streaks[3] == -3.0, f"Week 4 streak should be -3, got {streaks[3]}"

    def test_shift1_lag_verified(self, schedule_df, monkeypatch):
        """Week N momentum uses only weeks before N (shift(1))."""
        monkeypatch.setattr(
            "feature_engineering._read_bronze_schedules",
            lambda season: schedule_df,
        )
        result = _compute_momentum_features(2023)
        team_a = result[result["team"] == "TeamA"].sort_values("week")

        # ats_cover_sum3 with shift(1):
        # TeamA covers: wk1(7>-(-3)=7>3? result=7,spread=-3 => result-spread=7-(-3)=10>0 YES),
        #   wk2(3-(-1)=4>0 YES), wk3(10-(-7)=17>0 YES), wk4(-6-2=-8<0 NO), wk5(-3-1=-4<0 NO)
        # After shift(1) and rolling(3,min_periods=1).sum():
        # wk1=NaN, wk2=sum([1])=1, wk3=sum([1,1])=2, wk4=sum([1,1,1])=3, wk5=sum([1,1,0])=2
        sums = team_a["ats_cover_sum3"].tolist()
        assert pd.isna(sums[0]), f"Week 1 ats_cover_sum3 should be NaN, got {sums[0]}"
        assert sums[1] == 1.0, f"Week 2 should be 1, got {sums[1]}"
        assert sums[3] == 3.0, f"Week 4 should be 3, got {sums[3]}"

    def test_ats_margin_avg3(self, schedule_df, monkeypatch):
        """ats_margin_avg3 is rolling mean of (result - spread_line) with shift(1)."""
        monkeypatch.setattr(
            "feature_engineering._read_bronze_schedules",
            lambda season: schedule_df,
        )
        result = _compute_momentum_features(2023)
        team_a = result[result["team"] == "TeamA"].sort_values("week")

        # TeamA (home) ats_margin = result - spread_line:
        # wk1: 7-(-3)=10, wk2: 3-(-1)=4, wk3: 10-(-7)=17, wk4: -6-2=-8, wk5: -3-1=-4
        # After shift(1), rolling(3,min_periods=1).mean():
        # wk1=NaN, wk2=mean([10])=10, wk3=mean([10,4])=7, wk4=mean([10,4,17])=10.33, wk5=mean([4,17,-8])=4.33
        avgs = team_a["ats_margin_avg3"].tolist()
        assert pd.isna(avgs[0]), f"Week 1 should be NaN, got {avgs[0]}"
        assert abs(avgs[1] - 10.0) < 0.01, f"Week 2 should be 10.0, got {avgs[1]}"
        assert abs(avgs[2] - 7.0) < 0.01, f"Week 3 should be 7.0, got {avgs[2]}"

    def test_away_team_ats_margin_sign(self, schedule_df, monkeypatch):
        """Away team ATS margin has correct sign (negated relative to home)."""
        monkeypatch.setattr(
            "feature_engineering._read_bronze_schedules",
            lambda season: schedule_df,
        )
        result = _compute_momentum_features(2023)
        team_b = result[result["team"] == "TeamB"].sort_values("week")

        # TeamB (away) ats_margin = -result - (-spread_line) = -result + spread_line
        # wk1: -7+(-3)=-10, wk2: -3+(-1)=-4, wk3: -10+(-7)=-17, wk4: 6+2=8, wk5: 3+1=4
        # After shift(1), rolling(3,min_periods=1).mean():
        # wk1=NaN, wk2=mean([-10])=-10, wk3=mean([-10,-4])=-7
        avgs = team_b["ats_margin_avg3"].tolist()
        assert pd.isna(avgs[0]), f"Week 1 should be NaN, got {avgs[0]}"
        assert abs(avgs[1] - (-10.0)) < 0.01, f"Week 2 should be -10.0, got {avgs[1]}"
        assert abs(avgs[2] - (-7.0)) < 0.01, f"Week 3 should be -7.0, got {avgs[2]}"

    def test_momentum_in_pre_game_cumulative(self, monkeypatch):
        """Momentum column names appear in _PRE_GAME_CUMULATIVE inside get_feature_columns."""
        # Create a minimal game_df with momentum columns as diff_ columns
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "diff_win_streak": [2.0],
                "diff_ats_cover_sum3": [1.0],
                "diff_ats_margin_avg3": [5.0],
            }
        )
        feature_cols = get_feature_columns(game_df)
        assert "diff_win_streak" in feature_cols, "diff_win_streak not in features"
        assert (
            "diff_ats_cover_sum3" in feature_cols
        ), "diff_ats_cover_sum3 not in features"
        assert (
            "diff_ats_margin_avg3" in feature_cols
        ), "diff_ats_margin_avg3 not in features"


class TestEWMFeatures:
    """Test that _is_rolling() recognizes EWM column patterns."""

    def test_is_rolling_recognizes_ewm3(self):
        """_is_rolling('off_epa_per_play_ewm3') returns True."""
        # Create a game_df with an ewm3 diff column -- if recognized, it appears in features
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "diff_off_epa_per_play_ewm3": [0.05],
            }
        )
        feature_cols = get_feature_columns(game_df)
        assert (
            "diff_off_epa_per_play_ewm3" in feature_cols
        ), "EWM column not recognized by _is_rolling / get_feature_columns"


class TestMarketFeatureFiltering:
    """Test that market features are correctly included/excluded by get_feature_columns().

    Pre-game knowable features (opening_spread, opening_total) should pass
    the filter (D-05). Retrospective features (spread_shift, total_shift,
    spread_magnitude, total_magnitude, etc.) must be excluded (D-06/D-08).
    """

    def test_opening_spread_included(self):
        """opening_spread passes get_feature_columns() as pre-game context (D-05)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "opening_spread_home": [3.0],
                "opening_spread_away": [-3.0],
                "diff_opening_spread": [6.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert "opening_spread_home" in cols, "opening_spread_home not in features"
        assert "opening_spread_away" in cols, "opening_spread_away not in features"
        assert "diff_opening_spread" in cols, "diff_opening_spread not in features"

    def test_opening_total_included(self):
        """opening_total passes get_feature_columns() as pre-game context (D-05)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "opening_total_home": [45.0],
                "opening_total_away": [45.0],
                "diff_opening_total": [0.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert "opening_total_home" in cols, "opening_total_home not in features"
        assert "opening_total_away" in cols, "opening_total_away not in features"
        assert "diff_opening_total" in cols, "diff_opening_total not in features"

    def test_retrospective_spread_shift_excluded(self):
        """spread_shift does NOT pass get_feature_columns() -- retrospective (D-06)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "spread_shift_home": [-0.5],
                "spread_shift_away": [0.5],
                "diff_spread_shift": [-1.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert "spread_shift_home" not in cols, "spread_shift_home should be excluded"
        assert "spread_shift_away" not in cols, "spread_shift_away should be excluded"
        assert "diff_spread_shift" not in cols, "diff_spread_shift should be excluded"

    def test_retrospective_total_shift_excluded(self):
        """total_shift does NOT pass get_feature_columns() -- retrospective (D-06)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "total_shift_home": [-1.0],
                "total_shift_away": [-1.0],
                "diff_total_shift": [0.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert "total_shift_home" not in cols, "total_shift_home should be excluded"
        assert "total_shift_away" not in cols, "total_shift_away should be excluded"
        assert "diff_total_shift" not in cols, "diff_total_shift should be excluded"

    def test_retrospective_magnitude_excluded(self):
        """spread_magnitude and total_magnitude do NOT pass -- retrospective (D-06)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "spread_magnitude_home": [2.0],
                "spread_magnitude_away": [2.0],
                "total_magnitude_home": [1.0],
                "total_magnitude_away": [1.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert (
            "spread_magnitude_home" not in cols
        ), "spread_magnitude_home should be excluded"
        assert (
            "total_magnitude_home" not in cols
        ), "total_magnitude_home should be excluded"

    def test_retrospective_move_abs_excluded(self):
        """spread_move_abs and total_move_abs do NOT pass -- retrospective (D-06)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "spread_move_abs_home": [1.5],
                "total_move_abs_home": [2.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert (
            "spread_move_abs_home" not in cols
        ), "spread_move_abs_home should be excluded"
        assert (
            "total_move_abs_home" not in cols
        ), "total_move_abs_home should be excluded"

    def test_retrospective_crosses_key_excluded(self):
        """crosses_key_spread and crosses_key_total do NOT pass -- retrospective (D-06)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "crosses_key_spread_home": [1.0],
                "crosses_key_total_home": [0.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert (
            "crosses_key_spread_home" not in cols
        ), "crosses_key_spread should be excluded"
        assert (
            "crosses_key_total_home" not in cols
        ), "crosses_key_total should be excluded"

    def test_closing_spread_excluded(self):
        """closing_spread does NOT pass -- retrospective (D-06)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "closing_spread_home": [-3.5],
                "closing_spread_away": [3.5],
            }
        )
        cols = get_feature_columns(game_df)
        assert (
            "closing_spread_home" not in cols
        ), "closing_spread_home should be excluded"
        assert (
            "closing_spread_away" not in cols
        ), "closing_spread_away should be excluded"

    def test_is_steam_move_excluded(self):
        """is_steam_move does NOT pass -- retrospective (D-06)."""
        game_df = pd.DataFrame(
            {
                "game_id": ["g1"],
                "season": [2023],
                "week": [3],
                "game_type": ["REG"],
                "is_steam_move_home": [1.0],
                "is_steam_move_away": [1.0],
            }
        )
        cols = get_feature_columns(game_df)
        assert "is_steam_move_home" not in cols, "is_steam_move should be excluded"


# ---------------------------------------------------------------------------
# Player-aggregate team features (opportunity-scan move #2, 2026-08-16)
# ---------------------------------------------------------------------------


def _synthetic_usage_df() -> pd.DataFrame:
    """Team AAA has a QB and two skill players across weeks 1-4; team BBB is
    a bystander so team-level groupby doesn't collapse to a single group."""
    rows = []
    for week in range(1, 5):
        rows.append(
            {
                "player_id": "QB1",
                "recent_team": "AAA",
                "season": 2023,
                "week": week,
                "position": "QB",
                "attempts": 30,
                "dakota": float(week),
                "snap_pct": 0.95,
                "target_share": 0.0,
                "carry_share": 0.05,
            }
        )
        rows.append(
            {
                "player_id": "WR1",
                "recent_team": "AAA",
                "season": 2023,
                "week": week,
                "position": "WR",
                "attempts": 0,
                "dakota": 0.0,
                "snap_pct": 0.80,
                "target_share": 0.30,
                "carry_share": 0.0,
            }
        )
        rows.append(
            {
                "player_id": "RB1",
                "recent_team": "AAA",
                "season": 2023,
                "week": week,
                "position": "RB",
                "attempts": 0,
                "dakota": 0.0,
                "snap_pct": 0.40,
                "target_share": 0.10,
                "carry_share": 0.90,
            }
        )
        rows.append(
            {
                "player_id": "QB2",
                "recent_team": "BBB",
                "season": 2023,
                "week": week,
                "position": "QB",
                "attempts": 28,
                "dakota": 0.5,
                "snap_pct": 0.95,
                "target_share": 0.0,
                "carry_share": 0.05,
            }
        )
    return pd.DataFrame(rows)


def _synthetic_advanced_df() -> pd.DataFrame:
    rows = []
    for week in range(1, 5):
        rows.append(
            {
                "player_gsis_id": "QB1",
                "season": 2023,
                "week": week,
                "ngs_completion_percentage_above_expectation": 2.0,
                "pfr_times_pressured_pct": 0.20,
                "ngs_avg_separation": np.nan,
                "ngs_avg_yac_above_expectation": np.nan,
                "ngs_rush_yards_over_expected_per_att": np.nan,
                "ngs_avg_time_to_los": np.nan,
            }
        )
        rows.append(
            {
                "player_gsis_id": "WR1",
                "season": 2023,
                "week": week,
                "ngs_completion_percentage_above_expectation": np.nan,
                "pfr_times_pressured_pct": np.nan,
                "ngs_avg_separation": 3.0,
                "ngs_avg_yac_above_expectation": 1.0,
                "ngs_rush_yards_over_expected_per_att": np.nan,
                "ngs_avg_time_to_los": np.nan,
            }
        )
        rows.append(
            {
                "player_gsis_id": "RB1",
                "season": 2023,
                "week": week,
                "ngs_completion_percentage_above_expectation": np.nan,
                "pfr_times_pressured_pct": np.nan,
                "ngs_avg_separation": np.nan,
                "ngs_avg_yac_above_expectation": np.nan,
                "ngs_rush_yards_over_expected_per_att": 0.5,
                "ngs_avg_time_to_los": 2.5,
            }
        )
    return pd.DataFrame(rows)


class TestHelperFunctions:
    """Unit tests for the HHI and share-weighted-average helpers."""

    def test_herfindahl_even_split(self):
        """Two equal shares -> HHI = 0.5 (1/N)."""
        assert abs(_herfindahl(pd.Series([0.5, 0.5])) - 0.5) < 1e-9

    def test_herfindahl_full_concentration(self):
        """One player with all the share -> HHI = 1.0."""
        assert abs(_herfindahl(pd.Series([1.0, 0.0, 0.0])) - 1.0) < 1e-9

    def test_herfindahl_renormalizes(self):
        """Shares that don't sum to 1 are renormalized before squaring."""
        # 0.2 and 0.2 renormalize to 0.5/0.5 -> HHI 0.5, same as even split
        assert abs(_herfindahl(pd.Series([0.2, 0.2])) - 0.5) < 1e-9

    def test_herfindahl_all_zero(self):
        """All-zero/NaN shares -> HHI 0.0, not a crash or NaN."""
        assert _herfindahl(pd.Series([0.0, np.nan])) == 0.0

    def test_share_weighted_avg_basic(self):
        """Weighted average matches manual computation."""
        g = pd.DataFrame({"val": [10.0, 20.0], "w": [0.3, 0.7]})
        result = _share_weighted_avg(g, "val", "w")
        assert abs(result - 17.0) < 1e-9  # 10*0.3 + 20*0.7

    def test_share_weighted_avg_ignores_nan_value(self):
        """Rows with NaN value are excluded from the weighted average."""
        g = pd.DataFrame({"val": [np.nan, 20.0], "w": [0.5, 0.5]})
        result = _share_weighted_avg(g, "val", "w")
        assert abs(result - 20.0) < 1e-9

    def test_share_weighted_avg_all_missing_returns_nan(self):
        """No valid (value, positive weight) pairs -> NaN, not 0 or crash."""
        g = pd.DataFrame({"val": [np.nan, np.nan], "w": [0.5, 0.5]})
        assert pd.isna(_share_weighted_avg(g, "val", "w"))


class TestPlayerTeamFeatures:
    """Leak-free construction tests for _compute_player_team_features()."""

    @pytest.fixture
    def result(self, monkeypatch):
        """Compute player-team features against synthetic usage/advanced data."""
        usage_df = _synthetic_usage_df()
        advanced_df = _synthetic_advanced_df()

        def fake_read(subdir, season):
            if subdir.endswith("usage"):
                return usage_df
            if subdir.endswith("advanced"):
                return advanced_df
            return pd.DataFrame()

        monkeypatch.setattr("feature_engineering._read_latest_local", fake_read)
        return _compute_player_team_features(2023)

    def test_returns_expected_raw_and_rolled_columns(self, result):
        """Output has team/season/week plus each raw stat and its roll3/roll6/std."""
        assert not result.empty
        for col in _PLAYER_TEAM_STAT_COLS:
            assert col in result.columns, f"Missing raw column {col}"
            for suffix in ("roll3", "roll6", "std"):
                assert f"{col}_{suffix}" in result.columns, f"Missing {col}_{suffix}"

    def test_week1_rolling_is_nan(self, result):
        """Week 1 has no prior data -- shift(1) makes every rolled column NaN."""
        team_a = result[(result["team"] == "AAA")].sort_values("week")
        wk1 = team_a[team_a["week"] == 1].iloc[0]
        assert pd.isna(wk1["qb_dakota_roll3"])
        assert pd.isna(wk1["skill_snap_share_hhi_roll3"])

    def test_shift1_lag_excludes_current_week(self, result):
        """Week 4's roll3 reflects only weeks 1-3's raw dakota (mean=2.0), not week 4 (4.0)."""
        team_a = result[result["team"] == "AAA"].sort_values("week")
        wk4 = team_a[team_a["week"] == 4].iloc[0]
        # raw dakota per week = week number (1,2,3,4); roll3 at week4 = mean(1,2,3)
        assert (
            abs(wk4["qb_dakota_roll3"] - 2.0) < 1e-9
        ), f"Expected week4 qb_dakota_roll3 == mean(wk1-3)=2.0, got {wk4['qb_dakota_roll3']}"
        # If shift(1) were missing, this would equal mean(1,2,3,4)=2.5 instead.
        assert abs(wk4["qb_dakota_roll3"] - 2.5) > 1e-9

    def test_qb_starter_selection_by_max_attempts(self, result):
        """QB composite uses the highest-attempts passer, not a random QB row."""
        # AAA's only passer is QB1 (attempts=30); dakota should track QB1's values
        team_a = result[result["team"] == "AAA"].sort_values("week")
        wk3 = team_a[team_a["week"] == 3].iloc[0]
        # roll3 at week3 = mean(wk1,wk2) = mean(1,2) = 1.5
        assert abs(wk3["qb_dakota_roll3"] - 1.5) < 1e-9

    def test_skill_hhi_concentration_direction(self, result):
        """HHI reflects the synthetic snap-share split (0.80 WR vs 0.40 RB -> WR dominant)."""
        team_a = result[result["team"] == "AAA"].sort_values("week")
        # Raw column present (pre-roll) -- concentration should be > even-split (0.5)
        assert (team_a["skill_snap_share_hhi"] > 0.5).all()

    def test_missing_usage_returns_empty(self, monkeypatch):
        """No players/usage Silver for the season -> empty DataFrame, no crash."""
        monkeypatch.setattr(
            "feature_engineering._read_latest_local",
            lambda subdir, season: pd.DataFrame(),
        )
        result = _compute_player_team_features(2099)
        assert result.empty

    def test_missing_advanced_still_produces_usage_derived_features(self, monkeypatch):
        """players/advanced missing (NGS/PFR down) -- usage-only features still compute."""
        usage_df = _synthetic_usage_df()

        def fake_read(subdir, season):
            if subdir.endswith("usage"):
                return usage_df
            return pd.DataFrame()

        monkeypatch.setattr("feature_engineering._read_latest_local", fake_read)
        result = _compute_player_team_features(2023)
        assert not result.empty
        # dakota-derived (usage-only) column has real values
        team_a = result[result["team"] == "AAA"].sort_values("week")
        wk4 = team_a[team_a["week"] == 4].iloc[0]
        assert abs(wk4["qb_dakota_roll3"] - 2.0) < 1e-9
        # NGS-derived column is present but entirely NaN (advanced missing)
        assert result["qb_cpoe"].isna().all()


class TestPlayerFeaturesOptIn:
    """Verify the include_player_features flag is additive/opt-in only."""

    @pytest.fixture(autouse=True)
    def _skip_if_data_missing(self):
        if not _silver_data_available(2024):
            pytest.skip("Silver/Bronze data for 2024 not available locally")

    def test_default_flag_off_matches_no_player_columns(self):
        """assemble_game_features(season) with no flag has zero playerfeat diff cols."""
        df = assemble_game_features(2024)
        pf_cols = [
            c
            for c in df.columns
            if any(
                c == f"diff_{base}" or c.startswith(f"diff_{base}_")
                for base in _PLAYER_TEAM_STAT_COLS
            )
        ]
        assert (
            pf_cols == []
        ), f"Unexpected player-feature columns with flag off: {pf_cols}"

    def test_flag_on_adds_columns_without_shrinking_baseline(self):
        """include_player_features=True is strictly additive vs the default assembly."""
        base = assemble_game_features(2024)
        with_pf = assemble_game_features(2024, include_player_features=True)
        assert set(base.columns).issubset(set(with_pf.columns))
        assert len(with_pf) == len(base), "Row count must be unchanged by the merge"

    def test_flag_on_selected_features_include_only_rolled_playerfeat_cols(self):
        """get_feature_columns() only ever selects the _roll3/_roll6/_std playerfeat diffs."""
        with_pf = assemble_game_features(2024, include_player_features=True)
        selected = get_feature_columns(with_pf)
        pf_selected = [
            c for c in selected if any(base in c for base in _PLAYER_TEAM_STAT_COLS)
        ]
        assert (
            pf_selected
        ), "Expected at least one player-feature column to be selectable"
        assert all(
            ("roll3" in c or "roll6" in c or "std" in c) for c in pf_selected
        ), f"Raw (unlagged) playerfeat column leaked into features: {pf_selected}"

    def test_multiyear_assembly_passes_flag_through(self):
        """assemble_multiyear_features forwards include_player_features per season."""
        df = assemble_multiyear_features([2024], include_player_features=True)
        pf_cols = [c for c in df.columns if c.startswith("diff_qb_dakota")]
        assert pf_cols, "Expected diff_qb_dakota* columns when flag is passed through"


def _synthetic_ep_df() -> pd.DataFrame:
    """Team AAA has a QB/WR/RB across weeks 1-4; team BBB is a bystander RB
    so the team-week groupby doesn't collapse to a single group.

    AAA's per-role exp fantasy points scale linearly with week (w, 2w, 3w)
    so the shift(1) rolling test has real week-to-week variation; the
    over/under-expected and opportunity-share columns are held constant
    across weeks so their manually-computed values are easy to check.
    """
    rows = []
    for week in range(1, 5):
        w = float(week)
        rows.append(
            {
                "player_id": "QB1",
                "team": "AAA",
                "season": 2023,
                "week": week,
                "position": "QB",
                "targets": 0.0,
                "carries": 1.0,
                "total_tds": 0.0,
                "exp_total_tds": 0.1,
                "exp_pass_fantasy_points": w,
                "exp_rush_fantasy_points": 0.0,
                "exp_rec_fantasy_points": 0.0,
                "exp_fantasy_points_total": w,
                "actual_fantasy_points_total": w + 1.0,
                "fantasy_points_over_expected": 1.0,
            }
        )
        rows.append(
            {
                "player_id": "WR1",
                "team": "AAA",
                "season": 2023,
                "week": week,
                "position": "WR",
                "targets": 8.0,
                "carries": 0.0,
                "total_tds": 0.0,
                "exp_total_tds": 0.2,
                "exp_pass_fantasy_points": 0.0,
                "exp_rush_fantasy_points": 0.0,
                "exp_rec_fantasy_points": 2 * w,
                "exp_fantasy_points_total": 2 * w,
                "actual_fantasy_points_total": 2 * w - 0.5,
                "fantasy_points_over_expected": -0.5,
            }
        )
        rows.append(
            {
                "player_id": "RB1",
                "team": "AAA",
                "season": 2023,
                "week": week,
                "position": "RB",
                "targets": 2.0,
                "carries": 10.0,
                "total_tds": 1.0,
                "exp_total_tds": 0.3,
                "exp_pass_fantasy_points": 0.0,
                "exp_rush_fantasy_points": 3 * w,
                "exp_rec_fantasy_points": 0.0,
                "exp_fantasy_points_total": 3 * w,
                "actual_fantasy_points_total": 3 * w + 2.0,
                "fantasy_points_over_expected": 2.0,
            }
        )
        rows.append(
            {
                "player_id": "RB2",
                "team": "BBB",
                "season": 2023,
                "week": week,
                "position": "RB",
                "targets": 1.0,
                "carries": 5.0,
                "total_tds": 0.0,
                "exp_total_tds": 0.1,
                "exp_pass_fantasy_points": 0.0,
                "exp_rush_fantasy_points": 1.0,
                "exp_rec_fantasy_points": 0.0,
                "exp_fantasy_points_total": 1.0,
                "actual_fantasy_points_total": 1.0,
                "fantasy_points_over_expected": 0.0,
            }
        )
    return pd.DataFrame(rows)


class TestEpTeamFeatures:
    """Leak-free construction tests for _compute_ep_team_features()
    (2026-08-21 gated re-experiment -- .planning/ENSEMBLE_EP_FEATURES_GATE.md)."""

    @pytest.fixture
    def result(self, monkeypatch):
        """Compute EP team features against synthetic ffopportunity_features data."""
        ep_df = _synthetic_ep_df()
        monkeypatch.setattr(
            "feature_engineering._read_ep_features", lambda season: ep_df
        )
        return _compute_ep_team_features(2023)

    def test_returns_expected_raw_and_rolled_columns(self, result):
        """Output has team/season/week plus each raw stat and its roll3/roll6/std."""
        assert not result.empty
        for col in _EP_TEAM_STAT_COLS:
            assert col in result.columns, f"Missing raw column {col}"
            for suffix in ("roll3", "roll6", "std"):
                assert f"{col}_{suffix}" in result.columns, f"Missing {col}_{suffix}"

    def test_missing_ep_data_returns_empty(self, monkeypatch):
        """No ffopportunity_features Silver for the season -> empty DataFrame, no crash."""
        monkeypatch.setattr(
            "feature_engineering._read_ep_features", lambda season: pd.DataFrame()
        )
        result = _compute_ep_team_features(2099)
        assert result.empty

    def test_week1_rolling_is_nan(self, result):
        """Week 1 has no prior data -- shift(1) makes every rolled column NaN."""
        team_a = result[result["team"] == "AAA"].sort_values("week")
        wk1 = team_a[team_a["week"] == 1].iloc[0]
        assert pd.isna(wk1["ep_team_exp_fp_total_roll3"])
        assert pd.isna(wk1["ep_team_opportunity_hhi_roll3"])

    def test_shift1_lag_excludes_current_week(self, result):
        """Week 4's roll3 reflects only weeks 1-3's raw exp_fp_total (mean=12.0), not week 4 (24.0)."""
        team_a = result[result["team"] == "AAA"].sort_values("week")
        wk4 = team_a[team_a["week"] == 4].iloc[0]
        # raw ep_team_exp_fp_total per week = 6*week (1,2,3,4)*6 = 6,12,18,24
        # roll3 at week4 = mean(6,12,18) = 12.0
        assert (
            abs(wk4["ep_team_exp_fp_total_roll3"] - 12.0) < 1e-9
        ), f"Expected 12.0, got {wk4['ep_team_exp_fp_total_roll3']}"
        # If shift(1) were missing, this would equal mean(6,12,18,24)=15.0 instead.
        assert abs(wk4["ep_team_exp_fp_total_roll3"] - 15.0) > 1e-9

    def test_raw_aggregation_sums_match_manual_computation(self, result):
        """Raw team-week sums match hand-computed values for team AAA."""
        team_a = result[result["team"] == "AAA"].sort_values("week")
        row = team_a[team_a["week"] == 2].iloc[0]
        # exp_fp_total = QB(2) + WR(4) + RB(6) = 12.0
        assert abs(row["ep_team_exp_fp_total"] - 12.0) < 1e-9
        assert abs(row["ep_team_exp_pass_fp"] - 2.0) < 1e-9
        assert abs(row["ep_team_exp_rush_fp"] - 6.0) < 1e-9
        assert abs(row["ep_team_exp_rec_fp"] - 4.0) < 1e-9
        # fp_over_expected = 1.0 + (-0.5) + 2.0 = 2.5 (constant across weeks)
        assert abs(row["ep_team_fp_over_expected"] - 2.5) < 1e-9
        # exp_total_tds = 0.1 + 0.2 + 0.3 = 0.6; actual total_tds = 0+0+1 = 1
        assert abs(row["ep_team_exp_total_tds"] - 0.6) < 1e-9
        assert abs(row["ep_team_td_over_expected"] - 0.4) < 1e-9

    def test_opportunity_hhi_matches_manual_computation(self, result):
        """Opportunity HHI (targets+carries share) matches hand computation for AAA."""
        team_a = result[result["team"] == "AAA"].sort_values("week")
        row = team_a[team_a["week"] == 1].iloc[0]
        # opportunities: QB1=0+1=1, WR1=8+0=8, RB1=2+10=12; total=21
        # HHI = (1/21)^2 + (8/21)^2 + (12/21)^2 = 209/441
        expected = (1 / 21) ** 2 + (8 / 21) ** 2 + (12 / 21) ** 2
        assert abs(row["ep_team_opportunity_hhi"] - expected) < 1e-9

    def test_rush_share_hhi_full_concentration_single_back(self, result):
        """Only one RB carrying the ball on AAA -> rush_share_hhi == 1.0 (full concentration)."""
        team_a = result[result["team"] == "AAA"].sort_values("week")
        assert (team_a["ep_team_rush_share_hhi"] == 1.0).all()


class TestEpFeaturesOptIn:
    """Verify the include_ep_features flag is additive/opt-in only."""

    @pytest.fixture(autouse=True)
    def _skip_if_data_missing(self):
        if not _silver_data_available(2024):
            pytest.skip("Silver/Bronze data for 2024 not available locally")

    def test_default_flag_off_matches_no_ep_columns(self):
        """assemble_game_features(season) with no flag has zero EP-feature diff cols."""
        df = assemble_game_features(2024)
        ep_cols = [
            c
            for c in df.columns
            if any(
                c == f"diff_{base}" or c.startswith(f"diff_{base}_")
                for base in _EP_TEAM_STAT_COLS
            )
        ]
        assert ep_cols == [], f"Unexpected EP-feature columns with flag off: {ep_cols}"

    def test_flag_on_adds_columns_without_shrinking_baseline(self):
        """include_ep_features=True is strictly additive vs the default assembly."""
        base = assemble_game_features(2024)
        with_ep = assemble_game_features(2024, include_ep_features=True)
        assert set(base.columns).issubset(set(with_ep.columns))
        assert len(with_ep) == len(base), "Row count must be unchanged by the merge"

    def test_flags_are_independent_and_composable(self):
        """include_player_features and include_ep_features can be combined."""
        both = assemble_game_features(
            2024, include_player_features=True, include_ep_features=True
        )
        pf_cols = [c for c in both.columns if c.startswith("diff_qb_dakota")]
        ep_cols = [c for c in both.columns if c.startswith("diff_ep_team_exp_fp_total")]
        assert pf_cols, "Expected player-feature columns when both flags are on"
        assert ep_cols, "Expected EP-feature columns when both flags are on"

    def test_flag_on_selected_features_include_only_rolled_epfeat_cols(self):
        """get_feature_columns() only ever selects the _roll3/_roll6/_std EP diffs."""
        with_ep = assemble_game_features(2024, include_ep_features=True)
        selected = get_feature_columns(with_ep)
        ep_selected = [
            c for c in selected if any(base in c for base in _EP_TEAM_STAT_COLS)
        ]
        assert ep_selected, "Expected at least one EP-feature column to be selectable"
        assert all(
            ("roll3" in c or "roll6" in c or "std" in c) for c in ep_selected
        ), f"Raw (unlagged) EP-feature column leaked into features: {ep_selected}"

    def test_multiyear_assembly_passes_ep_flag_through(self):
        """assemble_multiyear_features forwards include_ep_features per season."""
        df = assemble_multiyear_features([2024], include_ep_features=True)
        ep_cols = [c for c in df.columns if c.startswith("diff_ep_team_exp_fp_total")]
        assert ep_cols, "Expected diff_ep_team_exp_fp_total* columns when flag is passed through"
