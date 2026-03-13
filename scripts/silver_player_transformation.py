#!/usr/bin/env python3
"""
Silver Layer - Player Transformation Script

Reads raw player data from local Bronze parquet files (or nfl-data-py),
applies analytics transformations, and writes to the local Silver layer.
Optionally uploads to S3 if AWS credentials are available.

Usage:
    python scripts/silver_player_transformation.py --season 2024
    python scripts/silver_player_transformation.py --seasons 2020 2021 2022 2023 2024
    python scripts/silver_player_transformation.py --season 2024 --week 10
"""

import sys
import os
import argparse
import glob as globmod
from datetime import datetime
from typing import Optional

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

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')
BRONZE_DIR = os.path.join(PROJECT_ROOT, 'data', 'bronze')
SILVER_DIR = os.path.join(PROJECT_ROOT, 'data', 'silver')


def _prepare_weekly_data(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize weekly data column names for analytics functions."""
    df = df.copy()
    # Create 'air_yards' if missing (analytics expects it)
    if 'air_yards' not in df.columns:
        if 'receiving_air_yards' in df.columns:
            df['air_yards'] = df['receiving_air_yards'].fillna(0)
        else:
            df['air_yards'] = 0
    return df


def _prepare_snap_data(snap_df: pd.DataFrame, weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Map snap count columns to match what compute_usage_metrics expects."""
    if snap_df.empty:
        return snap_df
    snap = snap_df.copy()
    # Map offense_pct -> snap_pct
    if 'snap_pct' not in snap.columns and 'offense_pct' in snap.columns:
        snap['snap_pct'] = snap['offense_pct']
    # Map player name to player_id via weekly data lookup
    if 'player_id' not in snap.columns and 'player' in snap.columns:
        # Build name -> id map from weekly data
        id_map = weekly_df.drop_duplicates('player_id')[['player_id', 'player_name']].copy()
        # snap counts use 'player' (display name) and 'team'
        snap = snap.merge(
            id_map, left_on='player', right_on='player_name', how='left',
        )
    return snap


# ---------------------------------------------------------------------------
# Local file helpers
# ---------------------------------------------------------------------------

def _read_local_bronze(data_type: str, season: int) -> pd.DataFrame:
    """Read the latest parquet file from local Bronze directory.

    For snap_counts, reads from players/snaps/ (week-partitioned) and
    concatenates all week files for the season.  For other data types,
    reads the latest file from players/{data_type}/season={season}/.
    """
    if data_type == 'snap_counts':
        # Snap counts are stored week-partitioned under players/snaps/
        pattern = os.path.join(
            BRONZE_DIR, 'players', 'snaps', f'season={season}', 'week=*', '*.parquet',
        )
        files = sorted(globmod.glob(pattern))
        if not files:
            return pd.DataFrame()
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    pattern = os.path.join(BRONZE_DIR, 'players', data_type, f'season={season}', '*.parquet')
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    # Take the latest file (sorted alphabetically = latest timestamp)
    return pd.read_parquet(files[-1])


def _read_local_schedules(season: int) -> pd.DataFrame:
    """Read schedule data from local Bronze directory."""
    pattern = os.path.join(BRONZE_DIR, 'schedules', f'season={season}', '*.parquet')
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _save_local_silver(df: pd.DataFrame, key: str, ts: str) -> str:
    """Save a DataFrame to the local Silver directory."""
    path = os.path.join(SILVER_DIR, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"    Saved -> data/silver/{key}")
    return path


def _try_s3_upload(df: pd.DataFrame, bucket: str, key: str) -> bool:
    """Attempt to upload to S3. Returns True on success, False on failure."""
    try:
        import boto3
        s3 = boto3.client('s3', region_name='us-east-2')
        # Quick credential check
        s3.head_bucket(Bucket=bucket)
        tmp = f"/tmp/{key.replace('/', '_')}.parquet"
        df.to_parquet(tmp, index=False)
        s3.upload_file(tmp, bucket, key)
        os.remove(tmp)
        print(f"    Uploaded -> s3://{bucket}/{key}")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main transform logic
# ---------------------------------------------------------------------------

def run_silver_transform(seasons: list, week: Optional[int], s3_bucket: Optional[str] = None):
    """Read Bronze data, transform, and write to Silver layer."""
    fetcher = NFLDataFetcher()
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    for season in seasons:
        print(f"\n{'='*60}")
        print(f"Processing Season {season}" + (f" Week {week}" if week else " (full season)"))
        print('=' * 60)

        # -------------------------------------------------------------------
        # 1. Load player weekly data (local Bronze -> nfl-data-py fallback)
        # -------------------------------------------------------------------
        print("  Loading player weekly data...")
        weekly_df = _read_local_bronze('weekly', season)
        if weekly_df.empty:
            print("    Not found locally, fetching from nfl-data-py...")
            try:
                weekly_df = fetcher.fetch_player_weekly([season], week=week)
            except Exception as e:
                print(f"    ERROR: {e}")
                continue

        if weekly_df.empty:
            print("    No player weekly data found, skipping.")
            continue
        weekly_df = _prepare_weekly_data(weekly_df)
        print(f"    Loaded {len(weekly_df):,} rows")

        # -------------------------------------------------------------------
        # 2. Load schedule data
        # -------------------------------------------------------------------
        print("  Loading schedule data...")
        schedules_df = _read_local_schedules(season)
        if schedules_df.empty:
            try:
                schedules_df = fetcher.fetch_game_schedules([season])
            except Exception as e:
                print(f"    WARN: Could not fetch schedules: {e}")
                schedules_df = pd.DataFrame()
        if not schedules_df.empty:
            print(f"    Loaded {len(schedules_df):,} games")

        # -------------------------------------------------------------------
        # 3. Load snap counts
        # -------------------------------------------------------------------
        print("  Loading snap counts...")
        snap_df = _read_local_bronze('snap_counts', season)
        if snap_df.empty:
            try:
                snap_df = fetcher.fetch_snap_counts([season], week=week)
            except Exception:
                snap_df = None
        if snap_df is not None and not snap_df.empty:
            snap_df = _prepare_snap_data(snap_df, weekly_df)
            print(f"    Loaded {len(snap_df):,} snap count rows")
        else:
            snap_df = None

        # -------------------------------------------------------------------
        # 4. Compute transformations
        # -------------------------------------------------------------------
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

        # -------------------------------------------------------------------
        # 5. Save to Silver layer (local + optional S3)
        # -------------------------------------------------------------------
        print("  Saving to Silver layer...")

        # Main player usage/rolling table
        if week:
            usage_key = f"players/usage/season={season}/week={week}/usage_{ts}.parquet"
        else:
            usage_key = f"players/usage/season={season}/usage_{ts}.parquet"
        _save_local_silver(transformed, usage_key, ts)
        if s3_bucket:
            _try_s3_upload(transformed, s3_bucket, usage_key)

        # Opponent rankings
        if not opp_rankings.empty:
            if week:
                opp_key = f"defense/positional/season={season}/week={week}/opp_rankings_{ts}.parquet"
            else:
                opp_key = f"defense/positional/season={season}/opp_rankings_{ts}.parquet"
            _save_local_silver(opp_rankings, opp_key, ts)
            if s3_bucket:
                _try_s3_upload(opp_rankings, s3_bucket, opp_key)

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
    parser.add_argument('--no-s3', action='store_true', help='Skip S3 upload even if credentials are available')
    args = parser.parse_args()

    seasons = args.seasons or ([args.season] if args.season else [2024])

    # Try S3 only if credentials are available and --no-s3 not set
    s3_bucket = None
    if not args.no_s3:
        try:
            import config as cfg
            access_key = os.getenv('AWS_ACCESS_KEY_ID')
            secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            if access_key and secret_key:
                s3_bucket = os.getenv('S3_BUCKET_SILVER', cfg.S3_BUCKET_SILVER)
        except Exception:
            pass

    print("NFL Silver Layer - Player Transformation")
    print(f"Seasons: {seasons}" + (f", Week: {args.week}" if args.week else ""))
    print(f"Storage: local" + (f" + S3 ({s3_bucket})" if s3_bucket else ""))

    run_silver_transform(seasons, args.week, s3_bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
