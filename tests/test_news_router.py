"""
Tests for the /api/news FastAPI router.

Uses FastAPI TestClient with mocked news_service so tests run without
real sentiment data on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from web.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Shared mock data builders
# ---------------------------------------------------------------------------


def _mock_news_item(
    player_id: str = "00-0023459",
    title: str = "Mahomes limited in practice",
    source: str = "rss_espn",
    is_questionable: bool = True,
) -> Dict[str, Any]:
    return {
        "doc_id": "doc-0001",
        "title": title,
        "source": source,
        "url": "https://espn.com/article/1",
        "published_at": "2026-04-07T09:00:00+00:00",
        "sentiment": -0.3,
        "category": "injury",
        "player_id": player_id,
        "player_name": "Patrick Mahomes",
        "is_ruled_out": False,
        "is_inactive": False,
        "is_questionable": is_questionable,
        "is_suspended": False,
        "is_returning": False,
        "body_snippet": "Patrick Mahomes was limited in practice on Wednesday...",
    }


def _mock_alert(
    player_id: str = "00-0023459",
    alert_type: str = "questionable",
    sentiment_multiplier: float = 0.92,
) -> Dict[str, Any]:
    return {
        "player_id": player_id,
        "player_name": "Patrick Mahomes",
        "team": None,
        "position": None,
        "alert_type": alert_type,
        "sentiment_multiplier": sentiment_multiplier,
        "latest_signal_at": "2026-04-07T09:00:00+00:00",
        "doc_count": 3,
    }


def _mock_sentiment(
    player_id: str = "00-0023459",
    sentiment_multiplier: float = 0.92,
    is_questionable: bool = True,
) -> Dict[str, Any]:
    return {
        "player_id": player_id,
        "player_name": "Patrick Mahomes",
        "season": 2026,
        "week": 1,
        "sentiment_multiplier": sentiment_multiplier,
        "sentiment_score_avg": -0.25,
        "doc_count": 3,
        "is_ruled_out": False,
        "is_inactive": False,
        "is_questionable": is_questionable,
        "is_suspended": False,
        "is_returning": False,
        "latest_signal_at": "2026-04-07T09:00:00+00:00",
        "signal_staleness_hours": 2.5,
    }


# ---------------------------------------------------------------------------
# GET /api/news/player/{player_id}
# ---------------------------------------------------------------------------


class TestGetPlayerNews:
    @patch("web.api.services.news_service.get_player_news")
    def test_returns_news_items(self, mock_get) -> None:
        mock_get.return_value = [_mock_news_item()]
        resp = client.get("/api/news/player/00-0023459?season=2026&week=1")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["player_id"] == "00-0023459"
        assert body[0]["source"] == "rss_espn"
        assert body[0]["is_questionable"] is True

    @patch("web.api.services.news_service.get_player_news")
    def test_returns_empty_list_when_no_news(self, mock_get) -> None:
        """Endpoint should return 200 with empty list when no news found."""
        mock_get.return_value = []
        resp = client.get("/api/news/player/UNKNOWN?season=2026&week=1")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("web.api.services.news_service.get_player_news")
    def test_limit_param_passed_to_service(self, mock_get) -> None:
        mock_get.return_value = []
        client.get("/api/news/player/00-0023459?season=2026&week=1&limit=5")
        mock_get.assert_called_once_with(
            player_id="00-0023459", season=2026, week=1, limit=5
        )

    def test_missing_season_returns_422(self) -> None:
        resp = client.get("/api/news/player/00-0023459?week=1")
        assert resp.status_code == 422

    def test_missing_week_returns_422(self) -> None:
        resp = client.get("/api/news/player/00-0023459?season=2026")
        assert resp.status_code == 422

    def test_invalid_limit_too_high_returns_422(self) -> None:
        resp = client.get("/api/news/player/00-0023459?season=2026&week=1&limit=999")
        assert resp.status_code == 422

    def test_invalid_limit_zero_returns_422(self) -> None:
        resp = client.get("/api/news/player/00-0023459?season=2026&week=1&limit=0")
        assert resp.status_code == 422

    @patch(
        "web.api.services.news_service.get_player_news",
        side_effect=RuntimeError("Unexpected error"),
    )
    def test_service_exception_returns_500(self, mock_get) -> None:
        resp = client.get("/api/news/player/00-0023459?season=2026&week=1")
        assert resp.status_code == 500

    @patch("web.api.services.news_service.get_player_news")
    def test_multiple_items_returned(self, mock_get) -> None:
        mock_get.return_value = [
            _mock_news_item(title="Article 1"),
            _mock_news_item(title="Article 2"),
        ]
        resp = client.get("/api/news/player/00-0023459?season=2026&week=1")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# GET /api/news/alerts
# ---------------------------------------------------------------------------


class TestGetAlerts:
    @patch("web.api.services.news_service.get_active_alerts")
    def test_returns_alert_list(self, mock_get) -> None:
        mock_get.return_value = [_mock_alert()]
        resp = client.get("/api/news/alerts?season=2026&week=1")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["alert_type"] == "questionable"
        assert body[0]["player_id"] == "00-0023459"

    @patch("web.api.services.news_service.get_active_alerts")
    def test_returns_empty_list_when_no_alerts(self, mock_get) -> None:
        mock_get.return_value = []
        resp = client.get("/api/news/alerts?season=2026&week=1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_missing_season_returns_422(self) -> None:
        resp = client.get("/api/news/alerts?week=1")
        assert resp.status_code == 422

    def test_missing_week_returns_422(self) -> None:
        resp = client.get("/api/news/alerts?season=2026")
        assert resp.status_code == 422

    @patch("web.api.services.news_service.get_active_alerts")
    def test_ruled_out_alert_fields(self, mock_get) -> None:
        mock_get.return_value = [
            _mock_alert(alert_type="ruled_out", sentiment_multiplier=0.0)
        ]
        resp = client.get("/api/news/alerts?season=2026&week=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["alert_type"] == "ruled_out"
        assert body[0]["sentiment_multiplier"] == 0.0

    @patch(
        "web.api.services.news_service.get_active_alerts",
        side_effect=RuntimeError("Service down"),
    )
    def test_service_exception_returns_500(self, mock_get) -> None:
        resp = client.get("/api/news/alerts?season=2026&week=1")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/news/sentiment/{player_id}
# ---------------------------------------------------------------------------


class TestGetPlayerSentiment:
    @patch("web.api.services.news_service.get_player_sentiment")
    def test_returns_sentiment_data(self, mock_get) -> None:
        mock_get.return_value = _mock_sentiment()
        resp = client.get("/api/news/sentiment/00-0023459?season=2026&week=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["player_id"] == "00-0023459"
        assert body["sentiment_multiplier"] == pytest.approx(0.92)
        assert body["doc_count"] == 3
        assert body["is_questionable"] is True
        assert body["season"] == 2026
        assert body["week"] == 1

    @patch("web.api.services.news_service.get_player_sentiment")
    def test_returns_404_when_player_not_found(self, mock_get) -> None:
        """Should return 404 when service returns None (no Gold data for player)."""
        mock_get.return_value = None
        resp = client.get("/api/news/sentiment/UNKNOWN?season=2026&week=1")
        assert resp.status_code == 404
        assert "No sentiment data" in resp.json()["detail"]

    def test_missing_season_returns_422(self) -> None:
        resp = client.get("/api/news/sentiment/00-0023459?week=1")
        assert resp.status_code == 422

    def test_missing_week_returns_422(self) -> None:
        resp = client.get("/api/news/sentiment/00-0023459?season=2026")
        assert resp.status_code == 422

    @patch(
        "web.api.services.news_service.get_player_sentiment",
        side_effect=RuntimeError("DB read error"),
    )
    def test_service_exception_returns_500(self, mock_get) -> None:
        resp = client.get("/api/news/sentiment/00-0023459?season=2026&week=1")
        assert resp.status_code == 500

    @patch("web.api.services.news_service.get_player_sentiment")
    def test_null_fields_allowed(self, mock_get) -> None:
        """Optional fields like sentiment_score_avg may be null."""
        data = _mock_sentiment()
        data["sentiment_score_avg"] = None
        data["signal_staleness_hours"] = None
        mock_get.return_value = data
        resp = client.get("/api/news/sentiment/00-0023459?season=2026&week=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sentiment_score_avg"] is None
        assert body["signal_staleness_hours"] is None
