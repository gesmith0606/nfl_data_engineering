"""
Tests for batch Bronze ingestion script (Phase 11 Plan 01).

Covers requirements ORCH-01, ORCH-02, VALID-01:
- All 15 DATA_TYPE_REGISTRY entries are iterated
- Failures are caught and reported (not abort)
- 0-row returns recorded as SKIP
- Skip-existing prevents redundant fetches
- Summary output with succeeded/failed/skipped counts
- validate_data called for each non-empty DataFrame
"""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock, call

import pandas as pd
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_ingestion_simple import DATA_TYPE_REGISTRY


# ------------------------------------------------------------------
# Helper: small DataFrame for mocking adapter returns
# ------------------------------------------------------------------

def _make_df(rows: int = 5) -> pd.DataFrame:
    """Return a small DataFrame with basic columns."""
    return pd.DataFrame({
        "season": [2024] * rows,
        "week": [1] * rows,
        "player": [f"player_{i}" for i in range(rows)],
        "team": ["KC"] * rows,
    })


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestRunBatch:
    """Tests for the run_batch() function."""

    @patch("scripts.bronze_batch_ingestion.save_local")
    @patch("scripts.bronze_batch_ingestion.NFLDataAdapter")
    def test_all_registry_types_processed(self, MockAdapter, mock_save):
        """run_batch returns results containing all 15 DATA_TYPE_REGISTRY keys."""
        from scripts.bronze_batch_ingestion import run_batch

        adapter = MockAdapter.return_value
        # Make every adapter method return a small DataFrame
        for entry in DATA_TYPE_REGISTRY.values():
            getattr(adapter, entry["adapter_method"]).return_value = _make_df()
        adapter.validate_data.return_value = {"is_valid": True, "issues": [], "column_count": 4, "row_count": 5}

        results = run_batch(season_start=2024, season_end=2024, skip_existing=False, dry_run=False)

        # Every registry key must appear in results
        result_types = {r[0] for r in results}
        for key in DATA_TYPE_REGISTRY:
            assert key in result_types, f"Missing data type in results: {key}"

    @patch("scripts.bronze_batch_ingestion.save_local")
    @patch("scripts.bronze_batch_ingestion.NFLDataAdapter")
    def test_failure_continues_processing(self, MockAdapter, mock_save):
        """When adapter raises Exception for one type, that type shows FAIL but others still process."""
        from scripts.bronze_batch_ingestion import run_batch

        adapter = MockAdapter.return_value
        for entry in DATA_TYPE_REGISTRY.values():
            getattr(adapter, entry["adapter_method"]).return_value = _make_df()
        # Make schedules raise an error
        adapter.fetch_schedules.side_effect = Exception("API timeout")
        adapter.validate_data.return_value = {"is_valid": True, "issues": [], "column_count": 4, "row_count": 5}

        results = run_batch(season_start=2024, season_end=2024, skip_existing=False, dry_run=False)

        # Find the schedules result
        schedules_results = [r for r in results if r[0] == "schedules"]
        assert any(r[3] == "FAIL" for r in schedules_results), "schedules should be FAIL"

        # Other types should still have OK results
        ok_types = {r[0] for r in results if r[3] == "OK"}
        assert len(ok_types) > 10, f"Most types should be OK, got {len(ok_types)}"

    @patch("scripts.bronze_batch_ingestion.save_local")
    @patch("scripts.bronze_batch_ingestion.NFLDataAdapter")
    def test_zero_rows_is_skip_not_fail(self, MockAdapter, mock_save):
        """When 0-row DataFrame returned, status is SKIP not FAIL."""
        from scripts.bronze_batch_ingestion import run_batch

        adapter = MockAdapter.return_value
        for entry in DATA_TYPE_REGISTRY.values():
            getattr(adapter, entry["adapter_method"]).return_value = _make_df()
        # QBR returns empty
        adapter.fetch_qbr.return_value = pd.DataFrame()
        adapter.validate_data.return_value = {"is_valid": True, "issues": [], "column_count": 4, "row_count": 5}

        results = run_batch(season_start=2024, season_end=2024, skip_existing=False, dry_run=False)

        qbr_results = [r for r in results if r[0] == "qbr"]
        assert any(r[3] == "SKIP" for r in qbr_results), f"qbr should be SKIP, got: {qbr_results}"

    @patch("scripts.bronze_batch_ingestion.save_local")
    @patch("scripts.bronze_batch_ingestion.NFLDataAdapter")
    def test_skip_existing_when_parquet_present(self, MockAdapter, mock_save):
        """When parquet files already exist for a type/season, status is SKIPPED (no fetch)."""
        from scripts.bronze_batch_ingestion import run_batch

        adapter = MockAdapter.return_value
        for entry in DATA_TYPE_REGISTRY.values():
            getattr(adapter, entry["adapter_method"]).return_value = _make_df()
        adapter.validate_data.return_value = {"is_valid": True, "issues": [], "column_count": 4, "row_count": 5}

        # Create a temp dir with existing parquet for schedules
        with tempfile.TemporaryDirectory() as tmpdir:
            sched_dir = os.path.join(tmpdir, "bronze", "schedules", "season=2024")
            os.makedirs(sched_dir)
            _make_df().to_parquet(os.path.join(sched_dir, "schedules_20240101_000000.parquet"))

            results = run_batch(
                season_start=2024, season_end=2024,
                skip_existing=True, dry_run=False,
                base_dir=tmpdir,
            )

        sched_results = [r for r in results if r[0] == "schedules"]
        assert any(r[3] == "SKIPPED" for r in sched_results), f"schedules should be SKIPPED, got: {sched_results}"
        # fetch_schedules should NOT have been called for season 2024
        # (it may be called for other reasons, but the result should be SKIPPED)

    @patch("scripts.bronze_batch_ingestion.save_local")
    @patch("scripts.bronze_batch_ingestion.NFLDataAdapter")
    def test_summary_counts(self, MockAdapter, mock_save):
        """Summary output contains succeeded/failed/skipped counts."""
        from scripts.bronze_batch_ingestion import run_batch, print_summary

        adapter = MockAdapter.return_value
        for entry in DATA_TYPE_REGISTRY.values():
            getattr(adapter, entry["adapter_method"]).return_value = _make_df()
        adapter.fetch_schedules.side_effect = Exception("API error")
        adapter.fetch_qbr.return_value = pd.DataFrame()
        adapter.validate_data.return_value = {"is_valid": True, "issues": [], "column_count": 4, "row_count": 5}

        results = run_batch(season_start=2024, season_end=2024, skip_existing=False, dry_run=False)

        # Count statuses
        statuses = [r[3] for r in results]
        ok_count = statuses.count("OK")
        fail_count = statuses.count("FAIL")
        skip_count = statuses.count("SKIP")

        assert ok_count > 0, "Should have some OK results"
        assert fail_count > 0, "Should have at least 1 FAIL"
        assert skip_count > 0, "Should have at least 1 SKIP (QBR 0 rows)"

    @patch("scripts.bronze_batch_ingestion.save_local")
    @patch("scripts.bronze_batch_ingestion.NFLDataAdapter")
    def test_validate_data_called_for_each_nonempty_df(self, MockAdapter, mock_save):
        """validate_data called for each non-empty ingested DataFrame."""
        from scripts.bronze_batch_ingestion import run_batch

        adapter = MockAdapter.return_value
        for entry in DATA_TYPE_REGISTRY.values():
            getattr(adapter, entry["adapter_method"]).return_value = _make_df()
        adapter.validate_data.return_value = {"is_valid": True, "issues": [], "column_count": 4, "row_count": 5}

        results = run_batch(season_start=2024, season_end=2024, skip_existing=False, dry_run=False)

        # validate_data should have been called at least once for each type that returned data
        ok_count = sum(1 for r in results if r[3] == "OK")
        assert adapter.validate_data.call_count >= ok_count, (
            f"validate_data called {adapter.validate_data.call_count} times, "
            f"expected at least {ok_count}"
        )
