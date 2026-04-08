"""Hybrid projection: blend heuristic + ML or train residual correction models.

Approach 1 (Simple Blend):
    blended = alpha * heuristic + (1 - alpha) * ML
    Search alpha per position to minimise MAE.

Approach 2 (Residual Model):
    target = actual_fantasy_points - heuristic_fantasy_points
    Train RidgeCV on features -> residual, then final = heuristic + ridge.predict()

Approach 3 (Production Residual — save/load/apply):
    train_and_save_residual_models: Train residual models (Ridge or LightGBM), save.
    load_residual_model: Load a saved residual model from disk.
    apply_residual_correction: Correct heuristic projections using saved residual model.

Supports two residual model types:
    - 'ridge': RidgeCV pipeline (original, used as fallback)
    - 'lgb': LightGBM with SHAP feature selection + early stopping (Phase 55)

LightGBM residual models with 60 SHAP-selected features outperform Ridge on all
positions: WR -37%, TE -33%, RB -32%, QB -76% improvement over heuristic.

Exports:
    compute_fantasy_points_from_preds: Convert pred_{stat} columns to fantasy points.
    evaluate_blend: Grid-search alpha for heuristic-ML blend.
    train_residual_model: Walk-forward CV residual correction model.
    train_and_save_residual_models: Train + persist residual models.
    load_residual_model: Load saved residual model.
    apply_residual_correction: Apply residual correction to heuristic projections.
    load_graph_features: Load and merge all Silver graph feature tables by season.
    GRAPH_FEATURE_SET: Complete list of 49 graph feature column names.
"""

import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
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
# LightGBM residual model configuration (Phase 55)
# ---------------------------------------------------------------------------

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

# Default SHAP feature count per position (from Phase 55 experiment)
DEFAULT_SHAP_FEATURE_COUNT = 60

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_SILVER_GRAPH_DIR = os.path.join(_BASE_DIR, "data", "silver", "graph_features")

# ---------------------------------------------------------------------------
# Complete set of 49 graph feature columns (from all Silver graph tables)
# ---------------------------------------------------------------------------

# WR matchup features (4)
_WR_MATCHUP_FEATURES = [
    "def_pass_epa_allowed",
    "wr_epa_vs_defense_history",
    "cb_cooccurrence_quality",
    "similar_wr_vs_defense",
]

# TE matchup features (4)
_TE_MATCHUP_FEATURES = [
    "te_lb_coverage_rate",
    "te_vs_defense_epa_history",
    "te_red_zone_target_share",
    "def_te_fantasy_pts_allowed",
]

# QB-WR chemistry features (5)
_QB_WR_CHEMISTRY_FEATURES = [
    "qb_wr_chemistry_epa_roll3",
    "qb_wr_pair_comp_rate_roll3",
    "qb_wr_pair_target_share",
    "qb_wr_pair_games_together",
    "qb_wr_pair_td_rate",
]

# Red zone features (7)
_RED_ZONE_FEATURES = [
    "rz_target_share_roll3",
    "rz_carry_share_roll3",
    "rz_td_rate_roll3",
    "rz_usage_vs_general",
    "team_rz_trips_roll3",
    "rz_td_regression",
    "opp_rz_td_rate_allowed_roll3",
]

# Game script features (6)
_GAME_SCRIPT_FEATURES = [
    "usage_when_trailing_roll3",
    "usage_when_leading_roll3",
    "garbage_time_share_roll3",
    "clock_killer_share_roll3",
    "script_volatility",
    "predicted_script_boost",
]

# Injury cascade features (4)
_INJURY_CASCADE_FEATURES = [
    "injury_cascade_target_boost",
    "injury_cascade_carry_boost",
    "teammate_injured_starter",
    "historical_absorption_rate",
]

# OL/RB features (5)
_OL_RB_FEATURES = [
    "ol_starters_active",
    "ol_backup_insertions",
    "rb_ypc_with_full_ol",
    "rb_ypc_delta_backup_ol",
    "ol_continuity_score",
]

# Scheme/defensive front features for RB (4)
_SCHEME_FEATURES = [
    "def_front_quality_vs_run",
    "scheme_matchup_score",
    "rb_ypc_by_gap_vs_defense",
    "def_run_epa_allowed",
]

# All 49 graph features combined (the complete "graph feature set")
GRAPH_FEATURE_SET: List[str] = (
    _WR_MATCHUP_FEATURES
    + _TE_MATCHUP_FEATURES
    + _QB_WR_CHEMISTRY_FEATURES
    + _RED_ZONE_FEATURES
    + _GAME_SCRIPT_FEATURES
    + _INJURY_CASCADE_FEATURES
    + _OL_RB_FEATURES
    + _SCHEME_FEATURES
)

# Position-specific graph feature subsets for targeted enrichment
GRAPH_FEATURES_BY_POSITION: Dict[str, List[str]] = {
    "WR": (
        _QB_WR_CHEMISTRY_FEATURES
        + _WR_MATCHUP_FEATURES
        + _GAME_SCRIPT_FEATURES
        + _RED_ZONE_FEATURES
        + _INJURY_CASCADE_FEATURES
    ),
    "TE": (
        _TE_MATCHUP_FEATURES
        + _RED_ZONE_FEATURES
        + _GAME_SCRIPT_FEATURES
        + _QB_WR_CHEMISTRY_FEATURES
        + _INJURY_CASCADE_FEATURES
    ),
    "RB": (
        _OL_RB_FEATURES
        + _SCHEME_FEATURES
        + _RED_ZONE_FEATURES
        + _INJURY_CASCADE_FEATURES
        + _GAME_SCRIPT_FEATURES
    ),
    "QB": (
        _QB_WR_CHEMISTRY_FEATURES
        + _RED_ZONE_FEATURES
        + _GAME_SCRIPT_FEATURES
        + _INJURY_CASCADE_FEATURES
    ),
}


# ---------------------------------------------------------------------------
# Graph feature loading
# ---------------------------------------------------------------------------


def _read_latest_graph_parquet(season: int, prefix: str) -> pd.DataFrame:
    """Read the latest Silver graph feature parquet for a given prefix and season.

    Args:
        season: NFL season year.
        prefix: File prefix (e.g. 'graph_qb_wr_chemistry').

    Returns:
        DataFrame from the latest matching parquet, or empty DataFrame if none found.
    """
    season_dir = os.path.join(_SILVER_GRAPH_DIR, f"season={season}")
    pattern = os.path.join(season_dir, f"{prefix}_*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    try:
        return pd.read_parquet(files[-1])
    except Exception as exc:
        logger.warning("Failed to read %s for season=%d: %s", prefix, season, exc)
        return pd.DataFrame()


def load_graph_features(
    seasons: List[int],
    position_filter: Optional[str] = None,
) -> pd.DataFrame:
    """Load and merge all Silver graph feature tables across seasons.

    Reads each graph feature table (QB-WR chemistry, game script, red zone,
    WR matchup, TE matchup, injury cascade, OL/RB, scheme) from
    data/silver/graph_features/ and merges them into a single per-player-week
    DataFrame. Uses a left-join cascade on (player_id, season, week).

    The ``graph_all_features`` consolidated file is used as the primary source
    when available. Individual topic files are loaded as fallback to ensure
    maximum coverage.

    Graph features already have temporal integrity baked in (shift(1) lag is
    applied during graph feature computation in compute_graph_features.py).
    NaN values for missing player-weeks are expected and handled by the Ridge
    pipeline's SimpleImputer.

    Args:
        seasons: List of NFL season years to load.
        position_filter: If provided, only return position-relevant features
            for this position (e.g. 'WR'). None returns all graph features.

    Returns:
        DataFrame with columns [player_id, season, week, <graph_feature_cols>].
        Empty DataFrame if no graph feature data found for any season.

    Example:
        >>> gf = load_graph_features([2022, 2023, 2024], position_filter='WR')
        >>> gf.columns.tolist()[:4]
        ['player_id', 'season', 'week', 'qb_wr_chemistry_epa_roll3']
    """
    join_keys = ["player_id", "season", "week"]

    # Table definitions: (file_prefix, feature_columns, join_on)
    # scheme features join on team+season+week instead of player_id
    _player_tables = [
        ("graph_qb_wr_chemistry", _QB_WR_CHEMISTRY_FEATURES),
        ("graph_red_zone", _RED_ZONE_FEATURES),
        ("graph_game_script", _GAME_SCRIPT_FEATURES),
        ("graph_wr_matchup", _WR_MATCHUP_FEATURES),
        ("graph_te_matchup", _TE_MATCHUP_FEATURES),
        ("graph_injury_cascade", _INJURY_CASCADE_FEATURES),
        ("graph_ol_rb", _OL_RB_FEATURES),
    ]

    all_season_dfs: List[pd.DataFrame] = []

    for season in seasons:
        # Attempt consolidated file first for efficiency
        consolidated = _read_latest_graph_parquet(season, "graph_all_features")
        if not consolidated.empty and all(k in consolidated.columns for k in join_keys):
            all_season_dfs.append(consolidated)
            logger.debug(
                "Season %d: loaded consolidated graph features (%d rows)",
                season,
                len(consolidated),
            )
            continue

        # Fall back to individual tables merged together
        logger.debug(
            "Season %d: consolidated graph_all_features not found, "
            "loading individual tables",
            season,
        )
        base_df: Optional[pd.DataFrame] = None

        for prefix, feat_cols in _player_tables:
            tbl = _read_latest_graph_parquet(season, prefix)
            if tbl.empty:
                continue

            avail_keys = [k for k in join_keys if k in tbl.columns]
            if len(avail_keys) < 3:
                logger.debug(
                    "Season %d | %s: missing join keys, skipping", season, prefix
                )
                continue

            avail_feats = [c for c in feat_cols if c in tbl.columns]
            if not avail_feats:
                continue

            subset = tbl[avail_keys + avail_feats].copy()

            if base_df is None:
                base_df = subset
            else:
                dup_cols = [
                    c for c in avail_feats if c in base_df.columns
                ]
                merge_feats = [c for c in avail_feats if c not in dup_cols]
                if not merge_feats:
                    continue
                base_df = base_df.merge(
                    subset[avail_keys + merge_feats],
                    on=avail_keys,
                    how="outer",
                )

        # Scheme features join on team+season+week — handled separately
        scheme_tbl = _read_latest_graph_parquet(season, "graph_scheme")
        if not scheme_tbl.empty:
            team_keys = ["team", "season", "week"]
            avail_team_keys = [k for k in team_keys if k in scheme_tbl.columns]
            avail_scheme_feats = [
                c for c in _SCHEME_FEATURES if c in scheme_tbl.columns
            ]
            if len(avail_team_keys) >= 3 and avail_scheme_feats:
                if base_df is not None and "recent_team" in base_df.columns:
                    base_df = base_df.merge(
                        scheme_tbl[avail_team_keys + avail_scheme_feats],
                        left_on=["recent_team", "season", "week"],
                        right_on=avail_team_keys,
                        how="left",
                        suffixes=("", "__scheme"),
                    )
                    dup = [c for c in base_df.columns if c.endswith("__scheme")]
                    base_df = base_df.drop(columns=dup + ["team"], errors="ignore")

        if base_df is not None and not base_df.empty:
            all_season_dfs.append(base_df)

    if not all_season_dfs:
        logger.warning("load_graph_features: no data found for seasons=%s", seasons)
        return pd.DataFrame()

    result = pd.concat(all_season_dfs, ignore_index=True)

    # Ensure join keys are present
    missing_keys = [k for k in join_keys if k not in result.columns]
    if missing_keys:
        logger.warning(
            "load_graph_features: missing join keys %s in result", missing_keys
        )
        return pd.DataFrame()

    # Deduplicate keeping last (most recent computation)
    result = result.drop_duplicates(subset=join_keys, keep="last")

    # Apply position filter — keep only position-relevant graph columns
    if position_filter and position_filter.upper() in GRAPH_FEATURES_BY_POSITION:
        relevant = GRAPH_FEATURES_BY_POSITION[position_filter.upper()]
        available_relevant = [c for c in relevant if c in result.columns]
        result = result[join_keys + available_relevant].copy()

    logger.info(
        "load_graph_features: %d rows, %d graph feature cols across %d seasons",
        len(result),
        len(result.columns) - len(join_keys),
        len(seasons),
    )
    return result


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


def _select_residual_features(
    train_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "residual",
    target_count: int = DEFAULT_SHAP_FEATURE_COUNT,
    nan_threshold: float = 0.90,
) -> List[str]:
    """SHAP-based feature selection for residual prediction.

    Filters features with >nan_threshold NaN rate, then runs SHAP importance
    ranking with correlation filtering via feature_selector.

    Args:
        train_data: Training DataFrame with features and target column.
        feature_cols: Candidate feature column names.
        target_col: Target column name (residual).
        target_count: Number of features to select.
        nan_threshold: Maximum NaN fraction to keep a feature.

    Returns:
        List of selected feature column names.
    """
    from feature_selector import select_features_for_fold

    # Filter to features available and with sufficient non-NaN coverage
    available = [f for f in feature_cols if f in train_data.columns]
    nan_rates = train_data[available].isna().mean()
    pos_features = [f for f in available if nan_rates[f] < nan_threshold]

    if len(pos_features) < target_count:
        logger.info(
            "Only %d features pass NaN filter (threshold=%.0f%%); using all",
            len(pos_features),
            nan_threshold * 100,
        )
        return pos_features

    result = select_features_for_fold(
        train_data=train_data,
        feature_cols=pos_features,
        target_col=target_col,
        target_count=target_count,
        correlation_threshold=0.90,
    )

    logger.info(
        "SHAP feature selection: %d -> %d features (correlation dropped %d)",
        len(pos_features),
        result.n_selected,
        len(result.dropped_correlation),
    )
    return result.selected_features


def _train_lgb_residual(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_eval: Optional[np.ndarray] = None,
    y_eval: Optional[np.ndarray] = None,
) -> lgb.LGBMRegressor:
    """Train a LightGBM residual model with early stopping.

    Args:
        X_train: Training features (imputed).
        y_train: Training residuals.
        X_eval: Eval features for early stopping (optional).
        y_eval: Eval residuals for early stopping (optional).

    Returns:
        Fitted LGBMRegressor.
    """
    model = lgb.LGBMRegressor(**RESIDUAL_LGB_PARAMS)

    if X_eval is not None and y_eval is not None and len(X_eval) > 10:
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_eval, y_eval)],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )
    else:
        model.fit(X_train, y_train)

    return model


def train_and_save_residual_models(
    positions: Optional[List[str]] = None,
    scoring_format: str = "half_ppr",
    output_dir: Optional[str] = None,
    use_graph_features: bool = False,
    model_type: str = "lgb",
    shap_feature_count: int = DEFAULT_SHAP_FEATURE_COUNT,
) -> Dict[str, Dict[str, Any]]:
    """Train residual correction models and save to disk.

    For each position, trains a model on:
        residual = actual_fantasy_points - production_heuristic_points
    using the full feature vector from assemble_multiyear_player_features
    and the unified production heuristic from unified_evaluation.py.

    Supports two model types:
        - 'lgb': LightGBM with SHAP feature selection + early stopping (default)
        - 'ridge': RidgeCV pipeline (original approach)

    When model_type='lgb', SHAP-based feature selection reduces the full
    feature set to shap_feature_count features per position. Phase 55
    showed LightGBM with 60 SHAP-selected features outperforms Ridge
    on all positions.

    The final production model is trained on ALL non-holdout data. For
    LightGBM, the most recent non-holdout season is used as early-stopping
    eval set.

    Args:
        positions: Positions to train residual models for.
            Default ['QB', 'RB', 'WR', 'TE'].
        scoring_format: Scoring format string.
        output_dir: Directory to save models. Default 'models/residual'.
        use_graph_features: If True, explicitly load and merge all Silver graph
            feature tables into the training data.
        model_type: 'lgb' for LightGBM (default) or 'ridge' for RidgeCV.
        shap_feature_count: Number of features to select via SHAP when
            model_type='lgb'. Default 60.

    Returns:
        Dict mapping position -> {mae, model_type, n_train, n_features, features}.
    """
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

    if positions is None:
        positions = ["QB", "RB", "WR", "TE"]
    if output_dir is None:
        output_dir = RESIDUAL_MODEL_DIR

    os.makedirs(output_dir, exist_ok=True)

    # Load full feature data
    logger.info("Loading player feature data for residual training...")
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        logger.error("No data assembled for residual training")
        return {}

    # Optionally merge graph features explicitly
    graph_features_added: int = 0
    if use_graph_features:
        logger.info(
            "Loading graph features from Silver for explicit enrichment..."
        )
        graph_df = load_graph_features(PLAYER_DATA_SEASONS)
        if not graph_df.empty:
            join_keys = ["player_id", "season", "week"]
            existing_cols = set(all_data.columns)
            new_graph_cols = [
                c
                for c in graph_df.columns
                if c not in join_keys and c not in existing_cols
            ]
            if new_graph_cols:
                all_data = all_data.merge(
                    graph_df[join_keys + new_graph_cols],
                    on=join_keys,
                    how="left",
                )
                graph_features_added = len(new_graph_cols)
                logger.info(
                    "Merged %d new graph features (total cols: %d)",
                    graph_features_added,
                    len(all_data.columns),
                )
            else:
                graph_features_added = len(
                    [c for c in GRAPH_FEATURE_SET if c in all_data.columns]
                )

    feature_cols = get_player_feature_columns(all_data)
    logger.info("Found %d candidate features", len(feature_cols))

    # Build opponent rankings (for production heuristic)
    opp_rankings = build_opp_rankings(PLAYER_DATA_SEASONS)

    results: Dict[str, Dict[str, Any]] = {}

    for position in positions:
        logger.info(
            "Training %s residual model for %s...", model_type.upper(), position
        )
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

        if pos_data.empty:
            logger.warning("No data for %s", position)
            continue

        # Compute heuristic + actual using unified evaluation
        prod_pts = compute_production_heuristic(
            pos_data, position, opp_rankings, scoring_format
        )
        actual_pts = compute_actual_fantasy_points(pos_data, scoring_format)

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
        train_data["residual"] = residual

        # Feature selection
        available_features = [f for f in feature_cols if f in train_data.columns]
        if not available_features:
            logger.warning("No features for %s", position)
            continue

        if shap_feature_count < len(available_features):
            # SHAP-based feature selection (for both Ridge and LGB)
            selected_features = _select_residual_features(
                train_data,
                available_features,
                target_col="residual",
                target_count=shap_feature_count,
            )
        else:
            selected_features = available_features

        X_train_raw = train_data[selected_features]
        y_train = residual

        if model_type == "lgb":
            # Impute then train LightGBM with early stopping
            imputer = SimpleImputer(strategy="median")
            X_train_imp = imputer.fit_transform(X_train_raw)

            # Use most recent season as early-stopping eval set
            seasons = sorted(train_data["season"].unique())
            if len(seasons) >= 2:
                eval_season = seasons[-1]
                eval_mask = train_data["season"] == eval_season
                tr_mask = ~eval_mask
                tr_idx = np.where(tr_mask.values)[0]
                es_idx = np.where(eval_mask.values)[0]

                lgb_model = _train_lgb_residual(
                    X_train_imp[tr_idx],
                    y_train.iloc[tr_idx].values,
                    X_train_imp[es_idx],
                    y_train.iloc[es_idx].values,
                )
            else:
                lgb_model = _train_lgb_residual(
                    X_train_imp, y_train.values
                )

            train_preds = lgb_model.predict(X_train_imp)
            train_mae = float(mean_absolute_error(y_train, train_preds))

            # Save imputer + LightGBM model + metadata
            model_path = os.path.join(
                output_dir, f"{position.lower()}_residual.joblib"
            )
            imputer_path = os.path.join(
                output_dir, f"{position.lower()}_residual_imputer.joblib"
            )
            meta_path = os.path.join(
                output_dir, f"{position.lower()}_residual_meta.json"
            )

            joblib.dump(lgb_model, model_path)
            joblib.dump(imputer, imputer_path)

            meta = {
                "position": position,
                "model_type": "lgb",
                "scoring_format": scoring_format,
                "n_train": len(X_train_raw),
                "train_residual_mae": train_mae,
                "n_features": len(selected_features),
                "features": selected_features,
                "best_iteration": getattr(lgb_model, "best_iteration_", -1),
                "graph_features_added": graph_features_added,
                "lgb_params": RESIDUAL_LGB_PARAMS,
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

            logger.info(
                "%s LGB residual saved: n=%d, features=%d, "
                "best_iter=%d, train_mae=%.3f",
                position,
                len(X_train_raw),
                len(selected_features),
                meta["best_iteration"],
                train_mae,
            )

            results[position] = {
                "mae": train_mae,
                "model_type": "lgb",
                "n_train": len(X_train_raw),
                "n_features": len(selected_features),
                "features": selected_features,
                "graph_features_added": graph_features_added,
            }

        else:
            # Ridge pipeline (original approach)
            model = Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
                ]
            )
            model.fit(X_train_raw, y_train)

            ridge_alpha = float(model.named_steps["model"].alpha_)
            train_preds = model.predict(X_train_raw)
            train_mae = float(mean_absolute_error(y_train, train_preds))

            model_path = os.path.join(
                output_dir, f"{position.lower()}_residual.joblib"
            )
            meta_path = os.path.join(
                output_dir, f"{position.lower()}_residual_meta.json"
            )

            joblib.dump(model, model_path)
            meta = {
                "position": position,
                "model_type": "ridge",
                "scoring_format": scoring_format,
                "ridge_alpha": ridge_alpha,
                "n_train": len(X_train_raw),
                "train_residual_mae": train_mae,
                "n_features": len(selected_features),
                "features": selected_features,
                "graph_features_added": graph_features_added,
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

            logger.info(
                "%s Ridge residual saved: alpha=%.3f, n=%d, features=%d",
                position,
                ridge_alpha,
                len(X_train_raw),
                len(selected_features),
            )

            results[position] = {
                "mae": train_mae,
                "model_type": "ridge",
                "ridge_alpha": ridge_alpha,
                "n_train": len(X_train_raw),
                "n_features": len(selected_features),
                "features": selected_features,
                "graph_features_added": graph_features_added,
            }

    return results


def load_residual_model(
    position: str,
    model_dir: Optional[str] = None,
) -> Tuple[Any, Dict[str, Any]]:
    """Load a saved residual correction model and its metadata.

    Supports both Ridge (sklearn Pipeline) and LightGBM models.
    For LightGBM models, also loads the associated imputer.

    Args:
        position: Position code (e.g., 'WR', 'TE').
        model_dir: Directory containing saved models. Default 'models/residual'.

    Returns:
        Tuple of (fitted model, metadata dict).
        For LightGBM, model is a dict {'model': LGBMRegressor, 'imputer': SimpleImputer}.
        For Ridge, model is a sklearn Pipeline.

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

    # For LightGBM models, also load the imputer
    if meta.get("model_type") == "lgb":
        imputer_path = os.path.join(
            model_dir, f"{position.lower()}_residual_imputer.joblib"
        )
        imputer = None
        if os.path.exists(imputer_path):
            imputer = joblib.load(imputer_path)
        model = {"model": model, "imputer": imputer}

    return model, meta


def apply_residual_correction(
    heuristic_projections: pd.DataFrame,
    player_features: pd.DataFrame,
    position: str,
    model_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Apply residual correction to heuristic projections.

    Loads a pre-trained residual model (Ridge or LightGBM), predicts the
    correction (residual), and adds it to heuristic projected_points.
    Floors at 0.0.

    Supports both model types:
        - Ridge: sklearn Pipeline with built-in imputer
        - LightGBM: separate imputer + LGBMRegressor

    Args:
        heuristic_projections: DataFrame with 'projected_points' and
            'player_id' columns from heuristic engine.
        player_features: Silver-layer features DataFrame with feature
            columns matching the model's training features.
        position: Position code ('WR', 'TE', 'QB', 'RB').
        model_dir: Directory containing saved residual models.

    Returns:
        DataFrame with corrected projected_points. Unchanged if model
        loading fails or no matching features.
    """
    try:
        model_obj, meta = load_residual_model(position, model_dir)
    except FileNotFoundError:
        logger.warning("No residual model for %s; returning heuristic as-is", position)
        return heuristic_projections

    model_type = meta.get("model_type", "ridge")
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

    # Build full feature matrix (all model features, NaN for missing ones)
    feature_data = {
        f: merged[f].values if f in merged.columns else np.nan for f in features
    }
    X = pd.DataFrame(feature_data, index=merged.index)

    has_features = X[available].notna().any(axis=1)

    if has_features.sum() == 0:
        logger.warning("No rows with features for %s residual", position)
        return heuristic_projections

    logger.info(
        "%s (%s): %d/%d features available; %d imputed",
        position,
        model_type,
        len(available),
        len(features),
        len(features) - len(available),
    )

    corrections = np.zeros(len(merged))
    if has_features.any():
        X_predict = X[has_features]

        if model_type == "lgb" and isinstance(model_obj, dict):
            # LightGBM model with separate imputer
            lgb_model = model_obj["model"]
            imputer = model_obj.get("imputer")
            if imputer is not None:
                X_imp = imputer.transform(X_predict)
            else:
                X_imp = X_predict.fillna(0.0).values
            corrections[has_features] = lgb_model.predict(X_imp)
        else:
            # Ridge Pipeline (has built-in imputer)
            corrections[has_features] = model_obj.predict(X_predict)

    # Apply correction (floor at 0)
    corrected = merged["projected_points"].values + corrections
    result["projected_points"] = np.clip(corrected, 0.0, None).round(2)

    logger.info(
        "%s residual correction (%s): %d players, mean correction=%.2f",
        position,
        model_type,
        has_features.sum(),
        float(np.mean(corrections[has_features])) if has_features.any() else 0.0,
    )

    return result
