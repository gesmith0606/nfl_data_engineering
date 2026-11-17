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

import numpy as np
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


class TestCheck3PartialHybrid:
    """Post-push review M-2: partial hybrid routing must FAIL, not pass."""

    def test_partial_hybrid_wr_is_failure(self, tmp_path):
        # 40 WR rows but only 1 routed hybrid — Check 3's old position-level
        # set test would pass; the coverage check must fail it.
        df = _make_projection_df(wr_source="heuristic", te_source="hybrid")
        wr_idx = df.index[df["position"] == "WR"][:1]
        df.loc[wr_idx, "projection_source"] = "hybrid"
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        _write_residual_meta(str(tmp_path), "WR")
        _write_residual_meta(str(tmp_path), "TE")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert any(
            "CHECK3" in f and "WR" in f and "%" in f for f in failures
        ), f"partial WR hybrid coverage must fail Check 3: {failures}"

    def test_full_hybrid_coverage_passes(self, tmp_path):
        df = _make_projection_df(wr_source="hybrid", te_source="hybrid")
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        _write_residual_meta(str(tmp_path), "WR")
        _write_residual_meta(str(tmp_path), "TE")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert not any("CHECK3" in f for f in failures)

    def test_consensus_fallback_rows_do_not_count_against_hybrid_share(self, tmp_path):
        # A week-1 board can carry many consensus_fallback rows (rookies, no
        # basis): they took no route, so they must not fail the routing check.
        df = _make_projection_df(wr_source="hybrid", te_source="hybrid")
        fb = pd.DataFrame(
            [
                {
                    "player_id": f"WRfb_{i}",
                    "player_name": f"WR Fallback {i}",
                    "position": "WR",
                    "recent_team": "KC",
                    "projected_points": 6.0,
                    "is_bye_week": False,
                    "projection_source": "consensus_fallback",
                    "week": 5,
                }
                for i in range(10)
            ]
        )
        df = pd.concat([df, fb], ignore_index=True)
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        _write_residual_meta(str(tmp_path), "WR")
        _write_residual_meta(str(tmp_path), "TE")
        with _patch_paths(str(tmp_path)):
            failures, _ = cml.run_checks(2026, 5, "half_ppr")
        assert not any("CHECK3" in f for f in failures), failures


class TestCheck3AppliedFlag:
    """PR 2: boards carry residual_correction_applied / residual_skip_reason and
    the check covers all four routed positions, not just WR/TE."""

    @staticmethod
    def _board(**by_pos):
        """by_pos: position -> (n_applied, n_skipped, skip_reason)."""
        rows = []
        for pos, (n_app, n_skip, why) in by_pos.items():
            for i in range(n_app + n_skip):
                ok = i < n_app
                rows.append(
                    {
                        "player_id": f"{pos}_{i}",
                        "player_name": f"{pos} {i}",
                        "position": pos,
                        "recent_team": "KC",
                        "projected_points": 8.0 + i * 0.1,
                        "is_bye_week": False,
                        "projection_source": "hybrid" if ok else "heuristic",
                        "residual_correction_applied": ok,
                        "residual_skip_reason": "" if ok else why,
                        "week": 5,
                    }
                )
        return pd.DataFrame(rows)

    def _run(self, tmp_path, df, positions=("QB", "RB", "WR", "TE")):
        _write_gold(df, str(tmp_path), season=2026, week=5, scoring="half_ppr")
        for p in positions:
            _write_residual_meta(str(tmp_path), p)
        with _patch_paths(str(tmp_path)):
            return cml.run_checks(2026, 5, "half_ppr")

    def test_all_four_positions_corrected_passes(self, tmp_path):
        df = self._board(QB=(30, 0, ""), RB=(60, 0, ""), WR=(90, 0, ""), TE=(40, 0, ""))
        failures, warnings = self._run(tmp_path, df)
        assert failures == [] and not any("CHECK3" in w for w in warnings)

    def test_coverage_guard_skip_is_a_warning_not_a_failure(self, tmp_path):
        df = self._board(QB=(0, 30, "coverage_guard"), RB=(60, 0, ""), WR=(90, 0, ""), TE=(40, 0, ""))
        failures, warnings = self._run(tmp_path, df)
        assert not any("CHECK3" in f for f in failures), failures
        assert any("QB" in w and "coverage" in w.lower() for w in warnings)

    def test_qb_silently_not_corrected_fails_now(self, tmp_path):
        """The old check only looked at WR/TE; a QB residual that silently failed passed."""
        df = self._board(QB=(0, 30, "no_model"), RB=(60, 0, ""), WR=(90, 0, ""), TE=(40, 0, ""))
        failures, _ = self._run(tmp_path, df)
        assert any("CHECK3" in f and "QB" in f and "no_model" in f for f in failures), failures

    def test_hybrid_label_on_uncorrected_row_fails(self, tmp_path):
        df = self._board(QB=(30, 0, ""), RB=(60, 0, ""), WR=(90, 0, ""), TE=(40, 0, ""))
        df.loc[df.position == "RB", "residual_correction_applied"] = False  # label still 'hybrid'
        failures, _ = self._run(tmp_path, df)
        assert any("labelled" in f and "RB" in f for f in failures), failures

    def test_few_rows_without_features_are_tolerated(self, tmp_path):
        df = self._board(QB=(25, 5, "no_features"), RB=(60, 0, ""), WR=(90, 0, ""), TE=(40, 0, ""))
        failures, _ = self._run(tmp_path, df)
        assert not any("CHECK3" in f for f in failures), failures

    def test_most_rows_without_features_fails(self, tmp_path):
        df = self._board(QB=(10, 20, "no_features"), RB=(60, 0, ""), WR=(90, 0, ""), TE=(40, 0, ""))
        failures, _ = self._run(tmp_path, df)
        assert any("QB" in f and "no populated model feature" in f for f in failures), failures

    def test_fallback_rows_are_excluded_from_the_shares(self, tmp_path):
        df = self._board(QB=(30, 0, ""), RB=(60, 0, ""), WR=(90, 0, ""), TE=(40, 0, ""))
        fb = pd.DataFrame(
            [
                {
                    "player_id": f"fb{i}",
                    "player_name": f"fb {i}",
                    "position": "QB",
                    "recent_team": "KC",
                    "projected_points": 7.0,
                    "is_bye_week": False,
                    "projection_source": "consensus_fallback",
                    "residual_correction_applied": np.nan,
                    "residual_skip_reason": np.nan,
                    "week": 5,
                }
                for i in range(20)
            ]
        )
        failures, _ = self._run(tmp_path, pd.concat([df, fb], ignore_index=True))
        assert not any("CHECK3" in f for f in failures), failures
