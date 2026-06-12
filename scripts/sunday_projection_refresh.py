#!/usr/bin/env python3
"""
Sunday Projection Refresh

Re-applies the LATEST injury/inactive information to the already-published
Gold weekly projections WITHOUT regenerating the model (cheap, leak-free).

This script exists because:
  - Projections are generated Tuesday and graded against Sleeper consensus
    that updates through Sunday-morning inactives.
  - RB rank-ordering is disproportionately affected by last-minute committee
    decisions, IR activations, and game-day inactives.
  - Rather than re-running the full projection model (which would be costly
    and could introduce consistency issues), this script performs a targeted
    undo/re-apply of the injury multiplier layer only.

Undo/re-apply strategy
----------------------
Case A — Gold file has ``injury_multiplier`` column (regular-season run):
    For multiplier > 0: undo = stat / old_multiplier; then re-apply new mult.
    For multiplier == 0 (player was Out on Tuesday): raw stat columns are
    already zeroed. We CANNOT restore them from disk alone. Strategy:
        - If NEW status is also zeroed (Out/IR/etc.): no-op — already zero.
        - If NEW status clears them (Active/Questionable): log the asymmetry;
          leave projected_points at 0 (we don't have the pre-injury value).
          This is a known, documented limitation — honesty > silent corruption.

Case B — Gold file has NO ``injury_multiplier`` column (preseason-era file
    or old schema without injury persistence):
    The injury adjustment was never applied to the stored stats. Apply fresh
    multipliers directly with no undo step. This is the simpler, safer path.

Idempotency
-----------
Running the refresh twice with identical injury data produces no change beyond
a second timestamped file with the same values. The downstream
``download_latest_parquet()`` pattern always reads only the newest file, so
a re-run is harmless.

Usage
-----
    python scripts/sunday_projection_refresh.py
    python scripts/sunday_projection_refresh.py --season 2026 --week 5
    python scripts/sunday_projection_refresh.py --season 2026 --week 5 --scoring half_ppr
    python scripts/sunday_projection_refresh.py --dry-run

Backtest probe (for analysis only — does NOT write Gold output):
    python scripts/sunday_projection_refresh.py --backtest-probe --season 2024 --weeks 10 11 12
"""

import argparse
import datetime
import glob as globmod
import logging
import os
import sys
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nfl_data_integration import NFLDataFetcher  # noqa: E402
from projection_engine import (  # noqa: E402
    INJURY_MULTIPLIERS,
    apply_injury_adjustments,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")

# Columns that must be scaled when the injury multiplier changes.
#
# ``apply_injury_adjustments()`` scales only two groups:
#   1. ``projected_points`` (always)
#   2. Any column whose name starts with ``proj_`` *except*
#      ``proj_season`` and ``proj_week`` (informational metadata)
#
# The bare stat columns in the Gold files (passing_yards, rushing_yards, etc.)
# are NOT scaled by apply_injury_adjustments — they remain at their pre-injury
# values even when a player is Out.  This is by design: they represent the
# projected workload if healthy and are used downstream for display purposes.
#
# ``projected_floor`` and ``projected_ceiling`` are also bare (no proj_ prefix)
# and are NOT scaled by apply_injury_adjustments.
#
# For the undo step in Case A, we only need to undo/re-apply the columns that
# were scaled: projected_points + proj_* (minus proj_season/proj_week).
# The actual set is discovered dynamically from the DataFrame at runtime.
# This constant defines the fallback list if no proj_* columns are present.
SCALABLE_ALWAYS_COLS: list = ["projected_points"]

# Scores that the weekly pipeline can produce.
SCORING_FORMATS: list = ["half_ppr", "ppr", "standard"]


# ---------------------------------------------------------------------------
# Season / week auto-detection (mirrors daily_sentiment_pipeline.py)
# ---------------------------------------------------------------------------


def detect_nfl_week(
    _today: Optional[datetime.date] = None,
) -> tuple:
    """Auto-detect current NFL season and week from today's date.

    The NFL season starts the first Thursday on or after September 5.
    Each week is 7 days.  Before Week 1 of the current year's season,
    we treat the date as belonging to the prior season's off-season.

    Args:
        _today: Override today's date (for testing only).  If None,
            uses ``datetime.date.today()``.

    Returns:
        Tuple of (season_year, week_number).
    """
    today = _today if _today is not None else datetime.date.today()

    def week1_thursday(yr: int) -> datetime.date:
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
# Local file helpers
# ---------------------------------------------------------------------------


def _load_latest_gold_projections(
    season: int, week: int, scoring: str
) -> tuple:
    """Load the latest Gold projection file for a given season/week/scoring.

    Args:
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format (half_ppr, ppr, standard).

    Returns:
        Tuple of (DataFrame, source_path) where source_path is the parquet
        file that was read, or (empty DataFrame, None) if nothing found.
    """
    pattern = os.path.join(
        GOLD_DIR,
        f"projections/season={season}/week={week}",
        f"projections_{scoring}_*.parquet",
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        logger.warning(
            "No Gold projection files found for season=%d week=%d scoring=%s "
            "(pattern: %s)",
            season,
            week,
            scoring,
            pattern,
        )
        return pd.DataFrame(), None

    latest = files[-1]
    logger.info(
        "Loading latest Gold projection: %s (%d candidates)",
        latest,
        len(files),
    )
    return pd.read_parquet(latest), latest


def _load_latest_bronze_injuries(season: int, week: int) -> pd.DataFrame:
    """Load the latest Bronze injury file for a season, filtered to a week.

    Args:
        season: NFL season year.
        week: NFL week number to filter to.

    Returns:
        DataFrame of injury rows for the target week, or empty DataFrame.
    """
    pattern = os.path.join(
        BRONZE_DIR,
        f"players/injuries/season={season}/*.parquet",
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()

    # Prefer the newest file (largest timestamp suffix)
    df = pd.read_parquet(files[-1])
    if df.empty:
        return df

    if "week" in df.columns:
        week_rows = df[pd.to_numeric(df["week"], errors="coerce") == week].copy()
        if not week_rows.empty:
            return week_rows
        # No rows for target week yet (common in preseason/early season)
        logger.debug(
            "No Bronze injury rows for season=%d week=%d (available weeks: %s)",
            season,
            week,
            sorted(df["week"].unique().tolist()),
        )
    return pd.DataFrame()


def _fetch_live_injuries(season: int, week: int) -> pd.DataFrame:
    """Fetch the freshest injury report from nfl_data_py for season/week.

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        DataFrame with injury rows, or empty DataFrame on failure.
    """
    try:
        fetcher = NFLDataFetcher()
        df = fetcher.fetch_injuries([season], week=week)
        logger.info("Fetched %d live injury rows from nfl-data-py", len(df))
        return df
    except Exception as exc:
        logger.warning("Could not fetch live injury data: %s", exc)
        return pd.DataFrame()


def _get_fresh_injuries(season: int, week: int) -> pd.DataFrame:
    """Get the freshest injury report: live nfl_data_py then Bronze fallback.

    Priority:
      1. nfl_data_py live fetch (most current).
      2. Latest Bronze file filtered to target week.

    An empty DataFrame is NOT an error — it simply means no injury report
    exists yet for the target week (normal in preseason or early week).

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        DataFrame with the freshest available injury rows.
    """
    df = _fetch_live_injuries(season, week)
    if not df.empty:
        return df

    logger.info("Live fetch empty; falling back to Bronze injury file")
    df = _load_latest_bronze_injuries(season, week)
    if not df.empty:
        logger.info("Loaded %d rows from Bronze injury file", len(df))
    return df


# ---------------------------------------------------------------------------
# Undo / re-apply logic
# ---------------------------------------------------------------------------


def _undo_and_reapply(
    df: pd.DataFrame,
    new_injuries_df: pd.DataFrame,
) -> tuple:
    """Undo old injury multipliers and re-apply fresh ones.

    This function is the core of the refresh mechanism.  It handles two
    distinct cases based on whether the Gold file already has injury columns:

    Case A (columns present — regular-season Gold file):
        For each player, undo the stored ``injury_multiplier`` by dividing
        the stat columns, then apply the new multiplier from the fresh injury
        report.  Players whose old multiplier was 0 (Outs) cannot have their
        stat values restored from disk, so if their NEW status is Active or
        Questionable this produces an under-projection of 0 points.  This
        asymmetry is logged explicitly and documented in the return summary.

    Case B (no injury columns — preseason or old-schema Gold file):
        Call ``apply_injury_adjustments`` directly with no undo step.  The
        stored stat columns are assumed to be pre-injury-adjustment values.

    Args:
        df: Gold projection DataFrame loaded from disk.
        new_injuries_df: Fresh injury report, week-filtered.

    Returns:
        Tuple of (refreshed DataFrame, summary dict with change counts).
    """
    has_old_injury_cols = (
        "injury_multiplier" in df.columns and "injury_status" in df.columns
    )

    summary: dict = {
        "case": "A" if has_old_injury_cols else "B",
        "total_players": len(df),
        "status_changed": 0,
        "multiplier_changed": 0,
        "asymmetry_limited": 0,  # count where old=0 but new>0 → can't restore
        "new_outs": 0,
        "new_questionable": 0,
        "cleared_to_active": 0,
    }

    if not has_old_injury_cols:
        # Case B — no prior injury columns in the file; apply directly
        logger.info(
            "Case B: no injury columns in Gold file; applying fresh adjustments directly"
        )
        refreshed = apply_injury_adjustments(df, new_injuries_df)
        # Compute summary from result
        if "injury_multiplier" in refreshed.columns:
            summary["multiplier_changed"] = int(
                (refreshed["injury_multiplier"] < 1.0).sum()
            )
        return refreshed, summary

    # Case A — Gold file has injury columns; undo then re-apply
    logger.info(
        "Case A: undoing old injury multipliers and re-applying fresh ones"
    )

    # Build a working copy.
    work = df.copy()

    # -----------------------------------------------------------------------
    # Determine which columns to undo: only the columns that
    # apply_injury_adjustments actually scales.  That function scales:
    #   - projected_points (always)
    #   - Any col starting with proj_*, except proj_season and proj_week
    # Bare stat columns (passing_yards, etc.) are NOT scaled — do not undo them.
    # -----------------------------------------------------------------------
    proj_star_cols = [
        c
        for c in work.columns
        if c.startswith("proj_") and c not in ("proj_season", "proj_week")
    ]
    scalable_present = (
        ["projected_points"] + proj_star_cols
        if "projected_points" in work.columns
        else proj_star_cols
    )
    scalable_present = [c for c in scalable_present if c in work.columns]

    # -----------------------------------------------------------------------
    # Undo step: for rows with old multiplier > 0, divide to recover pre-
    # injury values.  Rows with multiplier == 0 are zeroed — we cannot
    # recover the original values from the file alone.
    # -----------------------------------------------------------------------
    old_mult = work["injury_multiplier"].copy()
    old_status = work["injury_status"].copy()

    can_undo = old_mult > 0.0
    # Restore projected values for rows that were NOT fully zeroed
    for col in scalable_present:
        work.loc[can_undo, col] = (
            work.loc[can_undo, col] / old_mult[can_undo]
        ).round(4)

    # -----------------------------------------------------------------------
    # Now apply fresh injury adjustments using the upstream function.
    # We pass the "undone" DataFrame so it starts from pre-injury values.
    # -----------------------------------------------------------------------
    # Strip the old injury columns before calling apply_injury_adjustments so
    # it does not try to re-scale already-scaled columns.
    work = work.drop(columns=["injury_status", "injury_multiplier"])

    refreshed = apply_injury_adjustments(work, new_injuries_df)

    # -----------------------------------------------------------------------
    # Asymmetry handling: rows that were zeroed (old_mult == 0) but whose
    # new status is non-zero cannot be restored.  Mark them in the log.
    # -----------------------------------------------------------------------
    if "injury_multiplier" in refreshed.columns:
        new_mult = refreshed["injury_multiplier"]
        asymmetric_mask = (~can_undo) & (new_mult > 0.0)
        n_asymmetric = int(asymmetric_mask.sum())
        if n_asymmetric > 0:
            names = refreshed.loc[asymmetric_mask, "player_name"].tolist()
            logger.warning(
                "ASYMMETRY: %d player(s) were previously zeroed (Out/IR) but "
                "now cleared to a non-zero status — their stats on disk are 0 "
                "and cannot be restored without re-running the full model. "
                "These players remain at 0 projected points this refresh. "
                "Players: %s",
                n_asymmetric,
                names,
            )
            summary["asymmetry_limited"] = n_asymmetric

    # -----------------------------------------------------------------------
    # Compute change statistics for the summary log.
    # -----------------------------------------------------------------------
    if "injury_status" in refreshed.columns:
        new_status = refreshed["injury_status"]
        changed_mask = old_status != new_status
        summary["status_changed"] = int(changed_mask.sum())

        new_outs = (new_status.isin(["Out", "IR", "Injured Reserve",
                                     "PUP", "Physically Unable to Perform",
                                     "Suspension"])).sum()
        new_q = (new_status == "Questionable").sum()
        cleared = (
            (old_status.isin(["Out", "IR", "Injured Reserve",
                               "PUP", "Physically Unable to Perform",
                               "Suspension"]))
            & (new_status == "Active")
        ).sum()
        summary["new_outs"] = int(new_outs)
        summary["new_questionable"] = int(new_q)
        summary["cleared_to_active"] = int(cleared)

    if "injury_multiplier" in refreshed.columns:
        new_mult = refreshed["injury_multiplier"]
        old_mult_aligned = old_mult.reindex(refreshed.index).fillna(1.0)
        summary["multiplier_changed"] = int(
            (new_mult != old_mult_aligned).sum()
        )

    return refreshed, summary


# ---------------------------------------------------------------------------
# Refresh summary log
# ---------------------------------------------------------------------------


def _write_refresh_summary(
    season: int,
    week: int,
    scoring: str,
    source_file: str,
    output_file: str,
    summary: dict,
    refreshed: pd.DataFrame,
    injuries_df: pd.DataFrame,
    dry_run: bool,
) -> None:
    """Print a human-readable refresh summary to stdout.

    Args:
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format string.
        source_file: Path to the Gold file that was read.
        output_file: Path to the new Gold file written (or None if dry-run).
        summary: Summary dict from _undo_and_reapply.
        refreshed: Refreshed projections DataFrame.
        injuries_df: Injury report used.
        dry_run: If True, no file was written.
    """
    print()
    print("=" * 70)
    print(
        f"SUNDAY PROJECTION REFRESH — Season {season} Week {week} "
        f"({scoring.upper()})"
    )
    print("=" * 70)
    print(f"  Source Gold file : {os.path.basename(source_file)}")
    if dry_run:
        print("  Output           : (dry-run — no file written)")
    else:
        print(f"  Output Gold file : {os.path.basename(output_file)}")
    print(f"  Injury rows used : {len(injuries_df)}")
    print(f"  Undo/reapply case: {summary.get('case', '?')}")
    print(f"  Total players    : {summary['total_players']}")
    print(f"  Status changed   : {summary['status_changed']}")
    print(f"  Multiplier chgd  : {summary['multiplier_changed']}")
    print(f"  New Outs/IR      : {summary['new_outs']}")
    print(f"  New Questionable : {summary['new_questionable']}")
    print(f"  Cleared→Active   : {summary['cleared_to_active']}")
    print(f"  Asymmetry-limited: {summary['asymmetry_limited']}")

    if summary["status_changed"] > 0 and "injury_status" in refreshed.columns:
        # Print detailed change table
        print()
        print("  Players whose injury status changed:")
        print(
            f"  {'Name':<30} {'Pos':<5} {'Old Mult':>9} {'New Mult':>9} "
            f"{'Old Status':<15} {'New Status':<15}"
        )
        print(f"  {'-'*90}")

        # We need old status info — pull it from the injury columns in the
        # refreshed df vs what was in the source (we have old in summary via
        # side-channel; simplest is to re-join from injuries_df)
        display_df = refreshed[
            ["player_name", "position", "injury_status", "injury_multiplier"]
        ].copy()
        display_df = display_df.sort_values("injury_multiplier")
        for _, row in display_df[display_df["injury_multiplier"] < 1.0].iterrows():
            print(
                f"  {row['player_name']:<30} {row['position']:<5} "
                f"{row['injury_multiplier']:>9.2f}  "
                f"  {row['injury_status']}"
            )

    print("=" * 70)
    print()


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------


def _write_gold_output(
    refreshed: pd.DataFrame,
    season: int,
    week: int,
    scoring: str,
    ts: str,
) -> str:
    """Write the refreshed projections to the Gold partition as a new timestamped file.

    The file name uses the ``refresh_`` prefix instead of ``projections_`` so
    it is easily distinguishable from the Tuesday-generated file while still
    being picked up as the latest by any consumer calling
    ``download_latest_parquet()`` on the partition.

    Args:
        refreshed: Refreshed projection DataFrame.
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format string.
        ts: Timestamp string (YYYYMMDD_HHMMSS) for the file name.

    Returns:
        Absolute path to the written file.
    """
    partition = os.path.join(
        GOLD_DIR, f"projections/season={season}/week={week}"
    )
    os.makedirs(partition, exist_ok=True)
    filename = f"projections_{scoring}_{ts}.parquet"
    output_path = os.path.join(partition, filename)
    refreshed.to_parquet(output_path, index=False)
    logger.info("Wrote refreshed Gold file: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Backtest sanity probe
# ---------------------------------------------------------------------------


def run_backtest_probe(season: int, weeks: list) -> None:
    """Run a cheap backtest sanity probe for a range of weeks.

    Simulates what the Sunday refresh would do for historical weeks:
    loads the available Bronze injury data for the given week and computes
    how many players' projections would change vs a baseline with no
    injury adjustments applied.  DOES NOT generate projections or write
    any Gold output.

    Args:
        season: NFL season year.
        weeks: List of week numbers to probe.
    """
    print()
    print("=" * 70)
    print(f"BACKTEST PROBE — Season {season}, Weeks {weeks}")
    print("=" * 70)

    for week in weeks:
        print(f"\n  Week {week}:")

        # Load the actual Gold files for this week
        files = sorted(
            globmod.glob(
                os.path.join(
                    GOLD_DIR,
                    f"projections/season={season}/week={week}",
                    "projections_half_ppr_*.parquet",
                )
            )
        )
        if not files:
            print(f"    No Gold projections found for season={season} week={week} — skipping")
            continue

        gold_df = pd.read_parquet(files[-1])
        print(f"    Gold file: {os.path.basename(files[-1])} ({len(gold_df)} players)")

        # Load Bronze injury data for this week
        injuries_df = _load_latest_bronze_injuries(season, week)
        if injuries_df.empty:
            print("    No Bronze injury data found — skipping")
            continue

        print(f"    Injury rows: {len(injuries_df)}")

        # Compute the "with injury" baseline
        # Case B: Gold files without prior injury columns; apply_injury_adjustments
        # is the reference point. Compare it to the raw Gold file.
        refreshed = apply_injury_adjustments(gold_df.copy(), injuries_df)

        if "injury_multiplier" not in refreshed.columns:
            print("    Could not apply injury adjustments — skipping")
            continue

        # Count how many players changed and in what direction
        changed_mask = refreshed["injury_multiplier"] < 1.0
        n_changed = int(changed_mask.sum())
        pts_before = gold_df["projected_points"].sum()
        pts_after = refreshed["projected_points"].sum()
        delta = pts_after - pts_before

        # Break down by direction
        zeroed = (refreshed["injury_multiplier"] == 0.0).sum()
        reduced = ((refreshed["injury_multiplier"] > 0.0) & changed_mask).sum()

        print(f"    Players affected by injury: {n_changed}")
        print(f"      - Zeroed (Out/IR):         {zeroed}")
        print(f"      - Reduced (Q/Doubtful):    {reduced}")
        print(
            f"    Aggregate projected pts:   {pts_before:.1f} → {pts_after:.1f} "
            f"(delta {delta:+.1f})"
        )

        # Position breakdown
        if "position" in refreshed.columns:
            pos_impact = (
                refreshed[changed_mask]
                .groupby("position")
                .agg(
                    n_affected=("player_name", "count"),
                    pts_lost=("projected_points", "sum"),
                )
                .reset_index()
            )
            if not pos_impact.empty:
                print("    By position:")
                for _, row in pos_impact.iterrows():
                    pts_before_pos = gold_df[
                        gold_df["position"] == row["position"]
                    ]["projected_points"].sum()
                    print(
                        f"      {row['position']}: {int(row['n_affected'])} players, "
                        f"pts now {row['pts_lost']:.1f} vs before {pts_before_pos:.1f}"
                    )

    print()
    print("Probe complete — no Gold files were written.")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point for the Sunday projection refresh.

    Returns:
        0 on success or fail-open exit, 1 on unexpected error.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Sunday Projection Refresh — re-applies fresh injury status to "
            "published Gold projections without re-running the model."
        )
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="NFL season year (default: auto-detected from calendar)",
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="NFL week number 1-18 (default: auto-detected from calendar)",
    )
    parser.add_argument(
        "--scoring",
        choices=SCORING_FORMATS + ["all"],
        default="all",
        help=(
            "Scoring format to refresh.  Use 'all' to refresh all three "
            "formats (default: all)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Load and compute the refresh but do NOT write any output files. "
            "Useful for local testing without polluting the Gold partition."
        ),
    )
    parser.add_argument(
        "--backtest-probe",
        action="store_true",
        default=False,
        help=(
            "Run a cheap backtest probe over --season / --weeks to measure "
            "how many players' projections would change.  Writes no output."
        ),
    )
    parser.add_argument(
        "--weeks",
        type=int,
        nargs="+",
        default=None,
        help="Week list for --backtest-probe (e.g. 10 11 12)",
    )

    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Backtest probe mode — separate code path
    # -----------------------------------------------------------------------
    if args.backtest_probe:
        season = args.season or 2024
        weeks = args.weeks or [10, 11, 12]
        run_backtest_probe(season=season, weeks=weeks)
        return 0

    # -----------------------------------------------------------------------
    # Auto-detect season / week if not supplied
    # -----------------------------------------------------------------------
    if args.season is None or args.week is None:
        auto_season, auto_week = detect_nfl_week()
        season = args.season if args.season is not None else auto_season
        week = args.week if args.week is not None else auto_week
        logger.info(
            "Auto-detected: season=%d week=%d (overrides: season=%s week=%s)",
            auto_season,
            auto_week,
            args.season,
            args.week,
        )
    else:
        season, week = args.season, args.week

    logger.info(
        "Sunday refresh: season=%d week=%d scoring=%s dry_run=%s",
        season,
        week,
        args.scoring,
        args.dry_run,
    )

    # -----------------------------------------------------------------------
    # Determine which scoring formats to process
    # -----------------------------------------------------------------------
    formats_to_run = SCORING_FORMATS if args.scoring == "all" else [args.scoring]

    # -----------------------------------------------------------------------
    # Fetch fresh injury data once (shared across all scoring formats)
    # -----------------------------------------------------------------------
    logger.info("Fetching fresh injury data for season=%d week=%d ...", season, week)
    injuries_df = _get_fresh_injuries(season, week)

    if injuries_df.empty:
        logger.info(
            "No fresh injury data available for season=%d week=%d. "
            "This is expected in preseason or the first days of a new week "
            "before the official report is published. Exiting with 0.",
            season,
            week,
        )
        print(
            f"[sunday-refresh] No injury data for season={season} week={week}. "
            "Nothing to do — exiting cleanly."
        )
        return 0

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    any_refreshed = False

    for scoring in formats_to_run:
        logger.info("Processing scoring format: %s", scoring)

        # Load latest Gold projection
        gold_df, source_path = _load_latest_gold_projections(season, week, scoring)
        if gold_df.empty:
            logger.info(
                "No Gold projections for scoring=%s; skipping (fail-open)", scoring
            )
            print(
                f"[sunday-refresh] No Gold file found for scoring={scoring} — "
                "skipping this format."
            )
            continue

        # Undo old multipliers and re-apply fresh ones
        refreshed, summary = _undo_and_reapply(gold_df, injuries_df)

        # Write output
        output_path = None
        if not args.dry_run:
            output_path = _write_gold_output(refreshed, season, week, scoring, ts)
            any_refreshed = True

        _write_refresh_summary(
            season=season,
            week=week,
            scoring=scoring,
            source_file=source_path,
            output_file=output_path,
            summary=summary,
            refreshed=refreshed,
            injuries_df=injuries_df,
            dry_run=args.dry_run,
        )

    if not any_refreshed and not args.dry_run:
        logger.info(
            "No formats were refreshed (no Gold files found). "
            "This is fail-open — the Tuesday projections remain authoritative."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
