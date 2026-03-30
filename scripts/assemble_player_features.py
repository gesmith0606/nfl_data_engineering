#!/usr/bin/env python3
"""Assemble player-week feature vectors from Silver data sources.

Reads 9 Silver sources (usage, advanced, historical, defense, pbp_metrics,
tendencies, player_quality, game_context, market_data) plus Bronze schedules,
applies temporal lag enforcement and eligibility filtering, and writes per-season
Parquet files to data/gold/player_features/.

Usage:
    python scripts/assemble_player_features.py --seasons 2020 2021 2022 2023 2024
    python scripts/assemble_player_features.py --season 2024
    python scripts/assemble_player_features.py --seasons 2020 2021 2022 2023 2024 --validate
"""

import argparse
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import PLAYER_DATA_SEASONS, PLAYER_LABEL_COLUMNS
from player_feature_engineering import (
    assemble_player_features,
    detect_leakage,
    get_player_feature_columns,
    validate_temporal_integrity,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Assemble player-week feature vectors from Silver data sources "
            "and write per-season Parquet files to the Gold layer."
        ),
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=None,
        help=f"Seasons to assemble (default: {PLAYER_DATA_SEASONS})",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Single season shorthand (mutually exclusive with --seasons)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run leakage detection and temporal integrity checks",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(
            os.path.dirname(__file__), "..", "data", "gold", "player_features"
        ),
        help="Output directory (default: data/gold/player_features)",
    )
    return parser


def main() -> int:
    """Run player feature assembly pipeline.

    Returns:
        Exit code: 0 on success, 1 on validation failure.
    """
    parser = build_parser()
    args = parser.parse_args()

    # Resolve seasons
    if args.season is not None and args.seasons is not None:
        logger.error("Cannot specify both --season and --seasons")
        return 1
    if args.season is not None:
        seasons = [args.season]
    elif args.seasons is not None:
        seasons = args.seasons
    else:
        seasons = PLAYER_DATA_SEASONS

    output_dir = os.path.abspath(args.output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    total_rows = 0
    total_features = 0
    all_violations = []
    all_leakage = []

    logger.info("Assembling player features for seasons: %s", seasons)

    for season in seasons:
        logger.info("--- Season %d ---", season)
        df = assemble_player_features(season)

        if df.empty:
            logger.warning("Season %d: no data assembled (skipping)", season)
            continue

        feat_cols = get_player_feature_columns(df)
        logger.info(
            "Season %d: %d rows, %d total columns, %d feature columns",
            season, len(df), len(df.columns), len(feat_cols),
        )

        # Write Parquet
        season_dir = os.path.join(output_dir, f"season={season}")
        os.makedirs(season_dir, exist_ok=True)
        out_path = os.path.join(season_dir, f"player_features_{timestamp}.parquet")
        df.to_parquet(out_path, index=False)
        logger.info("Wrote %s", out_path)

        total_rows += len(df)
        total_features = len(feat_cols)

        # Validation
        if args.validate:
            violations = validate_temporal_integrity(df)
            leakage = detect_leakage(df, feat_cols, PLAYER_LABEL_COLUMNS)
            all_violations.extend(violations)
            all_leakage.extend(leakage)

            if violations:
                for raw, roll, r in violations:
                    logger.warning(
                        "TEMPORAL VIOLATION: %s vs %s (r=%.3f)", raw, roll, r
                    )
            else:
                logger.info("Season %d: 0 temporal violations", season)

            if leakage:
                for feat, target, r in leakage:
                    logger.warning(
                        "LEAKAGE WARNING: %s -> %s (r=%.3f)", feat, target, r
                    )
            else:
                logger.info("Season %d: 0 leakage warnings", season)

    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("  Seasons: %d", len(seasons))
    logger.info("  Total rows: %d", total_rows)
    logger.info("  Feature columns: %d", total_features)

    if args.validate:
        logger.info("  Temporal violations: %d", len(all_violations))
        logger.info("  Leakage warnings: %d", len(all_leakage))
        if all_violations or all_leakage:
            logger.error("VALIDATION FAILED")
            return 1
        logger.info("VALIDATION PASSED: 0 leakage warnings, 0 temporal violations")

    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
