#!/usr/bin/env python3
"""
Enhanced Projection Backtest

Runs the standard backtest with projection enhancements (injury recovery,
regression to mean) and compares against the baseline.

Usage:
    python scripts/backtest_enhanced.py --seasons 2022,2023,2024 --scoring half_ppr
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

from projection_enhancements import run_enhanced_backtest

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def print_summary(results_df: pd.DataFrame, scoring_format: str, label: str = ""):
    """Print backtesting summary statistics."""
    if results_df.empty:
        print("No results to summarize.")
        return

    tag = f" ({label})" if label else ""
    print(f"\n{'=' * 70}")
    print(f"BACKTEST RESULTS{tag} -- {scoring_format.upper()}")
    print(f"{'=' * 70}")

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
    parser = argparse.ArgumentParser(
        description="Enhanced NFL Fantasy Projection Backtester"
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default="2022,2023,2024",
        help="Comma-separated seasons (default: 2022,2023,2024)",
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default=None,
        help='Week range: "3-18" or "1,5,10" (default: 3-18)',
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--no-injury-recovery",
        action="store_true",
        help="Disable injury recovery model",
    )
    parser.add_argument(
        "--no-regression",
        action="store_true",
        help="Disable regression to mean",
    )
    args = parser.parse_args()

    seasons = [int(s) for s in args.seasons.split(",")]
    weeks = None
    if args.weeks:
        if "-" in args.weeks:
            start, end = args.weeks.split("-", 1)
            weeks = list(range(int(start), int(end) + 1))
        else:
            weeks = [int(w) for w in args.weeks.split(",")]

    print(f"\nEnhanced NFL Fantasy Projection Backtester")
    print(
        f"Seasons: {seasons} | Scoring: {args.scoring.upper()}"
    )
    features = []
    if not args.no_injury_recovery:
        features.append("Injury Recovery")
    if not args.no_regression:
        features.append("Regression-to-Mean")
    print(f"Enhancements: {', '.join(features) if features else 'NONE'}")
    print("=" * 60)

    results = run_enhanced_backtest(
        seasons,
        weeks,
        args.scoring,
        use_injury_recovery=not args.no_injury_recovery,
        use_regression=not args.no_regression,
    )

    if results.empty:
        print("\nERROR: No backtest results generated.")
        return 1

    print_summary(results, args.scoring, label="ENHANCED")

    # Save results
    os.makedirs("output/backtest", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"output/backtest/backtest_enhanced_{args.scoring}_{ts}.csv"
    results.to_csv(csv_path, index=False)
    print(f"\nDetailed results saved to: {csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
