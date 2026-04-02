"""Hybrid projection: blend heuristic + ML or train residual correction models.

Approach 1 (Simple Blend):
    blended = alpha * heuristic + (1 - alpha) * ML
    Search alpha per position to minimise MAE.

Approach 2 (Residual Model):
    target = actual_fantasy_points - heuristic_fantasy_points
    Train RidgeCV on features -> residual, then final = heuristic + ridge.predict()

Exports:
    compute_fantasy_points_from_preds: Convert pred_{stat} columns to fantasy points.
    evaluate_blend: Grid-search alpha for heuristic-ML blend.
    train_residual_model: Walk-forward CV residual correction model.
    evaluate_residual_model: Evaluate residual model MAE per position.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline

from projection_engine import POSITION_STAT_PROFILE
from scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fantasy point conversion from pred_{stat} columns
# ---------------------------------------------------------------------------


def compute_fantasy_points_from_preds(
    df: pd.DataFrame,
    position: str,
    scoring_format: str = "half_ppr",
    pred_prefix: str = "pred_",
    output_col: str = "pred_fantasy_points",
) -> pd.Series:
    """Convert pred_{stat} columns to a single fantasy point series.

    Renames pred_{stat} -> stat, runs calculate_fantasy_points_df,
    and returns the resulting series. Does NOT modify the input df.

    Args:
        df: DataFrame with pred_{stat} columns.
        position: Position code (for stat list).
        scoring_format: Scoring format string.
        pred_prefix: Prefix on predicted stat columns.
        output_col: Name for the output fantasy points column.

    Returns:
        pd.Series of predicted fantasy points, aligned to df.index.
    """
    stats = POSITION_STAT_PROFILE.get(position, [])
    work = df.copy()

    rename_map = {}
    drop_cols = []
    for stat in stats:
        pred_col = f"{pred_prefix}{stat}"
        if pred_col in work.columns:
            rename_map[pred_col] = stat
            if stat in work.columns:
                drop_cols.append(stat)

    work = work.drop(columns=drop_cols, errors="ignore")
    work = work.rename(columns=rename_map)
    work = calculate_fantasy_points_df(
        work, scoring_format=scoring_format, output_col=output_col
    )
    return work[output_col]


def compute_actual_fantasy_points(
    df: pd.DataFrame,
    scoring_format: str = "half_ppr",
    output_col: str = "actual_fantasy_points",
) -> pd.Series:
    """Compute actual fantasy points from raw stat columns.

    Args:
        df: DataFrame with actual stat columns (passing_yards, etc.).
        scoring_format: Scoring format string.
        output_col: Output column name.

    Returns:
        pd.Series of actual fantasy points aligned to df.index.
    """
    work = calculate_fantasy_points_df(
        df.copy(), scoring_format=scoring_format, output_col=output_col
    )
    return work[output_col]


# ---------------------------------------------------------------------------
# Approach 1: Simple Blend
# ---------------------------------------------------------------------------


def evaluate_blend(
    heuristic_pts: pd.Series,
    ml_pts: pd.Series,
    actual_pts: pd.Series,
    alphas: Optional[List[float]] = None,
) -> Tuple[float, float, Dict[float, float]]:
    """Grid-search alpha for heuristic-ML blend.

    blended = alpha * heuristic + (1 - alpha) * ML

    Args:
        heuristic_pts: Heuristic fantasy point predictions.
        ml_pts: ML fantasy point predictions.
        actual_pts: Actual fantasy points.
        alphas: Alpha values to test. Default [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8].

    Returns:
        Tuple of (best_alpha, best_mae, dict of alpha -> mae).
    """
    if alphas is None:
        alphas = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

    # Align on non-NaN rows
    valid = heuristic_pts.notna() & ml_pts.notna() & actual_pts.notna()
    h = heuristic_pts[valid].values
    m = ml_pts[valid].values
    a = actual_pts[valid].values

    results: Dict[float, float] = {}
    for alpha in alphas:
        blended = alpha * h + (1 - alpha) * m
        mae = float(mean_absolute_error(a, blended))
        results[alpha] = mae

    best_alpha = min(results, key=results.get)  # type: ignore[arg-type]
    return best_alpha, results[best_alpha], results


# ---------------------------------------------------------------------------
# Approach 2: Residual Model
# ---------------------------------------------------------------------------


def _create_residual_pipeline() -> Pipeline:
    """Create a RidgeCV pipeline for residual prediction.

    Uses median imputation and broad alpha search.

    Returns:
        sklearn Pipeline with SimpleImputer + RidgeCV.
    """
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
        ]
    )


def train_residual_model(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols: List[str],
    scoring_format: str = "half_ppr",
    val_seasons: Optional[List[int]] = None,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Train residual correction model with walk-forward CV.

    For each validation season:
    1. Generate heuristic predictions on train+val
    2. Compute residual = actual - heuristic
    3. Train Ridge on features -> residual (train only)
    4. Predict residual on val
    5. Final = heuristic + predicted_residual

    Args:
        pos_data: Position-filtered DataFrame with features and actual stats.
        position: Position code.
        feature_cols: Feature column names.
        scoring_format: Scoring format.
        val_seasons: Validation seasons. Default [2022, 2023, 2024].

    Returns:
        Tuple of:
        - results dict with mean_mae, fold_details
        - oof_df with columns [idx, season, week, heuristic_pts,
          residual_pred, hybrid_pts, actual_pts]
    """
    from player_model_training import generate_heuristic_predictions

    if val_seasons is None:
        val_seasons = [2022, 2023, 2024]

    available_features = [f for f in feature_cols if f in pos_data.columns]
    if not available_features:
        logger.warning("No features available for residual model")
        return {"mean_mae": 0.0, "fold_details": []}, pd.DataFrame()

    # Pre-compute heuristic predictions for all rows
    heur_df = generate_heuristic_predictions(pos_data, position)
    heur_pts = compute_fantasy_points_from_preds(
        heur_df, position, scoring_format, output_col="heuristic_pts"
    )
    actual_pts = compute_actual_fantasy_points(
        pos_data, scoring_format, output_col="actual_pts"
    )

    # Filter to weeks 3-18 only
    week_mask = pos_data["week"].between(3, 18)

    fold_maes: List[float] = []
    fold_details: List[Dict[str, Any]] = []
    oof_records: List[pd.DataFrame] = []

    for val_season in val_seasons:
        train_mask = (pos_data["season"] < val_season) & week_mask
        val_mask = (pos_data["season"] == val_season) & week_mask

        train_idx = pos_data.index[train_mask]
        val_idx = pos_data.index[val_mask]

        if len(train_idx) < 50 or len(val_idx) < 10:
            logger.info(
                "Skipping fold val_season=%d: train=%d, val=%d",
                val_season,
                len(train_idx),
                len(val_idx),
            )
            continue

        # Residual = actual - heuristic
        train_residual = actual_pts.loc[train_idx] - heur_pts.loc[train_idx]
        val_residual_actual = actual_pts.loc[val_idx] - heur_pts.loc[val_idx]

        # Drop rows where residual is NaN
        train_valid = train_residual.notna()
        val_valid = val_residual_actual.notna()

        train_idx_valid = train_idx[train_valid.loc[train_idx].values]
        val_idx_valid = val_idx[val_valid.loc[val_idx].values]

        if len(train_idx_valid) < 50 or len(val_idx_valid) < 10:
            continue

        X_train = pos_data.loc[train_idx_valid, available_features]
        y_train = train_residual.loc[train_idx_valid]
        X_val = pos_data.loc[val_idx_valid, available_features]

        # Train residual model
        model = _create_residual_pipeline()
        model.fit(X_train, y_train)

        # Predict residual correction
        residual_pred = model.predict(X_val)

        # Hybrid = heuristic + predicted_residual
        hybrid_pts = heur_pts.loc[val_idx_valid].values + residual_pred
        actual_val = actual_pts.loc[val_idx_valid].values

        mae = float(mean_absolute_error(actual_val, hybrid_pts))
        fold_maes.append(mae)

        fold_details.append(
            {
                "val_season": val_season,
                "train_size": len(train_idx_valid),
                "val_size": len(val_idx_valid),
                "mae": mae,
                "ridge_alpha": float(model.named_steps["model"].alpha_),
            }
        )

        oof_fold = pd.DataFrame(
            {
                "idx": val_idx_valid,
                "season": pos_data.loc[val_idx_valid, "season"].values,
                "week": pos_data.loc[val_idx_valid, "week"].values,
                "heuristic_pts": heur_pts.loc[val_idx_valid].values,
                "residual_pred": residual_pred,
                "hybrid_pts": hybrid_pts,
                "actual_pts": actual_val,
            }
        )
        oof_records.append(oof_fold)

    mean_mae = float(np.mean(fold_maes)) if fold_maes else 0.0
    oof_df = (
        pd.concat(oof_records, ignore_index=True)
        if oof_records
        else pd.DataFrame(
            columns=[
                "idx",
                "season",
                "week",
                "heuristic_pts",
                "residual_pred",
                "hybrid_pts",
                "actual_pts",
            ]
        )
    )

    return {"mean_mae": mean_mae, "fold_details": fold_details}, oof_df
