"""
Tests for Phase 3 Advanced Stats & Context Data ingestion.

Covers requirements ADV-01 through ADV-05 (NGS, PFR weekly, PFR seasonal, QBR,
depth charts), CTX-01 (draft picks), CTX-02 (combine), and VAL-03 (validation).

All tests mock nfl-data-py to avoid API dependency.
"""

import argparse
import os
import sys
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# Ensure project root is on path for script imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.nfl_data_adapter import NFLDataAdapter


# ------------------------------------------------------------------
# Helper: build mock DataFrames with required columns
# ------------------------------------------------------------------

def _ngs_df():
    """DataFrame with required NGS columns."""
    return pd.DataFrame({
        "season": [2024],
        "season_type": ["REG"],
        "week": [1],
        "player_display_name": ["Patrick Mahomes"],
        "player_position": ["QB"],
        "team_abbr": ["KC"],
        "player_gsis_id": ["00-0033873"],
    })


def _pfr_weekly_df():
    """DataFrame with required PFR weekly columns."""
    return pd.DataFrame({
        "game_id": ["2024_01_KC_BAL"],
        "season": [2024],
        "week": [1],
        "team": ["KC"],
        "pfr_player_name": ["Patrick Mahomes"],
        "pfr_player_id": ["MahoPa00"],
    })


def _pfr_seasonal_df():
    """DataFrame with required PFR seasonal columns."""
    return pd.DataFrame({
        "player": ["Patrick Mahomes"],
        "team": ["KC"],
        "season": [2024],
        "pfr_id": ["MahoPa00"],
    })


def _qbr_df():
    """DataFrame with required QBR columns."""
    return pd.DataFrame({
        "season": [2024],
        "season_type": ["Regular"],
        "qbr_total": [72.5],
        "pts_added": [45.3],
        "epa_total": [120.1],
        "qb_plays": [580],
    })


def _depth_charts_df():
    """DataFrame with required depth charts columns."""
    return pd.DataFrame({
        "season": [2024],
        "club_code": ["KC"],
        "week": [1],
        "position": ["QB"],
        "full_name": ["Patrick Mahomes"],
        "gsis_id": ["00-0033873"],
    })


def _draft_picks_df():
    """DataFrame with required draft picks columns."""
    return pd.DataFrame({
        "season": [2024],
        "round": [1],
        "pick": [10],
        "team": ["KC"],
        "pfr_player_name": ["Xavier Worthy"],
        "position": ["WR"],
    })


def _combine_df():
    """DataFrame with required combine columns."""
    return pd.DataFrame({
        "season": [2024],
        "player_name": ["Xavier Worthy"],
        "pos": ["WR"],
        "school": ["Texas"],
        "ht": ["5-11"],
        "wt": [165],
    })


# ------------------------------------------------------------------
# ADV-01: NGS ingestion
# ------------------------------------------------------------------

class TestNGSIngestion:
    """Tests for fetch_ngs across all stat types (ADV-01)."""

    @pytest.mark.parametrize("stat_type", ["passing", "rushing", "receiving"])
    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_ngs_returns_dataframe(self, mock_import_nfl, stat_type):
        """fetch_ngs returns non-empty DataFrame for each stat_type."""
        mock_nfl = MagicMock()
        mock_nfl.import_ngs_data.return_value = _ngs_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_ngs([2024], stat_type=stat_type)

        assert not df.empty
        mock_nfl.import_ngs_data.assert_called_once()


# ------------------------------------------------------------------
# ADV-02: PFR weekly ingestion
# ------------------------------------------------------------------

class TestPFRWeeklyIngestion:
    """Tests for fetch_pfr_weekly across all s_types (ADV-02)."""

    @pytest.mark.parametrize("s_type", ["pass", "rush", "rec", "def"])
    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_pfr_weekly_returns_dataframe(self, mock_import_nfl, s_type):
        """fetch_pfr_weekly returns non-empty DataFrame for each s_type."""
        mock_nfl = MagicMock()
        mock_nfl.import_weekly_pfr.return_value = _pfr_weekly_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_pfr_weekly([2024], s_type=s_type)

        assert not df.empty
        mock_nfl.import_weekly_pfr.assert_called_once()


# ------------------------------------------------------------------
# ADV-03: PFR seasonal ingestion
# ------------------------------------------------------------------

class TestPFRSeasonalIngestion:
    """Tests for fetch_pfr_seasonal across all s_types (ADV-03)."""

    @pytest.mark.parametrize("s_type", ["pass", "rush", "rec", "def"])
    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_pfr_seasonal_returns_dataframe(self, mock_import_nfl, s_type):
        """fetch_pfr_seasonal returns non-empty DataFrame for each s_type."""
        mock_nfl = MagicMock()
        mock_nfl.import_seasonal_pfr.return_value = _pfr_seasonal_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_pfr_seasonal([2024], s_type=s_type)

        assert not df.empty
        mock_nfl.import_seasonal_pfr.assert_called_once()


# ------------------------------------------------------------------
# ADV-04: QBR ingestion (both frequencies)
# ------------------------------------------------------------------

class TestQBRIngestion:
    """Tests for fetch_qbr — weekly and seasonal frequency (ADV-04)."""

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_qbr_weekly(self, mock_import_nfl):
        """fetch_qbr with frequency='weekly' returns non-empty DataFrame."""
        mock_nfl = MagicMock()
        mock_nfl.import_qbr.return_value = _qbr_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_qbr([2024], frequency="weekly")

        assert not df.empty
        mock_nfl.import_qbr.assert_called_once_with(
            years=[2024], frequency="weekly"
        )

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_qbr_seasonal(self, mock_import_nfl):
        """fetch_qbr with frequency='season' returns non-empty DataFrame."""
        mock_nfl = MagicMock()
        mock_nfl.import_qbr.return_value = _qbr_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_qbr([2024], frequency="season")

        assert not df.empty
        mock_nfl.import_qbr.assert_called_once_with(
            years=[2024], frequency="season"
        )


# ------------------------------------------------------------------
# ADV-05: Depth charts ingestion
# ------------------------------------------------------------------

class TestDepthChartsIngestion:
    """Tests for fetch_depth_charts (ADV-05)."""

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_depth_charts_returns_dataframe(self, mock_import_nfl):
        """fetch_depth_charts returns non-empty DataFrame."""
        mock_nfl = MagicMock()
        mock_nfl.import_depth_charts.return_value = _depth_charts_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_depth_charts([2024])

        assert not df.empty
        mock_nfl.import_depth_charts.assert_called_once_with([2024])


# ------------------------------------------------------------------
# CTX-01: Draft picks ingestion
# ------------------------------------------------------------------

class TestDraftPicksIngestion:
    """Tests for fetch_draft_picks (CTX-01)."""

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_draft_picks_returns_dataframe(self, mock_import_nfl):
        """fetch_draft_picks returns non-empty DataFrame."""
        mock_nfl = MagicMock()
        mock_nfl.import_draft_picks.return_value = _draft_picks_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_draft_picks([2024])

        assert not df.empty
        mock_nfl.import_draft_picks.assert_called_once_with([2024])


# ------------------------------------------------------------------
# CTX-02: Combine ingestion
# ------------------------------------------------------------------

class TestCombineIngestion:
    """Tests for fetch_combine (CTX-02)."""

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_combine_returns_dataframe(self, mock_import_nfl):
        """fetch_combine returns non-empty DataFrame."""
        mock_nfl = MagicMock()
        mock_nfl.import_combine_data.return_value = _combine_df()
        mock_import_nfl.return_value = mock_nfl

        adapter = NFLDataAdapter()
        df = adapter.fetch_combine([2024])

        assert not df.empty
        mock_nfl.import_combine_data.assert_called_once_with([2024])


# ------------------------------------------------------------------
# VAL-03: validate_data() for new types
# ------------------------------------------------------------------

class TestValidation:
    """Tests for validate_data() with new data types (VAL-03)."""

    def test_validate_data_accepts_valid_ngs(self):
        """validate_data('ngs') returns is_valid=True for valid DataFrame."""
        from src.nfl_data_integration import NFLDataFetcher

        fetcher = NFLDataFetcher()
        result = fetcher.validate_data(_ngs_df(), "ngs")

        assert result["is_valid"] is True

    @pytest.mark.parametrize(
        "data_type,df_factory,drop_col",
        [
            ("ngs", _ngs_df, "player_gsis_id"),
            ("pfr_weekly", _pfr_weekly_df, "pfr_player_id"),
            ("pfr_seasonal", _pfr_seasonal_df, "pfr_id"),
            ("qbr", _qbr_df, "qbr_total"),
            ("depth_charts", _depth_charts_df, "gsis_id"),
            ("draft_picks", _draft_picks_df, "position"),
            ("combine", _combine_df, "wt"),
        ],
    )
    def test_validate_data_rejects_missing_columns(
        self, data_type, df_factory, drop_col
    ):
        """validate_data() returns is_valid=False when a required column is missing."""
        from src.nfl_data_integration import NFLDataFetcher

        fetcher = NFLDataFetcher()
        df = df_factory().drop(columns=[drop_col])
        result = fetcher.validate_data(df, data_type)

        assert result["is_valid"] is False
        assert any("Missing required columns" in issue for issue in result["issues"])


# ------------------------------------------------------------------
# QBR frequency kwarg wiring
# ------------------------------------------------------------------

class TestQBRFrequencyKwargs:
    """Test that CLI correctly wires QBR frequency to adapter kwargs."""

    def test_qbr_frequency_from_args(self):
        """_build_method_kwargs passes frequency from args for QBR."""
        from scripts.bronze_ingestion_simple import (
            _build_method_kwargs,
            DATA_TYPE_REGISTRY,
        )

        entry = DATA_TYPE_REGISTRY["qbr"]
        args = argparse.Namespace(
            season=2024, week=None, sub_type=None, frequency="seasonal"
        )
        kwargs = _build_method_kwargs(entry, args)

        assert kwargs["frequency"] == "seasonal"
