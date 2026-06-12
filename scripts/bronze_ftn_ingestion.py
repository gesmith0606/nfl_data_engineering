#!/usr/bin/env python3
"""Bronze FTN Charting Data Ingestion.

Fetches FTN play-charting data via nfl_data_py.import_ftn_data for the
requested seasons and writes raw Parquet to:

    data/bronze/ftn_charting/season=YYYY/ftn_charting_YYYYMMDD_HHMMSS.parquet

FTN data is available from 2022 onwards (CC-BY-SA 4.0 — attribution: FTN Data
via nflverse). Pre-2022 requests are rejected with a clear error message.

Usage:
    python scripts/bronze_ftn_ingestion.py --seasons 2022-2025
    python scripts/bronze_ftn_ingestion.py --season 2024
    python scripts/bronze_ftn_ingestion.py --seasons 2022-2025 --s3  # Also upload to S3
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import List

import pandas as pd

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

logger = logging.getLogger(__name__)

BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
FTN_FIRST_SEASON = 2022


def _parse_seasons(seasons_arg: str, season_arg: int) -> List[int]:
    """Parse --seasons range or --season single into a list of ints.

    Args:
        seasons_arg: Optional range string like "2022-2025".
        season_arg: Optional single season int.

    Returns:
        Sorted list of season years.

    Raises:
        ValueError: If any requested season is before FTN_FIRST_SEASON.
    """
    if seasons_arg:
        if "-" in seasons_arg:
            parts = seasons_arg.split("-")
            start, end = int(parts[0]), int(parts[1])
            if start > end:
                raise ValueError(f"Season range start {start} > end {end}")
            seasons = list(range(start, end + 1))
        else:
            seasons = [int(seasons_arg)]
    elif season_arg:
        seasons = [season_arg]
    else:
        seasons = [datetime.now().year - 1]

    pre_2022 = [s for s in seasons if s < FTN_FIRST_SEASON]
    if pre_2022:
        raise ValueError(
            f"FTN charting data begins in {FTN_FIRST_SEASON}. "
            f"Requested pre-FTN seasons: {pre_2022}"
        )
    return sorted(seasons)


def _save_local(df: pd.DataFrame, season: int) -> str:
    """Save FTN DataFrame to local Bronze directory.

    Args:
        df: FTN charting DataFrame for a single season.
        season: NFL season year.

    Returns:
        Absolute path of saved Parquet file.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    season_dir = os.path.join(BRONZE_DIR, "ftn_charting", f"season={season}")
    os.makedirs(season_dir, exist_ok=True)
    path = os.path.join(season_dir, f"ftn_charting_{ts}.parquet")
    df.to_parquet(path, index=False)
    print(f"  Saved -> data/bronze/ftn_charting/season={season}/ftn_charting_{ts}.parquet "
          f"({len(df):,} rows)")
    return path


def ingest_ftn_season(season: int) -> pd.DataFrame:
    """Fetch FTN charting data for a single season from nfl_data_py.

    Args:
        season: NFL season year (must be >= 2022).

    Returns:
        FTN charting DataFrame, or empty DataFrame on failure.
    """
    try:
        import nfl_data_py as nfl
    except ImportError:
        logger.error("nfl_data_py is not installed")
        return pd.DataFrame()

    print(f"  Fetching FTN data for season {season} ...")
    try:
        df = nfl.import_ftn_data([season])
    except Exception as exc:
        logger.warning("FTN fetch failed for season %d: %s", season, exc)
        return pd.DataFrame()

    if df is None or df.empty:
        logger.warning("FTN returned empty DataFrame for season %d", season)
        return pd.DataFrame()

    # Ensure season column present and correct
    if "season" not in df.columns:
        df = df.assign(season=season)

    print(f"  Season {season}: {len(df):,} rows x {df.shape[1]} cols")
    return df


def main() -> None:
    """Entry point for Bronze FTN ingestion CLI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Ingest FTN charting data to Bronze layer"
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Single NFL season to ingest (e.g. 2024). Overridden by --seasons.",
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default=None,
        help='Season range string, e.g. "2022-2025". Overrides --season.',
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        default=False,
        help="Also upload to S3 nfl-raw bucket (requires AWS credentials in .env).",
    )
    args = parser.parse_args()

    try:
        seasons = _parse_seasons(args.seasons, args.season)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    print(f"FTN Bronze Ingestion — seasons: {seasons}")

    s3_client = None
    if args.s3:
        try:
            import boto3
            from dotenv import load_dotenv

            load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                region_name=os.environ.get("AWS_REGION", "us-east-2"),
            )
            print("  S3 client initialised.")
        except Exception as exc:
            print(f"  S3 init failed ({exc}); proceeding local-only.")
            s3_client = None

    total_rows = 0
    for season in seasons:
        df = ingest_ftn_season(season)
        if df.empty:
            continue

        _save_local(df, season)
        total_rows += len(df)

        if s3_client is not None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            s3_key = f"ftn_charting/season={season}/ftn_charting_{ts}.parquet"
            try:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                    df.to_parquet(tmp.name, index=False)
                    s3_client.upload_file(tmp.name, "nfl-raw", s3_key)
                    os.unlink(tmp.name)
                print(f"  Uploaded -> s3://nfl-raw/{s3_key}")
            except Exception as exc:
                print(f"  S3 upload failed: {exc}")

    print(f"\nDone. Total rows ingested: {total_rows:,}")


if __name__ == "__main__":
    main()
