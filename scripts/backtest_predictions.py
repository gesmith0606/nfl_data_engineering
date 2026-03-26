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
from ensemble_training import load_ensemble, predict_ensemble
from config import ENSEMBLE_DIR, HOLDOUT_SEASON
from prediction_backtester import (
    BREAK_EVEN_PCT,
    compute_profit,
    evaluate_ats,
    evaluate_holdout,
    evaluate_ou,
    compute_season_stability,
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
            correct_col, push_col = "ats_correct", "push"
        else:
            results = evaluate_ou(all_data)
            print_ou_report(results, f"Overall ({len(results)} games)")
            correct_col, push_col = "ou_correct", "push_ou"

        # Per-season stability breakdown
        per_season_df, stability = compute_season_stability(
            results, correct_col=correct_col, push_col=push_col
        )
        label = "ATS" if tgt == "spread" else "O/U"
        print(f"\n  PER-SEASON BREAKDOWN")
        print(f"  {'=' * 60}")
        print(f"  {'Season':<8} {'Games':>6} {label + ' Acc':>8} {'Profit':>10} {'ROI':>8}")
        print(f"  {'-' * 46}")
        for _, row in per_season_df.iterrows():
            print(
                f"  {int(row['season']):<8} {int(row['games']):>6} "
                f"{row['ats_accuracy']:>7.1%} {row['profit']:>+10.2f} {row['roi']:>+7.2f}%"
            )
        print(f"  {'=' * 60}")
        print(
            f"  Stability: Mean {stability['mean_accuracy']:.1%} "
            f"+/- {stability['std_accuracy']:.1%} "
            f"(min {stability['min_accuracy']:.1%}, max {stability['max_accuracy']:.1%})"
        )

        # Leakage warning
        if stability["leakage_warning"]:
            for _, row in per_season_df.iterrows():
                if row["ats_accuracy"] > 0.58:
                    print(
                        f"\n  WARNING: Season {int(row['season'])} shows "
                        f"{row['ats_accuracy']:.1%} {label} accuracy (> 58% threshold)."
                    )
                    print("  Investigate potential data leakage before trusting results.")

        # Sealed holdout section (spread only, when 2024 data present)
        if tgt == "spread" and HOLDOUT_SEASON in results["season"].values:
            holdout_result = evaluate_holdout(results, metadata, holdout_season=HOLDOUT_SEASON)
            ps = holdout_result["profit_stats"]
            print(f"\n{'=' * 60}")
            print(f"SEALED HOLDOUT -- {HOLDOUT_SEASON} Season ({holdout_result['n_games']} games)")
            print(f"{'=' * 60}")
            print(f"  ATS Accuracy: {holdout_result['ats_accuracy']:.1%}")
            print(f"  Record:       {ps['wins']}-{ps['losses']}-{ps['pushes']} (W-L-P)")
            print(f"  Profit:       {ps['profit']:+.2f} units")
            print(f"  ROI:          {ps['roi']:+.2f}%")
            print(f"\n  NOTE: Model trained on {min(metadata.get('training_seasons', []))}–"
                  f"{max(metadata.get('training_seasons', []))} only. {HOLDOUT_SEASON} data was NEVER")
            print(f"  seen during training or hyperparameter tuning.")
            print(f"{'=' * 60}")

    print(f"\nNote: spread_line assumed to be closing line (nflverse convention).")


def run_ensemble_backtest(
    target: str,
    seasons: Optional[List[int]],
    ensemble_dir: Optional[str],
) -> dict:
    """Run ensemble prediction backtest.

    Args:
        target: One of 'spread', 'total', or 'both'.
        seasons: List of seasons to evaluate. None uses PREDICTION_SEASONS.
        ensemble_dir: Directory containing ensemble artifacts.

    Returns:
        Dict mapping target name to (results_df, profit_stats) tuple.
    """
    print("Loading ensemble models...")
    try:
        spread_models, total_models, metadata = load_ensemble(ensemble_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("  Train the ensemble first: python scripts/train_ensemble.py")
        return {}

    # Assemble features
    print("Assembling game features...")
    all_data = assemble_multiyear_features(seasons)
    if all_data.empty:
        print("ERROR: No game data assembled. Check Silver/Bronze data.")
        return {}

    # Use features from ensemble metadata (not config.py -- per Pitfall 5)
    feature_cols = metadata.get("selected_features", [])
    available = [c for c in feature_cols if c in all_data.columns]
    if len(available) < len(feature_cols):
        missing = set(feature_cols) - set(available)
        print(f"  WARNING: {len(missing)} features missing: {sorted(missing)[:5]}...")
    print(f"  {len(all_data)} games, {len(available)} features")

    # Check required label columns
    for col in ["actual_margin", "actual_total", "spread_line", "total_line"]:
        if col not in all_data.columns:
            print(f"ERROR: Missing required column '{col}' in assembled data.")
            return {}

    targets_map = []
    if target in ("spread", "both"):
        targets_map.append("spread")
    if target in ("total", "both"):
        targets_map.append("total")

    ensemble_results = {}
    for tgt in targets_map:
        models = spread_models if tgt == "spread" else total_models
        pred_col = "predicted_margin" if tgt == "spread" else "predicted_total"

        features_input = all_data[available].fillna(0.0)
        all_data[pred_col] = predict_ensemble(features_input, models)

        if tgt == "spread":
            results = evaluate_ats(all_data)
            print_ats_report(results, f"Ensemble ({len(results)} games)")
        else:
            results = evaluate_ou(all_data)
            print_ou_report(results, f"Ensemble ({len(results)} games)")

        print_per_season_breakdown(results, tgt)
        ensemble_results[tgt] = results

    return ensemble_results


def run_comparison_backtest(
    target: str,
    seasons: Optional[List[int]],
    model_dir: Optional[str],
    ensemble_dir: Optional[str],
) -> None:
    """Run side-by-side comparison of single XGBoost vs ensemble.

    Args:
        target: One of 'spread', 'total', or 'both'.
        seasons: List of seasons to evaluate.
        model_dir: Directory containing single XGBoost models.
        ensemble_dir: Directory containing ensemble artifacts.
    """
    # Assemble features once
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

    # Load ensemble
    print("Loading ensemble models...")
    try:
        spread_models, total_models, ens_metadata = load_ensemble(ensemble_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("  Train the ensemble first: python scripts/train_ensemble.py")
        return

    ens_feature_cols = ens_metadata.get("selected_features", [])
    ens_available = [c for c in ens_feature_cols if c in all_data.columns]

    targets_map = []
    if target in ("spread", "both"):
        targets_map.append("spread")
    if target in ("total", "both"):
        targets_map.append("total")

    for tgt in targets_map:
        pred_col = "predicted_margin" if tgt == "spread" else "predicted_total"
        correct_col = "ats_correct" if tgt == "spread" else "ou_correct"
        push_col = "push" if tgt == "spread" else "push_ou"
        label = "ATS" if tgt == "spread" else "O/U"

        # --- Single XGBoost ---
        xgb_stats = None
        try:
            model, metadata = load_model(tgt, model_dir=model_dir)
            model_features = metadata.get("feature_names", feature_cols)
            avail_xgb = [c for c in model_features if c in all_data.columns]
            all_data[pred_col] = model.predict(all_data[avail_xgb])

            if tgt == "spread":
                xgb_results = evaluate_ats(all_data)
            else:
                xgb_results = evaluate_ou(all_data)

            non_push = xgb_results[~xgb_results[push_col]]
            xgb_accuracy = non_push[correct_col].mean() if len(non_push) > 0 else 0.0
            xgb_profit = compute_profit(xgb_results, correct_col=correct_col, push_col=push_col)
            xgb_stats = {"accuracy": xgb_accuracy, "profit": xgb_profit}

            # Print single-model report
            if tgt == "spread":
                print_ats_report(xgb_results, f"Single XGBoost ({len(xgb_results)} games)")
            else:
                print_ou_report(xgb_results, f"Single XGBoost ({len(xgb_results)} games)")
        except FileNotFoundError:
            print(f"  WARNING: No single XGBoost {tgt} model found. Skipping comparison.")

        # --- Ensemble ---
        models = spread_models if tgt == "spread" else total_models
        ens_input = all_data[ens_available].fillna(0.0)
        all_data[pred_col] = predict_ensemble(ens_input, models)

        if tgt == "spread":
            ens_results = evaluate_ats(all_data)
        else:
            ens_results = evaluate_ou(all_data)

        non_push = ens_results[~ens_results[push_col]]
        ens_accuracy = non_push[correct_col].mean() if len(non_push) > 0 else 0.0
        ens_profit = compute_profit(ens_results, correct_col=correct_col, push_col=push_col)

        # Print ensemble report
        if tgt == "spread":
            print_ats_report(ens_results, f"Ensemble ({len(ens_results)} games)")
        else:
            print_ou_report(ens_results, f"Ensemble ({len(ens_results)} games)")

        # --- Side-by-side COMPARISON ---
        print(f"\n{'=' * 60}")
        print(f"COMPARISON: Single XGBoost vs Ensemble ({label})")
        print(f"{'=' * 60}")
        print(f"  {'Metric':<20} {'XGBoost':>10} {'Ensemble':>10} {'Delta':>10}")
        print(f"  {'-' * 52}")

        if xgb_stats is not None:
            xgb_acc = xgb_stats["accuracy"]
            xgb_p = xgb_stats["profit"]
            delta_acc = ens_accuracy - xgb_acc
            delta_profit = ens_profit["profit"] - xgb_p["profit"]
            delta_roi = ens_profit["roi"] - xgb_p["roi"]

            print(f"  {label + ' Accuracy':<20} {xgb_acc:>9.1%} {ens_accuracy:>9.1%} {delta_acc:>+9.1%}")
            print(f"  {label + ' Profit':<20} {xgb_p['profit']:>+10.2f} {ens_profit['profit']:>+10.2f} {delta_profit:>+10.2f}")
            print(f"  {label + ' ROI':<20} {xgb_p['roi']:>+9.1f}% {ens_profit['roi']:>+9.1f}% {delta_roi:>+9.1f}%")
        else:
            print(f"  {label + ' Accuracy':<20} {'N/A':>10} {ens_accuracy:>9.1%} {'N/A':>10}")
            print(f"  {label + ' Profit':<20} {'N/A':>10} {ens_profit['profit']:>+10.2f} {'N/A':>10}")
            print(f"  {label + ' ROI':<20} {'N/A':>10} {ens_profit['roi']:>+9.1f}% {'N/A':>10}")

        print(f"  {'=' * 52}")


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
    parser.add_argument(
        "--ensemble",
        action="store_true",
        help="Use stacking ensemble (XGB+LGB+CB+Ridge) instead of single XGBoost",
    )
    parser.add_argument(
        "--ensemble-dir",
        type=str,
        default=None,
        help="Directory containing ensemble artifacts (default: models/ensemble/)",
    )
    args = parser.parse_args(argv)

    print(f"\nNFL Game Prediction Backtester")
    print(f"Target: {args.target.upper()}")
    if args.seasons:
        print(f"Seasons: {args.seasons}")
    print("=" * 60)

    try:
        if args.ensemble:
            run_comparison_backtest(
                args.target, args.seasons, args.model_dir, args.ensemble_dir
            )
        else:
            run_backtest(args.target, args.seasons, args.model_dir)
    except Exception as e:
        print(f"\nERROR: {e}")
        logger.exception("Backtest failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
