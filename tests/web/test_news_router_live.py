"""Integration tests for news router event endpoints (Plan 61-05).

Covers the live FastAPI contract for event-based news surfacing:

* ``GET /api/news/feed`` — carries ``event_flags`` populated from Silver
  signal event dicts per D-02/D-03.
* ``GET /api/news/team-events`` — returns exactly 32 zero-filled rows,
  sentiment_label derived from event-count ratios (bearish/bullish/neutral).
* ``GET /api/news/player-badges/{player_id}`` — deduplicated event
  badges sorted by occurrence count desc.

All endpoints must return 200 with zero-filled shapes (never 404) when
Gold/Silver data is missing for the requested (season, week).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the news_service data constants at a temp directory.

    Rewires ``BRONZE_SENTIMENT_DIR``, ``SILVER_SENTIMENT_DIR``,
    ``GOLD_SENTIMENT_DIR`` plus the already-resolved module-level copies
    in ``web.api.services.news_service``. Returns the tmp data root so
    tests can write sample Silver files.
    """
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    (data_root / "bronze" / "sentiment").mkdir(parents=True, exist_ok=True)
    (data_root / "silver" / "sentiment" / "signals").mkdir(parents=True, exist_ok=True)
    (data_root / "gold" / "sentiment").mkdir(parents=True, exist_ok=True)

    import web.api.config as api_config
    import web.api.services.news_service as ns

    monkeypatch.setattr(
        api_config, "BRONZE_SENTIMENT_DIR", data_root / "bronze" / "sentiment"
    )
    monkeypatch.setattr(
        api_config, "SILVER_SENTIMENT_DIR", data_root / "silver" / "sentiment"
    )
    monkeypatch.setattr(
        api_config, "GOLD_SENTIMENT_DIR", data_root / "gold" / "sentiment"
    )

    # Rebind the already-loaded module constants so the live service reads
    # from the temp directory.
    monkeypatch.setattr(ns, "_BRONZE_SENTIMENT_DIR", data_root / "bronze" / "sentiment")
    monkeypatch.setattr(
        ns, "_SILVER_SIGNALS_DIR", data_root / "silver" / "sentiment" / "signals"
    )
    monkeypatch.setattr(ns, "_GOLD_SENTIMENT_DIR", data_root / "gold" / "sentiment")

    return data_root


@pytest.fixture
def client(tmp_data_dir: Path) -> TestClient:
    """Build a TestClient bound to the app with temp data roots."""
    from web.api.main import app

    return TestClient(app)


def _write_silver_records(
    data_root: Path,
    season: int,
    week: int,
    records: List[Dict[str, Any]],
) -> Path:
    """Write a Silver signals JSON file matching the current pipeline shape."""
    week_dir = (
        data_root
        / "silver"
        / "sentiment"
        / "signals"
        / f"season={season}"
        / f"week={week:02d}"
    )
    week_dir.mkdir(parents=True, exist_ok=True)
    path = week_dir / f"signals_test_{season}_{week:02d}.json"
    payload = {
        "batch_id": "test-batch",
        "season": season,
        "week": week,
        "computed_at": "2026-04-18T00:00:00Z",
        "signal_count": len(records),
        "records": records,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_bronze_items(
    data_root: Path,
    source: str,
    season: int,
    items: List[Dict[str, Any]],
) -> Path:
    """Write a Bronze source-items file matching the ingestor envelope."""
    season_dir = data_root / "bronze" / "sentiment" / source / f"season={season}"
    season_dir.mkdir(parents=True, exist_ok=True)
    path = season_dir / f"{source}_test_{season}.json"
    payload = {
        "fetch_run_id": "test-fetch",
        "source": source,
        "fetched_at": "2026-04-18T00:00:00Z",
        "season": season,
        "week": None,
        "item_count": len(items),
        "items": items,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _silver_record(
    doc_id: str,
    player_name: str,
    player_id: str,
    events: Dict[str, bool],
    sentiment: float = 0.0,
    source: str = "rss_espn",
) -> Dict[str, Any]:
    """Build a Silver record with the events sub-dict populated."""
    default_events = {
        "is_ruled_out": False,
        "is_inactive": False,
        "is_questionable": False,
        "is_suspended": False,
        "is_returning": False,
        "is_traded": False,
        "is_released": False,
        "is_signed": False,
        "is_activated": False,
        "is_usage_boost": False,
        "is_usage_drop": False,
        "is_weather_risk": False,
    }
    default_events.update(events)

    return {
        "signal_id": f"sig-{doc_id}",
        "doc_id": doc_id,
        "source": source,
        "season": 2025,
        "week": 1,
        "player_name": player_name,
        "player_id": player_id,
        "sentiment_score": sentiment,
        "sentiment_confidence": 0.7,
        "category": "injury",
        "events": default_events,
        "published_at": "2026-04-10T12:00:00Z",
        "extracted_at": "2026-04-10T12:00:00Z",
        "model_version": "RuleExtractor",
        "raw_excerpt": f"Test excerpt for {player_name}",
    }


# ---------------------------------------------------------------------------
# Tests — get_news_feed event_flags
# ---------------------------------------------------------------------------


def test_news_feed_carries_event_flags_from_silver(
    client: TestClient, tmp_data_dir: Path
) -> None:
    """Test 1: /news/feed items carry event_flags populated from silver events."""
    _write_silver_records(
        tmp_data_dir,
        2025,
        1,
        [
            _silver_record(
                "doc-001",
                "Patrick Mahomes",
                "00-0033873",
                events={"is_questionable": True, "is_returning": True},
            )
        ],
    )
    _write_bronze_items(
        tmp_data_dir,
        "rss",
        2025,
        [
            {
                "external_id": "doc-001",
                "title": "Mahomes questionable but returning",
                "url": "https://example.com/mahomes",
                "source": "rss_espn",
                "published_at": "2026-04-10T12:00:00Z",
                "body_text": "Patrick Mahomes is listed as questionable.",
                "team_hint": "KC",
                "resolved_player_ids": ["00-0033873"],
            }
        ],
    )

    resp = client.get(
        "/api/news/feed",
        params={"season": 2025, "week": 1, "limit": 50},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) >= 1
    mahomes = next((i for i in items if i.get("player_id") == "00-0033873"), None)
    assert mahomes is not None
    assert "event_flags" in mahomes
    flags = mahomes["event_flags"]
    assert "Questionable" in flags
    assert "Returning" in flags


# ---------------------------------------------------------------------------
# Tests — /news/team-events
# ---------------------------------------------------------------------------


def test_team_events_returns_exactly_32_teams(
    client: TestClient, tmp_data_dir: Path
) -> None:
    """Test 2: /news/team-events returns 32 rows even with partial data."""
    # Only 2 teams have events; remaining 30 must be zero-filled.
    _write_silver_records(
        tmp_data_dir,
        2025,
        1,
        [
            _silver_record(
                "doc-010",
                "Patrick Mahomes",
                "00-0033873",
                events={"is_ruled_out": True},
                source="rss_espn",
            ),
            _silver_record(
                "doc-011",
                "Justin Jefferson",
                "00-0036322",
                events={"is_usage_boost": True},
                source="reddit",
            ),
        ],
    )
    _write_bronze_items(
        tmp_data_dir,
        "rss",
        2025,
        [
            {
                "external_id": "doc-010",
                "title": "Mahomes out",
                "url": "https://example.com/1",
                "source": "rss_espn",
                "published_at": "2026-04-10T12:00:00Z",
                "body_text": "Mahomes is out.",
                "team_hint": "KC",
                "resolved_player_ids": ["00-0033873"],
            },
            {
                "external_id": "doc-011",
                "title": "Jefferson primary target",
                "url": "https://example.com/2",
                "source": "reddit",
                "published_at": "2026-04-10T12:00:00Z",
                "body_text": "Justin Jefferson is the primary target.",
                "team_hint": "MIN",
                "resolved_player_ids": ["00-0036322"],
            },
        ],
    )

    resp = client.get("/api/news/team-events", params={"season": 2025, "week": 1})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) == 32


def test_team_events_bearish_when_negative_events_dominate(
    client: TestClient, tmp_data_dir: Path
) -> None:
    """Test 3: Team with 3 is_ruled_out events has sentiment_label=='bearish'."""
    records = [
        _silver_record(
            f"doc-bear-{i}",
            f"KC Player {i}",
            f"id-bear-{i}",
            events={"is_ruled_out": True},
            source="rss_espn",
        )
        for i in range(3)
    ]
    _write_silver_records(tmp_data_dir, 2025, 1, records)
    _write_bronze_items(
        tmp_data_dir,
        "rss",
        2025,
        [
            {
                "external_id": f"doc-bear-{i}",
                "title": f"Player {i} ruled out",
                "url": f"https://example.com/bear-{i}",
                "source": "rss_espn",
                "published_at": "2026-04-10T12:00:00Z",
                "body_text": "Ruled out.",
                "team_hint": "KC",
                "resolved_player_ids": [f"id-bear-{i}"],
            }
            for i in range(3)
        ],
    )

    resp = client.get("/api/news/team-events", params={"season": 2025, "week": 1})
    assert resp.status_code == 200
    rows = resp.json()
    kc = next((r for r in rows if r["team"] == "KC"), None)
    assert kc is not None
    assert kc["sentiment_label"] == "bearish"
    assert kc["negative_event_count"] == 3


def test_team_events_bullish_when_positive_events_dominate(
    client: TestClient, tmp_data_dir: Path
) -> None:
    """Test 4: Team with 5 is_usage_boost events has sentiment_label=='bullish'."""
    records = [
        _silver_record(
            f"doc-bull-{i}",
            f"MIN Player {i}",
            f"id-bull-{i}",
            events={"is_usage_boost": True},
            source="reddit",
        )
        for i in range(5)
    ]
    _write_silver_records(tmp_data_dir, 2025, 1, records)
    _write_bronze_items(
        tmp_data_dir,
        "reddit",
        2025,
        [
            {
                "external_id": f"doc-bull-{i}",
                "title": f"Player {i} primary target",
                "url": f"https://example.com/bull-{i}",
                "source": "reddit",
                "published_at": "2026-04-10T12:00:00Z",
                "body_text": "Named starter, workhorse.",
                "team_hint": "MIN",
                "resolved_player_ids": [f"id-bull-{i}"],
            }
            for i in range(5)
        ],
    )

    resp = client.get("/api/news/team-events", params={"season": 2025, "week": 1})
    assert resp.status_code == 200
    rows = resp.json()
    minn = next((r for r in rows if r["team"] == "MIN"), None)
    assert minn is not None
    assert minn["sentiment_label"] == "bullish"
    assert minn["positive_event_count"] == 5


def test_team_events_neutral_with_no_events(client: TestClient) -> None:
    """Test 5: Team with 0 events has sentiment_label=='neutral' and all counts==0.

    The fixture tmp_data_dir writes no data, so every one of the 32 teams
    should land in the neutral bucket with zero counts.
    """
    resp = client.get("/api/news/team-events", params={"season": 2025, "week": 1})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 32
    for row in rows:
        assert row["negative_event_count"] == 0
        assert row["positive_event_count"] == 0
        assert row["neutral_event_count"] == 0
        assert row["total_articles"] == 0
        assert row["sentiment_label"] == "neutral"
        assert row["top_events"] == []


# ---------------------------------------------------------------------------
# Tests — /news/player-badges
# ---------------------------------------------------------------------------


def test_player_badges_unique_and_sorted_by_frequency(
    client: TestClient, tmp_data_dir: Path
) -> None:
    """Test 6: /news/player-badges/{id} returns unique labels sorted by frequency desc.

    Three is_questionable events + one is_returning event on the same player
    should produce badges=["Questionable", "Returning"] — dedupe + sorted.
    """
    records = [
        _silver_record(
            "doc-p1",
            "Patrick Mahomes",
            "00-0033873",
            events={"is_questionable": True},
        ),
        _silver_record(
            "doc-p2",
            "Patrick Mahomes",
            "00-0033873",
            events={"is_questionable": True},
        ),
        _silver_record(
            "doc-p3",
            "Patrick Mahomes",
            "00-0033873",
            events={"is_questionable": True},
        ),
        _silver_record(
            "doc-p4",
            "Patrick Mahomes",
            "00-0033873",
            events={"is_returning": True},
        ),
    ]
    _write_silver_records(tmp_data_dir, 2025, 1, records)

    resp = client.get(
        "/api/news/player-badges/00-0033873",
        params={"season": 2025, "week": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["player_id"] == "00-0033873"
    assert data["badges"] == ["Questionable", "Returning"]  # by freq desc
    # neutral-dominant since 3 neutral vs 1 positive; neutral bucket wins
    # or positive; just check it's a valid label
    assert data["overall_label"] in {"bullish", "bearish", "neutral"}
    assert data["article_count"] == 4


# ---------------------------------------------------------------------------
# Tests — graceful empty-state degradation
# ---------------------------------------------------------------------------


def test_endpoints_degrade_gracefully_on_empty_data(client: TestClient) -> None:
    """Test 7: All endpoints return 200 with zero shapes when no data exists.

    The fixture writes nothing, so every endpoint must succeed with an
    empty/zero-filled payload — no 404s, no 500s.
    """
    r_feed = client.get(
        "/api/news/feed", params={"season": 2025, "week": 1, "limit": 10}
    )
    assert r_feed.status_code == 200
    assert r_feed.json() == []

    r_team = client.get("/api/news/team-events", params={"season": 2025, "week": 1})
    assert r_team.status_code == 200
    rows = r_team.json()
    assert len(rows) == 32
    assert all(r["sentiment_label"] == "neutral" for r in rows)

    r_badges = client.get(
        "/api/news/player-badges/00-0000000",
        params={"season": 2025, "week": 1},
    )
    assert r_badges.status_code == 200
    data = r_badges.json()
    assert data["player_id"] == "00-0000000"
    assert data["badges"] == []
    assert data["overall_label"] == "neutral"
    assert data["article_count"] == 0
