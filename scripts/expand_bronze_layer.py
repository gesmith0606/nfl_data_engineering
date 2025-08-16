#!/usr/bin/env python3
"""
Bronze Layer Expansion Script
Add more NFL data to Bronze layer for better Silver layer development
"""

import sys
import os
sys.path.append('src')

from nfl_data_integration import NFLDataFetcher
import argparse

def expand_bronze_data():
    """Add strategic additional data to Bronze layer"""
    
    print("📈 Bronze Layer Strategic Expansion")
    print("Adding key data for Silver layer development")
    print("=" * 60)
    
    fetcher = NFLDataFetcher()
    
    # Strategic data to add for Silver layer development
    expansions = [
        # More weeks from same season for temporal patterns
        {"season": 2023, "week": 2, "data_type": "schedules", "reason": "Week-over-week comparison"},
        {"season": 2023, "week": 2, "data_type": "pbp", "reason": "Weekly play pattern analysis"},
        
        # Different season for year-over-year patterns  
        {"season": 2022, "week": 1, "data_type": "schedules", "reason": "Year-over-year comparison"},
        {"season": 2022, "week": 1, "data_type": "pbp", "reason": "Historical play analysis"},
        
        # Team data we haven't ingested yet
        {"season": 2023, "week": None, "data_type": "teams", "reason": "Team reference data"},
    ]
    
    for expansion in expansions:
        season = expansion["season"]
        week = expansion["week"]
        data_type = expansion["data_type"]
        reason = expansion["reason"]
        
        print(f"\n📊 Adding {data_type} data: {season} Season" + (f" Week {week}" if week else ""))
        print(f"   Purpose: {reason}")
        
        # Build command
        cmd = f"python scripts/bronze_ingestion_simple.py --season {season} --data-type {data_type}"
        if week:
            cmd += f" --week {week}"
        
        print(f"   Command: {cmd}")
        
        # Execute ingestion
        try:
            exit_code = os.system(cmd)
            if exit_code == 0:
                print(f"   ✅ Successfully ingested {data_type} data")
            else:
                print(f"   ❌ Failed to ingest {data_type} data (exit code: {exit_code})")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
    
    print(f"\n" + "=" * 60)
    print("📈 Bronze Layer Expansion Complete!")
    print("🔍 View results: python scripts/list_bronze_contents.py")

if __name__ == "__main__":
    expand_bronze_data()
