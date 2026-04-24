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

import os
import re
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

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


# ===========================================================================
# Phase 68-02 Task 3 — end-to-end canary covering ALL 6 audit regressions
# ===========================================================================


def test_canary_detects_all_six_regressions(tmp_path, monkeypatch):
    """THE acceptance canary: all 6 regressions from 2026-04-20 audit produce CRITICALs.

    Wires together:
      1. Plan 68-01's HTTP mocks (_pre_v7_response) — regressions #2, #3, #4, #5
      2. A mocked Sleeper response with Kyler as FA — regression #1
      3. A stale (72h) Silver sentiment fixture — regression #6
      4. ENABLE_LLM_ENRICHMENT=true with ANTHROPIC_API_KEY unset — regression #5 key

    This is the phase acceptance gate (success criterion #1 from ROADMAP):
    running the v2 gate against pre-v7.0 state MUST surface at least one
    distinct CRITICAL per regression.
    """
    # --- Redirect filesystem-rooted helpers to tmp fixtures -------------------
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sanity, "GOLD_DIR", str(tmp_path / "data" / "gold"))
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))

    # --- Build Gold projections with Kyler still on ARI (pre-v7.0 state) ----
    top50_df = pd.DataFrame(
        [
            {
                "player_name": "Kyler Murray",
                "team": "ARI",
                "position": "QB",
                "projected_points": 280.5,
                "projected_season_points": 280.5,
                "scoring": "half_ppr",
            },
            *[
                {
                    "player_name": f"Player {i}",
                    "team": "KC",
                    "position": "WR",
                    "projected_points": 200.0 - i,
                    "projected_season_points": 200.0 - i,
                    "scoring": "half_ppr",
                }
                for i in range(1, 50)
            ],
        ]
    )

    # --- Stale Silver sentiment fixture — mtime 72h old -> CRITICAL ---------
    silver_dir = (
        tmp_path
        / "data"
        / "silver"
        / "sentiment"
        / "signals"
        / "season=2025"
        / "week=01"
    )
    silver_dir.mkdir(parents=True, exist_ok=True)
    stale_file = silver_dir / "stale.parquet"
    stale_file.write_bytes(b"")
    stale_mtime = time.time() - (72 * 3600)
    os.utime(stale_file, (stale_mtime, stale_mtime))

    # --- Mock Sleeper response: Kyler has team=None (FA) --------------------
    fake_sleeper = {
        "kyler_id": {
            "full_name": "Kyler Murray",
            "team": None,
            "position": "QB",
        },
        **{
            f"p{i}": {
                "full_name": f"Player {i}",
                "team": "KC",
                "position": "WR",
            }
            for i in range(1, 50)
        },
    }

    # --- Combined HTTP side_effect: route both Railway probes AND Sleeper ---
    def combined_response(url, *args, **kwargs):
        if "api.sleeper.app" in url:
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = fake_sleeper
            return resp
        return _pre_v7_response(url, *args, **kwargs)

    # --- Regression #5 env trigger: ENABLE_LLM_ENRICHMENT=true, key missing -
    monkeypatch.setenv("ENABLE_LLM_ENRICHMENT", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # --- Run all relevant checks ---------------------------------------------
    with patch.object(
        sanity,
        "_top_n_teams_by_snap_count",
        return_value=(list(sanity._TOP_10_TEAMS_FALLBACK), None),
    ), patch.object(
        sanity, "_load_our_projections", return_value=top50_df
    ), patch.object(
        sanity.requests, "get", side_effect=combined_response
    ):
        # Live probe criticals (regressions #2, #3, #4, #5-news-content, #6 freshness)
        live_crit, _ = sanity.run_live_site_check(
            backend_url="https://x.railway.app",
            frontend_url="https://x.vercel.app",
            season=2026,
        )
        # Non-live criticals (regression #1 drift, regression #5 missing key)
        drift_crit, _ = sanity._check_roster_drift_top50("half_ppr", 2026)
        key_crit, _ = sanity._assert_api_key_when_enrichment_enabled()

    all_criticals = live_crit + drift_crit + key_crit
    crits_str = " || ".join(all_criticals)

    # --- Assert each of the 6 regressions surfaces a distinct CRITICAL ------
    assert "Kyler Murray" in crits_str and (
        "FA" in crits_str or "ARI" in crits_str
    ), f"Missing Kyler Murray roster drift CRITICAL (regression #1). Got: {crits_str}"
    assert (
        "/api/predictions" in crits_str and "422" in crits_str
    ), f"Missing /api/predictions 422 CRITICAL (regression #2). Got: {crits_str}"
    assert (
        "/api/lineups" in crits_str and "422" in crits_str
    ), f"Missing /api/lineups 422 CRITICAL (regression #3). Got: {crits_str}"
    assert (
        "/api/teams" in crits_str or "ROSTER PROBE" in crits_str
    ) and "503" in crits_str, (
        f"Missing /api/teams/*/roster 503 CRITICAL (regression #4). Got: {crits_str}"
    )
    assert (
        "NEWS CONTENT EMPTY" in crits_str or "API KEY MISSING" in crits_str
    ), f"Missing news extractor/API key CRITICAL (regression #5). Got: {crits_str}"
    assert (
        "EXTRACTOR STALE" in crits_str and "72" in crits_str
    ), f"Missing stalled-extractor freshness CRITICAL (regression #6). Got: {crits_str}"

    # --- Aggregate cardinality: at least 6 distinct CRITICALs ---------------
    assert len(all_criticals) >= 6, (
        f"Expected >= 6 distinct CRITICAL findings for 6 audit regressions; "
        f"got {len(all_criticals)}:\n" + "\n".join(f"  - {c}" for c in all_criticals)
    )
