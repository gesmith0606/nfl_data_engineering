#!/usr/bin/env python3
"""
Silver Layer - Player Transformation Script

Reads raw player data from the Bronze S3 layer, applies analytics
transformations, and writes cleaned analytics-ready data to the Silver layer.

Usage:
    python scripts/silver_player_transformation.py --season 2024
    python scripts/silver_player_transformation.py --season 2024 --week 10
    python scripts/silver_player_transformation.py --seasons 2022 2023 2024
"""

import sys
import os
import argparse
from datetime import datetime
from typing import Optional

import boto3
import pandas as pd
from dotenv import load_dotenv

# Project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nfl_data_integration import NFLDataFetcher
from player_analytics import (
    compute_usage_metrics,
    compute_opponent_rankings,
    compute_rolling_averages,
    compute_game_script_indicators,
    compute_venue_splits,
)
from utils import download_latest_parquet, get_latest_s3_key
import config


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def _s3_client(creds: dict):
    return boto3.client(
        's3',
        aws_access_key_id=creds['access_key'],
        aws_secret_access_key=creds['secret_key'],
        region_name=creds['region'],
    )


def upload_df(df: pd.DataFrame, bucket: str, key: str, creds: dict) -> str:
    """Upload a DataFrame as Parquet to S3 and return the S3 URI."""
    tmp = f"/tmp/{key.replace('/', '_')}.parquet"
    df.to_parquet(tmp, index=False)
    _s3_client(creds).upload_file(tmp, bucket, key)
    os.remove(tmp)
    uri = f"s3://{bucket}/{key}"
    print(f"  Uploaded -> {uri}")
    return uri



# ---------------------------------------------------------------------------
# Main transform logic
# ---------------------------------------------------------------------------

def run_silver_transform(seasons: list, week: Optional[int], creds: dict, silver_bucket: str, bronze_bucket: str):
    """Fetch Bronze data, transform, and write to Silver."""
    fetcher = NFLDataFetcher()
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    for season in seasons:
        print(f"\n{'='*60}")
        print(f"Processing Season {season}" + (f" Week {week}" if week else " (full season)"))
        print('=' * 60)

        # -----------------------------------------------------------------------
        # 1. Fetch raw player weekly data from Bronze (or nfl-data-py directly)
        # -----------------------------------------------------------------------
        print("  Fetching player weekly data...")
        try:
            weekly_df = fetcher.fetch_player_weekly([season], week=week)
        except Exception as e:
            print(f"  ERROR fetching weekly data: {e}")
            continue

        if weekly_df.empty:
            print("  No player weekly data found, skipping.")
            continue

        # -----------------------------------------------------------------------
        # 2. Fetch schedule data for opponent/venue context
        # -----------------------------------------------------------------------
        print("  Fetching schedule data...")
        try:
            schedules_df = fetcher.fetch_game_schedules([season], week=week)
        except Exception as e:
            print(f"  WARN: Could not fetch schedules: {e}")
            schedules_df = pd.DataFrame()

        # -----------------------------------------------------------------------
        # 3. Fetch snap counts for snap_pct
        # -----------------------------------------------------------------------
        print("  Fetching snap counts...")
        try:
            snap_df = fetcher.fetch_snap_counts([season], week=week)
        except Exception as e:
            print(f"  WARN: Could not fetch snap counts: {e}")
            snap_df = None

        # -----------------------------------------------------------------------
        # 4. Compute transformations
        # -----------------------------------------------------------------------
        print("  Computing usage metrics...")
        transformed = compute_usage_metrics(weekly_df, snap_df)

        print("  Computing rolling averages...")
        transformed = compute_rolling_averages(transformed, windows=[3, 6])

        if not schedules_df.empty:
            print("  Computing game script indicators...")
            transformed = compute_game_script_indicators(transformed, schedules_df)

            print("  Computing venue splits...")
            transformed = compute_venue_splits(transformed, schedules_df)

        print("  Computing opponent defensive rankings...")
        opp_rankings = pd.DataFrame()
        if not schedules_df.empty:
            opp_rankings = compute_opponent_rankings(weekly_df, schedules_df, n_seasons=3)

        # -----------------------------------------------------------------------
        # 5. Upload to Silver layer
        # -----------------------------------------------------------------------
        print("  Uploading to Silver layer...")

        # Usage metrics + rolling averages (main player table)
        if week:
            usage_key = f"players/usage/season={season}/week={week}/usage_{ts}.parquet"
        else:
            usage_key = f"players/usage/season={season}/usage_{ts}.parquet"
        upload_df(transformed, silver_bucket, usage_key, creds)

        # Opponent rankings
        if not opp_rankings.empty:
            if week:
                opp_key = f"defense/positional/season={season}/week={week}/opp_rankings_{ts}.parquet"
            else:
                opp_key = f"defense/positional/season={season}/opp_rankings_{ts}.parquet"
            upload_df(opp_rankings, silver_bucket, opp_key, creds)

        print(f"  Season {season} complete: {len(transformed):,} player-week rows transformed")

    print("\nSilver transformation complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='NFL Silver Layer - Player Transformation')
    parser.add_argument('--season', type=int, help='Single NFL season to transform')
    parser.add_argument('--seasons', type=int, nargs='+', help='Multiple seasons to transform')
    parser.add_argument('--week', type=int, default=None, help='Specific week (optional)')
    args = parser.parse_args()

    seasons = args.seasons or ([args.season] if args.season else [2024])

    creds = {
        'access_key': os.getenv('AWS_ACCESS_KEY_ID'),
        'secret_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
        'region': os.getenv('AWS_REGION', 'us-east-2'),
    }
    silver_bucket = os.getenv('S3_BUCKET_SILVER', config.S3_BUCKET_SILVER)
    bronze_bucket = os.getenv('S3_BUCKET_BRONZE', config.S3_BUCKET_BRONZE)

    if not all(creds.values()):
        print("ERROR: Missing AWS credentials in .env file")
        return 1

    print(f"NFL Silver Layer - Player Transformation")
    print(f"Seasons: {seasons}" + (f", Week: {args.week}" if args.week else ""))

    run_silver_transform(seasons, args.week, creds, silver_bucket, bronze_bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
