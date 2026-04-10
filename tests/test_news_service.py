"""
Tests for web.api.services.news_service.

All tests use temporary directories and in-memory data so they run without
real sentiment pipeline output on disk.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pandas as pd
import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers — build fixture data
# ---------------------------------------------------------------------------


def _make_silver_record(
    player_id: str = "00-0023459",
    player_name: str = "Patrick Mahomes",
    source: str = "rss_espn",
    title: str = "Mahomes limited in practice",
    sentiment_score: float = -0.3,
    published_at: str = "2026-04-07T09:00:00+00:00",
    is_questionable: bool = True,
    is_ruled_out: bool = False,
) -> Dict[str, Any]:
    return {
        "player_id": player_id,
        "player_name": player_name,
        "source": source,
        "title": title,
        "sentiment_score": sentiment_score,
        "sentiment_confidence": 0.8,
        "published_at": published_at,
        "category": "injury",
        "external_id": f"doc-{player_id[:4]}",
        "events": {
            "is_ruled_out": is_ruled_out,
            "is_inactive": False,
            "is_questionable": is_questionable,
            "is_suspended": False,
            "is_returning": False,
        },
    }


def _make_gold_sentiment_df(
    player_id: str = "00-0023459",
    player_name: str = "Patrick Mahomes",
    sentiment_multiplier: float = 0.92,
    is_ruled_out: bool = False,
    is_questionable: bool = True,
    doc_count: int = 3,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": player_id,
                "player_name": player_name,
                "season": 2026,
                "week": 1,
                "sentiment_multiplier": sentiment_multiplier,
                "sentiment_score_avg": -0.25,
                "doc_count": doc_count,
                "is_ruled_out": is_ruled_out,
                "is_inactive": False,
                "is_questionable": is_questionable,
                "is_suspended": False,
                "is_returning": False,
                "latest_signal_at": "2026-04-07T09:00:00+00:00",
                "signal_staleness_hours": 2.5,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Fixtures — write temp files
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_data_root(tmp_path: Path) -> Path:
    """Return a temporary directory tree mimicking data/silver/sentiment/."""
    return tmp_path


def _write_silver_file(
    root: Path,
    season: int,
    week: int,
    records: List[Dict[str, Any]],
) -> Path:
    week_dir = root / "silver" / "sentiment" / "signals" / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    path = week_dir / "signals_20260407_120000.json"
    path.write_text(json.dumps({"records": records}), encoding="utf-8")
    return path


def _write_gold_file(root: Path, season: int, week: int, df: pd.DataFrame) -> Path:
    week_dir = root / "gold" / "sentiment" / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    path = week_dir / "sentiment_multipliers_20260407_120000.parquet"
    df.to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Tests — get_player_news
# ---------------------------------------------------------------------------


class TestGetPlayerNews:
    def test_returns_empty_when_no_silver_files(self, tmp_data_root: Path) -> None:
        """Should return [] gracefully when no Silver data exists."""
        from web.api.services import news_service

        with (
            patch.object(news_service, "_SILVER_SIGNALS_DIR", tmp_data_root / "silver" / "sentiment" / "signals"),
            patch.object(news_service, "_BRONZE_SENTIMENT_DIR", tmp_data_root / "bronze" / "sentiment"),
        ):
            items = news_service.get_player_news("00-0023459", season=2026, week=1)

        assert items == []

    def test_returns_items_for_matching_player(self, tmp_data_root: Path) -> None:
        """Should return news items for the requested player_id."""
        from web.api.services import news_service

        records = [
            _make_silver_record(player_id="00-0023459"),
            _make_silver_record(player_id="00-0031408", player_name="Travis Kelce"),
        ]
        _write_silver_file(tmp_data_root, 2026, 1, records)

        with (
            patch.object(news_service, "_SILVER_SIGNALS_DIR", tmp_data_root / "silver" / "sentiment" / "signals"),
            patch.object(news_service, "_BRONZE_SENTIMENT_DIR", tmp_data_root / "bronze" / "sentiment"),
        ):
            items = news_service.get_player_news("00-0023459", season=2026, week=1)

        assert len(items) == 1
        assert items[0]["player_id"] == "00-0023459"
        assert items[0]["source"] == "rss_espn"
        assert items[0]["title"] == "Mahomes limited in practice"

    def test_respects_limit(self, tmp_data_root: Path) -> None:
        """Should not return more items than the limit parameter."""
        from web.api.services import news_service

        records = [
            _make_silver_record(player_id="00-0023459", title=f"Article {i}")
            for i in range(10)
        ]
        _write_silver_file(tmp_data_root, 2026, 1, records)

        with (
            patch.object(news_service, "_SILVER_SIGNALS_DIR", tmp_data_root / "silver" / "sentiment" / "signals"),
            patch.object(news_service, "_BRONZE_SENTIMENT_DIR", tmp_data_root / "bronze" / "sentiment"),
        ):
            items = news_service.get_player_news("00-0023459", season=2026, week=1, limit=3)

        assert len(items) == 3

    def test_event_flags_mapped_correctly(self, tmp_data_root: Path) -> None:
        """Event flags from Silver records should appear in returned items."""
        from web.api.services import news_service

        record = _make_silver_record(
            player_id="00-0023459",
            is_questionable=True,
            is_ruled_out=False,
        )
        _write_silver_file(tmp_data_root, 2026, 1, [record])

        with (
            patch.object(news_service, "_SILVER_SIGNALS_DIR", tmp_data_root / "silver" / "sentiment" / "signals"),
            patch.object(news_service, "_BRONZE_SENTIMENT_DIR", tmp_data_root / "bronze" / "sentiment"),
        ):
            items = news_service.get_player_news("00-0023459", season=2026, week=1)

        assert len(items) == 1
        item = items[0]
        assert item["is_questionable"] is True
        assert item["is_ruled_out"] is False
        assert item["is_inactive"] is False

    def test_returns_empty_for_unknown_player(self, tmp_data_root: Path) -> None:
        """Should return [] when the player has no signals, not raise."""
        from web.api.services import news_service

        records = [_make_silver_record(player_id="00-0023459")]
        _write_silver_file(tmp_data_root, 2026, 1, records)

        with (
            patch.object(news_service, "_SILVER_SIGNALS_DIR", tmp_data_root / "silver" / "sentiment" / "signals"),
            patch.object(news_service, "_BRONZE_SENTIMENT_DIR", tmp_data_root / "bronze" / "sentiment"),
        ):
            items = news_service.get_player_news("UNKNOWN-PLAYER", season=2026, week=1)

        assert items == []

    def test_handles_malformed_json_file(self, tmp_data_root: Path) -> None:
        """Should skip malformed JSON files and return empty list."""
        from web.api.services import news_service

        signals_dir = (
            tmp_data_root / "silver" / "sentiment" / "signals"
            / "season=2026" / "week=01"
        )
        signals_dir.mkdir(parents=True, exist_ok=True)
        (signals_dir / "bad.json").write_text("NOT JSON {{{", encoding="utf-8")

        with (
            patch.object(news_service, "_SILVER_SIGNALS_DIR", tmp_data_root / "silver" / "sentiment" / "signals"),
            patch.object(news_service, "_BRONZE_SENTIMENT_DIR", tmp_data_root / "bronze" / "sentiment"),
        ):
            items = news_service.get_player_news("00-0023459", season=2026, week=1)

        assert items == []


# ---------------------------------------------------------------------------
# Tests — get_active_alerts
# ---------------------------------------------------------------------------


class TestGetActiveAlerts:
    def test_returns_empty_when_no_gold_data(self, tmp_data_root: Path) -> None:
        """Should return [] when Gold sentiment directory does not exist."""
        from web.api.services import news_service

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            alerts = news_service.get_active_alerts(season=2026, week=1)

        assert alerts == []

    def test_ruled_out_player_triggers_alert(self, tmp_data_root: Path) -> None:
        """A player flagged is_ruled_out should appear as a ruled_out alert."""
        from web.api.services import news_service

        df = _make_gold_sentiment_df(
            player_id="00-0023459",
            is_ruled_out=True,
            is_questionable=False,
            sentiment_multiplier=0.0,
        )
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            alerts = news_service.get_active_alerts(season=2026, week=1)

        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "ruled_out"
        assert alerts[0]["player_id"] == "00-0023459"

    def test_questionable_player_triggers_alert(self, tmp_data_root: Path) -> None:
        """A player flagged is_questionable should appear as a questionable alert."""
        from web.api.services import news_service

        df = _make_gold_sentiment_df(
            is_ruled_out=False,
            is_questionable=True,
            sentiment_multiplier=0.92,
        )
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            alerts = news_service.get_active_alerts(season=2026, week=1)

        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "questionable"

    def test_major_negative_sentiment_triggers_alert(self, tmp_data_root: Path) -> None:
        """A player with multiplier <= 0.85 triggers a major_negative alert."""
        from web.api.services import news_service

        df = _make_gold_sentiment_df(
            is_questionable=False,
            sentiment_multiplier=0.75,
        )
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            alerts = news_service.get_active_alerts(season=2026, week=1)

        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "major_negative"

    def test_neutral_player_produces_no_alert(self, tmp_data_root: Path) -> None:
        """A player with no flags and neutral multiplier should produce no alert."""
        from web.api.services import news_service

        df = _make_gold_sentiment_df(
            is_ruled_out=False,
            is_questionable=False,
            sentiment_multiplier=1.0,
        )
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            alerts = news_service.get_active_alerts(season=2026, week=1)

        assert alerts == []

    def test_ruled_out_sorted_before_questionable(self, tmp_data_root: Path) -> None:
        """ruled_out alerts should appear before questionable alerts."""
        from web.api.services import news_service

        df = pd.DataFrame(
            [
                {
                    "player_id": "00-QUES",
                    "player_name": "Questionable Player",
                    "season": 2026,
                    "week": 1,
                    "sentiment_multiplier": 0.92,
                    "sentiment_score_avg": -0.1,
                    "doc_count": 2,
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": True,
                    "is_suspended": False,
                    "is_returning": False,
                    "latest_signal_at": "2026-04-07T09:00:00+00:00",
                    "signal_staleness_hours": 2.0,
                },
                {
                    "player_id": "00-OUT",
                    "player_name": "Ruled Out Player",
                    "season": 2026,
                    "week": 1,
                    "sentiment_multiplier": 0.0,
                    "sentiment_score_avg": -1.0,
                    "doc_count": 5,
                    "is_ruled_out": True,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                    "latest_signal_at": "2026-04-07T09:00:00+00:00",
                    "signal_staleness_hours": 1.0,
                },
            ]
        )
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            alerts = news_service.get_active_alerts(season=2026, week=1)

        assert len(alerts) == 2
        assert alerts[0]["alert_type"] == "ruled_out"
        assert alerts[1]["alert_type"] == "questionable"


# ---------------------------------------------------------------------------
# Tests — get_player_sentiment
# ---------------------------------------------------------------------------


class TestGetPlayerSentiment:
    def test_returns_none_when_no_gold_data(self, tmp_data_root: Path) -> None:
        """Should return None when no Gold sentiment Parquet exists."""
        from web.api.services import news_service

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            result = news_service.get_player_sentiment("00-0023459", season=2026, week=1)

        assert result is None

    def test_returns_sentiment_for_known_player(self, tmp_data_root: Path) -> None:
        """Should return a populated dict for a player present in Gold data."""
        from web.api.services import news_service

        df = _make_gold_sentiment_df(
            player_id="00-0023459",
            player_name="Patrick Mahomes",
            sentiment_multiplier=0.92,
            is_questionable=True,
            doc_count=3,
        )
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            result = news_service.get_player_sentiment("00-0023459", season=2026, week=1)

        assert result is not None
        assert result["player_id"] == "00-0023459"
        assert result["player_name"] == "Patrick Mahomes"
        assert result["sentiment_multiplier"] == pytest.approx(0.92)
        assert result["doc_count"] == 3
        assert result["is_questionable"] is True
        assert result["season"] == 2026
        assert result["week"] == 1

    def test_returns_none_for_unknown_player(self, tmp_data_root: Path) -> None:
        """Should return None when player_id is not found in Gold data."""
        from web.api.services import news_service

        df = _make_gold_sentiment_df(player_id="00-0023459")
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            result = news_service.get_player_sentiment("UNKNOWN", season=2026, week=1)

        assert result is None

    def test_handles_nan_scores_gracefully(self, tmp_data_root: Path) -> None:
        """NaN in sentiment_score_avg should be returned as None, not crash."""
        from web.api.services import news_service

        df = _make_gold_sentiment_df(player_id="00-0023459")
        df["sentiment_score_avg"] = float("nan")
        _write_gold_file(tmp_data_root, 2026, 1, df)

        with patch.object(news_service, "_GOLD_SENTIMENT_DIR", tmp_data_root / "gold" / "sentiment"):
            result = news_service.get_player_sentiment("00-0023459", season=2026, week=1)

        assert result is not None
        assert result["sentiment_score_avg"] is None
