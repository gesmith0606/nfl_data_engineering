"""Tests for production_eval.py and swap_and_eval.py.

Validates:
- summary.json is written with the correct structure
- comparison/delta logic produces correct ship verdicts
- --gate flag emits warnings
- swap-and-restore logic always restores originals (even on error)
"""

import json
import os
import shutil
import sys
import tempfile
import warnings
from typing import Dict
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Allow imports from scripts/ and src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import production_eval as pe
import swap_and_eval as sae


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_eval_dir(tmp_path, monkeypatch):
    """Redirect all eval output to a temp directory."""
    monkeypatch.setattr(pe, "EVAL_OUTPUT_DIR", str(tmp_path / "eval"))
    return tmp_path / "eval"


@pytest.fixture
def sample_results_df() -> pd.DataFrame:
    """Minimal backtest results DataFrame with one player per position."""
    rows = []
    for pos, mae_base in [("QB", 7.0), ("RB", 4.5), ("WR", 4.8), ("TE", 4.2)]:
        for i in range(10):
            projected = mae_base + np.random.default_rng(i).uniform(-1, 1)
            actual = mae_base + np.random.default_rng(i + 100).uniform(-2, 2)
            rows.append(
                {
                    "player_name": f"Player_{pos}_{i}",
                    "position": pos,
                    "projected_points": projected,
                    "actual_points": actual,
                    "error": projected - actual,
                    "abs_error": abs(projected - actual),
                    "season": 2024,
                    "week": i + 3,
                    "projection_source": "hybrid" if pos in ("WR", "TE") else "xgb",
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def baseline_summary(tmp_eval_dir) -> Dict:
    """Write a baseline summary JSON and return its dict."""
    summary = {
        "experiment": "baseline",
        "timestamp": "2026-04-07T00:00:00",
        "seasons": [2024],
        "is_gate": False,
        "overall_mae": 5.50,
        "overall_bias": -0.20,
        "position_mae": {"QB": 7.10, "RB": 4.60, "WR": 4.95, "TE": 4.30},
        "position_bias": {"QB": -0.10, "RB": -0.05, "WR": -0.30, "TE": -0.10},
        "by_source": {"hybrid": 4.62, "xgb": 5.85},
        "baseline": None,
        "delta_vs_baseline": None,
    }
    path = tmp_eval_dir / "baseline" / "summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(summary, fh)
    return summary


# ---------------------------------------------------------------------------
# Tests: _extract_metrics
# ---------------------------------------------------------------------------


class TestExtractMetrics:
    def test_returns_all_keys(self, sample_results_df):
        metrics = pe._extract_metrics(sample_results_df)
        assert "overall_mae" in metrics
        assert "overall_bias" in metrics
        assert "position_mae" in metrics
        assert "position_bias" in metrics
        assert "by_source" in metrics

    def test_overall_mae_positive(self, sample_results_df):
        metrics = pe._extract_metrics(sample_results_df)
        assert metrics["overall_mae"] > 0

    def test_position_mae_covers_all_positions(self, sample_results_df):
        metrics = pe._extract_metrics(sample_results_df)
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in metrics["position_mae"]

    def test_by_source_populated_when_column_present(self, sample_results_df):
        metrics = pe._extract_metrics(sample_results_df)
        assert len(metrics["by_source"]) > 0

    def test_by_source_empty_when_column_absent(self, sample_results_df):
        df = sample_results_df.drop(columns=["projection_source"])
        metrics = pe._extract_metrics(df)
        assert metrics["by_source"] == {}


# ---------------------------------------------------------------------------
# Tests: _save_summary and _load_summary
# ---------------------------------------------------------------------------


class TestSaveSummary:
    def test_summary_json_written(self, tmp_eval_dir, sample_results_df):
        metrics = pe._extract_metrics(sample_results_df)
        path = pe._save_summary(
            experiment_name="test_exp",
            metrics=metrics,
            seasons=[2024],
            is_gate=False,
            baseline_name=None,
            delta=None,
        )
        assert os.path.exists(path)

    def test_summary_json_structure(self, tmp_eval_dir, sample_results_df):
        metrics = pe._extract_metrics(sample_results_df)
        path = pe._save_summary(
            experiment_name="test_exp",
            metrics=metrics,
            seasons=[2024],
            is_gate=False,
            baseline_name=None,
            delta=None,
        )
        with open(path, "r") as fh:
            saved = json.load(fh)

        required_keys = [
            "experiment",
            "timestamp",
            "seasons",
            "is_gate",
            "overall_mae",
            "overall_bias",
            "position_mae",
            "position_bias",
            "by_source",
            "baseline",
            "delta_vs_baseline",
        ]
        for key in required_keys:
            assert key in saved, f"Missing key '{key}' in summary.json"

    def test_summary_values_match_metrics(self, tmp_eval_dir, sample_results_df):
        metrics = pe._extract_metrics(sample_results_df)
        pe._save_summary(
            experiment_name="val_test",
            metrics=metrics,
            seasons=[2024],
            is_gate=False,
            baseline_name="my_baseline",
            delta=None,
        )
        loaded = pe._load_summary("val_test")
        assert loaded["experiment"] == "val_test"
        assert loaded["overall_mae"] == pytest.approx(metrics["overall_mae"])
        assert loaded["baseline"] == "my_baseline"
        assert loaded["seasons"] == [2024]

    def test_load_summary_returns_none_for_missing(self, tmp_eval_dir):
        result = pe._load_summary("does_not_exist")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: _compute_delta
# ---------------------------------------------------------------------------


class TestComputeDelta:
    def _make_metrics(self, qb: float, rb: float, wr: float, te: float) -> Dict:
        return {
            "overall_mae": (qb + rb + wr + te) / 4,
            "overall_bias": 0.0,
            "position_mae": {"QB": qb, "RB": rb, "WR": wr, "TE": te},
            "position_bias": {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0},
            "by_source": {},
        }

    def test_ship_when_improvement_exceeds_threshold(self, baseline_summary):
        # Improve QB by 0.50 pts (> 0.10 threshold)
        metrics = self._make_metrics(qb=6.60, rb=4.60, wr=4.95, te=4.30)
        delta = pe._compute_delta(baseline_summary, metrics, is_gate=False)
        assert delta["QB"]["ship"] is True
        assert delta["QB"]["delta"] == pytest.approx(-0.50, abs=0.01)

    def test_no_ship_when_improvement_below_threshold(self, baseline_summary):
        # Improve QB by only 0.05 pts (< 0.10 threshold)
        metrics = self._make_metrics(qb=7.05, rb=4.60, wr=4.95, te=4.30)
        delta = pe._compute_delta(baseline_summary, metrics, is_gate=False)
        assert delta["QB"]["ship"] is False

    def test_no_ship_when_regression(self, baseline_summary):
        # WR gets worse
        metrics = self._make_metrics(qb=7.10, rb=4.60, wr=5.20, te=4.30)
        delta = pe._compute_delta(baseline_summary, metrics, is_gate=False)
        assert delta["WR"]["ship"] is False
        assert delta["WR"]["delta"] > 0

    def test_no_ship_when_bias_exceeds_iter_limit(self, baseline_summary):
        # Improve but bias too large (iter limit = 0.5)
        metrics = self._make_metrics(qb=6.60, rb=4.60, wr=4.95, te=4.30)
        metrics["position_bias"]["QB"] = 0.8  # exceeds 0.5 limit
        delta = pe._compute_delta(baseline_summary, metrics, is_gate=False)
        assert delta["QB"]["ship"] is False

    def test_no_ship_when_bias_exceeds_gate_limit(self, baseline_summary):
        # Gate has stricter bias limit (1.0 pts)
        metrics = self._make_metrics(qb=6.60, rb=4.60, wr=4.95, te=4.30)
        metrics["position_bias"]["QB"] = 1.2  # exceeds gate limit 1.0
        delta = pe._compute_delta(baseline_summary, metrics, is_gate=True)
        assert delta["QB"]["ship"] is False

    def test_ship_allowed_within_gate_bias(self, baseline_summary):
        # Improvement AND bias within gate limit
        metrics = self._make_metrics(qb=6.60, rb=4.60, wr=4.95, te=4.30)
        metrics["position_bias"]["QB"] = 0.9  # within 1.0 gate limit
        delta = pe._compute_delta(baseline_summary, metrics, is_gate=True)
        assert delta["QB"]["ship"] is True

    def test_all_positions_returned(self, baseline_summary):
        metrics = self._make_metrics(qb=7.10, rb=4.60, wr=4.95, te=4.30)
        delta = pe._compute_delta(baseline_summary, metrics, is_gate=False)
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in delta


# ---------------------------------------------------------------------------
# Tests: gate warning
# ---------------------------------------------------------------------------


class TestGateWarning:
    def test_gate_flag_emits_user_warning(self, tmp_eval_dir, sample_results_df):
        """--gate flag must print a warning about single-use semantics."""
        with patch(
            "production_eval.run_backtest", return_value=sample_results_df
        ):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                pe.run_experiment(
                    experiment_name="gate_test",
                    seasons=[2024],
                    weeks=None,
                    scoring_format="half_ppr",
                    baseline_name=None,
                    is_gate=True,
                    use_ml=True,
                    full_features=False,
                )
            assert any("SEALED" in str(w.message) for w in caught), (
                "Expected a warning containing 'SEALED' when --gate is active"
            )

    def test_no_gate_warning_without_flag(self, tmp_eval_dir, sample_results_df):
        """Without --gate, no SEALED warning should be emitted."""
        with patch(
            "production_eval.run_backtest", return_value=sample_results_df
        ):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                pe.run_experiment(
                    experiment_name="no_gate_test",
                    seasons=[2024],
                    weeks=None,
                    scoring_format="half_ppr",
                    baseline_name=None,
                    is_gate=False,
                    use_ml=True,
                    full_features=False,
                )
            assert not any("SEALED" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# Tests: run_experiment writes summary.json
# ---------------------------------------------------------------------------


class TestRunExperiment:
    def test_summary_json_created(self, tmp_eval_dir, sample_results_df):
        with patch(
            "production_eval.run_backtest", return_value=sample_results_df
        ):
            result = pe.run_experiment(
                experiment_name="my_exp",
                seasons=[2024],
                weeks=None,
                scoring_format="half_ppr",
                baseline_name=None,
                is_gate=False,
                use_ml=True,
                full_features=False,
            )
        summary_path = tmp_eval_dir / "my_exp" / "summary.json"
        assert summary_path.exists()
        assert result["experiment"] == "my_exp"

    def test_summary_json_includes_delta_when_baseline_exists(
        self, tmp_eval_dir, sample_results_df, baseline_summary
    ):
        with patch(
            "production_eval.run_backtest", return_value=sample_results_df
        ):
            result = pe.run_experiment(
                experiment_name="candidate_exp",
                seasons=[2024],
                weeks=None,
                scoring_format="half_ppr",
                baseline_name="baseline",
                is_gate=False,
                use_ml=True,
                full_features=False,
            )
        assert result["delta_vs_baseline"] is not None
        delta = result["delta_vs_baseline"]
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in delta
            assert "ship" in delta[pos]

    def test_missing_baseline_does_not_crash(self, tmp_eval_dir, sample_results_df):
        with patch(
            "production_eval.run_backtest", return_value=sample_results_df
        ):
            result = pe.run_experiment(
                experiment_name="orphan_exp",
                seasons=[2024],
                weeks=None,
                scoring_format="half_ppr",
                baseline_name="nonexistent_baseline",
                is_gate=False,
                use_ml=True,
                full_features=False,
            )
        assert result["delta_vs_baseline"] is None


# ---------------------------------------------------------------------------
# Tests: compare_experiments
# ---------------------------------------------------------------------------


class TestCompareExperiments:
    def test_compare_exits_on_missing_experiment(self, tmp_eval_dir):
        with pytest.raises(SystemExit):
            pe.compare_experiments("does_not_exist_1", "does_not_exist_2")

    def test_compare_prints_table(
        self, tmp_eval_dir, sample_results_df, baseline_summary, capsys
    ):
        # Write a second experiment
        metrics = pe._extract_metrics(sample_results_df)
        pe._save_summary(
            experiment_name="exp2",
            metrics=metrics,
            seasons=[2024],
            is_gate=False,
            baseline_name=None,
            delta=None,
        )
        pe.compare_experiments("baseline", "exp2")
        captured = capsys.readouterr()
        assert "COMPARISON" in captured.out
        assert "baseline" in captured.out
        assert "exp2" in captured.out


# ---------------------------------------------------------------------------
# Tests: swap-and-restore (mock file system)
# ---------------------------------------------------------------------------


class TestSwapAndRestore:
    """Verify that swap_and_eval always restores original model files."""

    def _make_joblib_file(self, path: str, content: bytes = b"original") -> None:
        """Write a dummy model file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(content)

    def test_restore_on_success(self, tmp_path, monkeypatch):
        """Original model is restored after successful PFE run."""
        # Setup fake residual dir
        residual_dir = tmp_path / "models" / "residual"
        residual_dir.mkdir(parents=True)
        prod_model = residual_dir / "wr_residual.joblib"
        prod_model.write_bytes(b"production_content")

        candidate = tmp_path / "candidate.joblib"
        candidate.write_bytes(b"candidate_content")

        monkeypatch.setattr(sae, "RESIDUAL_DIR", str(residual_dir))
        monkeypatch.setattr(sae, "BACKUP_DIR", str(tmp_path / "backup"))

        # Patch subprocess to simulate successful eval
        with patch("swap_and_eval.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # Patch summary load so we don't need real output
            with patch("swap_and_eval._load_eval_summary", return_value=None):
                sae.swap_and_eval(
                    position="wr",
                    candidate_model=str(candidate),
                    experiment_name="test_swap",
                    seasons=[2024],
                )

        # Original content must be restored
        assert prod_model.read_bytes() == b"production_content"

    def test_restore_on_subprocess_failure(self, tmp_path, monkeypatch):
        """Original model is restored even when PFE subprocess fails."""
        residual_dir = tmp_path / "models" / "residual"
        residual_dir.mkdir(parents=True)
        prod_model = residual_dir / "rb_residual.joblib"
        prod_model.write_bytes(b"rb_original")

        candidate = tmp_path / "rb_candidate.joblib"
        candidate.write_bytes(b"rb_candidate")

        monkeypatch.setattr(sae, "RESIDUAL_DIR", str(residual_dir))
        monkeypatch.setattr(sae, "BACKUP_DIR", str(tmp_path / "backup"))

        with patch("swap_and_eval.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with patch("swap_and_eval._load_eval_summary", return_value=None):
                returncode = sae.swap_and_eval(
                    position="rb",
                    candidate_model=str(candidate),
                    experiment_name="rb_fail_test",
                    seasons=[2024],
                )

        assert returncode == 1, "Should propagate failure returncode"
        assert prod_model.read_bytes() == b"rb_original"

    def test_restore_on_exception_during_eval(self, tmp_path, monkeypatch):
        """Original model is restored even when _run_production_eval raises."""
        residual_dir = tmp_path / "models" / "residual"
        residual_dir.mkdir(parents=True)
        prod_model = residual_dir / "te_residual.joblib"
        prod_model.write_bytes(b"te_original")

        candidate = tmp_path / "te_candidate.joblib"
        candidate.write_bytes(b"te_candidate")

        monkeypatch.setattr(sae, "RESIDUAL_DIR", str(residual_dir))
        monkeypatch.setattr(sae, "BACKUP_DIR", str(tmp_path / "backup"))

        def _raise(*args, **kwargs):
            raise RuntimeError("simulated eval crash")

        with patch("swap_and_eval._run_production_eval", side_effect=_raise):
            with pytest.raises(RuntimeError):
                sae.swap_and_eval(
                    position="te",
                    candidate_model=str(candidate),
                    experiment_name="te_crash_test",
                    seasons=[2024],
                )

        assert prod_model.read_bytes() == b"te_original"

    def test_restore_when_no_original_exists(self, tmp_path, monkeypatch):
        """When production model didn't exist before swap, it is removed on restore."""
        residual_dir = tmp_path / "models" / "residual"
        residual_dir.mkdir(parents=True)
        prod_model = residual_dir / "qb_residual.joblib"
        # Intentionally DO NOT create prod_model — no pre-existing file

        candidate = tmp_path / "qb_candidate.joblib"
        candidate.write_bytes(b"qb_candidate")

        monkeypatch.setattr(sae, "RESIDUAL_DIR", str(residual_dir))
        monkeypatch.setattr(sae, "BACKUP_DIR", str(tmp_path / "backup"))

        with patch("swap_and_eval.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("swap_and_eval._load_eval_summary", return_value=None):
                sae.swap_and_eval(
                    position="qb",
                    candidate_model=str(candidate),
                    experiment_name="qb_noexist_test",
                    seasons=[2024],
                )

        # Production file should not exist after restore (nothing to restore to)
        assert not prod_model.exists()

    def test_companion_files_also_restored(self, tmp_path, monkeypatch):
        """Imputer and meta companion files are also restored after swap."""
        residual_dir = tmp_path / "models" / "residual"
        residual_dir.mkdir(parents=True)

        prod_model = residual_dir / "wr_residual.joblib"
        prod_imputer = residual_dir / "wr_residual_imputer.joblib"
        prod_meta = residual_dir / "wr_residual_meta.json"

        prod_model.write_bytes(b"wr_model_original")
        prod_imputer.write_bytes(b"wr_imputer_original")
        prod_meta.write_text('{"original": true}')

        candidate_model = tmp_path / "wr_candidate.joblib"
        candidate_model.write_bytes(b"wr_model_candidate")
        candidate_imputer = tmp_path / "wr_imputer_candidate.joblib"
        candidate_imputer.write_bytes(b"wr_imputer_candidate")
        candidate_meta = tmp_path / "wr_meta_candidate.json"
        candidate_meta.write_text('{"candidate": true}')

        monkeypatch.setattr(sae, "RESIDUAL_DIR", str(residual_dir))
        monkeypatch.setattr(sae, "BACKUP_DIR", str(tmp_path / "backup"))

        with patch("swap_and_eval.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("swap_and_eval._load_eval_summary", return_value=None):
                sae.swap_and_eval(
                    position="wr",
                    candidate_model=str(candidate_model),
                    experiment_name="wr_full_swap",
                    candidate_imputer=str(candidate_imputer),
                    candidate_meta=str(candidate_meta),
                    seasons=[2024],
                )

        assert prod_model.read_bytes() == b"wr_model_original"
        assert prod_imputer.read_bytes() == b"wr_imputer_original"
        assert json.loads(prod_meta.read_text()) == {"original": True}

    def test_candidate_not_found_raises(self, tmp_path, monkeypatch):
        """FileNotFoundError is raised immediately if candidate does not exist."""
        residual_dir = tmp_path / "models" / "residual"
        residual_dir.mkdir(parents=True)
        monkeypatch.setattr(sae, "RESIDUAL_DIR", str(residual_dir))
        monkeypatch.setattr(sae, "BACKUP_DIR", str(tmp_path / "backup"))

        with pytest.raises(FileNotFoundError):
            sae.swap_and_eval(
                position="wr",
                candidate_model=str(tmp_path / "nonexistent.joblib"),
                experiment_name="should_not_run",
                seasons=[2024],
            )

    def test_invalid_position_raises(self, tmp_path, monkeypatch):
        """ValueError is raised for an unrecognized position string."""
        residual_dir = tmp_path / "models" / "residual"
        residual_dir.mkdir(parents=True)
        monkeypatch.setattr(sae, "RESIDUAL_DIR", str(residual_dir))

        candidate = tmp_path / "model.joblib"
        candidate.write_bytes(b"x")

        with pytest.raises(ValueError, match="Unknown position"):
            sae.swap_and_eval(
                position="kicker",
                candidate_model=str(candidate),
                experiment_name="bad_pos",
                seasons=[2024],
            )


# ---------------------------------------------------------------------------
# Tests: backup_tag and production_path helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_backup_tag_format(self):
        tag = sae._backup_tag()
        # Should be YYYYMMDD_HHMMSS
        assert len(tag) == 15
        assert tag[8] == "_"

    def test_production_path_model(self):
        path = sae._production_path("wr", "model")
        assert path.endswith("wr_residual.joblib")

    def test_production_path_imputer(self):
        path = sae._production_path("qb", "imputer")
        assert path.endswith("qb_residual_imputer.joblib")

    def test_production_path_meta(self):
        path = sae._production_path("te", "meta")
        assert path.endswith("te_residual_meta.json")

    def test_production_path_invalid_type_raises(self):
        with pytest.raises(ValueError):
            sae._production_path("wr", "unknown_type")

    def test_production_path_invalid_position_raises(self):
        with pytest.raises(ValueError):
            sae._production_path("dt", "model")
