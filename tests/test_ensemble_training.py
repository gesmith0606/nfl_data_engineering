"""Tests for ensemble training: model factories, walk-forward CV with OOF,
Ridge meta-learner, full ensemble pipeline, save/load, and prediction.

Tests cover:
- LightGBM and CatBoost model factories (ENS-01, ENS-02)
- Generalized walk-forward CV producing OOF predictions (ENS-03)
- Temporal correctness: OOF for season S only from model trained on S-1
- Holdout season guard
- Ridge meta-learner on 3-column OOF matrix (ENS-04)
- Full train_ensemble pipeline with artifact save
- load_ensemble and predict_ensemble round-trip
- metadata.json structure
"""

import json
import os
import pickle

import numpy as np
import pandas as pd
import pytest

from src.config import (
    CB_CONSERVATIVE_PARAMS,
    HOLDOUT_SEASON,
    LGB_CONSERVATIVE_PARAMS,
    VALIDATION_SEASONS,
)


def _make_synthetic_ensemble_data(seasons=None, n_games_per_week=8):
    """Create synthetic game data for ensemble tests.

    Smaller than model_training fixture for speed -- fewer games per week.
    """
    if seasons is None:
        seasons = list(range(2018, 2024))

    rows = []
    np.random.seed(42)
    for season in seasons:
        n_weeks = 17 if season < 2021 else 18
        for week in range(1, n_weeks + 1):
            for g in range(n_games_per_week):
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
                    "diff_off_epa_roll3": np.random.normal(0, 0.1),
                    "diff_def_epa_roll3": np.random.normal(0, 0.1),
                    "diff_success_rate_roll3": np.random.normal(0, 0.05),
                    "diff_pace_roll3": np.random.normal(0, 2),
                    "diff_proe_roll3": np.random.normal(0, 0.05),
                    "diff_sos_off_rank": np.random.normal(0, 5),
                    "diff_sos_def_rank": np.random.normal(0, 5),
                    "diff_penalty_yards_roll3": np.random.normal(0, 10),
                    "diff_turnover_margin_roll3": np.random.normal(0, 1),
                    "diff_third_down_pct_roll3": np.random.normal(0, 0.05),
                    "div_game": np.random.choice([0, 1]),
                })

    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def synthetic_data():
    """Synthetic game data spanning 2018-2023 for ensemble tests."""
    return _make_synthetic_ensemble_data(list(range(2018, 2024)))


@pytest.fixture(scope="module")
def feature_cols(synthetic_data):
    """Feature column names from synthetic data."""
    return [c for c in synthetic_data.columns if c.startswith("diff_")] + ["div_game"]


# ---------------------------------------------------------------------------
# Model Factory Tests
# ---------------------------------------------------------------------------

class TestModelFactories:
    """Tests for make_xgb_model, make_lgb_model, make_cb_model."""

    def test_lgb_factory_creates_model_with_fit_predict(self):
        """LGBMRegressor factory creates model that accepts .fit()/.predict()."""
        from src.ensemble_training import make_lgb_model

        model = make_lgb_model(LGB_CONSERVATIVE_PARAMS)
        assert hasattr(model, "fit")
        assert hasattr(model, "predict")

    def test_cb_factory_creates_model_with_fit_predict(self):
        """CatBoostRegressor factory creates model that accepts .fit()/.predict()."""
        from src.ensemble_training import make_cb_model

        model = make_cb_model(CB_CONSERVATIVE_PARAMS)
        assert hasattr(model, "fit")
        assert hasattr(model, "predict")

    def test_xgb_factory_creates_model_with_fit_predict(self):
        """XGBRegressor factory creates model that accepts .fit()/.predict()."""
        from src.ensemble_training import make_xgb_model
        from src.config import CONSERVATIVE_PARAMS

        model = make_xgb_model(CONSERVATIVE_PARAMS)
        assert hasattr(model, "fit")
        assert hasattr(model, "predict")


# ---------------------------------------------------------------------------
# Walk-Forward CV with OOF Tests
# ---------------------------------------------------------------------------

class TestWalkForwardCVWithOOF:
    """Tests for walk_forward_cv_with_oof function."""

    def test_returns_walk_forward_result_and_oof_df(self, synthetic_data, feature_cols):
        """walk_forward_cv_with_oof returns (WalkForwardResult, oof_df)."""
        from src.ensemble_training import make_xgb_model, walk_forward_cv_with_oof
        from src.config import CONSERVATIVE_PARAMS

        factory = lambda: make_xgb_model(CONSERVATIVE_PARAMS)
        def fit_kwargs(X_train, y_train, X_val, y_val):
            return {"eval_set": [(X_val, y_val)], "verbose": False}

        result, oof_df = walk_forward_cv_with_oof(
            synthetic_data, feature_cols, "actual_margin",
            model_factory=factory,
            fit_kwargs_fn=fit_kwargs,
            val_seasons=[2021, 2022, 2023],
        )
        # Check duck-type: WalkForwardResult fields
        assert hasattr(result, "mean_mae")
        assert hasattr(result, "fold_maes")
        assert hasattr(result, "fold_details")
        assert isinstance(result.mean_mae, float)
        assert isinstance(oof_df, pd.DataFrame)
        assert "game_id" in oof_df.columns
        assert "season" in oof_df.columns
        assert "oof_prediction" in oof_df.columns

    def test_oof_temporal_correctness(self, synthetic_data, feature_cols):
        """OOF predictions for season S come only from model trained on seasons < S."""
        from src.ensemble_training import make_xgb_model, walk_forward_cv_with_oof
        from src.config import CONSERVATIVE_PARAMS

        factory = lambda: make_xgb_model(CONSERVATIVE_PARAMS)
        def fit_kwargs(X_train, y_train, X_val, y_val):
            return {"eval_set": [(X_val, y_val)], "verbose": False}

        result, oof_df = walk_forward_cv_with_oof(
            synthetic_data, feature_cols, "actual_margin",
            model_factory=factory,
            fit_kwargs_fn=fit_kwargs,
            val_seasons=[2021, 2022, 2023],
        )
        # Each OOF season should be one of the val_seasons
        oof_seasons = set(oof_df["season"].unique())
        assert oof_seasons == {2021, 2022, 2023}
        # Fold details should show training seasons < val season
        for fold in result.fold_details:
            for ts in fold["train_seasons"]:
                assert ts < fold["val_season"]

    def test_holdout_guard_raises_value_error(self, synthetic_data, feature_cols):
        """walk_forward_cv_with_oof raises ValueError if val_season == HOLDOUT_SEASON."""
        from src.ensemble_training import make_xgb_model, walk_forward_cv_with_oof
        from src.config import CONSERVATIVE_PARAMS

        factory = lambda: make_xgb_model(CONSERVATIVE_PARAMS)
        def fit_kwargs(X_train, y_train, X_val, y_val):
            return {"eval_set": [(X_val, y_val)], "verbose": False}

        with pytest.raises(ValueError, match="HOLDOUT_SEASON"):
            walk_forward_cv_with_oof(
                synthetic_data, feature_cols, "actual_margin",
                model_factory=factory,
                fit_kwargs_fn=fit_kwargs,
                val_seasons=[2023, HOLDOUT_SEASON],
            )


# ---------------------------------------------------------------------------
# Ridge Meta-Learner Tests
# ---------------------------------------------------------------------------

class TestRidgeMeta:
    """Tests for train_ridge_meta function."""

    def test_ridge_trains_on_3_column_oof_matrix(self):
        """Ridge meta-learner trains on 3-column OOF matrix and produces predictions."""
        from src.ensemble_training import train_ridge_meta

        np.random.seed(42)
        n = 100
        oof_matrix = pd.DataFrame({
            "game_id": [f"g_{i}" for i in range(n)],
            "season": [2020 + (i % 3) for i in range(n)],
            "xgb_pred": np.random.normal(0, 10, n),
            "lgb_pred": np.random.normal(0, 10, n),
            "cb_pred": np.random.normal(0, 10, n),
            "actual": np.random.normal(0, 14, n),
        })
        ridge = train_ridge_meta(oof_matrix)
        assert hasattr(ridge, "predict")
        assert hasattr(ridge, "alpha_")
        assert ridge.coef_.shape == (3,)

    def test_ridge_predictions_have_correct_shape(self):
        """Ridge predict output has same length as input."""
        from src.ensemble_training import train_ridge_meta

        np.random.seed(42)
        n = 50
        oof_matrix = pd.DataFrame({
            "game_id": [f"g_{i}" for i in range(n)],
            "season": [2020] * n,
            "xgb_pred": np.random.normal(0, 10, n),
            "lgb_pred": np.random.normal(0, 10, n),
            "cb_pred": np.random.normal(0, 10, n),
            "actual": np.random.normal(0, 14, n),
        })
        ridge = train_ridge_meta(oof_matrix)
        preds = ridge.predict(oof_matrix[["xgb_pred", "lgb_pred", "cb_pred"]])
        assert len(preds) == n


# ---------------------------------------------------------------------------
# Full Train Ensemble Tests
# ---------------------------------------------------------------------------

class TestTrainEnsemble:
    """Tests for train_ensemble integration."""

    def test_train_ensemble_saves_all_artifacts(self, synthetic_data, feature_cols, tmp_path):
        """train_ensemble produces all expected files in ensemble dir."""
        from src.ensemble_training import train_ensemble

        ensemble_dir = str(tmp_path / "ensemble")
        metadata = train_ensemble(
            synthetic_data, feature_cols,
            ensemble_dir=ensemble_dir,
        )

        # Check spread artifacts
        assert os.path.isfile(os.path.join(ensemble_dir, "xgb_spread.json"))
        assert os.path.isfile(os.path.join(ensemble_dir, "lgb_spread.txt"))
        assert os.path.isfile(os.path.join(ensemble_dir, "cb_spread.cbm"))
        assert os.path.isfile(os.path.join(ensemble_dir, "ridge_spread.pkl"))

        # Check total artifacts
        assert os.path.isfile(os.path.join(ensemble_dir, "xgb_total.json"))
        assert os.path.isfile(os.path.join(ensemble_dir, "lgb_total.txt"))
        assert os.path.isfile(os.path.join(ensemble_dir, "cb_total.cbm"))
        assert os.path.isfile(os.path.join(ensemble_dir, "ridge_total.pkl"))

        # Check metadata
        assert os.path.isfile(os.path.join(ensemble_dir, "metadata.json"))

    def test_metadata_json_structure(self, synthetic_data, feature_cols, tmp_path):
        """metadata.json contains required keys per D-11."""
        from src.ensemble_training import train_ensemble

        ensemble_dir = str(tmp_path / "ensemble_meta")
        metadata = train_ensemble(
            synthetic_data, feature_cols,
            ensemble_dir=ensemble_dir,
        )

        with open(os.path.join(ensemble_dir, "metadata.json")) as f:
            disk_meta = json.load(f)

        assert "ensemble_version" in disk_meta
        assert "trained_at" in disk_meta
        assert "training_seasons" in disk_meta
        assert "holdout_season" in disk_meta
        assert "selected_features" in disk_meta
        assert "n_features" in disk_meta

        # Per-target entries
        assert "spread" in disk_meta
        assert "total" in disk_meta
        for target_key in ["spread", "total"]:
            t = disk_meta[target_key]
            assert "xgb_cv_mae" in t
            assert "lgb_cv_mae" in t
            assert "cb_cv_mae" in t
            assert "ridge_alpha" in t
            assert "ridge_coefficients" in t


# ---------------------------------------------------------------------------
# Load Ensemble Tests
# ---------------------------------------------------------------------------

class TestLoadEnsemble:
    """Tests for load_ensemble function."""

    def test_load_returns_models_and_metadata(self, synthetic_data, feature_cols, tmp_path):
        """load_ensemble returns (spread_models, total_models, metadata)."""
        from src.ensemble_training import train_ensemble, load_ensemble

        ensemble_dir = str(tmp_path / "ensemble_load")
        train_ensemble(synthetic_data, feature_cols, ensemble_dir=ensemble_dir)

        spread_models, total_models, metadata = load_ensemble(ensemble_dir=ensemble_dir)

        assert "xgb" in spread_models
        assert "lgb" in spread_models
        assert "cb" in spread_models
        assert "ridge" in spread_models

        assert "xgb" in total_models
        assert "lgb" in total_models
        assert "cb" in total_models
        assert "ridge" in total_models

        assert isinstance(metadata, dict)


# ---------------------------------------------------------------------------
# Predict Ensemble Tests
# ---------------------------------------------------------------------------

class TestPredictEnsemble:
    """Tests for predict_ensemble function."""

    def test_predict_returns_numpy_array(self, synthetic_data, feature_cols, tmp_path):
        """predict_ensemble takes game features + loaded models and returns numpy array."""
        from src.ensemble_training import train_ensemble, load_ensemble, predict_ensemble

        ensemble_dir = str(tmp_path / "ensemble_predict")
        train_ensemble(synthetic_data, feature_cols, ensemble_dir=ensemble_dir)
        spread_models, total_models, metadata = load_ensemble(ensemble_dir=ensemble_dir)

        test_features = synthetic_data.head(10)[feature_cols]
        preds = predict_ensemble(test_features, spread_models)

        assert isinstance(preds, np.ndarray)
        assert len(preds) == 10
