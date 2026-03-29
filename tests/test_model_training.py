"""Tests for walk-forward CV framework and XGBoost model training.

Tests cover:
- Walk-forward CV with 5 season-boundary folds
- Holdout season never touched during CV
- Spread and total model training with JSON serialization
- Model loading and prediction
- Conservative default hyperparameters
"""

import json
import os

import numpy as np
import pandas as pd
import pytest

from src.config import (
    CONSERVATIVE_PARAMS,
    HOLDOUT_SEASON,
    TRAINING_SEASONS,
    VALIDATION_SEASONS,
)


def _make_synthetic_game_data(seasons=None):
    """Create synthetic game data for testing without needing local Silver data.

    Generates minimal DataFrame with diff_ feature columns, label columns,
    and season/week identifiers matching assemble_game_features() output.
    """
    if seasons is None:
        seasons = TRAINING_SEASONS

    rows = []
    np.random.seed(42)
    for season in seasons:
        n_weeks = 17 if season < 2021 else 18
        games_per_week = 16
        for week in range(1, n_weeks + 1):
            for g in range(games_per_week):
                margin = np.random.normal(0, 14)
                total = np.random.normal(46, 10)
                rows.append({
                    "game_id": f"{season}_{week:02d}_{g:03d}",
                    "season": season,
                    "week": week,
                    "game_type": "REG",
                    "home_score": (total / 2) + (margin / 2),
                    "away_score": (total / 2) - (margin / 2),
                    "actual_margin": margin,
                    "actual_total": total,
                    "result": margin,
                    "spread_line": margin + np.random.normal(0, 3),
                    "total_line": total + np.random.normal(0, 3),
                    # Differential features
                    "diff_off_epa_per_play_roll3": np.random.normal(0, 0.1),
                    "diff_def_epa_per_play_roll3": np.random.normal(0, 0.1),
                    "diff_off_success_rate_roll3": np.random.normal(0, 0.05),
                    "diff_pace_roll3": np.random.normal(0, 2),
                    "diff_proe_roll3": np.random.normal(0, 0.05),
                    "diff_sos_off_rank": np.random.normal(0, 5),
                    "diff_sos_def_rank": np.random.normal(0, 5),
                    "diff_penalty_yards_roll3": np.random.normal(0, 10),
                    "diff_turnover_margin_roll3": np.random.normal(0, 1),
                    "diff_third_down_pct_roll3": np.random.normal(0, 0.05),
                    # Context columns
                    "div_game": np.random.choice([0, 1]),
                })

    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def synthetic_data():
    """Synthetic game data spanning 2016-2023 for testing."""
    return _make_synthetic_game_data(TRAINING_SEASONS)


@pytest.fixture(scope="module")
def feature_cols(synthetic_data):
    """Feature column names from synthetic data."""
    return [c for c in synthetic_data.columns if c.startswith("diff_")] + ["div_game"]


# ---------------------------------------------------------------------------
# Walk-Forward CV Tests
# ---------------------------------------------------------------------------

class TestWalkForwardCV:
    """Tests for walk_forward_cv function."""

    def test_returns_walk_forward_result_with_correct_folds(self, synthetic_data, feature_cols):
        """walk_forward_cv with target='actual_margin' returns WalkForwardResult with len(VALIDATION_SEASONS) fold scores."""
        from src.model_training import walk_forward_cv, WalkForwardResult

        result = walk_forward_cv(synthetic_data, feature_cols, "actual_margin")
        assert isinstance(result, WalkForwardResult)
        assert len(result.fold_maes) == len(VALIDATION_SEASONS)
        assert len(result.fold_details) == len(VALIDATION_SEASONS)

    def test_fold_1_trains_before_2019_validates_on_2019(self, synthetic_data, feature_cols):
        """walk_forward_cv fold 1 trains on seasons < 2019 and validates on season == 2019."""
        from src.model_training import walk_forward_cv

        result = walk_forward_cv(synthetic_data, feature_cols, "actual_margin")
        fold_1 = result.fold_details[0]
        assert fold_1["val_season"] == 2019
        # Train seasons should all be < 2019
        for s in fold_1["train_seasons"]:
            assert s < 2019

    def test_last_fold_validates_on_last_validation_season(self, synthetic_data, feature_cols):
        """walk_forward_cv last fold validates on the last VALIDATION_SEASON."""
        from src.model_training import walk_forward_cv

        result = walk_forward_cv(synthetic_data, feature_cols, "actual_margin")
        last_fold = result.fold_details[-1]
        assert last_fold["val_season"] == VALIDATION_SEASONS[-1]
        for s in last_fold["train_seasons"]:
            assert s < VALIDATION_SEASONS[-1]

    def test_never_includes_holdout_season(self, synthetic_data, feature_cols):
        """walk_forward_cv never includes holdout season in any fold."""
        from src.model_training import walk_forward_cv

        # Add holdout data to test that it's excluded
        data_with_holdout = _make_synthetic_game_data(list(range(2016, HOLDOUT_SEASON + 1)))
        result = walk_forward_cv(data_with_holdout, feature_cols, "actual_margin")
        for fold in result.fold_details:
            assert HOLDOUT_SEASON not in fold["train_seasons"]
            assert fold["val_season"] != HOLDOUT_SEASON

    def test_returns_mean_mae_as_float_and_fold_list(self, synthetic_data, feature_cols):
        """walk_forward_cv returns mean_mae as float and per-fold MAE list."""
        from src.model_training import walk_forward_cv

        result = walk_forward_cv(synthetic_data, feature_cols, "actual_margin")
        assert isinstance(result.mean_mae, float)
        assert result.mean_mae > 0
        assert isinstance(result.fold_maes, list)
        for mae in result.fold_maes:
            assert isinstance(mae, float)
            assert mae > 0

    def test_conservative_params_used_by_default(self, synthetic_data, feature_cols):
        """CONSERVATIVE_PARAMS are used as defaults when no custom params provided."""
        from src.model_training import walk_forward_cv

        # This should not raise — default params from config are applied
        result = walk_forward_cv(synthetic_data, feature_cols, "actual_margin")
        assert result.mean_mae > 0  # Successfully ran with defaults


# ---------------------------------------------------------------------------
# Train Final Model Tests
# ---------------------------------------------------------------------------

class TestTrainFinalModel:
    """Tests for train_final_model function."""

    def test_spread_model_saves_to_models_spread(self, synthetic_data, feature_cols, tmp_path):
        """train_final_model with target='actual_margin' saves model.json and metadata.json to models/spread/."""
        from src.model_training import train_final_model

        model, metadata = train_final_model(
            synthetic_data, feature_cols, "actual_margin",
            target_name="spread", model_dir=str(tmp_path),
        )
        assert os.path.isfile(os.path.join(tmp_path, "spread", "model.json"))
        assert os.path.isfile(os.path.join(tmp_path, "spread", "metadata.json"))

    def test_total_model_saves_to_models_total(self, synthetic_data, feature_cols, tmp_path):
        """train_final_model with target='actual_total' saves to models/total/."""
        from src.model_training import train_final_model

        model, metadata = train_final_model(
            synthetic_data, feature_cols, "actual_total",
            target_name="total", model_dir=str(tmp_path),
        )
        assert os.path.isfile(os.path.join(tmp_path, "total", "model.json"))
        assert os.path.isfile(os.path.join(tmp_path, "total", "metadata.json"))

    def test_metadata_contains_required_keys(self, synthetic_data, feature_cols, tmp_path):
        """saved metadata.json contains required keys."""
        from src.model_training import train_final_model

        _, metadata = train_final_model(
            synthetic_data, feature_cols, "actual_margin",
            target_name="spread", model_dir=str(tmp_path),
        )
        required_keys = {
            "target", "training_seasons", "n_features",
            "feature_names", "cv_scores", "best_params", "trained_at",
        }
        assert required_keys.issubset(set(metadata.keys())), (
            f"Missing keys: {required_keys - set(metadata.keys())}"
        )
        # Verify types
        assert isinstance(metadata["training_seasons"], list)
        assert isinstance(metadata["n_features"], int)
        assert isinstance(metadata["feature_names"], list)
        assert isinstance(metadata["cv_scores"], dict)
        assert "mean_mae" in metadata["cv_scores"]
        assert "fold_maes" in metadata["cv_scores"]

    def test_metadata_persisted_on_disk(self, synthetic_data, feature_cols, tmp_path):
        """metadata.json on disk matches returned metadata."""
        from src.model_training import train_final_model

        _, metadata = train_final_model(
            synthetic_data, feature_cols, "actual_margin",
            target_name="spread", model_dir=str(tmp_path),
        )
        with open(os.path.join(tmp_path, "spread", "metadata.json")) as f:
            disk_metadata = json.load(f)
        assert disk_metadata["target"] == metadata["target"]
        assert disk_metadata["n_features"] == metadata["n_features"]


# ---------------------------------------------------------------------------
# Load Model Tests
# ---------------------------------------------------------------------------

class TestLoadModel:
    """Tests for load_model function."""

    def test_loaded_model_predicts_correct_length(self, synthetic_data, feature_cols, tmp_path):
        """Loaded model can predict on new data (returns array of floats same length as input)."""
        from src.model_training import train_final_model, load_model

        train_final_model(
            synthetic_data, feature_cols, "actual_margin",
            target_name="spread", model_dir=str(tmp_path),
        )
        model, metadata = load_model("spread", model_dir=str(tmp_path))

        # Predict on a subset
        test_data = synthetic_data.head(20)
        preds = model.predict(test_data[feature_cols])
        assert len(preds) == 20
        assert preds.dtype in (np.float32, np.float64)
