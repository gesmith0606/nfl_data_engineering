"""Tests for scripts/export_rankings_submission.py."""

import pandas as pd
import pytest

from scripts.export_rankings_submission import (
    DEFAULT_COLUMNS,
    export_preseason,
    export_weekly,
)


def test_preseason_export_ranked_and_complete(tmp_path):
    written = export_preseason(2026, out_dir=tmp_path)
    names = [p.name for p in written]
    assert "2026_draft_overall.csv" in names
    overall = pd.read_csv(tmp_path / "2026_draft_overall.csv")
    assert list(overall.columns) == DEFAULT_COLUMNS
    assert overall["rank"].tolist() == list(range(1, len(overall) + 1))
    # Positional file is position-pure.
    qb = pd.read_csv(tmp_path / "2026_draft_QB.csv")
    assert set(qb["position"].str.upper()) == {"QB"}


def test_weekly_export_sorted(tmp_path):
    written = export_weekly(2025, 18, out_dir=tmp_path)
    assert written, "no positional files written for 2025 wk18"
    rb = pd.read_csv(tmp_path / "2025_wk18_half_ppr_RB.csv")
    assert rb["rank"].is_monotonic_increasing


def test_custom_columns(tmp_path):
    export_preseason(2026, columns=["rank", "player_name"], out_dir=tmp_path)
    overall = pd.read_csv(tmp_path / "2026_draft_overall.csv")
    assert list(overall.columns) == ["rank", "player_name"]


def test_missing_data_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        export_weekly(2031, 1, out_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        export_preseason(2020, out_dir=tmp_path)
