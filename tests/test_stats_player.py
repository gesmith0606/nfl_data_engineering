"""Tests for stats_player adapter (2025+ player data via nflverse stats_player tag)."""

import io
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.config import STATS_PLAYER_COLUMN_MAP, STATS_PLAYER_MIN_SEASON


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_stats_player_weekly_df(season: int = 2025) -> pd.DataFrame:
    """Build a 10-row mock DataFrame mimicking the stats_player_week schema.

    Contains the *new* column names (before mapping) plus a handful of
    representative counting-stat columns used in aggregation.

    Layout: 3 QBs (KC weeks 1-3), 3 RBs (KC weeks 1-2 + BUF week 3),
    4 WRs (BUF weeks 1-4) -- 10 rows total.
    """
    n = 10
    return pd.DataFrame({
        "player_id": ["QB01"] * 3 + ["RB01"] * 2 + ["RB02"] + ["WR01"] * 2 + ["WR02"] * 2,
        "player_name": ["P Mahomes"] * 3 + ["I Pacheco"] * 2 + ["J Cook"] + ["S Diggs"] * 2 + ["G Davis"] * 2,
        "player_display_name": ["Patrick Mahomes"] * 3 + ["Isiah Pacheco"] * 2 + ["James Cook"] + ["Stefon Diggs"] * 2 + ["Gabe Davis"] * 2,
        "position": ["QB"] * 3 + ["RB"] * 3 + ["WR"] * 4,
        "position_group": ["QB"] * 3 + ["RB"] * 3 + ["WR"] * 4,
        "headshot_url": ["http://img"] * n,
        # New column names that need mapping
        "team": ["KC"] * 5 + ["BUF"] * 5,
        "passing_interceptions": [1, 0, 2, 0, 0, 0, 0, 0, 0, 0],
        "sacks_suffered": [2, 1, 3, 0, 0, 0, 0, 0, 0, 0],
        "sack_yards_lost": [14, 7, 21, 0, 0, 0, 0, 0, 0, 0],
        "passing_cpoe": [3.5, 1.2, -0.5, None, None, None, None, None, None, None],
        # Standard columns present in both schemas
        "season": [season] * n,
        "week": [1, 2, 3, 1, 2, 3, 1, 2, 1, 2],
        "season_type": ["REG"] * 8 + ["POST"] * 2,
        "attempts": [30, 25, 35, 0, 0, 0, 0, 0, 0, 0],
        "completions": [20, 18, 22, 0, 0, 0, 0, 0, 0, 0],
        "passing_yards": [280, 210, 350, 0, 0, 0, 0, 0, 0, 0],
        "passing_tds": [2, 1, 3, 0, 0, 0, 0, 0, 0, 0],
        "carries": [0, 0, 0, 15, 12, 18, 0, 0, 0, 0],
        "rushing_yards": [0, 0, 0, 75, 60, 90, 0, 0, 0, 0],
        "rushing_tds": [0, 0, 0, 1, 0, 2, 0, 0, 0, 0],
        "receptions": [0, 0, 0, 2, 3, 1, 5, 7, 6, 4],
        "targets": [0, 0, 0, 3, 4, 2, 8, 10, 9, 6],
        "receiving_yards": [0, 0, 0, 15, 25, 10, 70, 95, 80, 50],
        "receiving_tds": [0, 0, 0, 0, 1, 0, 1, 2, 1, 0],
        "receiving_air_yards": [0, 0, 0, 5, 8, 3, 30, 40, 35, 20],
        "receiving_yards_after_catch": [0, 0, 0, 10, 17, 7, 40, 55, 45, 30],
        "receiving_first_downs": [0, 0, 0, 1, 2, 0, 3, 5, 4, 2],
        "receiving_epa": [0.0, 0.0, 0.0, 0.5, 1.2, -0.3, 2.1, 3.5, 2.8, 1.0],
        "receiving_2pt_conversions": [0] * n,
        "rushing_fumbles": [0] * n,
        "rushing_fumbles_lost": [0] * n,
        "rushing_first_downs": [0, 0, 0, 3, 2, 4, 0, 0, 0, 0],
        "rushing_epa": [0.0, 0.0, 0.0, 1.5, 0.8, 2.3, 0.0, 0.0, 0.0, 0.0],
        "rushing_2pt_conversions": [0] * n,
        "receiving_fumbles": [0] * n,
        "receiving_fumbles_lost": [0] * n,
        "sack_fumbles": [0] * n,
        "sack_fumbles_lost": [0] * n,
        "passing_air_yards": [40, 35, 50, 0, 0, 0, 0, 0, 0, 0],
        "passing_yards_after_catch": [20, 15, 25, 0, 0, 0, 0, 0, 0, 0],
        "passing_first_downs": [10, 8, 12, 0, 0, 0, 0, 0, 0, 0],
        "passing_epa": [5.0, 3.0, 8.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "passing_2pt_conversions": [0] * n,
        "special_teams_tds": [0] * n,
        "fantasy_points": [15.0, 10.0, 20.0, 12.0, 10.0, 16.0, 8.0, 12.5, 10.5, 6.0],
        "fantasy_points_ppr": [15.0, 10.0, 20.0, 14.0, 13.0, 17.0, 13.0, 19.5, 16.5, 10.0],
    })


# ---------------------------------------------------------------------------
# Task 1 Tests: Config constants and column mapping
# ---------------------------------------------------------------------------

class TestConfigConstants:
    """Verify stats_player config constants exist and have correct values."""

    def test_min_season_equals_2025(self):
        assert STATS_PLAYER_MIN_SEASON == 2025

    def test_column_map_has_all_five_renames(self):
        expected_keys = {
            "passing_interceptions",
            "sacks_suffered",
            "sack_yards_lost",
            "team",
            "passing_cpoe",
        }
        assert set(STATS_PLAYER_COLUMN_MAP.keys()) == expected_keys

    def test_column_map_target_names(self):
        assert STATS_PLAYER_COLUMN_MAP["passing_interceptions"] == "interceptions"
        assert STATS_PLAYER_COLUMN_MAP["sacks_suffered"] == "sacks"
        assert STATS_PLAYER_COLUMN_MAP["sack_yards_lost"] == "sack_yards"
        assert STATS_PLAYER_COLUMN_MAP["team"] == "recent_team"
        assert STATS_PLAYER_COLUMN_MAP["passing_cpoe"] == "dakota"


class TestColumnMapping:
    """Verify column mapping applied to a DataFrame renames correctly."""

    def test_rename_all_five_columns(self):
        df = _make_stats_player_weekly_df()
        mapped = df.rename(columns=STATS_PLAYER_COLUMN_MAP)

        # Old (new-schema) names should be gone
        assert "passing_interceptions" not in mapped.columns
        assert "sacks_suffered" not in mapped.columns
        assert "sack_yards_lost" not in mapped.columns
        assert "team" not in mapped.columns
        assert "passing_cpoe" not in mapped.columns

        # Backward-compatible names should be present
        assert "interceptions" in mapped.columns
        assert "sacks" in mapped.columns
        assert "sack_yards" in mapped.columns
        assert "recent_team" in mapped.columns
        assert "dakota" in mapped.columns

    def test_mapping_preserves_values(self):
        df = _make_stats_player_weekly_df()
        original_ints = df["passing_interceptions"].tolist()
        mapped = df.rename(columns=STATS_PLAYER_COLUMN_MAP)
        assert mapped["interceptions"].tolist() == original_ints


class TestRoutingLogic:
    """Verify season routing based on STATS_PLAYER_MIN_SEASON threshold."""

    def test_seasons_below_threshold_not_routed_to_stats_player(self):
        """Seasons < 2025 should go through old nfl.import_weekly_data path."""
        seasons = [2022, 2023, 2024]
        old = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]
        assert old == [2022, 2023, 2024]
        assert new == []

    def test_seasons_at_threshold_routed_to_stats_player(self):
        """Season 2025 should go through stats_player path."""
        seasons = [2025]
        old = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]
        assert old == []
        assert new == [2025]

    def test_mixed_seasons_split_correctly(self):
        """Mixed list should split at the threshold."""
        seasons = [2023, 2024, 2025, 2026]
        old = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]
        assert old == [2023, 2024]
        assert new == [2025, 2026]
