#!/usr/bin/env python3
"""
Projection Backtesting Framework

Compares model projections against actual fantasy points for historical
weeks to measure accuracy and identify systematic biases.

Usage:
    python scripts/backtest_projections.py --seasons 2023,2024 --scoring half_ppr
    python scripts/backtest_projections.py --seasons 2024 --weeks 1-10
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nfl_data_integration import NFLDataFetcher
from scoring_calculator import calculate_fantasy_points_df, list_scoring_formats
from player_analytics import (
    compute_usage_metrics,
    compute_rolling_averages,
    compute_opponent_rankings,
    compute_implied_team_totals,
)
from projection_engine import generate_weekly_projections

try:
    from ml_projection_router import generate_ml_projections

    HAS_ML_ROUTER = True
except ImportError:
    HAS_ML_ROUTER = False


logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_weeks(weeks_str: str) -> List[int]:
    """Parse '1-10' or '1,5,10' into a list of ints."""
    if "-" in weeks_str:
        start, end = weeks_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(w) for w in weeks_str.split(",")]


def compute_actuals(
    weekly_df: pd.DataFrame, season: int, week: int, scoring_format: str
) -> pd.DataFrame:
    """Compute actual fantasy points for a specific week."""
    week_data = weekly_df[
        (weekly_df["season"] == season) & (weekly_df["week"] == week)
    ].copy()
    if week_data.empty:
        return pd.DataFrame()

    week_data = calculate_fantasy_points_df(
        week_data, scoring_format=scoring_format, output_col="actual_points"
    )

    id_col = "player_id" if "player_id" in week_data.columns else "player_name"
    keep = [id_col, "player_name", "position", "recent_team", "actual_points"]
    keep = [c for c in keep if c in week_data.columns]
    return week_data[keep]


def build_silver_features(
    weekly_df: pd.DataFrame, season: int, up_to_week: int
) -> pd.DataFrame:
    """Build Silver-layer features using only data available up to a given week."""
    hist = weekly_df[
        (weekly_df["season"] == season) & (weekly_df["week"] < up_to_week)
    ].copy()
    if hist.empty or len(hist) < 5:
        # Need some history; try including prior season
        prior = weekly_df[weekly_df["season"] == season - 1].copy()
        hist = pd.concat([prior, hist], ignore_index=True)

    if hist.empty:
        return pd.DataFrame()

    try:
        usage = compute_usage_metrics(hist)
        rolling = compute_rolling_averages(usage)
        return rolling
    except Exception as e:
        logger.debug(
            "Feature build failed for season=%d week<%d: %s", season, up_to_week, e
        )
        return pd.DataFrame()


def _load_local_parquet(base_dir: str, pattern: str) -> pd.DataFrame:
    """Load latest parquet from local data directory."""
    import glob as globmod

    files = sorted(globmod.glob(os.path.join(base_dir, pattern)))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _prepare_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure air_yards column exists for analytics functions."""
    if "air_yards" not in df.columns:
        if "receiving_air_yards" in df.columns:
            df = df.copy()
            df["air_yards"] = df["receiving_air_yards"].fillna(0)
    return df


def _compute_week_implied_totals(
    schedules_df: pd.DataFrame, week: int
) -> Optional[Dict]:
    """Compute per-team implied scoring totals from schedule lines for a week."""
    required = {"week", "home_team", "away_team", "total_line", "spread_line"}
    if schedules_df.empty or not required.issubset(schedules_df.columns):
        return None

    games = schedules_df[schedules_df["week"] == week].dropna(
        subset=["total_line", "spread_line"]
    )
    if games.empty:
        return None

    implied: Dict[str, float] = {}
    for _, row in games.iterrows():
        total = float(row["total_line"])
        spread = float(row["spread_line"])
        implied[row["home_team"]] = round((total - spread) / 2, 2)
        implied[row["away_team"]] = round((total + spread) / 2, 2)

    return implied


def run_backtest(
    seasons: List[int],
    weeks: Optional[List[int]],
    scoring_format: str,
    use_ml: bool = False,
    apply_constraints: bool = False,
) -> pd.DataFrame:
    """Run backtesting across specified seasons and weeks."""
    fetcher = NFLDataFetcher()
    project_root = os.path.join(os.path.dirname(__file__), "..")
    bronze_dir = os.path.join(project_root, "data", "bronze")

    # Fetch all weekly data upfront — try local Bronze first
    all_seasons = list(set(seasons + [s - 1 for s in seasons]))
    print(f"Loading weekly data for seasons: {all_seasons}")

    dfs = []
    for s in sorted(all_seasons):
        local = _load_local_parquet(bronze_dir, f"players/weekly/season={s}/*.parquet")
        if not local.empty:
            dfs.append(local)
    if dfs:
        weekly_df = pd.concat(dfs, ignore_index=True)
        print(f"Loaded {len(weekly_df):,} weekly rows from local Bronze")
    else:
        weekly_df = fetcher.fetch_player_weekly(all_seasons)
        print(f"Loaded {len(weekly_df):,} weekly rows from nfl-data-py")

    weekly_df = _prepare_weekly(weekly_df)

    # Load schedules for opponent rankings (and implied totals if --constrain)
    sched_dfs = []
    for s in sorted(all_seasons):
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
        if apply_constraints:
            has_lines = {"total_line", "spread_line"}.issubset(schedules_df.columns)
            print(f"  Constraints enabled — Vegas lines available: {has_lines}")

    results = []
    total_weeks = 0

    for season in seasons:
        season_weeks = weeks or list(
            range(3, 19)
        )  # Start week 3 (need 2 weeks of history)

        for week in season_weeks:
            print(f"  Backtesting {season} Week {week}...", end=" ", flush=True)

            # Build features from data available before this week
            silver_df = build_silver_features(weekly_df, season, up_to_week=week)
            if silver_df.empty:
                print("SKIP (insufficient history)")
                continue

            # Build opponent rankings
            try:
                opp_rankings = compute_opponent_rankings(weekly_df, schedules_df)
            except Exception:
                opp_rankings = pd.DataFrame()

            # Compute implied totals for constraints (if enabled)
            implied_totals = None
            sched_for_week = None
            if apply_constraints and not schedules_df.empty:
                week_sched = (
                    schedules_df[
                        schedules_df.get("season", pd.Series(dtype=int)).eq(season)
                    ]
                    if "season" in schedules_df.columns
                    else schedules_df
                )
                implied_totals = _compute_week_implied_totals(week_sched, week)
                if implied_totals:
                    sched_for_week = week_sched

            # Generate projections
            try:
                if use_ml and HAS_ML_ROUTER:
                    projections = generate_ml_projections(
                        silver_df,
                        opp_rankings,
                        season=season,
                        week=week,
                        scoring_format=scoring_format,
                        schedules_df=(
                            sched_for_week
                            if sched_for_week is not None
                            else (schedules_df if not schedules_df.empty else None)
                        ),
                        implied_totals=implied_totals,
                        apply_constraints=apply_constraints,
                    )
                else:
                    projections = generate_weekly_projections(
                        silver_df,
                        opp_rankings,
                        season=season,
                        week=week,
                        scoring_format=scoring_format,
                        schedules_df=(
                            sched_for_week
                            if sched_for_week is not None
                            else (schedules_df if not schedules_df.empty else None)
                        ),
                        implied_totals=implied_totals,
                        apply_constraints=apply_constraints,
                    )
            except Exception as e:
                print(f"FAIL ({e})")
                continue

            if projections.empty:
                print("SKIP (no projections)")
                continue

            # Compute actuals
            actuals = compute_actuals(weekly_df, season, week, scoring_format)
            if actuals.empty:
                print("SKIP (no actuals)")
                continue

            # Merge projected vs actual
            id_col = "player_name"
            merged = projections.merge(
                actuals[[id_col, "actual_points"]],
                on=id_col,
                how="inner",
            )
            if merged.empty:
                print("SKIP (no matches)")
                continue

            merged["season"] = season
            merged["week"] = week
            merged["error"] = merged["projected_points"] - merged["actual_points"]
            merged["abs_error"] = merged["error"].abs()
            results.append(merged)
            total_weeks += 1
            print(f"OK ({len(merged)} players)")

    if not results:
        return pd.DataFrame()

    print(f"\nBacktest complete: {total_weeks} weeks processed")
    return pd.concat(results, ignore_index=True)


def print_summary(results_df: pd.DataFrame, scoring_format: str):
    """Print backtesting summary statistics."""
    if results_df.empty:
        print("No results to summarize.")
        return

    print(f"\n{'=' * 70}")
    print(f"BACKTEST RESULTS — {scoring_format.upper()}")
    print(f"{'=' * 70}")

    # Overall metrics
    mae = results_df["abs_error"].mean()
    rmse = np.sqrt((results_df["error"] ** 2).mean())
    corr = results_df[["projected_points", "actual_points"]].corr().iloc[0, 1]
    bias = results_df["error"].mean()
    n_players = len(results_df)
    n_weeks = results_df[["season", "week"]].drop_duplicates().shape[0]

    print(f"\nOverall ({n_players:,} player-weeks across {n_weeks} weeks):")
    print(f"  MAE:         {mae:.2f} pts")
    print(f"  RMSE:        {rmse:.2f} pts")
    print(f"  Correlation: {corr:.3f}")
    print(
        f"  Avg Bias:    {bias:+.2f} pts {'(over-projects)' if bias > 0 else '(under-projects)'}"
    )

    # Per-position breakdown
    print(f"\nPer-Position Breakdown:")
    print(
        f"  {'Position':<10} {'MAE':>8} {'RMSE':>8} {'Corr':>8} {'Bias':>8} {'Count':>8}"
    )
    print(f"  {'-' * 50}")

    for pos in ["QB", "RB", "WR", "TE"]:
        pos_data = results_df[results_df["position"] == pos]
        if pos_data.empty:
            continue
        p_mae = pos_data["abs_error"].mean()
        p_rmse = np.sqrt((pos_data["error"] ** 2).mean())
        p_corr = pos_data[["projected_points", "actual_points"]].corr().iloc[0, 1]
        p_bias = pos_data["error"].mean()
        print(
            f"  {pos:<10} {p_mae:>8.2f} {p_rmse:>8.2f} {p_corr:>8.3f} {p_bias:>+8.2f} {len(pos_data):>8,}"
        )

    # ML vs heuristic breakdown (if projection_source column exists)
    if "projection_source" in results_df.columns:
        print(f"\nBy Projection Source:")
        print(f"  {'Source':<12} {'MAE':>8} {'RMSE':>8} {'Bias':>8} {'Count':>8}")
        print(f"  {'-' * 44}")
        for src in sorted(results_df["projection_source"].unique()):
            src_data = results_df[results_df["projection_source"] == src]
            s_mae = src_data["abs_error"].mean()
            s_rmse = np.sqrt((src_data["error"] ** 2).mean())
            s_bias = src_data["error"].mean()
            print(
                f"  {src:<12} {s_mae:>8.2f} {s_rmse:>8.2f} {s_bias:>+8.2f} {len(src_data):>8,}"
            )

    # Biggest misses
    print(f"\nTop 10 Biggest Misses:")
    top_misses = results_df.nlargest(10, "abs_error")
    for _, row in top_misses.iterrows():
        name = row.get("player_name", "Unknown")[:20]
        print(
            f"  {name:<22} {row['position']:<4} S{int(row['season'])} W{int(row['week']):>2}  "
            f"Proj: {row['projected_points']:>6.1f}  Actual: {row['actual_points']:>6.1f}  "
            f"Error: {row['error']:>+7.1f}"
        )


def main():
    formats = list_scoring_formats()
    parser = argparse.ArgumentParser(description="Backtest NFL Fantasy Projections")
    parser.add_argument(
        "--seasons",
        type=str,
        default="2023,2024",
        help="Comma-separated seasons to backtest (default: 2023,2024)",
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default=None,
        help='Week range: "3-18" or "1,5,10" (default: 3-18)',
    )
    parser.add_argument(
        "--scoring",
        choices=formats,
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--ml",
        action="store_true",
        help="Use ML router: QB/RB via XGB, WR/TE via hybrid residual",
    )
    parser.add_argument(
        "--constrain",
        action="store_true",
        help="Apply team-level constraints so player totals align with implied team totals",
    )
    parser.add_argument(
        "--output-dir",
        default="output/backtest",
        help="Output directory for results CSV",
    )
    args = parser.parse_args()

    seasons = [int(s) for s in args.seasons.split(",")]
    weeks = parse_weeks(args.weeks) if args.weeks else None

    print(f"\nNFL Fantasy Projection Backtester")
    mode = "ML (QB/RB→XGB, WR/TE→Hybrid Residual)" if args.ml else "Heuristic"
    constrain_label = " | Constraints: ON" if args.constrain else ""
    print(
        f"Seasons: {seasons} | Scoring: {args.scoring.upper()} | Mode: {mode}{constrain_label}"
    )
    if args.ml and not HAS_ML_ROUTER:
        print(
            "WARNING: --ml flag set but ml_projection_router not available; using heuristic"
        )
    if weeks:
        print(f"Weeks: {weeks}")
    print("=" * 60)

    results = run_backtest(
        seasons, weeks, args.scoring, use_ml=args.ml, apply_constraints=args.constrain
    )

    if results.empty:
        print("\nERROR: No backtest results generated.")
        return 1

    print_summary(results, args.scoring)

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ml_tag = "_ml" if args.ml else ""
    constrain_tag = "_constrained" if args.constrain else ""
    csv_path = os.path.join(
        args.output_dir, f"backtest_{args.scoring}{ml_tag}{constrain_tag}_{ts}.csv"
    )
    results.to_csv(csv_path, index=False)
    print(f"\nDetailed results saved to: {csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
