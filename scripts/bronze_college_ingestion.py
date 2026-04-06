#!/usr/bin/env python3
"""
Bronze College Data Ingestion — CFBD API → local Parquet files.

Fetches college football player stats, usage, team info, and draft picks
from the CFBD (CollegeFootballData.com) API and stores them as Parquet
in data/bronze/college_*/.

Usage:
    python scripts/bronze_college_ingestion.py --season 2024 --data-type player_stats
    python scripts/bronze_college_ingestion.py --season 2024 --data-type usage
    python scripts/bronze_college_ingestion.py --season 2024 --data-type draft_picks
    python scripts/bronze_college_ingestion.py --seasons 2020 2021 2022 2023 2024

Requires CFBD_API_KEY environment variable (free key from collegefootballdata.com).
"""

import sys
import os
import argparse
from datetime import datetime

import pandas as pd

# Add project root to path so src imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.college_data_adapter import CollegeDataAdapter, pivot_player_stats

# Project root for local storage
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")

# Data type registry
COLLEGE_DATA_TYPES = {
    "player_stats": {
        "method": "fetch_player_season_stats",
        "bronze_path": "college_player_stats/season={season}",
        "post_process": "pivot",
    },
    "usage": {
        "method": "fetch_player_usage",
        "bronze_path": "college_usage/season={season}",
        "post_process": None,
    },
    "teams": {
        "method": "fetch_team_info",
        "bronze_path": "college_teams",
        "post_process": None,
    },
    "draft_picks": {
        "method": "fetch_draft_picks",
        "bronze_path": "college_draft_picks/season={season}",
        "post_process": None,
    },
}


def ingest_college_data(
    adapter: CollegeDataAdapter,
    data_type: str,
    season: int,
) -> bool:
    """Fetch and save one college data type for a single season.

    Args:
        adapter: Configured CollegeDataAdapter instance.
        data_type: One of COLLEGE_DATA_TYPES keys.
        season: College football season year.

    Returns:
        True if data was successfully written, False otherwise.
    """
    entry = COLLEGE_DATA_TYPES[data_type]
    method_name = entry["method"]
    method = getattr(adapter, method_name)

    # Teams endpoint doesn't need season arg
    if data_type == "teams":
        df = method()
    elif data_type == "draft_picks":
        df = method(nfl_year=season)
    else:
        df = method(season=season)

    if df.empty:
        print(f"  [SKIP] No data returned for {data_type} season={season}")
        return False

    # Post-process if needed
    if entry["post_process"] == "pivot":
        df = pivot_player_stats(df)
        if df.empty:
            print(
                f"  [SKIP] Pivot produced empty result for {data_type} season={season}"
            )
            return False

    # Build output path
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path_template = entry["bronze_path"]
    rel_dir = path_template.format(season=season)
    out_dir = os.path.join(PROJECT_ROOT, "data", "bronze", rel_dir)
    os.makedirs(out_dir, exist_ok=True)

    filename = f"{data_type}_{ts}.parquet"
    out_path = os.path.join(out_dir, filename)

    df.to_parquet(out_path, index=False)
    print(f"  [OK] {data_type} season={season}: {len(df)} rows → {out_path}")
    return True


def main() -> None:
    """CLI entrypoint for college data ingestion."""
    parser = argparse.ArgumentParser(
        description="Ingest college football data from CFBD API"
    )
    parser.add_argument(
        "--season",
        type=int,
        help="Single season to ingest",
    )
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        help="Multiple seasons to ingest (space-separated)",
    )
    parser.add_argument(
        "--data-type",
        choices=list(COLLEGE_DATA_TYPES.keys()),
        default="player_stats",
        help="Type of college data to ingest (default: player_stats)",
    )

    args = parser.parse_args()

    if args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = args.seasons
    else:
        # Default: last 5 seasons
        seasons = list(range(2020, 2026))

    adapter = CollegeDataAdapter()
    if not adapter.is_available:
        print(
            "ERROR: CFBD API unavailable. Set CFBD_API_KEY environment variable.\n"
            "Get a free key at https://collegefootballdata.com/key"
        )
        sys.exit(1)

    print(f"Ingesting college {args.data_type} for seasons: {seasons}")
    success_count = 0
    for season in seasons:
        ok = ingest_college_data(adapter, args.data_type, season)
        if ok:
            success_count += 1

    print(f"\nDone: {success_count}/{len(seasons)} seasons ingested")


if __name__ == "__main__":
    main()
