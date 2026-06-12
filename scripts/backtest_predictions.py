#!/usr/bin/env python3
"""Backtest NFL game prediction models against historical Vegas closing lines.

Loads trained XGBoost spread and/or total models, generates predictions for
historical games, and evaluates ATS accuracy, O/U accuracy, vig-adjusted
profit/loss, and ROI.

Usage:
    python scripts/backtest_predictions.py --target both
    python scripts/backtest_predictions.py --target spread --seasons 2022 2023 2024
    python scripts/backtest_predictions.py --target total --model-dir models/
    python scripts/backtest_predictions.py --ensemble --clv-true --season 2026

CLV (line-capture) mode (--clv-true)
=====================================
When ``--clv-true`` is passed, the script reads Bronze Parquet snapshots
written by ``scripts/bronze_odds_api_ingestion.py`` (via the odds-capture cron
``odds-capture.yml``), derives an open-proxy and closing line per game, and
computes true signed line capture for each pick made against the open-proxy.

This mode requires live snapshot data.  The odds-capture cron is activated once
ODDS_API_KEY is set in GitHub Secrets (register free at https://the-odds-api.com).
Once the key is set, the cron runs 2×/day and commits snapshots to
``data/bronze/odds_api/snapshots/season=YYYY/``.

Success gate (ELITE 2.4): mean signed capture > +0.3 pts, n ≥ 100 picks, by
2026 week 10.  Kill criterion: capture ≤ 0 at n ≥ 150.

Primary spread metric once 2026 data flows: line capture.
ATS% is secondary — it cannot distinguish sharp from lucky.
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
    evaluate_clv,
    evaluate_holdout,
    evaluate_ou,
    evaluate_line_capture,
    compute_line_capture_summary,
    compute_clv_by_season,
    compute_clv_by_tier,
    compute_season_stability,
    print_holdout_comparison,
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


def print_clv_report(results: pd.DataFrame, label: str = "Overall") -> None:
    """Print formatted CLV (Closing Line Value) report.

    Args:
        results: DataFrame with predicted_margin, spread_line columns.
        label: Report section label.
    """
    clv_df = evaluate_clv(results)
    n_games = len(clv_df)
    mean_clv = float(clv_df["clv"].mean())
    median_clv = float(clv_df["clv"].median())
    pct_beating = float((clv_df["clv"] > 0).mean())

    print(f"\n{'=' * 60}")
    print(f"CLV RESULTS -- {label}")
    print(f"{'=' * 60}")
    print(f"  Mean CLV:           {mean_clv:+.2f} points")
    print(f"  Median CLV:         {median_clv:+.2f} points")
    print(f"  Pct Beating Close:  {pct_beating:.1%}")

    # By Confidence Tier
    tier_df = compute_clv_by_tier(clv_df)
    print(f"\n  By Confidence Tier:")
    print(f"  {'Tier':<10} {'Games':>6}   {'Mean CLV':>9}  {'Median CLV':>10}  {'Pct Beat Close':>14}")
    print(f"  {'-' * 55}")
    for _, row in tier_df.iterrows():
        print(
            f"  {row['tier']:<10} {int(row['games']):>6}   "
            f"{row['mean_clv']:>+9.2f}  {row['median_clv']:>+10.2f}  "
            f"{row['pct_beating_close']:>13.1%}"
        )

    # By Season
    season_df = compute_clv_by_season(clv_df)
    print(f"\n  By Season:")
    print(f"  {'Season':<8} {'Games':>6}   {'Mean CLV':>9}  {'Median CLV':>10}  {'Pct Beat Close':>14}")
    print(f"  {'-' * 55}")
    for _, row in season_df.iterrows():
        print(
            f"  {int(row['season']):<8} {int(row['games']):>6}   "
            f"{row['mean_clv']:>+9.2f}  {row['median_clv']:>+10.2f}  "
            f"{row['pct_beating_close']:>13.1%}"
        )
    print(f"{'=' * 60}")


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
        if tgt == "spread":
            print_clv_report(results, f"Ensemble CLV ({len(results)} games)")
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

        # CLV report for ensemble spread results
        if tgt == "spread":
            print_clv_report(ens_results, f"Ensemble CLV ({len(ens_results)} games)")


def run_holdout_comparison(
    model_dir: Optional[str],
    ensemble_dir: Optional[str],
) -> None:
    """Run sealed holdout three-way comparison: v1.4 XGB vs P30 Ensemble vs P31 Full.

    Args:
        model_dir: Directory containing v1.4 single XGBoost models.
        ensemble_dir: Directory containing Phase-31 ensemble artifacts.
    """
    from config import PREDICTION_SEASONS

    # Phase-30 ensemble backup directory (parallel to ensemble_dir)
    if ensemble_dir is None:
        ensemble_dir = ENSEMBLE_DIR
    p30_dir = os.path.join(os.path.dirname(ensemble_dir), "ensemble_p30")

    # Assemble features for holdout evaluation
    print("Assembling game features for holdout comparison...")
    all_data = assemble_multiyear_features(PREDICTION_SEASONS)
    if all_data.empty:
        print("ERROR: No game data assembled. Check Silver/Bronze data.")
        return

    feature_cols = get_feature_columns(all_data)
    print(f"  {len(all_data)} games, {len(feature_cols)} features")

    # Check required columns
    for col in ["actual_margin", "actual_total", "spread_line", "total_line"]:
        if col not in all_data.columns:
            print(f"ERROR: Missing required column '{col}' in assembled data.")
            return

    # --- v1.4 Single XGBoost ---
    print("\nLoading v1.4 single XGBoost spread model...")
    try:
        model, metadata = load_model("spread", model_dir=model_dir)
        model_features = metadata.get("feature_names", feature_cols)
        avail = [c for c in model_features if c in all_data.columns]
        xgb_data = all_data.copy()
        xgb_data["predicted_margin"] = model.predict(xgb_data[avail])
        # O/U model
        try:
            ou_model, ou_meta = load_model("total", model_dir=model_dir)
            ou_features = ou_meta.get("feature_names", feature_cols)
            ou_avail = [c for c in ou_features if c in xgb_data.columns]
            xgb_data["predicted_total"] = ou_model.predict(xgb_data[ou_avail])
        except FileNotFoundError:
            xgb_data["predicted_total"] = xgb_data["total_line"]  # fallback
        xgb_results = evaluate_ats(xgb_data)
        from prediction_backtester import evaluate_ou as _eval_ou
        xgb_results = _eval_ou(xgb_results)
        print(f"  v1.4 XGBoost: {len(xgb_results)} games evaluated")
    except FileNotFoundError as e:
        print(f"WARNING: v1.4 XGBoost model not found: {e}")
        xgb_results = pd.DataFrame()

    # --- Phase-30 Ensemble ---
    print("Loading Phase-30 ensemble...")
    try:
        p30_spread, p30_total, p30_meta = load_ensemble(p30_dir)
        p30_features = p30_meta.get("selected_features", [])
        p30_avail = [c for c in p30_features if c in all_data.columns]
        p30_data = all_data.copy()
        p30_input = p30_data[p30_avail].fillna(0.0)
        p30_data["predicted_margin"] = predict_ensemble(p30_input, p30_spread)
        p30_data["predicted_total"] = predict_ensemble(p30_input, p30_total)
        p30_results = evaluate_ats(p30_data)
        p30_results = _eval_ou(p30_results)
        print(f"  P30 Ensemble: {len(p30_results)} games evaluated")
    except FileNotFoundError as e:
        print(f"WARNING: Phase-30 ensemble not found at {p30_dir}: {e}")
        p30_results = pd.DataFrame()

    # --- Phase-31 Full Ensemble ---
    print("Loading Phase-31 full ensemble...")
    try:
        p31_spread, p31_total, p31_meta = load_ensemble(ensemble_dir)
        p31_features = p31_meta.get("selected_features", [])
        p31_avail = [c for c in p31_features if c in all_data.columns]
        p31_data = all_data.copy()
        p31_input = p31_data[p31_avail].fillna(0.0)
        p31_data["predicted_margin"] = predict_ensemble(p31_input, p31_spread)
        p31_data["predicted_total"] = predict_ensemble(p31_input, p31_total)
        p31_results = evaluate_ats(p31_data)
        p31_results = _eval_ou(p31_results)
        print(f"  P31 Full: {len(p31_results)} games evaluated")
    except FileNotFoundError as e:
        print(f"WARNING: Phase-31 ensemble not found at {ensemble_dir}: {e}")
        p31_results = pd.DataFrame()

    # --- Three-way comparison ---
    if xgb_results.empty and p30_results.empty and p31_results.empty:
        print("ERROR: No models could be loaded for holdout comparison.")
        return

    # Use non-empty fallback DataFrames for comparison
    if xgb_results.empty:
        xgb_results = p31_results.copy()
        xgb_results["predicted_margin"] = xgb_results["spread_line"]  # baseline
    if p30_results.empty:
        p30_results = p31_results.copy()
    if p31_results.empty:
        p31_results = p30_results.copy() if not p30_results.empty else xgb_results.copy()

    comparison = print_holdout_comparison(
        xgb_results, p30_results, p31_results,
        holdout_season=HOLDOUT_SEASON,
    )

    # CLV report for P31 ensemble on holdout season
    if not p31_results.empty:
        holdout_data = p31_results[p31_results["season"] == HOLDOUT_SEASON]
        if not holdout_data.empty:
            print_clv_report(holdout_data, f"P31 Ensemble CLV -- {HOLDOUT_SEASON} Holdout")

    return comparison


def print_line_capture_report(
    summary: dict,
    label: str = "Overall",
) -> None:
    """Print formatted line-capture (true CLV) report.

    Args:
        summary: Dict returned by ``compute_line_capture_summary``.
        label: Report section label.
    """
    print(f"\n{'=' * 60}")
    print(f"LINE CAPTURE (True CLV) -- {label}")
    print(f"{'=' * 60}")

    n = summary.get("n", 0)
    if n == 0:
        print("  No valid line-capture data (missing open/close lines).")
        print(f"{'=' * 60}")
        return

    mean_cap = summary.get("mean_capture", float("nan"))
    median_cap = summary.get("median_capture", float("nan"))
    pct_cap = summary.get("pct_captured", float("nan"))
    std_cap = summary.get("std_capture", float("nan"))

    print(f"  Picks with capture data: {n}")
    print(f"  Mean capture:   {mean_cap:+.2f} pts  (success gate: > +0.3)")
    print(f"  Median capture: {median_cap:+.2f} pts")
    print(f"  Std deviation:  {std_cap:.2f} pts")
    print(f"  Pct captured:   {pct_cap:.1%}  (fraction where number moved our way)")

    # Verdict vs gate
    if n >= 100:
        if mean_cap > 0.3:
            verdict = f"PASS  (mean {mean_cap:+.2f} > +0.3, n={n})"
        else:
            verdict = f"FAIL  (mean {mean_cap:+.2f} ≤ +0.3, n={n})"
        print(f"\n  Gate (n≥100):   {verdict}")
    else:
        print(f"\n  Gate: not yet evaluable (need n≥100, have n={n})")

    # By tier (if available)
    by_tier = summary.get("by_tier")
    if by_tier:
        print(f"\n  By Edge Tier:")
        print(f"  {'Tier':<10} {'n':>5}  {'Mean Capture':>14}  {'Pct Captured':>14}")
        print(f"  {'-' * 48}")
        for row in by_tier:
            print(
                f"  {row['tier']:<10} {row['n']:>5}  "
                f"{row['mean_capture']:>+14.2f}  "
                f"{row['pct_captured']:>13.1%}"
            )

    print(f"{'=' * 60}")


def run_clv_true_backtest(
    seasons: Optional[List[int]],
    ensemble_dir: Optional[str],
    snapshot_dir: Optional[str] = None,
) -> None:
    """Run true-CLV (line-capture) evaluation using Bronze odds snapshots.

    For each season in ``seasons``, loads open-proxy and closing lines from
    the Bronze Parquet snapshots written by the odds-capture cron
    (``scripts/bronze_odds_api_ingestion.py``).  Assembles game features,
    generates ensemble spread predictions, determines pick direction, and
    computes signed line capture per pick.

    This function requires Bronze snapshot data (ODDS_API_KEY must have been
    active during the season).  When no snapshot data exists for a season (e.g.
    pre-2026 or key not yet set), it reports 0 picks with valid capture data
    and exits cleanly without error.

    Args:
        seasons: List of season years to evaluate.  Defaults to all
            PREDICTION_SEASONS when None.
        ensemble_dir: Path to ensemble model artifacts.  Defaults to
            ENSEMBLE_DIR from config.
        snapshot_dir: Override path to Bronze snapshot root.  Defaults to
            ``data/bronze/odds_api/snapshots``.

    Note:
        Once the ODDS_API_KEY GitHub Secret is set, the cron captures
        snapshots twice daily.  Re-run this command after each game week to
        accumulate line-capture evidence toward the ELITE 2.4 gate.
        Command once key is live:
            python scripts/backtest_predictions.py --ensemble --clv-true --seasons 2026
    """
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

    from odds_snapshot_loader import load_open_close_lines
    from config import PREDICTION_SEASONS

    if seasons is None:
        seasons = PREDICTION_SEASONS

    print(f"\nNFL True CLV (Line Capture) Backtest")
    print(f"Seasons: {seasons}")
    print("=" * 60)
    print(
        "NOTE: Requires Bronze snapshot data from the odds-capture cron.\n"
        "      Set ODDS_API_KEY in GitHub Secrets to activate capture.\n"
        "      See .github/workflows/odds-capture.yml for details."
    )
    print("=" * 60)

    # Load ensemble.
    print("\nLoading ensemble models...")
    try:
        from ensemble_training import load_ensemble, predict_ensemble
        spread_models, _total_models, metadata = load_ensemble(ensemble_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("  Train the ensemble first: python scripts/train_ensemble.py")
        return

    # Assemble game features.
    from feature_engineering import assemble_multiyear_features
    print("Assembling game features...")
    all_data = assemble_multiyear_features(seasons)
    if all_data.empty:
        print("ERROR: No game data assembled.")
        return

    feature_cols = metadata.get("selected_features", [])
    available = [c for c in feature_cols if c in all_data.columns]
    all_data["predicted_margin"] = predict_ensemble(
        all_data[available].fillna(0.0), spread_models
    )

    # Determine pick direction for each game.
    if "spread_line" not in all_data.columns:
        print("ERROR: spread_line column missing from assembled features.")
        return

    # nflverse sign: negative spread_line = home favoured.
    # We pick home when predicted_margin > spread_line (model thinks home does
    # better than the line), away otherwise.
    all_data["pick_side"] = "away"
    all_data.loc[all_data["predicted_margin"] > all_data["spread_line"], "pick_side"] = "home"

    # Build a model-edge column for tier breakdown.
    all_data["model_edge"] = (
        all_data["predicted_margin"] - all_data["spread_line"]
    ).abs()

    # Load open/close lines from Bronze snapshots for each season.
    season_frames = []
    for season in sorted(seasons):
        snap_df = load_open_close_lines(
            season=season,
            market="spreads",
            snapshot_dir=snapshot_dir,
        )
        if snap_df.empty:
            logger.info("No spread snapshot data for season=%d", season)
            continue
        snap_df["season"] = season
        season_frames.append(snap_df)

    if not season_frames:
        print(
            "\n  No Bronze snapshot data found for any requested season.\n"
            "  Activate the capture cron by setting ODDS_API_KEY in GitHub Secrets."
        )
        print_line_capture_report(
            {"n": 0}, label=f"Seasons {min(seasons)}–{max(seasons)}"
        )
        return

    snap_combined = pd.concat(season_frames, ignore_index=True)

    # Join open/close lines onto the game features.
    # Match on (home_team_nfl, away_team_nfl, season).
    required_join_cols = {"home_team_nfl", "away_team_nfl"}
    if not required_join_cols.issubset(all_data.columns):
        missing = required_join_cols - set(all_data.columns)
        print(f"ERROR: Missing join columns in assembled features: {sorted(missing)}")
        return

    joined = all_data.merge(
        snap_combined[["home_team_nfl", "away_team_nfl", "season", "open_spread", "close_spread"]],
        on=["home_team_nfl", "away_team_nfl", "season"],
        how="left",
    )

    n_total = len(joined)
    n_with_open = joined["open_spread"].notna().sum()
    n_with_close = joined["close_spread"].notna().sum()
    print(
        f"\n  Games in feature set:     {n_total}"
        f"\n  Games with open-proxy:    {n_with_open}"
        f"\n  Games with close line:    {n_with_close}"
    )

    if n_with_open == 0:
        print(
            "\n  No open-proxy lines available.  "
            "Start capturing before 2026 week 1."
        )
        print_line_capture_report({"n": 0}, label="All Seasons")
        return

    # Compute true line capture.
    capture_df = evaluate_line_capture(
        joined,
        open_col="open_spread",
        close_col="close_spread",
        pick_side_col="pick_side",
        market="spread",
    )

    # Overall summary.
    summary = compute_line_capture_summary(capture_df, edge_col="model_edge")
    print_line_capture_report(summary, label=f"All ({len(seasons)} seasons)")

    # Per-season breakdown.
    if "season" in capture_df.columns:
        print(f"\n  Per-Season Line Capture:")
        print(f"  {'Season':<8} {'n':>5}  {'Mean Capture':>14}  {'Pct Captured':>14}")
        print(f"  {'-' * 48}")
        for season_val in sorted(capture_df["season"].dropna().unique()):
            season_df = capture_df[capture_df["season"] == season_val]
            s = compute_line_capture_summary(season_df)
            if s["n"] > 0:
                print(
                    f"  {int(season_val):<8} {s['n']:>5}  "
                    f"{s['mean_capture']:>+14.2f}  "
                    f"{s['pct_captured']:>13.1%}"
                )
            else:
                print(f"  {int(season_val):<8} {'0':>5}  {'N/A':>14}  {'N/A':>14}")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for prediction backtesting.

    Args:
        argv: Command-line arguments. None uses sys.argv.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Backtest NFL game prediction models against Vegas closing lines.\n\n"
            "Primary spread metric once 2026 data flows: line capture (--clv-true).\n"
            "ATS% is secondary — it cannot distinguish sharp from lucky.\n\n"
            "CLV (true line capture) requires Bronze snapshot data from the\n"
            "odds-capture cron.  Activate by setting ODDS_API_KEY in GitHub Secrets.\n"
            "Register free at https://the-odds-api.com — free tier is sufficient\n"
            "(~60 credits/month for 2x daily capture).\n\n"
            "Once ODDS_API_KEY is live, run:\n"
            "  python scripts/backtest_predictions.py --ensemble --clv-true --seasons 2026\n\n"
            "ELITE 2.4 success gate: mean signed capture > +0.3 pts, n >= 100, by 2026 w10.\n"
            "Kill criterion: capture <= 0 at n >= 150 -> declare no betting edge."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="Run sealed holdout comparison (v1.4 vs Phase-30 vs Phase-31)",
    )
    parser.add_argument(
        "--clv-true",
        action="store_true",
        dest="clv_true",
        help=(
            "Run true CLV (line-capture) evaluation using Bronze odds snapshots.\n"
            "Requires --ensemble and snapshot data from the odds-capture cron.\n"
            "Reads data/bronze/odds_api/snapshots/ (written by bronze_odds_api_ingestion.py).\n"
            "Primary spread metric for 2026 season evaluation."
        ),
    )
    parser.add_argument(
        "--snapshot-dir",
        type=str,
        default=None,
        dest="snapshot_dir",
        help=(
            "Override Bronze snapshot directory for --clv-true mode.\n"
            "Default: data/bronze/odds_api/snapshots (project root-relative)."
        ),
    )
    args = parser.parse_args(argv)

    print(f"\nNFL Game Prediction Backtester")
    print(f"Target: {args.target.upper()}")
    if args.seasons:
        print(f"Seasons: {args.seasons}")
    print("=" * 60)

    try:
        if args.clv_true:
            if not args.ensemble:
                print("ERROR: --clv-true requires --ensemble (ensemble models provide pick direction).")
                return 1
            run_clv_true_backtest(
                seasons=args.seasons,
                ensemble_dir=args.ensemble_dir,
                snapshot_dir=args.snapshot_dir,
            )
        elif args.holdout:
            run_holdout_comparison(args.model_dir, args.ensemble_dir)
        elif args.ensemble:
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
