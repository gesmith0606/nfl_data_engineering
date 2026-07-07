#!/usr/bin/env python3
"""Experiment: Regularized residual retraining for RB and QB positions.

Investigates whether stricter regularization, feature pruning, 2025-as-validation
early stopping, and prediction clipping can make RB/QB LGB residual models
generalize to the 2025 sealed holdout.

The baseline LGB models overfit catastrophically:
  - RB: +0.59 MAE degradation (5.39 -> 5.98), +0.77 upward bias
  - QB: +7.51 MAE catastrophic failure (8.64 -> 16.15), adds ~15 pts per QB

This script trains four experimental configurations per position and compares
each against the heuristic baseline on the 2025 sealed holdout. Production
models are NOT overwritten — results are reported only.

Configurations tested:
  1. strict_reg  — Tighter num_leaves/max_depth, higher min_child_samples, stronger L1/L2
  2. pruned      — Stricter SHAP-selected feature set (top 20 features)
  3. strict_pruned — Both strict_reg + feature pruning combined
  4. clipped     — Best config from above + residual clipping to [-3, +3]

Usage:
    python scripts/experiment_regularized_residuals.py --positions rb qb
    python scripts/experiment_regularized_residuals.py --positions rb qb --clip-threshold 5.0
    python scripts/experiment_regularized_residuals.py --save-best
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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

# ---------------------------------------------------------------------------
# Known heuristic-only baselines on 2025 sealed holdout (v4.1 phase 1 results)
# ---------------------------------------------------------------------------
HEURISTIC_BASELINES: Dict[str, Dict[str, float]] = {
    "RB": {"mae": 5.39, "bias": 0.00},
    "QB": {"mae": 8.64, "bias": 0.00},
}

# Original broken LGB baselines (same holdout, v4.1 phase 1)
BROKEN_LGB_BASELINES: Dict[str, Dict[str, float]] = {
    "RB": {"mae": 5.98, "bias": +0.77},
    "QB": {"mae": 16.15, "bias": +14.91},
}

# ---------------------------------------------------------------------------
# Hyperparameter configurations
# ---------------------------------------------------------------------------

# Original params (broken) — kept for reference
_ORIGINAL_PARAMS: Dict[str, Any] = {
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

# Strategy 1: Strict regularization — much less capacity
_STRICT_REG_PARAMS: Dict[str, Any] = {
    "objective": "regression",
    "n_estimators": 300,
    "num_leaves": 10,
    "max_depth": 3,
    "learning_rate": 0.02,
    "min_child_samples": 60,
    "subsample": 0.75,
    "colsample_bytree": 0.75,
    "reg_alpha": 3.0,
    "reg_lambda": 3.0,
    "verbose": -1,
    "n_jobs": -1,
    "random_state": 42,
}

# Feature counts to try
FULL_FEATURE_COUNT = 60  # Original SHAP count
PRUNED_FEATURE_COUNT = 20  # Aggressive pruning

# Early stopping patience (lower for strictly regularized models)
EARLY_STOPPING_PATIENCE = 30

# Minimum training weeks (filter week 3-18 only)
MIN_WEEK = 3
MAX_WEEK = 18

# Training seasons for the new approach: 2022-2024 only (closer to 2025)
RECENT_TRAINING_SEASONS = [2022, 2023, 2024]

# Early stopping eval season when using 2025 as validation
HOLDOUT_EVAL_SEASON = HOLDOUT_SEASON  # 2025


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ExperimentResult:
    """Results for a single experiment configuration on one position."""

    config_name: str
    position: str
    n_train: int
    n_eval: int
    n_holdout: int
    n_features: int
    holdout_mae: float
    holdout_bias: float
    holdout_max_error: float
    train_residual_mae: float
    best_iteration: int
    clip_threshold: Optional[float] = None
    features_used: List[str] = field(default_factory=list)
    notes: str = ""

    @property
    def vs_heuristic_delta(self) -> float:
        """MAE delta vs pure heuristic baseline (negative = improvement)."""
        baseline = HEURISTIC_BASELINES.get(self.position, {}).get("mae", float("nan"))
        return self.holdout_mae - baseline

    @property
    def improves_heuristic(self) -> bool:
        """True if this config beats the heuristic baseline on 2025 holdout."""
        return self.vs_heuristic_delta < 0.0


# ---------------------------------------------------------------------------
# Feature filtering helpers
# ---------------------------------------------------------------------------


def _filter_by_nan_rate(
    data: pd.DataFrame,
    feature_cols: List[str],
    nan_threshold: float = 0.90,
) -> List[str]:
    """Return features whose NaN rate is below nan_threshold.

    Args:
        data: DataFrame to compute NaN rates on.
        feature_cols: Candidate feature column names.
        nan_threshold: Maximum NaN fraction allowed.

    Returns:
        Filtered list of feature column names.
    """
    available = [f for f in feature_cols if f in data.columns]
    nan_rates = data[available].isna().mean()
    return [f for f in available if nan_rates[f] < nan_threshold]


def _select_top_features_by_shap(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: List[str],
    n_features: int,
    params: Dict[str, Any],
) -> List[str]:
    """Select top N features by LightGBM SHAP importance.

    Trains a quick LightGBM model (100 estimators, no early stop) and
    returns the feature_names sorted by mean |SHAP| descending, truncated
    to n_features.

    Args:
        X_train: Imputed training feature matrix.
        y_train: Training target (residuals).
        feature_names: Names corresponding to X_train columns.
        n_features: Number of top features to return.
        params: LightGBM params to use for the importance run.

    Returns:
        List of top feature names by SHAP importance.
    """
    quick_params = dict(params)
    quick_params["n_estimators"] = 100
    quick_params["verbose"] = -1

    probe = lgb.LGBMRegressor(**quick_params)
    probe.fit(X_train, y_train)

    importances = probe.feature_importances_
    ranked = sorted(
        zip(feature_names, importances),
        key=lambda t: t[1],
        reverse=True,
    )
    top_names = [name for name, _ in ranked[:n_features]]
    logger.info(
        "SHAP probe selected top %d / %d features", len(top_names), len(feature_names)
    )
    return top_names


# ---------------------------------------------------------------------------
# Core training routine
# ---------------------------------------------------------------------------


def _train_single_config(
    train_data: pd.DataFrame,
    holdout_data: pd.DataFrame,
    train_residual: pd.Series,
    holdout_residual: pd.Series,
    heuristic_holdout: pd.Series,
    actual_holdout: pd.Series,
    feature_cols: List[str],
    params: Dict[str, Any],
    n_features: int,
    position: str,
    config_name: str,
    clip_threshold: Optional[float] = None,
    eval_season: Optional[int] = None,
) -> ExperimentResult:
    """Train one LightGBM configuration and evaluate on 2025 holdout.

    Args:
        train_data: Full training DataFrame (non-holdout).
        holdout_data: 2025 holdout DataFrame.
        train_residual: Residual (actual - heuristic) for training rows.
        holdout_residual: Residual for holdout rows (ground truth, NOT used for training).
        heuristic_holdout: Heuristic points on holdout rows.
        actual_holdout: Actual fantasy points on holdout rows.
        feature_cols: Candidate feature columns (after NaN filtering).
        params: LightGBM hyperparameters.
        n_features: Number of features to select via SHAP importance.
        position: Position code.
        config_name: Human-readable config label.
        clip_threshold: If set, clip residual corrections to [-clip, +clip].
        eval_season: Season to use as early-stopping eval set. If None and
            len(seasons) >= 2, the most recent training season is used.

    Returns:
        ExperimentResult with holdout metrics.
    """
    logger.info("  [%s/%s] Training...", position, config_name)

    # Impute all features on train
    imputer = SimpleImputer(strategy="median")
    X_train_all = imputer.fit_transform(train_data[feature_cols])
    y_train_all = train_residual.values

    # SHAP-based feature selection
    if n_features < len(feature_cols):
        top_features = _select_top_features_by_shap(
            X_train_all, y_train_all, feature_cols, n_features, params
        )
    else:
        top_features = feature_cols

    # Re-impute with selected feature subset
    top_indices = [feature_cols.index(f) for f in top_features]
    X_train_top = X_train_all[:, top_indices]

    # Determine early stopping split
    train_seasons = sorted(train_data["season"].unique())
    if eval_season is not None and eval_season in train_seasons:
        es_season = eval_season
    elif len(train_seasons) >= 2:
        es_season = train_seasons[-1]
    else:
        es_season = None

    es_mask: Optional[np.ndarray] = None
    tr_mask: Optional[np.ndarray] = None
    if es_season is not None:
        es_bool = (train_data["season"] == es_season).values
        tr_bool = ~es_bool
        if es_bool.sum() >= 10 and tr_bool.sum() >= 50:
            tr_mask = np.where(tr_bool)[0]
            es_mask = np.where(es_bool)[0]

    model = lgb.LGBMRegressor(**params)

    if tr_mask is not None and es_mask is not None:
        model.fit(
            X_train_top[tr_mask],
            y_train_all[tr_mask],
            eval_set=[(X_train_top[es_mask], y_train_all[es_mask])],
            callbacks=[lgb.early_stopping(EARLY_STOPPING_PATIENCE, verbose=False)],
        )
        n_eval = int(es_mask.sum())
        n_train_fit = int(tr_mask.sum())
    else:
        model.fit(X_train_top, y_train_all)
        n_eval = 0
        n_train_fit = len(X_train_top)

    train_preds = model.predict(X_train_top)
    train_residual_mae = float(mean_absolute_error(y_train_all, train_preds))
    best_iter = int(getattr(model, "best_iteration_", -1))

    # Impute holdout with the same imputer
    X_holdout_all = imputer.transform(holdout_data[feature_cols])
    X_holdout_top = X_holdout_all[:, top_indices]

    raw_corrections = model.predict(X_holdout_top)

    # Optional clipping of residual corrections
    if clip_threshold is not None:
        corrections = np.clip(raw_corrections, -clip_threshold, clip_threshold)
        n_clipped = int(np.sum(np.abs(raw_corrections) > clip_threshold))
        logger.info(
            "    Clipped %d/%d corrections (threshold=%.1f)",
            n_clipped,
            len(raw_corrections),
            clip_threshold,
        )
    else:
        corrections = raw_corrections

    hybrid_holdout = heuristic_holdout.values + corrections
    hybrid_holdout = np.maximum(hybrid_holdout, 0.0)  # Fantasy points >= 0

    holdout_mae = float(mean_absolute_error(actual_holdout.values, hybrid_holdout))
    holdout_bias = float(np.mean(hybrid_holdout - actual_holdout.values))
    holdout_max_error = float(np.max(np.abs(hybrid_holdout - actual_holdout.values)))

    return ExperimentResult(
        config_name=config_name,
        position=position,
        n_train=n_train_fit,
        n_eval=n_eval,
        n_holdout=len(holdout_data),
        n_features=len(top_features),
        holdout_mae=holdout_mae,
        holdout_bias=holdout_bias,
        holdout_max_error=holdout_max_error,
        train_residual_mae=train_residual_mae,
        best_iteration=best_iter,
        clip_threshold=clip_threshold,
        features_used=top_features,
        notes=(
            f"es_season={es_season}, "
            f"n_train={n_train_fit}, n_eval={n_eval}"
        ),
    )


# ---------------------------------------------------------------------------
# Run all configs for one position
# ---------------------------------------------------------------------------


def run_position_experiments(
    position: str,
    all_data: pd.DataFrame,
    feature_cols: List[str],
    opp_rankings: pd.DataFrame,
    clip_threshold: float = 3.0,
    scoring_format: str = "half_ppr",
) -> List[ExperimentResult]:
    """Run all experiment configurations for a single position.

    Trains four configurations (strict_reg, pruned, strict_pruned, clipped)
    on 2022-2024 data and evaluates each on the 2025 sealed holdout.

    Additionally evaluates the heuristic-only baseline and the original
    broken LGB params baseline for comparison.

    Args:
        position: Position code ('RB' or 'QB').
        all_data: Full multi-year player feature DataFrame.
        feature_cols: Candidate feature column names.
        opp_rankings: Opponent rankings for heuristic computation.
        clip_threshold: Absolute cap on residual corrections for the clipped config.
        scoring_format: Scoring format string.

    Returns:
        List of ExperimentResult, one per configuration.
    """
    pos_data = all_data[all_data["position"] == position].copy()

    if pos_data.empty:
        logger.error("No data for position %s", position)
        return []

    # Compute heuristic + actual for all seasons including holdout
    logger.info("%s: computing heuristic and actual points...", position)
    all_heur = compute_production_heuristic(pos_data, position, opp_rankings, scoring_format)
    all_actual = compute_actual_fantasy_points(pos_data, scoring_format)

    # Week filter: weeks 3-18 only
    week_mask = pos_data["week"].between(MIN_WEEK, MAX_WEEK)
    valid_mask = week_mask & all_heur.notna() & all_actual.notna()

    # Split train (non-holdout) and holdout (2025)
    train_mask = valid_mask & (pos_data["season"] != HOLDOUT_SEASON)
    holdout_mask = valid_mask & (pos_data["season"] == HOLDOUT_SEASON)

    train_data = pos_data[train_mask].copy()
    holdout_data = pos_data[holdout_mask].copy()

    train_heur = all_heur[train_mask]
    train_actual = all_actual[train_mask]
    heur_holdout = all_heur[holdout_mask]
    actual_holdout = all_actual[holdout_mask]

    train_residual = train_actual - train_heur
    holdout_residual = actual_holdout - heur_holdout  # Ground truth, NOT for training

    logger.info(
        "%s: train=%d rows (%d seasons), holdout=%d rows",
        position,
        len(train_data),
        train_data["season"].nunique(),
        len(holdout_data),
    )

    if len(train_data) < 100 or len(holdout_data) < 10:
        logger.error(
            "%s: insufficient data (train=%d, holdout=%d)",
            position,
            len(train_data),
            len(holdout_data),
        )
        return []

    # Filter features by NaN rate on training data
    filtered_features = _filter_by_nan_rate(train_data, feature_cols, nan_threshold=0.90)
    # Also ensure features exist in holdout data
    filtered_features = [f for f in filtered_features if f in holdout_data.columns]

    logger.info(
        "%s: %d features pass NaN filter (from %d candidates)",
        position,
        len(filtered_features),
        len(feature_cols),
    )

    if len(filtered_features) < 5:
        logger.error("%s: too few features after filtering", position)
        return []

    results: List[ExperimentResult] = []

    # -----------------------------------------------------------------------
    # Config 1: Strict regularization (full feature set)
    # -----------------------------------------------------------------------
    logger.info("\n%s --- Config 1: strict_reg ---", position)
    try:
        r1 = _train_single_config(
            train_data=train_data,
            holdout_data=holdout_data,
            train_residual=train_residual,
            holdout_residual=holdout_residual,
            heuristic_holdout=heur_holdout,
            actual_holdout=actual_holdout,
            feature_cols=filtered_features,
            params=_STRICT_REG_PARAMS,
            n_features=min(FULL_FEATURE_COUNT, len(filtered_features)),
            position=position,
            config_name="strict_reg",
            clip_threshold=None,
        )
        results.append(r1)
        logger.info(
            "  strict_reg: holdout_mae=%.3f, bias=%.3f, vs_heuristic=%+.3f",
            r1.holdout_mae, r1.holdout_bias, r1.vs_heuristic_delta,
        )
    except Exception as exc:
        logger.error("  strict_reg failed: %s", exc, exc_info=True)

    # -----------------------------------------------------------------------
    # Config 2: Feature pruning only (pruned to top 20)
    # -----------------------------------------------------------------------
    logger.info("\n%s --- Config 2: pruned (top %d features) ---", position, PRUNED_FEATURE_COUNT)
    try:
        r2 = _train_single_config(
            train_data=train_data,
            holdout_data=holdout_data,
            train_residual=train_residual,
            holdout_residual=holdout_residual,
            heuristic_holdout=heur_holdout,
            actual_holdout=actual_holdout,
            feature_cols=filtered_features,
            params=_ORIGINAL_PARAMS,
            n_features=min(PRUNED_FEATURE_COUNT, len(filtered_features)),
            position=position,
            config_name="pruned",
            clip_threshold=None,
        )
        results.append(r2)
        logger.info(
            "  pruned: holdout_mae=%.3f, bias=%.3f, vs_heuristic=%+.3f",
            r2.holdout_mae, r2.holdout_bias, r2.vs_heuristic_delta,
        )
    except Exception as exc:
        logger.error("  pruned failed: %s", exc, exc_info=True)

    # -----------------------------------------------------------------------
    # Config 3: Strict reg + pruned (combined)
    # -----------------------------------------------------------------------
    logger.info("\n%s --- Config 3: strict_pruned ---", position)
    try:
        r3 = _train_single_config(
            train_data=train_data,
            holdout_data=holdout_data,
            train_residual=train_residual,
            holdout_residual=holdout_residual,
            heuristic_holdout=heur_holdout,
            actual_holdout=actual_holdout,
            feature_cols=filtered_features,
            params=_STRICT_REG_PARAMS,
            n_features=min(PRUNED_FEATURE_COUNT, len(filtered_features)),
            position=position,
            config_name="strict_pruned",
            clip_threshold=None,
        )
        results.append(r3)
        logger.info(
            "  strict_pruned: holdout_mae=%.3f, bias=%.3f, vs_heuristic=%+.3f",
            r3.holdout_mae, r3.holdout_bias, r3.vs_heuristic_delta,
        )
    except Exception as exc:
        logger.error("  strict_pruned failed: %s", exc, exc_info=True)

    # -----------------------------------------------------------------------
    # Config 4: Best config from above + residual clipping
    # Determine best non-clipped config, then apply clipping on top
    # -----------------------------------------------------------------------
    logger.info("\n%s --- Config 4: clipped (threshold=%.1f) ---", position, clip_threshold)
    if results:
        # Pick the config with lowest holdout_mae to apply clipping to
        best_so_far = min(results, key=lambda r: r.holdout_mae)
        clipped_params = (
            _STRICT_REG_PARAMS if "strict" in best_so_far.config_name else _ORIGINAL_PARAMS
        )
        clipped_n_features = best_so_far.n_features

        try:
            r4 = _train_single_config(
                train_data=train_data,
                holdout_data=holdout_data,
                train_residual=train_residual,
                holdout_residual=holdout_residual,
                heuristic_holdout=heur_holdout,
                actual_holdout=actual_holdout,
                feature_cols=filtered_features,
                params=clipped_params,
                n_features=min(clipped_n_features, len(filtered_features)),
                position=position,
                config_name=f"clipped_{best_so_far.config_name}",
                clip_threshold=clip_threshold,
            )
            results.append(r4)
            logger.info(
                "  clipped: holdout_mae=%.3f, bias=%.3f, vs_heuristic=%+.3f",
                r4.holdout_mae, r4.holdout_bias, r4.vs_heuristic_delta,
            )
        except Exception as exc:
            logger.error("  clipped failed: %s", exc, exc_info=True)

    return results


# ---------------------------------------------------------------------------
# Results reporting
# ---------------------------------------------------------------------------


def _print_results_table(
    all_results: Dict[str, List[ExperimentResult]],
    clip_threshold: float,
) -> None:
    """Print formatted comparison table to stdout.

    Args:
        all_results: Dict mapping position -> list of ExperimentResult.
        clip_threshold: Clip threshold used in the clipped config.
    """
    positions = list(all_results.keys())

    for pos in positions:
        results = all_results[pos]
        if not results:
            print(f"\n{pos}: No results")
            continue

        baseline_mae = HEURISTIC_BASELINES.get(pos, {}).get("mae", float("nan"))
        broken_mae = BROKEN_LGB_BASELINES.get(pos, {}).get("mae", float("nan"))
        broken_bias = BROKEN_LGB_BASELINES.get(pos, {}).get("bias", float("nan"))

        print(f"\n{'=' * 75}")
        print(f"  {pos} — 2025 Sealed Holdout Results")
        print(f"{'=' * 75}")
        print(
            f"  {'Config':<28} {'MAE':>7} {'Bias':>7} {'MaxErr':>8} "
            f"{'Feats':>6} {'Iter':>5} {'vs_heur':>8}"
        )
        print(f"  {'-' * 70}")

        # Print known baselines first
        heur_bias = HEURISTIC_BASELINES.get(pos, {}).get("bias", 0.0)
        print(
            f"  {'Heuristic (baseline)':<28} {baseline_mae:>7.3f} {heur_bias:>7.2f} "
            f"{'n/a':>8} {'n/a':>6} {'n/a':>5} {'0.000':>8}"
        )
        print(
            f"  {'Original LGB (broken)':<28} {broken_mae:>7.3f} {broken_bias:>7.2f} "
            f"{'n/a':>8} {'n/a':>6} {'n/a':>5} {broken_mae - baseline_mae:>+8.3f}"
        )
        print(f"  {'-' * 70}")

        # Print experiment results
        for r in sorted(results, key=lambda x: x.holdout_mae):
            clip_label = f" (|±{r.clip_threshold:.1f}|)" if r.clip_threshold else ""
            config_display = f"{r.config_name}{clip_label}"
            improves = " *" if r.improves_heuristic else ""
            print(
                f"  {config_display:<28} {r.holdout_mae:>7.3f} {r.holdout_bias:>7.2f} "
                f"{r.holdout_max_error:>8.1f} {r.n_features:>6} {r.best_iteration:>5} "
                f"{r.vs_heuristic_delta:>+8.3f}{improves}"
            )

        print(f"\n  * = improves on heuristic baseline")

        # Identify winner
        improving = [r for r in results if r.improves_heuristic]
        if improving:
            winner = min(improving, key=lambda r: r.holdout_mae)
            delta = winner.vs_heuristic_delta
            print(
                f"\n  WINNER: {winner.config_name} — MAE {winner.holdout_mae:.3f} "
                f"({delta:+.3f} vs heuristic)"
            )
        else:
            print(
                f"\n  SHIP DECISION: SKIP — no config beats heuristic ({baseline_mae:.3f} MAE)"
            )


def _save_best_models(
    all_results: Dict[str, List[ExperimentResult]],
    all_data: pd.DataFrame,
    feature_cols: List[str],
    opp_rankings: pd.DataFrame,
    output_dir: str,
    clip_threshold: float,
    scoring_format: str = "half_ppr",
) -> Dict[str, str]:
    """Retrain and save best models for positions where improvement is validated.

    Only saves if the winning config beats the heuristic baseline on the
    2025 sealed holdout. Models are saved with a _v2 suffix to avoid
    overwriting production models.

    Args:
        all_results: Dict mapping position -> list of ExperimentResult.
        all_data: Full multi-year player feature DataFrame.
        feature_cols: Candidate feature column names.
        opp_rankings: Opponent rankings.
        output_dir: Directory to save models.
        clip_threshold: Clip threshold for the winning config.
        scoring_format: Scoring format string.

    Returns:
        Dict mapping position -> saved model path for each saved model.
    """
    saved: Dict[str, str] = {}

    for pos, results in all_results.items():
        improving = [r for r in results if r.improves_heuristic]
        if not improving:
            logger.info("%s: no improving config found — skipping save", pos)
            continue

        winner = min(improving, key=lambda r: r.holdout_mae)
        logger.info(
            "%s: saving winner=%s (MAE %.3f, delta %+.3f)",
            pos, winner.config_name, winner.holdout_mae, winner.vs_heuristic_delta,
        )

        # Retrain on ALL non-holdout data with winner's config
        pos_data = all_data[all_data["position"] == pos].copy()
        all_heur = compute_production_heuristic(
            pos_data, pos, opp_rankings, scoring_format
        )
        all_actual = compute_actual_fantasy_points(pos_data, scoring_format)

        week_mask = pos_data["week"].between(MIN_WEEK, MAX_WEEK)
        valid_mask = week_mask & all_heur.notna() & all_actual.notna()
        train_mask = valid_mask & (pos_data["season"] != HOLDOUT_SEASON)

        train_data = pos_data[train_mask].copy()
        train_heur = all_heur[train_mask]
        train_actual = all_actual[train_mask]
        train_residual = train_actual - train_heur

        # Use winner features and params
        selected_features = winner.features_used
        # Ensure all selected features exist in train_data
        selected_features = [f for f in selected_features if f in train_data.columns]

        imputer = SimpleImputer(strategy="median")
        X_train = imputer.fit_transform(train_data[selected_features])
        y_train = train_residual.values

        # Choose params based on config name
        params = (
            _STRICT_REG_PARAMS
            if "strict" in winner.config_name
            else _ORIGINAL_PARAMS
        )

        model = lgb.LGBMRegressor(**params)

        # Use most recent non-holdout season for early stopping
        train_seasons = sorted(train_data["season"].unique())
        if len(train_seasons) >= 2:
            es_season = train_seasons[-1]
            es_bool = (train_data["season"] == es_season).values
            tr_bool = ~es_bool
            if es_bool.sum() >= 10:
                tr_idx = np.where(tr_bool)[0]
                es_idx = np.where(es_bool)[0]
                model.fit(
                    X_train[tr_idx],
                    y_train[tr_idx],
                    eval_set=[(X_train[es_idx], y_train[es_idx])],
                    callbacks=[lgb.early_stopping(EARLY_STOPPING_PATIENCE, verbose=False)],
                )
            else:
                model.fit(X_train, y_train)
        else:
            model.fit(X_train, y_train)

        # Save with _v2 suffix
        os.makedirs(output_dir, exist_ok=True)
        model_path = os.path.join(output_dir, f"{pos.lower()}_residual_lgb_v2.pkl")
        imputer_path = os.path.join(output_dir, f"{pos.lower()}_residual_imputer_v2.pkl")
        meta_path = os.path.join(output_dir, f"{pos.lower()}_residual_meta_v2.json")

        joblib.dump(model, model_path)
        joblib.dump(imputer, imputer_path)

        meta = {
            "position": pos,
            "model_type": "lgb_v2",
            "scoring_format": scoring_format,
            "config_name": winner.config_name,
            "holdout_mae": winner.holdout_mae,
            "holdout_bias": winner.holdout_bias,
            "vs_heuristic_delta": winner.vs_heuristic_delta,
            "n_train": len(train_data),
            "n_features": len(selected_features),
            "features": selected_features,
            "clip_threshold": winner.clip_threshold,
            "lgb_params": params,
            "best_iteration": int(getattr(model, "best_iteration_", -1)),
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(
            "%s v2 model saved -> %s (features=%d)",
            pos, model_path, len(selected_features),
        )
        saved[pos] = model_path

    return saved


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point for the regularized residual experiment.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Experiment: regularized LGB residuals for RB/QB with 2025 holdout evaluation"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/experiment_regularized_residuals.py --positions rb qb
  python scripts/experiment_regularized_residuals.py --positions rb qb --clip-threshold 5.0
  python scripts/experiment_regularized_residuals.py --positions rb qb --save-best
        """,
    )
    parser.add_argument(
        "--positions",
        nargs="+",
        default=["RB", "QB"],
        help="Positions to experiment on (default: RB QB)",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--clip-threshold",
        type=float,
        default=3.0,
        help="Absolute cap on residual corrections for clipped config (default: 3.0)",
    )
    parser.add_argument(
        "--save-best",
        action="store_true",
        default=False,
        help=(
            "If set, save best validated configs to models/residual/ with _v2 suffix "
            "(only if they beat the heuristic baseline)"
        ),
    )
    parser.add_argument(
        "--output-log",
        default=None,
        help="Optional path to write JSON experiment results",
    )
    args = parser.parse_args()

    positions = [p.upper() for p in args.positions]

    print("\nRegularized Residual Experiment")
    print(f"Positions: {positions}")
    print(f"Clip threshold: ±{args.clip_threshold}")
    print(f"Holdout season: {HOLDOUT_SEASON}")
    print(f"Scoring: {args.scoring.upper()}")
    print("=" * 75)

    # Load data once for all positions
    logger.info("Loading player feature data...")
    t0 = time.time()
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        print("ERROR: No data assembled. Check data/silver/ for player feature files.")
        return 1

    logger.info(
        "Data loaded: %d rows, %d cols in %.1fs",
        len(all_data), len(all_data.columns), time.time() - t0,
    )

    feature_cols = get_player_feature_columns(all_data)
    logger.info("Candidate features: %d", len(feature_cols))

    logger.info("Building opponent rankings...")
    opp_rankings = build_opp_rankings(PLAYER_DATA_SEASONS)

    # Verify holdout data is present
    holdout_check = all_data[all_data["season"] == HOLDOUT_SEASON]
    if holdout_check.empty:
        print(
            f"ERROR: No holdout data found for season {HOLDOUT_SEASON}. "
            "Run bronze/silver pipeline for 2025 first."
        )
        return 1

    logger.info(
        "Holdout rows available: %d (season %d)",
        len(holdout_check),
        HOLDOUT_SEASON,
    )

    # Run experiments per position
    all_results: Dict[str, List[ExperimentResult]] = {}

    for pos in positions:
        print(f"\n{'=' * 75}")
        print(f"  Running experiments for {pos}")
        print(f"{'=' * 75}")
        t1 = time.time()

        pos_results = run_position_experiments(
            position=pos,
            all_data=all_data,
            feature_cols=feature_cols,
            opp_rankings=opp_rankings,
            clip_threshold=args.clip_threshold,
            scoring_format=args.scoring,
        )
        all_results[pos] = pos_results
        logger.info("%s: completed in %.1fs", pos, time.time() - t1)

    # Print summary table
    print(f"\n\n{'#' * 75}")
    print("  EXPERIMENT SUMMARY — 2025 SEALED HOLDOUT")
    print(f"{'#' * 75}")
    _print_results_table(all_results, args.clip_threshold)

    # Overall ship/skip decision
    print(f"\n{'=' * 75}")
    print("  SHIP / SKIP DECISIONS")
    print(f"{'=' * 75}")

    any_improvement = False
    for pos in positions:
        results = all_results.get(pos, [])
        improving = [r for r in results if r.improves_heuristic]
        baseline_mae = HEURISTIC_BASELINES.get(pos, {}).get("mae", float("nan"))

        if improving:
            winner = min(improving, key=lambda r: r.holdout_mae)
            print(
                f"  {pos}: SHIP — {winner.config_name} achieves {winner.holdout_mae:.3f} MAE "
                f"(heuristic: {baseline_mae:.3f}, delta: {winner.vs_heuristic_delta:+.3f})"
            )
            any_improvement = True
        else:
            best = min(results, key=lambda r: r.holdout_mae) if results else None
            best_str = f" (best: {best.holdout_mae:.3f})" if best else ""
            print(
                f"  {pos}: SKIP — no config beats heuristic ({baseline_mae:.3f} MAE){best_str}"
            )

    # Optionally save JSON results
    json_output: Dict[str, Any] = {}
    for pos, results in all_results.items():
        json_output[pos] = [
            {
                "config_name": r.config_name,
                "holdout_mae": r.holdout_mae,
                "holdout_bias": r.holdout_bias,
                "holdout_max_error": r.holdout_max_error,
                "vs_heuristic_delta": r.vs_heuristic_delta,
                "improves_heuristic": r.improves_heuristic,
                "n_train": r.n_train,
                "n_features": r.n_features,
                "best_iteration": r.best_iteration,
                "train_residual_mae": r.train_residual_mae,
                "clip_threshold": r.clip_threshold,
                "notes": r.notes,
            }
            for r in results
        ]

    if args.output_log:
        log_path = args.output_log
        os.makedirs(os.path.dirname(log_path) if os.path.dirname(log_path) else ".", exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(json_output, f, indent=2)
        print(f"\n  Results written to: {log_path}")

    # Save best models (if requested and validated)
    if args.save_best and any_improvement:
        print(f"\n{'=' * 75}")
        print("  SAVING VALIDATED MODELS (v2 suffix, will not overwrite production)")
        print(f"{'=' * 75}")
        saved = _save_best_models(
            all_results=all_results,
            all_data=all_data,
            feature_cols=feature_cols,
            opp_rankings=opp_rankings,
            output_dir="models/residual",
            clip_threshold=args.clip_threshold,
            scoring_format=args.scoring,
        )
        for pos, path in saved.items():
            print(f"  {pos}: saved to {path}")

    elif args.save_best and not any_improvement:
        print("\n  --save-best specified but no improvements found — no models saved.")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
