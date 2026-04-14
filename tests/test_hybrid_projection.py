"""Tests for hybrid projection module (blend + residual approaches)."""

import json
import numpy as np
import pandas as pd
import pytest
import tempfile

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hybrid_projection import (
    apply_residual_correction,
    compute_actual_fantasy_points,
    compute_fantasy_points_from_preds,
    evaluate_blend,
    load_residual_model,
    train_residual_model,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_pred_df():
    """DataFrame with pred_{stat} columns for RB."""
    return pd.DataFrame(
        {
            "player_name": ["Player A", "Player B", "Player C"],
            "position": ["RB", "RB", "RB"],
            "rushing_yards": [80.0, 40.0, 100.0],
            "rushing_tds": [1.0, 0.0, 1.0],
            "receptions": [3.0, 1.0, 5.0],
            "receiving_yards": [25.0, 10.0, 50.0],
            "receiving_tds": [0.0, 0.0, 1.0],
            "carries": [15.0, 8.0, 20.0],
            "pred_rushing_yards": [75.0, 45.0, 90.0],
            "pred_rushing_tds": [0.8, 0.2, 1.1],
            "pred_receptions": [2.5, 1.5, 4.0],
            "pred_receiving_yards": [20.0, 12.0, 40.0],
            "pred_receiving_tds": [0.1, 0.0, 0.5],
            "pred_carries": [14.0, 9.0, 18.0],
        }
    )


@pytest.fixture
def sample_blend_data():
    """Aligned series for blend testing."""
    np.random.seed(42)
    n = 100
    actual = np.random.uniform(0, 30, n)
    heuristic = actual + np.random.normal(0, 5, n)  # noisy estimate
    ml = actual + np.random.normal(0, 3, n)  # better estimate
    return (
        pd.Series(heuristic, name="heuristic"),
        pd.Series(ml, name="ml"),
        pd.Series(actual, name="actual"),
    )


@pytest.fixture
def sample_pos_data_for_residual():
    """Position-filtered DataFrame for residual model testing."""
    np.random.seed(42)
    rows = []
    for season in [2020, 2021, 2022, 2023]:
        for week in range(1, 19):
            for player_id in range(10):
                base_yards = 50.0 + np.random.normal(0, 20)
                base_tds = max(0, 0.3 + np.random.normal(0, 0.3))
                base_rec = max(0, 3.0 + np.random.normal(0, 1.5))
                base_rec_yds = max(0, 20.0 + np.random.normal(0, 15))
                rows.append(
                    {
                        "player_id": f"player_{player_id}",
                        "player_name": f"Player {player_id}",
                        "position": "RB",
                        "season": season,
                        "week": week,
                        "rushing_yards": max(0, base_yards),
                        "rushing_tds": max(0, base_tds),
                        "receptions": max(0, base_rec),
                        "receiving_yards": max(0, base_rec_yds),
                        "receiving_tds": max(0, np.random.normal(0, 0.2)),
                        "carries": max(0, 10 + np.random.normal(0, 5)),
                        "rushing_yards_roll3": max(
                            0, base_yards + np.random.normal(0, 5)
                        ),
                        "rushing_yards_roll6": max(
                            0, base_yards + np.random.normal(0, 3)
                        ),
                        "rushing_yards_std": max(
                            0, base_yards + np.random.normal(0, 2)
                        ),
                        "rushing_tds_roll3": max(
                            0, base_tds + np.random.normal(0, 0.1)
                        ),
                        "rushing_tds_roll6": max(
                            0, base_tds + np.random.normal(0, 0.05)
                        ),
                        "rushing_tds_std": max(0, base_tds + np.random.normal(0, 0.03)),
                        "receptions_roll3": max(0, base_rec + np.random.normal(0, 0.5)),
                        "receptions_roll6": max(0, base_rec + np.random.normal(0, 0.3)),
                        "receptions_std": max(0, base_rec + np.random.normal(0, 0.2)),
                        "receiving_yards_roll3": max(
                            0, base_rec_yds + np.random.normal(0, 5)
                        ),
                        "receiving_yards_roll6": max(
                            0, base_rec_yds + np.random.normal(0, 3)
                        ),
                        "receiving_yards_std": max(
                            0, base_rec_yds + np.random.normal(0, 2)
                        ),
                        "receiving_tds_roll3": max(0, 0.1 + np.random.normal(0, 0.05)),
                        "receiving_tds_roll6": max(0, 0.1 + np.random.normal(0, 0.03)),
                        "receiving_tds_std": max(0, 0.1 + np.random.normal(0, 0.02)),
                        "carries_roll3": max(0, 10 + np.random.normal(0, 2)),
                        "carries_roll6": max(0, 10 + np.random.normal(0, 1)),
                        "carries_std": max(0, 10 + np.random.normal(0, 0.5)),
                        "snap_pct": 0.5 + np.random.normal(0, 0.15),
                        "carry_share": 0.3 + np.random.normal(0, 0.1),
                        "feature_1": np.random.normal(0, 1),
                        "feature_2": np.random.normal(0, 1),
                        "feature_3": np.random.normal(0, 1),
                    }
                )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: compute_fantasy_points_from_preds
# ---------------------------------------------------------------------------


class TestComputeFantasyPointsFromPreds:
    def test_returns_series(self, sample_pred_df):
        result = compute_fantasy_points_from_preds(sample_pred_df, "RB", "half_ppr")
        assert isinstance(result, pd.Series)
        assert len(result) == 3

    def test_positive_values(self, sample_pred_df):
        result = compute_fantasy_points_from_preds(sample_pred_df, "RB", "half_ppr")
        assert (result >= 0).all()

    def test_does_not_modify_input(self, sample_pred_df):
        original_cols = list(sample_pred_df.columns)
        compute_fantasy_points_from_preds(sample_pred_df, "RB", "half_ppr")
        assert list(sample_pred_df.columns) == original_cols

    def test_different_scoring_formats(self, sample_pred_df):
        ppr = compute_fantasy_points_from_preds(sample_pred_df, "RB", "ppr")
        half = compute_fantasy_points_from_preds(sample_pred_df, "RB", "half_ppr")
        std = compute_fantasy_points_from_preds(sample_pred_df, "RB", "standard")
        # PPR should be highest (more points per reception)
        assert ppr.sum() >= half.sum() >= std.sum()


# ---------------------------------------------------------------------------
# Tests: compute_actual_fantasy_points
# ---------------------------------------------------------------------------


class TestComputeActualFantasyPoints:
    def test_returns_series(self, sample_pred_df):
        result = compute_actual_fantasy_points(sample_pred_df, "half_ppr")
        assert isinstance(result, pd.Series)
        assert len(result) == 3

    def test_positive_values(self, sample_pred_df):
        result = compute_actual_fantasy_points(sample_pred_df, "half_ppr")
        assert (result >= 0).all()


# ---------------------------------------------------------------------------
# Tests: evaluate_blend
# ---------------------------------------------------------------------------


class TestEvaluateBlend:
    def test_returns_tuple(self, sample_blend_data):
        h, m, a = sample_blend_data
        best_alpha, best_mae, results = evaluate_blend(h, m, a)
        assert isinstance(best_alpha, float)
        assert isinstance(best_mae, float)
        assert isinstance(results, dict)

    def test_best_alpha_in_range(self, sample_blend_data):
        h, m, a = sample_blend_data
        best_alpha, _, _ = evaluate_blend(h, m, a)
        assert 0.0 <= best_alpha <= 1.0

    def test_best_mae_positive(self, sample_blend_data):
        h, m, a = sample_blend_data
        _, best_mae, _ = evaluate_blend(h, m, a)
        assert best_mae > 0.0

    def test_custom_alphas(self, sample_blend_data):
        h, m, a = sample_blend_data
        alphas = [0.0, 0.5, 1.0]
        _, _, results = evaluate_blend(h, m, a, alphas)
        assert set(results.keys()) == {0.0, 0.5, 1.0}

    def test_ml_dominant_when_better(self, sample_blend_data):
        """When ML is better, optimal alpha should be low (more ML weight)."""
        h, m, a = sample_blend_data
        best_alpha, _, _ = evaluate_blend(h, m, a)
        # ML has lower noise (3 vs 5), so alpha < 0.5 expected
        assert best_alpha < 0.5

    def test_blend_handles_nan(self):
        h = pd.Series([1.0, np.nan, 3.0])
        m = pd.Series([2.0, 2.0, np.nan])
        a = pd.Series([1.5, 1.5, 2.5])
        best_alpha, best_mae, results = evaluate_blend(h, m, a)
        # Should only use the one valid row (index 0)
        assert best_mae >= 0.0

    def test_perfect_ml_alpha_zero(self):
        """When ML is perfect, alpha=0 (or near it) should win."""
        a = pd.Series([10.0, 20.0, 30.0])
        m = pd.Series([10.0, 20.0, 30.0])  # perfect
        h = pd.Series([5.0, 25.0, 35.0])  # noisy
        alphas = [0.0, 0.1, 0.5, 1.0]
        best_alpha, best_mae, _ = evaluate_blend(h, m, a, alphas)
        assert best_alpha <= 0.1
        assert best_mae < 1.0


# ---------------------------------------------------------------------------
# Tests: train_residual_model
# ---------------------------------------------------------------------------


class TestTrainResidualModel:
    def test_returns_dict_and_dataframe(self, sample_pos_data_for_residual):
        feature_cols = [
            "feature_1",
            "feature_2",
            "feature_3",
            "rushing_yards_roll3",
            "rushing_yards_roll6",
            "snap_pct",
            "carry_share",
        ]
        result, oof_df = train_residual_model(
            sample_pos_data_for_residual,
            "RB",
            feature_cols,
            scoring_format="half_ppr",
            val_seasons=[2022, 2023],
        )
        assert "mean_mae" in result
        assert "fold_details" in result
        assert isinstance(oof_df, pd.DataFrame)

    def test_oof_has_required_columns(self, sample_pos_data_for_residual):
        feature_cols = ["feature_1", "feature_2", "feature_3"]
        _, oof_df = train_residual_model(
            sample_pos_data_for_residual,
            "RB",
            feature_cols,
            val_seasons=[2022, 2023],
        )
        if not oof_df.empty:
            expected_cols = {
                "idx",
                "season",
                "week",
                "heuristic_pts",
                "residual_pred",
                "hybrid_pts",
                "actual_pts",
            }
            assert expected_cols.issubset(set(oof_df.columns))

    def test_fold_count_matches_val_seasons(self, sample_pos_data_for_residual):
        feature_cols = ["feature_1", "feature_2", "feature_3"]
        result, _ = train_residual_model(
            sample_pos_data_for_residual,
            "RB",
            feature_cols,
            val_seasons=[2022, 2023],
        )
        assert len(result["fold_details"]) == 2

    def test_hybrid_is_heuristic_plus_residual(self, sample_pos_data_for_residual):
        """hybrid_pts should equal heuristic_pts + residual_pred."""
        feature_cols = ["feature_1", "feature_2", "feature_3"]
        _, oof_df = train_residual_model(
            sample_pos_data_for_residual,
            "RB",
            feature_cols,
            val_seasons=[2022, 2023],
        )
        if not oof_df.empty:
            expected = oof_df["heuristic_pts"] + oof_df["residual_pred"]
            np.testing.assert_allclose(
                oof_df["hybrid_pts"].values,
                expected.values,
                atol=1e-6,
            )

    def test_empty_features_returns_empty(self, sample_pos_data_for_residual):
        result, oof_df = train_residual_model(
            sample_pos_data_for_residual,
            "RB",
            [],  # no features
            val_seasons=[2022, 2023],
        )
        assert result["mean_mae"] == 0.0
        assert oof_df.empty

    def test_mae_positive(self, sample_pos_data_for_residual):
        feature_cols = ["feature_1", "feature_2", "feature_3"]
        result, _ = train_residual_model(
            sample_pos_data_for_residual,
            "RB",
            feature_cols,
            val_seasons=[2022, 2023],
        )
        assert result["mean_mae"] > 0.0

    def test_ridge_alpha_reported(self, sample_pos_data_for_residual):
        feature_cols = ["feature_1", "feature_2", "feature_3"]
        result, _ = train_residual_model(
            sample_pos_data_for_residual,
            "RB",
            feature_cols,
            val_seasons=[2022, 2023],
        )
        for fold in result["fold_details"]:
            assert "ridge_alpha" in fold
            assert fold["ridge_alpha"] > 0


# ---------------------------------------------------------------------------
# Tests: load_residual_model
# ---------------------------------------------------------------------------


class TestLoadResidualModel:
    def test_load_saved_model(self):
        """Load pre-trained WR residual model from models/residual/."""
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models", "residual")
        if not os.path.exists(os.path.join(model_dir, "wr_residual.joblib")):
            pytest.skip("WR residual model not trained yet")

        model, meta = load_residual_model("WR", model_dir)
        assert model is not None
        assert "features" in meta
        assert len(meta["features"]) > 0
        assert meta["position"] == "WR"

    def test_load_te_model(self):
        """Load pre-trained TE residual model."""
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models", "residual")
        if not os.path.exists(os.path.join(model_dir, "te_residual.joblib")):
            pytest.skip("TE residual model not trained yet")

        model, meta = load_residual_model("TE", model_dir)
        assert meta["position"] == "TE"

    def test_file_not_found(self):
        """Raises FileNotFoundError for missing model."""
        with pytest.raises(FileNotFoundError):
            load_residual_model("QB", "/tmp/nonexistent_dir")


# ---------------------------------------------------------------------------
# Tests: apply_residual_correction
# ---------------------------------------------------------------------------


class TestApplyResidualCorrection:
    @pytest.fixture
    def sample_heuristic_projections(self):
        """Heuristic projections for WR players."""
        return pd.DataFrame(
            {
                "player_id": ["wr1", "wr2", "wr3"],
                "player_name": ["Hill", "Chase", "Jefferson"],
                "position": ["WR", "WR", "WR"],
                "projected_points": [14.0, 12.0, 11.0],
                "projected_floor": [8.0, 7.0, 6.5],
                "projected_ceiling": [20.0, 17.0, 15.5],
            }
        )

    @pytest.fixture
    def sample_features(self):
        """Feature data for WR players."""
        np.random.seed(42)
        return pd.DataFrame(
            {
                "player_id": ["wr1", "wr2", "wr3"],
                "receiving_yards_roll3": [80.0, 70.0, 65.0],
                "receiving_yards_roll6": [75.0, 68.0, 62.0],
                "targets_roll3": [8.0, 7.0, 6.5],
                "receptions_roll3": [5.0, 4.5, 4.0],
            }
        )

    def test_returns_dataframe(self, sample_heuristic_projections, sample_features):
        """apply_residual_correction returns a DataFrame."""
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models", "residual")
        if not os.path.exists(os.path.join(model_dir, "wr_residual.joblib")):
            pytest.skip("WR residual model not trained yet")

        result = apply_residual_correction(
            sample_heuristic_projections, sample_features, "WR", model_dir
        )
        assert isinstance(result, pd.DataFrame)
        assert "projected_points" in result.columns
        assert len(result) == 3

    def test_projections_non_negative(
        self, sample_heuristic_projections, sample_features
    ):
        """Corrected projections are always >= 0."""
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models", "residual")
        if not os.path.exists(os.path.join(model_dir, "wr_residual.joblib")):
            pytest.skip("WR residual model not trained yet")

        result = apply_residual_correction(
            sample_heuristic_projections, sample_features, "WR", model_dir
        )
        assert (result["projected_points"] >= 0).all()

    def test_no_model_returns_unchanged(
        self, sample_heuristic_projections, sample_features
    ):
        """When model file is missing, returns heuristic unchanged."""
        result = apply_residual_correction(
            sample_heuristic_projections,
            sample_features,
            "WR",
            model_dir="/tmp/nonexistent_dir",
        )
        pd.testing.assert_frame_equal(result, sample_heuristic_projections)

    def test_handles_missing_features_gracefully(self, sample_heuristic_projections):
        """Model handles features DataFrame with none of the expected columns."""
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models", "residual")
        if not os.path.exists(os.path.join(model_dir, "wr_residual.joblib")):
            pytest.skip("WR residual model not trained yet")

        # Features with no matching columns
        no_match_features = pd.DataFrame(
            {
                "player_id": ["wr1", "wr2", "wr3"],
                "totally_fake_col": [1.0, 2.0, 3.0],
            }
        )
        result = apply_residual_correction(
            sample_heuristic_projections, no_match_features, "WR", model_dir
        )
        # Should return heuristic unchanged (no features matched)
        pd.testing.assert_frame_equal(result, sample_heuristic_projections)


# ---------------------------------------------------------------------------
# Tests: ML router hybrid integration
# ---------------------------------------------------------------------------


class TestRouterHybridIntegration:
    def test_hybrid_positions_constant(self):
        """HYBRID_POSITIONS contains WR and TE."""
        from ml_projection_router import HYBRID_POSITIONS

        assert "WR" in HYBRID_POSITIONS
        assert "TE" in HYBRID_POSITIONS

    def test_ship_gate_returns_skip_for_all_positions(self):
        """Ship gate returns SKIP for all positions — heuristic-only with bias corrections."""
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models", "player")
        if not os.path.exists(os.path.join(model_dir, "ship_gate_report.json")):
            pytest.skip("Ship gate report not found")

        from ml_projection_router import _load_ship_gate

        verdicts = _load_ship_gate(model_dir)
        # v4.1-p5: All positions use heuristic-only with bias corrections
        # QB: POSITION_BIAS_CORRECTION +2.5, WR/TE: POSITION_CEILING_SHRINKAGE
        assert verdicts.get("QB") == "SKIP"
        assert verdicts.get("WR") == "SKIP"
        assert verdicts.get("TE") == "SKIP"
