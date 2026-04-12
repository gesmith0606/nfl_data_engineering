"""Per-position, per-stat player model training with walk-forward CV.

Trains XGBoost models for each stat in POSITION_STAT_PROFILE per position,
using walk-forward cross-validation with holdout exclusion, SHAP-based
feature selection per stat-type group, and model serialization.

Exports:
    PLAYER_VALIDATION_SEASONS: Walk-forward validation seasons for player models.
    STAT_TYPE_GROUPS: Feature selection groups by stat type.
    STAT_TYPE_PARAMS: Hyperparameter profiles per stat type.
    get_stat_type: Map a stat name to its group key.
    get_player_model_params: Return hyperparams for a stat's type group.
    get_lgb_params_for_stat: Return LGB hyperparams for a stat's type group.
    _player_xgb_fit_kwargs: XGBoost fit kwargs for walk-forward CV.
    _player_lgb_fit_kwargs: LightGBM fit kwargs for walk-forward CV.
    player_walk_forward_cv: Walk-forward CV keyed on row index.
    run_player_feature_selection: SHAP selection per stat-type group.
    train_position_models: Train all stat models for one position.
    assemble_player_oof_matrix: Merge XGB/LGB OOF predictions on idx.
    train_player_ridge_meta: Train RidgeCV on 2-column OOF matrix.
    player_ensemble_stacking: XGB + LGB + Ridge ensemble per stat.
    save_player_model: Save model JSON + metadata sidecar.
    load_player_model: Load saved model.
    predict_player_stats: Predict all stats for a position.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNetCV, RidgeCV
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from config import CONSERVATIVE_PARAMS, HOLDOUT_SEASON, LGB_CONSERVATIVE_PARAMS
from ensemble_training import make_lgb_model, make_xgb_model
from feature_selector import _assert_no_holdout, filter_correlated_features
from model_training import WalkForwardResult
from projection_engine import POSITION_STAT_PROFILE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Per D-17: Walk-forward validation seasons for player models
# With 2016-2025 training data, validate on 2019-2024 (need >=2 train seasons per fold)
PLAYER_VALIDATION_SEASONS = [2019, 2020, 2021, 2022, 2023, 2024]

# Per D-04: Feature selection groups (stat types that share features)
STAT_TYPE_GROUPS = {
    "yardage": ["passing_yards", "rushing_yards", "receiving_yards"],
    "td": ["passing_tds", "rushing_tds", "receiving_tds"],
    "volume": ["targets", "receptions", "carries"],
    "turnover": ["interceptions"],
}

# Per D-03: Hyperparameter profiles by stat type
YARDAGE_PARAMS = {
    **CONSERVATIVE_PARAMS,
    "max_depth": 4,
    "min_child_weight": 5,
    "n_estimators": 500,
}
TD_PARAMS = {
    **CONSERVATIVE_PARAMS,
    "max_depth": 3,
    "min_child_weight": 10,
    "n_estimators": 300,
}
VOLUME_PARAMS = {
    **CONSERVATIVE_PARAMS,
    "max_depth": 4,
    "min_child_weight": 5,
    "n_estimators": 500,
}
TURNOVER_PARAMS = {
    **CONSERVATIVE_PARAMS,
    "max_depth": 3,
    "min_child_weight": 10,
    "n_estimators": 300,
}

STAT_TYPE_PARAMS = {
    "yardage": YARDAGE_PARAMS,
    "td": TD_PARAMS,
    "volume": VOLUME_PARAMS,
    "turnover": TURNOVER_PARAMS,
}

# Representative targets for feature selection (one per stat-type group)
_REPRESENTATIVE_TARGETS = {
    "yardage": "rushing_yards",
    "td": "rushing_tds",
    "volume": "receptions",
    "turnover": "interceptions",
}

# Maximum features per group after SHAP selection
_MAX_FEATURES_PER_GROUP = 80


# ---------------------------------------------------------------------------
# Stat type helpers
# ---------------------------------------------------------------------------


def get_stat_type(stat: str) -> str:
    """Map a stat name to its STAT_TYPE_GROUPS key.

    Args:
        stat: Stat name (e.g., 'rushing_yards', 'passing_tds').

    Returns:
        Group key string (e.g., 'yardage', 'td').

    Raises:
        ValueError: If stat is not found in any group.
    """
    for group, stats in STAT_TYPE_GROUPS.items():
        if stat in stats:
            return group
    raise ValueError(f"Stat '{stat}' not found in any STAT_TYPE_GROUPS")


def get_player_model_params(stat: str) -> dict:
    """Return hyperparameters for a stat's type group.

    Args:
        stat: Stat name (e.g., 'rushing_yards').

    Returns:
        Copy of the hyperparameter dict for this stat's group.
    """
    stat_type = get_stat_type(stat)
    return STAT_TYPE_PARAMS[stat_type].copy()


def get_lgb_params_for_stat(stat: str) -> dict:
    """Return LGB hyperparameters adapted for a stat's type group.

    TD/turnover stats get shallower trees; yardage/volume use base params.

    Args:
        stat: Stat name (e.g., 'rushing_yards', 'passing_tds').

    Returns:
        Copy of LGB_CONSERVATIVE_PARAMS with stat-type adjustments.
    """
    stat_type = get_stat_type(stat)
    base = LGB_CONSERVATIVE_PARAMS.copy()
    if stat_type in ("td", "turnover"):
        base["max_depth"] = 3
        base["min_child_samples"] = 30
        base["n_estimators"] = 300
    return base


# ---------------------------------------------------------------------------
# Ridge / ElasticNet model factories
# ---------------------------------------------------------------------------


def create_ridge_pipeline() -> Pipeline:
    """Create a Ridge regression pipeline with median imputation.

    Uses RidgeCV with a broad alpha search over np.logspace(-3, 3, 50).
    Imputes NaN values with column medians before fitting.

    Returns:
        sklearn Pipeline with SimpleImputer + RidgeCV.
    """
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
        ]
    )


def create_elasticnet_pipeline() -> Pipeline:
    """Create an ElasticNet regression pipeline with median imputation.

    Uses ElasticNetCV with multiple l1_ratio values and broad alpha search.
    Imputes NaN values with column medians before fitting.

    Returns:
        sklearn Pipeline with SimpleImputer + ElasticNetCV.
    """
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                ElasticNetCV(
                    l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9],
                    alphas=np.logspace(-3, 3, 20),
                    max_iter=5000,
                ),
            ),
        ]
    )


def _linear_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """Fit kwargs for Ridge/ElasticNet — no eval_set needed.

    Linear models use built-in CV for alpha selection, so no
    early stopping or eval_set is needed during walk-forward CV.

    Returns:
        Empty dict.
    """
    return {}


# ---------------------------------------------------------------------------
# XGBoost fit kwargs (adapted from ensemble_training._xgb_fit_kwargs)
# ---------------------------------------------------------------------------


def _player_xgb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """XGBoost fit kwargs with eval_set for early stopping."""
    return {"eval_set": [(X_val, y_val)], "verbose": False}


def _player_lgb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """LightGBM fit kwargs for player walk-forward CV."""
    import lightgbm as lgb_lib

    return {
        "eval_set": [(X_val, y_val)],
        "callbacks": [lgb_lib.early_stopping(50, verbose=False)],
    }


# ---------------------------------------------------------------------------
# Walk-forward CV for player models
# ---------------------------------------------------------------------------


def player_walk_forward_cv(
    pos_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    model_factory: Callable[[], Any],
    fit_kwargs_fn: Optional[Callable] = None,
    val_seasons: Optional[List[int]] = None,
) -> Tuple[WalkForwardResult, pd.DataFrame]:
    """Walk-forward CV keyed on row index (NOT game_id).

    For each validation season, trains on all prior seasons and validates
    on that single season. Collects OOF predictions keyed by row index.

    Args:
        pos_data: Position-filtered DataFrame with features, target, 'season'.
        feature_cols: Feature column names.
        target_col: Target column name.
        model_factory: Callable returning a fresh model instance.
        fit_kwargs_fn: Optional callable(X_train, y_train, X_val, y_val) -> dict.
            Defaults to _player_xgb_fit_kwargs.
        val_seasons: Seasons to validate on. Defaults to PLAYER_VALIDATION_SEASONS.

    Returns:
        Tuple of (WalkForwardResult, oof_df) where oof_df has columns
        [idx, season, week, oof_prediction].

    Raises:
        ValueError: If a validation season equals HOLDOUT_SEASON.
    """
    if val_seasons is None:
        val_seasons = PLAYER_VALIDATION_SEASONS

    if fit_kwargs_fn is None:
        fit_kwargs_fn = _player_xgb_fit_kwargs

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

        train = pos_data[pos_data["season"] < val_season]
        val = pos_data[pos_data["season"] == val_season]

        if train.empty or val.empty:
            continue

        # Skip fold if train has fewer than 2 unique seasons (per D-17)
        train_seasons = sorted(train["season"].unique().tolist())
        if len(train_seasons) < 2:
            logger.info(
                f"Skipping fold val_season={val_season}: only {len(train_seasons)} "
                "training season(s) (need >= 2)"
            )
            continue

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

        fold_details.append(
            {
                "train_seasons": train_seasons,
                "val_season": val_season,
                "train_size": len(train),
                "val_size": len(val),
                "mae": mae,
            }
        )

        # Collect OOF predictions keyed by row index (NOT game_id)
        oof_fold = pd.DataFrame(
            {
                "idx": val.index.values,
                "season": val["season"].values,
                "week": val["week"].values,
                "oof_prediction": preds,
            }
        )
        oof_records.append(oof_fold)

    mean_mae = float(np.mean(fold_maes)) if fold_maes else 0.0
    result = WalkForwardResult(
        mean_mae=mean_mae,
        fold_maes=fold_maes,
        fold_details=fold_details,
    )

    oof_df = (
        pd.concat(oof_records, ignore_index=True)
        if oof_records
        else pd.DataFrame(columns=["idx", "season", "week", "oof_prediction"])
    )

    return result, oof_df


# ---------------------------------------------------------------------------
# Feature selection per stat-type group
# ---------------------------------------------------------------------------


def run_player_feature_selection(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    positions: List[str],
    target_count: int = _MAX_FEATURES_PER_GROUP,
    corr_threshold: float = 0.90,
    output_dir: Optional[str] = None,
) -> Dict[str, List[str]]:
    """SHAP-based feature selection per stat-type group.

    For each group (yardage, td, volume, turnover):
    1. Pick a representative target stat
    2. Filter to positions that have this stat
    3. Train XGBoost and compute SHAP importances
    4. Apply correlation filtering
    5. Truncate to target_count features

    Args:
        all_data: Full player-week DataFrame (no holdout season).
        feature_cols: Candidate feature column names.
        positions: Positions to include.
        target_count: Max features per group. Default 80.
        corr_threshold: Correlation threshold for pair removal. Default 0.90.
        output_dir: Directory to save selection results. None to skip saving.

    Returns:
        Dict mapping group name to list of selected feature names.
    """
    # Guard: exclude holdout season
    train_data = all_data[all_data["season"] != HOLDOUT_SEASON].copy()
    _assert_no_holdout(train_data, "player feature selection")

    # Only use features that exist in the DataFrame
    available_features = [f for f in feature_cols if f in train_data.columns]

    result: Dict[str, List[str]] = {}

    for group_name, group_stats in STAT_TYPE_GROUPS.items():
        representative = _REPRESENTATIVE_TARGETS[group_name]

        # Filter to positions that have this stat
        relevant_positions = [
            pos
            for pos in positions
            if representative in POSITION_STAT_PROFILE.get(pos, [])
        ]
        if not relevant_positions:
            logger.warning(
                f"No positions have stat '{representative}' for group '{group_name}'"
            )
            result[group_name] = available_features[:target_count]
            continue

        group_data = train_data[train_data["position"].isin(relevant_positions)].copy()
        if group_data.empty or representative not in group_data.columns:
            result[group_name] = available_features[:target_count]
            continue

        # Drop rows with NaN target
        group_data = group_data.dropna(subset=[representative])
        if len(group_data) < 50:
            logger.warning(
                f"Too few rows ({len(group_data)}) for group '{group_name}', "
                "using all features"
            )
            result[group_name] = available_features[:target_count]
            continue

        # Drop zero-variance features
        active = [f for f in available_features if group_data[f].var() > 0.0]
        if not active:
            result[group_name] = available_features[:target_count]
            continue

        # Train quick XGBoost for SHAP
        params = get_player_model_params(representative)
        params_copy = params.copy()
        early_stopping = params_copy.pop("early_stopping_rounds", 50)

        X = group_data[active]
        y = group_data[representative]

        X_train, X_eval, y_train, y_eval = train_test_split(
            X, y, test_size=0.2, random_state=params_copy.get("random_state", 42)
        )

        model = xgb.XGBRegressor(early_stopping_rounds=early_stopping, **params_copy)
        model.fit(X_train, y_train, eval_set=[(X_eval, y_eval)], verbose=False)

        # Compute SHAP importances
        sample_size = min(500, len(group_data))
        X_sample = group_data[active].sample(
            n=sample_size, random_state=params_copy.get("random_state", 42)
        )
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)
        mean_abs_shap = np.mean(np.abs(shap_values), axis=0)

        shap_scores = {col: float(score) for col, score in zip(active, mean_abs_shap)}

        # Correlation filtering
        surviving, _, _ = filter_correlated_features(
            group_data, active, shap_scores, threshold=corr_threshold
        )

        # Truncate to target_count by SHAP rank
        if len(surviving) > target_count:
            surviving_ranked = sorted(
                surviving, key=lambda f: shap_scores.get(f, 0.0), reverse=True
            )
            surviving = surviving_ranked[:target_count]

        result[group_name] = surviving
        logger.info(
            f"Feature selection for '{group_name}': {len(active)} -> "
            f"{len(surviving)} features"
        )

    # Save results if output_dir specified
    if output_dir is not None:
        fs_dir = os.path.join(output_dir, "feature_selection")
        os.makedirs(fs_dir, exist_ok=True)
        for group_name, features in result.items():
            path = os.path.join(fs_dir, f"{group_name}_features.json")
            with open(path, "w") as f:
                json.dump({"group": group_name, "features": features}, f, indent=2)

    return result


# ---------------------------------------------------------------------------
# Per-position model training
# ---------------------------------------------------------------------------


def train_position_models(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols_by_group: Dict[str, List[str]],
    output_dir: str = "models/player",
) -> Dict[str, Any]:
    """Train all stat models for one position.

    For each stat in POSITION_STAT_PROFILE[position]:
    1. Get stat type and corresponding features/hyperparams
    2. Drop rows with NaN target
    3. Run walk-forward CV
    4. Train final model on all non-holdout data
    5. Save model and metadata

    Args:
        pos_data: Position-filtered DataFrame.
        position: Position code (e.g., 'QB', 'RB').
        feature_cols_by_group: Dict from run_player_feature_selection.
        output_dir: Directory to save models. Default 'models/player'.

    Returns:
        Dict mapping stat -> {model, walk_forward_result, oof_df}.
    """
    stats = POSITION_STAT_PROFILE.get(position, [])
    results: Dict[str, Any] = {}

    for stat in stats:
        stat_type = get_stat_type(stat)
        feat_cols = feature_cols_by_group.get(stat_type, [])

        if not feat_cols:
            logger.warning(f"No features for {position}/{stat} (group={stat_type})")
            continue

        # Only use feature columns that exist
        available = [f for f in feat_cols if f in pos_data.columns]
        if not available:
            logger.warning(f"No available features for {position}/{stat}")
            continue

        # Drop rows with NaN target
        stat_data = pos_data.dropna(subset=[stat]).copy()
        if stat_data.empty:
            logger.warning(f"No non-NaN rows for {position}/{stat}")
            continue

        # Exclude holdout from training
        stat_data = stat_data[stat_data["season"] != HOLDOUT_SEASON]

        params = get_player_model_params(stat)
        model_factory = lambda p=params: make_xgb_model(p)

        # Walk-forward CV
        wf_result, oof_df = player_walk_forward_cv(
            stat_data, available, stat, model_factory
        )

        # Train final model on all non-holdout data
        X_all = stat_data[available]
        y_all = stat_data[stat]

        final_model = make_xgb_model(params)
        # Train without early stopping (use all data, no eval set)
        params_no_es = params.copy()
        params_no_es.pop("early_stopping_rounds", None)
        final_model = xgb.XGBRegressor(**params_no_es)
        final_model.fit(X_all, y_all)

        # Save model
        metadata = {
            "position": position,
            "stat": stat,
            "stat_type": stat_type,
            "mean_mae": wf_result.mean_mae,
            "fold_maes": wf_result.fold_maes,
            "n_features": len(available),
            "features": available,
            "training_seasons": sorted(stat_data["season"].unique().tolist()),
            "n_training_rows": len(stat_data),
            "timestamp": datetime.utcnow().isoformat(),
        }
        save_player_model(final_model, position, stat, metadata, output_dir)

        results[stat] = {
            "model": final_model,
            "walk_forward_result": wf_result,
            "oof_df": oof_df,
        }

        logger.info(
            f"Trained {position}/{stat}: MAE={wf_result.mean_mae:.3f} "
            f"({len(available)} features, {len(stat_data)} rows)"
        )

    return results


def train_position_models_linear(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols: List[str],
    model_type: str = "ridge",
    output_dir: str = "models/player",
) -> Dict[str, Any]:
    """Train Ridge or ElasticNet models for all stats of one position.

    Unlike XGBoost, linear models:
    - Use ALL features (L2/L1 regularization handles multicollinearity)
    - Skip SHAP-based feature selection
    - Need NaN imputation (handled inside the Pipeline)
    - Use _linear_fit_kwargs (no eval_set or early stopping)

    Args:
        pos_data: Position-filtered DataFrame.
        position: Position code (e.g., 'QB', 'RB').
        feature_cols: All candidate feature columns (no per-group splitting).
        model_type: One of 'ridge' or 'elasticnet'.
        output_dir: Directory to save models. Default 'models/player'.

    Returns:
        Dict mapping stat -> {model, walk_forward_result, oof_df, features}.
    """
    import joblib

    stats = POSITION_STAT_PROFILE.get(position, [])
    results: Dict[str, Any] = {}

    if model_type == "ridge":
        factory = create_ridge_pipeline
    elif model_type == "elasticnet":
        factory = create_elasticnet_pipeline
    else:
        raise ValueError(
            f"Unknown model_type '{model_type}'. Use 'ridge' or 'elasticnet'."
        )

    # Use all available feature columns
    available = [f for f in feature_cols if f in pos_data.columns]
    if not available:
        logger.warning(f"No available features for {position}")
        return results

    # Drop zero-variance features (Ridge can handle them, but they add noise)
    non_holdout = pos_data[pos_data["season"] != HOLDOUT_SEASON]
    nonzero_var = [
        f for f in available if f in non_holdout.columns and non_holdout[f].var() > 0.0
    ]
    logger.info(
        f"{position}: {len(nonzero_var)} non-zero-variance features "
        f"(from {len(available)} available)"
    )

    for stat in stats:
        # Drop rows with NaN target
        stat_data = pos_data.dropna(subset=[stat]).copy()
        if stat_data.empty:
            logger.warning(f"No non-NaN rows for {position}/{stat}")
            continue

        # Exclude holdout from training
        stat_data = stat_data[stat_data["season"] != HOLDOUT_SEASON]

        # Walk-forward CV with linear model
        wf_result, oof_df = player_walk_forward_cv(
            stat_data,
            nonzero_var,
            stat,
            model_factory=factory,
            fit_kwargs_fn=_linear_fit_kwargs,
        )

        # Train final model on all non-holdout data
        final_model = factory()
        X_all = stat_data[nonzero_var]
        y_all = stat_data[stat]
        final_model.fit(X_all, y_all)

        # Save model via joblib (sklearn Pipeline, not XGBoost JSON)
        pos_dir = os.path.join(output_dir, position.lower())
        os.makedirs(pos_dir, exist_ok=True)
        model_path = os.path.join(pos_dir, f"{stat}_{model_type}.joblib")
        joblib.dump(final_model, model_path)

        metadata = {
            "position": position,
            "stat": stat,
            "model_type": model_type,
            "mean_mae": wf_result.mean_mae,
            "fold_maes": wf_result.fold_maes,
            "n_features": len(nonzero_var),
            "features": nonzero_var,
            "training_seasons": sorted(stat_data["season"].unique().tolist()),
            "n_training_rows": len(stat_data),
            "timestamp": datetime.utcnow().isoformat(),
        }
        meta_path = os.path.join(pos_dir, f"{stat}_{model_type}_meta.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        results[stat] = {
            "model": final_model,
            "walk_forward_result": wf_result,
            "oof_df": oof_df,
            "features": nonzero_var,
        }

        logger.info(
            f"Trained {model_type} {position}/{stat}: MAE={wf_result.mean_mae:.3f} "
            f"({len(nonzero_var)} features, {len(stat_data)} rows)"
        )

    return results


# ---------------------------------------------------------------------------
# Ensemble stacking: XGB + LGB + Ridge meta-learner
# ---------------------------------------------------------------------------


def assemble_player_oof_matrix(
    xgb_oof: pd.DataFrame,
    lgb_oof: pd.DataFrame,
    pos_data: pd.DataFrame,
    target_col: str,
) -> pd.DataFrame:
    """Assemble 2-column OOF prediction matrix for Ridge meta-learner.

    Joins XGB and LGB OOF predictions on idx (row index), adds actual target.

    Args:
        xgb_oof: XGB OOF DataFrame with idx, oof_prediction columns.
        lgb_oof: LGB OOF DataFrame with idx, oof_prediction columns.
        pos_data: Source position data with target column.
        target_col: Name of the target column in pos_data.

    Returns:
        DataFrame with xgb_pred, lgb_pred, actual columns.
    """
    merged = xgb_oof.rename(columns={"oof_prediction": "xgb_pred"})
    merged = merged.merge(
        lgb_oof.rename(columns={"oof_prediction": "lgb_pred"})[["idx", "lgb_pred"]],
        on="idx",
        how="inner",
    )
    # Add actual target from source data, keyed by idx
    actuals = pos_data[[target_col]].copy()
    actuals["idx"] = actuals.index
    merged = merged.merge(
        actuals.rename(columns={target_col: "actual"}),
        on="idx",
        how="inner",
    )
    return merged


def train_player_ridge_meta(
    oof_matrix: pd.DataFrame,
    target_col: str = "actual",
):
    """Train RidgeCV on 2-column OOF matrix (xgb_pred, lgb_pred).

    Args:
        oof_matrix: DataFrame with xgb_pred, lgb_pred, and target columns.
        target_col: Name of the actual target column.

    Returns:
        Fitted RidgeCV instance.
    """
    from sklearn.linear_model import RidgeCV

    X = oof_matrix[["xgb_pred", "lgb_pred"]].values
    y = oof_matrix[target_col].values
    ridge = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])
    ridge.fit(X, y)
    return ridge


def player_ensemble_stacking(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols_by_group: Dict[str, List[str]],
    output_dir: str = "models/player",
) -> Dict[str, Any]:
    """Train XGB + LGB per stat, stack with Ridge meta-learner.

    Per D-10: XGB + LGB + Ridge (no CatBoost). Returns dict mapping
    stat -> {xgb_wf, lgb_wf, xgb_oof, lgb_oof, ridge, oof_matrix}.

    Args:
        pos_data: Position-filtered DataFrame.
        position: Position code (e.g., 'QB', 'RB').
        feature_cols_by_group: Dict from run_player_feature_selection.
        output_dir: Directory to save models. Default 'models/player'.

    Returns:
        Dict mapping stat -> {xgb_wf, lgb_wf, xgb_oof, lgb_oof, ridge, oof_matrix}.
    """
    import joblib

    stats = POSITION_STAT_PROFILE.get(position, [])
    results: Dict[str, Any] = {}

    for stat in stats:
        stat_type = get_stat_type(stat)
        feat_cols = feature_cols_by_group.get(stat_type, [])
        available = [f for f in feat_cols if f in pos_data.columns]
        if not available:
            continue

        stat_data = pos_data.dropna(subset=[stat]).copy()
        stat_data = stat_data[stat_data["season"] != HOLDOUT_SEASON]
        if stat_data.empty:
            continue

        # XGB walk-forward CV
        xgb_params = get_player_model_params(stat)
        xgb_wf, xgb_oof = player_walk_forward_cv(
            stat_data,
            available,
            stat,
            lambda p=xgb_params: make_xgb_model(p),
            fit_kwargs_fn=_player_xgb_fit_kwargs,
        )

        # LGB walk-forward CV
        lgb_params = get_lgb_params_for_stat(stat)
        lgb_wf, lgb_oof = player_walk_forward_cv(
            stat_data,
            available,
            stat,
            lambda p=lgb_params: make_lgb_model(p),
            fit_kwargs_fn=_player_lgb_fit_kwargs,
        )

        # Assemble OOF matrix and train Ridge
        oof_matrix = assemble_player_oof_matrix(xgb_oof, lgb_oof, stat_data, stat)
        if oof_matrix.empty or len(oof_matrix) < 10:
            logger.warning(f"Insufficient OOF data for {position}/{stat} ensemble")
            continue

        ridge = train_player_ridge_meta(oof_matrix)

        # Generate ensemble OOF predictions
        X_oof = oof_matrix[["xgb_pred", "lgb_pred"]].values
        oof_matrix["ensemble_pred"] = ridge.predict(X_oof)

        # Save models
        pos_dir = os.path.join(output_dir, position.lower())
        os.makedirs(pos_dir, exist_ok=True)

        # Save LGB model (final, trained on all non-holdout data)
        lgb_final = make_lgb_model(lgb_params)
        X_all = stat_data[available]
        y_all = stat_data[stat]
        lgb_final.fit(X_all, y_all)
        joblib.dump(lgb_final, os.path.join(pos_dir, f"{stat}_lgb.joblib"))

        # Save Ridge meta
        joblib.dump(ridge, os.path.join(pos_dir, f"{stat}_ridge.joblib"))

        results[stat] = {
            "xgb_wf": xgb_wf,
            "lgb_wf": lgb_wf,
            "xgb_oof": xgb_oof,
            "lgb_oof": lgb_oof,
            "ridge": ridge,
            "oof_matrix": oof_matrix,
        }
        logger.info(
            f"Ensemble {position}/{stat}: XGB OOF MAE={xgb_wf.mean_mae:.3f}, "
            f"LGB OOF MAE={lgb_wf.mean_mae:.3f}, "
            f"Ridge weights={ridge.coef_.tolist()}"
        )

    return results


# ---------------------------------------------------------------------------
# Model serialization
# ---------------------------------------------------------------------------


def save_player_model(
    model: Any,
    position: str,
    stat: str,
    metadata: dict,
    output_dir: str = "models/player",
) -> None:
    """Save model JSON + metadata sidecar.

    Creates directory {output_dir}/{position_lower}/ if needed.

    Args:
        model: Fitted XGBRegressor.
        position: Position code (e.g., 'RB').
        stat: Stat name (e.g., 'rushing_yards').
        metadata: Dict of metadata (MAE, features, etc.).
        output_dir: Base directory. Default 'models/player'.
    """
    pos_dir = os.path.join(output_dir, position.lower())
    os.makedirs(pos_dir, exist_ok=True)

    model_path = os.path.join(pos_dir, f"{stat}.json")
    meta_path = os.path.join(pos_dir, f"{stat}_meta.json")

    model.save_model(model_path)
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Saved model to {model_path}")


def load_player_model(
    position: str,
    stat: str,
    model_dir: str = "models/player",
) -> xgb.XGBRegressor:
    """Load saved model.

    Args:
        position: Position code (e.g., 'RB').
        stat: Stat name (e.g., 'rushing_yards').
        model_dir: Base directory. Default 'models/player'.

    Returns:
        Loaded XGBRegressor.
    """
    pos_dir = os.path.join(model_dir, position.lower())
    model_path = os.path.join(pos_dir, f"{stat}.json")

    model = xgb.XGBRegressor()
    model.load_model(model_path)
    return model


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def predict_player_stats(
    model_dict: Dict[str, Any],
    player_data: pd.DataFrame,
    position: str,
    feature_cols_by_group: Dict[str, List[str]],
) -> pd.DataFrame:
    """Predict all stats for a position.

    For each stat in POSITION_STAT_PROFILE[position], predicts using
    the corresponding model and feature set.

    Args:
        model_dict: Dict mapping stat -> {model, ...} (from train_position_models).
        player_data: Player-week DataFrame to predict on.
        position: Position code.
        feature_cols_by_group: Features per stat-type group.

    Returns:
        DataFrame with pred_{stat} columns for each predicted stat.
    """
    result_df = player_data.copy()
    stats = POSITION_STAT_PROFILE.get(position, [])

    for stat in stats:
        if stat not in model_dict:
            result_df[f"pred_{stat}"] = np.nan
            continue

        stat_type = get_stat_type(stat)
        feat_cols = feature_cols_by_group.get(stat_type, [])

        if not feat_cols:
            result_df[f"pred_{stat}"] = np.nan
            continue

        # XGBoost requires all trained features to be present. Fill any
        # missing columns with NaN — XGBoost handles NaN natively via its
        # internal sparsity-aware split logic. This allows inference to
        # succeed even when upstream data sources (e.g., QBR for 2024+)
        # are not yet available from nflverse.
        missing = [f for f in feat_cols if f not in player_data.columns]
        predict_df = player_data
        if missing:
            predict_df = player_data.copy()
            for col in missing:
                predict_df[col] = np.nan

        model = model_dict[stat]["model"]
        preds = model.predict(predict_df[feat_cols])
        result_df[f"pred_{stat}"] = preds

    return result_df


def predict_player_stats_linear(
    model_dict: Dict[str, Any],
    player_data: pd.DataFrame,
    position: str,
) -> pd.DataFrame:
    """Predict all stats for a position using linear models.

    Linear model results store their feature list under the 'features' key,
    so this function does not need feature_cols_by_group.

    Args:
        model_dict: Dict mapping stat -> {model, features, ...}
            (from train_position_models_linear).
        player_data: Player-week DataFrame to predict on.
        position: Position code.

    Returns:
        DataFrame with pred_{stat} columns for each predicted stat.
    """
    result_df = player_data.copy()
    stats = POSITION_STAT_PROFILE.get(position, [])

    for stat in stats:
        if stat not in model_dict:
            result_df[f"pred_{stat}"] = np.nan
            continue

        model = model_dict[stat]["model"]
        features = model_dict[stat].get("features", [])
        available = [f for f in features if f in player_data.columns]

        if not available:
            result_df[f"pred_{stat}"] = np.nan
            continue

        preds = model.predict(player_data[available])
        result_df[f"pred_{stat}"] = preds

    return result_df


# ---------------------------------------------------------------------------
# Ship gate: heuristic baseline comparison
# ---------------------------------------------------------------------------


def generate_heuristic_predictions(
    player_data: pd.DataFrame,
    position: str,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Re-run heuristic baseline on the same player-week rows as ML.

    Delegates to ``projection_engine.compute_heuristic_baseline`` — the single
    source of truth for heuristic computation — with an empty opponent-rankings
    DataFrame so the matchup factor defaults to 1.0.  Callers that hold real
    opponent rankings (e.g. ``train_residual_model``, ``train_and_save_residual_models``)
    should call ``compute_production_heuristic`` or ``compute_heuristic_baseline``
    directly for a fully-faithful baseline.

    Backward-compatible return format: the input DataFrame is returned with
    ``pred_{stat}`` columns populated (via usage × matchup × weighted-baseline
    per stat, same as ``compute_heuristic_baseline`` internally) plus a
    ``heuristic_pts`` column holding the fully-scored, ceiling-shrunken total.
    Existing callers that pass the result to ``compute_position_mae`` or
    ``compute_fantasy_points_from_preds`` continue to work unchanged.

    Args:
        player_data: Player-week DataFrame with rolling feature columns.
        position: Position code (e.g., 'QB', 'RB').
        scoring_format: Fantasy scoring format.  Default ``'half_ppr'``.

    Returns:
        DataFrame with ``pred_{stat}`` columns and a ``heuristic_pts`` column
        added, all aligned to the input index.
    """
    from projection_engine import (
        POSITION_STAT_PROFILE,
        _matchup_factor,
        _usage_multiplier,
        _weighted_baseline,
        compute_heuristic_baseline,
    )

    result_df = player_data.copy()
    # Drop opp_rank to avoid merge conflict inside _matchup_factor
    result_df = result_df.drop(columns=["opp_rank"], errors="ignore")

    stats = POSITION_STAT_PROFILE.get(position, [])
    usage_mult = _usage_multiplier(result_df, position)
    # No opponent rankings available here — neutral matchup factor (1.0)
    matchup = _matchup_factor(result_df, pd.DataFrame(), position)

    for stat in stats:
        baseline = _weighted_baseline(result_df, stat)
        result_df[f"pred_{stat}"] = (baseline * usage_mult * matchup).round(2)

    # Heuristic total (includes ceiling shrinkage) via canonical function
    result_df["heuristic_pts"] = compute_heuristic_baseline(
        player_data,
        position,
        opp_rankings=pd.DataFrame(),
        scoring_format=scoring_format,
    )
    return result_df


def compute_position_mae(
    predictions_df: pd.DataFrame,
    position: str,
    scoring_format: str = "half_ppr",
    output_col: str = "pred_fantasy_points",
    actual_col: str = "actual_fantasy_points",
) -> float:
    """Compute MAE between predicted and actual fantasy points for a position.

    Renames pred_{stat} columns to stat names, scores via
    calculate_fantasy_points_df, then compares to actual fantasy points
    computed from label columns. Filters to weeks 3-18 only (D-14).

    Args:
        predictions_df: DataFrame with pred_{stat} columns and actual stat columns.
        position: Position code.
        scoring_format: Scoring format for fantasy point calculation.
        output_col: Column name for predicted fantasy points.
        actual_col: Column name for actual fantasy points.

    Returns:
        MAE float.
    """
    from scoring_calculator import calculate_fantasy_points_df

    stats = POSITION_STAT_PROFILE.get(position, [])
    df = predictions_df.copy()

    # Filter to weeks 3-18 only (per D-14: skip early-season noise)
    if "week" in df.columns:
        df = df[(df["week"] >= 3) & (df["week"] <= 18)]

    if df.empty:
        return 0.0

    # Build predicted-points DataFrame: rename pred_{stat} -> stat for scoring
    # Drop original stat columns first to avoid duplicates after rename
    pred_cols_to_rename = {}
    original_stat_cols_to_drop = []
    for stat in stats:
        pred_col = f"pred_{stat}"
        if pred_col in df.columns:
            pred_cols_to_rename[pred_col] = stat
            if stat in df.columns:
                original_stat_cols_to_drop.append(stat)

    pred_df = df.drop(columns=original_stat_cols_to_drop, errors="ignore")
    pred_df = pred_df.rename(columns=pred_cols_to_rename)
    pred_df = calculate_fantasy_points_df(
        pred_df, scoring_format=scoring_format, output_col=output_col
    )

    # Build actual-points DataFrame from label columns
    actual_df = calculate_fantasy_points_df(
        df, scoring_format=scoring_format, output_col=actual_col
    )

    # Compute MAE
    valid = pred_df[output_col].notna() & actual_df[actual_col].notna()
    if valid.sum() == 0:
        return 0.0

    mae = float(
        np.mean(
            np.abs(pred_df.loc[valid, output_col] - actual_df.loc[valid, actual_col])
        )
    )
    return mae


# ---------------------------------------------------------------------------
# Ship gate: verdict logic
# ---------------------------------------------------------------------------


def ship_gate_verdict(
    position: str,
    ml_mae: float,
    heuristic_mae: float,
    oof_ml_mae: float,
    oof_heuristic_mae: float,
    per_stat_results: list,
) -> dict:
    """Per-position ship-or-skip with dual agreement and safety floor.

    Per D-07, D-08, D-09, D-10, D-11:
    - D-08: 4%+ improvement required on both OOF and holdout
    - D-09: Safety floor -- no individual stat >10% worse
    - D-10: Dual agreement -- both OOF and holdout must pass

    Args:
        position: Position code (e.g., 'QB').
        ml_mae: ML model MAE on holdout (fantasy points).
        heuristic_mae: Heuristic MAE on holdout (fantasy points).
        oof_ml_mae: ML model MAE on OOF data.
        oof_heuristic_mae: Heuristic MAE on OOF data.
        per_stat_results: List of dicts with keys: stat, ml_mae, heuristic_mae.

    Returns:
        Dict with position, ml_mae, heuristic_mae, improvement percentages,
        safety_violation flag, and verdict ("SHIP" or "SKIP").
    """
    holdout_improvement = (
        (heuristic_mae - ml_mae) / heuristic_mae if heuristic_mae > 0 else 0.0
    )
    oof_improvement = (
        (oof_heuristic_mae - oof_ml_mae) / oof_heuristic_mae
        if oof_heuristic_mae > 0
        else 0.0
    )

    # D-09: Safety floor -- no individual stat >10% worse
    safety_violation = False
    for stat_result in per_stat_results:
        if stat_result["heuristic_mae"] > 0:
            if stat_result["ml_mae"] > stat_result["heuristic_mae"] * 1.10:
                safety_violation = True
                break

    # D-08 + D-10: Dual agreement at 4% threshold
    ship = (
        holdout_improvement >= 0.04 and oof_improvement >= 0.04 and not safety_violation
    )

    return {
        "position": position,
        "ml_mae": round(ml_mae, 4),
        "heuristic_mae": round(heuristic_mae, 4),
        "holdout_improvement_pct": round(holdout_improvement * 100, 2),
        "oof_improvement_pct": round(oof_improvement * 100, 2),
        "safety_violation": safety_violation,
        "verdict": "SHIP" if ship else "SKIP",
    }


def build_ship_gate_report(
    position_results: list,
    output_dir: str = "models/player",
) -> dict:
    """Build and save ship gate report from per-position verdict dicts.

    Args:
        position_results: List of dicts from ship_gate_verdict.
        output_dir: Directory to save ship_gate_report.json.

    Returns:
        Dict with keys: positions, summary, timestamp, scoring_format.
    """
    from datetime import datetime as _dt

    ship_count = sum(1 for r in position_results if r["verdict"] == "SHIP")
    total = len(position_results)

    if ship_count == 0:
        summary = "All positions SKIP"
    else:
        summary = f"{ship_count}/{total} positions SHIP"

    report = {
        "positions": position_results,
        "summary": summary,
        "timestamp": _dt.utcnow().isoformat(),
        "scoring_format": "half_ppr",
    }

    # Save to JSON
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "ship_gate_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Ship gate report saved to {report_path}")

    return report


def print_ship_gate_table(report: dict) -> None:
    """Print formatted ship gate table to stdout.

    Args:
        report: Dict from build_ship_gate_report.
    """
    positions = report.get("positions", [])
    if not positions:
        print("No position results to display.")
        return

    # Header
    header = (
        "| Position | Heuristic MAE | ML MAE | Delta % | OOF Delta % "
        "| Safety | Verdict |"
    )
    sep = (
        "|----------|--------------|--------|---------|-------------|"
        "--------|---------|"
    )
    print("\n" + header)
    print(sep)

    for p in positions:
        safety = "FAIL" if p.get("safety_violation", False) else "OK"
        print(
            f"| {p['position']:<8} "
            f"| {p['heuristic_mae']:<12.2f} "
            f"| {p['ml_mae']:<6.2f} "
            f"| {p['holdout_improvement_pct']:>+6.1f}% "
            f"| {p['oof_improvement_pct']:>+10.1f}% "
            f"| {safety:<6} "
            f"| {p['verdict']:<7} |"
        )

    print(f"\nSummary: {report.get('summary', 'N/A')}")
    print(f"Scoring: {report.get('scoring_format', 'N/A')}")
    print()
