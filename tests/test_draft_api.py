"""
Tests for the Draft API endpoints (/api/draft/*).

Uses mock projection data to avoid network dependencies on nfl-data-py.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from web.api.main import app

# Ensure src/ is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

client = TestClient(app)


# ---------------------------------------------------------------------------
# Synthetic data for mocking
# ---------------------------------------------------------------------------

def _make_mock_projections() -> pd.DataFrame:
    """Create a small synthetic projection DataFrame."""
    players = [
        ("P001", "Patrick Mahomes", "QB", "KC", 380.0),
        ("P002", "Josh Allen", "QB", "BUF", 370.0),
        ("P003", "Jalen Hurts", "QB", "PHI", 350.0),
        ("P004", "Christian McCaffrey", "RB", "SF", 320.0),
        ("P005", "Breece Hall", "RB", "NYJ", 280.0),
        ("P006", "Bijan Robinson", "RB", "ATL", 275.0),
        ("P007", "Jahmyr Gibbs", "RB", "DET", 260.0),
        ("P008", "Ja'Marr Chase", "WR", "CIN", 300.0),
        ("P009", "Tyreek Hill", "WR", "MIA", 290.0),
        ("P010", "CeeDee Lamb", "WR", "DAL", 285.0),
        ("P011", "Amon-Ra St. Brown", "WR", "DET", 270.0),
        ("P012", "Travis Kelce", "TE", "KC", 250.0),
        ("P013", "Sam LaPorta", "TE", "DET", 200.0),
        ("P014", "Saquon Barkley", "RB", "PHI", 270.0),
        ("P015", "Davante Adams", "WR", "NYJ", 260.0),
        ("P016", "Lamar Jackson", "QB", "BAL", 360.0),
        ("P017", "Jonathan Taylor", "RB", "IND", 265.0),
        ("P018", "A.J. Brown", "WR", "PHI", 275.0),
        ("P019", "George Kittle", "TE", "SF", 195.0),
        ("P020", "Kyren Williams", "RB", "LAR", 255.0),
    ]
    df = pd.DataFrame(players, columns=["player_id", "player_name", "position", "recent_team", "projected_season_points"])
    return df


def _mock_load_draft_data(scoring: str, season: int) -> pd.DataFrame:
    """Mock replacement for _load_draft_data that returns synthetic data."""
    from draft_optimizer import compute_value_scores
    return compute_value_scores(_make_mock_projections())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_load_draft_data():
    """Patch _load_draft_data to avoid network calls."""
    with patch("web.api.routers.draft._load_draft_data", side_effect=_mock_load_draft_data):
        yield


@pytest.fixture(scope="function")
def draft_session(_patch_load_draft_data):
    """Create a draft session. Returns the full JSON response."""
    # Clear sessions between tests
    from web.api.routers import draft as draft_module
    draft_module._sessions.clear()

    resp = client.get(
        "/api/draft/board",
        params={"scoring": "half_ppr", "roster_format": "standard", "n_teams": 12, "season": 2026},
    )
    assert resp.status_code == 200, f"Board creation failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test: GET /api/draft/board
# ---------------------------------------------------------------------------


class TestDraftBoard:
    """Tests for the draft board endpoint."""

    def test_creates_session(self, draft_session):
        """GET /api/draft/board creates a new session with players."""
        assert draft_session["session_id"]
        assert isinstance(draft_session["players"], list)
        assert len(draft_session["players"]) > 0
        assert draft_session["my_roster"] == []
        assert draft_session["picks_taken"] == 0
        assert draft_session["scoring_format"] == "half_ppr"
        assert draft_session["roster_format"] == "standard"
        assert draft_session["n_teams"] == 12

    def test_player_fields(self, draft_session):
        """Each player has the expected schema fields."""
        player = draft_session["players"][0]
        assert "player_id" in player
        assert "player_name" in player
        assert "position" in player
        assert "projected_points" in player
        assert "model_rank" in player
        assert "vorp" in player
        assert "value_tier" in player

    def test_reuse_session(self, draft_session):
        """GET /api/draft/board with existing session_id returns same state."""
        sid = draft_session["session_id"]
        resp = client.get("/api/draft/board", params={"session_id": sid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert len(data["players"]) == len(draft_session["players"])


# ---------------------------------------------------------------------------
# Test: POST /api/draft/pick
# ---------------------------------------------------------------------------


class TestDraftPick:
    """Tests for the draft pick endpoint."""

    def test_pick_valid_player(self, draft_session):
        """POST /api/draft/pick with valid player_id records the pick."""
        sid = draft_session["session_id"]
        player_id = draft_session["players"][0]["player_id"]

        resp = client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": player_id, "by_me": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["player"]["player_id"] == player_id
        assert "Drafted" in data["message"]

    def test_pick_updates_board(self, draft_session):
        """After a pick, the board reflects the change."""
        sid = draft_session["session_id"]
        player_id = draft_session["players"][0]["player_id"]
        original_count = len(draft_session["players"])

        client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": player_id, "by_me": True},
        )

        resp = client.get("/api/draft/board", params={"session_id": sid})
        data = resp.json()
        assert len(data["players"]) == original_count - 1
        assert data["my_pick_count"] == 1
        assert data["picks_taken"] == 1
        assert len(data["my_roster"]) == 1

    def test_pick_invalid_session(self):
        """POST /api/draft/pick with fake session_id returns 404."""
        resp = client.post(
            "/api/draft/pick",
            json={"session_id": "nonexistent_session_id", "player_id": "X", "by_me": True},
        )
        assert resp.status_code == 404

    def test_pick_invalid_player(self, draft_session):
        """POST /api/draft/pick with bad player_id returns 400."""
        sid = draft_session["session_id"]
        resp = client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": "ZZZZZ_NOT_REAL", "by_me": True},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: GET /api/draft/recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    """Tests for the recommendations endpoint."""

    def test_recommendations(self, draft_session):
        """GET /api/draft/recommendations returns non-empty list."""
        sid = draft_session["session_id"]
        resp = client.get(
            "/api/draft/recommendations", params={"session_id": sid, "top_n": 5}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) > 0
        assert isinstance(data["reasoning"], str)
        assert isinstance(data["remaining_needs"], dict)

    def test_recommendations_with_position(self, draft_session):
        """GET /api/draft/recommendations with position filter works."""
        sid = draft_session["session_id"]
        resp = client.get(
            "/api/draft/recommendations",
            params={"session_id": sid, "top_n": 3, "position": "QB"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for rec in data["recommendations"]:
            assert rec["position"] == "QB"

    def test_recommendations_invalid_session(self):
        """GET /api/draft/recommendations with bad session returns 404."""
        resp = client.get(
            "/api/draft/recommendations",
            params={"session_id": "bad_session", "top_n": 5},
        )
        assert resp.status_code == 404

    def test_recommendation_fields(self, draft_session):
        """Recommendations include all expected fields."""
        sid = draft_session["session_id"]
        resp = client.get(
            "/api/draft/recommendations", params={"session_id": sid, "top_n": 1}
        )
        rec = resp.json()["recommendations"][0]
        assert "player_id" in rec
        assert "player_name" in rec
        assert "position" in rec
        assert "projected_points" in rec
        assert "model_rank" in rec
        assert "vorp" in rec
        assert "recommendation_score" in rec


# ---------------------------------------------------------------------------
# Test: POST /api/draft/mock/start & POST /api/draft/mock/pick
# ---------------------------------------------------------------------------


class TestMockDraft:
    """Tests for mock draft start and pick advancement."""

    def test_mock_start(self):
        """POST /api/draft/mock/start returns a session_id."""
        resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 1, "season": 2026},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "message" in data
        assert "12 teams" in data["message"]

    def test_mock_start_invalid_pick(self):
        """POST /api/draft/mock/start with user_pick > n_teams returns 400."""
        resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 15},
        )
        assert resp.status_code == 400

    def test_mock_pick_advances(self):
        """POST /api/draft/mock/pick advances the pick number."""
        start_resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 1, "season": 2026},
        )
        sid = start_resp.json()["session_id"]

        resp = client.post("/api/draft/mock/pick", json={"session_id": sid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["pick_number"] >= 1
        assert data["round_number"] >= 1
        assert data["player_name"] is not None

    def test_mock_pick_multiple(self):
        """Multiple mock picks advance sequentially."""
        start_resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 4, "user_pick": 1, "season": 2026},
        )
        sid = start_resp.json()["session_id"]

        pick_numbers = []
        for _ in range(4):
            resp = client.post("/api/draft/mock/pick", json={"session_id": sid})
            assert resp.status_code == 200
            pick_numbers.append(resp.json()["pick_number"])

        assert pick_numbers == [1, 2, 3, 4]

    def test_mock_pick_invalid_session(self):
        """POST /api/draft/mock/pick with bad session returns 404."""
        resp = client.post(
            "/api/draft/mock/pick", json={"session_id": "no_such_session"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: GET /api/draft/adp
# ---------------------------------------------------------------------------


class TestAdp:
    """Tests for the ADP endpoint."""

    def test_adp_response(self):
        """GET /api/draft/adp returns 200 or 404 depending on file existence."""
        resp = client.get("/api/draft/adp")
        # No ADP file in test env -- expect 404
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data["players"], list)
            assert data["source"] == "adp_latest.csv"
