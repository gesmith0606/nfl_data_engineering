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
