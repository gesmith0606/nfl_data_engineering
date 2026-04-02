"""
Tests for bronze validation wiring: NFLDataAdapter.validate_data() delegation
and validation output formatting.

Covers requirement VAL-01: validate_data() called during ingestion.
"""

import inspect
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from src.nfl_data_adapter import NFLDataAdapter


# ------------------------------------------------------------------
# TestAdapterValidation — validate_data() delegation
# ------------------------------------------------------------------


class TestAdapterValidation:
    """Tests for NFLDataAdapter.validate_data() method."""

    def _make_df(self, cols=None):
        """Create a small test DataFrame."""
        cols = cols or ["game_id", "season", "week", "home_team", "away_team"]
        return pd.DataFrame({c: ["val"] for c in cols})

    @patch("nfl_data_integration.NFLDataFetcher")
    def test_delegates_to_fetcher(self, MockFetcher):
        """validate_data(df, 'schedules') calls NFLDataFetcher.validate_data."""
        mock_instance = MockFetcher.return_value
        expected = {"is_valid": True, "row_count": 1, "column_count": 5, "issues": []}
        mock_instance.validate_data.return_value = expected

        adapter = NFLDataAdapter()
        df = self._make_df()
        result = adapter.validate_data(df, "schedules")

        mock_instance.validate_data.assert_called_once_with(df, "schedules")
        assert result == expected

    @patch("nfl_data_integration.NFLDataFetcher")
    def test_lazy_import(self, MockFetcher):
        """NFLDataFetcher is imported inside the method, not at module level."""
        mock_instance = MockFetcher.return_value
        mock_instance.validate_data.return_value = {
            "is_valid": True, "row_count": 1, "column_count": 5, "issues": []
        }

        adapter = NFLDataAdapter()
        adapter.validate_data(self._make_df(), "schedules")
        MockFetcher.assert_called_once()

    @patch("nfl_data_integration.NFLDataFetcher")
    def test_returns_dict(self, MockFetcher):
        """Return value has keys is_valid, row_count, column_count, issues."""
        mock_instance = MockFetcher.return_value
        mock_instance.validate_data.return_value = {
            "is_valid": True,
            "row_count": 5,
            "column_count": 3,
            "null_percentage": {},
            "issues": [],
        }

        adapter = NFLDataAdapter()
        result = adapter.validate_data(self._make_df(), "teams")

        assert "is_valid" in result
        assert "row_count" in result
        assert "column_count" in result
        assert "issues" in result


# ------------------------------------------------------------------
# TestValidationOutput — formatting helpers
# ------------------------------------------------------------------


class TestValidationOutput:
    """Tests for validation output formatting logic."""

    def test_pass_output(self):
        """When issues=[], output contains checkmark and 'Validation passed'."""
        from src.nfl_data_adapter import format_validation_output

        result = {
            "is_valid": True,
            "row_count": 10,
            "column_count": 5,
            "issues": [],
        }
        output = format_validation_output(result)
        assert output is not None
        assert "Validation passed" in output
        assert "5/5 columns valid" in output

    def test_warn_output(self):
        """When issues present, output contains warning and issue text."""
        from src.nfl_data_adapter import format_validation_output

        result = {
            "is_valid": False,
            "row_count": 10,
            "column_count": 5,
            "issues": ["Missing required columns: ['col_a']"],
        }
        output = format_validation_output(result)
        assert output is not None
        assert "Validation" in output
        assert "Missing required columns" in output

    def test_silent_skip(self):
        """No-rules type with is_valid=True and empty issues still produces output."""
        from src.nfl_data_adapter import format_validation_output

        # Per plan: always print the pass message. "No rules" types still
        # return is_valid=True, and the pass message is accurate.
        result = {
            "is_valid": True,
            "row_count": 5,
            "column_count": 3,
            "issues": [],
        }
        output = format_validation_output(result)
        assert output is not None
        assert "Validation passed" in output

    def test_save_after_warning(self):
        """Validation issues do not raise exceptions (non-blocking)."""
        from src.nfl_data_adapter import format_validation_output

        result = {
            "is_valid": False,
            "row_count": 10,
            "column_count": 5,
            "issues": [
                "Missing required columns: ['air_yards']",
                "High null percentage in weather_detail: 78.2%",
            ],
        }
        # Should not raise — just returns a string
        output = format_validation_output(result)
        assert isinstance(output, str)
        assert "air_yards" in output
        assert "weather_detail" in output


# ------------------------------------------------------------------
# TestIngestionValidation — wiring in bronze_ingestion_simple.py
# ------------------------------------------------------------------


class TestIngestionValidation:
    """Structural test verifying validate_data() is called in the ingestion script."""

    def test_validation_called_in_script(self):
        """bronze_ingestion_simple.py calls adapter.validate_data() after fetch."""
        import importlib
        import sys

        # Import the script as a module
        script_path = "scripts.bronze_ingestion_simple"
        # Use direct source reading to check the call site exists
        with open("scripts/bronze_ingestion_simple.py", "r") as f:
            source = f.read()

        # Verify the validate_data call is present between fetch and save
        assert "adapter.validate_data(" in source, (
            "validate_data() call not found in bronze_ingestion_simple.py"
        )

        # Verify it appears BEFORE save_local (wired between fetch and save)
        val_pos = source.index("adapter.validate_data(")
        save_pos = source.index("save_local(df,")
        assert val_pos < save_pos, (
            "validate_data() must be called before save_local()"
        )

        # Verify it's wrapped in try/except (non-blocking)
        # Find the try block containing validate_data
        lines = source.split("\n")
        val_line_idx = None
        for i, line in enumerate(lines):
            if "adapter.validate_data(" in line:
                val_line_idx = i
                break
        assert val_line_idx is not None

        # Walk backwards to find the enclosing try
        found_try = False
        for i in range(val_line_idx - 1, max(0, val_line_idx - 5), -1):
            if "try:" in lines[i]:
                found_try = True
                break
        assert found_try, (
            "validate_data() should be wrapped in try/except for non-blocking behavior"
        )
