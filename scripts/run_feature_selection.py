#!/usr/bin/env python3
"""CV-validated feature selection for NFL game prediction models.

Evaluates multiple candidate feature counts via walk-forward cross-validation,
selects the count with lowest MAE, then runs final selection on all training
data to produce the definitive SELECTED_FEATURES list.

Usage:
    python scripts/run_feature_selection.py --target spread
    python scripts/run_feature_selection.py --target spread --counts 60 80 100 120 150
    python scripts/run_feature_selection.py --target spread --dry-run
    python scripts/run_feature_selection.py --target total --correlation-threshold 0.85
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import (
    CONSERVATIVE_PARAMS,
    HOLDOUT_SEASON,
    MODEL_DIR,
    TRAINING_SEASONS,
    VALIDATION_SEASONS,
)
from feature_engineering import assemble_multiyear_features, get_feature_columns
from feature_selector import FeatureSelectionResult, select_features_for_fold

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def find_optimal_feature_count(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    candidate_counts: Optional[List[int]] = None,
    correlation_threshold: float = 0.90,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[int, float]]:
    """Evaluate candidate feature counts via walk-forward CV and pick the best.

    For each candidate count, iterates over VALIDATION_SEASONS. In each fold:
    - Splits data into train (seasons < val_season) and val (season == val_season)
    - Runs select_features_for_fold on train to get the top features
    - Trains XGBoost on train with selected features
    - Predicts on val and computes MAE

    Averages MAE across folds for each count and returns the count with lowest MAE.

    Args:
        all_data: DataFrame with features, target, and 'season' column.
            Must NOT contain HOLDOUT_SEASON rows.
        feature_cols: All candidate feature column names.
        target_col: Target column name (e.g., 'actual_margin').
        candidate_counts: List of feature counts to evaluate.
            Defaults to [60, 80, 100, 120, 150] per D-05.
        correlation_threshold: Pearson r threshold for correlation filter.
        params: XGBoost parameters. Defaults to CONSERVATIVE_PARAMS.

    Returns:
        Tuple of (best_count, {count: mean_mae}) where best_count has lowest MAE.

    Raises:
        ValueError: If all_data contains HOLDOUT_SEASON.
    """
    if candidate_counts is None:
        candidate_counts = [60, 80, 100, 120, 150]

    if HOLDOUT_SEASON in all_data["season"].values:
        raise ValueError(
            f"Holdout season {HOLDOUT_SEASON} found in data. "
            "CV search must use only training data."
        )

    if params is None:
        params = CONSERVATIVE_PARAMS.copy()
    else:
        params = params.copy()

    # Extract early_stopping_rounds for fit() call
    early_stopping_rounds = params.pop("early_stopping_rounds", 50)

    cv_results: Dict[int, float] = {}

    for count in candidate_counts:
        fold_maes: List[float] = []
        logger.info("Evaluating feature count: %d", count)

        for val_season in VALIDATION_SEASONS:
            if val_season == HOLDOUT_SEASON:
                continue

            train = all_data[all_data["season"] < val_season]
            val = all_data[all_data["season"] == val_season]

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

            # Train XGBoost on train with selected features
            fold_params = params.copy()
            model = xgb.XGBRegressor(
                early_stopping_rounds=early_stopping_rounds,
                **fold_params,
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
                count, val_season, mae, len(selected),
            )

        mean_mae = float(np.mean(fold_maes)) if fold_maes else float("inf")
        cv_results[count] = mean_mae
        logger.info("  count=%d mean_MAE=%.4f", count, mean_mae)

    best_count = min(cv_results, key=cv_results.get)
    logger.info(
        "Optimal feature count: %d (MAE=%.4f)", best_count, cv_results[best_count]
    )

    return best_count, cv_results


def run_final_selection(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    optimal_count: int,
    correlation_threshold: float = 0.90,
    params: Optional[Dict[str, Any]] = None,
) -> FeatureSelectionResult:
    """Run feature selection on ALL training data at the optimal count.

    Produces the definitive SELECTED_FEATURES list by running
    select_features_for_fold on all training data (seasons < HOLDOUT_SEASON).

    Args:
        all_data: DataFrame with features, target, and 'season' column.
            Must NOT contain HOLDOUT_SEASON rows.
        feature_cols: All candidate feature column names.
        target_col: Target column name.
        optimal_count: Number of features to select (from CV search).
        correlation_threshold: Pearson r threshold for correlation filter.
        params: XGBoost parameters. Defaults to CONSERVATIVE_PARAMS.

    Returns:
        FeatureSelectionResult with the definitive feature list.
    """
    return select_features_for_fold(
        all_data,
        feature_cols,
        target_col,
        target_count=optimal_count,
        correlation_threshold=correlation_threshold,
        params=params,
    )


def save_metadata(
    result: FeatureSelectionResult,
    cutoff_results: Dict[int, float],
    output_dir: Optional[str] = None,
) -> str:
    """Save feature selection metadata to JSON.

    Creates models/feature_selection/ directory if needed and writes
    metadata.json with all selection details per D-15.

    Args:
        result: FeatureSelectionResult from run_final_selection.
        cutoff_results: Dict of {count: mean_mae} from find_optimal_feature_count.
        output_dir: Directory for metadata output.
            Defaults to models/feature_selection/.

    Returns:
        Path to the written metadata.json file.
    """
    if output_dir is None:
        output_dir = os.path.join(MODEL_DIR, "feature_selection")

    os.makedirs(output_dir, exist_ok=True)

    metadata = {
        "selected_features": sorted(result.selected_features),
        "dropped_correlation": result.dropped_correlation,
        "dropped_low_importance": result.dropped_low_importance,
        "shap_scores": {
            k: round(v, 6) for k, v in sorted(
                result.shap_scores.items(), key=lambda x: x[1], reverse=True
            )
        },
        "correlated_pairs": [
            [a, b, round(r, 4)] for a, b, r in result.correlated_pairs
        ],
        "optimal_cutoff": result.n_selected,
        "cv_mae_by_cutoff": {
            str(k): round(v, 4) for k, v in sorted(cutoff_results.items())
        },
        "n_original": result.n_original,
        "n_after_correlation": result.n_after_correlation,
        "n_selected": result.n_selected,
        "fold_seasons": result.fold_seasons,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Metadata saved to %s", metadata_path)
    return metadata_path


def update_config_selected_features(features: List[str]) -> None:
    """Programmatically update SELECTED_FEATURES in src/config.py.

    Reads src/config.py, finds the SELECTED_FEATURES assignment line,
    and replaces it with the actual feature list (sorted, one per line).

    Args:
        features: List of selected feature names.
    """
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "config.py"
    )
    config_path = os.path.normpath(config_path)

    with open(config_path, "r") as f:
        content = f.read()

    # Build the replacement block
    import re

    # Match the SELECTED_FEATURES assignment (single line or multiline)
    pattern = r"SELECTED_FEATURES\s*=\s*(?:None|\[.*?\])"
    # Use DOTALL for multiline list
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        raise RuntimeError(
            "Could not find SELECTED_FEATURES in src/config.py. "
            "Ensure it exists (initialized as None)."
        )

    sorted_features = sorted(features)
    lines = ['SELECTED_FEATURES = [']
    for feat in sorted_features:
        lines.append(f'    "{feat}",')
    lines.append(']')
    replacement = "\n".join(lines)

    content = content[:match.start()] + replacement + content[match.end():]

    with open(config_path, "w") as f:
        f.write(content)

    logger.info(
        "Updated SELECTED_FEATURES in %s with %d features",
        config_path, len(features),
    )


def main(argv=None):
    """CLI entry point for CV-validated feature selection.

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].
    """
    parser = argparse.ArgumentParser(
        description="CV-validated feature selection for NFL prediction models"
    )
    parser.add_argument(
        "--target",
        choices=["spread", "total"],
        default="spread",
        help="Prediction target (default: spread)",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Find optimal count but don't update config.py",
    )
    args = parser.parse_args(argv)

    # Map target name to column
    target_col = "actual_margin" if args.target == "spread" else "actual_total"

    # Load and prepare data
    logger.info("Loading multi-year features for seasons %s", TRAINING_SEASONS)
    all_data = assemble_multiyear_features(TRAINING_SEASONS)

    if all_data.empty:
        logger.error(
            "No data assembled. Ensure Silver data exists for seasons %s",
            TRAINING_SEASONS,
        )
        sys.exit(1)

    feature_cols = get_feature_columns(all_data)
    logger.info("Loaded %d games with %d features", len(all_data), len(feature_cols))

    # Filter to training seasons only (exclude holdout)
    all_data = all_data[all_data["season"] < HOLDOUT_SEASON].copy()
    logger.info("Training data: %d games after holdout exclusion", len(all_data))

    # Step 1: Find optimal feature count via CV
    logger.info("Starting CV-validated cutoff search with counts: %s", args.counts)
    best_count, cv_results = find_optimal_feature_count(
        all_data,
        feature_cols,
        target_col,
        candidate_counts=args.counts,
        correlation_threshold=args.correlation_threshold,
    )

    # Step 2: Run final selection on all training data
    logger.info("Running final selection with optimal count: %d", best_count)
    result = run_final_selection(
        all_data,
        feature_cols,
        target_col,
        optimal_count=best_count,
        correlation_threshold=args.correlation_threshold,
    )

    # Step 3: Save metadata
    metadata_path = save_metadata(result, cv_results)

    # Step 4: Update config.py unless dry-run
    if not args.dry_run:
        update_config_selected_features(result.selected_features)
        logger.info("SELECTED_FEATURES written to src/config.py")
    else:
        logger.info("Dry run -- config.py NOT updated")

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"FEATURE SELECTION SUMMARY -- target={args.target}")
    print(f"{'=' * 60}")
    print(f"  Original features:       {result.n_original}")
    print(f"  After correlation filter: {result.n_after_correlation}")
    print(f"  Final selected:          {result.n_selected}")
    print(f"  Optimal count:           {best_count}")
    print(f"\n  CV MAE by count:")
    for count in sorted(cv_results.keys()):
        marker = " <-- best" if count == best_count else ""
        print(f"    {count:>4d}: {cv_results[count]:.4f}{marker}")
    print(f"\n  Dropped by correlation:  {len(result.dropped_correlation)}")
    print(f"  Dropped by low importance: {len(result.dropped_low_importance)}")
    print(f"  Metadata saved to: {metadata_path}")
    if not args.dry_run:
        print("  SELECTED_FEATURES updated in src/config.py")
    else:
        print("  [DRY RUN] config.py NOT modified")
    print()


if __name__ == "__main__":
    main()
