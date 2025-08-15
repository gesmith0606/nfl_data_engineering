#!/usr/bin/env python3
"""
Test NFL Data Integration
Test nfl-data-py library functionality for our pipeline
"""

import nfl_data_py as nfl
import pandas as pd
from datetime import datetime
import sys

def test_nfl_data_library():
    """Test nfl-data-py library basic functionality"""
    
    print("🏈 Testing NFL Data Library")
    print("=" * 50)
    
    # Test 1: Check library version and basic import
    try:
        print(f"✅ NFL Data Library imported successfully")
        print(f"   Available functions: {[func for func in dir(nfl) if not func.startswith('_')]}")
    except Exception as e:
        print(f"❌ Import failed: {str(e)}")
        return False
    
    # Test 2: Fetch current season games (2024)
    print(f"\n📅 Testing Game Data Fetch (2024 season):")
    try:
        # Get 2024 season schedule - this is usually available
        games_2024 = nfl.import_schedules([2024])
        print(f"✅ 2024 Schedule fetched: {len(games_2024)} games")
        print(f"   Columns: {list(games_2024.columns[:10])}...")  # Show first 10 columns
        
        # Show sample data
        if len(games_2024) > 0:
            print(f"   Sample game: {games_2024.iloc[0]['home_team']} vs {games_2024.iloc[0]['away_team']} (Week {games_2024.iloc[0]['week']})")
            
    except Exception as e:
        print(f"❌ Game data fetch failed: {str(e)}")
        print(f"   This might be expected if 2024 data isn't available yet")
    
    # Test 3: Try 2023 season (should be available)
    print(f"\n📅 Testing with 2023 season (should be available):")
    try:
        games_2023 = nfl.import_schedules([2023])
        print(f"✅ 2023 Schedule fetched: {len(games_2023)} games")
        
        # Filter for Week 1
        week1_games = games_2023[games_2023['week'] == 1]
        print(f"✅ Week 1 games: {len(week1_games)} games")
        
        if len(week1_games) > 0:
            print(f"   Sample Week 1 game: {week1_games.iloc[0]['home_team']} vs {week1_games.iloc[0]['away_team']}")
            
    except Exception as e:
        print(f"❌ 2023 data fetch failed: {str(e)}")
    
    # Test 4: Try to get play-by-play data (more detailed)
    print(f"\n🎯 Testing Play-by-Play Data:")
    try:
        # Get a small sample of play-by-play data
        pbp_data = nfl.import_pbp_data([2023], columns=['game_id', 'home_team', 'away_team', 'week'])
        print(f"✅ Play-by-play data fetched: {len(pbp_data)} plays")
        
        if len(pbp_data) > 0:
            unique_games = pbp_data['game_id'].nunique()
            print(f"   Covers {unique_games} games from 2023 season")
            
    except Exception as e:
        print(f"❌ Play-by-play data failed: {str(e)}")
    
    # Test 5: Test different data types available
    print(f"\n📊 Testing Available Data Types:")
    
    data_types = [
        ('Team Stats', lambda: nfl.import_team_desc()),
        ('Weekly Stats', lambda: nfl.import_weekly_data([2023], columns=['player_name', 'team', 'week', 'fantasy_points'])),
    ]
    
    for data_name, data_func in data_types:
        try:
            data = data_func()
            print(f"✅ {data_name}: {len(data)} records")
        except Exception as e:
            print(f"❌ {data_name} failed: {str(e)}")
    
    print("\n" + "=" * 50)
    print("✅ NFL Data Library Test Complete!")
    return True

if __name__ == "__main__":
    success = test_nfl_data_library()
    sys.exit(0 if success else 1)
