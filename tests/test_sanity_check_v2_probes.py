"""Unit tests for Phase 68 sanity-check v2 probes and validators.

These tests mock HTTP responses and filesystem state so the gate can be
validated against the 2026-04-20 regression shape (HTTP 422 on predictions /
lineups, HTTP 503 on sampled team rosters, 32-row-but-empty news payload,
stale Silver sentiment parquet mtime). No network calls.

Organization:
    - Task 1 (Tests 1-9): live endpoint probes + top-10 sampling helper
    - Task 2 (Tests 10-17): news content validator + extractor freshness

See ``.planning/phases/68-sanity-check-v2/68-01-live-probes-and-content-validators-PLAN.md``.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.sanity_check_projections as sanity  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _mock_response(status: int, json_data=None):
    """Build a MagicMock shaped like a requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    if json_data is None:
        resp.json.return_value = {}
    else:
        resp.json.return_value = json_data
    resp.text = ""
    return resp


_ALL_32_TEAMS = [
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LA",
    "LAC",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
]


# ===========================================================================
# Task 1 — live probe tests (9 tests)
# ===========================================================================


# --- Test 1: predictions 422 -> CRITICAL ----------------------------------


def test_probe_predictions_flags_422_as_critical():
    """The 2026-04-20 audit regression: /api/predictions returning HTTP 422."""
    with patch.object(
        sanity.requests,
        "get",
        return_value=_mock_response(422, {"detail": "field required"}),
    ):
        criticals, warnings = sanity._probe_predictions_endpoint(
            "https://example.test", season=2026, week=1
        )
    assert len(criticals) == 1
    assert "422" in criticals[0]
    assert "/api/predictions" in criticals[0]
    assert warnings == []


# --- Test 2: predictions 200 non-empty -> PASS ----------------------------


def test_probe_predictions_passes_on_200_with_predictions():
    """Healthy state: HTTP 200 with a populated predictions list."""
    payload = {
        "predictions": [{"home_team": "KC", "away_team": "BUF"}],
        "season": 2026,
        "week": 1,
    }
    with patch.object(
        sanity.requests, "get", return_value=_mock_response(200, payload)
    ):
        criticals, warnings = sanity._probe_predictions_endpoint(
            "https://example.test", season=2026, week=1
        )
    assert criticals == []
    assert warnings == []


# --- Test 3: predictions 200 empty list -> PASS (offseason allowed) -------


def test_probe_predictions_allows_empty_list_in_offseason():
    """Empty predictions list is legitimate (preseason / no schedule)."""
    payload = {"predictions": [], "season": 2026, "week": 1}
    with patch.object(
        sanity.requests, "get", return_value=_mock_response(200, payload)
    ):
        criticals, warnings = sanity._probe_predictions_endpoint(
            "https://example.test", season=2026, week=1
        )
    assert criticals == []
    assert warnings == []


# --- Test 4: lineups 422 -> CRITICAL --------------------------------------


def test_probe_lineups_flags_422_as_critical():
    """The 2026-04-20 audit regression: /api/lineups returning HTTP 422."""
    with patch.object(
        sanity.requests,
        "get",
        return_value=_mock_response(422, {"detail": "field required"}),
    ):
        criticals, warnings = sanity._probe_lineups_endpoint(
            "https://example.test", season=2026, week=1
        )
    assert len(criticals) == 1
    assert "422" in criticals[0]
    assert "/api/lineups" in criticals[0]
    assert warnings == []


# --- Test 5: lineups 200 -> PASS ------------------------------------------


def test_probe_lineups_passes_on_200_with_lineups_key():
    """Healthy state: HTTP 200 with a lineups list (any length, including empty)."""
    payload = {"lineups": [], "season": 2026, "week": 1}
    with patch.object(
        sanity.requests, "get", return_value=_mock_response(200, payload)
    ):
        criticals, warnings = sanity._probe_lineups_endpoint(
            "https://example.test", season=2026, week=1
        )
    assert criticals == []
    assert warnings == []


# --- Test 6: team rosters 503 across top-10 -> CRITICAL -------------------


def test_probe_team_rosters_flags_503_as_critical():
    """503s on all top-10 sampled teams produce a single aggregated CRITICAL."""

    def _503_for_rosters(url, *args, **kwargs):
        return _mock_response(503, {"detail": "Service unavailable"})

    # Force the fallback list so the test is independent of Silver data state
    # and URL matching is deterministic.
    with patch.object(
        sanity,
        "_top_n_teams_by_snap_count",
        return_value=(list(sanity._TOP_10_TEAMS_FALLBACK), None),
    ), patch.object(sanity.requests, "get", side_effect=_503_for_rosters):
        criticals, warnings = sanity._probe_team_rosters_sampled(
            "https://example.test", season=2025
        )
    assert len(criticals) == 1
    crit = criticals[0]
    assert "10/10 sampled teams" in crit
    assert "503" in crit
    # At least 5 team abbreviations must appear in the aggregated message.
    team_hits = sum(1 for t in sanity._TOP_10_TEAMS_FALLBACK if t in crit)
    assert team_hits >= 5, f"expected ≥5 team abbrs in {crit!r}"


# --- Test 7: team rosters 200 -> PASS -------------------------------------


def test_probe_team_rosters_passes_when_all_ten_return_200():
    """Healthy state: every sampled team returns 200 with non-empty players."""

    def _healthy(url, *args, **kwargs):
        return _mock_response(200, {"players": [{"id": "x"}]})

    with patch.object(
        sanity,
        "_top_n_teams_by_snap_count",
        return_value=(list(sanity._TOP_10_TEAMS_FALLBACK), None),
    ), patch.object(sanity.requests, "get", side_effect=_healthy):
        criticals, warnings = sanity._probe_team_rosters_sampled(
            "https://example.test", season=2025
        )
    assert criticals == []
    # No fallback warning because the patched helper returned warning=None.
    assert warnings == []


# --- Test 8: fallback list used when no Silver team_metrics ---------------


def test_top_n_teams_falls_back_to_hardcoded_list(tmp_path, monkeypatch):
    """With no team_metrics and no snaps parquet, fallback list is returned."""
    # Redirect PROJECT_ROOT to an empty tmp directory so all globs miss.
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))

    teams, warning = sanity._top_n_teams_by_snap_count(2025, n=10)
    assert teams == sanity._TOP_10_TEAMS_FALLBACK
    assert teams == [
        "KC",
        "BUF",
        "PHI",
        "DET",
        "BAL",
        "SF",
        "MIA",
        "CIN",
        "GB",
        "DAL",
    ]
    assert warning is not None
    assert "SAMPLING FALLBACK" in warning


# --- Test 9: timeout -> CRITICAL with TIMEOUT token -----------------------


def test_probe_predictions_flags_timeout_as_critical():
    """When requests.get raises Timeout, probe returns CRITICAL mentioning TIMEOUT."""
    with patch.object(
        sanity.requests,
        "get",
        side_effect=requests.exceptions.Timeout("read timeout"),
    ):
        criticals, warnings = sanity._probe_predictions_endpoint(
            "https://example.test", season=2026, week=1
        )
    assert len(criticals) == 1
    assert "TIMEOUT" in criticals[0]
    assert "/api/predictions" in criticals[0]
    assert warnings == []


# ===========================================================================
# Task 2 — news content validator + extractor freshness tests (8 tests)
# ===========================================================================


def _team_events_payload(
    healthy_teams: int, total_teams: int = 32, articles_per_team: int = 5
):
    """Build a mock /api/news/team-events payload with ``healthy_teams`` populated."""
    assert 0 <= healthy_teams <= total_teams
    return [
        {
            "team": _ALL_32_TEAMS[i],
            "total_articles": articles_per_team if i < healthy_teams else 0,
            "negative_event_count": 1 if i < healthy_teams else 0,
            "positive_event_count": 1 if i < healthy_teams else 0,
            "neutral_event_count": 3 if i < healthy_teams else 0,
            "sentiment_label": "neutral",
            "top_events": [],
        }
        for i in range(total_teams)
    ]


# --- Test 10: content validator — ≥20 teams populated -> PASS --------------


def test_validate_team_events_passes_when_enough_teams_have_articles():
    """≥20 of 32 teams with total_articles > 0 = healthy news extraction."""
    payload = _team_events_payload(healthy_teams=25)
    criticals, warnings = sanity._validate_team_events_content(payload)
    assert criticals == []
    assert warnings == []


# --- Test 11: content validator — all empty -> CRITICAL --------------------


def test_validate_team_events_flags_all_empty_as_critical():
    """All 32 rows present but zero articles = stalled extractor (2026-04-20 regression)."""
    payload = _team_events_payload(healthy_teams=0)
    criticals, warnings = sanity._validate_team_events_content(payload)
    assert len(criticals) == 1
    assert "NEWS CONTENT EMPTY" in criticals[0]
    assert "0/32" in criticals[0]
    assert warnings == []


# --- Test 12: content validator — 12 populated -> CRITICAL (below 17) -----


def test_validate_team_events_flags_thin_content_as_critical():
    """12/32 with articles is below the WARN threshold of 17 -> CRITICAL."""
    payload = _team_events_payload(healthy_teams=12)
    criticals, warnings = sanity._validate_team_events_content(payload)
    assert len(criticals) == 1
    assert "NEWS CONTENT EMPTY" in criticals[0]
    assert "12/32" in criticals[0]
    assert warnings == []


# --- Test 13: content validator — 18 populated -> WARNING (17..19 band) ---


def test_validate_team_events_flags_marginal_as_warning():
    """18/32 falls in the marginal band (17..19) -> WARNING, not CRITICAL."""
    payload = _team_events_payload(healthy_teams=18)
    criticals, warnings = sanity._validate_team_events_content(payload)
    assert criticals == []
    assert len(warnings) == 1
    assert "NEWS CONTENT MARGINAL" in warnings[0]
    assert "18/32" in warnings[0]


# --- Test 14: extractor freshness — fresh file -> PASS --------------------


def _write_fresh_parquet(tmp_path: Path, age_hours: float) -> Path:
    """Create an empty file and backdate its mtime by ``age_hours``."""
    parquet = (
        tmp_path
        / "data"
        / "silver"
        / "sentiment"
        / "signals"
        / "season=2025"
        / "week=01"
        / "signals_test.parquet"
    )
    parquet.parent.mkdir(parents=True, exist_ok=True)
    parquet.write_bytes(b"")
    target_mtime = time.time() - (age_hours * 3600.0)
    os.utime(parquet, (target_mtime, target_mtime))
    return parquet


def test_extractor_freshness_passes_when_recent(tmp_path, monkeypatch):
    """Parquet written within 24h = PASS, no criticals or warnings."""
    _write_fresh_parquet(tmp_path, age_hours=2.0)
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))

    criticals, warnings = sanity._check_extractor_freshness()
    assert criticals == []
    assert warnings == []


# --- Test 15: extractor freshness — 36h old -> WARNING --------------------


def test_extractor_freshness_warns_in_24_to_48h_band(tmp_path, monkeypatch):
    """Parquet in the 24..48h band produces WARNING only."""
    _write_fresh_parquet(tmp_path, age_hours=36.0)
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))

    criticals, warnings = sanity._check_extractor_freshness()
    assert criticals == []
    assert len(warnings) == 1
    assert "EXTRACTOR STALE" in warnings[0]
    assert "36" in warnings[0]


# --- Test 16: extractor freshness — 72h old -> CRITICAL -------------------


def test_extractor_freshness_critical_when_older_than_48h(tmp_path, monkeypatch):
    """Parquet older than 48h = CRITICAL (daily cron has stopped)."""
    _write_fresh_parquet(tmp_path, age_hours=72.0)
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))

    criticals, warnings = sanity._check_extractor_freshness()
    assert len(criticals) == 1
    assert "EXTRACTOR STALE" in criticals[0]
    assert "72" in criticals[0]
    assert warnings == []


# --- Test 17: extractor freshness — no files -> CRITICAL -----------------


def test_extractor_freshness_critical_when_no_files(tmp_path, monkeypatch):
    """Missing parquet directory entirely = CRITICAL (never ran)."""
    # tmp_path is empty; no data/silver/sentiment/... exists.
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))

    criticals, warnings = sanity._check_extractor_freshness()
    assert len(criticals) == 1
    assert "EXTRACTOR DATA MISSING" in criticals[0]
    assert warnings == []


# --- Test 18: extractor freshness — JSON sink (Phase 71+) -> PASS ---------


def test_extractor_freshness_recognizes_json_files(tmp_path, monkeypatch):
    """Phase 71+ writes JSON envelopes (not parquet); freshness must still PASS."""
    json_file = (
        tmp_path
        / "data"
        / "silver"
        / "sentiment"
        / "signals"
        / "season=2025"
        / "week=18"
        / "signals_abc.json"
    )
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_bytes(b"{}")
    target_mtime = time.time() - (2.0 * 3600.0)
    os.utime(json_file, (target_mtime, target_mtime))
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))

    criticals, warnings = sanity._check_extractor_freshness()
    assert criticals == []
    assert warnings == []
