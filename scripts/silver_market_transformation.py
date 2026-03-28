#!/usr/bin/env python3
"""
Silver Layer - Market Data Transformation Script

Reads Bronze odds Parquet files, computes line movement features (spread shift,
total shift, magnitude buckets, key number crossings, steam move placeholder),
reshapes to per-team-per-week rows, and writes to the local Silver layer.
Optionally uploads to S3 if a bucket is provided.

Usage:
    python scripts/silver_market_transformation.py --seasons 2020
    python scripts/silver_market_transformation.py --seasons 2016 2017 2018 2019 2020 2021
"""

import sys
import os
import argparse
import glob as globmod
from datetime import datetime
from typing import Optional

import pandas as pd

# Project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import SILVER_TEAM_S3_KEYS
from market_analytics import compute_movement_features, reshape_to_per_team

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")


# ---------------------------------------------------------------------------
# Local file helpers
# ---------------------------------------------------------------------------


def _read_local_odds(season: int) -> pd.DataFrame:
    """Read the latest odds Parquet file from local Bronze directory.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with Bronze odds data, or empty DataFrame if not found.
    """
    pattern = os.path.join(BRONZE_DIR, "odds", f"season={season}", "*.parquet")
    files = sorted(globmod.glob(pattern))
    if not files:
        print(f"  No Bronze odds files found for season {season}, skipping.")
        return pd.DataFrame()
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


def _try_s3_upload(df: pd.DataFrame, bucket: str, key: str) -> None:
    """Attempt S3 upload; skip gracefully on failure.

    Args:
        df: DataFrame to upload.
        bucket: S3 bucket name.
        key: S3 object key.
    """
    try:
        import boto3
        s3 = boto3.client("s3")
        import io
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
        print(f"    Uploaded -> s3://{bucket}/{key}")
    except Exception as e:
        print(f"    S3 upload skipped: {e}")


# ---------------------------------------------------------------------------
# Main transform
# ---------------------------------------------------------------------------


def run_market_transform(seasons: list, s3_bucket: str = None) -> None:
    """Run market data transformation for the given seasons.

    Reads Bronze odds, computes movement features, reshapes to per-team rows,
    and saves to the Silver layer.

    Args:
        seasons: List of NFL season years to process.
        s3_bucket: Optional S3 bucket for upload.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n=== Silver Market Data Transformation ===")
    print(f"Seasons: {seasons}")
    print(f"Timestamp: {ts}\n")

    for season in seasons:
        print(f"Processing season {season}...")

        # Read Bronze odds
        odds_df = _read_local_odds(season)
        if odds_df.empty:
            print(f"  No Bronze odds for season {season}, skipping.")
            continue

        # Compute movement features
        with_features = compute_movement_features(odds_df)
        print(f"  Computed movement features: {len(with_features)} games")

        # Reshape to per-team rows
        market_df = reshape_to_per_team(with_features)
        print(f"  Reshaped to per-team: {len(market_df)} rows, {len(market_df.columns)} columns")

        # Save locally
        key = f"teams/market_data/season={season}/market_data_{ts}.parquet"
        _save_local_silver(market_df, key, ts)

        # Optional S3 upload
        if s3_bucket and "market_data" in SILVER_TEAM_S3_KEYS:
            s3_key = SILVER_TEAM_S3_KEYS["market_data"].format(season=season, ts=ts)
            _try_s3_upload(market_df, s3_bucket, s3_key)

    print("\nDone.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transform Bronze odds to Silver market_data with line movement features."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2020],
        help="Season years to process (default: 2020)",
    )
    parser.add_argument(
        "--s3-bucket",
        type=str,
        default=None,
        help="S3 bucket for upload (optional; skip if not provided)",
    )
    args = parser.parse_args()
    run_market_transform(args.seasons, args.s3_bucket)
