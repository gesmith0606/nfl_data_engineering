"""Quantile regression models for calibrated floor/ceiling predictions.

Trains per-position LightGBM quantile models (10th, 50th, 90th percentile)
using walk-forward cross-validation on the 42-column Silver feature set.
Produces calibrated prediction intervals that replace the hardcoded
variance multipliers in projection_engine.add_floor_ceiling().

Exports:
    train_quantile_models: Train LightGBM quantile models per position.
    save_quantile_models: Persist trained models to disk.
    load_quantile_models: Load saved models from disk.
    predict_quantiles: Generate floor/projection/ceiling from trained models.
    compute_calibration: Evaluate coverage and tail calibration.
"""

import json
import logging
import os
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DEFAULT_MODEL_DIR = os.path.join(_BASE_DIR, "models", "quantile")

# Conservative hyperparameters to avoid overfitting
QUANTILE_LGB_PARAMS = {
    "objective": "quantile",
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "verbose": -1,
    "n_jobs": -1,
    "random_state": 42,
}

DEFAULT_QUANTILES = [0.1, 0.5, 0.9]
POSITIONS = ["QB", "RB", "WR", "TE"]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train_quantile_models(
    features_df: pd.DataFrame,
    target_col: str = "fantasy_points_ppr",
    positions: Optional[List[str]] = None,
    quantiles: Optional[List[float]] = None,
    validation_seasons: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Train LightGBM quantile regression models per position.

    Uses walk-forward CV: for each validation season, trains on all prior
    seasons and predicts the validation season. Collects out-of-fold (OOF)
    predictions for calibration evaluation.

    Args:
        features_df: Player-week DataFrame with feature columns, position,
            season, and the target column.
        target_col: Name of the fantasy points target column.
        positions: Positions to train (default: QB, RB, WR, TE).
        quantiles: Quantile levels (default: 0.1, 0.5, 0.9).
        validation_seasons: Seasons to validate on. Defaults to seasons
            with at least 2 prior training seasons in the data.

    Returns:
        Dict with keys:
            'models': {position: {quantile: LGBMRegressor}}
            'feature_cols': list of feature column names used
            'oof_predictions': DataFrame with OOF quantile predictions
            'imputer': fitted SimpleImputer for feature NaN handling
    """
    if positions is None:
        positions = POSITIONS
    if quantiles is None:
        quantiles = DEFAULT_QUANTILES

    # Identify feature columns (exclude identifiers, labels, target)
    from player_feature_engineering import get_player_feature_columns

    feature_cols = get_player_feature_columns(features_df)
    logger.info("Using %d feature columns for quantile training", len(feature_cols))

    # Determine validation seasons
    available_seasons = sorted(features_df["season"].unique())
    if validation_seasons is None:
        # Need at least 2 training seasons before each validation season
        validation_seasons = [
            s for s in available_seasons if s >= available_seasons[0] + 2
        ]
    logger.info("Validation seasons: %s", validation_seasons)

    # Fit imputer on all data (feature NaNs)
    imputer = SimpleImputer(strategy="median")
    valid_features = [c for c in feature_cols if c in features_df.columns]
    imputer.fit(features_df[valid_features])

    all_models: Dict[str, Dict[float, lgb.LGBMRegressor]] = {}
    oof_rows: List[pd.DataFrame] = []

    for position in positions:
        pos_df = features_df[features_df["position"] == position].copy()
        if len(pos_df) < 100:
            logger.warning(
                "Skipping %s: only %d rows (need 100+)", position, len(pos_df)
            )
            continue

        logger.info("Training %s quantile models (%d rows)", position, len(pos_df))
        pos_models: Dict[float, lgb.LGBMRegressor] = {}

        # Walk-forward CV to collect OOF predictions
        pos_oof_parts: List[pd.DataFrame] = []
        for val_season in validation_seasons:
            train_mask = pos_df["season"] < val_season
            val_mask = pos_df["season"] == val_season

            train_data = pos_df[train_mask]
            val_data = pos_df[val_mask]

            if len(train_data) < 50 or len(val_data) < 10:
                continue

            X_train = imputer.transform(train_data[valid_features])
            X_val = imputer.transform(val_data[valid_features])
            y_train = train_data[target_col].values
            y_val = val_data[target_col].values

            oof_part = val_data[
                ["player_id", "player_name", "position", "season", "week"]
            ].copy()
            oof_part["actual"] = y_val

            for alpha in quantiles:
                params = {**QUANTILE_LGB_PARAMS, "alpha": alpha}
                model = lgb.LGBMRegressor(**params)
                model.fit(X_train, y_train)
                preds = model.predict(X_val)
                col_name = f"q{int(alpha * 100):02d}"
                oof_part[col_name] = preds

            pos_oof_parts.append(oof_part)

        if pos_oof_parts:
            pos_oof = pd.concat(pos_oof_parts, ignore_index=True)
            oof_rows.append(pos_oof)

        # Train final models on ALL data for each quantile
        X_all = imputer.transform(pos_df[valid_features])
        y_all = pos_df[target_col].values

        for alpha in quantiles:
            params = {**QUANTILE_LGB_PARAMS, "alpha": alpha}
            model = lgb.LGBMRegressor(**params)
            model.fit(X_all, y_all)
            pos_models[alpha] = model
            logger.info(
                "  %s q%d: trained on %d rows",
                position,
                int(alpha * 100),
                len(X_all),
            )

        all_models[position] = pos_models

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()

    return {
        "models": all_models,
        "feature_cols": valid_features,
        "oof_predictions": oof_df,
        "imputer": imputer,
    }


# ---------------------------------------------------------------------------
# Calibration evaluation
# ---------------------------------------------------------------------------


def compute_calibration(
    oof_df: pd.DataFrame,
    positions: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Compute calibration metrics from OOF predictions.

    For each position, computes:
        - coverage: P(q10 <= actual <= q90) -- target 80%
        - lower_tail: P(actual < q10) -- should be ~10%
        - upper_tail: P(actual > q90) -- should be ~10%
        - mean_interval_width: avg(q90 - q10)
        - q50_mae: MAE of 50th percentile predictions

    Args:
        oof_df: OOF predictions DataFrame with actual, q10, q50, q90 columns.
        positions: Positions to evaluate (default: all in oof_df).

    Returns:
        DataFrame with one row per position and calibration columns.
    """
    if oof_df.empty or "position" not in oof_df.columns:
        return pd.DataFrame()

    if positions is None:
        positions = sorted(oof_df["position"].unique())

    results = []
    for pos in positions:
        pos_data = oof_df[oof_df["position"] == pos]
        if pos_data.empty or "q10" not in pos_data.columns:
            continue

        actual = pos_data["actual"].values
        q10 = pos_data["q10"].values
        q50 = pos_data["q50"].values
        q90 = pos_data["q90"].values
        n = len(actual)

        coverage = float(np.mean((actual >= q10) & (actual <= q90)))
        lower_tail = float(np.mean(actual < q10))
        upper_tail = float(np.mean(actual > q90))
        mean_width = float(np.mean(q90 - q10))
        q50_mae = float(mean_absolute_error(actual, q50))

        results.append(
            {
                "position": pos,
                "n_rows": n,
                "coverage_80": round(coverage, 4),
                "lower_tail_10": round(lower_tail, 4),
                "upper_tail_10": round(upper_tail, 4),
                "mean_interval_width": round(mean_width, 2),
                "q50_mae": round(q50_mae, 2),
            }
        )

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_quantile_models(
    result: Dict[str, Any],
    path: Optional[str] = None,
) -> str:
    """Save trained quantile models and metadata to disk.

    Args:
        result: Output from train_quantile_models().
        path: Directory to save to (default: models/quantile/).

    Returns:
        Path where models were saved.
    """
    if path is None:
        path = DEFAULT_MODEL_DIR

    os.makedirs(path, exist_ok=True)

    # Save models
    for position, pos_models in result["models"].items():
        for alpha, model in pos_models.items():
            fname = f"{position}_q{int(alpha * 100):02d}.pkl"
            with open(os.path.join(path, fname), "wb") as f:
                pickle.dump(model, f)

    # Save imputer
    with open(os.path.join(path, "imputer.pkl"), "wb") as f:
        pickle.dump(result["imputer"], f)

    # Save metadata
    metadata = {
        "feature_cols": result["feature_cols"],
        "positions": list(result["models"].keys()),
        "quantiles": (
            [float(q) for q in next(iter(result["models"].values())).keys()]
            if result["models"]
            else []
        ),
        "created_at": datetime.now().isoformat(),
    }
    with open(os.path.join(path, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Quantile models saved to %s", path)
    return path


def load_quantile_models(
    path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Load saved quantile models from disk.

    Args:
        path: Directory to load from (default: models/quantile/).

    Returns:
        Dict with 'models', 'feature_cols', 'imputer' keys, or None if
        no saved models are found.
    """
    if path is None:
        path = DEFAULT_MODEL_DIR

    metadata_path = os.path.join(path, "metadata.json")
    if not os.path.exists(metadata_path):
        return None

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    models: Dict[str, Dict[float, lgb.LGBMRegressor]] = {}
    for position in metadata["positions"]:
        pos_models: Dict[float, lgb.LGBMRegressor] = {}
        for alpha in metadata["quantiles"]:
            fname = f"{position}_q{int(alpha * 100):02d}.pkl"
            fpath = os.path.join(path, fname)
            if not os.path.exists(fpath):
                logger.warning("Missing model file: %s", fpath)
                return None
            with open(fpath, "rb") as f:
                pos_models[alpha] = pickle.load(f)
        models[position] = pos_models

    imputer_path = os.path.join(path, "imputer.pkl")
    imputer = None
    if os.path.exists(imputer_path):
        with open(imputer_path, "rb") as f:
            imputer = pickle.load(f)

    return {
        "models": models,
        "feature_cols": metadata["feature_cols"],
        "imputer": imputer,
    }


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def predict_quantiles(
    quantile_data: Dict[str, Any],
    features_df: pd.DataFrame,
    position: str,
) -> pd.DataFrame:
    """Generate quantile predictions for a given position.

    Args:
        quantile_data: Loaded model data from load_quantile_models().
        features_df: Player-week DataFrame with feature columns.
        position: Position to predict (QB, RB, WR, TE).

    Returns:
        DataFrame with quantile_floor, quantile_projection, quantile_ceiling
        columns aligned to features_df index.
    """
    models = quantile_data["models"]
    feature_cols = quantile_data["feature_cols"]
    imputer = quantile_data["imputer"]

    if position not in models:
        logger.warning("No quantile models for position %s", position)
        return pd.DataFrame(
            index=features_df.index,
            columns=["quantile_floor", "quantile_projection", "quantile_ceiling"],
        )

    pos_models = models[position]
    valid_features = [c for c in feature_cols if c in features_df.columns]

    if not valid_features:
        logger.warning("No matching feature columns for quantile prediction")
        return pd.DataFrame(
            index=features_df.index,
            columns=["quantile_floor", "quantile_projection", "quantile_ceiling"],
        )

    X = features_df[valid_features].copy()
    if imputer is not None:
        X_imp = imputer.transform(X)
    else:
        X_imp = X.values

    result = pd.DataFrame(index=features_df.index)

    # Map quantile levels to output columns
    quantile_map = {
        0.1: "quantile_floor",
        0.5: "quantile_projection",
        0.9: "quantile_ceiling",
    }

    for alpha, model in pos_models.items():
        col_name = quantile_map.get(alpha, f"quantile_{int(alpha * 100):02d}")
        preds = model.predict(X_imp)
        result[col_name] = np.clip(preds, 0.0, None).round(2)

    # Enforce floor <= projection <= ceiling invariant
    if "quantile_floor" in result.columns and "quantile_ceiling" in result.columns:
        if "quantile_projection" in result.columns:
            result["quantile_floor"] = result[
                ["quantile_floor", "quantile_projection"]
            ].min(axis=1)
            result["quantile_ceiling"] = result[
                ["quantile_ceiling", "quantile_projection"]
            ].max(axis=1)
        result["quantile_floor"] = result[["quantile_floor", "quantile_ceiling"]].min(
            axis=1
        )

    return result
