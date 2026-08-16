"""Tests for scripts/check_model_freshness.py — model staleness invariant gate.

Covers the exact mechanism from MODEL_REVIEW_2026_08_15.md finding #1
(frozen SimpleImputer permanently drops all-NaN-at-fit columns from every
future transform(), even after the live data is repaired), the finding #6
verdict that the ensemble Ridge meta-learner has no such imputer at all, the
finding #2/#11 staleness proxy, and bayesian's WARN-only tier (finding #14).
"""

import json
import os
import pickle
import sys
from datetime import datetime, timedelta, timezone
from unittest import mock

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import check_model_freshness as cmf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fit_imputer(matrix) -> SimpleImputer:
    import warnings

    imp = SimpleImputer(strategy="median")
    with warnings.catch_warnings():
        # sklearn warns when a column is all-NaN at fit time -- that's the
        # exact condition these fixtures are constructing on purpose.
        warnings.simplefilter("ignore", UserWarning)
        imp.fit(np.array(matrix, dtype=float))
    return imp


def _clean_imputer(n_features=3) -> SimpleImputer:
    rows = [[float(i + j) for j in range(n_features)] for i in range(5)]
    return _fit_imputer(rows)


def _nan_stat_imputer(n_features=3, nan_col_idx=(0,)) -> SimpleImputer:
    """Imputer with one or more columns entirely NaN at fit time."""
    rows = []
    for i in range(5):
        row = [float(i + j) for j in range(n_features)]
        for idx in nan_col_idx:
            row[idx] = np.nan
        rows.append(row)
    return _fit_imputer(rows)


# ---------------------------------------------------------------------------
# check_imputer_nan
# ---------------------------------------------------------------------------


class TestCheckImputerNan:
    def test_none_imputer_passes(self):
        r = cmf.check_imputer_nan("x", None, tier="FAIL")
        assert r.passed is True
        assert r.tier == "FAIL"

    def test_clean_imputer_passes(self):
        imp = _clean_imputer()
        r = cmf.check_imputer_nan("x", imp, tier="FAIL")
        assert r.passed is True

    def test_nan_stat_imputer_fails(self):
        imp = _nan_stat_imputer(n_features=3, nan_col_idx=(1,))
        r = cmf.check_imputer_nan("x", imp, tier="FAIL")
        assert r.passed is False
        assert r.tier == "FAIL"
        assert "1/3" in r.message

    def test_multiple_nan_stats_counted(self):
        imp = _nan_stat_imputer(n_features=4, nan_col_idx=(0, 2))
        r = cmf.check_imputer_nan("x", imp, tier="FAIL")
        assert r.passed is False
        assert "2/4" in r.message

    def test_object_without_statistics_fails(self):
        class NotAnImputer:
            pass

        r = cmf.check_imputer_nan("x", NotAnImputer(), tier="FAIL")
        assert r.passed is False

    def test_warn_tier_respected_on_failure(self):
        imp = _nan_stat_imputer(n_features=2, nan_col_idx=(0,))
        r = cmf.check_imputer_nan("x", imp, tier="WARN")
        assert r.passed is False
        assert r.tier == "WARN"


# ---------------------------------------------------------------------------
# check_feature_coverage
# ---------------------------------------------------------------------------


class TestCheckFeatureCoverage:
    def test_no_meta_features_skips_both(self):
        results = cmf.check_feature_coverage("x", [], None, {"a", "b"}, tier="FAIL")
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_live_columns_none_skips_both(self):
        results = cmf.check_feature_coverage("x", ["a", "b"], None, None, tier="FAIL")
        assert len(results) == 2
        assert all(r.passed for r in results)
        assert all(r.tier == "WARN" for r in results)

    def test_feature_dropped_by_imputer_and_live_is_a_fail(self):
        # feature "a" is index 0, all-NaN at fit -> NaN statistic; it IS
        # present in the live schema right now -> should FAIL (finding #1).
        imp = _nan_stat_imputer(n_features=2, nan_col_idx=(0,))
        features = ["a", "b"]
        live_cols = {"a", "b"}
        results = cmf.check_feature_coverage("x", features, imp, live_cols, tier="FAIL")
        dropped = next(r for r in results if r.id == "x/dropped")
        assert dropped.passed is False
        assert dropped.tier == "FAIL"
        assert "a" in dropped.message

    def test_feature_dropped_by_imputer_but_not_live_does_not_fail(self):
        # NaN stat exists, but the feature isn't present live -> not a live
        # regression (it's just an old/retired feature) -> dropped passes.
        imp = _nan_stat_imputer(n_features=2, nan_col_idx=(0,))
        features = ["a", "b"]
        live_cols = {"b"}  # "a" absent live
        results = cmf.check_feature_coverage("x", features, imp, live_cols, tier="FAIL")
        dropped = next(r for r in results if r.id == "x/dropped")
        assert dropped.passed is True

    def test_missing_from_live_schema_warns_on_coverage_only(self):
        imp = _clean_imputer(n_features=2)
        features = ["a", "b"]
        live_cols = {"a"}  # "b" missing entirely
        results = cmf.check_feature_coverage("x", features, imp, live_cols, tier="FAIL")
        dropped = next(r for r in results if r.id == "x/dropped")
        coverage = next(r for r in results if r.id == "x/live_coverage")
        assert dropped.passed is True
        assert coverage.passed is False
        assert coverage.tier == "WARN"
        assert "b" in coverage.message

    def test_all_present_and_clean_passes_both(self):
        imp = _clean_imputer(n_features=2)
        features = ["a", "b"]
        live_cols = {"a", "b"}
        results = cmf.check_feature_coverage("x", features, imp, live_cols, tier="FAIL")
        assert all(r.passed for r in results)


# ---------------------------------------------------------------------------
# check_staleness
# ---------------------------------------------------------------------------


class TestCheckStaleness:
    def test_no_silver_data_skips(self):
        r = cmf.check_staleness("x", "2026-01-01T00:00:00Z", None)
        assert r.passed is True
        assert r.tier == "WARN"

    def test_no_trained_at_fails(self):
        r = cmf.check_staleness("x", None, datetime.now(timezone.utc))
        assert r.passed is False
        assert r.tier == "WARN"

    def test_stale_artifact_warns(self):
        newest = datetime.now(timezone.utc)
        old = (newest - timedelta(days=30)).isoformat()
        r = cmf.check_staleness("x", old, newest)
        assert r.passed is False

    def test_fresh_artifact_passes(self):
        newest = datetime.now(timezone.utc) - timedelta(days=30)
        fresh = datetime.now(timezone.utc).isoformat()
        r = cmf.check_staleness("x", fresh, newest)
        assert r.passed is True

    def test_unparseable_timestamp_fails(self):
        r = cmf.check_staleness("x", "not-a-date", datetime.now(timezone.utc))
        assert r.passed is False

    def test_proxy_used_noted_in_message(self):
        newest = datetime.now(timezone.utc)
        old = (newest - timedelta(days=1)).isoformat()
        r = cmf.check_staleness("x", old, newest, proxy_used=True)
        assert "proxy" in r.message


# ---------------------------------------------------------------------------
# residual_family_results
# ---------------------------------------------------------------------------


class TestResidualFamilyResults:
    def _write_lgb_artifact(self, models_dir, pos, imputer):
        os.makedirs(models_dir, exist_ok=True)
        joblib.dump({"dummy": "model"}, models_dir / f"{pos}_residual.joblib")
        joblib.dump(imputer, models_dir / f"{pos}_residual_imputer.joblib")
        meta = {
            "position": pos.upper(),
            "model_type": "lgb_v2",
            "features": ["a", "b", "c"],
        }
        with open(models_dir / f"{pos}_residual_meta.json", "w") as f:
            json.dump(meta, f)

    def _write_ridge_artifact(self, models_dir, pos, imputer):
        os.makedirs(models_dir, exist_ok=True)
        pipe = Pipeline([("imputer", imputer), ("model", Ridge())])
        # Fit the Ridge step trivially so the pipeline is a realistic object
        X = np.nan_to_num(imputer.transform(np.zeros((3, imputer.n_features_in_))))
        pipe.named_steps["model"].fit(X, [0, 1, 2])
        joblib.dump(pipe, models_dir / f"{pos}_residual.joblib")
        meta = {"position": pos.upper(), "model_type": "ridge", "features": ["a", "b", "c"]}
        with open(models_dir / f"{pos}_residual_meta.json", "w") as f:
            json.dump(meta, f)

    def test_missing_artifact_is_fail(self, tmp_path):
        models_dir = tmp_path / "residual"
        os.makedirs(models_dir)
        results = cmf.residual_family_results(models_dir, None, None)
        # every position missing -> one artifact FAIL each
        artifact_fails = [r for r in results if r.id.endswith("/artifact")]
        assert len(artifact_fails) == len(cmf.POSITIONS)
        assert all(not r.passed and r.tier == "FAIL" for r in artifact_fails)

    def test_lgb_clean_imputer_passes(self, tmp_path):
        models_dir = tmp_path / "residual"
        self._write_lgb_artifact(models_dir, "qb", _clean_imputer(3))
        results = cmf.residual_family_results(models_dir, None, None)
        nan_check = next(r for r in results if r.id == "residual/qb/imputer_nan")
        assert nan_check.passed is True

    def test_lgb_nan_imputer_fails(self, tmp_path):
        models_dir = tmp_path / "residual"
        self._write_lgb_artifact(models_dir, "rb", _nan_stat_imputer(3, (0,)))
        results = cmf.residual_family_results(models_dir, None, None)
        nan_check = next(r for r in results if r.id == "residual/rb/imputer_nan")
        assert nan_check.passed is False
        assert nan_check.tier == "FAIL"

    def test_ridge_pipeline_imputer_is_extracted_and_checked(self, tmp_path):
        models_dir = tmp_path / "residual"
        self._write_ridge_artifact(models_dir, "wr", _nan_stat_imputer(3, (1,)))
        results = cmf.residual_family_results(models_dir, None, None)
        nan_check = next(r for r in results if r.id == "residual/wr/imputer_nan")
        assert nan_check.passed is False

    def test_missing_trained_at_falls_back_to_mtime_proxy(self, tmp_path):
        models_dir = tmp_path / "residual"
        self._write_lgb_artifact(models_dir, "te", _clean_imputer(3))
        results = cmf.residual_family_results(models_dir, None, None)
        staleness = next(r for r in results if r.id == "residual/te/staleness")
        # No silver_newest given -> skipped, but should not raise regardless
        assert staleness.tier == "WARN"


# ---------------------------------------------------------------------------
# quantile_family_results
# ---------------------------------------------------------------------------


class TestQuantileFamilyResults:
    def test_missing_metadata_is_fail(self, tmp_path):
        models_dir = tmp_path / "quantile"
        os.makedirs(models_dir)
        results = cmf.quantile_family_results(models_dir, None, None)
        assert len(results) == 1
        assert results[0].tier == "FAIL"
        assert results[0].passed is False

    def test_reproduces_finding_1_shape(self, tmp_path):
        """A shared imputer with NaN stats for features that ARE present
        live must FAIL both the raw NaN check and the dropped-but-live check
        -- this is the exact empirically-confirmed finding #1 shape.
        """
        models_dir = tmp_path / "quantile"
        os.makedirs(models_dir)
        imp = _nan_stat_imputer(n_features=3, nan_col_idx=(2,))
        with open(models_dir / "imputer.pkl", "wb") as f:
            pickle.dump(imp, f)
        meta = {
            "feature_cols": ["age", "snap_pct_roll3", "college_market_share"],
            "created_at": "2026-06-12T09:53:11.814206",
        }
        with open(models_dir / "metadata.json", "w") as f:
            json.dump(meta, f)

        live_cols = {"age", "snap_pct_roll3", "college_market_share"}
        results = cmf.quantile_family_results(models_dir, live_cols, None)

        nan_check = next(r for r in results if r.id == "quantile/imputer_nan")
        dropped_check = next(r for r in results if r.id == "quantile/features/dropped")
        assert nan_check.passed is False
        assert dropped_check.passed is False
        assert "college_market_share" in dropped_check.message


# ---------------------------------------------------------------------------
# ensemble_family_results — finding #6 verdict
# ---------------------------------------------------------------------------


class TestEnsembleFamilyResults:
    def test_missing_meta_learner_is_fail(self, tmp_path):
        models_dir = tmp_path / "ensemble"
        os.makedirs(models_dir)
        results = cmf.ensemble_family_results(models_dir, None)
        fails = [r for r in results if r.id.endswith("/meta_learner")]
        assert len(fails) == 2  # spread + total
        assert all(not r.passed for r in fails)

    def test_no_imputer_artifact_verdict_is_a_pass(self, tmp_path):
        """Finding #6: the ensemble meta-learner has no frozen imputer at
        all -- verify the checker reports this as an explicit, passing N/A
        rather than silently omitting the check.
        """
        models_dir = tmp_path / "ensemble"
        os.makedirs(models_dir)
        ridge = Ridge()
        ridge.fit(np.random.rand(10, 3), np.random.rand(10))
        joblib.dump(ridge, models_dir / "ridge_spread.pkl")
        joblib.dump(ridge, models_dir / "ridge_total.pkl")

        results = cmf.ensemble_family_results(models_dir, None)
        imputer_checks = [r for r in results if r.id.endswith("/imputer_nan")]
        assert len(imputer_checks) == 2
        assert all(r.passed for r in imputer_checks)
        assert all("N/A" in r.message for r in imputer_checks)

    def test_meta_learner_shape_mismatch_fails(self, tmp_path):
        models_dir = tmp_path / "ensemble"
        os.makedirs(models_dir)
        ridge = Ridge()
        # 5 base predictions instead of the expected 3 -- shape drift
        ridge.fit(np.random.rand(10, 5), np.random.rand(10))
        joblib.dump(ridge, models_dir / "ridge_spread.pkl")
        joblib.dump(ridge, models_dir / "ridge_total.pkl")

        results = cmf.ensemble_family_results(models_dir, None)
        shape_checks = [r for r in results if r.id.endswith("/meta_shape")]
        assert all(not r.passed for r in shape_checks)

    def test_uses_real_trained_at_from_metadata(self, tmp_path):
        models_dir = tmp_path / "ensemble"
        os.makedirs(models_dir)
        with open(models_dir / "metadata.json", "w") as f:
            json.dump({"trained_at": "2026-06-10T02:36:12.791577Z"}, f)

        newest = datetime.now(timezone.utc)
        results = cmf.ensemble_family_results(models_dir, newest)
        staleness = next(r for r in results if r.id == "ensemble/staleness")
        assert staleness.passed is False  # 2026-06-10 predates "now"


# ---------------------------------------------------------------------------
# bayesian_family_results — WARN-only tier (finding #14)
# ---------------------------------------------------------------------------


class MockBayesianModel:
    """Minimal stand-in for bayesian_projection.BayesianResidualModel."""

    def __init__(self, imputer, feature_names):
        self.pipeline = Pipeline([("imputer", imputer), ("model", Ridge())])
        X = np.nan_to_num(imputer.transform(np.zeros((3, imputer.n_features_in_))))
        self.pipeline.named_steps["model"].fit(X, [0, 1, 2])
        self.feature_names = feature_names


class TestBayesianFamilyResults:
    def test_missing_artifact_is_warn_not_fail(self, tmp_path):
        models_dir = tmp_path / "bayesian"
        os.makedirs(models_dir)
        results = cmf.bayesian_family_results(models_dir, None, None)
        artifact_checks = [r for r in results if r.id.endswith("/artifact")]
        assert len(artifact_checks) == len(cmf.POSITIONS)
        assert all(r.tier == "WARN" for r in artifact_checks)
        assert all(not r.passed for r in artifact_checks)

    def test_nan_imputer_is_warn_tier_not_fail(self, tmp_path):
        models_dir = tmp_path / "bayesian"
        os.makedirs(models_dir)
        imp = _nan_stat_imputer(n_features=3, nan_col_idx=(0,))
        model = MockBayesianModel(imp, ["a", "b", "c"])
        joblib.dump(model, models_dir / "bayesian_qb.joblib")
        with open(models_dir / "bayesian_qb_meta.json", "w") as f:
            json.dump({"position": "QB"}, f)

        results = cmf.bayesian_family_results(models_dir, None, None)
        nan_check = next(r for r in results if r.id == "bayesian/qb/imputer_nan")
        assert nan_check.tier == "WARN"
        assert nan_check.passed is False

        # Every single result in this family must be WARN tier, never FAIL.
        assert all(r.tier == "WARN" for r in results)


# ---------------------------------------------------------------------------
# find_newest_silver_timestamp
# ---------------------------------------------------------------------------


class TestFindNewestSilverTimestamp:
    def test_missing_silver_dir_returns_none(self, tmp_path):
        result = cmf.find_newest_silver_timestamp(tmp_path)
        assert result is None

    def test_finds_newest_file_mtime(self, tmp_path):
        silver = tmp_path / "silver" / "players" / "usage"
        os.makedirs(silver)
        pd.DataFrame({"a": [1]}).to_parquet(silver / "f.parquet", index=False)
        result = cmf.find_newest_silver_timestamp(tmp_path)
        assert result is not None
        assert isinstance(result, datetime)


# ---------------------------------------------------------------------------
# probe_live_feature_columns — best-effort, never raises
# ---------------------------------------------------------------------------


class TestProbeLiveFeatureColumns:
    def test_empty_frame_returns_none(self, monkeypatch):
        import player_feature_engineering as pfe

        monkeypatch.setattr(pfe, "assemble_player_features", lambda season: pd.DataFrame())
        result = cmf.probe_live_feature_columns(season=2025)
        assert result is None

    def test_exception_during_assembly_returns_none(self, monkeypatch):
        import player_feature_engineering as pfe

        def _raise(season):
            raise RuntimeError("no local Silver data")

        monkeypatch.setattr(pfe, "assemble_player_features", _raise)
        result = cmf.probe_live_feature_columns(season=2025)
        assert result is None

    def test_nonempty_frame_returns_columns(self, monkeypatch):
        import player_feature_engineering as pfe

        df = pd.DataFrame({"player_id": ["a"], "feat_a": [1.0], "feat_b": [2.0]})
        monkeypatch.setattr(pfe, "assemble_player_features", lambda season: df)
        monkeypatch.setattr(pfe, "get_player_feature_columns", lambda d: ["feat_a", "feat_b"])
        result = cmf.probe_live_feature_columns(season=2025)
        assert result == {"feat_a", "feat_b"}


# ---------------------------------------------------------------------------
# print_report — exit code aggregation
# ---------------------------------------------------------------------------


class TestPrintReport:
    def test_fail_tier_miss_exits_1(self, capsys):
        results = [cmf.CheckResult(id="a", tier="FAIL", passed=False, message="bad")]
        code = cmf.print_report(results)
        assert code == 1
        assert "FAIL" in capsys.readouterr().out

    def test_warn_tier_miss_exits_0(self, capsys):
        results = [cmf.CheckResult(id="a", tier="WARN", passed=False, message="meh")]
        code = cmf.print_report(results)
        assert code == 0
        out = capsys.readouterr().out
        assert "Overall: PASS" in out

    def test_all_pass_exits_0(self, capsys):
        results = [
            cmf.CheckResult(id="a", tier="FAIL", passed=True, message="ok"),
            cmf.CheckResult(id="b", tier="WARN", passed=True, message="ok"),
        ]
        code = cmf.print_report(results)
        assert code == 0
        assert "Overall: PASS" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run_checks — end-to-end against the real repo's models/ directory
# ---------------------------------------------------------------------------


class TestRunChecksRealRepo:
    def test_runs_without_raising_against_real_models_dir(self):
        # probe=False keeps this fast and independent of local Silver data.
        results = cmf.run_checks(probe=False)
        assert len(results) > 0
        assert all(isinstance(r, cmf.CheckResult) for r in results)

    def test_all_four_families_produce_results(self):
        # Deliberately not pinning exact PASS/FAIL counts here: this repo
        # has multiple workstreams retraining models/quantile and
        # models/residual concurrently (see MODEL_FRESHNESS_GUARDS.md for
        # the point-in-time verdict), so hardcoding today's pass/fail state
        # would make this test flaky by design. What must always hold is
        # structural: every family produces at least one imputer_nan check.
        results = cmf.run_checks(probe=False)
        ids = {r.id for r in results}
        for family in ("residual/qb", "residual/rb", "residual/wr", "residual/te", "quantile", "bayesian/qb"):
            assert f"{family}/imputer_nan" in ids
        assert "ensemble/spread/imputer_nan" in ids
        assert "ensemble/total/imputer_nan" in ids

    def test_ensemble_family_never_flags_a_missing_imputer(self):
        # Finding #6's verdict (no frozen imputer artifact exists in this
        # family) is a structural fact about the code, not about today's
        # artifact contents -- safe to pin.
        results = cmf.run_checks(probe=False)
        for check_id in ("ensemble/spread/imputer_nan", "ensemble/total/imputer_nan"):
            r = next(x for x in results if x.id == check_id)
            assert r.passed is True
            assert "N/A" in r.message
