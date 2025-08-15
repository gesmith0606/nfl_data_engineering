#!/usr/bin/env python3
"""
NFL Data Integration Functions
Core functions for fetching and processing NFL data from nfl-data-py
"""

import nfl_data_py as nfl
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NFLDataFetcher:
    """Class for fetching NFL data with error handling and validation"""
    
    def __init__(self):
        self.available_seasons = list(range(1999, 2025))  # nfl-data-py coverage
        
    def fetch_game_schedules(self, seasons: List[int], week: Optional[int] = None) -> pd.DataFrame:
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
            
            # Validate seasons
            invalid_seasons = [s for s in seasons if s not in self.available_seasons]
            if invalid_seasons:
                logger.warning(f"Invalid seasons requested: {invalid_seasons}")
            
            valid_seasons = [s for s in seasons if s in self.available_seasons]
            if not valid_seasons:
                raise ValueError("No valid seasons provided")
            
            # Fetch schedule data
            schedule_df = nfl.import_schedules(valid_seasons)
            logger.info(f"Fetched {len(schedule_df)} total games")
            
            # Filter by week if specified
            if week is not None:
                schedule_df = schedule_df[schedule_df['week'] == week].copy()
                logger.info(f"Filtered to {len(schedule_df)} games for week {week}")
            
            # Add metadata
            schedule_df['data_source'] = 'nfl-data-py'
            schedule_df['ingestion_timestamp'] = datetime.now()
            schedule_df['seasons_requested'] = str(seasons)
            schedule_df['week_filter'] = week
            
            return schedule_df
            
        except Exception as e:
            logger.error(f"Error fetching game schedules: {str(e)}")
            raise
    
    def fetch_play_by_play(self, seasons: List[int], columns: Optional[List[str]] = None, 
                          week: Optional[int] = None) -> pd.DataFrame:
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
            
            # Validate seasons
            valid_seasons = [s for s in seasons if s in self.available_seasons]
            if not valid_seasons:
                raise ValueError("No valid seasons provided")
            
            # Fetch play-by-play data
            pbp_df = nfl.import_pbp_data(valid_seasons, columns=columns)
            logger.info(f"Fetched {len(pbp_df)} plays")
            
            # Filter by week if specified
            if week is not None and 'week' in pbp_df.columns:
                pbp_df = pbp_df[pbp_df['week'] == week].copy()
                logger.info(f"Filtered to {len(pbp_df)} plays for week {week}")
            
            # Add metadata
            pbp_df['data_source'] = 'nfl-data-py'
            pbp_df['ingestion_timestamp'] = datetime.now()
            
            return pbp_df
            
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
            
            # Get team descriptions (static data)
            team_df = nfl.import_team_desc()
            
            # Try to get seasonal team data (without stat_type parameter)
            try:
                seasonal_data = nfl.import_seasonal_data(seasons)
                logger.info(f"Fetched seasonal data: {len(seasonal_data)} records")
                
                # Merge team descriptions with seasonal data if possible
                if 'team' in seasonal_data.columns and 'team_abbr' in team_df.columns:
                    team_df = team_df.merge(
                        seasonal_data.groupby('team').first().reset_index(),
                        left_on='team_abbr',
                        right_on='team',
                        how='left'
                    )
            except Exception as e:
                logger.warning(f"Could not fetch seasonal data: {str(e)}. Using team descriptions only.")
            
            # Add metadata
            team_df['data_source'] = 'nfl-data-py'
            team_df['ingestion_timestamp'] = datetime.now()
            
            return team_df
            
        except Exception as e:
            logger.error(f"Error fetching team stats: {str(e)}")
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
                'teams': ['team_abbr', 'team_name']
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
                    invalid_seasons = [s for s in seasons if s < 1999 or s > 2025]
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
    """Test the NFL data integration functions"""
    
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
