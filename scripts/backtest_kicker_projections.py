#!/usr/bin/env python3
"""
Kicker Projection Backtesting Framework

Compares kicker projections against actual fantasy points computed from PBP
data for historical weeks to measure accuracy and identify systematic biases.

Usage:
    python scripts/backtest_kicker_projections.py --seasons 2022,2023,2024
    python scripts/backtest_kicker_projections.py --seasons 2024 --weeks 3-18
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicker_analytics import (
    compute_kicker_stats,
    compute_team_kicker_features,
    compute_opponent_kicker_features,
    KICKER_SCORING,
)
from kicker_projection import generate_kicker_projections

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_weeks(weeks_str: str) -> List[int]:
    """Parse '3-18' or '3,5,10' into a list of ints."""
    if "-" in weeks_str:
        start, end = weeks_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(w) for w in weeks_str.split(",")]


def _load_local_parquet(base_dir: str, pattern: str) -> pd.DataFrame:
    """Load latest parquet from local data directory."""
    import glob as globmod

    files = sorted(globmod.glob(os.path.join(base_dir, pattern)))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def compute_actual_kicker_points(
    pbp_df: pd.DataFrame, season: int, week: int
) -> pd.DataFrame:
    """Compute actual kicker fantasy points from PBP for a specific week.

    Scoring: FG made = 3, FG 50+ made = 5 (replaces base 3), XP made = 1,
             FG missed = -1, XP missed = -1.

    Args:
        pbp_df: Play-by-play DataFrame.
        season: NFL season.
        week: NFL week.

    Returns:
        DataFrame with kicker_player_id, kicker_player_name, team,
        actual_points, fg_made, fg_made_long, xp_made, fg_missed, xp_missed.
    """
    # Use kicker_analytics.compute_kicker_stats which already computes fantasy_points
    stats = compute_kicker_stats(pbp_df, season=season, week=week)
    if stats.empty:
        return pd.DataFrame()

    result = stats[
        [
            "kicker_player_id",
            "kicker_player_name",
            "team",
            "season",
            "week",
            "fg_att",
            "fg_made",
            "fg_made_long",
            "xp_att",
            "xp_made",
            "fantasy_points",
        ]
    ].copy()
    result = result.rename(columns={"fantasy_points": "actual_points"})
    return result


def run_kicker_backtest(
    seasons: List[int],
    weeks: Optional[List[int]],
) -> pd.DataFrame:
    """Run kicker backtesting across specified seasons and weeks.

    For each week, loads PBP data available up to that point, computes
    kicker features, generates projections, and compares to actuals.

    Args:
        seasons: List of seasons to backtest.
        weeks: Optional list of weeks. Defaults to 3-18.

    Returns:
        DataFrame with projected and actual points per kicker per week.
    """
    project_root = os.path.join(os.path.dirname(__file__), "..")
    bronze_dir = os.path.join(project_root, "data", "bronze")

    # Load PBP for all needed seasons (include prior season for early weeks)
    all_seasons = sorted(set(seasons + [s - 1 for s in seasons]))
    print(f"Loading PBP data for seasons: {all_seasons}")

    pbp_dfs: List[pd.DataFrame] = []
    for s in all_seasons:
        local = _load_local_parquet(bronze_dir, f"pbp/season={s}/*.parquet")
        if not local.empty:
            pbp_dfs.append(local)

    if not pbp_dfs:
        print("ERROR: No PBP data found locally.")
        return pd.DataFrame()

    pbp_df = pd.concat(pbp_dfs, ignore_index=True)
    print(f"Loaded {len(pbp_df):,} PBP rows")

    # Load schedules
    sched_dfs: List[pd.DataFrame] = []
    for s in all_seasons:
        local = _load_local_parquet(bronze_dir, f"games/season={s}/*.parquet")
        if local.empty:
            local = _load_local_parquet(bronze_dir, f"schedules/season={s}/*.parquet")
        if not local.empty:
            if "season" not in local.columns:
                local["season"] = s
            sched_dfs.append(local)

    schedules_df = (
        pd.concat(sched_dfs, ignore_index=True) if sched_dfs else pd.DataFrame()
    )
    if not schedules_df.empty:
        print(f"Loaded {len(schedules_df):,} schedule rows")

    results: List[pd.DataFrame] = []
    total_weeks = 0

    for season in seasons:
        season_weeks = weeks or list(range(3, 19))

        # Precompute all kicker stats for the season (all weeks)
        season_kicker_stats = compute_kicker_stats(pbp_df, season=season)
        if season_kicker_stats.empty:
            print(f"  WARNING: No kicker stats for season {season}")
            continue

        print(f"\n  Season {season}: {len(season_kicker_stats)} kicker-week records")

        for week in season_weeks:
            print(f"    Backtesting {season} Week {week}...", end=" ", flush=True)

            # --- Compute actuals for this week ---
            actuals = compute_actual_kicker_points(pbp_df, season, week)
            if actuals.empty:
                print("SKIP (no actual kicker data)")
                continue

            # --- Build features using only data available before this week ---
            # Filter PBP to prior weeks only for feature computation
            prior_pbp = pbp_df[
                (pbp_df["season"] < season)
                | ((pbp_df["season"] == season) & (pbp_df["week"] < week))
            ].copy()

            if prior_pbp.empty:
                print("SKIP (no prior PBP data)")
                continue

            # Kicker stats from prior weeks only
            prior_kicker_stats = compute_kicker_stats(prior_pbp, season=season)
            if prior_kicker_stats.empty:
                # Try prior season as fallback for early weeks
                prior_kicker_stats = compute_kicker_stats(prior_pbp, season=season - 1)
                if prior_kicker_stats.empty:
                    print("SKIP (insufficient kicker history)")
                    continue

            # Team and opponent features (these use rolling + shift internally)
            team_features = compute_team_kicker_features(
                prior_pbp, schedules_df, season
            )
            opp_features = compute_opponent_kicker_features(
                prior_pbp, schedules_df, season
            )

            # Filter schedule to this season
            season_sched = (
                schedules_df[schedules_df["season"] == season]
                if not schedules_df.empty and "season" in schedules_df.columns
                else pd.DataFrame()
            )

            # --- Generate projections ---
            try:
                projections = generate_kicker_projections(
                    kicker_stats_df=prior_kicker_stats,
                    team_features_df=team_features,
                    opp_features_df=opp_features,
                    schedules_df=season_sched,
                    season=season,
                    week=week,
                )
            except Exception as e:
                print(f"FAIL ({e})")
                continue

            if projections.empty:
                print("SKIP (no projections)")
                continue

            # --- Merge projected vs actual ---
            merged = projections.merge(
                actuals[["kicker_player_id", "kicker_player_name", "actual_points"]],
                left_on="player_id",
                right_on="kicker_player_id",
                how="inner",
                suffixes=("_proj", "_actual"),
            )

            if merged.empty:
                # Try name-based merge as fallback
                merged = projections.merge(
                    actuals[["kicker_player_name", "actual_points"]],
                    left_on="player_name",
                    right_on="kicker_player_name",
                    how="inner",
                    suffixes=("_proj", "_actual"),
                )

            if merged.empty:
                print("SKIP (no matches)")
                continue

            # Clean up duplicate columns
            for col in ["kicker_player_id", "kicker_player_name"]:
                if col in merged.columns and col not in ["player_id", "player_name"]:
                    merged.drop(columns=[col], errors="ignore", inplace=True)

            merged["error"] = merged["projected_points"] - merged["actual_points"]
            merged["abs_error"] = merged["error"].abs()
            results.append(merged)
            total_weeks += 1
            print(f"OK ({len(merged)} kickers)")

    if not results:
        return pd.DataFrame()

    print(f"\nBacktest complete: {total_weeks} weeks processed")
    return pd.concat(results, ignore_index=True)


def compute_naive_baseline(results_df: pd.DataFrame) -> Dict[str, float]:
    """Compute naive baseline metrics for comparison.

    Baselines:
        1. Flat 8.0 points (approximate league average kicker score)
        2. Rolling 3-game average from each kicker's prior weeks

    Args:
        results_df: Backtest results with actual_points column.

    Returns:
        Dict with baseline MAE and RMSE for each method.
    """
    actuals = results_df["actual_points"]

    # Baseline 1: Flat 8.0
    flat_errors = (8.0 - actuals).abs()
    flat_mae = flat_errors.mean()
    flat_rmse = float(np.sqrt(((8.0 - actuals) ** 2).mean()))

    return {
        "flat_8_mae": float(flat_mae),
        "flat_8_rmse": flat_rmse,
    }


def print_summary(results_df: pd.DataFrame) -> None:
    """Print kicker backtesting summary statistics.

    Args:
        results_df: Merged DataFrame with projected_points, actual_points,
            error, abs_error columns.
    """
    if results_df.empty:
        print("No results to summarize.")
        return

    print(f"\n{'=' * 70}")
    print("KICKER BACKTEST RESULTS")
    print(f"{'=' * 70}")

    # Overall metrics
    mae = results_df["abs_error"].mean()
    rmse = float(np.sqrt((results_df["error"] ** 2).mean()))
    corr = float(results_df[["projected_points", "actual_points"]].corr().iloc[0, 1])
    bias = results_df["error"].mean()
    n_kickers = len(results_df)
    n_weeks = results_df[["season", "week"]].drop_duplicates().shape[0]
    n_unique_kickers = results_df["player_name"].nunique()

    print(
        f"\nOverall ({n_kickers:,} kicker-weeks across {n_weeks} weeks, "
        f"{n_unique_kickers} unique kickers):"
    )
    print(f"  MAE:         {mae:.2f} pts")
    print(f"  RMSE:        {rmse:.2f} pts")
    print(f"  Correlation: {corr:.3f}")
    print(
        f"  Avg Bias:    {bias:+.2f} pts "
        f"{'(over-projects)' if bias > 0 else '(under-projects)'}"
    )

    # --- Naive baseline comparison ---
    baselines = compute_naive_baseline(results_df)
    print(f"\nBaseline Comparison:")
    print(f"  {'Method':<25} {'MAE':>8} {'RMSE':>8}")
    print(f"  {'-' * 43}")
    print(f"  {'Kicker Model':<25} {mae:>8.2f} {rmse:>8.2f}")
    print(
        f"  {'Flat 8.0 pts':<25} {baselines['flat_8_mae']:>8.2f} "
        f"{baselines['flat_8_rmse']:>8.2f}"
    )

    model_vs_flat = mae - baselines["flat_8_mae"]
    print(
        f"\n  Model vs Flat baseline: {model_vs_flat:+.2f} MAE "
        f"({'better' if model_vs_flat < 0 else 'worse'})"
    )

    # --- Error distribution ---
    print(f"\nError Distribution:")
    within_1 = (results_df["abs_error"] <= 1.0).mean() * 100
    within_3 = (results_df["abs_error"] <= 3.0).mean() * 100
    within_5 = (results_df["abs_error"] <= 5.0).mean() * 100
    within_7 = (results_df["abs_error"] <= 7.0).mean() * 100
    print(f"  Within 1 pt:  {within_1:.1f}%")
    print(f"  Within 3 pts: {within_3:.1f}%")
    print(f"  Within 5 pts: {within_5:.1f}%")
    print(f"  Within 7 pts: {within_7:.1f}%")

    # --- Per-season breakdown ---
    print(f"\nPer-Season Breakdown:")
    print(
        f"  {'Season':<10} {'MAE':>8} {'RMSE':>8} {'Corr':>8} {'Bias':>8} "
        f"{'Count':>8}"
    )
    print(f"  {'-' * 50}")
    for season in sorted(results_df["season"].unique()):
        s_data = results_df[results_df["season"] == season]
        s_mae = s_data["abs_error"].mean()
        s_rmse = float(np.sqrt((s_data["error"] ** 2).mean()))
        s_corr = float(s_data[["projected_points", "actual_points"]].corr().iloc[0, 1])
        s_bias = s_data["error"].mean()
        print(
            f"  {season:<10} {s_mae:>8.2f} {s_rmse:>8.2f} {s_corr:>8.3f} "
            f"{s_bias:>+8.2f} {len(s_data):>8,}"
        )

    # --- Best/worst predicted kickers (by average abs error, min 5 appearances) ---
    kicker_summary = (
        results_df.groupby("player_name")
        .agg(
            avg_abs_error=("abs_error", "mean"),
            avg_projected=("projected_points", "mean"),
            avg_actual=("actual_points", "mean"),
            appearances=("abs_error", "count"),
        )
        .reset_index()
    )
    frequent = kicker_summary[kicker_summary["appearances"] >= 5]

    if not frequent.empty:
        print(f"\nBest Predicted Kickers (min 5 appearances):")
        best = frequent.nsmallest(10, "avg_abs_error")
        for _, row in best.iterrows():
            print(
                f"  {row['player_name']:<22} MAE: {row['avg_abs_error']:.2f}  "
                f"Avg Proj: {row['avg_projected']:.1f}  "
                f"Avg Actual: {row['avg_actual']:.1f}  "
                f"({int(row['appearances'])} wks)"
            )

        print(f"\nWorst Predicted Kickers (min 5 appearances):")
        worst = frequent.nlargest(10, "avg_abs_error")
        for _, row in worst.iterrows():
            print(
                f"  {row['player_name']:<22} MAE: {row['avg_abs_error']:.2f}  "
                f"Avg Proj: {row['avg_projected']:.1f}  "
                f"Avg Actual: {row['avg_actual']:.1f}  "
                f"({int(row['appearances'])} wks)"
            )

    # --- Top 10 biggest individual misses ---
    print(f"\nTop 10 Biggest Misses:")
    top_misses = results_df.nlargest(10, "abs_error")
    for _, row in top_misses.iterrows():
        name = str(row.get("player_name", "Unknown"))[:22]
        print(
            f"  {name:<24} S{int(row['season'])} W{int(row['week']):>2}  "
            f"Proj: {row['projected_points']:>6.1f}  "
            f"Actual: {row['actual_points']:>6.1f}  "
            f"Error: {row['error']:>+7.1f}"
        )


def main() -> int:
    """Run the kicker backtesting CLI."""
    parser = argparse.ArgumentParser(
        description="Backtest NFL Kicker Fantasy Projections"
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default="2022,2023,2024",
        help="Comma-separated seasons to backtest (default: 2022,2023,2024)",
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default=None,
        help='Week range: "3-18" or "3,5,10" (default: 3-18)',
    )
    parser.add_argument(
        "--output-dir",
        default="output/backtest",
        help="Output directory for results CSV",
    )
    args = parser.parse_args()

    seasons = [int(s) for s in args.seasons.split(",")]
    weeks = parse_weeks(args.weeks) if args.weeks else None

    print("\nNFL Kicker Projection Backtester")
    print(f"Seasons: {seasons}")
    if weeks:
        print(f"Weeks: {weeks}")
    print(f"Scoring: FG=3, FG 50+=5, XP=1, miss=-1")
    print("=" * 60)

    results = run_kicker_backtest(seasons, weeks)

    if results.empty:
        print("\nERROR: No backtest results generated.")
        return 1

    print_summary(results)

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(args.output_dir, f"backtest_kicker_{ts}.csv")
    results.to_csv(csv_path, index=False)
    print(f"\nDetailed results saved to: {csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
