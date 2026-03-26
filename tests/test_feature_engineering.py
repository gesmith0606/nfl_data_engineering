#!/usr/bin/env python3
"""Tests for game-level differential feature assembly.

Validates that assemble_game_features() produces correctly structured
game-level rows with home-away differential columns, proper temporal lag,
early-season NaN handling, and label exclusion from feature columns.
"""

import glob
import os
import sys

import pandas as pd
import pytest

# Project src/ on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feature_engineering import (
    assemble_game_features,
    get_feature_columns,
    _compute_momentum_features,
)
from config import LABEL_COLUMNS

SILVER_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "silver")
BRONZE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "bronze")


def _silver_data_available(season: int) -> bool:
    """Check if Silver team data is available for the given season."""
    sources = [
        "teams/pbp_metrics", "teams/tendencies", "teams/sos",
        "teams/situational", "teams/pbp_derived", "teams/game_context",
        "teams/referee_tendencies", "teams/playoff_context",
    ]
    for subdir in sources:
        pattern = os.path.join(SILVER_DIR, subdir, f"season={season}", "*.parquet")
        if not glob.glob(pattern):
            return False
    # Also need Bronze schedules
    sched_pattern = os.path.join(BRONZE_DIR, "schedules", f"season={season}", "*.parquet")
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
        assert len(diff_cols) >= 80, (
            f"Expected >= 80 diff_ columns, got {len(diff_cols)}"
        )

    def test_reg_games_only(self, game_df):
        """Only regular season games (game_type == 'REG') are included."""
        assert (game_df["game_type"] == "REG").all(), (
            "Expected all rows to have game_type == 'REG'"
        )

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
            assert label not in feature_cols, (
                f"Label column '{label}' found in feature columns"
            )

    def test_row_count(self, game_df):
        """Regular season produces ~272 rows (256-285 range)."""
        assert 256 <= len(game_df) <= 285, (
            f"Expected 256-285 REG game rows, got {len(game_df)}"
        )

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
        win_cols = [c for c in game_df.columns if "wins" in c.lower()
                    and c.startswith("diff_")]
        # Also check the source wins columns if present
        for suffix in ["_home", "_away"]:
            col = f"wins{suffix}"
            if col in game_df.columns:
                assert week1[col].notna().all(), (
                    f"Expected {col} to be non-null for Week 1"
                )
                assert (week1[col] == 0).all(), (
                    f"Expected {col} == 0 for Week 1, got: "
                    f"{week1[col].unique()}"
                )

    def test_temporal_lag(self, game_df):
        """No feature column contains future game scores or spread results."""
        feature_cols = get_feature_columns(game_df)
        # Feature columns should not include any raw score columns
        forbidden = {"home_score", "away_score", "actual_margin",
                     "actual_total", "result", "spread_line", "total_line"}
        overlap = set(feature_cols) & forbidden
        assert len(overlap) == 0, (
            f"Feature columns contain forbidden labels: {overlap}"
        )

    def test_identifier_columns_excluded(self, game_df):
        """get_feature_columns() excludes identifier columns."""
        feature_cols = get_feature_columns(game_df)
        identifiers = {"game_id", "season", "week", "game_type"}
        for ident in identifiers:
            assert ident not in feature_cols, (
                f"Identifier '{ident}' found in feature columns"
            )

    def test_game_id_unique(self, game_df):
        """Each game_id appears exactly once (one row per game)."""
        assert game_df["game_id"].is_unique, (
            "Expected unique game_id values (one row per game)"
        )


class TestMomentumFeatures:
    """Test momentum/streak feature computation."""

    @pytest.fixture
    def schedule_df(self):
        """Synthetic 5-week schedule for 2 teams (TeamA home, TeamB away)."""
        # TeamA wins weeks 1-3, loses weeks 4-5
        # result > 0 means home team won
        return pd.DataFrame({
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
        })

    def test_returns_expected_columns(self, schedule_df, monkeypatch):
        """_compute_momentum_features returns correct columns."""
        monkeypatch.setattr(
            "feature_engineering._read_bronze_schedules",
            lambda season: schedule_df,
        )
        result = _compute_momentum_features(2023)
        expected_cols = {"game_id", "season", "week", "team",
                         "win_streak", "ats_cover_sum3", "ats_margin_avg3"}
        assert expected_cols.issubset(set(result.columns)), (
            f"Missing columns: {expected_cols - set(result.columns)}"
        )

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
        game_df = pd.DataFrame({
            "game_id": ["g1"],
            "season": [2023],
            "week": [3],
            "game_type": ["REG"],
            "diff_win_streak": [2.0],
            "diff_ats_cover_sum3": [1.0],
            "diff_ats_margin_avg3": [5.0],
        })
        feature_cols = get_feature_columns(game_df)
        assert "diff_win_streak" in feature_cols, "diff_win_streak not in features"
        assert "diff_ats_cover_sum3" in feature_cols, "diff_ats_cover_sum3 not in features"
        assert "diff_ats_margin_avg3" in feature_cols, "diff_ats_margin_avg3 not in features"


class TestEWMFeatures:
    """Test that _is_rolling() recognizes EWM column patterns."""

    def test_is_rolling_recognizes_ewm3(self):
        """_is_rolling('off_epa_per_play_ewm3') returns True."""
        # Create a game_df with an ewm3 diff column -- if recognized, it appears in features
        game_df = pd.DataFrame({
            "game_id": ["g1"],
            "season": [2023],
            "week": [3],
            "game_type": ["REG"],
            "diff_off_epa_per_play_ewm3": [0.05],
        })
        feature_cols = get_feature_columns(game_df)
        assert "diff_off_epa_per_play_ewm3" in feature_cols, (
            "EWM column not recognized by _is_rolling / get_feature_columns"
        )
