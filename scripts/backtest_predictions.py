#!/usr/bin/env python3
"""Backtest NFL game prediction models against historical Vegas closing lines.

Loads trained XGBoost spread and/or total models, generates predictions for
historical games, and evaluates ATS accuracy, O/U accuracy, vig-adjusted
profit/loss, and ROI.

Usage:
    python scripts/backtest_predictions.py --target both
    python scripts/backtest_predictions.py --target spread --seasons 2022 2023 2024
    python scripts/backtest_predictions.py --target total --model-dir models/
"""

import argparse
import logging
import os
import sys
from typing import List, Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feature_engineering import assemble_multiyear_features, get_feature_columns
from model_training import load_model
from prediction_backtester import (
    BREAK_EVEN_PCT,
    compute_profit,
    evaluate_ats,
    evaluate_ou,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def print_ats_report(results: pd.DataFrame, label: str = "Overall") -> None:
    """Print formatted ATS backtest report.

    Args:
        results: DataFrame with ATS evaluation columns from evaluate_ats().
        label: Report section label (e.g., 'Overall', '2024 Holdout').
    """
    n_games = len(results)
    profit_stats = compute_profit(results, correct_col="ats_correct", push_col="push")

    non_push = results[~results["push"]]
    accuracy = non_push["ats_correct"].mean() if len(non_push) > 0 else 0.0

    print(f"\n{'=' * 60}")
    print(f"ATS RESULTS -- {label} ({n_games} games)")
    print(f"{'=' * 60}")
    print(f"  Record:       {profit_stats['wins']}-{profit_stats['losses']}-{profit_stats['pushes']} (W-L-P)")
    print(f"  ATS Accuracy: {accuracy:.1%}")
    print(f"  Break-even:   {BREAK_EVEN_PCT:.2%} (-110 vig)")
    print(f"  Profit:       {profit_stats['profit']:+.2f} units (flat $100 bets)")
    print(f"  ROI:          {profit_stats['roi']:+.2f}%")


def print_ou_report(results: pd.DataFrame, label: str = "Overall") -> None:
    """Print formatted O/U backtest report.

    Args:
        results: DataFrame with O/U evaluation columns from evaluate_ou().
        label: Report section label.
    """
    n_games = len(results)
    profit_stats = compute_profit(results, correct_col="ou_correct", push_col="push_ou")

    non_push = results[~results["push_ou"]]
    accuracy = non_push["ou_correct"].mean() if len(non_push) > 0 else 0.0

    print(f"\n{'=' * 60}")
    print(f"O/U RESULTS -- {label} ({n_games} games)")
    print(f"{'=' * 60}")
    print(f"  Record:       {profit_stats['wins']}-{profit_stats['losses']}-{profit_stats['pushes']} (W-L-P)")
    print(f"  O/U Accuracy: {accuracy:.1%}")
    print(f"  Break-even:   {BREAK_EVEN_PCT:.2%} (-110 vig)")
    print(f"  Profit:       {profit_stats['profit']:+.2f} units (flat $100 bets)")
    print(f"  ROI:          {profit_stats['roi']:+.2f}%")


def print_per_season_breakdown(results: pd.DataFrame, target: str) -> None:
    """Print per-season ATS or O/U breakdown.

    Args:
        results: DataFrame with evaluation columns.
        target: 'spread' or 'total' to determine which columns to use.
    """
    if target == "spread":
        correct_col, push_col, label = "ats_correct", "push", "ATS"
    else:
        correct_col, push_col, label = "ou_correct", "push_ou", "O/U"

    print(f"\n  Per-Season {label} Breakdown:")
    print(f"  {'Season':<8} {'Games':>6} {'W':>4} {'L':>4} {'P':>4} {'Acc':>8} {'Profit':>10} {'ROI':>8}")
    print(f"  {'-' * 56}")

    for season in sorted(results["season"].unique()):
        season_data = results[results["season"] == season]
        stats = compute_profit(season_data, correct_col=correct_col, push_col=push_col)
        non_push = season_data[~season_data[push_col]]
        acc = non_push[correct_col].mean() if len(non_push) > 0 else 0.0
        print(
            f"  {int(season):<8} {len(season_data):>6} "
            f"{stats['wins']:>4} {stats['losses']:>4} {stats['pushes']:>4} "
            f"{acc:>7.1%} {stats['profit']:>+10.2f} {stats['roi']:>+7.2f}%"
        )


def run_backtest(
    target: str,
    seasons: Optional[List[int]],
    model_dir: Optional[str],
) -> None:
    """Run prediction backtest for spread, total, or both.

    Args:
        target: One of 'spread', 'total', or 'both'.
        seasons: List of seasons to evaluate. None uses PREDICTION_SEASONS.
        model_dir: Directory containing trained models. None uses MODEL_DIR.
    """
    # Assemble features
    print("Assembling game features...")
    all_data = assemble_multiyear_features(seasons)
    if all_data.empty:
        print("ERROR: No game data assembled. Check Silver/Bronze data.")
        return

    feature_cols = get_feature_columns(all_data)
    print(f"  {len(all_data)} games, {len(feature_cols)} features")

    # Check required label columns
    for col in ["actual_margin", "actual_total", "spread_line", "total_line"]:
        if col not in all_data.columns:
            print(f"ERROR: Missing required column '{col}' in assembled data.")
            return

    targets = []
    if target in ("spread", "both"):
        targets.append("spread")
    if target in ("total", "both"):
        targets.append("total")

    for tgt in targets:
        print(f"\nLoading {tgt} model...")
        try:
            model, metadata = load_model(tgt, model_dir=model_dir)
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            print(f"  Train the {tgt} model first: python scripts/train_models.py --target {tgt}")
            continue

        # Predict
        pred_col = "predicted_margin" if tgt == "spread" else "predicted_total"
        target_col = "actual_margin" if tgt == "spread" else "actual_total"

        # Use only features the model was trained on
        model_features = metadata.get("feature_names", feature_cols)
        available = [c for c in model_features if c in all_data.columns]
        if len(available) < len(model_features):
            missing = set(model_features) - set(available)
            print(f"  WARNING: {len(missing)} features missing from data: {sorted(missing)[:5]}...")

        all_data[pred_col] = model.predict(all_data[available])

        # Evaluate
        if tgt == "spread":
            results = evaluate_ats(all_data)
            print_ats_report(results, f"Overall ({len(results)} games)")
            print_per_season_breakdown(results, "spread")
        else:
            results = evaluate_ou(all_data)
            print_ou_report(results, f"Overall ({len(results)} games)")
            print_per_season_breakdown(results, "total")

    print(f"\nNote: spread_line assumed to be closing line (nflverse convention).")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for prediction backtesting.

    Args:
        argv: Command-line arguments. None uses sys.argv.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="Backtest NFL game prediction models against Vegas closing lines"
    )
    parser.add_argument(
        "--target",
        choices=["spread", "total", "both"],
        default="both",
        help="Which model to evaluate (default: both)",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=None,
        help="Seasons to evaluate (default: all PREDICTION_SEASONS)",
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Directory containing trained models (default: models/)",
    )
    args = parser.parse_args(argv)

    print(f"\nNFL Game Prediction Backtester")
    print(f"Target: {args.target.upper()}")
    if args.seasons:
        print(f"Seasons: {args.seasons}")
    print("=" * 60)

    try:
        run_backtest(args.target, args.seasons, args.model_dir)
    except Exception as e:
        print(f"\nERROR: {e}")
        logger.exception("Backtest failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
