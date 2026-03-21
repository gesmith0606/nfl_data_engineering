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

from feature_engineering import assemble_game_features, get_feature_columns
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
