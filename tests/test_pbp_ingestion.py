"""
Tests for PBP ingestion: column curation, adapter wiring, CLI batch, range coverage.

Covers requirements PBP-01 (curated columns), PBP-02 (single-season processing),
PBP-03 (column subsetting via kwargs), PBP-04 (output path and batch range),
INGEST-09 (2016-2025 range coverage, exact column count regression guard).
"""

import argparse
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on path for script imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ------------------------------------------------------------------
# PBP-01: PBP_COLUMNS constant
# ------------------------------------------------------------------


class TestPBPColumns:
    """Tests for the PBP_COLUMNS config constant (PBP-01)."""

    def test_pbp_columns_has_key_metrics(self):
        """PBP_COLUMNS must contain EPA, WPA, CPOE, air_yards, success,
        plus game_id, play_id, season, week identifiers."""
        from src.config import PBP_COLUMNS

        required = [
            "epa",
            "wpa",
            "cpoe",
            "air_yards",
            "success",
            "game_id",
            "play_id",
            "season",
            "week",
        ]
        for col in required:
            assert col in PBP_COLUMNS, f"Missing required column: {col}"

    def test_pbp_columns_count(self):
        """PBP_COLUMNS should have between 128 and 160 entries."""
        from src.config import PBP_COLUMNS

        assert (
            128 <= len(PBP_COLUMNS) <= 160
        ), f"Expected 128-160 columns, got {len(PBP_COLUMNS)}"

    def test_pbp_columns_no_participation(self):
        """PBP_COLUMNS must NOT contain participation merge columns."""
        from src.config import PBP_COLUMNS

        forbidden = ["offense_players", "defense_players"]
        for col in forbidden:
            assert (
                col not in PBP_COLUMNS
            ), f"Participation column '{col}' should not be in PBP_COLUMNS"


# ------------------------------------------------------------------
# PBP-02: Single-season processing
# ------------------------------------------------------------------


class TestSingleSeasonProcessing:
    """Verify PBP is fetched one season at a time (PBP-02)."""

    @patch("src.nfl_data_adapter.NFLDataAdapter._import_nfl")
    def test_single_season_processing(self, mock_import_nfl):
        """fetch_pbp must receive seasons=[single_int], not a multi-season list."""
        import pandas as pd
        from src.nfl_data_adapter import NFLDataAdapter

        mock_nfl = MagicMock()
        mock_nfl.import_pbp_data.return_value = pd.DataFrame({"epa": [0.5]})
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        adapter.fetch_pbp(seasons=[2024])

        mock_nfl.import_pbp_data.assert_called_once()
        call_args = mock_nfl.import_pbp_data.call_args
        # First positional arg should be [2024] (single-element list)
        assert call_args[0][0] == [2024]


# ------------------------------------------------------------------
# PBP-03: Column subsetting via _build_method_kwargs
# ------------------------------------------------------------------


class TestColumnSubsetting:
    """Verify CLI wires columns/downcast/include_participation (PBP-03)."""

    def test_column_subsetting(self):
        """_build_method_kwargs for pbp must include columns=PBP_COLUMNS
        and downcast=True."""
        from scripts.bronze_ingestion_simple import (
            _build_method_kwargs,
            DATA_TYPE_REGISTRY,
        )
        from src.config import PBP_COLUMNS

        entry = DATA_TYPE_REGISTRY["pbp"]
        args = argparse.Namespace(season=2024, week=1, sub_type=None)
        kwargs = _build_method_kwargs(entry, args)

        assert "columns" in kwargs, "kwargs must contain 'columns'"
        assert kwargs["columns"] is PBP_COLUMNS
        assert kwargs.get("downcast") is True

    def test_include_participation_false(self):
        """_build_method_kwargs for pbp must include include_participation=False."""
        from scripts.bronze_ingestion_simple import (
            _build_method_kwargs,
            DATA_TYPE_REGISTRY,
        )

        entry = DATA_TYPE_REGISTRY["pbp"]
        args = argparse.Namespace(season=2024, week=1, sub_type=None)
        kwargs = _build_method_kwargs(entry, args)

        assert (
            "include_participation" in kwargs
        ), "kwargs must contain 'include_participation'"
        assert kwargs["include_participation"] is False


# ------------------------------------------------------------------
# PBP-04: Output path and batch range
# ------------------------------------------------------------------


class TestPBPOutputPath:
    """Verify PBP output path structure (PBP-04)."""

    def test_pbp_output_path(self):
        """PBP registry bronze_path must produce data/bronze/pbp/season=YYYY/."""
        from scripts.bronze_ingestion_simple import DATA_TYPE_REGISTRY

        entry = DATA_TYPE_REGISTRY["pbp"]
        path = entry["bronze_path"].format(season=2024, week=1)
        local_dir = os.path.join("data", "bronze", path)

        assert "pbp/season=2024" in local_dir


class TestSeasonsRangeParsing:
    """Verify --seasons range parsing (PBP-04)."""

    def test_seasons_range_parsing(self):
        """--seasons 2010-2025 must parse into list [2010, ..., 2025]."""
        from scripts.bronze_ingestion_simple import parse_seasons_range

        result = parse_seasons_range("2010-2025")
        assert result == list(range(2010, 2026))

    def test_seasons_single(self):
        """--seasons 2024 (single value) must parse into [2024]."""
        from scripts.bronze_ingestion_simple import parse_seasons_range

        result = parse_seasons_range("2024")
        assert result == [2024]

    def test_seasons_invalid_range(self):
        """--seasons 2025-2010 (reversed) should raise ValueError."""
        from scripts.bronze_ingestion_simple import parse_seasons_range

        with pytest.raises(ValueError):
            parse_seasons_range("2025-2010")


# ------------------------------------------------------------------
# INGEST-09: PBP season range coverage and regression guards
# ------------------------------------------------------------------


class TestPBPRangeCoverage:
    """Verify PBP config supports full 2016-2025 backfill range (INGEST-09)."""

    def test_pbp_seasons_2016_2025_valid(self):
        """Every season 2016-2025 must be valid for the pbp data type."""
        from src.config import validate_season_for_type

        for season in range(2016, 2026):
            assert validate_season_for_type(
                "pbp", season
            ), f"Season {season} should be valid for pbp"

    def test_pbp_columns_exact_count_141(self):
        """PBP_COLUMNS must have exactly 141 entries (regression guard)."""
        from src.config import PBP_COLUMNS

        assert (
            len(PBP_COLUMNS) == 141
        ), f"PBP_COLUMNS regression: expected exactly 141, got {len(PBP_COLUMNS)}"

    def test_pbp_season_range_lower_bound(self):
        """PBP data type must support seasons back to at least 1999."""
        from src.config import DATA_TYPE_SEASON_RANGES

        min_season, _ = DATA_TYPE_SEASON_RANGES["pbp"]
        assert min_season <= 1999, f"PBP min season should be <= 1999, got {min_season}"
