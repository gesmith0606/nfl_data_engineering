"""Smoke tests for /api/tools and /api/espn routers (market-gap sprint)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web.api.routers.tools as tools_mod
from web.api.main import app

client = TestClient(app)


def _skip_if_no_data(resp):
    if resp.status_code in (404, 503):
        pytest.skip("gold/silver parquet not on disk")


def test_ros_rankings_sorted_and_prorated():
    resp = client.get("/api/tools/ros?season=2026&week=10&limit=20")
    _skip_if_no_data(resp)
    assert resp.status_code == 200
    body = resp.json()
    assert body["weeks_remaining"] == 9
    pts = [p["ros_points"] for p in body["players"]]
    assert pts == sorted(pts, reverse=True) and len(pts) <= 20
    # Proration: ros < season points mid-season.
    top = body["players"][0]
    assert 0 < top["ros_points"] < top["projected_season_points"]


def test_ros_schedule_aware_sorted_and_bounded():
    """Schedule/injury-aware ROS: still sorted desc, still <= season points mid-season."""
    resp = client.get("/api/tools/ros?season=2026&week=10&limit=25")
    _skip_if_no_data(resp)
    assert resp.status_code == 200
    players = resp.json()["players"]
    pts = [p["ros_points"] for p in players]
    assert pts == sorted(pts, reverse=True)
    for p in players:
        assert 0 <= p["ros_points"] <= p["projected_season_points"]


def test_ros_fails_open_when_schedule_missing(monkeypatch):
    """No schedule/rank parquet on disk -> linear remaining/18 fallback, still 200.

    DATA_DIR backs both the schedule and defense-rank globs in tools.py, but
    NOT the preseason-projection loader (anchored separately in
    src/projection_store.py) — so pointing it at an empty directory
    exercises the fail-open path without also breaking projection loading.
    """
    monkeypatch.setattr(tools_mod, "DATA_DIR", Path("Z:/does/not/exist"))
    resp = client.get("/api/tools/ros?season=2026&week=10&limit=20")
    _skip_if_no_data(resp)
    assert resp.status_code == 200
    body = resp.json()
    remaining = body["weeks_remaining"]
    for p in body["players"]:
        expected = round(p["projected_season_points"] * remaining / 18, 1)
        assert p["ros_points"] == expected


def test_trade_verdict_consistent():
    ros = client.get("/api/tools/ros?season=2026&limit=6")
    _skip_if_no_data(ros)
    ids = [p["player_id"] for p in ros.json()["players"]]
    resp = client.post(
        "/api/tools/trade",
        json={"side_a": ids[:1], "side_b": ids[1:3], "season": 2026},
    )
    assert resp.status_code == 200
    body = resp.json()
    delta = round(
        body["side_b"]["total_ros_points"] - body["side_a"]["total_ros_points"], 1
    )
    assert body["delta_ros_points"] == delta


def test_trade_unmatched_ids_count_zero():
    resp = client.post(
        "/api/tools/trade",
        json={"side_a": ["nope-1"], "side_b": ["nope-2"], "season": 2026},
    )
    _skip_if_no_data(resp)
    body = resp.json()
    assert body["side_a"]["unmatched_player_ids"] == ["nope-1"]
    assert body["side_a"]["total_ros_points"] == 0


def test_compare_requires_two_ids():
    resp = client.get("/api/tools/compare?ids=only-one&season=2025&week=18")
    assert resp.status_code == 400


def test_sos_grid_regular_season_only():
    resp = client.get("/api/tools/sos")
    _skip_if_no_data(resp)
    body = resp.json()
    assert body["week"] <= 18
    assert len(body["cells"]) >= 100  # ~32 teams x 4 positions


def test_depth_charts_deduped():
    resp = client.get("/api/tools/depth-charts?season=2026&team=PHI")
    _skip_if_no_data(resp)
    entries = resp.json()["entries"]
    assert 0 < len(entries) < 60
    keys = [(e["position"], e["depth_rank"], e["player_name"]) for e in entries]
    assert len(keys) == len(set(keys))


def test_injuries_shape():
    resp = client.get("/api/tools/injuries?season=2025&week=18")
    _skip_if_no_data(resp)
    for p in resp.json()["players"][:5]:
        assert p["injury_status"]


def test_espn_import_validates():
    # No network in unit tests — invalid body only.
    resp = client.post("/api/espn/import", json={"league_id": "x"})
    assert resp.status_code == 422


def test_compare_404_when_no_weekly_parquet():
    # 2030 has no weekly Gold data — the preseason fallback must NOT leak
    # season-long numbers through the weekly comparator.
    resp = client.get("/api/tools/compare?ids=a,b&season=2030&week=1")
    assert resp.status_code == 404


def test_injuries_404_when_no_weekly_parquet():
    resp = client.get("/api/tools/injuries?season=2030&week=1")
    assert resp.status_code == 404
