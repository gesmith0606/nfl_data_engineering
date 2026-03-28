"""
Smoke tests for 2025 Bronze data completeness (BRNZ-03).

Verifies all 7 available core data types are ingested for 2025.
Injuries are excluded -- nflverse caps injury data at 2024.
"""
import glob
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BRONZE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "bronze")


class TestBronze2025Completeness:
    """BRNZ-03: 2025 season data exists for all available Bronze types."""

    def test_schedules_exist(self):
        files = glob.glob(os.path.join(BRONZE_DIR, "schedules", "season=2025", "*.parquet"))
        assert len(files) >= 1, "No 2025 schedules parquet found"

    def test_schedules_row_count(self):
        """D-06: 2025 schedules must have >= 285 games."""
        files = sorted(glob.glob(os.path.join(BRONZE_DIR, "schedules", "season=2025", "*.parquet")))
        df = pd.read_parquet(files[-1])
        assert len(df) >= 285, f"2025 schedules has {len(df)} rows, expected >= 285"

    def test_pbp_exists(self):
        files = glob.glob(os.path.join(BRONZE_DIR, "pbp", "season=2025", "*.parquet"))
        assert len(files) >= 1, "No 2025 PBP parquet found"

    def test_pbp_row_count(self):
        """2025 PBP should have >= 40000 rows (full season)."""
        files = sorted(glob.glob(os.path.join(BRONZE_DIR, "pbp", "season=2025", "*.parquet")))
        df = pd.read_parquet(files[-1])
        assert len(df) >= 40000, f"2025 PBP has {len(df)} rows, expected >= 40000"

    def test_player_weekly_exists(self):
        files = glob.glob(os.path.join(BRONZE_DIR, "players", "weekly", "season=2025", "*.parquet"))
        assert len(files) >= 1, "No 2025 player_weekly parquet found"

    def test_player_seasonal_exists(self):
        files = glob.glob(os.path.join(BRONZE_DIR, "players", "seasonal", "season=2025", "*.parquet"))
        assert len(files) >= 1, "No 2025 player_seasonal parquet found"

    def test_snap_counts_exist(self):
        """2025 snap counts should have >= 18 week subdirectories."""
        week_dirs = glob.glob(os.path.join(BRONZE_DIR, "players", "snaps", "season=2025", "week=*"))
        assert len(week_dirs) >= 18, f"2025 snap counts has {len(week_dirs)} weeks, expected >= 18"

    def test_rosters_exist(self):
        files = glob.glob(os.path.join(BRONZE_DIR, "players", "rosters", "season=2025", "*.parquet"))
        assert len(files) >= 1, "No 2025 rosters parquet found"

    def test_teams_exist(self):
        """Teams data exists (no season partition)."""
        files = glob.glob(os.path.join(BRONZE_DIR, "teams", "*.parquet"))
        assert len(files) >= 1, "No teams parquet found"

    def test_injuries_unavailable_for_2025(self):
        """Document known gap: nflverse caps injuries at 2024."""
        from src.config import validate_season_for_type
        assert validate_season_for_type("injuries", 2025) is False, \
            "Injuries should NOT be valid for 2025 (nflverse caps at 2024)"

    def test_all_7_available_types_present(self):
        """Meta-test: all 7 available core types have 2025 data."""
        checks = {
            "schedules": glob.glob(os.path.join(BRONZE_DIR, "schedules", "season=2025", "*.parquet")),
            "pbp": glob.glob(os.path.join(BRONZE_DIR, "pbp", "season=2025", "*.parquet")),
            "player_weekly": glob.glob(os.path.join(BRONZE_DIR, "players", "weekly", "season=2025", "*.parquet")),
            "player_seasonal": glob.glob(os.path.join(BRONZE_DIR, "players", "seasonal", "season=2025", "*.parquet")),
            "snap_counts": glob.glob(os.path.join(BRONZE_DIR, "players", "snaps", "season=2025", "week=*")),
            "rosters": glob.glob(os.path.join(BRONZE_DIR, "players", "rosters", "season=2025", "*.parquet")),
            "teams": glob.glob(os.path.join(BRONZE_DIR, "teams", "*.parquet")),
        }
        missing = [dtype for dtype, files in checks.items() if len(files) == 0]
        assert len(missing) == 0, f"Missing 2025 Bronze data types: {missing}"
