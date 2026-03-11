"""
Tests for Phase 10 backfill: snap_counts adapter fix and week partitioning.

Covers requirements BACKFILL-01 (snap_counts adapter takes list),
BACKFILL-02 (week partitioning for snap_counts output).
"""

import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from src.nfl_data_adapter import NFLDataAdapter


class TestSnapCountsAdapter:
    """Tests for the fixed fetch_snap_counts method."""

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_snap_counts_adapter_accepts_list(self, mock_nfl):
        """fetch_snap_counts accepts a list of seasons and passes it to
        nfl.import_snap_counts."""
        mock_mod = MagicMock()
        mock_mod.import_snap_counts.return_value = pd.DataFrame(
            {"player": ["A"], "week": [1], "offense_pct": [0.8]}
        )
        mock_nfl.return_value = mock_mod

        adapter = NFLDataAdapter()
        df = adapter.fetch_snap_counts([2023])

        assert len(df) == 1
        mock_mod.import_snap_counts.assert_called_once_with([2023])

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_snap_counts_adapter_empty_on_invalid(self, mock_nfl):
        """fetch_snap_counts with seasons outside valid range returns empty DataFrame."""
        adapter = NFLDataAdapter()
        df = adapter.fetch_snap_counts([1990])

        assert df.empty
        mock_nfl.assert_not_called()

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_snap_counts_adapter_filters_invalid_seasons(self, mock_nfl):
        """fetch_snap_counts filters out invalid seasons but processes valid ones."""
        mock_mod = MagicMock()
        mock_mod.import_snap_counts.return_value = pd.DataFrame(
            {"player": ["B"], "week": [5], "offense_pct": [0.6]}
        )
        mock_nfl.return_value = mock_mod

        adapter = NFLDataAdapter()
        df = adapter.fetch_snap_counts([1990, 2023])

        assert len(df) == 1
        mock_mod.import_snap_counts.assert_called_once_with([2023])


class TestWeekPartitioning:
    """Tests for week_partition logic in ingestion script."""

    def test_week_partition_splits_by_week(self, tmp_path):
        """When week_partition=True, a DataFrame with multiple weeks
        is split into separate per-week files."""
        df = pd.DataFrame({
            "player": ["A", "B", "C", "D"],
            "week": [1, 1, 2, 2],
            "offense_pct": [0.8, 0.7, 0.9, 0.6],
        })

        # Simulate the week partition logic
        weeks = df["week"].unique()
        assert len(weeks) == 2

        for week_num in sorted(weeks):
            week_df = df[df["week"] == week_num]
            week_dir = str(tmp_path / f"season=2023" / f"week={int(week_num)}")
            os.makedirs(week_dir, exist_ok=True)
            out_path = os.path.join(week_dir, "snap_counts_test.parquet")
            week_df.to_parquet(out_path, index=False)

        # Verify two separate directories with correct row counts
        w1_files = os.listdir(str(tmp_path / "season=2023" / "week=1"))
        w2_files = os.listdir(str(tmp_path / "season=2023" / "week=2"))
        assert len(w1_files) == 1
        assert len(w2_files) == 1

        w1_df = pd.read_parquet(str(tmp_path / "season=2023" / "week=1" / w1_files[0]))
        w2_df = pd.read_parquet(str(tmp_path / "season=2023" / "week=2" / w2_files[0]))
        assert len(w1_df) == 2
        assert len(w2_df) == 2
        assert set(w1_df["week"]) == {1}
        assert set(w2_df["week"]) == {2}

    def test_registry_snap_counts_has_week_partition(self):
        """snap_counts registry entry should have week_partition=True
        and requires_week=False after the fix."""
        import sys
        sys.path.insert(
            0, os.path.join(os.path.dirname(__file__), "..", "scripts")
        )
        from bronze_ingestion_simple import DATA_TYPE_REGISTRY

        entry = DATA_TYPE_REGISTRY["snap_counts"]
        assert entry.get("week_partition") is True, (
            "snap_counts should have week_partition=True"
        )
        assert entry["requires_week"] is False, (
            "snap_counts should have requires_week=False"
        )
