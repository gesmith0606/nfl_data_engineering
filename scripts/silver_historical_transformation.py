#!/usr/bin/env python3
"""
Silver Layer - Historical Player Profile Transformation Script

Reads Bronze combine and draft_picks data (all available seasons), calls the
historical_profiles compute module, and writes the combined dimension table
to the local Silver layer.

Usage:
    python scripts/silver_historical_transformation.py
    python scripts/silver_historical_transformation.py --no-s3
"""

import sys
import os
import argparse
import glob as globmod
import logging
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

# Project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from historical_profiles import build_combine_draft_profiles
from config import SILVER_PLAYER_S3_KEYS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")


def _read_local_bronze(subdir: str) -> pd.DataFrame:
    """Read ALL Parquet files from a Bronze subdirectory across all seasons.

    Unlike other Silver CLIs that read per-season, this reads everything
    since combine/draft is a static dimension table.

    Args:
        subdir: Relative path within BRONZE_DIR (e.g., 'combine').

    Returns:
        Concatenated DataFrame with all seasons, or empty DataFrame if none found.
    """
    pattern = os.path.join(BRONZE_DIR, subdir, "season=*", "*.parquet")
    files = sorted(globmod.glob(pattern))
    if not files:
        logger.error("No Parquet files found at %s", pattern)
        return pd.DataFrame()

    dfs = []
    for f in files:
        dfs.append(pd.read_parquet(f))

    result = pd.concat(dfs, ignore_index=True)
    logger.info(
        "Read %d files from data/bronze/%s/ -> %d rows",
        len(files),
        subdir,
        len(result),
    )
    return result


def main() -> int:
    """Parse CLI arguments and run Silver historical transformation."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="NFL Silver Layer - Historical Player Profile Transformation"
    )
    parser.add_argument(
        "--no-s3",
        action="store_true",
        help="Skip S3 upload even if credentials are available",
    )
    args = parser.parse_args()

    print("NFL Silver Layer - Historical Player Profile Transformation")
    print("Processing all available Bronze combine and draft_picks data")

    # Step 1: Read Bronze data
    print("\n  Loading Bronze combine data...")
    combine_df = _read_local_bronze("combine")
    if combine_df.empty:
        logger.error("No combine data found. Exiting.")
        return 1

    print("  Loading Bronze draft_picks data...")
    draft_df = _read_local_bronze("draft_picks")
    if draft_df.empty:
        logger.error("No draft_picks data found. Exiting.")
        return 1

    print(f"  Combine: {len(combine_df):,} rows | Draft: {len(draft_df):,} rows")

    # Step 2: Build profiles
    print("\n  Building combine/draft profiles...")
    profiles = build_combine_draft_profiles(combine_df, draft_df)

    # Step 3: Write output
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    key = SILVER_PLAYER_S3_KEYS["historical_profiles"].format(ts=ts)
    out_path = os.path.join(SILVER_DIR, key)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    profiles.to_parquet(out_path, index=False)

    file_size_mb = os.path.getsize(out_path) / (1024 * 1024)

    print(f"\n  Output: {out_path}")
    print(f"  Rows: {len(profiles):,} | Columns: {len(profiles.columns)}")
    print(f"  File size: {file_size_mb:.2f} MB")

    # Step 4: Log NaN rates for key columns
    key_cols = ["forty", "speed_score", "draft_value"]
    for col in key_cols:
        if col in profiles.columns:
            nan_rate = profiles[col].isna().mean() * 100
            logger.info("NaN rate for %s: %.1f%%", col, nan_rate)

    # Step 5: S3 upload (optional)
    if not args.no_s3:
        try:
            access_key = os.getenv("AWS_ACCESS_KEY_ID")
            secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            if access_key and secret_key:
                import boto3

                s3 = boto3.client("s3", region_name="us-east-2")
                bucket = os.getenv("S3_BUCKET_SILVER", "nfl-refined")
                s3.head_bucket(Bucket=bucket)
                s3.upload_file(out_path, bucket, key)
                print(f"  Uploaded -> s3://{bucket}/{key}")
        except Exception:
            logger.info("S3 upload skipped (credentials unavailable or expired)")

    print("\nSilver historical transformation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
