#!/usr/bin/env python3
"""
Bronze Layer Data Explorer
Quick tool to explore and sample Bronze layer data
"""

import boto3
import pandas as pd
from dotenv import load_dotenv
import os
import tempfile
from datetime import datetime

def explore_bronze_data():
    """Explore Bronze layer data with samples and statistics"""
    
    print("🔍 Bronze Layer Data Explorer")
    print("=" * 50)
    
    # Load environment variables
    load_dotenv()
    
    # AWS setup
    s3_client = boto3.client('s3')
    bronze_bucket = os.getenv('S3_BUCKET_BRONZE')
    
    try:
        # List all Bronze layer files
        response = s3_client.list_objects_v2(Bucket=bronze_bucket)
        
        if 'Contents' not in response:
            print("❌ No data found in Bronze layer")
            return
        
        print(f"📦 Found {len(response['Contents'])} files in Bronze layer\n")
        
        # Process each file
        for obj in response['Contents']:
            key = obj['Key']
            size_mb = obj['Size'] / (1024 * 1024)
            modified = obj['LastModified'].strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"📄 File: {key}")
            print(f"   Size: {size_mb:.3f} MB | Modified: {modified}")
            
            # Download and analyze file
            try:
                with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp_file:
                    s3_client.download_file(bronze_bucket, key, tmp_file.name)
                    
                    # Read parquet file
                    df = pd.read_parquet(tmp_file.name)
                    
                    print(f"   📊 Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
                    
                    # Show column info
                    print(f"   📋 Key Columns:")
                    if 'game_id' in df.columns:
                        unique_games = df['game_id'].nunique()
                        print(f"      - Unique Games: {unique_games}")
                    if 'season' in df.columns:
                        seasons = sorted(df['season'].unique())
                        print(f"      - Seasons: {seasons}")
                    if 'week' in df.columns:
                        weeks = sorted(df['week'].unique())
                        print(f"      - Weeks: {weeks}")
                    if 'home_team' in df.columns and 'away_team' in df.columns:
                        teams = sorted(set(df['home_team'].unique()) | set(df['away_team'].unique()))
                        print(f"      - Teams: {len(teams)} ({', '.join(teams[:5])}...)")
                    if 'play_type' in df.columns:
                        play_types = df['play_type'].value_counts().head(3)
                        print(f"      - Top Play Types: {dict(play_types)}")
                    
                    # Show sample data
                    print(f"   🔍 Sample Data (first 2 rows):")
                    sample_cols = ['game_id', 'season', 'week']
                    if 'home_team' in df.columns:
                        sample_cols.extend(['home_team', 'away_team'])
                    if 'home_score' in df.columns:
                        sample_cols.extend(['home_score', 'away_score'])
                    if 'play_type' in df.columns:
                        sample_cols.extend(['play_type', 'yards_gained'])
                    
                    available_cols = [col for col in sample_cols if col in df.columns]
                    print(df[available_cols].head(2).to_string(index=False))
                    
                    # Clean up temp file
                    os.unlink(tmp_file.name)
                    
            except Exception as e:
                print(f"   ❌ Error reading file: {str(e)}")
            
            print()  # Empty line between files
            
        print("=" * 50)
        print("✅ Bronze Layer Exploration Complete!")
        print("💡 Tip: Use scripts/list_bronze_contents.py for quick inventory")
        
    except Exception as e:
        print(f"❌ Exploration failed: {str(e)}")

if __name__ == "__main__":
    explore_bronze_data()
