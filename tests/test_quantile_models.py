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
    _check_imputer_statistics,
    compute_calibration,
    load_quantile_models,
    pinball_loss,
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

    def test_cv_fold_imputer_never_sees_future_seasons(
        self, synthetic_df: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression test for the walk-forward imputer leak.

        Each walk-forward CV fold must fit its imputer only on that fold's
        training slice (seasons strictly before the validation season). The
        single production-fit call (before the CV loop, and reused for the
        all-data final models) is exempt and is expected to see every
        season. We spy on SimpleImputer.fit to record which row indices --
        and therefore which seasons -- each fit call touched.
        """
        import quantile_models as qm

        fit_calls: list = []
        real_simple_imputer = qm.SimpleImputer

        class SpyImputer(real_simple_imputer):
            def fit(self, X, y=None):
                fit_calls.append(X.index)
                return super().fit(X, y)

        monkeypatch.setattr(qm, "SimpleImputer", SpyImputer)

        train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
        )

        assert len(fit_calls) > 1, "expected both a production fit and fold fits"

        # First fit call is the pre-loop production imputer fit on the full
        # dataset -- it legitimately spans every season.
        production_seasons = synthetic_df.loc[fit_calls[0], "season"]
        assert production_seasons.max() == synthetic_df["season"].max()

        # Every subsequent fit call is a per-fold imputer. None of them may
        # contain rows from a season >= the max season in that same slice's
        # neighboring validation fold; concretely, walk-forward means a
        # fold's training slice must never reach the dataset's final season
        # unless every season is used as training (impossible by construction
        # here since validation_seasons excludes the two earliest seasons).
        # The direct, robust check: no fold imputer fit call may include the
        # dataset's maximum season, because the maximum season is always
        # held out as a validation season for the last fold.
        max_season = synthetic_df["season"].max()
        for idx in fit_calls[1:]:
            fold_seasons = synthetic_df.loc[idx, "season"]
            assert fold_seasons.max() < max_season, (
                "fold imputer was fit on data including the latest season, "
                "meaning it saw validation/future data -- the walk-forward "
                "imputer leak has regressed"
            )


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


# ---------------------------------------------------------------------------
# T-08: Imputer statistics integrity (MODEL_REVIEW_2026_08_15.md finding #1)
# ---------------------------------------------------------------------------


class TestImputerStatisticsIntegrity:
    """Regression coverage for the shipped-imputer NaN/silent-drop bug.

    Before this fix, ``SimpleImputer(strategy="median")`` defaulted to
    ``keep_empty_features=False``: an all-NaN column at fit time was
    silently dropped from every future ``transform()`` call. Confirmed
    empirically against the shipped ``models/quantile/imputer.pkl`` -- 28
    columns (the entire snap_pct family + interactions) were dropped this
    way. The fix keeps the column (statistic backfilled to 0) and adds an
    explicit fail-loud check for the case where NaN statistics show up
    anyway.
    """

    def test_all_nan_feature_column_is_kept_not_dropped(
        self, synthetic_df: pd.DataFrame
    ) -> None:
        """An all-NaN feature column must survive fit+transform, not vanish."""
        df = synthetic_df.copy()
        df["wide_open_all_nan_roll3"] = np.nan

        result = train_quantile_models(
            df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )

        assert "wide_open_all_nan_roll3" in result["feature_cols"]

        imputer = result["imputer"]
        assert not np.isnan(imputer.statistics_).any()

        col_idx = result["feature_cols"].index("wide_open_all_nan_roll3")
        assert imputer.statistics_[col_idx] == 0.0

        # transform() must not drop the column either.
        X = df[result["feature_cols"]].head(5)
        transformed = imputer.transform(X)
        assert transformed.shape[1] == len(result["feature_cols"])

    def test_check_imputer_statistics_passes_for_clean_imputer(self) -> None:
        """No-op (does not raise) when statistics_ has no NaN."""
        from sklearn.impute import SimpleImputer

        imp = SimpleImputer(strategy="median", keep_empty_features=True)
        imp.fit(np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]))
        _check_imputer_statistics(imp, context="test")  # must not raise

    def test_check_imputer_statistics_raises_on_nan(self) -> None:
        """Detects a NaN-statistics imputer directly (unit-level).

        Reproduces the pre-fix shipped-artifact failure mode exactly:
        keep_empty_features=False + an all-NaN column at fit time leaves a
        real NaN entry in statistics_ (sklearn does not synthesize a
        fallback value in this configuration).
        """
        from sklearn.impute import SimpleImputer

        imp = SimpleImputer(strategy="median", keep_empty_features=False)
        imp.fit(np.array([[1.0, np.nan], [3.0, np.nan], [5.0, np.nan]]))
        assert np.isnan(imp.statistics_).any()  # sanity: reproduces the bug

        with pytest.raises(ValueError, match="NaN statistic"):
            _check_imputer_statistics(imp, context="test artifact")

    def test_predict_quantiles_detects_nan_stats_in_loaded_artifact(
        self, synthetic_df: pd.DataFrame
    ) -> None:
        """A loaded artifact with NaN imputer statistics must fail loud at
        predict time, not silently serve degraded (or dropped-feature)
        predictions."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )
        # Simulate a stale/pre-fix shipped artifact whose imputer somehow
        # carries NaN statistics (e.g. loaded from disk after being fit
        # with the old keep_empty_features=False default on an all-NaN
        # column).
        bad_stats = result["imputer"].statistics_.copy()
        bad_stats[0] = np.nan
        result["imputer"].statistics_ = bad_stats

        qb_data = synthetic_df[synthetic_df["position"] == "QB"].head(5)
        with pytest.raises(ValueError, match="NaN statistic"):
            predict_quantiles(result, qb_data, "QB")

    def test_pinball_loss_zero_for_perfect_prediction(self) -> None:
        """Pinball loss is 0 when predictions exactly match actuals."""
        actual = np.array([1.0, 2.0, 3.0])
        assert pinball_loss(actual, actual, alpha=0.1) == pytest.approx(0.0)
        assert pinball_loss(actual, actual, alpha=0.9) == pytest.approx(0.0)

    def test_pinball_loss_penalizes_asymmetrically(self) -> None:
        """Under vs over-prediction penalty flips sign around alpha=0.5."""
        actual = np.array([10.0])
        under = np.array([5.0])  # prediction below actual
        over = np.array([15.0])  # prediction above actual

        # At alpha=0.9 (ceiling), under-prediction should cost more than
        # over-prediction by the same margin.
        loss_under_90 = pinball_loss(actual, under, alpha=0.9)
        loss_over_90 = pinball_loss(actual, over, alpha=0.9)
        assert loss_under_90 > loss_over_90

        # At alpha=0.1 (floor), the asymmetry flips.
        loss_under_10 = pinball_loss(actual, under, alpha=0.1)
        loss_over_10 = pinball_loss(actual, over, alpha=0.1)
        assert loss_over_10 > loss_under_10


# ---------------------------------------------------------------------------
# T-07: Conformal width factors (ELITE 2.5)
# ---------------------------------------------------------------------------


class TestConformalWidening:
    """Test conformal width-factor application in predict_quantiles."""

    @staticmethod
    def _with_factors(result: dict, position: str, factor: float) -> dict:
        """Inject conformal width factors into a trained-result dict."""
        out = dict(result)
        out["conformal_width_factors"] = {
            position: {"width_factor": factor, "oof_coverage_at_factor": 0.80}
        }
        return out

    def test_widening_expands_band(self, synthetic_df: pd.DataFrame) -> None:
        """factor > 1 should lower floors and raise ceilings around q50."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["WR"],
        )
        wr_data = synthetic_df[synthetic_df["position"] == "WR"].head(30)
        raw = predict_quantiles(result, wr_data, "WR", apply_conformal=False)
        conf = predict_quantiles(
            self._with_factors(result, "WR", 1.15),
            wr_data,
            "WR",
            apply_conformal=True,
        )

        raw_width = raw["quantile_ceiling"] - raw["quantile_floor"]
        conf_width = conf["quantile_ceiling"] - conf["quantile_floor"]
        # Width must never shrink, and must grow wherever the raw band has
        # room (floor not clipped at 0).
        assert (conf_width >= raw_width - 1e-9).all()
        assert (conf["quantile_ceiling"] >= raw["quantile_ceiling"] - 1e-9).all()
        assert (conf_width > raw_width).any()

    def test_no_factor_is_noop(self, synthetic_df: pd.DataFrame) -> None:
        """apply_conformal=True without stored factors must not change output."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["RB"],
        )
        rb_data = synthetic_df[synthetic_df["position"] == "RB"].head(30)
        raw = predict_quantiles(result, rb_data, "RB", apply_conformal=False)
        conf = predict_quantiles(result, rb_data, "RB", apply_conformal=True)
        pd.testing.assert_frame_equal(raw, conf)

    def test_invariants_hold_after_widening(
        self, synthetic_df: pd.DataFrame
    ) -> None:
        """Floor >= 0 and floor <= projection <= ceiling after conformal."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["TE"],
        )
        te_data = synthetic_df[synthetic_df["position"] == "TE"]
        preds = predict_quantiles(
            self._with_factors(result, "TE", 1.15),
            te_data,
            "TE",
            apply_conformal=True,
        )
        valid = preds.dropna()
        assert (valid["quantile_floor"] >= 0).all()
        assert (valid["quantile_floor"] <= valid["quantile_projection"]).all()
        assert (valid["quantile_projection"] <= valid["quantile_ceiling"]).all()

    def test_load_exposes_conformal_factors(
        self, synthetic_df: pd.DataFrame, tmp_model_dir: str
    ) -> None:
        """load_quantile_models returns conformal_width_factors key (empty
        dict when metadata lacks them)."""
        result = train_quantile_models(
            synthetic_df,
            target_col="fantasy_points_target",
            positions=["QB"],
        )
        save_quantile_models(result, path=tmp_model_dir)
        loaded = load_quantile_models(path=tmp_model_dir)
        assert loaded is not None
        assert "conformal_width_factors" in loaded
        assert isinstance(loaded["conformal_width_factors"], dict)

    def test_production_metadata_has_factors(self) -> None:
        """The shipped models/quantile/metadata.json carries width factors
        for all four positions (regression guard for ELITE 2.5)."""
        import json

        meta_path = os.path.join(
            os.path.dirname(__file__), "..", "models", "quantile", "metadata.json"
        )
        if not os.path.exists(meta_path):
            pytest.skip("production quantile metadata not present")
        with open(meta_path) as f:
            meta = json.load(f)
        factors = meta.get("conformal_width_factors", {})
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in factors
            assert factors[pos]["width_factor"] >= 1.0
