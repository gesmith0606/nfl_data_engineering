#!/usr/bin/env python3
"""
NFL Data Integration Functions
Legacy fetch facade + canonical Bronze validation (``validate_data``).

All data fetching delegates to ``src/nfl_data_adapter.py`` (NFLDataAdapter),
the single module allowed to import ``nfl_data_py``. ``NFLDataFetcher`` is
kept as a thin compatibility shim for its existing callers; it preserves the
legacy contract on top of the adapter:

* raises on fetch failure (the adapter returns empty DataFrames instead),
* optional ``week=`` filtering,
* ``data_source`` / ``ingestion_timestamp`` metadata columns.

Do not add new fetch callers here — use ``NFLDataAdapter`` directly.
``validate_data()`` lives here and is the single validation implementation
(the adapter's ``validate_data`` delegates to it).
"""

import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import logging
from config import get_max_season

# Library module: logging configuration belongs to entrypoints, not here.
logger = logging.getLogger(__name__)


class NFLDataFetcher:
    """Legacy facade over :class:`NFLDataAdapter` with error handling and validation."""

    def __init__(self):
        self.available_seasons = list(range(1999, 2026))  # nfl-data-py coverage
        self._adapter = None

    def _get_adapter(self):
        """Lazily construct the shared NFLDataAdapter instance."""
        if self._adapter is None:
            from nfl_data_adapter import NFLDataAdapter

            self._adapter = NFLDataAdapter()
        return self._adapter

    def _valid_seasons(self, seasons: List[int]) -> List[int]:
        """Filter to seasons within nfl-data-py coverage, raising if none remain."""
        invalid_seasons = [s for s in seasons if s not in self.available_seasons]
        if invalid_seasons:
            logger.warning(f"Invalid seasons requested: {invalid_seasons}")
        valid_seasons = [s for s in seasons if s in self.available_seasons]
        if not valid_seasons:
            raise ValueError("No valid seasons provided")
        return valid_seasons

    @staticmethod
    def _require_data(df: pd.DataFrame, label: str) -> pd.DataFrame:
        """Convert the adapter's empty-on-error result back into an exception.

        Legacy callers rely on fetch methods raising on failure rather than
        silently receiving an empty DataFrame.
        """
        if df.empty:
            raise RuntimeError(f"{label} returned no data (fetch failed or empty)")
        return df

    @staticmethod
    def _add_metadata(df: pd.DataFrame) -> pd.DataFrame:
        df["data_source"] = "nfl-data-py"
        df["ingestion_timestamp"] = datetime.now()
        return df

    @staticmethod
    def _filter_week(df: pd.DataFrame, week: Optional[int]) -> pd.DataFrame:
        if week is not None and "week" in df.columns:
            df = df[df["week"] == week].copy()
            logger.info(f"Filtered to {len(df)} rows for week {week}")
        return df

    def fetch_game_schedules(
        self, seasons: List[int], week: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch NFL game schedules

        Args:
            seasons: List of seasons to fetch
            week: Specific week to filter (optional)

        Returns:
            DataFrame with game schedule data
        """
        try:
            logger.info(f"Fetching schedules for seasons: {seasons}")
            valid_seasons = self._valid_seasons(seasons)

            schedule_df = self._require_data(
                self._get_adapter().fetch_schedules(valid_seasons),
                "fetch_game_schedules",
            )
            logger.info(f"Fetched {len(schedule_df)} total games")

            schedule_df = self._filter_week(schedule_df, week)

            schedule_df = self._add_metadata(schedule_df)
            schedule_df["seasons_requested"] = str(seasons)
            schedule_df["week_filter"] = week
            return schedule_df

        except Exception as e:
            logger.error(f"Error fetching game schedules: {str(e)}")
            raise

    def fetch_play_by_play(
        self,
        seasons: List[int],
        columns: Optional[List[str]] = None,
        week: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Fetch play-by-play data

        Args:
            seasons: List of seasons to fetch
            columns: Specific columns to fetch (optional)
            week: Specific week to filter (optional)

        Returns:
            DataFrame with play-by-play data
        """
        try:
            logger.info(f"Fetching play-by-play data for seasons: {seasons}")

            # Default columns if none specified
            if columns is None:
                columns = ['game_id', 'home_team', 'away_team', 'week', 'season',
                          'play_id', 'quarter_seconds_remaining', 'down', 'ydstogo',
                          'yards_gained', 'play_type', 'passer_player_name', 'receiver_player_name']

            valid_seasons = self._valid_seasons(seasons)

            pbp_df = self._require_data(
                self._get_adapter().fetch_pbp(valid_seasons, columns=columns),
                "fetch_play_by_play",
            )
            logger.info(f"Fetched {len(pbp_df)} plays")

            pbp_df = self._filter_week(pbp_df, week)
            return self._add_metadata(pbp_df)

        except Exception as e:
            logger.error(f"Error fetching play-by-play data: {str(e)}")
            raise

    def fetch_team_stats(self, seasons: List[int]) -> pd.DataFrame:
        """
        Fetch team statistics

        Args:
            seasons: List of seasons to fetch

        Returns:
            DataFrame with team stats
        """
        try:
            logger.info(f"Fetching team stats for seasons: {seasons}")
            adapter = self._get_adapter()

            # Get team descriptions (static data)
            team_df = self._require_data(
                adapter.fetch_team_descriptions(), "fetch_team_stats"
            )

            # Try to enrich with seasonal team data
            try:
                seasonal_data = adapter.fetch_seasonal_data(seasons)
                logger.info(f"Fetched seasonal data: {len(seasonal_data)} records")

                if 'team' in seasonal_data.columns and 'team_abbr' in team_df.columns:
                    team_df = team_df.merge(
                        seasonal_data.groupby('team').first().reset_index(),
                        left_on='team_abbr',
                        right_on='team',
                        how='left'
                    )
            except Exception as e:
                logger.warning(f"Could not fetch seasonal data: {str(e)}. Using team descriptions only.")

            return self._add_metadata(team_df)

        except Exception as e:
            logger.error(f"Error fetching team stats: {str(e)}")
            raise

    def fetch_player_weekly(
        self, seasons: List[int], week: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch weekly player statistics (rushing, receiving, passing).

        Delegates to ``NFLDataAdapter.fetch_weekly_data``, which also covers
        2025+ seasons via the nflverse ``stats_player`` release.

        Args:
            seasons: List of seasons to fetch
            week: Specific week to filter (optional)

        Returns:
            DataFrame with per-player weekly stats
        """
        try:
            logger.info(f"Fetching player weekly stats for seasons: {seasons}")
            valid_seasons = self._valid_seasons(seasons)

            df = self._require_data(
                self._get_adapter().fetch_weekly_data(valid_seasons),
                "fetch_player_weekly",
            )
            logger.info(f"Fetched {len(df)} player-week rows")

            df = self._filter_week(df, week)
            return self._add_metadata(df)

        except Exception as e:
            logger.error(f"Error fetching player weekly stats: {str(e)}")
            raise

    def fetch_snap_counts(
        self, seasons: List[int], week: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch snap counts and route participation per player per week.

        Args:
            seasons: List of seasons to fetch
            week: Specific week to filter (optional)

        Returns:
            DataFrame with snap count data
        """
        try:
            logger.info(f"Fetching snap counts for seasons: {seasons}")
            valid_seasons = self._valid_seasons(seasons)

            df = self._require_data(
                self._get_adapter().fetch_snap_counts(valid_seasons),
                "fetch_snap_counts",
            )
            logger.info(f"Fetched {len(df)} snap count rows")

            df = self._filter_week(df, week)
            return self._add_metadata(df)

        except Exception as e:
            logger.error(f"Error fetching snap counts: {str(e)}")
            raise

    def fetch_injuries(
        self, seasons: List[int], week: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch weekly injury reports.

        Args:
            seasons: List of seasons to fetch
            week: Specific week to filter (optional)

        Returns:
            DataFrame with injury report data
        """
        try:
            logger.info(f"Fetching injuries for seasons: {seasons}")
            valid_seasons = self._valid_seasons(seasons)

            df = self._require_data(
                self._get_adapter().fetch_injuries(valid_seasons),
                "fetch_injuries",
            )
            logger.info(f"Fetched {len(df)} injury rows")

            df = self._filter_week(df, week)
            return self._add_metadata(df)

        except Exception as e:
            logger.error(f"Error fetching injuries: {str(e)}")
            raise

    def fetch_rosters(self, seasons: List[int]) -> pd.DataFrame:
        """
        Fetch roster data including depth chart positions.

        Args:
            seasons: List of seasons to fetch

        Returns:
            DataFrame with roster data
        """
        try:
            logger.info(f"Fetching rosters for seasons: {seasons}")
            valid_seasons = self._valid_seasons(seasons)

            df = self._require_data(
                self._get_adapter().fetch_rosters(valid_seasons),
                "fetch_rosters",
            )
            logger.info(f"Fetched {len(df)} roster rows")

            return self._add_metadata(df)

        except Exception as e:
            logger.error(f"Error fetching rosters: {str(e)}")
            raise

    def fetch_player_seasonal(self, seasons: List[int]) -> pd.DataFrame:
        """
        Fetch full-season player aggregates.

        Delegates to ``NFLDataAdapter.fetch_seasonal_data``, which also covers
        2025+ seasons by aggregating nflverse ``stats_player`` weekly data.

        Args:
            seasons: List of seasons to fetch

        Returns:
            DataFrame with seasonal player stats
        """
        try:
            logger.info(f"Fetching player seasonal data for seasons: {seasons}")
            valid_seasons = self._valid_seasons(seasons)

            df = self._require_data(
                self._get_adapter().fetch_seasonal_data(valid_seasons),
                "fetch_player_seasonal",
            )
            logger.info(f"Fetched {len(df)} seasonal player rows")

            return self._add_metadata(df)

        except Exception as e:
            logger.error(f"Error fetching player seasonal data: {str(e)}")
            raise

    def validate_data(self, df: pd.DataFrame, data_type: str) -> Dict[str, any]:
        """
        Validate fetched data

        Args:
            df: DataFrame to validate
            data_type: Type of data ('schedules', 'pbp', 'teams')

        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'is_valid': True,
            'row_count': len(df),
            'column_count': len(df.columns),
            'null_percentage': {},
            'issues': []
        }

        try:
            # Check if DataFrame is empty
            if len(df) == 0:
                validation_results['is_valid'] = False
                validation_results['issues'].append("DataFrame is empty")
                return validation_results

            # Check for required columns based on data type
            required_columns = {
                'schedules': ['game_id', 'season', 'week', 'home_team', 'away_team'],
                'pbp': ['game_id', 'play_id', 'season', 'week'],
                'teams': ['team_abbr', 'team_name'],
                'player_weekly': ['player_id', 'season', 'week'],
                'snap_counts': ['player', 'season', 'week'],
                'injuries': ['season', 'week'],
                'rosters': ['player_id', 'season'],
                'player_seasonal': ['player_id', 'season'],
                'ngs': ['season', 'season_type', 'week', 'player_display_name',
                        'player_position', 'team_abbr', 'player_gsis_id'],
                'pfr_weekly': ['game_id', 'season', 'week', 'team',
                               'pfr_player_name', 'pfr_player_id'],
                'pfr_seasonal': ['player', 'team', 'season', 'pfr_id'],
                'qbr': ['season', 'season_type', 'qbr_total', 'pts_added',
                        'epa_total', 'qb_plays'],
                'depth_charts': ['season', 'club_code', 'week', 'position',
                                 'full_name', 'gsis_id'],
                'draft_picks': ['season', 'round', 'pick', 'team',
                                'pfr_player_name', 'position'],
                'combine': ['season', 'player_name', 'pos', 'school',
                            'ht', 'wt'],
            }

            if data_type in required_columns:
                missing_cols = [col for col in required_columns[data_type] if col not in df.columns]
                if missing_cols:
                    validation_results['is_valid'] = False
                    validation_results['issues'].append(f"Missing required columns: {missing_cols}")

            # Calculate null percentages
            for col in df.columns:
                null_pct = (df[col].isnull().sum() / len(df)) * 100
                validation_results['null_percentage'][col] = round(null_pct, 2)

                # Flag high null percentages
                if null_pct > 50:
                    validation_results['issues'].append(f"High null percentage in {col}: {null_pct:.1f}%")

            # Data type specific validations
            if data_type == 'schedules':
                # Check for duplicate game_ids
                if df['game_id'].duplicated().any():
                    validation_results['issues'].append("Duplicate game_ids found")

                # Check season range
                if 'season' in df.columns:
                    seasons = df['season'].unique()
                    invalid_seasons = [s for s in seasons if s < 1999 or s > get_max_season()]
                    if invalid_seasons:
                        validation_results['issues'].append(f"Invalid seasons: {invalid_seasons}")

            logger.info(f"Validation complete for {data_type}: {validation_results}")
            return validation_results

        except Exception as e:
            logger.error(f"Error during validation: {str(e)}")
            validation_results['is_valid'] = False
            validation_results['issues'].append(f"Validation error: {str(e)}")
            return validation_results


def test_nfl_data_integration():
    """Manual smoke test for the NFL data integration facade (live network)."""

    print("🧪 Testing NFL Data Integration Functions")
    print("=" * 50)

    fetcher = NFLDataFetcher()

    # Test 1: Fetch game schedules
    try:
        print("\n📅 Test 1: Fetching game schedules...")
        schedules = fetcher.fetch_game_schedules([2023], week=1)
        validation = fetcher.validate_data(schedules, 'schedules')

        print(f"✅ Schedules fetched: {len(schedules)} games")
        print(f"   Validation: {'PASSED' if validation['is_valid'] else 'FAILED'}")
        if validation['issues']:
            print(f"   Issues: {validation['issues']}")

    except Exception as e:
        print(f"❌ Schedule test failed: {str(e)}")

    # Test 2: Fetch limited play-by-play data
    try:
        print("\n🎯 Test 2: Fetching play-by-play data...")
        columns = ['game_id', 'home_team', 'away_team', 'week', 'season', 'play_id', 'play_type']
        pbp = fetcher.fetch_play_by_play([2023], columns=columns, week=1)
        validation = fetcher.validate_data(pbp, 'pbp')

        print(f"✅ Play-by-play fetched: {len(pbp)} plays")
        print(f"   Validation: {'PASSED' if validation['is_valid'] else 'FAILED'}")
        if validation['issues']:
            print(f"   Issues: {validation['issues']}")

    except Exception as e:
        print(f"❌ Play-by-play test failed: {str(e)}")

    # Test 3: Fetch team data
    try:
        print("\n🏈 Test 3: Fetching team data...")
        teams = fetcher.fetch_team_stats([2023])
        validation = fetcher.validate_data(teams, 'teams')

        print(f"✅ Team data fetched: {len(teams)} teams")
        print(f"   Validation: {'PASSED' if validation['is_valid'] else 'FAILED'}")
        if validation['issues']:
            print(f"   Issues: {validation['issues']}")

    except Exception as e:
        print(f"❌ Team data test failed: {str(e)}")

    print("\n" + "=" * 50)
    print("✅ NFL Data Integration Test Complete!")


if __name__ == "__main__":
    test_nfl_data_integration()
