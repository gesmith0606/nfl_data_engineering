"""Tests for the Bronze layer inventory generation script."""

import os
import tempfile
from datetime import datetime
from typing import List
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# Ensure project root is importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from scripts.generate_inventory import scan_local, format_markdown


def _create_parquet(path: str, columns: List[str]) -> None:
    """Helper: write a tiny parquet file with given column names."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    table = pa.table({col: [1] for col in columns})
    pq.write_table(table, path)


class TestScanLocal:
    """Tests for scan_local()."""

    def test_returns_correct_file_count_and_size(self, tmp_path):
        """scan_local on a temp dir with fake parquet files returns correct file count and size."""
        # Create two parquet files under players/weekly/
        _create_parquet(
            str(tmp_path / "players" / "weekly" / "season=2023" / "data.parquet"),
            ["col_a", "col_b", "col_c"],
        )
        _create_parquet(
            str(tmp_path / "players" / "weekly" / "season=2024" / "data.parquet"),
            ["col_a", "col_b", "col_c"],
        )

        results = scan_local(str(tmp_path))

        # Should find "players/weekly" as a data type grouping
        # The exact key depends on how scan_local groups — top-level + second level
        found = False
        for key, metrics in results.items():
            if metrics["file_count"] == 2:
                found = True
                assert metrics["total_size_mb"] >= 0  # tiny test files may round to 0.0
                assert metrics["column_count"] == 3
        assert found, f"Expected a data type with 2 files, got: {results}"

    def test_groups_files_by_data_type(self, tmp_path):
        """scan_local groups files by data type (directory structure under bronze)."""
        _create_parquet(
            str(tmp_path / "players" / "weekly" / "season=2023" / "a.parquet"),
            ["x", "y"],
        )
        _create_parquet(
            str(tmp_path / "games" / "season=2023" / "b.parquet"),
            ["a", "b", "c", "d"],
        )

        results = scan_local(str(tmp_path))

        assert len(results) >= 2, f"Expected at least 2 data types, got: {list(results.keys())}"

    def test_extracts_season_range(self, tmp_path):
        """scan_local detects season range from partition directories."""
        _create_parquet(
            str(tmp_path / "players" / "weekly" / "season=2020" / "a.parquet"),
            ["x"],
        )
        _create_parquet(
            str(tmp_path / "players" / "weekly" / "season=2024" / "b.parquet"),
            ["x"],
        )

        results = scan_local(str(tmp_path))

        # Find the entry for players/weekly
        for key, metrics in results.items():
            if metrics["file_count"] == 2:
                assert "2020" in metrics["season_range"]
                assert "2024" in metrics["season_range"]
                break

    def test_empty_directory_returns_empty(self, tmp_path):
        """scan_local on an empty directory returns empty dict."""
        results = scan_local(str(tmp_path))
        assert results == {}


class TestFormatMarkdown:
    """Tests for format_markdown()."""

    def test_produces_valid_markdown_table(self):
        """format_markdown produces a markdown table with expected headers."""
        results = {
            "players/weekly": {
                "file_count": 5,
                "total_size_mb": 3.2,
                "season_range": "2020-2024",
                "column_count": 42,
                "last_modified": "2026-03-06",
            },
        }

        md = format_markdown(results)

        assert "Data Type" in md
        assert "Files" in md
        assert "Size (MB)" in md
        assert "Seasons" in md
        assert "Columns" in md
        assert "Last Updated" in md
        assert "players/weekly" in md
        assert "5" in md
        assert "3.2" in md

    def test_empty_results_shows_no_files(self):
        """format_markdown with empty results produces a message about no files."""
        md = format_markdown({})
        assert "no" in md.lower() or "No" in md or "0 files" in md.lower()

    def test_includes_summary_totals(self):
        """format_markdown includes total files and total size."""
        results = {
            "games": {
                "file_count": 6,
                "total_size_mb": 1.0,
                "season_range": "2020-2025",
                "column_count": 50,
                "last_modified": "2026-03-06",
            },
            "players/weekly": {
                "file_count": 5,
                "total_size_mb": 2.5,
                "season_range": "2020-2024",
                "column_count": 42,
                "last_modified": "2026-03-06",
            },
        }

        md = format_markdown(results)

        # Should mention total of 11 files somewhere
        assert "11" in md


class TestCLI:
    """Tests for the CLI main() function."""

    def test_output_flag_writes_file(self, tmp_path):
        """main() with --output flag writes markdown to specified file."""
        # Create a tiny bronze dir
        _create_parquet(
            str(tmp_path / "bronze" / "games" / "season=2023" / "a.parquet"),
            ["x", "y"],
        )
        output_file = str(tmp_path / "output.md")

        from scripts.generate_inventory import main

        with patch(
            "sys.argv",
            ["generate_inventory.py", "--base-dir", str(tmp_path / "bronze"), "--output", output_file],
        ):
            main()

        assert os.path.exists(output_file)
        content = open(output_file).read()
        assert "games" in content
