"""Tests for scripts/check_ml_output.py — ML output sanity gate.

Covers:
  - Missing Gold file → failure
  - Non-trivial row count check
  - Hybrid positions present (when model files exist)
  - All-zero position detection
  - Clean pass path with valid hybrid output
"""

import os
import sys
import tempfile
import json
from typing import Optional
from unittest import mock

import pandas as pd
import pytest

# Make scripts/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_ml_output as cml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_projection_df(
    n_qb: int = 5,
    n_rb: int = 20,
    n_wr: int = 40,
    n_te: int = 20,
    wr_source: str = "hybrid",
    te_source: str = "hybrid",
    all_zero_position: Optional[str] = None,
) -> pd.DataFrame:
    """Build a minimal projection DataFrame for testing.

    Args:
        n_qb / n_rb / n_wr / n_te: Player counts per position.
        wr_source: projection_source value for WR rows.
        te_source: projection_source value for TE rows.
        all_zero_position: If set, zero out projected_points for that position.

    Returns:
        DataFrame matching the Gold weekly projection schema.
    """
    rows = []
    for pos, count, src in [
        ("QB", n_qb, "heuristic"),
        ("RB", n_rb, "heuristic"),
        ("WR", n_wr, wr_source),
        ("TE", n_te, te_source),
    ]:
        for i in range(count):
            pts = 10.0 + i * 0.5
            if all_zero_position and pos == all_zero_position:
                pts = 0.0
            rows.append(
                {
                    "player_id": f"{pos}_{i:04d}",
                    "player_name": f"{pos} Player {i}",
                    "position": pos,
                    "recent_team": "KC",
                    "projected_points": pts,
                    "is_bye_week": False,
                    "projection_source": src,
                    "week": 5,
                }
            )
    return pd.DataFrame(rows)


def _write_gold(df: pd.DataFrame, tmpdir: str, season: int, week: int, scoring: str) -> str:
    """Write a projection DataFrame to the expected Gold path in tmpdir.

    Returns:
        Absolute path to the written parquet file.
    """
    gold_dir = os.path.join(
        tmpdir, "data", "gold", f"projections/season={season}/week={week}"
    )
    os.makedirs(gold_dir, exist_ok=True)
    path = os.path.join(gold_dir, f"projections_{scoring}_20260612_120000.parquet")
    df.to_parquet(path, index=False)
    return path


def _write_residual_meta(tmpdir: str, position: str) -> None:
    """Create a stub residual joblib + meta in tmpdir/models/residual/."""
    residual_dir = os.path.join(tmpdir, "models", "residual")
    os.makedirs(residual_dir, exist_ok=True)
    # Stub joblib (non-empty bytes so os.path.exists returns True)
    joblib_path = os.path.join(residual_dir, f"{position.lower()}_residual.joblib")
    with open(joblib_path, "wb") as fh:
        fh.write(b"stub")
    meta_path = os.path.join(residual_dir, f"{position.lower()}_residual_meta.json")
    with open(meta_path, "w") as fh:
        json.dump({"heuristic_version": "v4.2+blend", "position": position}, fh)


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


def _patch_paths(tmpdir: str):
    """Context manager patching that redirects GOLD_DIR and PROJECT_ROOT."""
    return mock.patch.multiple(
        cml,
        GOLD_DIR=os.path.join(tmpdir, "data", "gold"),
        PROJECT_ROOT=tmpdir,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFindLatestGold:
    """Tests for the _find_latest_gold helper."""

    def test_returns_empty_when_no_files(self, tmp_path):
        with _patch_paths(str(tmp_path)):
            result = cml._find_latest_gold(2026, 5, "half_ppr")
        assert result == ""

    def test_returns_latest_file(self, tmp_path):
        df = _make_projection_df()
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        with _patch_paths(str(tmp_path)):
            result = cml._find_latest_gold(2026, 5, "half_ppr")
        assert result.endswith(".parquet")
        assert "projections_half_ppr" in result


class TestRunChecks:
    """Tests for run_checks() covering all four invariants."""

    def test_check1_missing_file_is_failure(self, tmp_path):
        with _patch_paths(str(tmp_path)):
            failures, warnings = cml.run_checks(2026, 5, "half_ppr")
        assert any("CHECK1" in f for f in failures)

    def test_check2_too_few_rows_is_failure(self, tmp_path):
        # Write only 5 rows (< _MIN_ROWS=50)
        df = _make_projection_df(n_qb=1, n_rb=1, n_wr=2, n_te=1)
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert any("CHECK2" in f for f in failures)

    def test_check3_hybrid_absent_when_model_exists_is_failure(self, tmp_path):
        # Write full-size output with heuristic-only WR/TE, but model stubs present
        df = _make_projection_df(wr_source="heuristic", te_source="heuristic")
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        _write_residual_meta(str(tmp_path), "WR")
        _write_residual_meta(str(tmp_path), "TE")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert any("CHECK3" in f for f in failures)

    def test_check3_hybrid_absent_when_no_model_is_ok(self, tmp_path):
        # All-heuristic output is fine when model files are NOT present
        df = _make_projection_df(wr_source="heuristic", te_source="heuristic")
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        # Do NOT write residual model stubs
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert not any("CHECK3" in f for f in failures)

    def test_check4_all_zero_wr_is_failure(self, tmp_path):
        df = _make_projection_df(all_zero_position="WR")
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert any("CHECK4" in f and "WR" in f for f in failures)

    def test_check4_all_zero_te_is_failure(self, tmp_path):
        df = _make_projection_df(all_zero_position="TE")
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert any("CHECK4" in f and "TE" in f for f in failures)

    def test_clean_pass_with_hybrid_output(self, tmp_path):
        df = _make_projection_df(wr_source="hybrid", te_source="hybrid")
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        _write_residual_meta(str(tmp_path), "WR")
        _write_residual_meta(str(tmp_path), "TE")
        with _patch_paths(str(tmp_path)):
            failures, warnings = cml.run_checks(2026, 5, "half_ppr")
        assert failures == []

    def test_missing_projection_source_column_produces_warning(self, tmp_path):
        df = _make_projection_df()
        df = df.drop(columns=["projection_source"])
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        with _patch_paths(str(tmp_path)):
            failures, warnings = cml.run_checks(2026, 5, "half_ppr")
        assert not failures  # Not a hard failure
        assert any("projection_source" in w for w in warnings)

    def test_bye_week_players_excluded_from_all_zero_check(self, tmp_path):
        """All WR rows on bye should not trigger CHECK4."""
        df = _make_projection_df(n_wr=20, wr_source="hybrid")
        # Zero out all WR points and mark them as bye
        df.loc[df["position"] == "WR", "projected_points"] = 0.0
        df.loc[df["position"] == "WR", "is_bye_week"] = True
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert not any("CHECK4" in f and "WR" in f for f in failures)


class TestMainExitCodes:
    """Tests for main() exit codes via subprocess-style invocation."""

    def test_main_returns_0_on_pass(self, tmp_path, monkeypatch):
        df = _make_projection_df(wr_source="hybrid", te_source="hybrid")
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        _write_residual_meta(str(tmp_path), "WR")
        _write_residual_meta(str(tmp_path), "TE")
        monkeypatch.setattr(cml, "GOLD_DIR", os.path.join(str(tmp_path), "data", "gold"))
        monkeypatch.setattr(cml, "PROJECT_ROOT", str(tmp_path))
        with mock.patch("sys.argv", ["check_ml_output.py", "--season", "2026", "--week", "5"]):
            result = cml.main()
        assert result == 0

    def test_main_returns_1_on_failure(self, tmp_path, monkeypatch):
        # Write no Gold file → CHECK1 fails
        monkeypatch.setattr(cml, "GOLD_DIR", os.path.join(str(tmp_path), "data", "gold"))
        monkeypatch.setattr(cml, "PROJECT_ROOT", str(tmp_path))
        with mock.patch("sys.argv", ["check_ml_output.py", "--season", "2026", "--week", "5"]):
            result = cml.main()
        assert result == 1
