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
            {
                "player_name": "Alice",
                "position": "RB",
                "team": "KC",
                "our_rank": 2,
                "projected_points": 18.0,
            },
            {
                "player_name": "Bob",
                "position": "RB",
                "team": "KC",
                "our_rank": 2,
                "projected_points": 17.5,
            },
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
            {
                "player_name": "Alice",
                "position": "RB",
                "team": "KC",
                "external_rank": 1,
                "rank": 1,
            },
            {
                "player_name": "Bob",
                "position": "RB",
                "team": "KC",
                "external_rank": 2,
                "rank": 2,
            },
            {
                "player_name": "Carol",
                "position": "RB",
                "team": "KC",
                "external_rank": 3,
                "rank": 3,
            },
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
    """consensus source merges Sleeper/FantasyPros/ESPN into averaged ranks.

    Each source exposes a per-row ``external_rank``. The consensus merge
    averages those external_rank values across every source that returned a
    row for the player.
    """

    # Per-source external_ranks the parsers will emit:
    #   Sleeper uses search_rank directly as external_rank
    #   FantasyPros uses rank_ecr as external_rank
    #   ESPN uses list position (1-indexed) as external_rank
    # Fixture below yields:
    #   Alice  Sleeper=1, FantasyPros=3, ESPN=5 -> mean = 3.0
    #   Bob    Sleeper=2, FantasyPros=2, ESPN=2 -> mean = 2.0
    def make_sleeper_payload() -> Dict[str, Dict[str, Any]]:
        return {
            "p1": {
                "full_name": "Alice",
                "position": "RB",
                "team": "KC",
                "search_rank": 1,
                "status": "Active",
            },
            "p2": {
                "full_name": "Bob",
                "position": "RB",
                "team": "KC",
                "search_rank": 2,
                "status": "Active",
            },
        }

    def make_fantasypros_payload() -> Dict[str, Any]:
        return {
            "players": [
                {
                    "player_name": "Alice",
                    "position": "RB",
                    "player_team_id": "KC",
                    "rank_ecr": 3,
                },
                {
                    "player_name": "Bob",
                    "position": "RB",
                    "player_team_id": "KC",
                    "rank_ecr": 2,
                },
            ]
        }

    def make_espn_payload() -> Dict[str, Any]:
        # ESPN parser sets external_rank = list position. To get Alice=5 and
        # Bob=2 we fill slots 1..4 with dummies above Alice and keep Bob at 2.
        return {
            "players": [
                {"player": {"fullName": "Z1", "defaultPositionId": 2, "proTeamId": 12}},
                {
                    "player": {
                        "fullName": "Bob",
                        "defaultPositionId": 2,
                        "proTeamId": 12,
                    }
                },
                {"player": {"fullName": "Z3", "defaultPositionId": 2, "proTeamId": 12}},
                {"player": {"fullName": "Z4", "defaultPositionId": 2, "proTeamId": 12}},
                {
                    "player": {
                        "fullName": "Alice",
                        "defaultPositionId": 2,
                        "proTeamId": 12,
                    }
                },
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

    result = svc.compare_rankings(source="consensus", limit=10)

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
    assert required_keys.issubset(
        result.keys()
    ), f"Envelope missing keys: {required_keys - result.keys()}"


# ---------------------------------------------------------------------------
# multi_compare_rankings — Phase 79.x: side-by-side multi-source view
# ---------------------------------------------------------------------------
def _seed_cache(tmp_dir: Path, source: str, players: List[Dict[str, Any]]) -> None:
    """Write a canonical envelope cache file for ``source`` with given rows."""
    envelope = {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players": players,
    }
    (tmp_dir / f"{source}_rankings.json").write_text(json.dumps(envelope))


@pytest.mark.unit
def test_multi_compare_envelope_shape(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Envelope carries per-source stale/cache_age/last_updated maps + sort_by."""
    import requests

    monkeypatch.setattr(
        svc.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")),
    )

    result = svc.multi_compare_rankings(scoring="half_ppr", limit=5)

    required_top = {
        "scoring_format",
        "position_filter",
        "season",
        "sources",
        "sort_by",
        "rank_basis",
        "source_labels",
        "our_projections_available",
        "stale",
        "cache_age_hours",
        "last_updated",
        "players",
        "compared_at",
    }
    assert required_top.issubset(
        result.keys()
    ), f"missing top-level keys: {required_top - result.keys()}"
    assert result["sources"] == ["sleeper", "espn", "yahoo"]
    assert set(result["stale"].keys()) == {"sleeper", "espn", "yahoo"}
    assert result["sort_by"] == "consensus"
    assert "ours" in result["source_labels"]


@pytest.mark.unit
def test_multi_compare_joins_on_player_name(
    tmp_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each source's rank lands on the right column for the joined player."""
    import pandas as pd
    import requests

    # Block live fetches — force cache-only path.
    monkeypatch.setattr(
        svc.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")),
    )

    # Source rows carry OVERALL external_rank values; the service converts to
    # positional rank internally so ours-vs-source comparisons are
    # apples-to-apples (RB1 vs RB1, WR3 vs WR3) regardless of how each source
    # weights position scarcity.
    sleeper_rows = [
        {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 1, "rank": 1},
        {"player_name": "Bob", "position": "WR", "team": "DAL", "external_rank": 2, "rank": 2},
    ]
    espn_rows = [
        {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 5, "rank": 5},
    ]
    fp_rows = [  # Yahoo ↔ FantasyPros internal
        {"player_name": "Bob", "position": "WR", "team": "DAL", "external_rank": 3, "rank": 3},
    ]
    _seed_cache(tmp_cache_dir, "sleeper", sleeper_rows)
    _seed_cache(tmp_cache_dir, "espn", espn_rows)
    _seed_cache(tmp_cache_dir, "fantasypros", fp_rows)

    # _load_our_projections normally produces our_rank as positional rank;
    # the test seeds the post-computation frame directly. Alice = RB1, Bob = WR1.
    our_df = pd.DataFrame(
        [
            {"player_name": "Alice", "position": "RB", "team": "KC", "our_rank": 1, "projected_points": 18.0},
            {"player_name": "Bob", "position": "WR", "team": "DAL", "our_rank": 1, "projected_points": 12.5},
        ]
    )
    monkeypatch.setattr(svc, "_load_our_projections", lambda **kw: our_df)

    # No position filter → rank_basis="overall". Each source's headline
    # `<source>_rank` is its OVERALL rank (not positional). Both
    # `<source>_pos_rank` and `<source>_overall_rank` are also exposed
    # so the frontend can switch labels without a refetch.
    result = svc.multi_compare_rankings(limit=10)
    assert result["rank_basis"] == "overall"
    by_name = {p["player_name"]: p for p in result["players"]}

    alice = by_name["Alice"]
    # our_rank uses the parquet's overall_rank when no filter — fixture's
    # our_df has Alice's our_rank=1 (only RB), so overall and positional
    # match in this minimal setup.
    assert alice["our_rank"] == 1
    assert alice["our_pos_rank"] == 1
    # Both kinds of external rank exposed; headline matches overall.
    assert alice["sleeper_rank"] == 1.0
    assert alice["sleeper_overall_rank"] == 1.0
    assert alice["sleeper_pos_rank"] == 1.0
    assert alice["espn_rank"] == 5.0  # ESPN's overall (was external_rank=5)
    assert alice["espn_overall_rank"] == 5.0
    assert alice["espn_pos_rank"] == 1.0  # only RB in ESPN seed → RB1
    assert alice["yahoo_rank"] is None
    assert alice["rank_diff_vs_sleeper"] == 0.0  # 1 - 1
    assert alice["rank_diff_vs_espn"] == 4.0  # 5 - 1
    assert alice["rank_diff_vs_yahoo"] is None

    bob = by_name["Bob"]
    assert bob["our_rank"] == 1
    assert bob["sleeper_rank"] == 2.0  # overall=2 (sleeper had external_rank=2)
    assert bob["sleeper_pos_rank"] == 1.0  # only WR in sleeper seed → WR1
    assert bob["espn_rank"] is None
    assert bob["yahoo_rank"] == 3.0  # FP overall=3
    assert bob["yahoo_pos_rank"] == 1.0  # only WR in FP seed → WR1
    assert bob["rank_diff_vs_sleeper"] == 1.0  # 2 - 1
    assert bob["rank_diff_vs_yahoo"] == 2.0  # 3 - 1


@pytest.mark.unit
def test_multi_compare_rank_basis_switches_with_position_filter(
    tmp_cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a position filter, headline ranks switch to positional."""
    import pandas as pd
    import requests

    monkeypatch.setattr(
        svc.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")),
    )

    sleeper_rows = [
        {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 1, "rank": 1},
        {"player_name": "Bob", "position": "WR", "team": "DAL", "external_rank": 2, "rank": 2},
    ]
    espn_rows = [
        {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 5, "rank": 5},
    ]
    _seed_cache(tmp_cache_dir, "sleeper", sleeper_rows)
    _seed_cache(tmp_cache_dir, "espn", espn_rows)

    our_df = pd.DataFrame(
        [
            {"player_name": "Alice", "position": "RB", "team": "KC", "our_rank": 1, "our_overall_rank": 7, "projected_points": 18.0},
        ]
    )
    monkeypatch.setattr(svc, "_load_our_projections", lambda **kw: our_df)

    result = svc.multi_compare_rankings(
        limit=10, position="RB", sources=("sleeper", "espn")
    )
    assert result["rank_basis"] == "positional"
    by_name = {p["player_name"]: p for p in result["players"]}
    alice = by_name["Alice"]
    # Headline ranks are POSITIONAL when a filter is active.
    assert alice["our_rank"] == 1  # RB1
    assert alice["our_pos_rank"] == 1
    assert alice["our_overall_rank"] == 7  # still exposed
    assert alice["sleeper_rank"] == 1.0  # RB1 in sleeper
    assert alice["espn_rank"] == 1.0  # RB1 in espn
    assert alice["sleeper_overall_rank"] == 1.0
    assert alice["espn_overall_rank"] == 5.0


@pytest.mark.unit
def test_multi_compare_sort_by_consensus_uses_external_mean(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """consensus sort orders by mean of present external ranks (lowest first)."""
    import requests

    monkeypatch.setattr(
        svc.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")),
    )
    # Neutralize the Bronze yahoo_proxy_fp tier — this test seeds caches for
    # sleeper/espn only and must not pick up real repo data for yahoo.
    monkeypatch.setattr(svc, "_load_bronze_fantasypros", lambda **kw: None)

    # Alice: sleeper=10, espn=10  → mean=10
    # Bob:   sleeper=1,  espn=99  → mean=50
    # Carol: sleeper=2,  espn=2   → mean=2  ← should be #1
    _seed_cache(
        tmp_cache_dir,
        "sleeper",
        [
            {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 10, "rank": 10},
            {"player_name": "Bob", "position": "RB", "team": "KC", "external_rank": 1, "rank": 1},
            {"player_name": "Carol", "position": "RB", "team": "KC", "external_rank": 2, "rank": 2},
        ],
    )
    _seed_cache(
        tmp_cache_dir,
        "espn",
        [
            {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 10, "rank": 10},
            {"player_name": "Bob", "position": "RB", "team": "KC", "external_rank": 99, "rank": 99},
            {"player_name": "Carol", "position": "RB", "team": "KC", "external_rank": 2, "rank": 2},
        ],
    )

    # No position filter → rank_basis="overall". Headline `<source>_rank` is
    # the source's overall rank (not positional). Consensus = mean of
    # available external overalls. With:
    #   Alice: sleeper=10, espn=10 → mean=10
    #   Bob:   sleeper=1,  espn=99 → mean=50
    #   Carol: sleeper=2,  espn=2  → mean=2  ← lowest
    result = svc.multi_compare_rankings(limit=10, sort_by="consensus")
    names = [p["player_name"] for p in result["players"][:3]]
    assert names == ["Carol", "Alice", "Bob"], f"got {names}"


@pytest.mark.unit
def test_multi_compare_position_filter_uniform(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Position filter applies to every source uniformly — RB-only stays RB-only."""
    import requests

    monkeypatch.setattr(
        svc.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")),
    )

    rb_and_wr = [
        {"player_name": "Alice", "position": "RB", "team": "KC", "external_rank": 1, "rank": 1},
        {"player_name": "Bob", "position": "WR", "team": "DAL", "external_rank": 2, "rank": 2},
    ]
    _seed_cache(tmp_cache_dir, "sleeper", rb_and_wr)
    _seed_cache(tmp_cache_dir, "espn", rb_and_wr)

    result = svc.multi_compare_rankings(
        limit=10, position="RB", sources=("sleeper", "espn")
    )
    positions = {p["position"] for p in result["players"]}
    assert positions == {"RB"}


@pytest.mark.unit
def test_multi_compare_fail_open_when_all_sources_blocked(
    tmp_cache_dir: Path,
    empty_projections: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No live, no cache, no bronze, no projections → empty + stale per source."""
    import requests

    monkeypatch.setattr(
        svc.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")),
    )
    # Neutralize the Bronze yahoo_proxy_fp tier so "everything blocked"
    # genuinely means every tier, not just live+cache.
    monkeypatch.setattr(svc, "_load_bronze_fantasypros", lambda **kw: None)

    result = svc.multi_compare_rankings(limit=10)

    assert result["players"] == []
    assert result["our_projections_available"] is False
    assert all(result["stale"][k] is True for k in ("sleeper", "espn", "yahoo"))


@pytest.mark.unit
def test_multi_compare_rejects_invalid_sort_by(tmp_cache_dir: Path) -> None:
    with pytest.raises(ValueError, match="Invalid sort_by"):
        svc.multi_compare_rankings(sort_by="garbage")


@pytest.mark.unit
def test_multi_compare_rejects_invalid_source(tmp_cache_dir: Path) -> None:
    with pytest.raises(ValueError, match="Invalid source"):
        svc.multi_compare_rankings(sources=("not_a_source",))


@pytest.mark.unit
def test_fantasypros_bronze_fallback_serves_when_live_and_cache_fail(
    tmp_cache_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 3: fantasypros resolves from the Bronze yahoo_proxy_fp parquet.

    FP's v2 API requires an auth token (403 since ~2026-06), so with no cache
    the Bronze scrape is the only thing standing between the website and an
    empty yahoo column.
    """
    import pandas as pd
    import requests

    monkeypatch.setattr(
        svc.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("x")),
    )

    bronze_dir = (
        tmp_path
        / "bronze"
        / "external_projections"
        / "yahoo_proxy_fp"
        / "season=2026"
        / "week=00"
    )
    bronze_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "player_name": "Josh Allen",
                "position": "QB",
                "team": "BUF",
                "projected_points": 374.7,
                "projected_at": "2026-06-12T00:00:00+00:00",
            },
            {
                "player_name": "Bijan Robinson",
                "position": "RB",
                "team": "ATL",
                "projected_points": 294.2,
                "projected_at": "2026-06-12T00:00:00+00:00",
            },
        ]
    ).to_parquet(bronze_dir / "yahoo_proxy_fp_20260612_000000.parquet", index=False)
    monkeypatch.setattr(svc, "DATA_DIR", tmp_path)

    players, stale, age_hours, _ = svc._resolve_source(
        "fantasypros", season=2026, scoring="half_ppr", limit=10
    )
    assert stale is True
    assert age_hours is not None
    assert [p["player_name"] for p in players] == ["Josh Allen", "Bijan Robinson"]
    assert players[0]["external_rank"] == 1
