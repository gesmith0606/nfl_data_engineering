#!/usr/bin/env python3
"""
Daily Sentiment Pipeline -- ingest, extract, aggregate.

Orchestrates the full sentiment pipeline (5 sources + 3 processing steps):
1. Ingest from RSS feeds (5 feeds)
2. Ingest from Reddit (r/fantasyfootball, r/nfl, r/DynastyFF)
3. Ingest from Sleeper (trending players)
4. Ingest from RotoWire RSS (NEW in 61-04)
5. Ingest from Pro Football Talk RSS (NEW in 61-04)
6. Extract signals (rule-based ALWAYS runs per D-06; Claude is optional)
7. Aggregate player-level sentiment
8. Aggregate team-level sentiment

The pipeline is idempotent: re-running on the same day skips
already-processed documents (via processed_ids.json tracking).

Per Phase 61 D-06: individual source failures log a warning but do not
abort the pipeline.  The pipeline returns exit code 0 as long as at
least one step succeeded.  The rule-based extractor runs regardless of
``ANTHROPIC_API_KEY`` presence.

Usage
-----
  python scripts/daily_sentiment_pipeline.py --season 2026 --week 1
  python scripts/daily_sentiment_pipeline.py --season 2026 --week 1 --dry-run
  python scripts/daily_sentiment_pipeline.py --season 2026 --week 1 --skip-reddit
  python scripts/daily_sentiment_pipeline.py --skip-rotowire --skip-pft
  python scripts/daily_sentiment_pipeline.py --dry-run --verbose
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Bootstrap: add project root to sys.path so `src.*` imports work.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("daily_sentiment_pipeline")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """Outcome of a single pipeline step.

    Attributes:
        name: Human-readable step name.
        success: Whether the step completed without error.
        detail: Summary string (e.g. "5 feeds, 42 items").
        elapsed_sec: Wall-clock seconds for the step.
        error: Error message if ``success`` is False.
    """

    name: str
    success: bool = True
    detail: str = ""
    elapsed_sec: float = 0.0
    error: str = ""


@dataclass
class PipelineResult:
    """Aggregate outcome of the full pipeline run.

    Attributes:
        steps: List of individual step results.
        dry_run: Whether this was a dry-run (no files written).
    """

    steps: List[StepResult] = field(default_factory=list)
    dry_run: bool = False

    @property
    def all_success(self) -> bool:
        """True if every step succeeded."""
        return all(s.success for s in self.steps)

    @property
    def any_success(self) -> bool:
        """True if at least one step succeeded."""
        return any(s.success for s in self.steps)


# ---------------------------------------------------------------------------
# NFL week auto-detection
# ---------------------------------------------------------------------------


def detect_nfl_week() -> tuple:
    """Auto-detect current NFL season and week from today's date.

    The NFL season starts the first Thursday on or after September 5.
    Each week is 7 days.  Before Week 1 of the current year's season,
    we treat the date as belonging to the prior season's off-season.

    Returns:
        Tuple of (season_year, week_number).
    """
    today = datetime.date.today()

    def week1_thursday(yr: int) -> datetime.date:
        """Return the Thursday on or after September 5 for a given year."""
        sep5 = datetime.date(yr, 9, 5)
        days_ahead = (3 - sep5.weekday()) % 7
        return sep5 + datetime.timedelta(days=days_ahead)

    anchor = week1_thursday(today.year)
    if today < anchor:
        season = today.year - 1
        anchor = week1_thursday(season)
    else:
        season = today.year

    days_since = (today - anchor).days
    week = max(1, min((days_since // 7) + 1, 18))

    return season, week


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


def _run_rss_ingestion(season: int, dry_run: bool, verbose: bool) -> StepResult:
    """Ingest articles from RSS feeds.

    Args:
        season: NFL season year.
        dry_run: If True, fetches but does not write files.
        verbose: If True, enables debug logging in the sub-script.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="RSS Ingestion")
    t0 = time.monotonic()
    try:
        from scripts.ingest_sentiment_rss import main as rss_main

        argv = ["--season", str(season)]
        if dry_run:
            argv.append("--dry-run")
        if verbose:
            argv.append("--verbose")
        rc = rss_main(argv)
        step.success = rc == 0
        step.detail = "completed" if rc == 0 else f"exit code {rc}"
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.error("RSS ingestion failed: %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


def _run_reddit_ingestion(season: int, dry_run: bool, verbose: bool) -> StepResult:
    """Ingest posts from Reddit.

    Args:
        season: NFL season year.
        dry_run: If True, fetches but does not write files.
        verbose: If True, enables debug logging in the sub-script.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="Reddit Ingestion")
    t0 = time.monotonic()
    try:
        from scripts.ingest_sentiment_reddit import main as reddit_main

        argv = ["--season", str(season)]
        if dry_run:
            argv.append("--dry-run")
        if verbose:
            argv.append("--verbose")
        rc = reddit_main(argv)
        step.success = rc == 0
        step.detail = "completed" if rc == 0 else f"exit code {rc}"
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.error("Reddit ingestion failed: %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


def _run_sleeper_ingestion(season: int, dry_run: bool, verbose: bool) -> StepResult:
    """Ingest trending players from Sleeper API.

    Args:
        season: NFL season year.
        dry_run: If True, fetches but does not write files.
        verbose: If True, enables debug logging in the sub-script.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="Sleeper Ingestion")
    t0 = time.monotonic()
    try:
        from scripts.ingest_sentiment_sleeper import main as sleeper_main

        argv = ["--season", str(season)]
        if dry_run:
            argv.append("--dry-run")
        if verbose:
            argv.append("--verbose")
        rc = sleeper_main(argv)
        step.success = rc == 0
        step.detail = "completed" if rc == 0 else f"exit code {rc}"
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.error("Sleeper ingestion failed: %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


def _run_rotowire_ingestion(season: int, dry_run: bool, verbose: bool) -> StepResult:
    """Ingest articles from the RotoWire RSS feed.

    Wraps ``scripts.ingest_sentiment_rotowire.main`` with the same argv
    contract used by the other source wrappers (D-06 graceful exit is
    enforced inside the sub-script; we only surface its return code).

    Args:
        season: NFL season year.
        dry_run: If True, fetches but does not write files.
        verbose: If True, enables debug logging in the sub-script.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="RotoWire Ingestion")
    t0 = time.monotonic()
    try:
        from scripts.ingest_sentiment_rotowire import main as rotowire_main

        argv = ["--season", str(season)]
        if dry_run:
            argv.append("--dry-run")
        if verbose:
            argv.append("--verbose")
        rc = rotowire_main(argv)
        step.success = rc == 0
        step.detail = "completed" if rc == 0 else f"exit code {rc}"
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.warning("RotoWire ingestion failed (non-fatal, D-06): %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


def _run_pft_ingestion(season: int, dry_run: bool, verbose: bool) -> StepResult:
    """Ingest articles from the Pro Football Talk RSS feed.

    Wraps ``scripts.ingest_sentiment_pft.main`` with the same argv
    contract used by the other source wrappers (D-06 graceful exit is
    enforced inside the sub-script; we only surface its return code).

    Args:
        season: NFL season year.
        dry_run: If True, fetches but does not write files.
        verbose: If True, enables debug logging in the sub-script.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="PFT Ingestion")
    t0 = time.monotonic()
    try:
        from scripts.ingest_sentiment_pft import main as pft_main

        argv = ["--season", str(season)]
        if dry_run:
            argv.append("--dry-run")
        if verbose:
            argv.append("--verbose")
        rc = pft_main(argv)
        step.success = rc == 0
        step.detail = "completed" if rc == 0 else f"exit code {rc}"
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.warning("PFT ingestion failed (non-fatal, D-06): %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


def _run_extraction(season: int, week: int, dry_run: bool, verbose: bool) -> StepResult:
    """Extract sentiment signals from Bronze documents.

    Uses the SentimentPipeline which tracks processed document IDs
    to avoid reprocessing.  Falls back to rule-based extraction when
    ANTHROPIC_API_KEY is not set.  Per D-06 (phase 61 CONTEXT), the
    rule-based path is the primary model-facing signal source and
    MUST run regardless of API-key availability.

    Args:
        season: NFL season year.
        week: NFL week number.
        dry_run: If True, does not write output files.
        verbose: If True, enables debug logging.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="Signal Extraction")
    t0 = time.monotonic()
    try:
        from src.sentiment.processing.pipeline import SentimentPipeline
        from src.sentiment.processing.rule_extractor import RuleExtractor

        pipeline = SentimentPipeline()
        extractor_type = type(pipeline.extractor).__name__
        if isinstance(pipeline.extractor, RuleExtractor):
            logger.info(
                "Event-only path: ANTHROPIC_API_KEY unset, using "
                "RuleExtractor (rule-first per D-06)"
            )
        else:
            logger.info("Extractor=%s (Claude enrichment available)", extractor_type)
        result = pipeline.run(season=season, week=week, dry_run=dry_run)
        step.detail = (
            f"{result.processed_count} processed, "
            f"{result.skipped_count} skipped, "
            f"{result.signal_count} signals [extractor={extractor_type}]"
        )
        step.success = True
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.error("Signal extraction failed: %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


def _run_player_aggregation(season: int, week: int, dry_run: bool) -> StepResult:
    """Aggregate player-level weekly sentiment.

    Args:
        season: NFL season year.
        week: NFL week number.
        dry_run: If True, does not write output files.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="Player Aggregation")
    t0 = time.monotonic()
    try:
        from src.sentiment.aggregation.weekly import WeeklyAggregator

        aggregator = WeeklyAggregator()
        df = aggregator.aggregate(season=season, week=week, dry_run=dry_run)
        step.detail = f"{len(df)} players"
        step.success = True
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.error("Player aggregation failed: %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


def _run_team_aggregation(season: int, week: int, dry_run: bool) -> StepResult:
    """Aggregate team-level weekly sentiment.

    Args:
        season: NFL season year.
        week: NFL week number.
        dry_run: If True, does not write output files.

    Returns:
        StepResult with outcome details.
    """
    step = StepResult(name="Team Aggregation")
    t0 = time.monotonic()
    try:
        from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator

        aggregator = TeamWeeklyAggregator()
        df = aggregator.aggregate(season=season, week=week, dry_run=dry_run)
        step.detail = f"{len(df)} teams"
        step.success = True
    except Exception as exc:
        step.success = False
        step.error = str(exc)
        logger.error("Team aggregation failed: %s", exc)
    step.elapsed_sec = time.monotonic() - t0
    return step


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured ``argparse.ArgumentParser``.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Daily Sentiment Pipeline: ingest all sources, "
            "extract signals, aggregate player + team sentiment."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="NFL season year (default: auto-detected from calendar).",
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="NFL week number 1-18 (default: auto-detected from calendar).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview pipeline steps without writing any files.",
    )
    parser.add_argument(
        "--skip-rss",
        action="store_true",
        help="Skip RSS feed ingestion.",
    )
    parser.add_argument(
        "--skip-reddit",
        action="store_true",
        help="Skip Reddit ingestion.",
    )
    parser.add_argument(
        "--skip-sleeper",
        action="store_true",
        help="Skip Sleeper API ingestion.",
    )
    parser.add_argument(
        "--skip-rotowire",
        action="store_true",
        help="Skip RotoWire RSS ingestion.",
    )
    parser.add_argument(
        "--skip-pft",
        action="store_true",
        help="Skip Pro Football Talk RSS ingestion.",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip all ingestion; only run extraction + aggregation.",
    )
    parser.add_argument(
        "--enable-llm-enrichment",
        action="store_true",
        help=(
            "Reserved flag for plan 61-06 (D-04): toggles optional Claude "
            "Haiku website enrichment.  Currently a no-op; rule-based "
            "extraction is authoritative for the model path."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def run_pipeline(
    season: int,
    week: int,
    dry_run: bool = False,
    skip_rss: bool = False,
    skip_reddit: bool = False,
    skip_sleeper: bool = False,
    skip_rotowire: bool = False,
    skip_pft: bool = False,
    skip_ingest: bool = False,
    enable_llm_enrichment: bool = False,
    verbose: bool = False,
) -> PipelineResult:
    """Execute the full daily sentiment pipeline.

    Each step is independent; failures in one source do not abort
    subsequent steps (D-06 guarantee).  The pipeline returns exit code
    0 as long as at least one step succeeds.  The rule-based extractor
    runs regardless of ``ANTHROPIC_API_KEY`` availability.

    Args:
        season: NFL season year.
        week: NFL week number (1-18).
        dry_run: If True, no files are written.
        skip_rss: If True, skip RSS ingestion.
        skip_reddit: If True, skip Reddit ingestion.
        skip_sleeper: If True, skip Sleeper ingestion.
        skip_rotowire: If True, skip RotoWire RSS ingestion.
        skip_pft: If True, skip Pro Football Talk RSS ingestion.
        skip_ingest: If True, skip all ingestion steps.
        enable_llm_enrichment: Reserved for plan 61-06 (D-04); currently
            a no-op — Claude Haiku enrichment is not yet wired here.
        verbose: If True, enable debug logging.

    Returns:
        PipelineResult with per-step outcomes.
    """
    result = PipelineResult(dry_run=dry_run)

    logger.info("=" * 60)
    logger.info(
        "Daily Sentiment Pipeline | season=%d week=%d | dry_run=%s",
        season,
        week,
        dry_run,
    )
    if enable_llm_enrichment:
        logger.info("enable_llm_enrichment=True (reserved for 61-06; no-op today)")
    logger.info("=" * 60)

    # --- Phase 1: Ingestion (5 sources) ---
    if not skip_ingest:
        if not skip_rss:
            logger.info("--- Step 1/8: RSS Ingestion ---")
            result.steps.append(_run_rss_ingestion(season, dry_run, verbose))
        else:
            logger.info("--- Step 1/8: RSS Ingestion [SKIPPED] ---")

        if not skip_reddit:
            logger.info("--- Step 2/8: Reddit Ingestion ---")
            result.steps.append(_run_reddit_ingestion(season, dry_run, verbose))
        else:
            logger.info("--- Step 2/8: Reddit Ingestion [SKIPPED] ---")

        if not skip_sleeper:
            logger.info("--- Step 3/8: Sleeper Ingestion ---")
            result.steps.append(_run_sleeper_ingestion(season, dry_run, verbose))
        else:
            logger.info("--- Step 3/8: Sleeper Ingestion [SKIPPED] ---")

        if not skip_rotowire:
            logger.info("--- Step 4/8: RotoWire Ingestion ---")
            result.steps.append(_run_rotowire_ingestion(season, dry_run, verbose))
        else:
            logger.info("--- Step 4/8: RotoWire Ingestion [SKIPPED] ---")

        if not skip_pft:
            logger.info("--- Step 5/8: PFT Ingestion ---")
            result.steps.append(_run_pft_ingestion(season, dry_run, verbose))
        else:
            logger.info("--- Step 5/8: PFT Ingestion [SKIPPED] ---")
    else:
        logger.info("--- Steps 1-5: All Ingestion [SKIPPED] ---")

    # --- Phase 2: Extraction (rule-first per D-06; ALWAYS runs) ---
    logger.info("--- Step 6/8: Signal Extraction ---")
    result.steps.append(_run_extraction(season, week, dry_run, verbose))

    # --- Phase 3: Aggregation ---
    logger.info("--- Step 7/8: Player Aggregation ---")
    result.steps.append(_run_player_aggregation(season, week, dry_run))

    logger.info("--- Step 8/8: Team Aggregation ---")
    result.steps.append(_run_team_aggregation(season, week, dry_run))

    return result


def _print_summary(result: PipelineResult) -> None:
    """Print a human-readable summary of pipeline results.

    Args:
        result: Completed PipelineResult.
    """
    logger.info("=" * 60)
    logger.info("PIPELINE SUMMARY%s", " (DRY RUN)" if result.dry_run else "")
    logger.info("=" * 60)

    for step in result.steps:
        status = "OK" if step.success else "FAIL"
        elapsed = f"{step.elapsed_sec:.1f}s"
        detail = step.detail or step.error or ""
        logger.info(
            "  [%4s] %-22s %s  %s",
            status,
            step.name,
            elapsed,
            detail,
        )

    succeeded = sum(1 for s in result.steps if s.success)
    total = len(result.steps)
    logger.info(
        "Result: %d/%d steps succeeded",
        succeeded,
        total,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the daily sentiment pipeline.

    Args:
        argv: Argument list (uses sys.argv if None).

    Returns:
        Exit code: 0 if at least one step succeeded, 1 if all failed.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Auto-detect season and week if not provided
    if args.season is None or args.week is None:
        auto_season, auto_week = detect_nfl_week()
        season = args.season if args.season is not None else auto_season
        week = args.week if args.week is not None else auto_week
        logger.info("Auto-detected: season=%d week=%d", season, week)
    else:
        season = args.season
        week = args.week

    result = run_pipeline(
        season=season,
        week=week,
        dry_run=args.dry_run,
        skip_rss=args.skip_rss,
        skip_reddit=args.skip_reddit,
        skip_sleeper=args.skip_sleeper,
        skip_rotowire=args.skip_rotowire,
        skip_pft=args.skip_pft,
        skip_ingest=args.skip_ingest,
        enable_llm_enrichment=args.enable_llm_enrichment,
        verbose=args.verbose,
    )

    _print_summary(result)

    # Exit 0 if at least one step succeeded, 1 if all failed
    if not result.steps:
        logger.warning("No steps were executed.")
        return 0

    return 0 if result.any_success else 1


if __name__ == "__main__":
    sys.exit(main())
