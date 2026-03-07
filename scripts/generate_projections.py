#!/usr/bin/env python3
"""
Generate NFL Fantasy Football Projections

Pulls Silver-layer player data from S3, runs the projection engine,
and writes results to the Gold layer.

Usage:
    python scripts/generate_projections.py --week 1 --season 2026 --scoring ppr
    python scripts/generate_projections.py --week 10 --season 2025 --scoring half_ppr
    python scripts/generate_projections.py --preseason --season 2026 --scoring standard
"""

import sys
import os
import argparse
from datetime import datetime

import boto3
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nfl_data_integration import NFLDataFetcher
from projection_engine import generate_weekly_projections, generate_preseason_projections
from scoring_calculator import list_scoring_formats
from utils import download_latest_parquet
import config


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def _s3_client(creds):
    return boto3.client(
        's3',
        aws_access_key_id=creds['access_key'],
        aws_secret_access_key=creds['secret_key'],
        region_name=creds['region'],
    )



def upload_df(df, bucket, key, creds) -> str:
    tmp = f"/tmp/{key.replace('/', '_')}.parquet"
    df.to_parquet(tmp, index=False)
    _s3_client(creds).upload_file(tmp, bucket, key)
    os.remove(tmp)
    uri = f"s3://{bucket}/{key}"
    print(f"  Uploaded -> {uri}")
    return uri


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    formats = list_scoring_formats()
    parser = argparse.ArgumentParser(description='NFL Fantasy Football Projection Generator')
    parser.add_argument('--season', type=int, default=2026, help='Target season')
    parser.add_argument('--week', type=int, help='Target week (weekly projection mode)')
    parser.add_argument('--preseason', action='store_true', help='Run pre-season projection mode')
    parser.add_argument('--scoring', choices=formats, default='half_ppr', help='Scoring format')
    parser.add_argument('--output', choices=['s3', 'csv', 'both'], default='both',
                        help='Output destination')
    parser.add_argument('--output-dir', default='output/projections',
                        help='Local CSV output directory (default: output/projections)')
    args = parser.parse_args()

    if not args.preseason and not args.week:
        parser.error("Specify --week N for weekly projections or --preseason for draft projections")

    creds = {
        'access_key': os.getenv('AWS_ACCESS_KEY_ID'),
        'secret_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
        'region': os.getenv('AWS_REGION', 'us-east-2'),
    }
    silver_bucket = os.getenv('S3_BUCKET_SILVER', config.S3_BUCKET_SILVER)
    gold_bucket = os.getenv('S3_BUCKET_GOLD', config.S3_BUCKET_GOLD)
    has_aws = all(creds.values())

    fetcher = NFLDataFetcher()
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    print(f"\nNFL Fantasy Football Projection Generator")
    print(f"Season: {args.season} | Scoring: {args.scoring.upper()}")
    if args.preseason:
        print("Mode: Pre-Season Draft Projections")
    else:
        print(f"Mode: Weekly Projections (Week {args.week})")
    print('=' * 60)

    # -----------------------------------------------------------------------
    # Pre-season mode: use seasonal aggregates
    # -----------------------------------------------------------------------
    if args.preseason:
        print("\nFetching historical seasonal data...")
        # Use past 2 seasons as training data
        past_seasons = [args.season - 2, args.season - 1]
        try:
            seasonal_df = fetcher.fetch_player_seasonal(past_seasons)
        except Exception as e:
            print(f"ERROR fetching seasonal data: {e}")
            return 1

        print(f"Loaded {len(seasonal_df):,} seasonal player rows")
        print("Running pre-season projection model...")
        projections = generate_preseason_projections(
            seasonal_df,
            scoring_format=args.scoring,
            target_season=args.season,
        )
        s3_key = f"projections/preseason/season={args.season}/season_proj_{ts}.parquet"
        local_name = f"preseason_{args.season}_{args.scoring}_{ts}.csv"

    # -----------------------------------------------------------------------
    # Weekly mode: use Silver-layer rolling stats
    # -----------------------------------------------------------------------
    else:
        print(f"\nFetching Silver-layer data for season {args.season}...")
        # Try S3 first; fall back to fetching from nfl-data-py directly
        silver_df = pd.DataFrame()
        if has_aws:
            try:
                s3 = _s3_client(creds)
                prefix = f"players/usage/season={args.season}/week={args.week}/"
                silver_df = download_latest_parquet(s3, silver_bucket, prefix)
                print(f"Loaded {len(silver_df):,} rows from Silver S3 layer")
            except Exception as e:
                print(f"WARN: Could not load from Silver S3: {e}")

        if silver_df.empty:
            print("Falling back to fetching weekly data directly from nfl-data-py...")
            try:
                silver_df = fetcher.fetch_player_weekly([args.season])
            except Exception as e:
                print(f"ERROR: {e}")
                return 1

        # Load opponent rankings
        opp_rankings = pd.DataFrame()
        if has_aws and not silver_df.empty:
            try:
                opp_prefix = f"defense/positional/season={args.season}/week={args.week}/"
                opp_rankings = download_latest_parquet(s3, silver_bucket, opp_prefix)
                print(f"Loaded {len(opp_rankings):,} opponent ranking rows")
            except Exception as e:
                print(f"WARN: Could not load opponent rankings: {e}")

        print(f"Running weekly projection model (Week {args.week})...")
        projections = generate_weekly_projections(
            silver_df,
            opp_rankings,
            season=args.season,
            week=args.week,
            scoring_format=args.scoring,
        )
        s3_key = (f"projections/season={args.season}/week={args.week}/"
                  f"projections_{args.scoring}_{ts}.parquet")
        local_name = f"week{args.week}_{args.season}_{args.scoring}_{ts}.csv"

    if projections.empty:
        print("ERROR: No projections generated. Check that data is available.")
        return 1

    print(f"\nProjections generated: {len(projections):,} players")

    # -----------------------------------------------------------------------
    # Display top 20
    # -----------------------------------------------------------------------
    display_cols = ['player_name', 'position', 'recent_team', 'projected_points',
                    'position_rank', 'overall_rank'] if 'overall_rank' in projections.columns else \
                   ['player_name', 'position', 'recent_team', 'projected_points', 'position_rank']
    display_cols = [c for c in display_cols if c in projections.columns]

    print(f"\nTop 20 Players ({args.scoring.upper()}):")
    print(projections[display_cols].head(20).to_string(index=False))

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    if args.output in ('csv', 'both'):
        os.makedirs(args.output_dir, exist_ok=True)
        csv_path = os.path.join(args.output_dir, local_name)
        projections.to_csv(csv_path, index=False)
        print(f"\nSaved CSV -> {csv_path}")

    if args.output in ('s3', 'both') and has_aws:
        try:
            upload_df(projections, gold_bucket, s3_key, creds)
        except Exception as e:
            print(f"WARN: S3 upload failed: {e}")

    print("\nProjection run complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
