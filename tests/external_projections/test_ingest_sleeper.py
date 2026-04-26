"""Tests for the Sleeper external-projections Bronze ingester (Plan 73-01)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_INGESTER = _PROJECT_ROOT / "scripts" / "ingest_external_projections_sleeper.py"
_FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "external_projections"


@pytest.fixture
def registry_fixture(tmp_path):
    payload = {
        "4046": {"full_name": "Patrick Mahomes", "team": "KC", "position": "QB"},
        "6770": {"full_name": "Josh Allen", "team": "BUF", "position": "QB"},
        "7242": {"full_name": "Lamar Jackson", "team": "BAL", "position": "QB"},
        "4034": {"full_name": "Christian McCaffrey", "team": "SF", "position": "RB"},
    }
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_d01_no_direct_requests_import():
    """D-01 LOCKED: ingester MUST use src.sleeper_http.fetch_sleeper_json,
    never call requests directly. Structural test greps source."""
    src = _INGESTER.read_text(encoding="utf-8")
    # Direct `import requests` would violate D-01.
    assert not re.search(r"^import requests\b", src, re.MULTILINE), (
        "D-01 violation: ingest_external_projections_sleeper.py must not "
        "`import requests` directly. Use src.sleeper_http instead."
    )
    assert not re.search(r"^from requests\b", src, re.MULTILINE), (
        "D-01 violation: ingest_external_projections_sleeper.py must not "
        "import from requests. Use src.sleeper_http instead."
    )
    # Positive contract: must import from sleeper_http.
    assert "from src.sleeper_http import fetch_sleeper_json" in src


def test_writes_bronze_parquet_with_correct_path(tmp_path, registry_fixture):
    """Ingester writes Parquet at data/bronze/external_projections/sleeper/season=YYYY/week=WW/."""
    out_root = tmp_path / "bronze"
    proj_fixture = _FIXTURE_DIR / "sleeper_sample.json"

    rc = subprocess.call(
        [
            sys.executable,
            str(_INGESTER),
            "--season", "2025",
            "--week", "1",
            "--scoring", "half_ppr",
            "--out-root", str(out_root),
            "--registry-fixture", str(registry_fixture),
            "--projections-fixture", str(proj_fixture),
        ]
    )
    assert rc == 0

    week_dir = out_root / "sleeper" / "season=2025" / "week=01"
    parquets = list(week_dir.glob("sleeper_*.parquet"))
    assert len(parquets) == 1, f"expected 1 parquet, got {len(parquets)}"

    df = pd.read_parquet(parquets[0])
    assert len(df) >= 4  # at least the 4 fixture players with pts_half_ppr
    assert set(df.columns) >= {
        "player_name",
        "player_id",
        "team",
        "position",
        "projected_points",
        "scoring_format",
        "source",
        "season",
        "week",
        "projected_at",
    }
    assert (df["source"] == "sleeper").all()
    assert (df["scoring_format"] == "half_ppr").all()


def test_fail_open_on_empty_payload(tmp_path):
    """Empty payload from fail-open helper → no Parquet written, exit 0."""
    out_root = tmp_path / "bronze"
    empty_proj = tmp_path / "empty.json"
    empty_proj.write_text("{}", encoding="utf-8")
    empty_reg = tmp_path / "empty_reg.json"
    empty_reg.write_text("{}", encoding="utf-8")

    rc = subprocess.call(
        [
            sys.executable,
            str(_INGESTER),
            "--season", "2025",
            "--week", "1",
            "--out-root", str(out_root),
            "--registry-fixture", str(empty_reg),
            "--projections-fixture", str(empty_proj),
        ]
    )
    assert rc == 0
    week_dir = out_root / "sleeper" / "season=2025" / "week=01"
    assert not week_dir.exists() or not list(week_dir.glob("*.parquet"))
