"""Phase 68 SANITY canary — prove the v2 gate catches the 2026-04-20 audit regressions.

This is an integration-style test that mocks the HTTP surface of the deployed
Railway backend to reproduce the four endpoint-class regressions from the
2026-04-20 user audit:

    1. /api/predictions returns HTTP 422 (frontend omits season/week)
    2. /api/lineups returns HTTP 422 (same pattern)
    3. /api/teams/{team}/roster returns HTTP 503 (Docker image missing Bronze)
    4. /api/news/team-events returns 32 rows but every row has total_articles=0
       (extractor never ran because ANTHROPIC_API_KEY unset on Railway)

The canary MUST surface one CRITICAL finding per regression. A complementary
test confirms the gate does NOT false-positive on a healthy state.

The two remaining regressions from the audit — Kyler Murray roster drift
(SANITY-05) and Silver sentiment freshness CRITICAL (SANITY-06) — depend on
filesystem state and are covered in Plan 68-02's canary extension.

No network calls: every requests.get is patched via a side_effect function
keyed off the URL path.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.sanity_check_projections as sanity  # noqa: E402


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


def _pre_v7_response(url, *args, **kwargs):
    """Reproduce the 4 endpoint-class HTTP regressions from the 2026-04-20 audit.

    Maps regression -> mocked response so a single run_live_site_check() pass
    surfaces all 4 CRITICAL findings.
    """
    resp = MagicMock()
    resp.text = "<html><body>NFL Analytics Projections</body></html>" * 30
    if "/api/predictions" in url:
        # Audit finding #2: 422 on /api/predictions (frontend omits season/week).
        resp.status_code = 422
        resp.json.return_value = {
            "detail": [{"loc": ["query", "season"], "msg": "field required"}]
        }
    elif "/api/lineups" in url:
        # Audit finding #3: 422 on /api/lineups (same pattern).
        resp.status_code = 422
        resp.json.return_value = {"detail": [{"msg": "field required"}]}
    elif re.search(r"/api/teams/[A-Z]{2,3}/roster", url):
        # Audit finding #3/#4: 503 on /api/teams/*/roster (Docker image
        # missing data/bronze/schedules/).
        resp.status_code = 503
        resp.json.return_value = {"detail": "Service temporarily unavailable"}
    elif "/api/news/team-events" in url:
        # Audit finding #5: stalled extractor → 32 rows but all empty.
        resp.status_code = 200
        resp.json.return_value = [
            {
                "team": t,
                "total_articles": 0,
                "negative_event_count": 0,
                "positive_event_count": 0,
                "neutral_event_count": 0,
                "sentiment_label": "neutral",
                "top_events": [],
            }
            for t in _ALL_32_TEAMS
        ]
    elif "/api/health" in url:
        resp.status_code = 200
        resp.json.return_value = {"status": "ok", "llm_enrichment_ready": False}
    elif "/api/projections" in url:
        resp.status_code = 200
        resp.json.return_value = {
            "projections": [{"player_id": "x", "projected_points": 1.0}],
            "season": 2026,
            "week": 1,
        }
    else:
        resp.status_code = 200
        resp.json.return_value = {}
    return resp


def test_canary_detects_four_endpoint_regressions():
    """Re-running --check-live against pre-v7.0 prod state MUST emit ≥4 distinct CRITICALs."""
    # Force the top-10 fallback list so the test is independent of Silver state.
    with patch.object(
        sanity,
        "_top_n_teams_by_snap_count",
        return_value=(list(sanity._TOP_10_TEAMS_FALLBACK), None),
    ), patch.object(sanity.requests, "get", side_effect=_pre_v7_response):
        criticals, warnings = sanity.run_live_site_check(
            backend_url="https://nfldataengineering-production.up.railway.app",
            frontend_url="https://frontend-jet-seven-33.vercel.app",
            season=2026,
        )

    # Must surface at least 4 CRITICALs naming each endpoint-class regression.
    crits_str = " | ".join(criticals)
    assert (
        "/api/predictions" in crits_str and "422" in crits_str
    ), f"Missing /api/predictions 422 critical. Got: {crits_str}"
    assert (
        "/api/lineups" in crits_str and "422" in crits_str
    ), f"Missing /api/lineups 422 critical. Got: {crits_str}"
    assert (
        "ROSTER PROBE FAILED" in crits_str or "/api/teams" in crits_str
    ), f"Missing /api/teams/*/roster 503 critical. Got: {crits_str}"
    assert "NEWS CONTENT" in crits_str and (
        "EMPTY" in crits_str or "0/32" in crits_str
    ), f"Missing news content extractor-stalled critical. Got: {crits_str}"
    assert (
        len(criticals) >= 4
    ), f"Expected ≥4 distinct CRITICAL findings; got {len(criticals)}: {criticals}"


def _healthy_response(url, *args, **kwargs):
    """Healthy state: every endpoint returns a well-shaped 200 payload."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "<html><body>NFL Analytics Projections lineup</body></html>" * 30
    if "/api/news/team-events" in url:
        resp.json.return_value = [
            {
                "team": t,
                "total_articles": 5,
                "negative_event_count": 1,
                "positive_event_count": 1,
                "neutral_event_count": 3,
                "sentiment_label": "neutral",
                "top_events": [],
            }
            for t in _ALL_32_TEAMS
        ]
    elif "/api/predictions" in url:
        resp.json.return_value = {
            "predictions": [],
            "season": 2026,
            "week": 1,
        }
    elif "/api/lineups" in url:
        resp.json.return_value = {"lineups": [], "season": 2026, "week": 1}
    elif "/api/projections" in url:
        resp.json.return_value = {
            "projections": [{"player_id": "x", "projected_points": 1.0}],
            "season": 2026,
            "week": 1,
        }
    elif re.search(r"/api/teams/[A-Z]{2,3}/roster", url):
        resp.json.return_value = {"players": [{"id": "x"}]}
    elif "/api/health" in url:
        resp.json.return_value = {"status": "ok", "llm_enrichment_ready": True}
    else:
        resp.json.return_value = {}
    return resp


def test_canary_passes_against_healthy_state():
    """Sanity: when all endpoints return healthy responses, no CRITICALs surface."""
    with patch.object(
        sanity,
        "_top_n_teams_by_snap_count",
        return_value=(list(sanity._TOP_10_TEAMS_FALLBACK), None),
    ), patch.object(sanity.requests, "get", side_effect=_healthy_response):
        criticals, _ = sanity.run_live_site_check(
            backend_url="https://nfldataengineering-production.up.railway.app",
            frontend_url="https://frontend-jet-seven-33.vercel.app",
            season=2026,
        )

    # Endpoint criticals must all be absent. Extractor freshness is handled
    # separately against local filesystem state and may legitimately flag
    # stale/missing Silver sentiment here — that's Plan 68-02's canary.
    endpoint_crits = [
        c
        for c in criticals
        if "/api/" in c or "ROSTER PROBE" in c or "NEWS CONTENT" in c
    ]
    assert (
        endpoint_crits == []
    ), f"Healthy state produced false-positive endpoint CRITICALs: {endpoint_crits}"
