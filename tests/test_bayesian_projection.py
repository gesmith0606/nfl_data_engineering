"""Tests for Bayesian hierarchical residual projection model."""

import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bayesian_projection import (
    BAYESIAN_MODEL_DIR,
    BAYESIAN_PARAMS,
    CEILING_QUANTILE,
    FLOOR_QUANTILE,
    N_POSTERIOR_SAMPLES,
    BayesianResidualModel,
    apply_bayesian_correction,
    load_bayesian_model,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_train_data():
    """Generate simple training data for residual model testing."""
    rng = np.random.RandomState(42)
    n = 200

    X = rng.randn(n, 10)
    # True residual is linear in first 3 features + noise
    y = 2.0 * X[:, 0] - 1.5 * X[:, 1] + 0.5 * X[:, 2] + rng.randn(n) * 2.0

    feature_names = [f"feat_{i}" for i in range(10)]
    return X, y, feature_names


@pytest.fixture
def sample_pos_data():
    """Generate sample position data mimicking player-week features."""
    rng = np.random.RandomState(42)
    n_per_season = 100
    seasons = [2020, 2021, 2022, 2023, 2024]
    records = []

    for season in seasons:
        for i in range(n_per_season):
            week = rng.randint(3, 19)
            records.append(
                {
                    "player_id": f"player_{i % 20}",
                    "season": season,
                    "week": week,
                    "position": "WR",
                    "rushing_yards": rng.uniform(0, 20),
                    "rushing_tds": rng.choice([0, 0, 0, 1]),
                    "receptions": rng.uniform(0, 10),
                    "receiving_yards": rng.uniform(0, 120),
                    "receiving_tds": rng.choice([0, 0, 0, 1]),
                    "targets": rng.uniform(0, 15),
                    "carries": rng.uniform(0, 5),
                    "feat_a": rng.randn(),
                    "feat_b": rng.randn(),
                    "feat_c": rng.randn(),
                    "feat_d": rng.randn(),
                    "feat_e": rng.randn(),
                }
            )

    return pd.DataFrame(records)


@pytest.fixture
def projections_df():
    """Generate sample projections DataFrame for correction testing."""
    return pd.DataFrame(
        {
            "player_name": ["P1", "P2", "P3", "P4"],
            "position": ["WR", "WR", "RB", "TE"],
            "projected_points": [15.0, 10.0, 12.0, 8.0],
            "feat_0": [0.5, -0.3, 1.0, 0.2],
            "feat_1": [0.1, 0.8, -0.5, 0.3],
            "feat_2": [-0.2, 0.4, 0.7, -0.1],
        }
    )


# ---------------------------------------------------------------------------
# BayesianResidualModel tests
# ---------------------------------------------------------------------------


class TestBayesianResidualModel:
    """Tests for BayesianResidualModel class."""

    def test_init_default_params(self):
        """Model initializes with position-specific defaults."""
        model = BayesianResidualModel("WR")
        assert model.position == "WR"
        assert not model.is_fitted
        assert model.feature_names == []

    def test_init_custom_params(self):
        """Model accepts custom BayesianRidge params."""
        params = {"max_iter": 100, "tol": 1e-3, "compute_score": False}
        model = BayesianResidualModel("QB", params=params)
        br = model.pipeline.named_steps["model"]
        assert br.max_iter == 100
        assert br.tol == 1e-3

    def test_init_position_normalization(self):
        """Position is uppercased."""
        model = BayesianResidualModel("wr")
        assert model.position == "WR"

    def test_fit_basic(self, simple_train_data):
        """Model fits without errors."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)
        assert model.is_fitted

    def test_fit_sets_feature_names(self, simple_train_data):
        """Feature names set during fit override constructor."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR")
        model.fit(X, y, feature_names=feat_names)
        assert model.feature_names == feat_names

    def test_predict_basic(self, simple_train_data):
        """Predict returns correct shape."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)
        preds = model.predict(X)
        assert preds.shape == (len(X),)

    def test_predict_not_fitted_raises(self):
        """Predict before fit raises RuntimeError."""
        model = BayesianResidualModel("WR")
        with pytest.raises(RuntimeError, match="not fitted"):
            model.predict(np.zeros((5, 3)))

    def test_predict_reasonable_values(self, simple_train_data):
        """Predictions are reasonable (correlated with true values)."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)
        preds = model.predict(X)

        # Predictions should be correlated with actual
        corr = np.corrcoef(y, preds)[0, 1]
        assert corr > 0.5, f"Low correlation: {corr}"

    def test_predict_with_uncertainty_shape(self, simple_train_data):
        """Uncertainty prediction returns correct shapes."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)

        result = model.predict_with_uncertainty(X, n_samples=100)

        assert "mean" in result
        assert "std" in result
        assert "floor" in result
        assert "ceiling" in result
        assert "samples" in result

        assert result["mean"].shape == (len(X),)
        assert result["std"].shape == (len(X),)
        assert result["floor"].shape == (len(X),)
        assert result["ceiling"].shape == (len(X),)
        assert result["samples"].shape == (len(X), 100)

    def test_predict_with_uncertainty_ordering(self, simple_train_data):
        """Floor < mean < ceiling for most predictions."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)

        result = model.predict_with_uncertainty(X)

        # Most predictions should have floor < mean < ceiling
        valid = (result["floor"] <= result["mean"]) & (
            result["mean"] <= result["ceiling"]
        )
        pct_valid = np.mean(valid)
        assert pct_valid > 0.90, f"Only {pct_valid:.1%} satisfy floor<mean<ceiling"

    def test_predict_with_uncertainty_std_positive(self, simple_train_data):
        """Standard deviation is always positive."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)

        result = model.predict_with_uncertainty(X)
        assert np.all(result["std"] > 0)

    def test_predict_with_uncertainty_not_fitted_raises(self):
        """Uncertainty prediction before fit raises RuntimeError."""
        model = BayesianResidualModel("WR")
        with pytest.raises(RuntimeError, match="not fitted"):
            model.predict_with_uncertainty(np.zeros((5, 3)))

    def test_predict_with_custom_quantiles(self, simple_train_data):
        """Custom quantiles produce different interval widths."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)

        narrow = model.predict_with_uncertainty(
            X, floor_quantile=0.25, ceiling_quantile=0.75
        )
        wide = model.predict_with_uncertainty(
            X, floor_quantile=0.05, ceiling_quantile=0.95
        )

        narrow_width = np.mean(narrow["ceiling"] - narrow["floor"])
        wide_width = np.mean(wide["ceiling"] - wide["floor"])

        assert wide_width > narrow_width

    def test_get_learned_priors_after_fit(self, simple_train_data):
        """Learned priors available after fitting."""
        X, y, feat_names = simple_train_data
        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)

        priors = model.get_learned_priors()
        assert "alpha" in priors
        assert "lambda" in priors
        assert "sigma" in priors
        assert "n_iter" in priors
        assert priors["alpha"] > 0
        assert priors["lambda"] > 0
        assert priors["sigma"] > 0

    def test_get_learned_priors_not_fitted(self):
        """Learned priors returns empty dict when not fitted."""
        model = BayesianResidualModel("WR")
        assert model.get_learned_priors() == {}

    def test_handles_nan_features(self):
        """Model handles NaN in features via imputation."""
        rng = np.random.RandomState(42)
        X = rng.randn(100, 5)
        y = rng.randn(100)

        # Inject NaN
        X[10, 2] = np.nan
        X[20, 0] = np.nan
        X[30, 4] = np.nan

        model = BayesianResidualModel("WR")
        model.fit(X, y)
        preds = model.predict(X)
        assert preds.shape == (100,)
        assert not np.any(np.isnan(preds))

    def test_pipeline_components(self):
        """Pipeline has imputer, scaler, and BayesianRidge."""
        model = BayesianResidualModel("WR")
        steps = [name for name, _ in model.pipeline.steps]
        assert "imputer" in steps
        assert "scaler" in steps
        assert "model" in steps


# ---------------------------------------------------------------------------
# Save / Load tests
# ---------------------------------------------------------------------------


class TestBayesianPersistence:
    """Tests for model save/load functionality."""

    def test_save_and_load(self, simple_train_data):
        """Model can be saved and loaded with correct predictions."""
        X, y, feat_names = simple_train_data

        model = BayesianResidualModel("WR", feature_names=feat_names)
        model.fit(X, y)
        original_preds = model.predict(X[:5])

        with tempfile.TemporaryDirectory() as tmpdir:
            import joblib

            path = os.path.join(tmpdir, "bayesian_wr.joblib")
            joblib.dump(model, path)

            loaded = load_bayesian_model("WR", tmpdir)
            assert loaded is not None
            assert loaded.is_fitted
            assert loaded.position == "WR"

            loaded_preds = loaded.predict(X[:5])
            np.testing.assert_array_almost_equal(original_preds, loaded_preds)

    def test_load_missing_model(self):
        """Loading a non-existent model returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_bayesian_model("QB", tmpdir)
            assert result is None


# ---------------------------------------------------------------------------
# Apply correction tests
# ---------------------------------------------------------------------------


class TestApplyBayesianCorrection:
    """Tests for apply_bayesian_correction function."""

    def test_no_models_available(self, projections_df):
        """Without saved models, projections pass through unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = apply_bayesian_correction(projections_df, model_dir=tmpdir)
            pd.testing.assert_frame_equal(
                result[["projected_points"]],
                projections_df[["projected_points"]],
            )

    def test_correction_with_model(self, simple_train_data, projections_df):
        """Correction modifies projected_points when model exists."""
        X, y, feat_names = simple_train_data

        model = BayesianResidualModel("WR", feature_names=["feat_0", "feat_1", "feat_2"])
        # Train on simple data
        X_small = np.random.randn(50, 3)
        y_small = np.random.randn(50)
        model.fit(X_small, y_small)

        with tempfile.TemporaryDirectory() as tmpdir:
            import joblib

            joblib.dump(model, os.path.join(tmpdir, "bayesian_wr.joblib"))

            result = apply_bayesian_correction(
                projections_df,
                positions=["WR"],
                model_dir=tmpdir,
                include_intervals=True,
            )

            # WR projections should be modified
            wr_mask = projections_df["position"] == "WR"
            # Points will be different after correction
            assert not np.allclose(
                result.loc[wr_mask, "projected_points"].values,
                projections_df.loc[wr_mask, "projected_points"].values,
            )

            # Interval columns should exist for corrected positions
            assert "bayesian_floor" in result.columns
            assert "bayesian_ceiling" in result.columns
            assert "bayesian_std" in result.columns

    def test_non_negative_projections(self, simple_train_data, projections_df):
        """Projected points are clipped to >= 0."""
        model = BayesianResidualModel("WR", feature_names=["feat_0", "feat_1", "feat_2"])
        X_small = np.random.randn(50, 3)
        # Large negative residuals to force negative projections
        y_small = np.full(50, -100.0)
        model.fit(X_small, y_small)

        with tempfile.TemporaryDirectory() as tmpdir:
            import joblib

            joblib.dump(model, os.path.join(tmpdir, "bayesian_wr.joblib"))

            result = apply_bayesian_correction(
                projections_df,
                positions=["WR"],
                model_dir=tmpdir,
                include_intervals=False,
            )

            assert (result["projected_points"] >= 0).all()


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestBayesianConfig:
    """Tests for Bayesian model configuration."""

    def test_all_positions_have_params(self):
        """All standard positions have parameter configs."""
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in BAYESIAN_PARAMS

    def test_quantile_defaults(self):
        """Default quantiles are sensible."""
        assert 0 < FLOOR_QUANTILE < 0.5
        assert 0.5 < CEILING_QUANTILE < 1.0
        assert FLOOR_QUANTILE + CEILING_QUANTILE == pytest.approx(1.0)

    def test_n_posterior_samples(self):
        """Posterior sample count is reasonable."""
        assert N_POSTERIOR_SAMPLES >= 100
        assert N_POSTERIOR_SAMPLES <= 10000


# ---------------------------------------------------------------------------
# Calibration tests
# ---------------------------------------------------------------------------


class TestCalibration:
    """Tests for posterior predictive calibration."""

    def test_interval_coverage_well_specified(self):
        """On well-specified data, 80% interval covers ~80% of actuals."""
        rng = np.random.RandomState(42)
        n_train = 500
        n_test = 200

        # Generate data from a known linear model
        X_train = rng.randn(n_train, 5)
        noise_train = rng.randn(n_train) * 2.0
        y_train = X_train @ np.array([1.0, -0.5, 0.3, 0.0, 0.0]) + noise_train

        X_test = rng.randn(n_test, 5)
        noise_test = rng.randn(n_test) * 2.0
        y_test = X_test @ np.array([1.0, -0.5, 0.3, 0.0, 0.0]) + noise_test

        model = BayesianResidualModel("WR")
        model.fit(X_train, y_train)

        preds = model.predict_with_uncertainty(X_test)
        in_interval = (y_test >= preds["floor"]) & (y_test <= preds["ceiling"])
        coverage = np.mean(in_interval)

        # 80% interval should cover roughly 60-95% (with finite sample noise)
        assert 0.55 <= coverage <= 0.98, f"Coverage {coverage:.1%} out of range"

    def test_wider_interval_more_coverage(self):
        """Wider intervals (5-95%) cover more than narrow (25-75%)."""
        rng = np.random.RandomState(42)
        X_train = rng.randn(300, 5)
        y_train = X_train[:, 0] + rng.randn(300) * 3.0

        X_test = rng.randn(100, 5)
        y_test = X_test[:, 0] + rng.randn(100) * 3.0

        model = BayesianResidualModel("WR")
        model.fit(X_train, y_train)

        narrow = model.predict_with_uncertainty(
            X_test, floor_quantile=0.25, ceiling_quantile=0.75
        )
        wide = model.predict_with_uncertainty(
            X_test, floor_quantile=0.05, ceiling_quantile=0.95
        )

        narrow_coverage = np.mean(
            (y_test >= narrow["floor"]) & (y_test <= narrow["ceiling"])
        )
        wide_coverage = np.mean(
            (y_test >= wide["floor"]) & (y_test <= wide["ceiling"])
        )

        assert wide_coverage >= narrow_coverage
