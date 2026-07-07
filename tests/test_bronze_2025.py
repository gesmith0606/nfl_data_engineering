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

# BRNZ-03 audits the LOCAL data lake. CI checkouts only carry the committed
# Bronze subset (schedules/rosters/sentiment/madden — see .gitignore
# allowlists); PBP is never committed, so its presence is the canary for a
# full local lake. Skip the whole audit in environments without one.
_FULL_LAKE_PRESENT = os.path.isdir(os.path.join(BRONZE_DIR, "pbp"))

pytestmark = pytest.mark.skipif(
    not _FULL_LAKE_PRESENT,
    reason="local Bronze data lake not present (CI carries only the committed "
    "subset) — BRNZ-03 completeness audit only applies to a full local lake",
)


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

    def test_injuries_valid_for_2025(self):
        """Injuries follow dynamic bounds — the 2024 nflverse cap was disproven
        2026-07-02 (see DATA_TYPE_SEASON_RANGES comment in src/config.py)."""
        from src.config import validate_season_for_type
        assert validate_season_for_type("injuries", 2025) is True, \
            "Injuries should be valid for 2025 (dynamic bounds since 2026-07-02)"

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
