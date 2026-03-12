#!/usr/bin/env python3
"""
Batch Bronze Layer Ingestion — runs all 15 data types with progress reporting.

Iterates DATA_TYPE_REGISTRY, determines valid seasons per type from
DATA_TYPE_SEASON_RANGES, fetches via NFLDataAdapter, validates with
validate_data(), and saves locally via save_local().

Features:
- Graceful failure handling (continues on error)
- Skip-existing logic (default; override with --force)
- 0-row returns recorded as SKIP (not failure)
- Per-file validation via NFLDataAdapter.validate_data()
- gc.collect() after PBP seasons for memory safety
- Summary table with OK/SKIP/FAIL/SKIPPED counts

Usage:
    python scripts/bronze_batch_ingestion.py --dry-run
    python scripts/bronze_batch_ingestion.py --season-start 2020 --season-end 2024
    python scripts/bronze_batch_ingestion.py --force  # re-fetch even if files exist
"""

import argparse
import gc
import glob
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Add project root to path so `src.*` and `scripts.*` imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_ingestion_simple import DATA_TYPE_REGISTRY, save_local
from src.config import (
    DATA_TYPE_SEASON_RANGES,
    PBP_COLUMNS,
    validate_season_for_type,
)
from src.nfl_data_adapter import NFLDataAdapter, format_validation_output

# Result tuple: (data_type, variant, season, status, detail)
# status is one of: OK, SKIP, FAIL, SKIPPED, DRY_RUN
Result = Tuple[str, Optional[str], int, str, str]

DEFAULT_BASE_DIR = os.path.join("data")


def already_ingested(
    data_type: str,
    entry: dict,
    season: int,
    variant: Optional[str],
    base_dir: str,
) -> bool:
    """Check whether parquet files already exist for a type/season/variant.

    Args:
        data_type: Registry key (e.g. 'schedules', 'ngs').
        entry: Registry entry dict.
        season: Season year.
        variant: Sub-type or frequency variant (e.g. 'passing', 'weekly'), or None.
        base_dir: Root data directory (e.g. 'data').

    Returns:
        True if at least one parquet file exists in the expected directory.
    """
    bronze_path = entry["bronze_path"]

    # Format the path template
    fmt_kwargs: Dict[str, any] = {"season": season}
    if "{sub_type}" in bronze_path:
        fmt_kwargs["sub_type"] = variant or ""
    if "{week}" in bronze_path:
        # For week-partitioned types, check if ANY week directory has files
        fmt_kwargs["week"] = "*"

    try:
        subpath = bronze_path.format(**fmt_kwargs)
    except KeyError:
        return False

    search_dir = os.path.join(base_dir, "bronze", subpath)
    pattern = os.path.join(search_dir, "*.parquet")
    return len(glob.glob(pattern)) > 0


def _build_fetch_kwargs(entry: dict, season: int, variant: Optional[str]) -> dict:
    """Build keyword arguments for the adapter fetch method.

    Constructs kwargs directly from the registry entry, avoiding
    dependency on argparse Namespace objects.

    Args:
        entry: Registry entry dict for the data type.
        season: Season year to fetch.
        variant: Sub-type or frequency string, or None.

    Returns:
        kwargs dict to unpack into the adapter method.
    """
    method_name = entry["adapter_method"]
    kwargs: dict = {}

    # Most methods take seasons as a list
    if entry["requires_season"]:
        kwargs["seasons"] = [season]

    # Sub-type methods (ngs, pfr_weekly, pfr_seasonal)
    if "sub_types" in entry:
        key = "stat_type" if method_name == "fetch_ngs" else "s_type"
        kwargs[key] = variant

    # PBP: curated columns, downcast, no participation merge
    if method_name == "fetch_pbp":
        kwargs["columns"] = PBP_COLUMNS
        kwargs["downcast"] = True
        kwargs["include_participation"] = False

    # QBR frequency
    if method_name == "fetch_qbr":
        kwargs["frequency"] = variant or "weekly"

    return kwargs


def _get_variants(data_type: str, entry: dict) -> List[Tuple[Optional[str], str]]:
    """Determine the variant iterations for a data type.

    Args:
        data_type: Registry key.
        entry: Registry entry dict.

    Returns:
        List of (variant_value, display_label) tuples. Single-pass types
        return [(None, '')].
    """
    if "sub_types" in entry:
        return [(st, f"/{st}") for st in entry["sub_types"]]
    if data_type == "qbr":
        return [(f, f"/{f}") for f in ["weekly", "season"]]
    return [(None, "")]


def _get_valid_seasons(
    data_type: str, season_start: int, season_end: int
) -> List[int]:
    """Return the list of valid seasons for a data type within the requested range.

    Args:
        data_type: Registry key.
        season_start: First season to consider.
        season_end: Last season to consider.

    Returns:
        List of valid season ints, possibly empty.
    """
    seasons = []
    for s in range(season_start, season_end + 1):
        try:
            if validate_season_for_type(data_type, s):
                seasons.append(s)
        except ValueError:
            pass
    return seasons


def run_batch(
    season_start: int = 2016,
    season_end: int = 2025,
    skip_existing: bool = True,
    dry_run: bool = False,
    base_dir: str = DEFAULT_BASE_DIR,
) -> List[Result]:
    """Run batch ingestion across all data types.

    Args:
        season_start: First season to ingest (default 2016).
        season_end: Last season to ingest (default 2025).
        skip_existing: If True, skip types/seasons with existing parquet files.
        dry_run: If True, show what would run without fetching data.
        base_dir: Root data directory (default 'data').

    Returns:
        List of Result tuples: (data_type, variant, season, status, detail).
    """
    adapter = NFLDataAdapter()
    results: List[Result] = []
    total_types = len(DATA_TYPE_REGISTRY)

    for idx, (data_type, entry) in enumerate(DATA_TYPE_REGISTRY.items(), 1):
        variants = _get_variants(data_type, entry)

        # Teams has no season dimension
        if not entry["requires_season"]:
            print(f"\n[{idx}/{total_types}] {data_type}")
            for variant_val, variant_label in variants:
                if dry_run:
                    results.append((data_type, variant_val, 0, "DRY_RUN", "would fetch"))
                    print(f"  DRY_RUN: would fetch {data_type}{variant_label}")
                    continue
                try:
                    method = getattr(adapter, entry["adapter_method"])
                    kwargs = _build_fetch_kwargs(entry, 0, variant_val)
                    # Remove seasons key for non-season types
                    kwargs.pop("seasons", None)
                    df = method(**kwargs)

                    if df is None or (hasattr(df, "empty") and df.empty):
                        results.append((data_type, variant_val, 0, "SKIP", "0 rows returned"))
                        print(f"  SKIP: 0 rows returned")
                        continue

                    # Validate
                    try:
                        val_result = adapter.validate_data(df, data_type)
                        output = format_validation_output(val_result)
                        if output:
                            print(output)
                    except Exception as ve:
                        print(f"  Warning: validation error: {ve}")

                    # Save
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    local_dir = os.path.join(base_dir, "bronze", entry["bronze_path"])
                    local_path = os.path.join(local_dir, f"{data_type}_{ts}.parquet")
                    save_local(df, local_path)

                    results.append((data_type, variant_val, 0, "OK", f"{len(df)} rows, {len(df.columns)} cols"))
                    print(f"  OK: {len(df)} rows, {len(df.columns)} cols")
                except Exception as e:
                    results.append((data_type, variant_val, 0, "FAIL", str(e)))
                    print(f"  FAIL: {e}")
            continue

        # Season-based types
        valid_seasons = _get_valid_seasons(data_type, season_start, season_end)
        if not valid_seasons:
            print(f"\n[{idx}/{total_types}] {data_type} -- no valid seasons in range")
            continue

        print(f"\n[{idx}/{total_types}] {data_type} ({len(valid_seasons)} seasons)")

        for variant_val, variant_label in variants:
            if variant_label:
                print(f"  --- Variant: {variant_label.lstrip('/')} ---")

            for season in valid_seasons:
                if dry_run:
                    results.append((data_type, variant_val, season, "DRY_RUN", "would fetch"))
                    print(f"  Season {season}... DRY_RUN")
                    continue

                # Skip-existing check
                if skip_existing and already_ingested(data_type, entry, season, variant_val, base_dir):
                    results.append((data_type, variant_val, season, "SKIPPED", "already ingested"))
                    print(f"  Season {season}... SKIPPED (already ingested)")
                    continue

                try:
                    method = getattr(adapter, entry["adapter_method"])
                    kwargs = _build_fetch_kwargs(entry, season, variant_val)
                    df = method(**kwargs)

                    if df is None or (hasattr(df, "empty") and df.empty):
                        results.append((data_type, variant_val, season, "SKIP", "0 rows returned"))
                        print(f"  Season {season}... SKIP (0 rows returned)")
                        continue

                    # Validate
                    try:
                        val_result = adapter.validate_data(df, data_type)
                        output = format_validation_output(val_result)
                        if output:
                            print(output)
                    except Exception as ve:
                        print(f"  Warning: validation error: {ve}")

                    # Save (handle week-partitioned types)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                    if entry.get("week_partition") and "week" in df.columns:
                        for week_num in sorted(df["week"].unique()):
                            week_df = df[df["week"] == week_num]
                            week_subpath = entry["bronze_path"].format(
                                season=season, week=int(week_num),
                                sub_type=variant_val or "",
                            )
                            week_path = os.path.join(
                                base_dir, "bronze", week_subpath,
                                f"{data_type}_{ts}.parquet",
                            )
                            save_local(week_df, week_path)
                        detail = f"{len(df)} rows, {len(df['week'].unique())} weeks"
                    else:
                        bronze_subpath = entry["bronze_path"].format(
                            season=season, week=getattr(df, "week", 1) if entry.get("requires_week") else 0,
                            sub_type=variant_val or "",
                        )
                        if data_type == "qbr":
                            filename = f"qbr_{variant_val}_{ts}.parquet"
                        else:
                            filename = f"{data_type}_{ts}.parquet"
                        local_path = os.path.join(base_dir, "bronze", bronze_subpath, filename)
                        save_local(df, local_path)
                        detail = f"{len(df)} rows, {len(df.columns)} cols"

                    results.append((data_type, variant_val, season, "OK", detail))
                    print(f"  Season {season}... OK ({detail})")

                except Exception as e:
                    results.append((data_type, variant_val, season, "FAIL", str(e)))
                    print(f"  Season {season}... FAIL ({e})")

            # Memory cleanup for PBP
            if entry["adapter_method"] == "fetch_pbp":
                gc.collect()

    return results


def print_summary(results: List[Result]) -> None:
    """Print a summary table of batch results.

    Args:
        results: List of Result tuples from run_batch().
    """
    ok = sum(1 for r in results if r[3] == "OK")
    skip = sum(1 for r in results if r[3] == "SKIP")
    skipped = sum(1 for r in results if r[3] == "SKIPPED")
    fail = sum(1 for r in results if r[3] == "FAIL")
    dry = sum(1 for r in results if r[3] == "DRY_RUN")
    total = len(results)

    print("\n" + "=" * 60)
    print("BATCH INGESTION SUMMARY")
    print("=" * 60)
    print(f"  Total items:    {total}")
    print(f"  Succeeded (OK): {ok}")
    print(f"  Skipped (empty):{skip}")
    print(f"  Skipped (exist):{skipped}")
    print(f"  Failed:         {fail}")
    if dry:
        print(f"  Dry run:        {dry}")

    # Show failures
    failures = [r for r in results if r[3] == "FAIL"]
    if failures:
        print("\nFailed items:")
        for data_type, variant, season, status, detail in failures:
            v = f"/{variant}" if variant else ""
            print(f"  - {data_type}{v} season={season}: {detail}")

    print()


def main() -> int:
    """CLI entry point for batch Bronze ingestion.

    Returns:
        Exit code: 0 if no failures, 1 if any failures.
    """
    parser = argparse.ArgumentParser(
        description="Batch Bronze Layer Ingestion -- all 15 data types"
    )
    parser.add_argument(
        "--season-start",
        type=int,
        default=2016,
        help="First season to ingest (default: 2016)",
    )
    parser.add_argument(
        "--season-end",
        type=int,
        default=2025,
        help="Last season to ingest (default: 2025)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-fetch even if files already exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would run without fetching data",
    )

    args = parser.parse_args()

    print("NFL Batch Bronze Ingestion")
    print(f"Seasons: {args.season_start}-{args.season_end}")
    print(f"Skip existing: {not args.force}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 60)

    results = run_batch(
        season_start=args.season_start,
        season_end=args.season_end,
        skip_existing=not args.force,
        dry_run=args.dry_run,
    )

    print_summary(results)

    has_failures = any(r[3] == "FAIL" for r in results)
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
