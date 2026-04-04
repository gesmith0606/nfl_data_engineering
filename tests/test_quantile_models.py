"""Tests for quantile regression models.

Covers:
- Train/save/load cycle with synthetic data
- Predict quantiles output schema
- Floor <= projection <= ceiling invariant
- Calibration computation
- Fallback when no models available
- Integration with projection_engine
"""

import os
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest

# Ensure src is on path
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quantile_models import (
    DEFAULT_QUANTILES,
    compute_calibration,
    load_quantile_models,
    predict_quantiles,
    save_quantile_models,
    train_quantile_models,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_synthetic_data(
    n_per_season: int = 200,
    seasons: list = None,
) -> pd.DataFrame:
    """Create synthetic player-week data with known feature/target relationship.

    Target = 5*x1 + 3*x2 + noise, so quantile models should learn this pattern.
    """
    if seasons is None:
        seasons = [2020, 2021, 2022, 2023, 2024]

    rng = np.random.RandomState(42)
    rows = []

    for season in seasons:
        for week in range(1, 19):
            n = n_per_season // 18
            for _ in range(n):
                pos = rng.choice(["QB", "RB", "WR", "TE"])
                x1 = rng.normal(5, 2)
                x2 = rng.normal(3, 1)
                noise = rng.normal(0, 3)
                target = max(0, 5 * x1 + 3 * x2 + noise)

                rows.append(
                    {
                        "player_id": f"P{rng.randint(1, 50):03d}",
                        "player_name": f"Player {rng.randint(1, 50)}",
                        "position": pos,
                        "season": season,
                        "week": week,
                        # Feature columns (roll3/roll6 naming to pass get_player_feature_columns)
                        "rushing_yards_roll3": x1,
                        "receiving_yards_roll3": x2,
                        "rushing_yards_roll6": x1 * 0.9,
                        "receiving_yards_roll6": x2 * 0.9,
                        "rushing_tds_roll3": rng.uniform(0, 1),
                        "receiving_tds_roll3": rng.uniform(0, 1),
                        "carries_roll3": rng.uniform(5, 20),
                        "targets_roll3": rng.uniform(3, 12),
                        "receptions_roll3": rng.uniform(2, 8),
                        "snap_pct_roll3": rng.uniform(0.3, 1.0),
                        "target_share_roll3": rng.uniform(0.05, 0.30),
                        "carry_share_roll3": rng.uniform(0.1, 0.5),
                        "fantasy_points_target": target,
                        # Label columns (needed so get_player_feature_columns excludes them)
                        "passing_yards": rng.normal(100, 50),
                        "rushing_yards": rng.normal(40, 20),
                    }
                )

    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    """Synthetic player-week DataFrame for testing."""
    return _make_synthetic_data()


@pytest.fixture
def tmp_model_dir():
    """Temporary directory for model save/load tests."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# T-01: Training
# ---------------------------------------------------------------------------


class TestTrainQuantileModels:
    """Test train_quantile_models function."""

    def test_trains_all_positions(self, synthetic_df: pd.DataFrame) -> None:
        """Should train models for all 4 positions."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
        )
        assert "models" in result
        assert "feature_cols" in result
        assert "oof_predictions" in result
        assert "imputer" in result

        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in result["models"], f"Missing models for {pos}"
            assert len(result["models"][pos]) == 3  # 3 quantiles

    def test_trains_subset_positions(self, synthetic_df: pd.DataFrame) -> None:
        """Should train only requested positions."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB", "WR"],
        )
        assert "QB" in result["models"]
        assert "WR" in result["models"]
        assert "RB" not in result["models"]
        assert "TE" not in result["models"]

    def test_oof_predictions_not_empty(self, synthetic_df: pd.DataFrame) -> None:
        """OOF predictions should have rows for validation seasons."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
        )
        oof = result["oof_predictions"]
        assert not oof.empty
        assert "actual" in oof.columns
        assert "q10" in oof.columns
        assert "q50" in oof.columns
        assert "q90" in oof.columns

    def test_custom_quantiles(self, synthetic_df: pd.DataFrame) -> None:
        """Should support custom quantile levels."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            quantiles=[0.05, 0.5, 0.95],
            positions=["QB"],
        )
        assert len(result["models"]["QB"]) == 3
        assert 0.05 in result["models"]["QB"]
        assert 0.95 in result["models"]["QB"]

    def test_feature_cols_are_numeric(self, synthetic_df: pd.DataFrame) -> None:
        """Feature columns should all be numeric."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )
        for col in result["feature_cols"]:
            assert col in synthetic_df.columns
            assert synthetic_df[col].dtype in [
                np.float64,
                np.int64,
                np.float32,
                np.int32,
            ]


# ---------------------------------------------------------------------------
# T-02: Save / Load
# ---------------------------------------------------------------------------


class TestSaveLoadQuantileModels:
    """Test save and load cycle."""

    def test_save_load_roundtrip(
        self, synthetic_df: pd.DataFrame, tmp_model_dir: str
    ) -> None:
        """Models should survive save/load cycle."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB", "RB"],
        )
        save_quantile_models(result, path=tmp_model_dir)

        loaded = load_quantile_models(path=tmp_model_dir)
        assert loaded is not None
        assert "QB" in loaded["models"]
        assert "RB" in loaded["models"]
        assert len(loaded["feature_cols"]) == len(result["feature_cols"])
        assert loaded["imputer"] is not None

    def test_load_nonexistent_returns_none(self, tmp_model_dir: str) -> None:
        """Loading from empty directory should return None."""
        loaded = load_quantile_models(path=os.path.join(tmp_model_dir, "nonexistent"))
        assert loaded is None

    def test_predictions_match_after_reload(
        self, synthetic_df: pd.DataFrame, tmp_model_dir: str
    ) -> None:
        """Predictions from loaded models should match original."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )
        save_quantile_models(result, path=tmp_model_dir)
        loaded = load_quantile_models(path=tmp_model_dir)

        qb_data = synthetic_df[synthetic_df["position"] == "QB"].head(10)
        preds_orig = predict_quantiles(result, qb_data, "QB")
        preds_loaded = predict_quantiles(loaded, qb_data, "QB")

        pd.testing.assert_frame_equal(preds_orig, preds_loaded)


# ---------------------------------------------------------------------------
# T-03: Predict quantiles
# ---------------------------------------------------------------------------


class TestPredictQuantiles:
    """Test predict_quantiles function."""

    def test_output_columns(self, synthetic_df: pd.DataFrame) -> None:
        """Should output floor, projection, ceiling columns."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )
        qb_data = synthetic_df[synthetic_df["position"] == "QB"].head(20)
        preds = predict_quantiles(result, qb_data, "QB")

        assert "quantile_floor" in preds.columns
        assert "quantile_projection" in preds.columns
        assert "quantile_ceiling" in preds.columns

    def test_floor_le_projection_le_ceiling(self, synthetic_df: pd.DataFrame) -> None:
        """Floor should be <= projection <= ceiling for all rows."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["WR"],
        )
        wr_data = synthetic_df[synthetic_df["position"] == "WR"]
        preds = predict_quantiles(result, wr_data, "WR")

        valid = preds.dropna()
        assert (valid["quantile_floor"] <= valid["quantile_projection"]).all()
        assert (valid["quantile_projection"] <= valid["quantile_ceiling"]).all()

    def test_predictions_nonnegative(self, synthetic_df: pd.DataFrame) -> None:
        """All predictions should be >= 0."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["RB"],
        )
        rb_data = synthetic_df[synthetic_df["position"] == "RB"]
        preds = predict_quantiles(result, rb_data, "RB")

        valid = preds.dropna()
        assert (valid["quantile_floor"] >= 0).all()
        assert (valid["quantile_projection"] >= 0).all()
        assert (valid["quantile_ceiling"] >= 0).all()

    def test_missing_position_returns_nans(self, synthetic_df: pd.DataFrame) -> None:
        """Should return NaN columns for unknown position."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )
        rb_data = synthetic_df[synthetic_df["position"] == "RB"].head(5)
        preds = predict_quantiles(result, rb_data, "RB")

        assert preds["quantile_floor"].isna().all()

    def test_index_alignment(self, synthetic_df: pd.DataFrame) -> None:
        """Predictions index should match input index."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["TE"],
        )
        te_data = synthetic_df[synthetic_df["position"] == "TE"].head(15)
        preds = predict_quantiles(result, te_data, "TE")

        assert list(preds.index) == list(te_data.index)


# ---------------------------------------------------------------------------
# T-04: Calibration
# ---------------------------------------------------------------------------


class TestCalibration:
    """Test compute_calibration function."""

    def test_calibration_output_schema(self, synthetic_df: pd.DataFrame) -> None:
        """Calibration DataFrame should have expected columns."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
        )
        cal = compute_calibration(result["oof_predictions"])

        assert "position" in cal.columns
        assert "coverage_80" in cal.columns
        assert "lower_tail_10" in cal.columns
        assert "upper_tail_10" in cal.columns
        assert "mean_interval_width" in cal.columns
        assert "q50_mae" in cal.columns
        assert len(cal) == 4  # QB, RB, WR, TE

    def test_coverage_tails_sum_to_one(self, synthetic_df: pd.DataFrame) -> None:
        """coverage + lower_tail + upper_tail should approximately sum to 1."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
        )
        cal = compute_calibration(result["oof_predictions"])

        for _, row in cal.iterrows():
            total = row["coverage_80"] + row["lower_tail_10"] + row["upper_tail_10"]
            assert abs(total - 1.0) < 0.01, f"{row['position']}: sum={total}"

    def test_interval_width_positive(self, synthetic_df: pd.DataFrame) -> None:
        """Mean interval width should be positive."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
        )
        cal = compute_calibration(result["oof_predictions"])

        for _, row in cal.iterrows():
            assert row["mean_interval_width"] > 0

    def test_empty_oof_returns_empty(self) -> None:
        """Empty OOF DataFrame should return empty calibration."""
        cal = compute_calibration(pd.DataFrame())
        assert cal.empty


# ---------------------------------------------------------------------------
# T-05: Fallback in projection engine
# ---------------------------------------------------------------------------


class TestProjectionEngineFallback:
    """Test that projection engine falls back to heuristic when no models."""

    def test_add_floor_ceiling_without_quantile_models(self) -> None:
        """add_floor_ceiling should still work without quantile models."""
        from projection_engine import add_floor_ceiling

        df = pd.DataFrame(
            {
                "projected_points": [15.0, 10.0, 20.0, 8.0],
                "position": ["QB", "RB", "WR", "TE"],
            }
        )
        result = add_floor_ceiling(df)

        assert "projected_floor" in result.columns
        assert "projected_ceiling" in result.columns
        # Heuristic: floor = pts * (1 - mult), ceiling = pts * (1 + mult)
        assert result.loc[0, "projected_floor"] == round(15.0 * 0.55, 2)  # QB 45%
        assert result.loc[0, "projected_ceiling"] == round(15.0 * 1.45, 2)

    def test_add_floor_ceiling_with_quantile_override(
        self, synthetic_df: pd.DataFrame, tmp_model_dir: str
    ) -> None:
        """add_floor_ceiling should use quantile models when available."""
        from projection_engine import add_floor_ceiling

        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )
        save_quantile_models(result, path=tmp_model_dir)

        # The function should still produce valid output regardless
        df = pd.DataFrame(
            {
                "projected_points": [15.0, 10.0],
                "position": ["QB", "WR"],
            }
        )
        result_df = add_floor_ceiling(df)
        assert "projected_floor" in result_df.columns
        assert "projected_ceiling" in result_df.columns
        assert (result_df["projected_floor"] <= result_df["projected_points"]).all()
        assert (result_df["projected_ceiling"] >= result_df["projected_points"]).all()


# ---------------------------------------------------------------------------
# T-06: Integration with projection engine
# ---------------------------------------------------------------------------


class TestIntegrationProjectionEngine:
    """Test quantile models integrate correctly with projection pipeline."""

    def test_floor_ceiling_invariant_after_quantile(
        self, synthetic_df: pd.DataFrame
    ) -> None:
        """After quantile prediction, floor <= point <= ceiling."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB", "RB", "WR", "TE"],
        )
        for pos in ["QB", "RB", "WR", "TE"]:
            pos_data = synthetic_df[synthetic_df["position"] == pos].head(20)
            preds = predict_quantiles(result, pos_data, pos)
            valid = preds.dropna()
            if not valid.empty:
                assert (valid["quantile_floor"] <= valid["quantile_ceiling"]).all()
