#!/usr/bin/env python3
"""
Sentiment Processing CLI — Silver extraction and Gold aggregation.

Runs the Claude-powered extraction pipeline on Bronze sentiment documents,
then aggregates the resulting Silver signals into Gold player-week sentiment
multipliers.

Usage
-----
  # Full pipeline (extraction + aggregation) for week 1 of 2026
  python scripts/process_sentiment.py --season 2026 --week 1

  # Dry run: extract and aggregate but do not write output files
  python scripts/process_sentiment.py --season 2026 --week 1 --dry-run

  # Skip Claude extraction; aggregate existing Silver signals only
  python scripts/process_sentiment.py --season 2026 --week 1 --skip-extraction

Exit codes
----------
  0  Success
  1  Unexpected error
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: add project root to sys.path so `src.*` imports work whether
# the script is run from the project root or from scripts/.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.sentiment.processing.pipeline import SentimentPipeline
from src.sentiment.aggregation.weekly import WeeklyAggregator
from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("process_sentiment")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Returns:
        Configured ``argparse.ArgumentParser``.
    """
    parser = argparse.ArgumentParser(
        description="NFL Sentiment Pipeline: Bronze extraction → Silver → Gold aggregation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="NFL season year (e.g. 2026)",
    )
    parser.add_argument(
        "--week",
        type=int,
        required=True,
        help="NFL week number (1–18)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run extraction and aggregation without writing output files",
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        default=False,
        help="Skip Claude extraction; aggregate existing Silver signals only",
    )
    parser.add_argument(
        "--skip-team",
        action="store_true",
        default=False,
        help="Skip team-level sentiment aggregation",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    """Validate CLI arguments and exit with an error message if invalid.

    Args:
        args: Parsed namespace from argparse.

    Raises:
        SystemExit: If validation fails.
    """
    if not 1999 <= args.season <= 2030:
        logger.error("Invalid season %d — must be between 1999 and 2030", args.season)
        sys.exit(1)
    if not 1 <= args.week <= 18:
        logger.error("Invalid week %d — must be between 1 and 18", args.week)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point for the process_sentiment CLI.

    Returns:
        Integer exit code (0 = success, 1 = error).
    """
    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    _validate_args(args)

    season: int = args.season
    week: int = args.week
    dry_run: bool = args.dry_run
    skip_extraction: bool = args.skip_extraction

    logger.info(
        "process_sentiment: season=%d week=%d dry_run=%s skip_extraction=%s",
        season,
        week,
        dry_run,
        skip_extraction,
    )

    # ------------------------------------------------------------------
    # Step 1: Claude extraction (Bronze → Silver)
    # ------------------------------------------------------------------
    if not skip_extraction:
        logger.info("--- Step 1: Claude Extraction (Bronze → Silver) ---")
        try:
            pipeline = SentimentPipeline()
            if not pipeline.extractor.is_available:
                logger.warning(
                    "ANTHROPIC_API_KEY is not set. Extraction will be skipped. "
                    "Set the environment variable and re-run, or use --skip-extraction "
                    "if Silver signals already exist."
                )
            result = pipeline.run(season=season, week=week, dry_run=dry_run)
            logger.info(
                "Extraction complete: %d processed, %d skipped, %d failed, %d signals",
                result.processed_count,
                result.skipped_count,
                result.failed_count,
                result.signal_count,
            )
            if result.output_files:
                for path in result.output_files:
                    logger.info("  Silver output: %s", path)
        except Exception as exc:
            logger.error("Extraction step failed: %s", exc, exc_info=True)
            return 1
    else:
        logger.info("--- Step 1: Skipped (--skip-extraction) ---")

    # ------------------------------------------------------------------
    # Step 2: Aggregation (Silver → Gold)
    # ------------------------------------------------------------------
    logger.info("--- Step 2: Gold Aggregation (Silver → Gold) ---")
    try:
        aggregator = WeeklyAggregator()
        df = aggregator.aggregate(season=season, week=week, dry_run=dry_run)

        if df.empty:
            logger.warning(
                "No sentiment signals found for season=%d week=%d. "
                "Run ingestion scripts first (ingest_sentiment_rss.py, "
                "ingest_sentiment_sleeper.py).",
                season,
                week,
            )
        else:
            logger.info(
                "Aggregation complete: %d players with sentiment signals",
                len(df),
            )
            ruled_out = df["is_ruled_out"].sum() if "is_ruled_out" in df.columns else 0
            questionable = (
                df["is_questionable"].sum() if "is_questionable" in df.columns else 0
            )
            logger.info(
                "  Ruled out: %d | Questionable: %d",
                ruled_out,
                questionable,
            )
            if not dry_run:
                logger.info(
                    "Gold Parquet written to data/gold/sentiment/season=%d/week=%02d/",
                    season,
                    week,
                )
            else:
                logger.info("Dry run: Gold Parquet not written")

    except Exception as exc:
        logger.error("Aggregation step failed: %s", exc, exc_info=True)
        return 1

    # ------------------------------------------------------------------
    # Step 3: Team Aggregation (Gold player → Gold team)
    # ------------------------------------------------------------------
    if not args.skip_team:
        logger.info("--- Step 3: Team Aggregation (Gold player → Gold team) ---")
        try:
            team_agg = TeamWeeklyAggregator()
            team_df = team_agg.aggregate(season=season, week=week, dry_run=dry_run)

            if team_df.empty:
                logger.warning(
                    "No team sentiment produced for season=%d week=%d",
                    season,
                    week,
                )
            else:
                logger.info(
                    "Team aggregation complete: %d teams with sentiment signals",
                    len(team_df),
                )
                logger.info(
                    "  Multiplier range: [%.4f, %.4f]",
                    team_df["team_sentiment_multiplier"].min(),
                    team_df["team_sentiment_multiplier"].max(),
                )
                if not dry_run:
                    logger.info(
                        "Gold team Parquet written to data/gold/sentiment/team_sentiment/season=%d/week=%02d/",
                        season,
                        week,
                    )
                else:
                    logger.info("Dry run: Gold team Parquet not written")

        except Exception as exc:
            logger.error("Team aggregation step failed: %s", exc, exc_info=True)
            return 1
    else:
        logger.info("--- Step 3: Skipped (--skip-team) ---")

    logger.info("process_sentiment: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
