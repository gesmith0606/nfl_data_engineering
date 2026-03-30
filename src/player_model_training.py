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

from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from config import CONSERVATIVE_PARAMS, HOLDOUT_SEASON
from model_training import WalkForwardResult
from projection_engine import POSITION_STAT_PROFILE


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


# ---------------------------------------------------------------------------
# Functions (stubs — Task 1 RED phase)
# ---------------------------------------------------------------------------


def get_stat_type(stat: str) -> str:
    """Map a stat name to its STAT_TYPE_GROUPS key."""
    raise NotImplementedError


def get_player_model_params(stat: str) -> dict:
    """Return hyperparameters for a stat's type group."""
    raise NotImplementedError


def player_walk_forward_cv(
    pos_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    model_factory: Callable[[], Any],
    fit_kwargs_fn: Optional[Callable] = None,
    val_seasons: Optional[List[int]] = None,
) -> Tuple[WalkForwardResult, pd.DataFrame]:
    """Walk-forward CV keyed on row index (NOT game_id).

    Uses PLAYER_VALIDATION_SEASONS, with holdout guard.
    """
    raise NotImplementedError


def run_player_feature_selection(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    positions: List[str],
) -> Dict[str, List[str]]:
    """SHAP selection per stat-type group.

    Returns {group_name: selected_features}.
    """
    raise NotImplementedError


def train_position_models(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols_by_group: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Train all stat models for one position."""
    raise NotImplementedError


def save_player_model(
    model: Any,
    position: str,
    stat: str,
    metadata: dict,
    output_dir: str = "models/player",
) -> None:
    """Save model JSON + metadata sidecar."""
    raise NotImplementedError


def load_player_model(
    position: str,
    stat: str,
    model_dir: str = "models/player",
) -> Any:
    """Load saved model."""
    raise NotImplementedError


def predict_player_stats(
    model_dict: Dict[str, Any],
    player_data: pd.DataFrame,
    position: str,
    feature_cols_by_group: Dict[str, List[str]],
) -> pd.DataFrame:
    """Predict all stats for a position.

    Returns DataFrame with pred_{stat} columns.
    """
    raise NotImplementedError
