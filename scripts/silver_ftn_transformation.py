#!/usr/bin/env python3
"""Silver FTN Charting Transformation.

Reads Bronze FTN charting parquet + Bronze PBP, attributes per-play
flags to receiver and QB player IDs, aggregates to per-player-week,
adds shift(1) trailing features, and writes Silver parquet to:

    data/silver/players/ftn/season=YYYY/ftn_player_week_YYYYMMDD_HHMMSS.parquet

FTN coverage starts 2022; seasons before 2022 are skipped.

Output columns (all _roll4 and _trail are the model-safe lagged variants):
  Receiver: ftn_catchable_rate, ftn_contested_rate, ftn_drop_rate,
            ftn_pa_target_share, ftn_created_rec_rate
  QB:       ftn_blitz_rate, ftn_avg_pass_rushers, ftn_out_of_pocket_rate,
            ftn_throw_away_rate, ftn_interception_worthy_rate, ftn_play_action_rate
  Trailing: {above}_roll4, {above}_trail (shift(1) within player-season)

Usage:
    python scripts/silver_ftn_transformation.py --seasons 2022-2025
    python scripts/silver_ftn_transformation.py --season 2024
"""

import argparse
import logging
import os
import sys
from typing import List

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from ftn_features import (
    FTN_FEATURE_COLUMNS,
    build_ftn_silver,
)

logger = logging.getLogger(__name__)

BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")
FTN_FIRST_SEASON = 2022


def _parse_seasons(args) -> List[int]:
    """Parse CLI season arguments into a sorted list of ints.

    Args:
        args: Parsed argparse namespace with .seasons and .season attributes.

    Returns:
        Sorted list of season years, filtered to >= FTN_FIRST_SEASON.
    """
    if args.seasons:
        if "-" in args.seasons:
            parts = args.seasons.split("-")
            start, end = int(parts[0]), int(parts[1])
            seasons = list(range(start, end + 1))
        else:
            seasons = [int(args.seasons)]
    else:
        seasons = [args.season]

    valid = [s for s in seasons if s >= FTN_FIRST_SEASON]
    skipped = [s for s in seasons if s < FTN_FIRST_SEASON]
    if skipped:
        print(
            f"NOTE: Skipping seasons before {FTN_FIRST_SEASON} "
            f"(FTN coverage starts 2022): {skipped}"
        )
    return sorted(valid)


def main() -> None:
    """CLI entry point for Silver FTN transformation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Build Silver FTN charting features from Bronze PBP + FTN data"
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2024,
        help="Single NFL season (default: 2024). Overridden by --seasons.",
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default=None,
        help='Season range like "2022-2025" or single season like "2024".',
    )
    args = parser.parse_args()

    seasons = _parse_seasons(args)
    if not seasons:
        print("No valid FTN seasons to process.")
        sys.exit(0)

    print(f"Silver FTN Transformation — seasons: {seasons}")
    print(f"  Bronze dir: {BRONZE_DIR}")
    print(f"  Silver dir: {SILVER_DIR}")
    print(f"  FTN trailing feature columns: {len(FTN_FEATURE_COLUMNS)}")

    saved = build_ftn_silver(
        seasons=seasons,
        bronze_dir=BRONZE_DIR,
        silver_dir=SILVER_DIR,
    )

    if not saved:
        print("\nWARNING: No Silver FTN files written. Check Bronze data availability.")
        print("  Run: python scripts/bronze_ftn_ingestion.py --seasons 2022-2025")
        sys.exit(1)

    print(f"\nWrote {len(saved)} Silver FTN file(s):")
    for season, path in sorted(saved.items()):
        rel = os.path.relpath(path, PROJECT_ROOT)
        print(f"  season={season} -> {rel}")

    print("\nDone.")


if __name__ == "__main__":
    main()
