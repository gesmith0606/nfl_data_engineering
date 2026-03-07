#!/usr/bin/env python3
"""
Pipeline health check — validates data freshness and quality across all S3 layers.

Exit code 0 = healthy (zero errors, warnings are allowed).
Exit code 1 = unhealthy (one or more checks produced an ERROR).

Usage:
    python scripts/check_pipeline_health.py
    python scripts/check_pipeline_health.py --season 2024 --week 10
    python scripts/check_pipeline_health.py --layer bronze
    python scripts/check_pipeline_health.py --max-age-days 5
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, NamedTuple, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project root on sys.path so we can import src/config.py
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config  # noqa: E402 — must come after sys.path insertion

# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------

# A Parquet file under this threshold is almost certainly empty or corrupt.
MIN_FILE_SIZE_BYTES = 1_024  # 1 KB

# Default freshness window.  Overridable via --max-age-days or
# the HEALTH_CHECK_MAX_AGE_DAYS environment variable.
DEFAULT_MAX_AGE_DAYS = 8

# Bronze partition prefixes that must exist for each week.
# Keys are human-readable labels; values are prefix templates.
REQUIRED_BRONZE_PREFIXES = {
    "player_weekly": "players/weekly/season={season}/week={week}/",
    "snap_counts":   "players/snaps/season={season}/week={week}/",
    "injuries":      "players/injuries/season={season}/week={week}/",
    "rosters":       "players/rosters/season={season}/",
    "games":         "games/season={season}/week={week}/",
}

# Gold projection prefix template.
GOLD_PROJECTION_PREFIX = "projections/season={season}/week={week}/"


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class CheckResult(NamedTuple):
    """Single health-check outcome."""
    level: str          # "OK", "WARN", or "ERROR"
    label: str          # Short human-readable label
    message: str        # Detail message


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def _make_s3_client(region: str) -> boto3.client:
    """
    Return a boto3 S3 client.

    Credential resolution order (standard boto3 chain):
      1. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY environment variables
      2. ~/.aws/credentials profile
      3. IAM instance role (EC2 / ECS / Lambda)

    Raises RuntimeError with a clear message if credentials are absent.
    """
    try:
        client = boto3.client("s3", region_name=region)
        # Probe credentials early with a cheap call
        client.list_buckets()
        return client
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        raise RuntimeError(
            f"AWS credential error ({code}). "
            "Ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set, "
            "or that an IAM role is attached to this environment."
        ) from exc
    except BotoCoreError as exc:
        raise RuntimeError(f"AWS connection failed: {exc}") from exc


def _list_objects(s3_client, bucket: str, prefix: str) -> list:
    """
    Return all S3 object metadata dicts under *prefix* in *bucket*.

    Uses a paginator so it handles prefix listings with more than 1000 objects.
    Each dict contains at minimum: Key (str), Size (int), LastModified (datetime).
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    objects = []
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                objects.append(obj)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "NoSuchBucket":
            raise RuntimeError(f"Bucket does not exist: s3://{bucket}") from exc
        raise
    return objects


# ---------------------------------------------------------------------------
# Individual check implementations
# ---------------------------------------------------------------------------

def check_layer_freshness(
    s3_client,
    bucket: str,
    layer_name: str,
    prefix: str,
    max_age_days: int,
) -> CheckResult:
    """
    Check that at least one Parquet file under *prefix* was modified within
    *max_age_days* days.

    Returns:
        CheckResult with level OK / WARN / ERROR.
    """
    objects = _list_objects(s3_client, bucket, prefix)
    parquet_objects = [o for o in objects if o["Key"].endswith(".parquet")]

    if not parquet_objects:
        return CheckResult(
            level="ERROR",
            label=f"{layer_name} freshness",
            message=f"No Parquet files found under s3://{bucket}/{prefix}",
        )

    now = datetime.now(tz=timezone.utc)
    threshold = now - timedelta(days=max_age_days)
    latest_obj = max(parquet_objects, key=lambda o: o["LastModified"])
    latest_ts = latest_obj["LastModified"]
    age_days = (now - latest_ts).days

    if latest_ts < threshold:
        return CheckResult(
            level="WARN",
            label=f"{layer_name} freshness",
            message=(
                f"Most recent file is {age_days} day(s) old "
                f"(threshold: {max_age_days} days). "
                f"Key: {latest_obj['Key']}"
            ),
        )

    return CheckResult(
        level="OK",
        label=f"{layer_name} freshness",
        message=f"Fresh — latest file is {age_days} day(s) old ({len(parquet_objects)} Parquet files found)",
    )


def check_file_sizes(
    s3_client,
    bucket: str,
    label: str,
    prefix: str,
    min_size_bytes: int = MIN_FILE_SIZE_BYTES,
) -> List[CheckResult]:
    """
    Flag any Parquet file under *prefix* whose size is below *min_size_bytes*.

    A sub-threshold file almost always indicates an empty DataFrame was
    serialised, or the upload was interrupted.
    """
    objects = _list_objects(s3_client, bucket, prefix)
    parquet_objects = [o for o in objects if o["Key"].endswith(".parquet")]

    results = []
    for obj in parquet_objects:
        size_bytes = obj["Size"]
        size_kb = size_bytes / 1_024
        key = obj["Key"]
        if size_bytes < min_size_bytes:
            results.append(
                CheckResult(
                    level="ERROR",
                    label=f"{label} file size",
                    message=(
                        f"{key!r} is {size_kb:.1f} KB "
                        f"(minimum expected: {min_size_bytes / 1_024:.0f} KB) — "
                        "file may be empty or corrupt"
                    ),
                )
            )

    return results


def check_partition_exists(
    s3_client,
    bucket: str,
    label: str,
    prefix: str,
) -> CheckResult:
    """
    Verify that at least one Parquet file exists under the given S3 prefix.
    """
    objects = _list_objects(s3_client, bucket, prefix)
    parquet_objects = [o for o in objects if o["Key"].endswith(".parquet")]

    if parquet_objects:
        return CheckResult(
            level="OK",
            label=label,
            message=f"{len(parquet_objects)} Parquet file(s) present at s3://{bucket}/{prefix}",
        )

    return CheckResult(
        level="ERROR",
        label=label,
        message=f"No Parquet files found at s3://{bucket}/{prefix}",
    )


def check_gold_projections(
    s3_client,
    gold_bucket: str,
    season: int,
    week: int,
    max_age_days: int,
) -> CheckResult:
    """
    Verify that Gold projection files exist for *season*/*week* and are fresh.
    """
    prefix = GOLD_PROJECTION_PREFIX.format(season=season, week=week)
    return check_layer_freshness(
        s3_client,
        gold_bucket,
        f"Gold projections (season={season} week={week})",
        prefix,
        max_age_days,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_health_checks(
    season: int,
    week: int,
    layer_filter: Optional[str],
    max_age_days: int,
) -> int:
    """
    Execute all health checks and print a formatted report.

    Returns:
        0 if all checks pass (OK or WARN only).
        1 if any check returns ERROR.
    """
    region      = os.getenv("AWS_REGION", config.S3_REGION)
    bronze_bucket = os.getenv("S3_BUCKET_BRONZE", config.S3_BUCKET_BRONZE)
    silver_bucket = os.getenv("S3_BUCKET_SILVER", config.S3_BUCKET_SILVER)
    gold_bucket   = os.getenv("S3_BUCKET_GOLD",   config.S3_BUCKET_GOLD)

    print(f"\nNFL Pipeline Health Check — {season} Week {week}")
    print("=" * 60)

    # ---------------------------------------------------------
    # Build S3 client once; surface credential errors up front.
    # ---------------------------------------------------------
    try:
        s3 = _make_s3_client(region)
    except RuntimeError as exc:
        print(f"[ERROR] Cannot connect to AWS: {exc}")
        return 1

    all_results: List[CheckResult] = []

    # ---------------------------------------------------------
    # BRONZE layer checks
    # ---------------------------------------------------------
    if layer_filter in (None, "bronze"):
        print("\n--- Bronze Layer ---")

        # 1a. Overall freshness — scan the whole bronze bucket root
        all_results.append(
            check_layer_freshness(
                s3, bronze_bucket, "Bronze",
                prefix="",
                max_age_days=max_age_days,
            )
        )

        # 1b. Each required partition must be present
        for data_type, prefix_tmpl in REQUIRED_BRONZE_PREFIXES.items():
            prefix = prefix_tmpl.format(season=season, week=week)
            all_results.append(
                check_partition_exists(s3, bronze_bucket, f"Bronze {data_type}", prefix)
            )

            # 1c. File-size sanity check within each partition
            size_results = check_file_sizes(
                s3, bronze_bucket, f"Bronze {data_type}", prefix
            )
            all_results.extend(size_results)

    # ---------------------------------------------------------
    # SILVER layer checks
    # ---------------------------------------------------------
    if layer_filter in (None, "silver"):
        print("\n--- Silver Layer ---")

        silver_prefix = f"players/usage/season={season}/week={week}/"
        all_results.append(
            check_layer_freshness(
                s3, silver_bucket, "Silver usage metrics",
                prefix=silver_prefix,
                max_age_days=max_age_days,
            )
        )

        all_results.extend(
            check_file_sizes(s3, silver_bucket, "Silver usage metrics", silver_prefix)
        )

    # ---------------------------------------------------------
    # GOLD layer checks
    # ---------------------------------------------------------
    if layer_filter in (None, "gold"):
        print("\n--- Gold Layer ---")

        all_results.append(
            check_gold_projections(s3, gold_bucket, season, week, max_age_days)
        )

        gold_prefix = GOLD_PROJECTION_PREFIX.format(season=season, week=week)
        all_results.extend(
            check_file_sizes(s3, gold_bucket, "Gold projections", gold_prefix)
        )

    # ---------------------------------------------------------
    # Print results
    # ---------------------------------------------------------
    print("\n--- Results ---")
    error_count = 0
    warn_count  = 0

    level_icons = {
        "OK":    "OK ",
        "WARN":  "WARN",
        "ERROR": "ERROR",
    }

    for result in all_results:
        icon = level_icons.get(result.level, result.level)
        print(f"[{icon}]  {result.label}: {result.message}")
        if result.level == "ERROR":
            error_count += 1
        elif result.level == "WARN":
            warn_count += 1

    # ---------------------------------------------------------
    # Overall verdict
    # ---------------------------------------------------------
    print("\n" + "=" * 60)
    if error_count == 0 and warn_count == 0:
        overall = "HEALTHY"
    elif error_count == 0:
        overall = f"HEALTHY with warnings ({warn_count} warning(s))"
    else:
        overall = f"UNHEALTHY ({error_count} error(s), {warn_count} warning(s))"

    print(f"Overall: {overall}")
    print("=" * 60)

    return 1 if error_count > 0 else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_season_week(args: argparse.Namespace) -> tuple[int, int]:
    """
    Return (season, week) from CLI args, env overrides, or config defaults.

    Resolution order:
        1. CLI flags (--season / --week)
        2. PIPELINE_WEEK_OVERRIDE env var ("YYYY:WW")
        3. DEFAULT_SEASON / DEFAULT_WEEK from src/config.py
    """
    override = os.getenv("PIPELINE_WEEK_OVERRIDE", "").strip()

    season = args.season
    week   = args.week

    if not season or not week:
        if override and ":" in override:
            parts = override.split(":", 1)
            try:
                season = season or int(parts[0].strip())
                week   = week   or int(parts[1].strip())
            except ValueError:
                pass  # malformed override — fall through to defaults

    season = season or config.DEFAULT_SEASON
    week   = week   or config.DEFAULT_WEEK

    return int(season), int(week)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="NFL Pipeline Health Check — validates data freshness and quality across S3 layers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--season", type=int, default=None,
        help="NFL season year (default: config.DEFAULT_SEASON or PIPELINE_WEEK_OVERRIDE)",
    )
    parser.add_argument(
        "--week", type=int, default=None,
        help="NFL week number (default: config.DEFAULT_WEEK or PIPELINE_WEEK_OVERRIDE)",
    )
    parser.add_argument(
        "--layer",
        choices=["bronze", "silver", "gold"],
        default=None,
        help="Check only a specific layer (default: check all layers)",
    )
    parser.add_argument(
        "--max-age-days", type=int, default=None,
        help=(
            f"Freshness threshold in days "
            f"(default: HEALTH_CHECK_MAX_AGE_DAYS env var or {DEFAULT_MAX_AGE_DAYS})"
        ),
    )
    args = parser.parse_args()

    season, week = _resolve_season_week(args)

    # Freshness threshold: CLI flag > env var > hard-coded default
    if args.max_age_days is not None:
        max_age_days = args.max_age_days
    else:
        env_val = os.getenv("HEALTH_CHECK_MAX_AGE_DAYS", "").strip()
        try:
            max_age_days = int(env_val) if env_val else DEFAULT_MAX_AGE_DAYS
        except ValueError:
            print(f"[WARN] HEALTH_CHECK_MAX_AGE_DAYS='{env_val}' is not a valid integer; "
                  f"using default of {DEFAULT_MAX_AGE_DAYS} days.")
            max_age_days = DEFAULT_MAX_AGE_DAYS

    return run_health_checks(
        season=season,
        week=week,
        layer_filter=args.layer,
        max_age_days=max_age_days,
    )


if __name__ == "__main__":
    sys.exit(main())
