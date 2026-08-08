"""Tests for GET /api/report/weekly -- auto-generated weekly digest."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api.routers import weekly_report

app = FastAPI()
app.include_router(weekly_report.router, prefix="/api")
client = TestClient(app)


def _skip_if_no_data(resp):
    if resp.status_code in (404, 503):
        pytest.skip("gold/silver parquet not on disk")


def test_weekly_report_2025_week18_populated_and_sorted():
    resp = client.get("/api/report/weekly?season=2025&week=18&scoring=half_ppr")
    _skip_if_no_data(resp)
    assert resp.status_code == 200
    body = resp.json()

    assert body["mode"] == "weekly"
    assert body["headline"]["season"] == 2025
    assert body["headline"]["week"] == 18
    assert body["headline"]["generated_from"]

    # top_projected: top 5 per QB/RB/WR/TE, sorted desc by projected_points
    top = body["top_projected"]
    for pos in ("QB", "RB", "WR", "TE"):
        assert pos in top
        players = top[pos]
        assert 0 < len(players) <= 5
        pts = [p["projected_points"] for p in players]
        assert pts == sorted(pts, reverse=True)
        for p in players:
            assert p["position"] == pos
            assert "player_id" in p and "player_name" in p

    # injury_watch: at most 10, every entry carries a non-empty injury_status
    injuries = body["injury_watch"]
    assert len(injuries) <= 10
    for p in injuries:
        assert p["injury_status"]

    # matchup_spotlight: 5 best + 5 worst (team, position) cells
    spotlight = body["matchup_spotlight"]
    assert len(spotlight["best"]) <= 5
    assert len(spotlight["worst"]) <= 5
    if spotlight["best"] and spotlight["worst"]:
        best_ranks = [c["opp_rank"] for c in spotlight["best"]]
        worst_ranks = [c["opp_rank"] for c in spotlight["worst"]]
        # best = opponent rank near 32 (easy matchup), worst = near 1 (tough)
        assert min(best_ranks) >= max(worst_ranks)

    # boom_bust: upside (widest ceiling-floor) + safe (highest floor ratio),
    # both drawn from players with projected_points >= 8.
    boom_bust = body["boom_bust"]
    assert len(boom_bust["upside"]) <= 5
    assert len(boom_bust["safe"]) <= 5
    for p in boom_bust["upside"] + boom_bust["safe"]:
        assert p["projected_points"] >= 8
    if boom_bust["upside"]:
        spreads = [p["ceiling_minus_floor"] for p in boom_bust["upside"]]
        assert spreads == sorted(spreads, reverse=True)
    if boom_bust["safe"]:
        ratios = [p["floor_ratio"] for p in boom_bust["safe"]]
        assert ratios == sorted(ratios, reverse=True)


def test_weekly_report_preseason_missing_week():
    # Max-valid future season has no Gold projections on disk at all
    # (neither weekly nor preseason vintage).
    resp = client.get("/api/report/weekly?season=2030&week=1&scoring=half_ppr")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "preseason"
    assert body["message"]
    assert body["top_projected"] == {}
    assert body["injury_watch"] == []
    assert body["matchup_spotlight"] == {"best": [], "worst": []}
    assert body["boom_bust"] == {"upside": [], "safe": []}


def test_weekly_report_invalid_scoring():
    resp = client.get("/api/report/weekly?season=2025&week=18&scoring=bogus")
    assert resp.status_code == 400
