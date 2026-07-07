#!/usr/bin/env python3
"""Experiment: LightGBM residual models with SHAP feature selection.

Compares Ridge (current) vs LightGBM residual models with SHAP-selected
features on walk-forward CV (2022, 2023, 2024 validation seasons).

Usage:
    python scripts/experiment_lgb_residual.py
    python scripts/experiment_lgb_residual.py --positions WR TE
    python scripts/experiment_lgb_residual.py --feature-counts 60 80 100 120
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lightgbm as lgb
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline

from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS
from player_feature_engineering import (
    assemble_multiyear_player_features,
    get_player_feature_columns,
)
from unified_evaluation import (
    build_opp_rankings,
    compute_actual_fantasy_points,
    compute_production_heuristic,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# LightGBM conservative params for residual prediction
RESIDUAL_LGB_PARAMS = {
    "objective": "regression",
    "n_estimators": 500,
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "verbose": -1,
    "n_jobs": -1,
    "random_state": 42,
}

VAL_SEASONS = [2022, 2023, 2024]


def _filter_position_features(
    pos_data: pd.DataFrame,
    feature_cols: List[str],
    nan_threshold: float = 0.90,
) -> List[str]:
    """Filter features to those with <nan_threshold NaN rate for this position.

    Args:
        pos_data: Position-filtered DataFrame.
        feature_cols: All candidate feature columns.
        nan_threshold: Maximum NaN fraction to keep a feature.

    Returns:
        Filtered list of feature column names.
    """
    available = [f for f in feature_cols if f in pos_data.columns]
    nan_rates = pos_data[available].isna().mean()
    return [f for f in available if nan_rates[f] < nan_threshold]


def _shap_select_features(
    train_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    target_count: int = 100,
) -> Tuple[List[str], Dict[str, float]]:
    """SHAP-based feature selection on training data.

    Trains a quick XGBoost model, computes SHAP importance, removes
    correlated pairs, and truncates to target_count.

    Args:
        train_data: Training DataFrame (must NOT contain holdout season).
        feature_cols: Candidate feature columns.
        target_col: Target column name.
        target_count: Desired number of features.

    Returns:
        Tuple of (selected_features, shap_scores).
    """
    from feature_selector import select_features_for_fold

    # Ensure no holdout leakage
    clean = train_data[train_data["season"] != HOLDOUT_SEASON].copy()

    result = select_features_for_fold(
        train_data=clean,
        feature_cols=feature_cols,
        target_col=target_col,
        target_count=target_count,
        correlation_threshold=0.90,
    )

    return result.selected_features, result.shap_scores


def run_ridge_cv(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols: List[str],
    heur_pts: pd.Series,
    actual_pts: pd.Series,
    label: str = "Ridge (all)",
) -> Dict[str, Any]:
    """Run walk-forward CV with Ridge residual model.

    Args:
        pos_data: Position data with features.
        position: Position code.
        feature_cols: Feature columns to use.
        heur_pts: Heuristic fantasy points.
        actual_pts: Actual fantasy points.
        label: Model label for reporting.

    Returns:
        Dict with model label, per-fold MAEs, mean MAE.
    """
    available = [f for f in feature_cols if f in pos_data.columns]
    week_mask = pos_data["week"].between(3, 18)

    fold_results = []
    for val_season in VAL_SEASONS:
        train_mask = (pos_data["season"] < val_season) & week_mask
        val_mask = (pos_data["season"] == val_season) & week_mask

        train_idx = pos_data.index[train_mask]
        val_idx = pos_data.index[val_mask]

        # Compute residuals
        train_residual = actual_pts.loc[train_idx] - heur_pts.loc[train_idx]
        valid = train_residual.notna()
        train_idx = train_idx[valid.loc[train_idx].values]

        val_valid = (actual_pts.loc[val_idx].notna()) & (heur_pts.loc[val_idx].notna())
        val_idx = val_idx[val_valid.loc[val_idx].values]

        if len(train_idx) < 50 or len(val_idx) < 10:
            continue

        X_train = pos_data.loc[train_idx, available]
        y_train = train_residual.loc[train_idx]
        X_val = pos_data.loc[val_idx, available]

        model = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
        ])
        model.fit(X_train, y_train)

        residual_pred = model.predict(X_val)
        hybrid_pts = heur_pts.loc[val_idx].values + residual_pred
        hybrid_pts = np.clip(hybrid_pts, 0.0, None)

        heur_mae = float(mean_absolute_error(
            actual_pts.loc[val_idx].values, heur_pts.loc[val_idx].values
        ))
        hybrid_mae = float(mean_absolute_error(
            actual_pts.loc[val_idx].values, hybrid_pts
        ))

        fold_results.append({
            "val_season": val_season,
            "heur_mae": heur_mae,
            "hybrid_mae": hybrid_mae,
            "improvement_pct": (heur_mae - hybrid_mae) / heur_mae * 100,
            "n_train": len(train_idx),
            "n_val": len(val_idx),
            "ridge_alpha": float(model.named_steps["model"].alpha_),
        })

    mean_heur = np.mean([r["heur_mae"] for r in fold_results]) if fold_results else 0
    mean_hybrid = np.mean([r["hybrid_mae"] for r in fold_results]) if fold_results else 0

    return {
        "label": label,
        "n_features": len(available),
        "folds": fold_results,
        "mean_heur_mae": float(mean_heur),
        "mean_hybrid_mae": float(mean_hybrid),
        "mean_improvement_pct": float(
            (mean_heur - mean_hybrid) / mean_heur * 100 if mean_heur > 0 else 0
        ),
    }


def run_lgb_cv(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols: List[str],
    heur_pts: pd.Series,
    actual_pts: pd.Series,
    target_count: int = 100,
    label: str = "LGB (SHAP)",
    do_shap_select: bool = True,
) -> Dict[str, Any]:
    """Run walk-forward CV with LightGBM residual model.

    Per-fold SHAP feature selection to avoid leakage.

    Args:
        pos_data: Position data with features.
        position: Position code.
        feature_cols: Candidate feature columns.
        heur_pts: Heuristic fantasy points.
        actual_pts: Actual fantasy points.
        target_count: Number of features to select.
        label: Model label for reporting.
        do_shap_select: Whether to do SHAP selection.

    Returns:
        Dict with model label, per-fold MAEs, mean MAE.
    """
    week_mask = pos_data["week"].between(3, 18)

    fold_results = []
    all_selected_features = []

    for val_season in VAL_SEASONS:
        train_mask = (pos_data["season"] < val_season) & week_mask
        val_mask = (pos_data["season"] == val_season) & week_mask

        train_idx = pos_data.index[train_mask]
        val_idx = pos_data.index[val_mask]

        # Compute residuals
        train_residual = actual_pts.loc[train_idx] - heur_pts.loc[train_idx]
        valid = train_residual.notna()
        train_idx = train_idx[valid.loc[train_idx].values]

        val_valid = (actual_pts.loc[val_idx].notna()) & (heur_pts.loc[val_idx].notna())
        val_idx = val_idx[val_valid.loc[val_idx].values]

        if len(train_idx) < 50 or len(val_idx) < 10:
            continue

        # Feature selection (per fold to avoid leakage)
        if do_shap_select:
            train_df = pos_data.loc[train_idx].copy()
            train_df["residual"] = train_residual.loc[train_idx]
            selected, shap_scores = _shap_select_features(
                train_df, feature_cols, "residual", target_count
            )
            all_selected_features.append(set(selected))
        else:
            selected = [f for f in feature_cols if f in pos_data.columns]

        if not selected:
            continue

        X_train_raw = pos_data.loc[train_idx, selected]
        y_train = train_residual.loc[train_idx]
        X_val_raw = pos_data.loc[val_idx, selected]

        # Impute
        imputer = SimpleImputer(strategy="median")
        X_train = imputer.fit_transform(X_train_raw)
        X_val = imputer.transform(X_val_raw)

        # Split training into train/early-stop sets (use most recent season as eval)
        train_seasons = sorted(pos_data.loc[train_idx, "season"].unique())
        if len(train_seasons) >= 2:
            eval_season = train_seasons[-1]
            es_mask = pos_data.loc[train_idx, "season"] == eval_season
            es_idx = np.where(es_mask.values)[0]
            tr_idx = np.where(~es_mask.values)[0]

            if len(tr_idx) > 50 and len(es_idx) > 10:
                model = lgb.LGBMRegressor(**RESIDUAL_LGB_PARAMS)
                model.fit(
                    X_train[tr_idx], y_train.iloc[tr_idx],
                    eval_set=[(X_train[es_idx], y_train.iloc[es_idx])],
                    callbacks=[lgb.early_stopping(50, verbose=False)],
                )
            else:
                model = lgb.LGBMRegressor(**RESIDUAL_LGB_PARAMS)
                model.fit(X_train, y_train)
        else:
            model = lgb.LGBMRegressor(**RESIDUAL_LGB_PARAMS)
            model.fit(X_train, y_train)

        # Predict
        residual_pred = model.predict(X_val)
        hybrid_pts = heur_pts.loc[val_idx].values + residual_pred
        hybrid_pts = np.clip(hybrid_pts, 0.0, None)

        heur_mae = float(mean_absolute_error(
            actual_pts.loc[val_idx].values, heur_pts.loc[val_idx].values
        ))
        hybrid_mae = float(mean_absolute_error(
            actual_pts.loc[val_idx].values, hybrid_pts
        ))

        fold_results.append({
            "val_season": val_season,
            "heur_mae": heur_mae,
            "hybrid_mae": hybrid_mae,
            "improvement_pct": (heur_mae - hybrid_mae) / heur_mae * 100,
            "n_train": len(train_idx),
            "n_val": len(val_idx),
            "n_features": len(selected),
            "best_iteration": getattr(model, "best_iteration_", -1),
        })

    # Feature stability (Jaccard similarity across folds)
    stability = None
    if len(all_selected_features) >= 2:
        jaccard_sims = []
        for i in range(len(all_selected_features)):
            for j in range(i + 1, len(all_selected_features)):
                a, b = all_selected_features[i], all_selected_features[j]
                jaccard = len(a & b) / len(a | b) if (a | b) else 0
                jaccard_sims.append(jaccard)
        stability = float(np.mean(jaccard_sims))

    mean_heur = np.mean([r["heur_mae"] for r in fold_results]) if fold_results else 0
    mean_hybrid = np.mean([r["hybrid_mae"] for r in fold_results]) if fold_results else 0

    return {
        "label": label,
        "n_features": target_count if do_shap_select else len(feature_cols),
        "feature_stability": stability,
        "folds": fold_results,
        "mean_heur_mae": float(mean_heur),
        "mean_hybrid_mae": float(mean_hybrid),
        "mean_improvement_pct": float(
            (mean_heur - mean_hybrid) / mean_heur * 100 if mean_heur > 0 else 0
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Experiment: LightGBM residual with SHAP feature selection"
    )
    parser.add_argument(
        "--positions", nargs="+", default=["WR", "TE", "RB", "QB"],
        help="Positions to test (default: WR TE RB QB)",
    )
    parser.add_argument(
        "--feature-counts", nargs="+", type=int, default=[60, 80, 100, 120],
        help="Feature counts to sweep (default: 60 80 100 120)",
    )
    parser.add_argument(
        "--scoring", default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    args = parser.parse_args()

    start_time = time.time()

    print("\n" + "=" * 70)
    print("EXPERIMENT: LightGBM Residual with SHAP Feature Selection")
    print("=" * 70)
    print(f"Positions: {args.positions}")
    print(f"Feature counts: {args.feature_counts}")
    print(f"Scoring: {args.scoring}")
    print(f"Val seasons: {VAL_SEASONS}")
    print()

    # Load data
    print("Loading player feature data...")
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        print("ERROR: No data assembled")
        return 1

    feature_cols = get_player_feature_columns(all_data)
    print(f"Loaded {len(all_data):,} rows, {len(feature_cols)} features")

    # Build opponent rankings
    print("Building opponent rankings...")
    opp_rankings = build_opp_rankings(PLAYER_DATA_SEASONS)

    all_results = {}

    for position in args.positions:
        print(f"\n{'=' * 70}")
        print(f"POSITION: {position}")
        print(f"{'=' * 70}")

        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

        if pos_data.empty:
            print(f"  No data for {position}")
            continue

        print(f"  Data: {len(pos_data):,} player-weeks")

        # Compute heuristic + actual
        print("  Computing heuristic predictions...")
        heur_pts = compute_production_heuristic(
            pos_data, position, opp_rankings, args.scoring
        )
        actual_pts = compute_actual_fantasy_points(pos_data, args.scoring)

        # Filter to position-relevant features
        pos_features = _filter_position_features(pos_data, feature_cols)
        print(f"  Position-relevant features: {len(pos_features)}")

        # Heuristic baseline MAE (weeks 3-18)
        week_mask = pos_data["week"].between(3, 18)
        valid = week_mask & heur_pts.notna() & actual_pts.notna()
        heur_mae = float(mean_absolute_error(
            actual_pts[valid].values, heur_pts[valid].values
        ))
        print(f"  Heuristic baseline MAE: {heur_mae:.4f}")

        position_results = {"heuristic_mae": heur_mae, "models": []}

        # 1. Ridge baseline (all available features)
        print(f"\n  [1/N] Ridge (all {len(pos_features)} features)...")
        ridge_all = run_ridge_cv(
            pos_data, position, pos_features, heur_pts, actual_pts,
            label=f"Ridge (all {len(pos_features)})"
        )
        position_results["models"].append(ridge_all)
        print(f"    MAE: {ridge_all['mean_hybrid_mae']:.4f} "
              f"({ridge_all['mean_improvement_pct']:+.1f}% vs heuristic)")

        # 2. LightGBM with SHAP selection at various feature counts
        for i, fc in enumerate(args.feature_counts):
            label = f"LGB SHAP-{fc}"
            print(f"\n  [{i+2}/N] {label}...")
            lgb_result = run_lgb_cv(
                pos_data, position, pos_features, heur_pts, actual_pts,
                target_count=fc, label=label, do_shap_select=True,
            )
            position_results["models"].append(lgb_result)
            stab = f", stability={lgb_result['feature_stability']:.2f}" if lgb_result.get("feature_stability") else ""
            print(f"    MAE: {lgb_result['mean_hybrid_mae']:.4f} "
                  f"({lgb_result['mean_improvement_pct']:+.1f}% vs heuristic{stab})")

        # 3. LightGBM with all features (no selection)
        label = f"LGB all {len(pos_features)}"
        print(f"\n  [N/N] {label}...")
        lgb_all = run_lgb_cv(
            pos_data, position, pos_features, heur_pts, actual_pts,
            target_count=len(pos_features), label=label, do_shap_select=False,
        )
        position_results["models"].append(lgb_all)
        print(f"    MAE: {lgb_all['mean_hybrid_mae']:.4f} "
              f"({lgb_all['mean_improvement_pct']:+.1f}% vs heuristic)")

        all_results[position] = position_results

    # Summary
    duration = time.time() - start_time
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    for position, res in all_results.items():
        print(f"\n  {position} (heuristic baseline: {res['heuristic_mae']:.4f}):")
        print(f"    {'Model':<25} {'MAE':>8} {'vs Heur':>10} {'Features':>10}")
        print(f"    {'-' * 55}")
        for m in res["models"]:
            print(f"    {m['label']:<25} {m['mean_hybrid_mae']:>8.4f} "
                  f"{m['mean_improvement_pct']:>+9.1f}% {m['n_features']:>10}")

    # Find best model per position
    print(f"\n  BEST MODELS:")
    for position, res in all_results.items():
        best = min(res["models"], key=lambda m: m["mean_hybrid_mae"])
        print(f"    {position}: {best['label']} (MAE={best['mean_hybrid_mae']:.4f}, "
              f"{best['mean_improvement_pct']:+.1f}%)")

    print(f"\n  Duration: {duration:.0f}s")

    # Save results
    output_dir = os.path.join(os.path.dirname(__file__), "..", ".planning", "phases", "phase-55")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "experiment_results.json")

    # Convert to serializable format
    serializable = {}
    for pos, res in all_results.items():
        serializable[pos] = {
            "heuristic_mae": res["heuristic_mae"],
            "models": res["models"],
        }

    with open(output_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\n  Results saved to {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
