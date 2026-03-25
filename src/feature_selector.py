"""Walk-forward-safe feature selection via SHAP importance and correlation filtering.

Reduces a large feature set to an optimal subset by:
1. Training a quick XGBoost model and computing SHAP importance scores
2. Removing one of each highly correlated pair (keeping the higher-SHAP feature)
3. Truncating to a target feature count by SHAP rank

All operations run on a single fold's training data -- never the full dataset.
The 2024 holdout season is explicitly guarded against inclusion.

Exports:
    FeatureSelectionResult: Dataclass holding selection results and metadata.
    select_features_for_fold: Run full selection pipeline on one fold's training data.
    filter_correlated_features: Remove one of each highly correlated pair.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from config import CONSERVATIVE_PARAMS, HOLDOUT_SEASON


@dataclass
class FeatureSelectionResult:
    """Result container for the feature selection pipeline.

    Attributes:
        selected_features: Features that survived all filtering steps.
        dropped_correlation: Map of dropped feature -> the correlated feature that was kept.
        dropped_low_importance: Features dropped because they ranked below the target count.
        shap_scores: Map of feature name -> mean absolute SHAP value.
        correlated_pairs: List of (feat_a, feat_b, correlation) tuples above threshold.
        n_original: Number of features before any filtering.
        n_after_correlation: Number of features after correlation filtering.
        n_selected: Final number of selected features.
        fold_seasons: Seasons present in the training data used for this selection (D-09).
    """

    selected_features: List[str]
    dropped_correlation: Dict[str, str]
    dropped_low_importance: List[str]
    shap_scores: Dict[str, float]
    correlated_pairs: List[Tuple[str, str, float]]
    n_original: int
    n_after_correlation: int
    n_selected: int
    fold_seasons: Optional[List[int]] = None


def _assert_no_holdout(data: pd.DataFrame, context: str) -> None:
    """Raise ValueError if holdout season data is present.

    Args:
        data: DataFrame that must contain a 'season' column.
        context: Description of the operation for the error message.

    Raises:
        ValueError: If HOLDOUT_SEASON is found in data['season'].
    """
    if HOLDOUT_SEASON in data["season"].values:
        raise ValueError(
            f"Holdout season {HOLDOUT_SEASON} found in data during {context}. "
            "Feature selection must never use holdout data."
        )


def filter_correlated_features(
    data: pd.DataFrame,
    feature_cols: List[str],
    shap_rank: Dict[str, float],
    threshold: float = 0.90,
) -> Tuple[List[str], Dict[str, str], List[Tuple[str, str, float]]]:
    """Remove one of each highly correlated pair, keeping the higher-SHAP feature.

    Processes pairs in descending order of correlation (greedy) so transitive
    chains are resolved by dropping the weakest link first.

    Args:
        data: Training DataFrame containing feature columns.
        feature_cols: List of feature column names to check.
        shap_rank: Map of feature -> SHAP importance (higher = more important).
        threshold: Pearson correlation threshold (absolute). Default 0.90 (D-02).

    Returns:
        Tuple of:
            surviving: Features that passed the correlation filter.
            dropped_map: {dropped_feature: kept_feature} pairs.
            pairs: List of (feat_a, feat_b, r) tuples above threshold, sorted descending.
    """
    corr = data[feature_cols].corr(method="pearson").abs()

    dropped = set()
    dropped_map: Dict[str, str] = {}
    pairs: List[Tuple[str, str, float]] = []

    # Get upper triangle pairs above threshold, sorted by correlation (highest first)
    upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1))
    high_corr = []
    for i, row_name in enumerate(upper.index):
        for j, col_name in enumerate(upper.columns):
            if j > i:
                val = upper.iloc[i, j]
                if pd.notna(val) and val > threshold:
                    high_corr.append((row_name, col_name, float(val)))

    high_corr.sort(key=lambda x: x[2], reverse=True)

    for feat_a, feat_b, r in high_corr:
        if feat_a in dropped or feat_b in dropped:
            continue
        pairs.append((feat_a, feat_b, r))
        # Drop the one with lower SHAP importance (D-03)
        if shap_rank.get(feat_a, 0.0) >= shap_rank.get(feat_b, 0.0):
            dropped.add(feat_b)
            dropped_map[feat_b] = feat_a
        else:
            dropped.add(feat_a)
            dropped_map[feat_a] = feat_b

    surviving = [f for f in feature_cols if f not in dropped]
    return surviving, dropped_map, pairs


def select_features_for_fold(
    train_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    target_count: int,
    correlation_threshold: float = 0.90,
    params: Optional[Dict[str, Any]] = None,
) -> FeatureSelectionResult:
    """Run the full feature selection pipeline on one fold's training data.

    Steps (D-01):
        1. Guard: reject if holdout season data is present (FSEL-04).
        2. Drop zero-variance features from the fold's feature list.
        3. Train quick XGBoost -> compute SHAP -> rank features (FSEL-02).
        4. Correlation filter: remove one of each pair with r > threshold (FSEL-01).
        5. Truncate surviving features to target_count by SHAP rank.

    Args:
        train_data: Training DataFrame for this fold (must NOT contain holdout season).
        feature_cols: All candidate feature column names.
        target_col: Target column name (e.g., 'actual_margin').
        target_count: Desired number of features after selection.
        correlation_threshold: Pearson r threshold for pair removal. Default 0.90.
        params: XGBoost parameters. Defaults to CONSERVATIVE_PARAMS.

    Returns:
        FeatureSelectionResult with all fields populated.

    Raises:
        ValueError: If train_data contains HOLDOUT_SEASON.
    """
    # Step 1: Holdout guard (FSEL-04, D-08)
    _assert_no_holdout(train_data, "feature selection")

    if params is None:
        params = CONSERVATIVE_PARAMS.copy()
    else:
        params = params.copy()

    n_original = len(feature_cols)

    # Step 2: Drop zero-variance features
    variances = train_data[feature_cols].var()
    active_features = [f for f in feature_cols if variances[f] > 0.0]

    # Step 3: Train quick XGBoost and compute SHAP (FSEL-02)
    early_stopping_rounds = params.pop("early_stopping_rounds", 50)

    # 20% random split for eval_set (early stopping only, not temporal)
    from sklearn.model_selection import train_test_split

    X = train_data[active_features]
    y = train_data[target_col]

    X_train, X_eval, y_train, y_eval = train_test_split(
        X, y, test_size=0.2, random_state=params.get("random_state", 42)
    )

    model = xgb.XGBRegressor(
        early_stopping_rounds=early_stopping_rounds,
        **params,
    )
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_eval, y_eval)],
        verbose=False,
    )

    # SHAP on a subsample for speed
    sample_size = min(500, len(train_data))
    X_sample = train_data[active_features].sample(
        n=sample_size, random_state=params.get("random_state", 42)
    )

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)
    mean_abs_shap = np.mean(np.abs(shap_values), axis=0)

    shap_scores: Dict[str, float] = {
        col: float(score) for col, score in zip(active_features, mean_abs_shap)
    }

    # Step 4: Correlation filter (FSEL-01)
    surviving, dropped_map, correlated_pairs = filter_correlated_features(
        train_data, active_features, shap_scores, threshold=correlation_threshold
    )

    n_after_correlation = len(surviving)

    # Step 5: Truncate to target_count by SHAP rank (highest first)
    surviving_ranked = sorted(surviving, key=lambda f: shap_scores.get(f, 0.0), reverse=True)

    actual_count = min(target_count, len(surviving_ranked))
    selected = surviving_ranked[:actual_count]
    dropped_low = surviving_ranked[actual_count:]

    # Record fold seasons (D-09)
    fold_seasons = sorted(train_data["season"].unique().tolist())

    return FeatureSelectionResult(
        selected_features=selected,
        dropped_correlation=dropped_map,
        dropped_low_importance=dropped_low,
        shap_scores=shap_scores,
        correlated_pairs=correlated_pairs,
        n_original=n_original,
        n_after_correlation=n_after_correlation,
        n_selected=len(selected),
        fold_seasons=fold_seasons,
    )
