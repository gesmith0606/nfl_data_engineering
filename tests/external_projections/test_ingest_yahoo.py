"""Tests for the Yahoo (FP-proxy) external-projections Bronze ingester."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_INGESTER = _PROJECT_ROOT / "scripts" / "ingest_external_projections_yahoo.py"
_FIXTURE = (
    _PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "external_projections"
    / "fantasypros_sample.json"
)


def test_writes_bronze_with_yahoo_proxy_fp_label(tmp_path):
    out_root = tmp_path / "bronze"
    rc = subprocess.call(
        [
            sys.executable,
            str(_INGESTER),
            "--season", "2025",
            "--week", "1",
            "--scoring", "half_ppr",
            "--out-root", str(out_root),
            "--html-fixture", str(_FIXTURE),
        ]
    )
    assert rc == 0

    week_dir = out_root / "yahoo_proxy_fp" / "season=2025" / "week=01"
    parquets = list(week_dir.glob("yahoo_proxy_fp_*.parquet"))
    assert len(parquets) == 1

    df = pd.read_parquet(parquets[0])
    assert (df["source"] == "yahoo_proxy_fp").all()
    assert "Patrick Mahomes" in df["player_name"].values
    assert "Christian McCaffrey" in df["player_name"].values
    assert "Travis Kelce" in df["player_name"].values
    # All 5 positions covered
    assert set(df["position"].unique()) == {"QB", "RB", "WR", "TE", "K"}


def test_fail_open_on_missing_fixture(tmp_path):
    """Empty/missing HTML fixture → no parquet, exit 0."""
    empty = tmp_path / "empty.json"
    empty.write_text('{"qb":"","rb":"","wr":"","te":"","k":""}', encoding="utf-8")
    out_root = tmp_path / "bronze"

    rc = subprocess.call(
        [
            sys.executable,
            str(_INGESTER),
            "--season", "2025",
            "--week", "1",
            "--out-root", str(out_root),
            "--html-fixture", str(empty),
        ]
    )
    assert rc == 0
    week_dir = out_root / "yahoo_proxy_fp" / "season=2025" / "week=01"
    assert not week_dir.exists() or not list(week_dir.glob("*.parquet"))
