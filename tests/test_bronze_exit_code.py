"""
Tests for Finding 1 (silent-failure sweep): bronze_ingestion_simple.py main()
must exit non-zero when ingestion is a total no-op.

Prior behavior: main() always `return 0`, even when every requested season
returned an empty DataFrame -- skipped/ingested counters were computed but
never influenced the exit code. weekly-pipeline.yml and
weekly-reference-refresh.yml rely on the process exit code to fail hard.

Contract under test:
- ingested == 0 across the whole run (all requested seasons/variants empty)
  -> main() returns 1 and prints an ::error:: line.
- SOME season ingested (partial success) -> main() still returns 0 (existing
  fail-open-per-season behavior is preserved; only a total no-op is fatal).
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _draft_picks_df():
    return pd.DataFrame({
        "season": [2024],
        "round": [1],
        "pick": [1],
        "team": ["KC"],
        "player_name": ["Test Player"],
        "position": ["QB"],
        "pfr_player_id": ["TestP00"],
    })


class TestExitCodeAllEmpty:
    """main() must return 1 when zero rows were ingested for the whole run."""

    @patch("scripts.bronze_ingestion_simple.NFLDataAdapter")
    def test_single_season_empty_returns_1(self, MockAdapter, tmp_path, capsys):
        """A single --season request whose only fetch returns empty exits 1."""
        from scripts.bronze_ingestion_simple import main

        mock_adapter = MagicMock()
        mock_adapter.fetch_draft_picks.return_value = pd.DataFrame()
        MockAdapter.return_value = mock_adapter

        with patch("sys.argv", ["prog", "--data-type", "draft_picks", "--season", "2024"]):
            with patch("scripts.bronze_ingestion_simple.save_local") as mock_save:
                exit_code = main()

        assert exit_code == 1
        mock_save.assert_not_called()
        captured = capsys.readouterr()
        assert "::error::" in captured.out

    @patch("scripts.bronze_ingestion_simple.NFLDataAdapter")
    def test_all_requested_seasons_empty_returns_1(self, MockAdapter, tmp_path, capsys):
        """A --seasons range where every season returns empty data exits 1."""
        from scripts.bronze_ingestion_simple import main

        mock_adapter = MagicMock()
        mock_adapter.fetch_draft_picks.return_value = pd.DataFrame()
        MockAdapter.return_value = mock_adapter

        with patch("sys.argv", ["prog", "--data-type", "draft_picks", "--seasons", "2022-2024"]):
            with patch("scripts.bronze_ingestion_simple.save_local") as mock_save:
                exit_code = main()

        assert exit_code == 1
        mock_save.assert_not_called()


class TestExitCodePartialSuccess:
    """main() must stay 0 when at least one season/variant succeeded."""

    @patch("scripts.bronze_ingestion_simple.NFLDataAdapter")
    def test_some_seasons_ingested_returns_0(self, MockAdapter, tmp_path, capsys):
        """Partial success (one season ingested, others empty) preserves exit 0."""
        from scripts.bronze_ingestion_simple import main

        df_ok = _draft_picks_df()
        df_empty = pd.DataFrame()

        mock_adapter = MagicMock()
        mock_adapter.fetch_draft_picks.side_effect = [df_ok, df_empty, df_empty]
        mock_adapter.validate_data.return_value = {
            "is_valid": True, "issues": [], "row_count": 1, "column_count": 6,
        }
        MockAdapter.return_value = mock_adapter

        with patch("sys.argv", ["prog", "--data-type", "draft_picks", "--seasons", "2022-2024"]):
            with patch(
                "scripts.bronze_ingestion_simple.save_local",
                return_value=str(tmp_path / "test.parquet"),
            ):
                exit_code = main()

        assert exit_code == 0

    @patch("scripts.bronze_ingestion_simple.NFLDataAdapter")
    def test_full_success_returns_0(self, MockAdapter, tmp_path, capsys):
        """All seasons ingested successfully -> exit 0, no ::error::."""
        from scripts.bronze_ingestion_simple import main

        mock_adapter = MagicMock()
        mock_adapter.fetch_draft_picks.return_value = _draft_picks_df()
        mock_adapter.validate_data.return_value = {
            "is_valid": True, "issues": [], "row_count": 1, "column_count": 6,
        }
        MockAdapter.return_value = mock_adapter

        with patch("sys.argv", ["prog", "--data-type", "draft_picks", "--season", "2024"]):
            with patch(
                "scripts.bronze_ingestion_simple.save_local",
                return_value=str(tmp_path / "test.parquet"),
            ):
                exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "::error::" not in captured.out
