"""Contract tests for external_rankings_service cache-first fallback behavior.

These tests pin the ADVR-03 guarantee: `compare_rankings()` always returns a
well-formed envelope with `stale`, `cache_age_hours`, and `last_updated` keys,
regardless of whether the live source is reachable or the on-disk cache exists.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from web.api.services import external_rankings_service as svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the service's EXTERNAL_DIR to a clean tmp dir for each test."""
    tmp_external = tmp_path / "external"
    tmp_external.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(svc, "EXTERNAL_DIR", tmp_external)
    return tmp_external


@pytest.fixture
def empty_projections(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force _load_our_projections to return an empty DataFrame.

    Keeps these tests focused on external-fetch behavior rather than Gold parquet
    availability (covered separately in tests/test_web_api.py).
    """
    import pandas as pd

    monkeypatch.setattr(svc, "_load_our_projections", lambda **kwargs: pd.DataFrame())


def _fake_sleeper_players_payload(n: int = 25) -> Dict[str, Dict[str, Any]]:
    """Build a minimal but realistic Sleeper `/v1/players/nfl` payload."""
    players: Dict[str, Dict[str, Any]] = {}
    positions = ["RB", "QB", "WR", "TE"]
    for i in range(n):
        pos = positions[i % 4]
        players[f"pid-{i}"] = {
            "player_id": f"pid-{i}",
            "full_name": f"Player {i}",
            "first_name": "Player",
            "last_name": str(i),
            "position": pos,
            "team": "KC",
            "search_rank": i + 1,
            "status": "Active",
        }
    return players


class _FakeResponse:
    """Minimal stand-in for a `requests.Response` object."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_live_fetch_happy_path(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live source returns fresh data -> stale=False, cache_age_hours=None."""
    payload = _fake_sleeper_players_payload(n=30)

    def fake_get(url: str, timeout: int = 0, headers: Dict[str, str] | None = None):
        return _FakeResponse(payload, status_code=200)

    monkeypatch.setattr(svc.requests, "get", fake_get)

    result = svc.compare_rankings(source="sleeper", limit=20)

    assert result["source"] == "sleeper"
    assert result["stale"] is False
    assert result["cache_age_hours"] is None
    assert isinstance(result["last_updated"], str)
    # last_updated should parse as ISO-8601
    datetime.fromisoformat(result["last_updated"].replace("Z", "+00:00"))
    assert len(result["players"]) > 0
    # Cache file should now exist with the canonical envelope
    cache_path = tmp_cache_dir / "sleeper_rankings.json"
    assert cache_path.exists()
    envelope = json.loads(cache_path.read_text())
    assert envelope["source"] == "sleeper"
    assert "fetched_at" in envelope
    assert isinstance(envelope["players"], list)
    assert len(envelope["players"]) >= 20


@pytest.mark.unit
def test_live_blocked_falls_back_to_cache(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live fetch raises -> serve stale cache with stale=True and cache_age_hours>=0."""
    import requests

    # Pre-populate cache in canonical envelope format
    cache_path = tmp_cache_dir / "sleeper_rankings.json"
    cached_envelope = {
        "source": "sleeper",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players": [
            {
                "player_name": f"CachedPlayer {i}",
                "position": "RB",
                "team": "KC",
                "external_rank": i + 1,
                "rank": i + 1,
            }
            for i in range(25)
        ],
    }
    cache_path.write_text(json.dumps(cached_envelope))

    def fake_get(*a: Any, **kw: Any):
        raise requests.ConnectionError("network blocked")

    monkeypatch.setattr(svc.requests, "get", fake_get)

    result = svc.compare_rankings(source="sleeper", limit=20)

    assert result["source"] == "sleeper"
    assert result["stale"] is True
    assert result["cache_age_hours"] is not None
    assert result["cache_age_hours"] >= 0
    assert len(result["players"]) > 0


@pytest.mark.unit
def test_no_cache_no_live_returns_empty_stale(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cache + live fail -> stale=True, players=[], NO exception raised."""
    import requests

    def fake_get(*a: Any, **kw: Any):
        raise requests.ConnectionError("blocked")

    monkeypatch.setattr(svc.requests, "get", fake_get)

    # Cache dir is empty (tmp)
    assert not (tmp_cache_dir / "sleeper_rankings.json").exists()

    # Must not raise
    result = svc.compare_rankings(source="sleeper", limit=20)

    assert result["source"] == "sleeper"
    assert result["stale"] is True
    assert result["cache_age_hours"] is None
    assert result["players"] == []


@pytest.mark.unit
def test_rank_diff_math(
    tmp_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rank_diff = external_rank - our_rank, None iff our_rank is None."""
    import pandas as pd

    # Our projections have two players matching external rows 1 and 2 (both at our_rank 2).
    # Player 3 is unmatched in our projections, so our_rank=None, rank_diff=None.
    our_df = pd.DataFrame(
        [
            {"player_name": "Alice", "position": "RB", "team": "KC", "our_rank": 2, "projected_points": 18.0},
            {"player_name": "Bob", "position": "RB", "team": "KC", "our_rank": 2, "projected_points": 17.5},
        ]
    )

    def fake_load_our_projections(**kwargs: Any) -> pd.DataFrame:
        return our_df

    monkeypatch.setattr(svc, "_load_our_projections", fake_load_our_projections)

    # Seed a canonical cache with three players
    cache_path = tmp_cache_dir / "sleeper_rankings.json"
    cached_envelope = {
        "source": "sleeper",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players": [
            {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 1, "rank": 1},
            {"player_name": "Bob", "position": "RB", "team": "KC", "external_rank": 2, "rank": 2},
            {"player_name": "Carol", "position": "RB", "team": "KC", "external_rank": 3, "rank": 3},
        ],
    }
    cache_path.write_text(json.dumps(cached_envelope))

    import requests

    def fake_get(*a: Any, **kw: Any):
        raise requests.ConnectionError("blocked")  # Force cache-fallback

    monkeypatch.setattr(svc.requests, "get", fake_get)

    result = svc.compare_rankings(source="sleeper", limit=10)

    assert len(result["players"]) == 3
    by_name = {p["player_name"]: p for p in result["players"]}
    # external 1 - our 2 = -1
    assert by_name["Alice"]["rank_diff"] == -1
    # external 2 - our 2 = 0
    assert by_name["Bob"]["rank_diff"] == 0
    # Carol is unmatched -> our_rank None -> rank_diff None
    assert by_name["Carol"]["our_rank"] is None
    assert by_name["Carol"]["rank_diff"] is None


@pytest.mark.unit
def test_position_filter_respected(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When position=RB is passed, every returned player has position == 'RB'."""
    payload = _fake_sleeper_players_payload(n=40)

    def fake_get(*a: Any, **kw: Any):
        return _FakeResponse(payload, status_code=200)

    monkeypatch.setattr(svc.requests, "get", fake_get)

    result = svc.compare_rankings(source="sleeper", position="RB", limit=50)

    assert len(result["players"]) > 0
    for player in result["players"]:
        assert player["position"] == "RB"


@pytest.mark.unit
def test_consensus_averages_three_sources(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """consensus source merges Sleeper/FantasyPros/ESPN into averaged ranks."""
    # Fake three identical player sets with different ranks:
    # Sleeper ranks Alice=1, Bob=2
    # FantasyPros ranks Alice=3, Bob=2
    # ESPN ranks Alice=5, Bob=2
    # Expected consensus: Alice = mean(1,3,5) = 3.0 ; Bob = 2.0
    def make_sleeper_payload() -> Dict[str, Dict[str, Any]]:
        return {
            "p1": {"full_name": "Alice", "position": "RB", "team": "KC", "search_rank": 1, "status": "Active"},
            "p2": {"full_name": "Bob", "position": "RB", "team": "KC", "search_rank": 2, "status": "Active"},
        }

    def make_fantasypros_payload() -> Dict[str, Any]:
        return {
            "players": [
                {"player_name": "Alice", "position": "RB", "player_team_id": "KC", "rank_ecr": 3},
                {"player_name": "Bob", "position": "RB", "player_team_id": "KC", "rank_ecr": 2},
            ]
        }

    def make_espn_payload() -> Dict[str, Any]:
        return {
            "players": [
                {"player": {"fullName": "Alice", "defaultPositionId": 2, "proTeamId": 12}},
                {"player": {"fullName": "Bob", "defaultPositionId": 2, "proTeamId": 12}},
            ]
        }

    def fake_get(url: str, *a: Any, **kw: Any):
        if "sleeper.app" in url:
            return _FakeResponse(make_sleeper_payload(), status_code=200)
        if "fantasypros.com" in url:
            return _FakeResponse(make_fantasypros_payload(), status_code=200)
        if "espn.com" in url:
            return _FakeResponse(make_espn_payload(), status_code=200)
        return _FakeResponse({}, status_code=404)

    monkeypatch.setattr(svc.requests, "get", fake_get)

    result = svc.compare_rankings(source="consensus", limit=5)

    by_name = {p["player_name"]: p for p in result["players"]}
    assert "Alice" in by_name
    assert "Bob" in by_name
    assert by_name["Alice"]["external_rank"] == pytest.approx(3.0, abs=0.01)
    assert by_name["Bob"]["external_rank"] == pytest.approx(2.0, abs=0.01)


@pytest.mark.unit
def test_response_envelope_keys_present_even_on_empty(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every code path returns the full envelope shape the advisor depends on."""
    import requests

    def fake_get(*a: Any, **kw: Any):
        raise requests.ConnectionError("blocked")

    monkeypatch.setattr(svc.requests, "get", fake_get)

    result = svc.compare_rankings(source="sleeper", limit=10)

    required_keys = {
        "source",
        "scoring_format",
        "position_filter",
        "players",
        "stale",
        "cache_age_hours",
        "last_updated",
    }
    assert required_keys.issubset(result.keys()), (
        f"Envelope missing keys: {required_keys - result.keys()}"
    )
