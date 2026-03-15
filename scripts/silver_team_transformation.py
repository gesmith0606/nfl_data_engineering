#!/usr/bin/env python3
"""
Silver Layer - Team Transformation Script

Reads raw play-by-play data from local Bronze parquet files, computes team
PBP performance metrics and tendency metrics, and writes to the local Silver
layer. Optionally uploads to S3 if AWS credentials are available.

Usage:
    python scripts/silver_team_transformation.py --season 2024
    python scripts/silver_team_transformation.py --seasons 2020 2021 2022 2023 2024
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
from team_analytics import (
    compute_pbp_metrics,
    compute_tendency_metrics,
    compute_sos_metrics,
    compute_situational_splits,
)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")


# ---------------------------------------------------------------------------
# Local file helpers
# ---------------------------------------------------------------------------


def _read_local_pbp(season: int) -> pd.DataFrame:
    """Read the latest PBP parquet file from local Bronze directory.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with play-by-play data, or empty DataFrame if not found.
    """
    pattern = os.path.join(BRONZE_DIR, "pbp", f"season={season}", "*.parquet")
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


def run_silver_team_transform(
    seasons: list, s3_bucket: Optional[str] = None
) -> None:
    """Read Bronze PBP data, compute team metrics, and write to Silver layer.

    For each season:
        1. Read PBP from local Bronze
        2. Compute PBP performance metrics (EPA, success rate, CPOE, red zone)
        3. Compute tendency metrics (pace, PROE, 4th down, early-down run rate)
        4. Compute SOS metrics (opponent-adjusted EPA, schedule difficulty)
        5. Compute situational splits (home/away, divisional, game script EPA)
        6. Save all 4 tables as Parquet with timestamped filenames
        7. Optionally upload to S3

    Args:
        seasons: List of NFL season years to process.
        s3_bucket: S3 bucket name for Silver layer. None to skip S3 upload.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for season in seasons:
        print(f"\n{'=' * 60}")
        print(f"Processing Season {season}")
        print("=" * 60)

        # 1. Load PBP from local Bronze
        print("  Loading PBP data...")
        pbp_df = _read_local_pbp(season)
        if pbp_df.empty:
            print(f"    WARNING: No PBP data found for season {season}, skipping.")
            continue
        print(f"    Loaded {len(pbp_df):,} plays")

        # 2. Compute PBP performance metrics
        print("  Computing PBP performance metrics...")
        pbp_metrics_df = compute_pbp_metrics(pbp_df)
        if pbp_metrics_df.empty:
            print("    WARNING: No PBP metrics produced, skipping.")
            continue
        print(
            f"    PBP metrics: {len(pbp_metrics_df):,} rows, "
            f"{pbp_metrics_df['team'].nunique()} teams"
        )

        # 3. Compute tendency metrics
        print("  Computing tendency metrics...")
        tendencies_df = compute_tendency_metrics(pbp_df)
        if tendencies_df.empty:
            print("    WARNING: No tendency metrics produced.")
        else:
            print(
                f"    Tendencies: {len(tendencies_df):,} rows, "
                f"{tendencies_df['team'].nunique()} teams"
            )

        # 4. Compute SOS metrics
        print("  Computing SOS metrics...")
        sos_df = compute_sos_metrics(pbp_df)
        if sos_df.empty:
            print("    WARNING: No SOS metrics produced.")
        else:
            print(
                f"    SOS: {len(sos_df):,} rows, "
                f"{sos_df['team'].nunique()} teams"
            )

        # 5. Compute situational splits
        print("  Computing situational splits...")
        sit_df = compute_situational_splits(pbp_df)
        if sit_df.empty:
            print("    WARNING: No situational splits produced.")
        else:
            print(
                f"    Situational: {len(sit_df):,} rows, "
                f"{sit_df['team'].nunique()} teams"
            )

        # 6. Save to Silver layer (local + optional S3)
        print("  Saving to Silver layer...")

        pbp_key = SILVER_TEAM_S3_KEYS["pbp_metrics"].format(season=season, ts=ts)
        _save_local_silver(pbp_metrics_df, pbp_key, ts)
        if s3_bucket:
            _try_s3_upload(pbp_metrics_df, s3_bucket, pbp_key)

        if not tendencies_df.empty:
            tend_key = SILVER_TEAM_S3_KEYS["tendencies"].format(season=season, ts=ts)
            _save_local_silver(tendencies_df, tend_key, ts)
            if s3_bucket:
                _try_s3_upload(tendencies_df, s3_bucket, tend_key)

        if not sos_df.empty:
            sos_key = SILVER_TEAM_S3_KEYS["sos"].format(season=season, ts=ts)
            _save_local_silver(sos_df, sos_key, ts)
            if s3_bucket:
                _try_s3_upload(sos_df, s3_bucket, sos_key)

        if not sit_df.empty:
            sit_key = SILVER_TEAM_S3_KEYS["situational"].format(season=season, ts=ts)
            _save_local_silver(sit_df, sit_key, ts)
            if s3_bucket:
                _try_s3_upload(sit_df, s3_bucket, sit_key)

        print(f"  Season {season} complete.")

    print("\nSilver team transformation complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse CLI arguments and run Silver team transformation."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="NFL Silver Layer - Team Transformation"
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

    print("NFL Silver Layer - Team Transformation")
    print(f"Seasons: {seasons}")
    print(f"Storage: local" + (f" + S3 ({s3_bucket})" if s3_bucket else ""))

    run_silver_team_transform(seasons, s3_bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
