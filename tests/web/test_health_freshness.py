"""Unit tests for data freshness monitoring endpoint."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest

from web.api.routers.health_freshness import (
    FreshDataset,
    FreshnessResponse,
    age_in_hours,
    extract_timestamp_from_filename,
    get_freshness,
    set_data_root,
)


@pytest.fixture
def tmp_data_root(tmp_path):
    """Create a temporary data directory structure and set it as the root."""
    root = tmp_path / "data"
    root.mkdir()

    # Create directory structure
    (root / "gold" / "projections").mkdir(parents=True)
    (root / "gold" / "predictions").mkdir(parents=True)
    (root / "gold" / "sentiment").mkdir(parents=True)
    (root / "bronze" / "odds_api" / "snapshots").mkdir(parents=True)
    (root / "external").mkdir(parents=True)

    # Set the root before the test runs
    set_data_root(root)

    yield root

    # Reset after test
    set_data_root(None)


def test_age_in_hours():
    """Test age_in_hours calculation."""
    now = datetime.now(tz=timezone.utc)

    # 1 hour ago
    one_hour_ago = now - timedelta(hours=1)
    assert abs(age_in_hours(one_hour_ago) - 1.0) < 0.01

    # 24 hours ago
    one_day_ago = now - timedelta(days=1)
    assert abs(age_in_hours(one_day_ago) - 24.0) < 0.01

    # 7 days ago
    one_week_ago = now - timedelta(days=7)
    assert abs(age_in_hours(one_week_ago) - 168.0) < 0.1


def test_extract_timestamp_from_filename():
    """Test filename timestamp extraction."""
    # Valid timestamp
    dt = extract_timestamp_from_filename(
        "projections_20260606_123045.parquet"
    )
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.day == 6
    assert dt.hour == 12
    assert dt.minute == 30
    assert dt.second == 45

    # Missing timestamp
    assert extract_timestamp_from_filename("no_timestamp.parquet") is None

    # Malformed timestamp
    assert extract_timestamp_from_filename("file_20260632_999999.parquet") is None


def test_freshness_no_data(tmp_data_root):
    """Test freshness response when no data exists."""
    resp = get_freshness()

    assert isinstance(resp, FreshnessResponse)
    assert resp.overall_stale is True  # No projections, predictions, or rankings
    assert resp.projections.stale is True
    assert resp.projections.age_hours is None
    assert resp.predictions.stale is True
    assert resp.rankings.stale is True
    # Odds and sentiment non-blocking -> False when no data in off-season
    assert resp.odds.stale is False
    assert resp.sentiment.stale is False


def test_freshness_recent_projections(tmp_data_root):
    """Test freshness when projections are recent."""
    # Create a fresh projection file
    now = datetime.now(tz=timezone.utc)
    filename = f"projections_{now.strftime('%Y%m%d_%H%M%S')}.parquet"
    proj_file = tmp_data_root / "gold" / "projections" / filename

    # Write empty parquet (just create file)
    proj_file.write_bytes(b"PAR1")  # Minimal parquet header

    resp = get_freshness()

    # Projections should be fresh (< 1 hour old)
    assert resp.projections.age_hours is not None
    assert resp.projections.age_hours < 1.0
    assert resp.projections.stale is False

    # But still stale overall (no predictions or rankings)
    assert resp.overall_stale is True


def test_freshness_stale_projections_preseason(tmp_data_root, monkeypatch):
    """Test staleness detection in preseason (7-day threshold)."""
    # Fake the season check to be preseason (April)
    def fake_is_in_season():
        return False

    monkeypatch.setattr(
        "web.api.routers.health_freshness.is_in_season",
        fake_is_in_season,
    )

    # Create projection file 8 days old
    old_time = datetime.now(tz=timezone.utc) - timedelta(days=8)
    filename = f"projections_{old_time.strftime('%Y%m%d_%H%M%S')}.parquet"
    proj_file = tmp_data_root / "gold" / "projections" / filename

    proj_file.write_bytes(b"PAR1")
    # Backdate the file
    import os

    os.utime(proj_file, (old_time.timestamp(), old_time.timestamp()))

    resp = get_freshness()

    # Should be stale
    assert resp.projections.age_hours is not None
    assert resp.projections.age_hours > 168  # > 7 days
    assert resp.projections.stale is True
    assert resp.overall_stale is True


def test_freshness_stale_projections_in_season(tmp_data_root, monkeypatch):
    """Test staleness detection in-season (26-hour threshold)."""

    def fake_is_in_season():
        return True

    monkeypatch.setattr(
        "web.api.routers.health_freshness.is_in_season",
        fake_is_in_season,
    )

    # Create projection file 27 hours old
    old_time = datetime.now(tz=timezone.utc) - timedelta(hours=27)
    filename = f"projections_{old_time.strftime('%Y%m%d_%H%M%S')}.parquet"
    proj_file = tmp_data_root / "gold" / "projections" / filename

    proj_file.write_bytes(b"PAR1")
    import os

    os.utime(proj_file, (old_time.timestamp(), old_time.timestamp()))

    resp = get_freshness()

    assert resp.projections.age_hours is not None
    assert resp.projections.age_hours > 26  # > 26 hours
    assert resp.projections.stale is True
    assert resp.overall_stale is True


def test_freshness_rankings_json(tmp_data_root):
    """Test rankings freshness detection on JSON files."""
    now = datetime.now(tz=timezone.utc)
    rankings_file = (
        tmp_data_root / "external" / "sleeper_rankings.json"
    )

    rankings_file.write_text(json.dumps({"test": "data"}))

    resp = get_freshness()

    assert resp.rankings.age_hours is not None
    assert resp.rankings.age_hours < 1.0
    assert resp.rankings.stale is False


def test_freshness_odds_non_blocking_preseason(tmp_data_root, monkeypatch):
    """Test that odds are non-blocking (non-stale) in preseason."""

    def fake_is_in_season():
        return False

    monkeypatch.setattr(
        "web.api.routers.health_freshness.is_in_season",
        fake_is_in_season,
    )

    # No odds files at all
    resp = get_freshness()

    # Should be non-blocking -> stale=False
    assert resp.odds.stale is False
    # But overall should still be stale (projections/predictions/rankings)
    assert resp.overall_stale is True


def test_freshness_sentiment_non_blocking_in_season(tmp_data_root, monkeypatch):
    """Test that sentiment is non-blocking in-season when missing."""

    def fake_is_in_season():
        return True

    monkeypatch.setattr(
        "web.api.routers.health_freshness.is_in_season",
        fake_is_in_season,
    )

    # Add fresh projections and predictions to pass blocking thresholds
    now = datetime.now(tz=timezone.utc)

    proj_file = (
        tmp_data_root
        / "gold"
        / "projections"
        / f"proj_{now.strftime('%Y%m%d_%H%M%S')}.parquet"
    )
    proj_file.write_bytes(b"PAR1")

    pred_file = (
        tmp_data_root
        / "gold"
        / "predictions"
        / f"pred_{now.strftime('%Y%m%d_%H%M%S')}.parquet"
    )
    pred_file.write_bytes(b"PAR1")

    rank_file = tmp_data_root / "external" / "sleeper_rankings.json"
    rank_file.write_text("{}")

    resp = get_freshness()

    # Sentiment missing in-season IS stale, but it never blocks overall
    assert resp.sentiment.stale is True
    # Overall should be False (all blocking datasets present and fresh)
    assert resp.overall_stale is False


def test_freshness_response_json_serializable(tmp_data_root):
    """Test that the freshness response can be serialized to JSON."""
    resp = get_freshness()

    # Should be able to serialize
    json_str = resp.model_dump_json()
    assert json_str is not None

    # Should be able to deserialize
    parsed = json.loads(json_str)
    assert "projections" in parsed
    assert "overall_stale" in parsed
    assert "generated_at" in parsed


def test_freshness_generated_at_is_recent(tmp_data_root):
    """Test that generated_at timestamp is recent."""
    resp = get_freshness()

    generated = datetime.fromisoformat(resp.generated_at)
    now = datetime.now(tz=timezone.utc)

    # Should be within 1 second
    delta = abs((now - generated).total_seconds())
    assert delta < 1.0


def test_freshness_multiple_files_picks_newest(tmp_data_root):
    """Test that multiple files are scanned and newest is selected."""
    # Create 3 projection files at different times
    base_time = datetime.now(tz=timezone.utc)

    times = [
        base_time - timedelta(hours=3),
        base_time - timedelta(hours=1),  # Newest
        base_time - timedelta(hours=2),
    ]

    import os

    for i, t in enumerate(times):
        filename = f"proj_{i}_{t.strftime('%Y%m%d_%H%M%S')}.parquet"
        proj_file = tmp_data_root / "gold" / "projections" / filename
        proj_file.write_bytes(b"PAR1")
        os.utime(proj_file, (t.timestamp(), t.timestamp()))

    resp = get_freshness()

    # Should be ~1 hour old (the newest one)
    assert resp.projections.age_hours is not None
    assert 0.5 < resp.projections.age_hours < 1.5


def test_freshness_endpoint_integration():
    """Integration test: hit the actual endpoint via FastAPI test client."""
    pytest.importorskip("fastapi.testclient")

    from fastapi.testclient import TestClient

    from web.api.main import app

    client = TestClient(app)
    response = client.get("/api/health/freshness")

    assert response.status_code == 200
    data = response.json()

    assert "projections" in data
    assert "predictions" in data
    assert "rankings" in data
    assert "odds" in data
    assert "sentiment" in data
    assert "overall_stale" in data
    assert "generated_at" in data

    # Validate structure
    for dataset_name in [
        "projections",
        "predictions",
        "rankings",
        "odds",
        "sentiment",
    ]:
        dataset = data[dataset_name]
        assert "age_hours" in dataset or dataset["age_hours"] is None
        assert isinstance(dataset["stale"], bool)
