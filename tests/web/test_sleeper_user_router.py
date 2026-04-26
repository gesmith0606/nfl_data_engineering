"""Tests for /api/sleeper/* endpoints (Phase 74 SLEEP-01..04)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.api.main import app

client = TestClient(app)


_USER_PAYLOAD = {
    "user_id": "12345",
    "username": "testuser",
    "display_name": "Test User",
    "avatar": "abcd",
}

_LEAGUES_PAYLOAD = [
    {
        "league_id": "L1",
        "name": "Test League 1",
        "season": "2025",
        "total_rosters": 12,
        "sport": "nfl",
        "status": "in_season",
        "settings": {"playoff_teams": 6},
    },
    {
        "league_id": "L2",
        "name": "Test League 2",
        "season": "2025",
        "total_rosters": 10,
        "sport": "nfl",
        "status": "in_season",
    },
]

_REGISTRY_PAYLOAD = {
    "00-001": {"full_name": "Patrick Mahomes", "team": "KC", "position": "QB"},
    "00-002": {"full_name": "Christian McCaffrey", "team": "SF", "position": "RB"},
    "00-003": {"full_name": "Tyreek Hill", "team": "MIA", "position": "WR"},
}

_ROSTERS_PAYLOAD = [
    {
        "roster_id": 1,
        "owner_id": "12345",
        "starters": ["00-001", "00-002"],
        "players": ["00-001", "00-002", "00-003"],
    },
    {
        "roster_id": 2,
        "owner_id": "67890",
        "starters": ["00-003"],
        "players": ["00-003"],
    },
]


def _fetch_side_effect(url, *args, **kwargs):
    """Side-effect that returns appropriate payload based on URL pattern."""
    if "/user/" in url and "/leagues/" not in url:
        return _USER_PAYLOAD
    if "/leagues/" in url and "nfl/" in url:
        return _LEAGUES_PAYLOAD
    if "/players/nfl" in url:
        return _REGISTRY_PAYLOAD
    if "/league/" in url and "/rosters" in url:
        return _ROSTERS_PAYLOAD
    return {}


class TestSleeperUserLogin:
    def test_login_returns_user_and_leagues(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            side_effect=_fetch_side_effect,
        ):
            resp = client.post(
                "/api/sleeper/user/login", json={"username": "testuser"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["user_id"] == "12345"
        assert data["user"]["username"] == "testuser"
        assert len(data["leagues"]) == 2
        assert data["leagues"][0]["league_id"] == "L1"

    def test_login_sets_session_cookie(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            side_effect=_fetch_side_effect,
        ):
            resp = client.post(
                "/api/sleeper/user/login", json={"username": "testuser"}
            )
        assert resp.status_code == 200
        assert "sleeper_user_id" in resp.cookies
        assert resp.cookies["sleeper_user_id"] == "12345"

    def test_login_404_when_user_missing(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            return_value={},
        ):
            resp = client.post(
                "/api/sleeper/user/login", json={"username": "doesnotexist"}
            )
        assert resp.status_code == 404

    def test_login_400_when_username_empty(self):
        resp = client.post("/api/sleeper/user/login", json={"username": ""})
        assert resp.status_code == 400


class TestListUserLeagues:
    def test_list_leagues_returns_array(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            return_value=_LEAGUES_PAYLOAD,
        ):
            resp = client.get("/api/sleeper/leagues/12345?season=2025")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["league_id"] == "L1"

    def test_list_leagues_fail_open_empty(self):
        """D-06: Sleeper outage returns 200 with empty list."""
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            return_value={},
        ):
            resp = client.get("/api/sleeper/leagues/12345?season=2025")
        assert resp.status_code == 200
        assert resp.json() == []


class TestListLeagueRosters:
    def test_rosters_marks_user_roster(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            side_effect=_fetch_side_effect,
        ):
            resp = client.get("/api/sleeper/rosters/L1?user_id=12345")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Roster 1 belongs to user 12345 → is_user_roster=True
        user_roster = next(r for r in data if r["roster_id"] == 1)
        assert user_roster["is_user_roster"] is True
        # Roster 2 belongs to 67890 → is_user_roster=False
        other_roster = next(r for r in data if r["roster_id"] == 2)
        assert other_roster["is_user_roster"] is False

    def test_rosters_resolves_player_metadata(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            side_effect=_fetch_side_effect,
        ):
            resp = client.get("/api/sleeper/rosters/L1?user_id=12345")
        data = resp.json()
        user_roster = next(r for r in data if r["roster_id"] == 1)
        # Starter 00-001 → Mahomes/KC/QB
        starters = user_roster["starters"]
        mahomes = next(p for p in starters if p["player_id"] == "00-001")
        assert mahomes["player_name"] == "Patrick Mahomes"
        assert mahomes["team"] == "KC"
        assert mahomes["position"] == "QB"

    def test_rosters_separates_starters_and_bench(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            side_effect=_fetch_side_effect,
        ):
            resp = client.get("/api/sleeper/rosters/L1?user_id=12345")
        data = resp.json()
        user_roster = next(r for r in data if r["roster_id"] == 1)
        # Players list: [001, 002, 003], starters: [001, 002] → bench: [003]
        bench_ids = [p["player_id"] for p in user_roster["bench"]]
        assert bench_ids == ["00-003"]

    def test_rosters_fail_open_empty(self):
        with patch(
            "web.api.routers.sleeper_user.fetch_sleeper_json",
            return_value={},
        ):
            resp = client.get("/api/sleeper/rosters/L1?user_id=12345")
        assert resp.status_code == 200
        assert resp.json() == []
