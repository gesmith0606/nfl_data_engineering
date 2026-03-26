"""Ensemble training: XGBoost + LightGBM + CatBoost stacking with Ridge meta-learner.

Provides generalized walk-forward CV with out-of-fold (OOF) predictions,
model factories for three gradient boosting frameworks, Ridge meta-learner
stacking, and ensemble save/load for prediction pipelines.

Two independent ensembles are trained: one for point spread (actual_margin)
and one for game total (actual_total).

Exports:
    make_xgb_model: Factory for XGBRegressor.
    make_lgb_model: Factory for LGBMRegressor.
    make_cb_model: Factory for CatBoostRegressor.
    walk_forward_cv_with_oof: Generalized walk-forward CV producing OOF predictions.
    assemble_oof_matrix: Join base model OOF predictions into stacking matrix.
    train_ridge_meta: Train RidgeCV meta-learner on OOF matrix.
    train_ensemble: Full pipeline -- train all base models + Ridge for spread and total.
    load_ensemble: Load saved ensemble artifacts from disk.
    predict_ensemble: Generate predictions from loaded ensemble models.
"""

import json
import os
import pickle
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import catboost as cb
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error

from model_training import WalkForwardResult
from config import (
    CB_CONSERVATIVE_PARAMS,
    CONSERVATIVE_PARAMS,
    ENSEMBLE_DIR,
    HOLDOUT_SEASON,
    LGB_CONSERVATIVE_PARAMS,
    VALIDATION_SEASONS,
)


# ---------------------------------------------------------------------------
# Model Factories
# ---------------------------------------------------------------------------


def make_xgb_model(params: dict) -> xgb.XGBRegressor:
    """Create an XGBRegressor from params dict.

    Extracts early_stopping_rounds from params (if present) and passes
    it as a constructor argument separately.

    Args:
        params: XGBoost hyperparameters.

    Returns:
        Configured XGBRegressor instance (not yet fitted).
    """
    params = params.copy()
    early_stopping = params.pop("early_stopping_rounds", 50)
    return xgb.XGBRegressor(early_stopping_rounds=early_stopping, **params)


def make_lgb_model(params: dict) -> lgb.LGBMRegressor:
    """Create a LGBMRegressor from params dict.

    Args:
        params: LightGBM hyperparameters.

    Returns:
        Configured LGBMRegressor instance (not yet fitted).
    """
    return lgb.LGBMRegressor(**params)


def make_cb_model(params: dict) -> cb.CatBoostRegressor:
    """Create a CatBoostRegressor from params dict.

    Args:
        params: CatBoost hyperparameters.

    Returns:
        Configured CatBoostRegressor instance (not yet fitted).
    """
    return cb.CatBoostRegressor(**params)


# ---------------------------------------------------------------------------
# Generalized Walk-Forward CV with OOF
# ---------------------------------------------------------------------------


def walk_forward_cv_with_oof(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    model_factory: Callable[[], Any],
    fit_kwargs_fn: Optional[Callable] = None,
    val_seasons: Optional[List[int]] = None,
) -> Tuple[WalkForwardResult, pd.DataFrame]:
    """Run walk-forward cross-validation producing out-of-fold predictions.

    For each validation season, trains on all prior seasons and validates
    on that single season. Collects OOF predictions for the meta-learner.

    Args:
        all_data: DataFrame with feature columns, target column, and 'season'.
        feature_cols: List of column names to use as features.
        target_col: Name of the target column.
        model_factory: Callable that returns a fresh model instance.
        fit_kwargs_fn: Optional callable(X_train, y_train, X_val, y_val) -> dict
            of extra kwargs for model.fit(). Handles API differences between
            XGBoost, LightGBM, and CatBoost.
        val_seasons: Seasons to validate on. Defaults to VALIDATION_SEASONS.

    Returns:
        Tuple of (WalkForwardResult, oof_df) where oof_df has columns
        [game_id, season, oof_prediction].

    Raises:
        ValueError: If a validation season equals HOLDOUT_SEASON.
    """
    if val_seasons is None:
        val_seasons = VALIDATION_SEASONS

    fold_maes: List[float] = []
    fold_details: List[Dict[str, Any]] = []
    oof_records: List[pd.DataFrame] = []

    for val_season in val_seasons:
        if val_season == HOLDOUT_SEASON:
            raise ValueError(
                f"Validation season {val_season} equals HOLDOUT_SEASON "
                f"{HOLDOUT_SEASON}. The holdout season must never be used "
                "during cross-validation."
            )

        train = all_data[all_data["season"] < val_season]
        val = all_data[all_data["season"] == val_season]

        if train.empty or val.empty:
            continue

        train_seasons = sorted(train["season"].unique().tolist())

        X_train = train[feature_cols]
        y_train = train[target_col]
        X_val = val[feature_cols]
        y_val = val[target_col]

        model = model_factory()

        # Build fit kwargs
        fit_kw: Dict[str, Any] = {}
        if fit_kwargs_fn is not None:
            fit_kw = fit_kwargs_fn(X_train, y_train, X_val, y_val)

        model.fit(X_train, y_train, **fit_kw)

        preds = model.predict(X_val)
        mae = float(mean_absolute_error(y_val, preds))
        fold_maes.append(mae)

        fold_details.append({
            "train_seasons": train_seasons,
            "val_season": val_season,
            "train_size": len(train),
            "val_size": len(val),
            "mae": mae,
        })

        # Collect OOF predictions
        oof_fold = pd.DataFrame({
            "game_id": val["game_id"].values,
            "season": val["season"].values,
            "oof_prediction": preds,
        })
        oof_records.append(oof_fold)

    mean_mae = float(np.mean(fold_maes)) if fold_maes else 0.0
    result = WalkForwardResult(
        mean_mae=mean_mae,
        fold_maes=fold_maes,
        fold_details=fold_details,
    )

    oof_df = pd.concat(oof_records, ignore_index=True) if oof_records else pd.DataFrame(
        columns=["game_id", "season", "oof_prediction"]
    )

    return result, oof_df


# ---------------------------------------------------------------------------
# OOF Matrix Assembly
# ---------------------------------------------------------------------------


def assemble_oof_matrix(
    xgb_oof: pd.DataFrame,
    lgb_oof: pd.DataFrame,
    cb_oof: pd.DataFrame,
    all_data: pd.DataFrame,
    target_col: str,
) -> pd.DataFrame:
    """Assemble a 3-column OOF prediction matrix for the Ridge meta-learner.

    Inner-joins base model OOF predictions on game_id and adds the actual
    target column from the source data.

    Args:
        xgb_oof: XGBoost OOF DataFrame with [game_id, season, oof_prediction].
        lgb_oof: LightGBM OOF DataFrame with [game_id, season, oof_prediction].
        cb_oof: CatBoost OOF DataFrame with [game_id, season, oof_prediction].
        all_data: Full dataset with game_id and target column.
        target_col: Name of the actual target column.

    Returns:
        DataFrame with columns: game_id, season, xgb_pred, lgb_pred, cb_pred, actual.
    """
    merged = xgb_oof.rename(columns={"oof_prediction": "xgb_pred"})
    merged = merged.merge(
        lgb_oof.rename(columns={"oof_prediction": "lgb_pred"})[["game_id", "lgb_pred"]],
        on="game_id",
        how="inner",
    )
    merged = merged.merge(
        cb_oof.rename(columns={"oof_prediction": "cb_pred"})[["game_id", "cb_pred"]],
        on="game_id",
        how="inner",
    )

    # Add actual target
    actuals = all_data[["game_id", target_col]].drop_duplicates("game_id")
    merged = merged.merge(
        actuals.rename(columns={target_col: "actual"}),
        on="game_id",
        how="inner",
    )

    return merged


# ---------------------------------------------------------------------------
# Ridge Meta-Learner
# ---------------------------------------------------------------------------


def train_ridge_meta(
    oof_matrix: pd.DataFrame,
    target_col: str = "actual",
) -> RidgeCV:
    """Train a RidgeCV meta-learner on the 3-column OOF prediction matrix.

    Args:
        oof_matrix: DataFrame with xgb_pred, lgb_pred, cb_pred, and target_col.
        target_col: Column name of actual values.

    Returns:
        Fitted RidgeCV model with automatically selected alpha.
    """
    X = oof_matrix[["xgb_pred", "lgb_pred", "cb_pred"]].values
    y = oof_matrix[target_col].values

    ridge = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])
    ridge.fit(X, y)

    return ridge


# ---------------------------------------------------------------------------
# Fit-kwargs helpers for each framework
# ---------------------------------------------------------------------------


def _xgb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """XGBoost fit kwargs: eval_set as list of tuples, verbose=False."""
    return {"eval_set": [(X_val, y_val)], "verbose": False}


def _lgb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """LightGBM fit kwargs: eval_set + early_stopping callback."""
    return {
        "eval_set": [(X_val, y_val)],
        "callbacks": [lgb.early_stopping(50, verbose=False)],
    }


def _cb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """CatBoost fit kwargs: eval_set as tuple (not list)."""
    return {"eval_set": (X_val, y_val)}


# ---------------------------------------------------------------------------
# Full Ensemble Training
# ---------------------------------------------------------------------------


def train_ensemble(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    xgb_params: Optional[dict] = None,
    lgb_params: Optional[dict] = None,
    cb_params: Optional[dict] = None,
    ensemble_dir: Optional[str] = None,
) -> dict:
    """Train full ensemble (3 base learners + Ridge meta) for spread and total.

    For each target (spread=actual_margin, total=actual_total):
    1. Run walk-forward CV with OOF for XGBoost, LightGBM, CatBoost
    2. Assemble OOF matrix
    3. Train Ridge meta-learner
    4. Train final base models on all data < HOLDOUT_SEASON
    5. Save all artifacts

    Args:
        all_data: DataFrame with features, targets, season, game_id.
        feature_cols: Feature column names.
        xgb_params: XGBoost params. Defaults to CONSERVATIVE_PARAMS.
        lgb_params: LightGBM params. Defaults to LGB_CONSERVATIVE_PARAMS.
        cb_params: CatBoost params. Defaults to CB_CONSERVATIVE_PARAMS.
        ensemble_dir: Directory for saving artifacts. Defaults to ENSEMBLE_DIR.

    Returns:
        Metadata dict (also saved as metadata.json).
    """
    if xgb_params is None:
        xgb_params = CONSERVATIVE_PARAMS
    if lgb_params is None:
        lgb_params = LGB_CONSERVATIVE_PARAMS
    if cb_params is None:
        cb_params = CB_CONSERVATIVE_PARAMS
    if ensemble_dir is None:
        ensemble_dir = ENSEMBLE_DIR

    os.makedirs(ensemble_dir, exist_ok=True)

    targets = {
        "spread": "actual_margin",
        "total": "actual_total",
    }

    # Filter to training data (< holdout)
    train_data = all_data[all_data["season"] < HOLDOUT_SEASON]
    last_val_season = max(VALIDATION_SEASONS)

    metadata: Dict[str, Any] = {
        "ensemble_version": "1.0",
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "training_seasons": sorted(train_data["season"].unique().tolist()),
        "holdout_season": HOLDOUT_SEASON,
        "selected_features": feature_cols,
        "n_features": len(feature_cols),
    }

    for target_name, target_col in targets.items():
        # --- Walk-forward CV with OOF for each base learner ---
        xgb_result, xgb_oof = walk_forward_cv_with_oof(
            all_data, feature_cols, target_col,
            model_factory=lambda: make_xgb_model(xgb_params),
            fit_kwargs_fn=_xgb_fit_kwargs,
        )

        lgb_result, lgb_oof = walk_forward_cv_with_oof(
            all_data, feature_cols, target_col,
            model_factory=lambda: make_lgb_model(lgb_params),
            fit_kwargs_fn=_lgb_fit_kwargs,
        )

        cb_result, cb_oof = walk_forward_cv_with_oof(
            all_data, feature_cols, target_col,
            model_factory=lambda: make_cb_model(cb_params),
            fit_kwargs_fn=_cb_fit_kwargs,
        )

        # --- Assemble OOF matrix and train Ridge ---
        oof_matrix = assemble_oof_matrix(
            xgb_oof, lgb_oof, cb_oof, all_data, target_col,
        )
        ridge = train_ridge_meta(oof_matrix)

        # --- Train final base models on all training data ---
        train_set = train_data[train_data["season"] < last_val_season]
        eval_set_data = train_data[train_data["season"] == last_val_season]

        X_train = train_set[feature_cols]
        y_train = train_set[target_col]
        X_eval = eval_set_data[feature_cols]
        y_eval = eval_set_data[target_col]

        # XGBoost final
        xgb_final = make_xgb_model(xgb_params)
        xgb_final.fit(X_train, y_train, eval_set=[(X_eval, y_eval)], verbose=False)

        # LightGBM final
        lgb_final = make_lgb_model(lgb_params)
        lgb_final.fit(
            X_train, y_train,
            eval_set=[(X_eval, y_eval)],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )

        # CatBoost final
        cb_final = make_cb_model(cb_params)
        cb_final.fit(X_train, y_train, eval_set=(X_eval, y_eval))

        # --- Save artifacts ---
        xgb_final.save_model(os.path.join(ensemble_dir, f"xgb_{target_name}.json"))
        lgb_final.booster_.save_model(os.path.join(ensemble_dir, f"lgb_{target_name}.txt"))
        cb_final.save_model(os.path.join(ensemble_dir, f"cb_{target_name}.cbm"))

        ridge_path = os.path.join(ensemble_dir, f"ridge_{target_name}.pkl")
        with open(ridge_path, "wb") as f:
            pickle.dump(ridge, f)

        # --- Record per-target metadata ---
        metadata[target_name] = {
            "target_col": target_col,
            "xgb_cv_mae": xgb_result.mean_mae,
            "lgb_cv_mae": lgb_result.mean_mae,
            "cb_cv_mae": cb_result.mean_mae,
            "ridge_alpha": float(ridge.alpha_),
            "ridge_coefficients": ridge.coef_.tolist(),
        }

    # Save metadata.json
    meta_path = os.path.join(ensemble_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


# ---------------------------------------------------------------------------
# Load Ensemble
# ---------------------------------------------------------------------------


def load_ensemble(
    ensemble_dir: Optional[str] = None,
) -> Tuple[dict, dict, dict]:
    """Load saved ensemble artifacts from disk.

    Args:
        ensemble_dir: Directory containing ensemble artifacts.
            Defaults to ENSEMBLE_DIR.

    Returns:
        Tuple of (spread_models, total_models, metadata) where each
        models dict has keys: xgb, lgb, cb, ridge.
    """
    if ensemble_dir is None:
        ensemble_dir = ENSEMBLE_DIR

    # Load metadata
    with open(os.path.join(ensemble_dir, "metadata.json")) as f:
        metadata = json.load(f)

    def _load_target_models(target_name: str) -> dict:
        # XGBoost
        xgb_model = xgb.XGBRegressor()
        xgb_model.load_model(os.path.join(ensemble_dir, f"xgb_{target_name}.json"))

        # LightGBM -- load as Booster for prediction
        lgb_model = lgb.Booster(model_file=os.path.join(ensemble_dir, f"lgb_{target_name}.txt"))

        # CatBoost
        cb_model = cb.CatBoostRegressor()
        cb_model.load_model(os.path.join(ensemble_dir, f"cb_{target_name}.cbm"))

        # Ridge
        with open(os.path.join(ensemble_dir, f"ridge_{target_name}.pkl"), "rb") as f:
            ridge_model = pickle.load(f)

        return {
            "xgb": xgb_model,
            "lgb": lgb_model,
            "cb": cb_model,
            "ridge": ridge_model,
        }

    spread_models = _load_target_models("spread")
    total_models = _load_target_models("total")

    return spread_models, total_models, metadata


# ---------------------------------------------------------------------------
# Predict Ensemble
# ---------------------------------------------------------------------------


def predict_ensemble(
    features: pd.DataFrame,
    models: dict,
) -> np.ndarray:
    """Generate ensemble predictions from loaded models.

    Gets base predictions from XGBoost, LightGBM, and CatBoost, stacks
    them into a 3-column array, and passes through the Ridge meta-learner.

    Args:
        features: DataFrame of game features (same columns as training).
        models: Dict with keys xgb, lgb, cb, ridge from load_ensemble.

    Returns:
        Numpy array of ensemble predictions.
    """
    xgb_preds = models["xgb"].predict(features)

    # LightGBM Booster uses .predict() on raw data
    lgb_model = models["lgb"]
    if isinstance(lgb_model, lgb.Booster):
        lgb_preds = lgb_model.predict(features)
    else:
        lgb_preds = lgb_model.predict(features)

    cb_preds = models["cb"].predict(features)

    # Stack into 3-column array for Ridge
    stacked = np.column_stack([xgb_preds, lgb_preds, cb_preds])

    return models["ridge"].predict(stacked)
