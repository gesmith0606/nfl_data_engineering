#!/usr/bin/env python3
"""
Silver Layer - Game Context Transformation Script

Reads schedules data from local Bronze parquet files, computes game context
features (weather, rest/travel, coaching), and writes to the local Silver
layer. Optionally uploads to S3 if AWS credentials are available.

Usage:
    python scripts/silver_game_context_transformation.py --season 2024
    python scripts/silver_game_context_transformation.py --seasons 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025
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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import SILVER_TEAM_S3_KEYS
from game_context import compute_game_context, compute_referee_tendencies, compute_playoff_context, _unpivot_schedules

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")


# ---------------------------------------------------------------------------
# Local file helpers
# ---------------------------------------------------------------------------


def _read_local_pbp_derived(season: int) -> pd.DataFrame:
    """Read the latest pbp_derived parquet file from local Silver directory.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with pbp_derived data, or empty DataFrame if not found.
    """
    pattern = os.path.join(SILVER_DIR, "teams", "pbp_derived", f"season={season}", "*.parquet")
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _read_local_schedules(season: int) -> pd.DataFrame:
    """Read the latest schedules parquet file from local Bronze directory.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with schedules data, or empty DataFrame if not found.
    """
    pattern = os.path.join(BRONZE_DIR, "schedules", f"season={season}", "*.parquet")
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    # Take the latest file (sorted alphabetically = latest timestamp)
    return pd.read_parquet(files[-1])


def _save_local_silver(df: pd.DataFrame, key: str, ts: str) -> str:
    """Save a DataFrame to the local Silver directory.

    Args:
        df: DataFrame to save.
        key: Relative path within the Silver directory.
        ts: Timestamp string (unused but kept for API compatibility).

    Returns:
        Absolute path to the saved file.
    """
    path = os.path.join(SILVER_DIR, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"    Saved -> data/silver/{key}")
    return path


def _try_s3_upload(df: pd.DataFrame, bucket: str, key: str) -> bool:
    """Attempt to upload to S3. Returns True on success, False on failure.

    Args:
        df: DataFrame to upload.
        bucket: S3 bucket name.
        key: S3 object key.

    Returns:
        True if upload succeeded, False otherwise.
    """
    try:
        import boto3

        s3 = boto3.client("s3", region_name="us-east-2")
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


def run_game_context_transform(
    seasons: list, s3_bucket: Optional[str] = None
) -> None:
    """Read Bronze schedules data, compute game context, and write to Silver.

    Processes seasons in ascending order so that prior-season coaching context
    flows correctly across season boundaries.

    For each season:
        1. Read schedules from local Bronze
        2. Call compute_game_context(schedules_df, prior_season_df)
        3. Save game context features as Silver Parquet
        4. Optionally upload to S3

    Args:
        seasons: List of NFL season years to process.
        s3_bucket: S3 bucket name for Silver layer. None to skip S3 upload.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Sort ascending -- critical for coaching tenure across season boundaries
    seasons = sorted(seasons)
    prior_season_df = None

    for season in seasons:
        print(f"\n{'=' * 60}")
        print(f"Processing Season {season}")
        print("=" * 60)

        # 1. Load schedules from local Bronze
        print("  Loading schedules data...")
        schedules_df = _read_local_schedules(season)
        if schedules_df.empty:
            print(f"    WARNING: No schedules data found for season {season}, skipping.")
            prior_season_df = None
            continue
        print(f"    Loaded {len(schedules_df):,} games")

        # 2. Compute game context features
        print("  Computing game context features...")
        context_df = compute_game_context(schedules_df, prior_season_df)
        if context_df.empty:
            print("    WARNING: No game context produced, skipping.")
            prior_season_df = schedules_df
            continue
        print(
            f"    Game context: {len(context_df):,} rows, "
            f"{context_df['team'].nunique()} teams, "
            f"{len(context_df.columns)} columns"
        )

        # 3. Save to Silver layer (local + optional S3)
        print("  Saving to Silver layer...")
        gc_key = SILVER_TEAM_S3_KEYS["game_context"].format(season=season, ts=ts)
        _save_local_silver(context_df, gc_key, ts)
        if s3_bucket:
            _try_s3_upload(context_df, s3_bucket, gc_key)

        # 4. Compute referee tendencies (requires pbp_derived Silver)
        print("  Computing referee tendencies...")
        unpivoted = _unpivot_schedules(schedules_df)
        pbp_derived_df = _read_local_pbp_derived(season)
        if pbp_derived_df.empty:
            print(f"    WARNING: No pbp_derived data for season {season}, skipping referee tendencies.")
        else:
            referee_df = compute_referee_tendencies(unpivoted, pbp_derived_df)
            ref_key = SILVER_TEAM_S3_KEYS["referee_tendencies"].format(season=season, ts=ts)
            _save_local_silver(referee_df, ref_key, ts)
            if s3_bucket:
                _try_s3_upload(referee_df, s3_bucket, ref_key)
            print(
                f"    Referee tendencies: {len(referee_df):,} rows, "
                f"{referee_df['team'].nunique()} teams"
            )

        # 5. Compute playoff context (standings, division rank, contention)
        print("  Computing playoff context...")
        playoff_df = compute_playoff_context(unpivoted)
        play_key = SILVER_TEAM_S3_KEYS["playoff_context"].format(season=season, ts=ts)
        _save_local_silver(playoff_df, play_key, ts)
        if s3_bucket:
            _try_s3_upload(playoff_df, s3_bucket, play_key)
        print(
            f"    Playoff context: {len(playoff_df):,} rows, "
            f"{playoff_df['team'].nunique()} teams"
        )

        print(f"  Season {season} complete.")

        # 6. Track prior season for coaching context in next iteration
        prior_season_df = schedules_df

    print("\nSilver game context transformation complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse CLI arguments and run Silver game context transformation."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="NFL Silver Layer - Game Context Transformation"
    )
    parser.add_argument("--season", type=int, help="Single NFL season to transform")
    parser.add_argument(
        "--seasons", type=int, nargs="+", help="Multiple seasons to transform"
    )
    parser.add_argument(
        "--no-s3",
        action="store_true",
        help="Skip S3 upload even if credentials are available",
    )
    args = parser.parse_args()

    seasons = args.seasons or ([args.season] if args.season else [2024])

    # Try S3 only if credentials are available and --no-s3 not set
    s3_bucket = None
    if not args.no_s3:
        try:
            import config as cfg

            access_key = os.getenv("AWS_ACCESS_KEY_ID")
            secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            if access_key and secret_key:
                s3_bucket = os.getenv("S3_BUCKET_SILVER", cfg.S3_BUCKET_SILVER)
        except Exception:
            pass

    print("NFL Silver Layer - Game Context Transformation")
    print(f"Seasons: {seasons}")
    print(f"Storage: local" + (f" + S3 ({s3_bucket})" if s3_bucket else ""))

    run_game_context_transform(seasons, s3_bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
