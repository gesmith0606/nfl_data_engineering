#!/usr/bin/env python3
"""Ablation: compare P30 baseline vs market-feature-augmented ensemble on sealed holdout.

Per D-04, orchestrates:
1. Evaluate baseline P30 ensemble on 2024 holdout
2. Re-run feature selection with market features as candidates
3. Retrain ensemble with newly selected features to models/ensemble_ablation/
4. Evaluate ablation ensemble on 2024 holdout
5. Compare and produce report with SHAP importance

Usage:
    python scripts/ablation_market_features.py
    python scripts/ablation_market_features.py --dry-run
    python scripts/ablation_market_features.py --counts 60 80 100 120 150
"""

import argparse
import json
import logging
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import (
    CONSERVATIVE_PARAMS,
    ENSEMBLE_DIR,
    HOLDOUT_SEASON,
    TRAINING_SEASONS,
    VALIDATION_SEASONS,
)
from ensemble_training import load_ensemble, predict_ensemble, train_ensemble
from feature_engineering import assemble_multiyear_features, get_feature_columns
from feature_selector import FeatureSelectionResult, select_features_for_fold
from prediction_backtester import (
    compute_clv_by_tier,
    compute_profit,
    evaluate_ats,
    evaluate_clv,
    evaluate_holdout,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ABLATION_DIR = "models/ensemble_ablation"


# ---------------------------------------------------------------------------
# Baseline evaluation
# ---------------------------------------------------------------------------


def evaluate_baseline(
    all_data: pd.DataFrame,
    feature_cols: List[str],
) -> Dict[str, Any]:
    """Load P30 ensemble from models/ensemble/, predict on assembled data, evaluate holdout.

    Args:
        all_data: Full assembled DataFrame (training + holdout).
        feature_cols: Feature columns present in the P30 ensemble metadata.

    Returns:
        Dict with ats_accuracy, profit_stats, clv_by_tier, n_games.
    """
    spread_models, total_models, metadata = load_ensemble(ENSEMBLE_DIR)
    baseline_features = metadata.get("selected_features", feature_cols)

    # Ensure all features exist in data, filling missing with NaN
    for col in baseline_features:
        if col not in all_data.columns:
            all_data[col] = np.nan

    holdout = all_data[all_data["season"] == HOLDOUT_SEASON].copy()
    if holdout.empty:
        return {"ats_accuracy": 0.0, "profit_stats": {}, "n_games": 0}

    # Predict spread on holdout
    holdout["predicted_margin"] = predict_ensemble(
        holdout[baseline_features], spread_models
    )

    # Evaluate ATS
    holdout = evaluate_ats(holdout)
    holdout_result = evaluate_holdout(holdout, metadata)

    # CLV
    holdout = evaluate_clv(holdout)
    clv_tiers = compute_clv_by_tier(holdout)

    return {
        "ats_accuracy": holdout_result["ats_accuracy"],
        "profit_stats": holdout_result["profit_stats"],
        "n_games": holdout_result["n_games"],
        "clv_by_tier": clv_tiers,
        "feature_count": len(baseline_features),
    }


# ---------------------------------------------------------------------------
# Feature selection with market features
# ---------------------------------------------------------------------------


def run_feature_selection_with_market(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    candidate_counts: Optional[List[int]] = None,
    correlation_threshold: float = 0.90,
) -> Tuple[FeatureSelectionResult, int, Dict[int, float]]:
    """Re-run feature selection with market features as candidates.

    Reimplements the optimal feature count search using src/feature_selector.py
    directly (not importing from scripts/). Market features (opening_spread,
    opening_total) are already in feature_cols since Phase 33.

    Args:
        all_data: Full assembled data (will be filtered to training only).
        feature_cols: All candidate feature columns.
        target_col: Target column name.
        candidate_counts: Feature counts to evaluate via CV.
        correlation_threshold: Pearson r threshold for correlation filter.

    Returns:
        Tuple of (final_result, optimal_count, cv_results).
    """
    if candidate_counts is None:
        candidate_counts = [60, 80, 100, 120, 150]

    # Filter to training data (exclude holdout)
    train_data = all_data[all_data["season"] < HOLDOUT_SEASON].copy()

    # Step 1: Find optimal feature count via walk-forward CV
    cv_results: Dict[int, float] = {}

    for count in candidate_counts:
        fold_maes: List[float] = []
        logger.info("Evaluating feature count: %d", count)

        for val_season in VALIDATION_SEASONS:
            if val_season == HOLDOUT_SEASON:
                continue

            train = train_data[train_data["season"] < val_season]
            val = train_data[train_data["season"] == val_season]

            if train.empty or val.empty:
                continue

            # Run feature selection on this fold's training data
            result = select_features_for_fold(
                train,
                feature_cols,
                target_col,
                target_count=count,
                correlation_threshold=correlation_threshold,
                params=CONSERVATIVE_PARAMS.copy(),
            )

            selected = result.selected_features
            if not selected:
                continue

            # Train quick XGBoost on train with selected features
            params = CONSERVATIVE_PARAMS.copy()
            early_stopping = params.pop("early_stopping_rounds", 50)
            model = xgb.XGBRegressor(
                early_stopping_rounds=early_stopping,
                **params,
            )
            model.fit(
                train[selected],
                train[target_col],
                eval_set=[(val[selected], val[target_col])],
                verbose=False,
            )

            preds = model.predict(val[selected])
            mae = float(mean_absolute_error(val[target_col], preds))
            fold_maes.append(mae)

            logger.info(
                "  count=%d val_season=%d MAE=%.4f (%d features selected)",
                count,
                val_season,
                mae,
                len(selected),
            )

        mean_mae = float(np.mean(fold_maes)) if fold_maes else float("inf")
        cv_results[count] = mean_mae
        logger.info("  count=%d mean_MAE=%.4f", count, mean_mae)

    optimal_count = min(cv_results, key=cv_results.get)
    logger.info(
        "Optimal feature count: %d (MAE=%.4f)",
        optimal_count,
        cv_results[optimal_count],
    )

    # Step 2: Run final selection on all training data with optimal count
    final_result = select_features_for_fold(
        train_data,
        feature_cols,
        target_col,
        target_count=optimal_count,
        correlation_threshold=correlation_threshold,
    )

    return final_result, optimal_count, cv_results


# ---------------------------------------------------------------------------
# Retrain ablation ensemble
# ---------------------------------------------------------------------------


def retrain_ablation_ensemble(
    all_data: pd.DataFrame,
    selected_features: List[str],
) -> dict:
    """Train ensemble with ablation features to separate directory.

    Args:
        all_data: Full assembled data (training + holdout).
        selected_features: Features from ablation feature selection.

    Returns:
        Ensemble metadata dict.
    """
    logger.info(
        "Retraining ablation ensemble with %d features to %s",
        len(selected_features),
        ABLATION_DIR,
    )
    metadata = train_ensemble(
        all_data,
        selected_features,
        ensemble_dir=ABLATION_DIR,
    )
    return metadata


# ---------------------------------------------------------------------------
# Evaluate ablation model
# ---------------------------------------------------------------------------


def evaluate_ablation_model(
    all_data: pd.DataFrame,
    feature_cols: List[str],
) -> Dict[str, Any]:
    """Load ablation ensemble from ABLATION_DIR, predict, evaluate holdout.

    Args:
        all_data: Full assembled data.
        feature_cols: Feature columns for the ablation model.

    Returns:
        Dict with ats_accuracy, profit_stats, clv_by_tier, n_games.
    """
    spread_models, total_models, metadata = load_ensemble(ABLATION_DIR)
    ablation_features = metadata.get("selected_features", feature_cols)

    # Ensure all features exist in data
    for col in ablation_features:
        if col not in all_data.columns:
            all_data[col] = np.nan

    holdout = all_data[all_data["season"] == HOLDOUT_SEASON].copy()
    if holdout.empty:
        return {"ats_accuracy": 0.0, "profit_stats": {}, "n_games": 0}

    holdout["predicted_margin"] = predict_ensemble(
        holdout[ablation_features], spread_models
    )

    holdout = evaluate_ats(holdout)
    holdout_result = evaluate_holdout(holdout, metadata)

    holdout = evaluate_clv(holdout)
    clv_tiers = compute_clv_by_tier(holdout)

    return {
        "ats_accuracy": holdout_result["ats_accuracy"],
        "profit_stats": holdout_result["profit_stats"],
        "n_games": holdout_result["n_games"],
        "clv_by_tier": clv_tiers,
        "feature_count": len(ablation_features),
    }


# ---------------------------------------------------------------------------
# Ship or skip decision
# ---------------------------------------------------------------------------


def compute_ship_or_skip(baseline_ats: float, ablation_ats: float) -> str:
    """Determine whether to ship or skip the ablation model.

    Per D-08: any improvement (strict >) means SHIP.

    Args:
        baseline_ats: Baseline ATS accuracy (e.g. 0.530).
        ablation_ats: Ablation ATS accuracy.

    Returns:
        "SHIP" if ablation_ats > baseline_ats, else "SKIP".
    """
    if ablation_ats > baseline_ats:
        return "SHIP"
    return "SKIP"


# ---------------------------------------------------------------------------
# SHAP report formatting
# ---------------------------------------------------------------------------


def format_shap_report(shap_scores: Dict[str, float], top_n: int = 20) -> str:
    """Format top N features by SHAP importance as text table.

    Flags if opening_spread > 30% of total SHAP importance (D-12, D-13).

    Args:
        shap_scores: Map of feature name -> mean absolute SHAP value.
        top_n: Number of top features to display.

    Returns:
        Formatted string with SHAP importance table and optional dominance warning.
    """
    total_shap = sum(shap_scores.values())
    if total_shap == 0:
        return "SHAP Feature Importance: No scores available\n"

    sorted_features = sorted(shap_scores.items(), key=lambda x: x[1], reverse=True)
    top_features = sorted_features[:top_n]

    lines = ["SHAP Feature Importance (Top {})".format(min(top_n, len(top_features)))]
    lines.append("-" * 60)
    lines.append(f"  {'Feature':<40} {'SHAP':>8} {'Pct':>8}")
    lines.append(f"  {'-' * 40} {'-' * 8} {'-' * 8}")

    for feat, score in top_features:
        pct = score / total_shap * 100
        lines.append(f"  {feat:<40} {score:>8.4f} {pct:>7.1f}%")

    # Check opening_spread dominance (D-12, D-13)
    opening_spread_score = shap_scores.get("opening_spread", 0.0)
    opening_spread_pct = opening_spread_score / total_shap

    if opening_spread_pct > 0.30:
        lines.append("")
        lines.append(
            f"WARNING: opening_spread dominance detected "
            f"({opening_spread_pct:.1%} of total SHAP importance > 30% threshold)"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Comparison report formatting
# ---------------------------------------------------------------------------


def format_comparison_report(
    baseline: Dict[str, Any],
    ablation: Dict[str, Any],
    verdict: str,
    shap_report: str,
    feature_counts: Dict[str, int],
) -> str:
    """Format full comparison report.

    Args:
        baseline: Baseline evaluation results.
        ablation: Ablation evaluation results.
        verdict: "SHIP" or "SKIP".
        shap_report: Formatted SHAP importance string.
        feature_counts: Dict with baseline and ablation feature counts.

    Returns:
        Full comparison report string.
    """
    baseline_ats = baseline["ats_accuracy"]
    ablation_ats = ablation["ats_accuracy"]
    delta_ats = ablation_ats - baseline_ats

    baseline_profit = baseline.get("profit_stats", {}).get("profit", 0.0)
    ablation_profit = ablation.get("profit_stats", {}).get("profit", 0.0)
    delta_profit = ablation_profit - baseline_profit

    lines = []
    lines.append("=" * 72)
    lines.append("MARKET FEATURE ABLATION REPORT")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"  Baseline ATS:     {baseline_ats:.1%} ({baseline.get('n_games', 0)} games)")
    lines.append(f"  Ablation ATS:     {ablation_ats:.1%} ({ablation.get('n_games', 0)} games)")
    lines.append(f"  Delta ATS:        {delta_ats:+.1%}")
    lines.append("")
    lines.append(f"  Baseline Profit:  {baseline_profit:+.2f} units")
    lines.append(f"  Ablation Profit:  {ablation_profit:+.2f} units")
    lines.append(f"  Delta Profit:     {delta_profit:+.2f} units")
    lines.append("")
    lines.append(
        f"  Baseline Features: {feature_counts.get('baseline', 'N/A')}"
    )
    lines.append(
        f"  Ablation Features: {feature_counts.get('ablation', 'N/A')}"
    )
    lines.append("")
    lines.append(shap_report)
    lines.append("")

    # D-14: If opening_spread dominates AND verdict is SKIP
    has_dominance = "opening_spread dominance" in shap_report.lower()
    if has_dominance and verdict == "SKIP":
        lines.append(
            "NOTE: Despite opening_spread dominance in SHAP importance, "
            "the ablation model did not improve holdout accuracy. "
            "This suggests the model already captures market signal indirectly "
            "through correlated features (e.g., team quality differentials)."
        )
        lines.append("")

    # Verdict
    lines.append("-" * 72)
    if verdict == "SHIP":
        lines.append(
            f"VERDICT: SHIP -- Ablation model improves ATS by {delta_ats:+.1%}. "
            "Copying ablation artifacts to production."
        )
    else:
        lines.append(
            f"VERDICT: SKIP -- Ablation model does not improve ATS ({delta_ats:+.1%}). "
            "P30 ensemble remains production."
        )
    lines.append("=" * 72)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Apply ship decision
# ---------------------------------------------------------------------------


def apply_ship_decision(verdict: str) -> None:
    """Apply the ship/skip decision.

    If SHIP: copy ablation artifacts to production directory and verify
    metadata.json replacement. If SKIP: leave production untouched.

    Args:
        verdict: "SHIP" or "SKIP".
    """
    if verdict == "SHIP":
        logger.info("SHIP: Copying %s -> %s", ABLATION_DIR, ENSEMBLE_DIR)
        shutil.copytree(ABLATION_DIR, ENSEMBLE_DIR, dirs_exist_ok=True)

        # Verify metadata.json was replaced
        meta_path = os.path.join(ENSEMBLE_DIR, "metadata.json")
        with open(meta_path, "r") as f:
            new_meta = json.load(f)
        logger.info(
            "Verified: production metadata now has %d features",
            len(new_meta.get("selected_features", [])),
        )
    else:
        logger.info("SKIP: P30 ensemble remains production (no changes)")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_ablation(
    dry_run: bool = False,
    candidate_counts: Optional[List[int]] = None,
    correlation_threshold: float = 0.90,
) -> Dict[str, Any]:
    """Main ablation orchestrator.

    Steps:
    1. Assemble multi-year features
    2. Get feature columns
    3. Evaluate baseline P30 ensemble on holdout
    4. If not dry_run: feature selection, retrain, evaluate ablation
    5. Compute ship-or-skip verdict
    6. Format and print comparison report
    7. Apply decision (if not dry_run)

    Args:
        dry_run: If True, evaluate baseline only.
        candidate_counts: Feature counts for CV search.
        correlation_threshold: Pearson r threshold.

    Returns:
        Results dict with baseline_ats, ablation_ats, verdict, etc.
    """
    if candidate_counts is None:
        candidate_counts = [60, 80, 100, 120, 150]

    # Step 1: Assemble features
    logger.info("Assembling multi-year features...")
    all_data = assemble_multiyear_features()

    if all_data.empty:
        logger.error("No data assembled. Check Silver/Bronze data.")
        return {"error": "No data assembled"}

    # Step 2: Get feature columns
    feature_cols = get_feature_columns(all_data)
    logger.info("Loaded %d games with %d features", len(all_data), len(feature_cols))

    # Step 3: Evaluate baseline
    logger.info("Evaluating baseline P30 ensemble...")
    baseline = evaluate_baseline(all_data, feature_cols)
    logger.info(
        "Baseline: ATS=%.1f%%, Profit=%+.2f",
        baseline["ats_accuracy"] * 100,
        baseline.get("profit_stats", {}).get("profit", 0.0),
    )

    if dry_run:
        print("\n[DRY RUN] Baseline evaluation complete. Skipping retraining.")
        print(f"  Baseline ATS: {baseline['ats_accuracy']:.1%}")
        print(f"  Baseline Features: {baseline.get('feature_count', 'N/A')}")
        return {
            "baseline_ats": baseline["ats_accuracy"],
            "baseline_profit": baseline.get("profit_stats", {}).get("profit", 0.0),
            "dry_run": True,
        }

    # Step 4: Feature selection with market features
    target_col = "actual_margin"
    logger.info("Running feature selection with market features...")
    selection_result, optimal_count, cv_results = run_feature_selection_with_market(
        all_data,
        feature_cols,
        target_col,
        candidate_counts=candidate_counts,
        correlation_threshold=correlation_threshold,
    )
    selected_features = selection_result.selected_features
    logger.info(
        "Selected %d features (optimal count: %d)", len(selected_features), optimal_count
    )

    # Step 5: Retrain ablation ensemble
    ablation_metadata = retrain_ablation_ensemble(all_data, selected_features)

    # Step 6: Evaluate ablation model
    logger.info("Evaluating ablation ensemble...")
    ablation = evaluate_ablation_model(all_data, selected_features)
    logger.info(
        "Ablation: ATS=%.1f%%, Profit=%+.2f",
        ablation["ats_accuracy"] * 100,
        ablation.get("profit_stats", {}).get("profit", 0.0),
    )

    # Step 7: Ship or skip
    verdict = compute_ship_or_skip(baseline["ats_accuracy"], ablation["ats_accuracy"])

    # Step 8: Format report
    shap_report = format_shap_report(selection_result.shap_scores, top_n=20)
    feature_counts = {
        "baseline": baseline.get("feature_count", 0),
        "ablation": len(selected_features),
    }
    report = format_comparison_report(
        baseline, ablation, verdict, shap_report, feature_counts
    )
    print(report)

    # Step 9: Apply decision
    apply_ship_decision(verdict)

    # Check market features in final selection
    market_in_selection = [
        f for f in selected_features
        if "opening_spread" in f or "opening_total" in f
    ]
    logger.info("Market features in ablation selection: %s", market_in_selection)

    return {
        "baseline_ats": baseline["ats_accuracy"],
        "ablation_ats": ablation["ats_accuracy"],
        "baseline_profit": baseline.get("profit_stats", {}).get("profit", 0.0),
        "ablation_profit": ablation.get("profit_stats", {}).get("profit", 0.0),
        "verdict": verdict,
        "shap_top_20": dict(
            sorted(
                selection_result.shap_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:20]
        ),
        "feature_count_baseline": baseline.get("feature_count", 0),
        "feature_count_ablation": len(selected_features),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    """CLI entry point for market feature ablation."""
    parser = argparse.ArgumentParser(
        description="Ablation: compare P30 baseline vs market-feature-augmented ensemble"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate baseline only, skip retraining",
    )
    parser.add_argument(
        "--counts",
        nargs="+",
        type=int,
        default=[60, 80, 100, 120, 150],
        help="Candidate feature counts to evaluate (default: 60 80 100 120 150)",
    )
    parser.add_argument(
        "--correlation-threshold",
        type=float,
        default=0.90,
        help="Pearson r threshold for correlation filter (default: 0.90)",
    )
    args = parser.parse_args(argv)

    results = run_ablation(
        dry_run=args.dry_run,
        candidate_counts=args.counts,
        correlation_threshold=args.correlation_threshold,
    )

    if "error" in results:
        sys.exit(1)


if __name__ == "__main__":
    main()
