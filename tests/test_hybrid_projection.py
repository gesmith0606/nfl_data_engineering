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


class TestApplyResidualCorrectionBlend:
    """Secondary-model blend (2026-08-16 WR gap-fix, WR_GAP_FIX_2026_08_16.md).

    Fully synthetic — builds two tiny fitted Ridge pipelines directly so the
    test doesn't depend on the real trained artifacts on disk.
    """

    @staticmethod
    def _make_ridge_model_dir(tmp_dir, position, features, constant_pred, extra_meta=None):
        import joblib
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import Pipeline
        from sklearn.impute import SimpleImputer

        # A Ridge fit on all-zero features whose intercept equals
        # constant_pred always predicts constant_pred regardless of X.
        X = pd.DataFrame({f: [0.0, 0.0] for f in features})
        y = pd.Series([constant_pred, constant_pred])
        pipe = Pipeline(
            [("imputer", SimpleImputer(strategy="median")), ("model", Ridge(alpha=1.0))]
        )
        pipe.fit(X, y)

        os.makedirs(tmp_dir, exist_ok=True)
        model_path = os.path.join(tmp_dir, f"{position.lower()}_residual.joblib")
        meta_path = os.path.join(tmp_dir, f"{position.lower()}_residual_meta.json")
        joblib.dump(pipe, model_path)
        meta = {
            "position": position,
            "model_type": "ridge",
            "features": features,
            "graph_features_added": 0,
        }
        if extra_meta:
            meta.update(extra_meta)
        with open(meta_path, "w") as f:
            json.dump(meta, f)
        return tmp_dir

    def test_blend_averages_primary_and_secondary(self, tmp_path):
        """Blended projected_points == (1-w)*primary + w*secondary."""
        features = ["targets_roll3"]
        heuristic = pd.DataFrame(
            {
                "player_id": ["wr1", "wr2"],
                "position": ["WR", "WR"],
                "projected_points": [10.0, 20.0],
            }
        )
        player_features = pd.DataFrame(
            {"player_id": ["wr1", "wr2"], "targets_roll3": [8.0, 9.0]}
        )

        secondary_dir = self._make_ridge_model_dir(
            tmp_path / "secondary", "WR", features, constant_pred=4.0
        )
        primary_dir = self._make_ridge_model_dir(
            tmp_path / "primary",
            "WR",
            features,
            constant_pred=2.0,
            extra_meta={
                "blend_secondary_dir": str(secondary_dir),
                "blend_weight": 0.4,
            },
        )

        result = apply_residual_correction(
            heuristic, player_features, "WR", model_dir=str(primary_dir)
        )

        # primary correction = +2.0 -> 12.0, 22.0 ; secondary = +4.0 -> 14.0, 24.0
        # blended = 0.6*primary + 0.4*secondary
        expected = pd.Series([0.6 * 12.0 + 0.4 * 14.0, 0.6 * 22.0 + 0.4 * 24.0])
        pd.testing.assert_series_equal(
            result["projected_points"], expected, check_names=False, atol=0.05
        )

    def test_no_blend_keys_is_unaffected(self, tmp_path):
        """Meta without blend_secondary_dir/blend_weight behaves exactly as before."""
        features = ["targets_roll3"]
        heuristic = pd.DataFrame(
            {
                "player_id": ["wr1"],
                "position": ["WR"],
                "projected_points": [10.0],
            }
        )
        player_features = pd.DataFrame({"player_id": ["wr1"], "targets_roll3": [8.0]})
        primary_dir = self._make_ridge_model_dir(
            tmp_path / "primary_only", "WR", features, constant_pred=2.0
        )
        result = apply_residual_correction(
            heuristic, player_features, "WR", model_dir=str(primary_dir)
        )
        assert result["projected_points"].iloc[0] == pytest.approx(12.0, abs=0.05)


# ---------------------------------------------------------------------------
# Tests: apply_residual_correction dedup determinism (no real model needed)
# ---------------------------------------------------------------------------


class TestApplyResidualCorrectionDedupDeterminism:
    """Regression test for the feature-merge dedup bug.

    When heuristic_projections lacks season/week columns, extra_keys is
    empty and dedup_keys collapses to just the player id column --
    drop_duplicates(keep="last") then picked an arbitrary row per player
    based on incidental player_features row order. The fix sorts
    player_features by season/week before the merge so the most recent row
    wins deterministically. Uses a stub model (via patching
    load_residual_model) instead of a real trained model, so this runs
    without depending on any model artifact being present on disk.
    """

    def test_most_recent_season_week_row_wins(self):
        from unittest.mock import patch

        from hybrid_projection import apply_residual_correction

        heuristic_projections = pd.DataFrame(
            {
                "player_id": ["P1"],
                "player_name": ["Player One"],
                "position": ["WR"],
                "projected_points": [10.0],
            }
        )
        # Multiple rows per player across season/week, deliberately out of
        # order, with the earliest (wrong) row physically last so the old
        # unsorted keep="last" would have picked it.
        player_features = pd.DataFrame(
            {
                "player_id": ["P1", "P1", "P1"],
                "season": [2023, 2024, 2022],
                "week": [1, 1, 1],
                "signal": [1.0, 99.0, 2.0],
            }
        )

        class _DummyModel:
            def predict(self, X):
                return X["signal"].values

        meta = {
            "model_type": "ridge",
            "features": ["signal"],
            "graph_features_added": 0,
        }

        with patch(
            "hybrid_projection.load_residual_model",
            return_value=(_DummyModel(), meta),
        ):
            result = apply_residual_correction(
                heuristic_projections, player_features, "WR", model_dir="unused"
            )

        # Must use the season=2024 (most recent) row's signal (99.0), not
        # whichever row happened to be last in player_features (season=2022,
        # signal=2.0 -> would give 12.0 instead of 109.0).
        assert result["projected_points"].iloc[0] == pytest.approx(10.0 + 99.0)


# ---------------------------------------------------------------------------
# Tests: ML router hybrid integration
# ---------------------------------------------------------------------------


class TestRouterHybridIntegration:
    def test_hybrid_positions_constant(self):
        """HYBRID_POSITIONS is {QB, RB, TE, WR} after the v4.4 sealed-2025 gate.

        v4.2: TE shipped (3.521 -> 3.361 MAE); WR failed (bias +0.73,
        pre-blend-consistency training). v4.3 (2026-06-12): WR ships after
        the blend-consistent retrain — sealed 2025 gap -0.148 vs Sleeper,
        bias +0.29. v4.4 (2026-08-15): QB/RB retrained on repaired
        snap_pct/NGS/PFR/QBR features, leak-verified, and flipped SKIP->HYBRID
        (sealed 2025: QB 6.459->5.773 MAE, RB 5.109->4.920 MAE). See
        .planning/HYBRID_SHIP_2026_08_15.md.
        """
        from ml_projection_router import HYBRID_POSITIONS

        assert HYBRID_POSITIONS == {"QB", "RB", "TE", "WR"}

    def test_ship_gate_verdicts_v44(self):
        """QB/RB/TE/WR are all HYBRID when models exist with a v4.2+blend stamp."""
        model_dir = os.path.join(os.path.dirname(__file__), "..", "models", "player")
        if not os.path.exists(os.path.join(model_dir, "ship_gate_report.json")):
            pytest.skip("Ship gate report not found")

        from ml_projection_router import _load_ship_gate

        verdicts = _load_ship_gate(model_dir)
        for pos in ("QB", "RB"):
            meta_path = os.path.join(
                os.path.dirname(__file__), "..", "models", "residual",
                f"{pos.lower()}_residual_meta.json",
            )
            if os.path.exists(meta_path):
                with open(meta_path) as fh:
                    meta = json.load(fh)
                expected = (
                    "HYBRID"
                    if meta.get("heuristic_version") == "v4.2+blend"
                    else "SKIP"
                )
                assert verdicts.get(pos) == expected
        wr_meta_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "residual",
            "wr_residual_meta.json",
        )
        if os.path.exists(wr_meta_path):
            with open(wr_meta_path) as fh:
                wr_meta = json.load(fh)
            # Only blend-consistent models may activate HYBRID: a "v4.2"
            # stamp predates the veteran prior blend in the inference
            # baseline and is known-broken (TE -0.38 -> +0.15 swing).
            expected_wr = (
                "HYBRID"
                if wr_meta.get("heuristic_version") == "v4.2+blend"
                else "SKIP"
            )
            assert verdicts.get("WR") == expected_wr

        te_meta_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "residual",
            "te_residual_meta.json",
        )
        if os.path.exists(te_meta_path):
            with open(te_meta_path) as fh:
                te_meta = json.load(fh)
            # Only the blend-consistent retrain may activate HYBRID.
            expected = (
                "HYBRID"
                if te_meta.get("heuristic_version") == "v4.2+blend"
                else "SKIP"
            )
            assert verdicts.get("TE") == expected

    def test_stale_pre_blend_stamp_stays_skip(self, tmp_path):
        """A v4.2 (pre-blend) residual meta must NOT activate HYBRID.

        Guards against restoring *.pre_blend_backup models: the inference
        baseline includes the veteran prior blend, so a residual trained on
        the raw heuristic is the exact mismatch that swung TE -0.38 -> +0.15
        vs consensus.
        """
        from ml_projection_router import _load_ship_gate

        model_dir = tmp_path / "player"
        model_dir.mkdir()
        (model_dir / "ship_gate_report.json").write_text(
            json.dumps(
                {
                    "positions": [
                        {"position": "TE", "verdict": "SKIP"},
                        {"position": "WR", "verdict": "SKIP"},
                    ]
                }
            )
        )
        residual_dir = tmp_path / "residual"
        residual_dir.mkdir()
        (residual_dir / "te_residual_meta.json").write_text(
            json.dumps({"heuristic_version": "v4.2"})
        )
        (residual_dir / "wr_residual_meta.json").write_text(
            json.dumps({"heuristic_version": "v4.2+blend"})
        )

        verdicts = _load_ship_gate(str(model_dir))
        assert verdicts.get("TE") == "SKIP"  # stale pre-blend stamp rejected
        assert verdicts.get("WR") == "HYBRID"  # blend-consistent accepted


class TestComputeHeuristicBaselineVeteranBlend:
    """Verify compute_heuristic_baseline applies veteran blend when weekly_df
    is provided (training/inference consistency fix for TE).
    """

    def _make_te_row_veteran_ramp(self) -> pd.DataFrame:
        """TE player at week 4 who only played 1 game (low rolling weight)."""
        return pd.DataFrame(
            {
                "player_id": ["vet_te_001"],
                "position": ["TE"],
                "recent_team": ["SF"],
                "season": [2023],
                "week": [4],
                "opponent": ["LAR"],
                "opponent_team": ["LAR"],
                # Low early-season rolling averages (only 1 game played)
                "targets_roll3": [2.0],
                "targets_roll6": [2.0],
                "targets_std": [2.0],
                "receptions_roll3": [1.5],
                "receptions_roll6": [1.5],
                "receptions_std": [1.5],
                "receiving_yards_roll3": [15.0],
                "receiving_yards_roll6": [15.0],
                "receiving_yards_std": [15.0],
                "receiving_tds_roll3": [0.0],
                "receiving_tds_roll6": [0.0],
                "receiving_tds_std": [0.0],
                "snap_pct": [0.75],
                "offense_pct": [0.75],
                "target_share": [0.12],
            }
        )

    def _make_weekly_df_with_prior(self) -> pd.DataFrame:
        """Prior-season data giving the TE a strong per-game rate in 2022."""
        rows = []
        for wk in range(1, 17):
            rows.append(
                {
                    "player_id": "vet_te_001",
                    "position": "TE",
                    "season": 2022,
                    "week": wk,
                    "recent_team": "SF",
                    "targets": 7.0,
                    "receptions": 5.0,
                    "receiving_yards": 60.0,
                    "receiving_tds": 0.5,
                }
            )
        return pd.DataFrame(rows)

    def test_with_weekly_df_raises_baseline_for_veteran(self):
        """When weekly_df is supplied, veteran blend should raise the low
        early-season baseline for a player with only 1 game played.

        The blend weight for n_games=1 with steepness=0.7 is ~0.50.
        With a strong prior (60 yds, 5 rec/game in 2022) the blended
        baseline should be meaningfully higher than the raw rolling columns.
        """
        from projection_engine import compute_heuristic_baseline, USE_VETERAN_PRIOR_BLEND

        if not USE_VETERAN_PRIOR_BLEND:
            pytest.skip("USE_VETERAN_PRIOR_BLEND is disabled globally")

        pos_df = self._make_te_row_veteran_ramp()
        weekly_df = self._make_weekly_df_with_prior()

        pts_no_blend = compute_heuristic_baseline(
            pos_df, "TE", pd.DataFrame()
        ).iloc[0]
        pts_with_blend = compute_heuristic_baseline(
            pos_df, "TE", pd.DataFrame(), weekly_df=weekly_df
        ).iloc[0]

        # The blend should raise the projection for this low-rolling veteran
        assert pts_with_blend > pts_no_blend, (
            f"Expected blend to raise projection for early-season veteran TE; "
            f"got no_blend={pts_no_blend:.2f}, with_blend={pts_with_blend:.2f}"
        )

    def test_without_weekly_df_blend_not_applied(self):
        """When weekly_df=None, blend is skipped and result equals the raw
        rolling-only heuristic (backward-compatible default).
        """
        from projection_engine import compute_heuristic_baseline

        pos_df = self._make_te_row_veteran_ramp()

        pts_default = compute_heuristic_baseline(pos_df, "TE", pd.DataFrame()).iloc[0]
        pts_explicit_none = compute_heuristic_baseline(
            pos_df, "TE", pd.DataFrame(), weekly_df=None
        ).iloc[0]

        assert pts_default == pytest.approx(pts_explicit_none, abs=1e-6), (
            "weekly_df=None should produce same result as default (no weekly_df)"
        )

    def test_blend_version_stamp_in_meta(self, tmp_path):
        """When Bronze weekly data is present, train_and_save_residual_models
        stamps heuristic_version='v4.2+blend' in the meta JSON.
        This allows the router to distinguish blend-consistent models.
        """
        # We verify the stamp logic without running a full training — just
        # check that the expected constant string exists in hybrid_projection.
        import hybrid_projection as hp
        import inspect

        source = inspect.getsource(hp.train_and_save_residual_models)
        assert "v4.2+blend" in source, (
            "train_and_save_residual_models must stamp 'v4.2+blend' when "
            "Bronze weekly data is available for veteran blend training"
        )
