"""Tests for WeeklyAggregator EVT-03 null-player tracking (Phase 72)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from src.sentiment.aggregation import weekly as weekly_module
from src.sentiment.aggregation.weekly import WeeklyAggregator


def _write_signal_envelope(
    target_dir: Path, season: int, week: int, records: List[dict], filename: str
) -> Path:
    """Write a Silver signal envelope file for testing."""
    week_dir = target_dir / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    path = week_dir / filename
    path.write_text(json.dumps({"records": records}), encoding="utf-8")
    return path


@pytest.fixture
def hermetic_silver(tmp_path, monkeypatch):
    """Redirect Silver path to a tmp_path for hermetic tests."""
    silver_dir = tmp_path / "silver" / "sentiment" / "signals"
    silver_dir.mkdir(parents=True)
    monkeypatch.setattr(weekly_module, "_SILVER_SIGNALS_DIR", silver_dir)
    monkeypatch.setattr(
        weekly_module,
        "_GOLD_SENTIMENT_DIR",
        tmp_path / "gold" / "sentiment",
    )
    return silver_dir


def _make_signal(player_id, sentiment=0.5, name="Test Player"):
    return {
        "player_id": player_id,
        "player_name": name,
        "sentiment": sentiment,
        "confidence": 0.8,
        "category": "general",
        "events": {},
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source": "rss",
        "external_id": f"id-{player_id}-{sentiment}",
    }


class TestNullPlayerCount:
    def test_counts_null_player_records(self, hermetic_silver):
        """Test 1: 2 null player_ids → last_null_player_count == 2."""
        records = [
            _make_signal("00-001"),
            _make_signal(None, name="Coach Smith"),
            _make_signal("00-002"),
            _make_signal(None, name="Reporter Bob"),
        ]
        _write_signal_envelope(hermetic_silver, 2025, 17, records, "test_w17.json")

        agg = WeeklyAggregator()
        agg.aggregate(season=2025, week=17, dry_run=True)

        assert agg.last_null_player_count == 2

    def test_resets_per_call(self, hermetic_silver):
        """Test 1b: Second call's count, not cumulative."""
        # First call: 2 nulls
        records_w17 = [
            _make_signal("00-001"),
            _make_signal(None),
            _make_signal(None),
        ]
        _write_signal_envelope(hermetic_silver, 2025, 17, records_w17, "w17.json")

        # Second call: 1 null
        records_w18 = [
            _make_signal("00-002"),
            _make_signal(None),
        ]
        _write_signal_envelope(hermetic_silver, 2025, 18, records_w18, "w18.json")

        agg = WeeklyAggregator()
        agg.aggregate(season=2025, week=17, dry_run=True)
        assert agg.last_null_player_count == 2

        agg.aggregate(season=2025, week=18, dry_run=True)
        # MUST be 1 (this call's count), NOT 3 (cumulative)
        assert agg.last_null_player_count == 1

    def test_zero_nulls_sets_count_zero(self, hermetic_silver):
        """Test 2: Pure-non-null batch sets count to 0."""
        records = [
            _make_signal("00-001"),
            _make_signal("00-002"),
        ]
        _write_signal_envelope(hermetic_silver, 2025, 17, records, "w17.json")

        agg = WeeklyAggregator()
        agg.aggregate(season=2025, week=17, dry_run=True)

        assert agg.last_null_player_count == 0

    def test_info_log_emitted_with_count(self, hermetic_silver, caplog):
        """Test 3: INFO log emitted with correct count when N > 0."""
        records = [
            _make_signal("00-001"),
            _make_signal(None),
            _make_signal(None),
            _make_signal(None),
        ]
        _write_signal_envelope(hermetic_silver, 2025, 17, records, "w17.json")

        agg = WeeklyAggregator()
        with caplog.at_level(logging.INFO, logger="src.sentiment.aggregation.weekly"):
            agg.aggregate(season=2025, week=17, dry_run=True)

        assert any(
            "skipped 3 records with player_id=null" in rec.message
            for rec in caplog.records
        )

    def test_no_log_when_zero_nulls(self, hermetic_silver, caplog):
        """No INFO log emitted when null count is 0."""
        records = [_make_signal("00-001"), _make_signal("00-002")]
        _write_signal_envelope(hermetic_silver, 2025, 17, records, "w17.json")

        agg = WeeklyAggregator()
        with caplog.at_level(logging.INFO, logger="src.sentiment.aggregation.weekly"):
            agg.aggregate(season=2025, week=17, dry_run=True)

        assert not any(
            "skipped" in rec.message and "player_id=null" in rec.message
            for rec in caplog.records
        )

    def test_init_default_zero(self):
        """Newly-constructed aggregator has count=0 before any aggregate() call."""
        agg = WeeklyAggregator()
        assert agg.last_null_player_count == 0
