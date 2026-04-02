"""Hybrid projection: blend heuristic + ML or train residual correction models.

Approach 1 (Simple Blend):
    blended = alpha * heuristic + (1 - alpha) * ML
    Search alpha per position to minimise MAE.

Approach 2 (Residual Model):
    target = actual_fantasy_points - heuristic_fantasy_points
    Train RidgeCV on features -> residual, then final = heuristic + ridge.predict()

Approach 3 (Production Residual — save/load/apply):
    train_and_save_residual_models: Train Ridge on production heuristic residuals, save.
    load_residual_model: Load a saved residual Pipeline from disk.
    apply_residual_correction: Correct heuristic projections using saved residual model.

Exports:
    compute_fantasy_points_from_preds: Convert pred_{stat} columns to fantasy points.
    evaluate_blend: Grid-search alpha for heuristic-ML blend.
    train_residual_model: Walk-forward CV residual correction model.
    train_and_save_residual_models: Train + persist residual models for WR/TE.
    load_residual_model: Load saved residual Pipeline.
    apply_residual_correction: Apply residual correction to heuristic projections.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import joblib
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


# ---------------------------------------------------------------------------
# Approach 3: Production Residual — save / load / apply
# ---------------------------------------------------------------------------

RESIDUAL_MODEL_DIR = os.path.join("models", "residual")


def train_and_save_residual_models(
    positions: Optional[List[str]] = None,
    scoring_format: str = "half_ppr",
    output_dir: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Train residual correction models and save to disk.

    For each position, trains a Ridge pipeline on:
        residual = actual_fantasy_points - production_heuristic_points
    using walk-forward CV with train on seasons < val_season.
    The final production model is trained on ALL non-holdout data.

    Args:
        positions: Positions to train residual models for. Default ['WR', 'TE'].
        scoring_format: Scoring format string.
        output_dir: Directory to save models. Default 'models/residual'.

    Returns:
        Dict mapping position -> {mae, ridge_alpha, n_train, features}.
    """
    from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS
    from player_feature_engineering import (
        assemble_multiyear_player_features,
        get_player_feature_columns,
    )

    if positions is None:
        positions = ["WR", "TE"]
    if output_dir is None:
        output_dir = RESIDUAL_MODEL_DIR

    os.makedirs(output_dir, exist_ok=True)

    # Load data
    logger.info("Loading player feature data for residual training...")
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        logger.error("No data assembled for residual training")
        return {}

    feature_cols = get_player_feature_columns(all_data)
    logger.info("Found %d candidate features", len(feature_cols))

    # Build opponent rankings (for production heuristic)
    from run_production_residual_experiment import (
        build_opp_rankings_from_features,
        compute_actual_points,
        compute_production_heuristic_points,
    )

    opp_rankings = build_opp_rankings_from_features(all_data)

    results: Dict[str, Dict[str, Any]] = {}

    for position in positions:
        logger.info("Training residual model for %s...", position)
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

        if pos_data.empty:
            logger.warning("No data for %s", position)
            continue

        # Compute heuristic + actual
        prod_pts = compute_production_heuristic_points(
            pos_data, position, opp_rankings, scoring_format
        )
        actual_pts = compute_actual_points(pos_data, scoring_format)

        # Filter: weeks 3-18, valid data
        week_mask = pos_data["week"].between(3, 18)
        valid_mask = week_mask & prod_pts.notna() & actual_pts.notna()
        train_data = pos_data[valid_mask].copy()
        train_prod = prod_pts[valid_mask]
        train_actual = actual_pts[valid_mask]

        if len(train_data) < 100:
            logger.warning(
                "Insufficient data for %s: %d rows", position, len(train_data)
            )
            continue

        # Residual = actual - heuristic
        residual = train_actual - train_prod

        # Features
        available_features = [f for f in feature_cols if f in train_data.columns]
        if not available_features:
            logger.warning("No features for %s", position)
            continue

        X_train = train_data[available_features]
        y_train = residual

        # Train final production model on ALL non-holdout data
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
            ]
        )
        model.fit(X_train, y_train)

        ridge_alpha = float(model.named_steps["model"].alpha_)
        train_preds = model.predict(X_train)
        train_mae = float(mean_absolute_error(y_train, train_preds))

        # Save model
        model_path = os.path.join(output_dir, f"{position.lower()}_residual.joblib")
        meta_path = os.path.join(output_dir, f"{position.lower()}_residual_meta.json")

        joblib.dump(model, model_path)
        meta = {
            "position": position,
            "scoring_format": scoring_format,
            "ridge_alpha": ridge_alpha,
            "n_train": len(X_train),
            "train_residual_mae": train_mae,
            "n_features": len(available_features),
            "features": available_features,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(
            "%s residual model saved: alpha=%.3f, n=%d, features=%d",
            position,
            ridge_alpha,
            len(X_train),
            len(available_features),
        )

        results[position] = {
            "mae": train_mae,
            "ridge_alpha": ridge_alpha,
            "n_train": len(X_train),
            "features": available_features,
        }

    return results


def load_residual_model(
    position: str,
    model_dir: Optional[str] = None,
) -> Tuple[Pipeline, Dict[str, Any]]:
    """Load a saved residual correction model and its metadata.

    Args:
        position: Position code (e.g., 'WR', 'TE').
        model_dir: Directory containing saved models. Default 'models/residual'.

    Returns:
        Tuple of (fitted Pipeline, metadata dict).

    Raises:
        FileNotFoundError: If model file does not exist.
    """
    if model_dir is None:
        model_dir = RESIDUAL_MODEL_DIR

    model_path = os.path.join(model_dir, f"{position.lower()}_residual.joblib")
    meta_path = os.path.join(model_dir, f"{position.lower()}_residual_meta.json")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Residual model not found: {model_path}")

    model = joblib.load(model_path)

    meta: Dict[str, Any] = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            meta = json.load(f)

    return model, meta


def apply_residual_correction(
    heuristic_projections: pd.DataFrame,
    player_features: pd.DataFrame,
    position: str,
    model_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Apply residual correction to heuristic projections.

    Loads a pre-trained residual Ridge model, predicts the correction
    (residual), and adds it to heuristic projected_points. Floors at 0.0.

    Args:
        heuristic_projections: DataFrame with 'projected_points' and
            'player_id' columns from heuristic engine.
        player_features: Silver-layer features DataFrame with feature
            columns matching the model's training features.
        position: Position code ('WR' or 'TE').
        model_dir: Directory containing saved residual models.

    Returns:
        DataFrame with corrected projected_points. Unchanged if model
        loading fails or no matching features.
    """
    try:
        model, meta = load_residual_model(position, model_dir)
    except FileNotFoundError:
        logger.warning("No residual model for %s; returning heuristic as-is", position)
        return heuristic_projections

    features = meta.get("features", [])
    available = [f for f in features if f in player_features.columns]

    if not available:
        logger.warning(
            "No matching features for %s residual model; returning heuristic", position
        )
        return heuristic_projections

    result = heuristic_projections.copy()

    # Build feature matrix aligned to heuristic players
    id_col = "player_id" if "player_id" in result.columns else "player_name"
    feat_id_col = (
        "player_id" if "player_id" in player_features.columns else "player_name"
    )

    if id_col not in result.columns or feat_id_col not in player_features.columns:
        logger.warning("Cannot align features for residual correction")
        return heuristic_projections

    # Merge features onto projections
    feat_subset = player_features[[feat_id_col] + available].drop_duplicates(
        subset=[feat_id_col], keep="last"
    )
    merged = result.merge(feat_subset, left_on=id_col, right_on=feat_id_col, how="left")

    # Build full feature matrix (all model features, NaN for missing ones).
    # The imputer in the Pipeline will fill NaN with training medians.
    feature_data = {
        f: merged[f].values if f in merged.columns else np.nan for f in features
    }
    X = pd.DataFrame(feature_data, index=merged.index)

    has_features = X[available].notna().any(axis=1)

    if has_features.sum() == 0:
        logger.warning("No rows with features for %s residual", position)
        return heuristic_projections

    logger.info(
        "%s: %d/%d features available from Silver; %d imputed",
        position,
        len(available),
        len(features),
        len(features) - len(available),
    )

    corrections = np.zeros(len(merged))
    if has_features.any():
        corrections[has_features] = model.predict(X[has_features])

    # Apply correction (numpy clip uses min=/max=, not lower=/upper=)
    corrected = merged["projected_points"].values + corrections
    result["projected_points"] = np.clip(corrected, 0.0, None).round(2)

    logger.info(
        "%s residual correction: %d players, mean correction=%.2f",
        position,
        has_features.sum(),
        float(np.mean(corrections[has_features])) if has_features.any() else 0.0,
    )

    return result
