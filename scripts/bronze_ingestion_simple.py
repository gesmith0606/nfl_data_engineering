#!/usr/bin/env python3
"""
Simple Bronze Layer Ingestion — Registry-driven CLI with local-first storage.

Uses DATA_TYPE_REGISTRY for dispatch (no if/elif chain). Saves to data/bronze/
by default; optionally uploads to S3 with --s3 flag.
"""

import sys
import os
import pandas as pd
import boto3
from datetime import datetime
import argparse
from dotenv import load_dotenv

# Add project root to path so `src.*` imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.nfl_data_adapter import NFLDataAdapter
from src.config import validate_season_for_type, DATA_TYPE_SEASON_RANGES

# ---------------------------------------------------------------------------
# DATA_TYPE_REGISTRY — single source of truth for all Bronze data types.
# Adding a new type only requires a new entry here.
# ---------------------------------------------------------------------------

DATA_TYPE_REGISTRY = {
    "schedules": {
        "adapter_method": "fetch_schedules",
        "bronze_path": "schedules/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "pbp": {
        "adapter_method": "fetch_pbp",
        "bronze_path": "pbp/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "player_weekly": {
        "adapter_method": "fetch_weekly_data",
        "bronze_path": "players/weekly/season={season}/week={week}",
        "requires_week": True,
        "requires_season": True,
    },
    "player_seasonal": {
        "adapter_method": "fetch_seasonal_data",
        "bronze_path": "players/seasonal/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "snap_counts": {
        "adapter_method": "fetch_snap_counts",
        "bronze_path": "players/snaps/season={season}/week={week}",
        "requires_week": True,
        "requires_season": True,
    },
    "injuries": {
        "adapter_method": "fetch_injuries",
        "bronze_path": "players/injuries/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "rosters": {
        "adapter_method": "fetch_rosters",
        "bronze_path": "players/rosters/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "teams": {
        "adapter_method": "fetch_team_descriptions",
        "bronze_path": "teams",
        "requires_week": False,
        "requires_season": False,
    },
    "ngs": {
        "adapter_method": "fetch_ngs",
        "bronze_path": "ngs/{sub_type}/season={season}",
        "requires_week": False,
        "requires_season": True,
        "sub_types": ["passing", "rushing", "receiving"],
    },
    "pfr_weekly": {
        "adapter_method": "fetch_pfr_weekly",
        "bronze_path": "pfr/weekly/{sub_type}/season={season}",
        "requires_week": False,
        "requires_season": True,
        "sub_types": ["pass", "rush", "rec", "def"],
    },
    "pfr_seasonal": {
        "adapter_method": "fetch_pfr_seasonal",
        "bronze_path": "pfr/seasonal/{sub_type}/season={season}",
        "requires_week": False,
        "requires_season": True,
        "sub_types": ["pass", "rush", "rec", "def"],
    },
    "qbr": {
        "adapter_method": "fetch_qbr",
        "bronze_path": "qbr/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "depth_charts": {
        "adapter_method": "fetch_depth_charts",
        "bronze_path": "depth_charts/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "draft_picks": {
        "adapter_method": "fetch_draft_picks",
        "bronze_path": "draft_picks/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
    "combine": {
        "adapter_method": "fetch_combine",
        "bronze_path": "combine/season={season}",
        "requires_week": False,
        "requires_season": True,
    },
}


def upload_to_s3(df: pd.DataFrame, bucket: str, key: str, aws_credentials: dict) -> str:
    """Upload DataFrame to S3 as Parquet.

    Args:
        df: DataFrame to upload.
        bucket: S3 bucket name.
        key: S3 key (path).
        aws_credentials: AWS credentials dict.

    Returns:
        S3 URI of uploaded file.
    """
    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=aws_credentials["access_key"],
            aws_secret_access_key=aws_credentials["secret_key"],
            region_name=aws_credentials["region"],
        )
        temp_file = f"/tmp/{key.replace('/', '_')}.parquet"
        df.to_parquet(temp_file, index=False)
        s3_client.upload_file(temp_file, bucket, key)
        os.remove(temp_file)
        s3_uri = f"s3://{bucket}/{key}"
        print(f"  Uploaded to: {s3_uri}")
        return s3_uri
    except Exception as e:
        print(f"  S3 upload failed: {str(e)}")
        raise


def save_local(df: pd.DataFrame, local_path: str) -> str:
    """Save DataFrame as Parquet to the local filesystem.

    Args:
        df: DataFrame to save.
        local_path: Full path including filename.

    Returns:
        The local path written.
    """
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    df.to_parquet(local_path, index=False)
    print(f"  Saved locally: {local_path}")
    return local_path


def _build_method_kwargs(entry: dict, args) -> dict:
    """Build keyword arguments for the adapter fetch method.

    Args:
        entry: Registry entry dict for the data type.
        args: Parsed CLI arguments.

    Returns:
        kwargs dict to unpack into the adapter method.
    """
    method_name = entry["adapter_method"]
    kwargs: dict = {}

    # snap_counts adapter takes (season, week) positional — handle specially
    if method_name == "fetch_snap_counts":
        return {"season": args.season, "week": args.week}

    # Most methods take seasons as a list
    if entry["requires_season"]:
        kwargs["seasons"] = [args.season]

    # Sub-type methods (ngs, pfr_weekly, pfr_seasonal)
    if "sub_types" in entry:
        key = "stat_type" if method_name == "fetch_ngs" else "s_type"
        kwargs[key] = args.sub_type

    # PBP: curated columns, downcast, no participation merge
    if method_name == "fetch_pbp":
        from src.config import PBP_COLUMNS
        kwargs["columns"] = PBP_COLUMNS
        kwargs["downcast"] = True
        kwargs["include_participation"] = False

    # QBR frequency
    if method_name == "fetch_qbr":
        kwargs["frequency"] = args.frequency

    return kwargs


def parse_seasons_range(seasons_str: str) -> list:
    """Parse a seasons range string into a list of ints.

    Accepts either a single season ("2024") or a range ("2010-2025").

    Args:
        seasons_str: Season range string, e.g. "2010-2025" or "2024".

    Returns:
        List of season ints.

    Raises:
        ValueError: If start > end in a range.
    """
    if "-" in seasons_str:
        parts = seasons_str.split("-")
        start, end = int(parts[0]), int(parts[1])
        if start > end:
            raise ValueError(
                f"Invalid season range: start ({start}) > end ({end})"
            )
        return list(range(start, end + 1))
    return [int(seasons_str)]


def main():
    """Main ingestion function using registry dispatch."""

    parser = argparse.ArgumentParser(description="NFL Data Bronze Layer Ingestion")
    parser.add_argument(
        "--season", type=int, default=2024, help="NFL season (default: 2024)"
    )
    parser.add_argument(
        "--week", type=int, default=1, help="NFL week (default: 1)"
    )
    parser.add_argument(
        "--data-type",
        choices=sorted(DATA_TYPE_REGISTRY.keys()),
        default="schedules",
        help="Data type to ingest",
    )
    parser.add_argument(
        "--sub-type",
        type=str,
        default=None,
        help="Sub-type for NGS (passing/rushing/receiving) or PFR (pass/rush/rec/def)",
    )
    parser.add_argument(
        "--frequency",
        type=str,
        choices=["weekly", "seasonal"],
        default="weekly",
        help="Frequency for QBR data (default: weekly)",
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default=None,
        help="Season range for batch ingestion, e.g., 2010-2025 (overrides --season)",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        default=False,
        help="Upload to S3 in addition to local save (requires AWS credentials)",
    )

    args = parser.parse_args()

    entry = DATA_TYPE_REGISTRY[args.data_type]

    # --- Validate sub-type if required ---
    if "sub_types" in entry:
        if args.sub_type is None:
            print(
                f"Error: --sub-type required for {args.data_type}. "
                f"Valid values: {entry['sub_types']}"
            )
            return 1
        if args.sub_type not in entry["sub_types"]:
            print(
                f"Error: invalid --sub-type '{args.sub_type}'. "
                f"Valid values: {entry['sub_types']}"
            )
            return 1

    # --- Validate week if required ---
    if entry["requires_week"] and args.week is None:
        print(f"Error: --week is required for {args.data_type}")
        return 1

    # --- Handle --seasons batch mode ---
    if args.seasons:
        season_list = parse_seasons_range(args.seasons)
    else:
        season_list = [args.season]

    # --- Validate all seasons upfront ---
    if entry["requires_season"]:
        for s in season_list:
            if not validate_season_for_type(args.data_type, s):
                min_s, max_fn = DATA_TYPE_SEASON_RANGES[args.data_type]
                print(
                    f"Error: season {s} is not valid for {args.data_type} "
                    f"(valid range: {min_s}-{max_fn()})"
                )
                return 1

    print(f"NFL Bronze Layer Ingestion")
    print(f"Data Type: {args.data_type}, Seasons: {season_list}, Week: {args.week}")
    print("=" * 60)

    # --- Loop one season at a time (memory-safe for large datasets like PBP) ---
    adapter = NFLDataAdapter()
    total = len(season_list)
    for idx, season in enumerate(season_list, 1):
        args.season = season
        if total > 1:
            print(f"\nIngesting season {season}... ({idx}/{total})")

        method = getattr(adapter, entry["adapter_method"])
        kwargs = _build_method_kwargs(entry, args)
        df = method(**kwargs)

        if df.empty:
            print(f"  No data returned for season {season}.")
            continue

        print(f"  Records: {len(df):,}  Columns: {len(df.columns)}")

        # --- Validate schema ---
        try:
            val_result = adapter.validate_data(df, args.data_type)
            if val_result:
                if val_result.get("issues"):
                    for issue in val_result["issues"]:
                        print(f"  \u26a0 Validation: {issue}")
                else:
                    col_count = val_result.get("column_count", len(df.columns))
                    print(f"  \u2713 Validation passed: {col_count}/{col_count} columns valid")
        except Exception as e:
            print(f"  \u26a0 Validation error: {e}")

        # --- Build local path ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bronze_subpath = entry["bronze_path"].format(
            season=season,
            week=args.week,
            sub_type=getattr(args, "sub_type", None) or "",
        )
        if args.data_type == "qbr":
            filename = f"qbr_{args.frequency}_{ts}.parquet"
        else:
            filename = f"{args.data_type}_{ts}.parquet"
        local_dir = os.path.join("data", "bronze", bronze_subpath)
        local_path = os.path.join(local_dir, filename)

        # --- Save locally (primary) ---
        save_local(df, local_path)

        # --- Optional S3 upload ---
        if args.s3:
            load_dotenv()
            aws_credentials = {
                "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
                "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
                "region": os.getenv("AWS_REGION"),
            }
            bronze_bucket = os.getenv("S3_BUCKET_BRONZE", "nfl-raw")

            if not all(aws_credentials.values()):
                print("  Warning: AWS credentials missing, skipping S3 upload.")
            else:
                s3_key = f"{bronze_subpath}/{filename}"
                try:
                    upload_to_s3(df, bronze_bucket, s3_key, aws_credentials)
                except Exception:
                    print("  S3 upload failed; local copy is available.")

        print(f"  Ingestion complete: {len(df):,} records -> {local_path}")

    print(f"\nBatch ingestion finished: {total} season(s) processed.")
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
