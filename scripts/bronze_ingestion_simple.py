#!/usr/bin/env python3
"""
Simple Bronze Layer Ingestion
Standalone script to ingest NFL data into S3 Bronze layer
"""

import sys
import os
import pandas as pd
import boto3
from datetime import datetime
import argparse
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from nfl_data_integration import NFLDataFetcher

def upload_to_s3(df: pd.DataFrame, bucket: str, key: str, aws_credentials: dict) -> str:
    """
    Upload DataFrame to S3 as Parquet
    
    Args:
        df: DataFrame to upload
        bucket: S3 bucket name
        key: S3 key (path)
        aws_credentials: AWS credentials dict
        
    Returns:
        S3 URI of uploaded file
    """
    try:
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            region_name=aws_credentials['region']
        )
        
        # Save DataFrame to temporary parquet file
        temp_file = f"/tmp/{key.replace('/', '_')}.parquet"
        df.to_parquet(temp_file, index=False)
        
        # Upload to S3
        s3_client.upload_file(temp_file, bucket, key)
        
        # Clean up temp file
        os.remove(temp_file)
        
        s3_uri = f"s3://{bucket}/{key}"
        print(f"✅ Uploaded to: {s3_uri}")
        return s3_uri
        
    except Exception as e:
        print(f"❌ Upload failed: {str(e)}")
        raise

def main():
    """Main ingestion function"""
    
    parser = argparse.ArgumentParser(description='NFL Data Bronze Layer Ingestion')
    parser.add_argument('--season', type=int, default=2023, help='NFL Season (default: 2023)')
    parser.add_argument('--week', type=int, default=1, help='NFL Week (default: 1)')
    parser.add_argument('--data-type', choices=['schedules', 'pbp', 'teams'], 
                       default='schedules', help='Data type to ingest')
    
    args = parser.parse_args()
    
    print(f"🏈 NFL Bronze Layer Ingestion")
    print(f"Season: {args.season}, Week: {args.week}, Data Type: {args.data_type}")
    print("=" * 60)
    
    # Load environment variables
    load_dotenv()
    
    # Get AWS credentials
    aws_credentials = {
        'access_key': os.getenv('AWS_ACCESS_KEY_ID'),
        'secret_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
        'region': os.getenv('AWS_REGION')
    }
    
    bronze_bucket = os.getenv('S3_BUCKET_BRONZE')
    
    if not all(aws_credentials.values()) or not bronze_bucket:
        print("❌ Missing AWS credentials or bucket configuration in .env file")
        return 1
    
    # Initialize data fetcher
    fetcher = NFLDataFetcher()
    
    try:
        # Fetch data based on type
        if args.data_type == 'schedules':
            print(f"📅 Fetching game schedules for {args.season}, week {args.week}...")
            df = fetcher.fetch_game_schedules([args.season], week=args.week)
            s3_key = f"games/season={args.season}/week={args.week}/schedules_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
            
        elif args.data_type == 'pbp':
            print(f"🎯 Fetching play-by-play data for {args.season}, week {args.week}...")
            columns = ['game_id', 'home_team', 'away_team', 'week', 'season', 'play_id', 
                      'play_type', 'yards_gained', 'down', 'ydstogo']
            df = fetcher.fetch_play_by_play([args.season], columns=columns, week=args.week)
            s3_key = f"plays/season={args.season}/week={args.week}/pbp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
            
        elif args.data_type == 'teams':
            print(f"🏈 Fetching team data for {args.season}...")
            df = fetcher.fetch_team_stats([args.season])
            s3_key = f"teams/season={args.season}/teams_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        
        # Validate data
        validation = fetcher.validate_data(df, args.data_type)
        print(f"\\n📊 Data Summary:")
        print(f"   Records: {validation['row_count']:,}")
        print(f"   Columns: {validation['column_count']}")
        print(f"   Validation: {'✅ PASSED' if validation['is_valid'] else '❌ FAILED'}")
        
        if validation['issues']:
            print(f"   Issues: {len(validation['issues'])}")
            for issue in validation['issues'][:3]:  # Show first 3 issues
                print(f"     - {issue}")
        
        # Upload to S3
        print(f"\\n📤 Uploading to Bronze layer...")
        s3_uri = upload_to_s3(df, bronze_bucket, s3_key, aws_credentials)
        
        print(f"\\n🎉 Ingestion Complete!")
        print(f"📍 Data Location: {s3_uri}")
        print(f"📊 Records Ingested: {len(df):,}")
        
        return 0
        
    except Exception as e:
        print(f"\\n❌ Ingestion failed: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
