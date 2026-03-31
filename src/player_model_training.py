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
    player_walk_forward_cv: Walk-forward CV keyed on row index.
    run_player_feature_selection: SHAP selection per stat-type group.
    train_position_models: Train all stat models for one position.
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
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from config import CONSERVATIVE_PARAMS, HOLDOUT_SEASON
from ensemble_training import make_xgb_model
from feature_selector import _assert_no_holdout, filter_correlated_features
from model_training import WalkForwardResult
from projection_engine import POSITION_STAT_PROFILE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Per D-17: Walk-forward validation seasons for player models
PLAYER_VALIDATION_SEASONS = [2022, 2023, 2024]

# Per D-04: Feature selection groups (stat types that share features)
STAT_TYPE_GROUPS = {
    "yardage": ["passing_yards", "rushing_yards", "receiving_yards"],
    "td": ["passing_tds", "rushing_tds", "receiving_tds"],
    "volume": ["targets", "receptions", "carries"],
    "turnover": ["interceptions"],
}

# Per D-03: Hyperparameter profiles by stat type
YARDAGE_PARAMS = {**CONSERVATIVE_PARAMS, "max_depth": 4, "min_child_weight": 5, "n_estimators": 500}
TD_PARAMS = {**CONSERVATIVE_PARAMS, "max_depth": 3, "min_child_weight": 10, "n_estimators": 300}
VOLUME_PARAMS = {**CONSERVATIVE_PARAMS, "max_depth": 4, "min_child_weight": 5, "n_estimators": 500}
TURNOVER_PARAMS = {**CONSERVATIVE_PARAMS, "max_depth": 3, "min_child_weight": 10, "n_estimators": 300}

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


# ---------------------------------------------------------------------------
# XGBoost fit kwargs (adapted from ensemble_training._xgb_fit_kwargs)
# ---------------------------------------------------------------------------


def _player_xgb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """XGBoost fit kwargs with eval_set for early stopping."""
    return {"eval_set": [(X_val, y_val)], "verbose": False}


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

        fold_details.append({
            "train_seasons": train_seasons,
            "val_season": val_season,
            "train_size": len(train),
            "val_size": len(val),
            "mae": mae,
        })

        # Collect OOF predictions keyed by row index (NOT game_id)
        oof_fold = pd.DataFrame({
            "idx": val.index.values,
            "season": val["season"].values,
            "week": val["week"].values,
            "oof_prediction": preds,
        })
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
            pos for pos in positions
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

        model = xgb.XGBRegressor(
            early_stopping_rounds=early_stopping, **params_copy
        )
        model.fit(X_train, y_train, eval_set=[(X_eval, y_eval)], verbose=False)

        # Compute SHAP importances
        sample_size = min(500, len(group_data))
        X_sample = group_data[active].sample(
            n=sample_size, random_state=params_copy.get("random_state", 42)
        )
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)
        mean_abs_shap = np.mean(np.abs(shap_values), axis=0)

        shap_scores = {
            col: float(score) for col, score in zip(active, mean_abs_shap)
        }

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
        available = [f for f in feat_cols if f in player_data.columns]

        if not available:
            result_df[f"pred_{stat}"] = np.nan
            continue

        model = model_dict[stat]["model"]
        preds = model.predict(player_data[available])
        result_df[f"pred_{stat}"] = preds

    return result_df
