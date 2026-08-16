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


def test_comparison_endpoint_falls_back_to_latest_available_slice(silver_fixture):
    """P1 audit 2026-08-01: requesting a season/week that has never been
    ingested (e.g. 2026, since weekly-external-projections.yml never wrote a
    2026 partition) must not silently serve an all-null comparison — it
    should walk back to the latest real slice and label it as a fallback.
    """
    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2026, "week": 1, "scoring": "half_ppr"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Requested slice echoed back...
    assert data["season"] == 2026
    assert data["week"] == 1
    # ...but the real data (from season=2025/week=01 in the fixture) is what
    # actually gets served, honestly labeled as a fallback.
    assert data["fallback"] is True
    assert data["fallback_season"] == 2025
    assert data["fallback_week"] == 1
    assert len(data["rows"]) == 1
    assert data["rows"][0]["player_name"] == "Patrick Mahomes"


def test_comparison_endpoint_no_fallback_flag_on_exact_match(silver_fixture):
    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2025, "week": 1, "scoring": "half_ppr"},
    )
    data = resp.json()
    assert data["fallback"] is False
    assert data["fallback_season"] is None
    assert data["fallback_week"] is None


def test_comparison_endpoint_overlays_live_ours_when_archive_missing_it(
    tmp_path, monkeypatch
):
    """A stale archived Silver snapshot (weekly-external-projections.yml ran
    before our own Gold weekly projections existed for that slice) must not
    permanently blank the "ours" column -- live Gold data for the same
    resolved (season, week) should be joined in instead of leaving dashes.
    """
    from web.api.services import projection_service

    # Silver snapshot has externals only (mirrors the real
    # season=2025/week=18 snapshot: sleeper rows, zero "ours" rows).
    silver_root = tmp_path / "silver" / "external_projections"
    week_dir = silver_root / "season=2025" / "week=18"
    week_dir.mkdir(parents=True)
    silver_df = pd.DataFrame(
        [
            {
                "player_id": "00-001",
                "player_name": "Patrick Mahomes",
                "position": "QB",
                "team": "KC",
                "source": "sleeper",
                "scoring_format": "half_ppr",
                "projected_points": 21.8,
                "projected_at": "2026-06-11T00:43:37+00:00",
                "season": 2025,
                "week": 18,
            }
        ]
    )
    silver_df.to_parquet(week_dir / "external_projections.parquet", index=False)
    monkeypatch.setattr(projection_service, "DATA_DIR", tmp_path)

    # Live Gold weekly projections for the same resolved slice, generated
    # AFTER the archived Silver snapshot -- this is what should win.
    gold_root = tmp_path / "gold" / "projections"
    gold_week_dir = gold_root / "season=2025" / "week=18"
    gold_week_dir.mkdir(parents=True)
    gold_df = pd.DataFrame(
        [
            {
                "player_id": "00-001",
                "player_name": "Patrick Mahomes",
                "position": "QB",
                "recent_team": "KC",
                "projected_points": 25.0,
            }
        ]
    )
    gold_df.to_parquet(
        gold_week_dir / "projections_half_ppr_20260702_143534.parquet", index=False
    )
    monkeypatch.setattr(projection_service, "GOLD_PROJECTIONS_DIR", gold_root)

    resp = client.get(
        "/api/projections/comparison",
        params={"season": 2025, "week": 18, "scoring": "half_ppr"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["ours"] == 25.0
    assert row["sleeper"] == 21.8
    assert row["delta_vs_ours"] == round(21.8 - 25.0, 2)
