"""Walk-forward cross-validation and XGBoost model training for NFL game predictions.

Provides season-boundary walk-forward CV that prevents temporal leakage,
trains spread and total prediction models on differential game features,
and serializes models as portable JSON with metadata sidecars.

Exports:
    WalkForwardResult: Dataclass holding CV fold scores and details.
    walk_forward_cv: Run walk-forward cross-validation with season boundaries.
    train_final_model: Train and save a final model with metadata.
    load_model: Load a saved model and its metadata from disk.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

from config import (
    CONSERVATIVE_PARAMS,
    HOLDOUT_SEASON,
    MODEL_DIR,
    VALIDATION_SEASONS,
)


@dataclass
class WalkForwardResult:
    """Result container for walk-forward cross-validation.

    Attributes:
        mean_mae: Mean absolute error averaged across all folds.
        fold_maes: Per-fold MAE values.
        fold_details: Per-fold detail dicts with train_seasons, val_season,
            train_size, val_size, and mae.
    """

    mean_mae: float
    fold_maes: List[float]
    fold_details: List[Dict[str, Any]] = field(default_factory=list)


def walk_forward_cv(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    params: Optional[Dict[str, Any]] = None,
    val_seasons: Optional[List[int]] = None,
) -> WalkForwardResult:
    """Run walk-forward cross-validation with season-level fold boundaries.

    For each validation season, trains on all prior seasons and validates
    on that single season. The holdout season (2024) is never used in any fold.

    Args:
        all_data: DataFrame with feature columns, target column, and 'season'.
        feature_cols: List of column names to use as features.
        target_col: Name of the target column (e.g., 'actual_margin').
        params: XGBoost parameters. Defaults to CONSERVATIVE_PARAMS.
        val_seasons: Seasons to validate on. Defaults to VALIDATION_SEASONS.

    Returns:
        WalkForwardResult with mean MAE, per-fold MAEs, and fold details.

    Raises:
        ValueError: If a validation season equals HOLDOUT_SEASON.
    """
    if params is None:
        params = CONSERVATIVE_PARAMS.copy()
    else:
        params = params.copy()

    if val_seasons is None:
        val_seasons = VALIDATION_SEASONS

    # Extract early_stopping_rounds from params for fit() call
    early_stopping_rounds = params.pop("early_stopping_rounds", 50)

    fold_maes: List[float] = []
    fold_details: List[Dict[str, Any]] = []

    for val_season in val_seasons:
        # Guard: never validate on holdout season
        if val_season == HOLDOUT_SEASON:
            raise ValueError(
                f"Validation season {val_season} equals HOLDOUT_SEASON {HOLDOUT_SEASON}. "
                "The holdout season must never be used during cross-validation."
            )

        train = all_data[all_data["season"] < val_season]
        val = all_data[all_data["season"] == val_season]

        if train.empty or val.empty:
            continue

        train_seasons = sorted(train["season"].unique().tolist())

        model = xgb.XGBRegressor(
            early_stopping_rounds=early_stopping_rounds,
            **params,
        )
        model.fit(
            train[feature_cols],
            train[target_col],
            eval_set=[(val[feature_cols], val[target_col])],
            verbose=False,
        )

        preds = model.predict(val[feature_cols])
        mae = float(mean_absolute_error(val[target_col], preds))
        fold_maes.append(mae)

        fold_details.append({
            "train_seasons": train_seasons,
            "val_season": val_season,
            "train_size": len(train),
            "val_size": len(val),
            "mae": mae,
        })

    mean_mae = float(np.mean(fold_maes)) if fold_maes else 0.0

    return WalkForwardResult(
        mean_mae=mean_mae,
        fold_maes=fold_maes,
        fold_details=fold_details,
    )


def train_final_model(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    params: Optional[Dict[str, Any]] = None,
    target_name: Optional[str] = None,
    model_dir: Optional[str] = None,
    cv_result: Optional["WalkForwardResult"] = None,
) -> Tuple[xgb.XGBRegressor, Dict[str, Any]]:
    """Train a final model on all training data and save to disk.

    Trains on all data where season < HOLDOUT_SEASON, using the last
    validation season (2023) as eval_set for early stopping. Saves the
    model as JSON and metadata as a sidecar JSON file.

    Args:
        all_data: Full DataFrame with features, target, and 'season'.
        feature_cols: List of feature column names.
        target_col: Target column name (e.g., 'actual_margin').
        params: XGBoost parameters. Defaults to CONSERVATIVE_PARAMS.
        target_name: Subdirectory name ('spread' or 'total').
        model_dir: Base directory for model output. Defaults to MODEL_DIR.
        cv_result: Pre-computed WalkForwardResult to avoid re-running CV.

    Returns:
        Tuple of (trained XGBRegressor model, metadata dict).
    """
    if params is None:
        params = CONSERVATIVE_PARAMS.copy()
    else:
        params = params.copy()

    if model_dir is None:
        model_dir = MODEL_DIR

    if target_name is None:
        target_name = target_col

    # Extract early_stopping_rounds for fit()
    early_stopping_rounds = params.pop("early_stopping_rounds", 50)

    # Training data: all seasons before holdout
    train_data = all_data[all_data["season"] < HOLDOUT_SEASON]

    # Use last validation season as eval_set for early stopping
    last_val_season = max(VALIDATION_SEASONS)
    train_set = train_data[train_data["season"] < last_val_season]
    eval_set = train_data[train_data["season"] == last_val_season]

    model = xgb.XGBRegressor(
        early_stopping_rounds=early_stopping_rounds,
        **params,
    )
    model.fit(
        train_set[feature_cols],
        train_set[target_col],
        eval_set=[(eval_set[feature_cols], eval_set[target_col])],
        verbose=False,
    )

    # Run walk-forward CV for metadata if not pre-computed
    if cv_result is None:
        cv_params = params.copy()
        cv_params["early_stopping_rounds"] = early_stopping_rounds
        cv_result = walk_forward_cv(
            all_data, feature_cols, target_col, params=cv_params,
        )

    # Save model and metadata
    output_dir = os.path.join(model_dir, target_name)
    os.makedirs(output_dir, exist_ok=True)

    model_path = os.path.join(output_dir, "model.json")
    model.save_model(model_path)

    training_seasons = sorted(train_data["season"].unique().tolist())
    metadata = {
        "target": target_col,
        "target_name": target_name,
        "training_seasons": training_seasons,
        "n_features": len(feature_cols),
        "feature_names": feature_cols,
        "cv_scores": {
            "mean_mae": cv_result.mean_mae,
            "fold_maes": cv_result.fold_maes,
        },
        "best_params": params,
        "trained_at": datetime.utcnow().isoformat() + "Z",
    }

    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return model, metadata


def load_model(
    target_name: str,
    model_dir: Optional[str] = None,
) -> Tuple[xgb.XGBRegressor, Dict[str, Any]]:
    """Load a saved model and its metadata from disk.

    Args:
        target_name: Subdirectory name ('spread' or 'total').
        model_dir: Base directory for model storage. Defaults to MODEL_DIR.

    Returns:
        Tuple of (XGBRegressor model, metadata dict).

    Raises:
        FileNotFoundError: If model.json or metadata.json not found.
        xgboost.core.XGBoostError: If model file is corrupt or unreadable.
    """
    if model_dir is None:
        model_dir = MODEL_DIR

    model_path = os.path.join(model_dir, target_name, "model.json")
    metadata_path = os.path.join(model_dir, target_name, "metadata.json")

    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not os.path.isfile(metadata_path):
        raise FileNotFoundError(f"Metadata not found: {metadata_path}")

    model = xgb.XGBRegressor()
    model.load_model(model_path)

    with open(metadata_path) as f:
        metadata = json.load(f)

    return model, metadata
