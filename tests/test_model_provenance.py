"""Tests for src/model_provenance.py — training-run provenance stamping.

Covers MODEL_REVIEW_2026_08_15.md finding #2 ("no data-vintage/provenance
pinning on any model artifact"): row counts + latest-partition timestamps
must be computed correctly from Parquet footer metadata (no data read), a
missing source directory must degrade to a 0/None entry rather than raise,
and git_sha must resolve in this repo (a real git checkout) while still
degrading gracefully outside one.
"""

import os
import subprocess
import sys
from unittest import mock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import model_provenance as mp


def _write_parquet(path, n_rows=10):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame({"col": range(n_rows)}).to_parquet(path, index=False)


# ---------------------------------------------------------------------------
# _scan_parquet_source
# ---------------------------------------------------------------------------


class TestScanParquetSource:
    def test_missing_directory_returns_zeroes(self, tmp_path):
        rows, n_files, latest = mp._scan_parquet_source(tmp_path / "nope")
        assert (rows, n_files, latest) == (0, 0, None)

    def test_empty_directory_returns_zeroes(self, tmp_path):
        (tmp_path / "empty").mkdir()
        rows, n_files, latest = mp._scan_parquet_source(tmp_path / "empty")
        assert (rows, n_files, latest) == (0, 0, None)

    def test_sums_rows_across_files(self, tmp_path):
        base = tmp_path / "src"
        _write_parquet(str(base / "season=2024" / "a.parquet"), n_rows=100)
        _write_parquet(str(base / "season=2025" / "b.parquet"), n_rows=50)
        rows, n_files, latest = mp._scan_parquet_source(base)
        assert rows == 150
        assert n_files == 2
        assert latest is not None

    def test_recurses_into_week_partitions(self, tmp_path):
        base = tmp_path / "snaps"
        _write_parquet(str(base / "season=2024" / "week=1" / "f.parquet"), n_rows=20)
        _write_parquet(str(base / "season=2024" / "week=2" / "f.parquet"), n_rows=20)
        rows, n_files, _ = mp._scan_parquet_source(base)
        assert rows == 40
        assert n_files == 2

    def test_latest_partition_reflects_newest_file_mtime(self, tmp_path):
        import time

        base = tmp_path / "src"
        _write_parquet(str(base / "old.parquet"), n_rows=5)
        old_mtime = (base / "old.parquet").stat().st_mtime
        time.sleep(0.05)
        _write_parquet(str(base / "new.parquet"), n_rows=5)
        new_mtime = (base / "new.parquet").stat().st_mtime
        assert new_mtime > old_mtime

        _, _, latest_iso = mp._scan_parquet_source(base)
        # ISO string should parse and correspond to the newer file
        from datetime import datetime

        latest_dt = datetime.fromisoformat(latest_iso)
        assert latest_dt.timestamp() == pytest.approx(new_mtime, abs=1.0)

    def test_unreadable_file_is_skipped_not_raised(self, tmp_path):
        base = tmp_path / "src"
        os.makedirs(base, exist_ok=True)
        # A .parquet file that isn't valid parquet at all
        with open(base / "corrupt.parquet", "w") as f:
            f.write("not parquet data")
        _write_parquet(str(base / "good.parquet"), n_rows=7)

        rows, n_files, _ = mp._scan_parquet_source(base)
        # good.parquet still counted; corrupt.parquet silently skipped
        assert rows == 7
        assert n_files == 2  # both files counted, only good.parquet's rows summed


# ---------------------------------------------------------------------------
# git_sha
# ---------------------------------------------------------------------------


class TestGitSha:
    def test_resolves_in_this_repo(self):
        # This test runs inside a real git checkout, so a real SHA must come back.
        sha = mp.git_sha()
        assert sha is not None
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_returns_none_outside_a_git_repo(self, tmp_path):
        sha = mp.git_sha(cwd=tmp_path)
        assert sha is None

    def test_returns_none_when_git_missing(self, tmp_path):
        with mock.patch("model_provenance.subprocess.run", side_effect=FileNotFoundError):
            sha = mp.git_sha(cwd=tmp_path)
        assert sha is None

    def test_returns_none_on_timeout(self, tmp_path):
        with mock.patch(
            "model_provenance.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5),
        ):
            sha = mp.git_sha(cwd=tmp_path)
        assert sha is None


# ---------------------------------------------------------------------------
# build_provenance
# ---------------------------------------------------------------------------


class TestBuildProvenance:
    def test_shape_and_keys(self, tmp_path):
        _write_parquet(str(tmp_path / "silver" / "players" / "usage" / "f.parquet"), n_rows=42)
        result = mp.build_provenance(
            {"silver_players_usage": "silver/players/usage"},
            data_root=tmp_path,
            project_root=tmp_path,
        )
        assert set(result.keys()) == {"generated_at", "git_sha", "sources"}
        assert "silver_players_usage" in result["sources"]
        src = result["sources"]["silver_players_usage"]
        assert src["path"] == "silver/players/usage"
        assert src["row_count"] == 42
        assert src["n_files"] == 1
        assert src["latest_partition_at"] is not None

    def test_multiple_sources_independent(self, tmp_path):
        _write_parquet(str(tmp_path / "bronze" / "players" / "snaps" / "f.parquet"), n_rows=10)
        _write_parquet(str(tmp_path / "silver" / "players" / "advanced" / "f.parquet"), n_rows=20)
        result = mp.build_provenance(
            {
                "bronze_players_snaps": "bronze/players/snaps",
                "silver_players_advanced": "silver/players/advanced",
            },
            data_root=tmp_path,
        )
        assert result["sources"]["bronze_players_snaps"]["row_count"] == 10
        assert result["sources"]["silver_players_advanced"]["row_count"] == 20

    def test_missing_source_degrades_gracefully(self, tmp_path):
        result = mp.build_provenance(
            {"nonexistent": "silver/does/not/exist"}, data_root=tmp_path
        )
        src = result["sources"]["nonexistent"]
        assert src["row_count"] == 0
        assert src["n_files"] == 0
        assert src["latest_partition_at"] is None

    def test_generated_at_is_iso8601(self, tmp_path):
        from datetime import datetime

        result = mp.build_provenance({}, data_root=tmp_path)
        # Should not raise
        datetime.fromisoformat(result["generated_at"])

    def test_json_serializable(self, tmp_path):
        import json

        _write_parquet(str(tmp_path / "silver" / "x" / "f.parquet"), n_rows=1)
        result = mp.build_provenance({"x": "silver/x"}, data_root=tmp_path, project_root=tmp_path)
        # Must round-trip through json.dump the way meta.json writers do
        json.dumps(result)
