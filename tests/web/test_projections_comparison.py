"""Tests for /api/projections/comparison endpoint (Plan 73-03)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from web.api.main import app


client = TestClient(app)


def _make_silver_df():
    return pd.DataFrame(
        [
            {
                "player_id": "00-001",
                "player_name": "Patrick Mahomes",
                "position": "QB",
                "team": "KC",
                "source": "ours",
                "scoring_format": "half_ppr",
                "projected_points": 25.0,
                "projected_at": "2026-04-25T12:00:00+00:00",
                "season": 2025,
                "week": 1,
            },
            {
                "player_id": "00-001",
                "player_name": "Patrick Mahomes",
                "position": "QB",
                "team": "KC",
                "source": "espn",
                "scoring_format": "half_ppr",
                "projected_points": 22.4,
                "projected_at": "2026-04-25T12:00:00+00:00",
                "season": 2025,
                "week": 1,
            },
            {
                "player_id": "00-001",
                "player_name": "Patrick Mahomes",
                "position": "QB",
                "team": "KC",
                "source": "sleeper",
                "scoring_format": "half_ppr",
                "projected_points": 21.8,
                "projected_at": "2026-04-25T12:00:00+00:00",
                "season": 2025,
                "week": 1,
            },
            {
                "player_id": "00-001",
                "player_name": "Patrick Mahomes",
                "position": "QB",
                "team": "KC",
                "source": "yahoo_proxy_fp",
                "scoring_format": "half_ppr",
                "projected_points": 23.1,
                "projected_at": "2026-04-25T12:00:00+00:00",
                "season": 2025,
                "week": 1,
            },
        ]
    )


@pytest.fixture
def silver_fixture(tmp_path, monkeypatch):
    silver_root = tmp_path / "silver" / "external_projections"
    week_dir = silver_root / "season=2025" / "week=01"
    week_dir.mkdir(parents=True)
    out = week_dir / "external_projections.parquet"
    _make_silver_df().to_parquet(out, index=False)
    # C-01 fix: service now anchors to DATA_DIR (env-overridable). Patch
    # the module-level DATA_DIR to point at our tmp tree.
    from web.api.services import projection_service
    monkeypatch.setattr(projection_service, "DATA_DIR", tmp_path)
    return tmp_path


def test_comparison_endpoint_returns_4_sources(silver_fixture):
    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2025, "week": 1, "scoring": "half_ppr"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["season"] == 2025
    assert data["week"] == 1
    assert data["scoring_format"] == "half_ppr"
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["player_name"] == "Patrick Mahomes"
    assert row["ours"] == 25.0
    assert row["espn"] == 22.4
    assert row["sleeper"] == 21.8
    assert row["yahoo"] == 23.1
    # delta_vs_ours = avg(externals) - ours = (22.4+21.8+23.1)/3 - 25.0 ≈ -2.57
    assert row["delta_vs_ours"] == round((22.4 + 21.8 + 23.1) / 3 - 25.0, 2)


def test_comparison_endpoint_yahoo_proxy_fp_renamed_to_yahoo(silver_fixture):
    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2025, "week": 1, "scoring": "half_ppr"},
    )
    data = resp.json()
    # Source labels expose the provenance for the UI tooltip
    assert "yahoo" in data["source_labels"]
    assert "FantasyPros" in data["source_labels"]["yahoo"]


def test_comparison_endpoint_returns_empty_when_no_silver(tmp_path, monkeypatch):
    """D-06 fail-open: missing Silver → empty rows, status 200."""
    from web.api.services import projection_service
    monkeypatch.setattr(projection_service, "DATA_DIR", tmp_path)
    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2030, "week": 1, "scoring": "half_ppr"},
    )
    assert resp.status_code == 200
    assert resp.json()["rows"] == []


def test_comparison_endpoint_validates_scoring():
    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2025, "week": 1, "scoring": "bogus"},
    )
    assert resp.status_code == 400


def test_comparison_endpoint_filters_by_position(silver_fixture):
    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2025, "week": 1, "scoring": "half_ppr", "position": "RB"},
    )
    data = resp.json()
    # No RB in fixture → empty
    assert data["rows"] == []
