"""Tests for src/nfl_data_integration.py (NFLDataFetcher facade)."""

import datetime as dt
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestAvailableSeasonsDateDerived:
    """Regression test: available_seasons must include the current NFL
    season without an annual hand-edit, derived from today's date."""

    def test_includes_current_season_from_march_onward(self):
        """From March onward, the current calendar year is available."""
        with patch("src.nfl_data_integration.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2026, 8, 8)
            from src.nfl_data_integration import NFLDataFetcher

            fetcher = NFLDataFetcher()

        assert 2026 in fetcher.available_seasons
        assert fetcher.available_seasons[-1] == 2026

    def test_excludes_upcoming_season_before_march(self):
        """Before March, the not-yet-started season isn't included yet."""
        with patch("src.nfl_data_integration.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2026, 1, 15)
            from src.nfl_data_integration import NFLDataFetcher

            fetcher = NFLDataFetcher()

        assert fetcher.available_seasons[-1] == 2025
        assert 2026 not in fetcher.available_seasons

    def test_valid_seasons_accepts_current_season(self):
        """_valid_seasons (used by fetch_injuries/fetch_pbp/etc.) must accept
        the live current season instead of raising ValueError."""
        with patch("src.nfl_data_integration.datetime") as mock_dt:
            mock_dt.now.return_value = dt.datetime(2026, 8, 8)
            from src.nfl_data_integration import NFLDataFetcher

            fetcher = NFLDataFetcher()

        assert fetcher._valid_seasons([2026]) == [2026]


class TestFetchTeamStatsAliasNormalization:
    """Regression test: fetch_team_stats must normalize team codes before
    merging seasonal enrichment onto team descriptions, so alias drift
    (LAR/LA, WSH/WAS) doesn't silently produce NaN enrichment columns."""

    def test_merge_survives_team_code_aliases(self):
        from src.nfl_data_integration import NFLDataFetcher

        # Mirrors real fetch_team_descriptions() output shape: relocated
        # franchises appear as two historical team_abbr rows (LA and LAR).
        team_df = pd.DataFrame({
            "team_abbr": ["LA", "LAR", "WAS", "KC"],
            "team_name": [
                "Los Angeles Rams", "Los Angeles Rams",
                "Washington Commanders", "Kansas City Chiefs",
            ],
        })
        # Seasonal enrichment source uses raw nfl-data-py codes, which drift
        # from the nflverse canonical team_abbr codes above.
        seasonal_data = pd.DataFrame({
            "team": ["LAR", "WSH", "KC"],
            "passing_yards": [4000, 3500, 4200],
        })

        fake_adapter = MagicMock()
        fake_adapter.fetch_team_descriptions.return_value = team_df
        fake_adapter.fetch_seasonal_data.return_value = seasonal_data

        fetcher = NFLDataFetcher()
        with patch.object(fetcher, "_get_adapter", return_value=fake_adapter):
            result = fetcher.fetch_team_stats([2025])

        merged = result.set_index("team_abbr")
        assert merged.loc["LA", "passing_yards"] == 4000
        assert merged.loc["LAR", "passing_yards"] == 4000
        assert merged.loc["WAS", "passing_yards"] == 3500
        assert merged.loc["KC", "passing_yards"] == 4200
        assert not result["passing_yards"].isna().any()
