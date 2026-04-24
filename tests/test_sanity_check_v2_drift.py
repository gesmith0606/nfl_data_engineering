"""Unit tests for Phase 68-02 roster drift + API key + DQAL-03 carry-over checks.

Tests are organized by task:
    - Task 1 (Tests 1-6): _check_roster_drift_top50 + _fetch_sleeper_canonical_cached
      including the Kyler Murray acceptance canary (ARI→FA drift).
    - Task 2 (Tests 7-16): _assert_api_key_when_enrichment_enabled + 3 DQAL-03
      assertions (negative-projection clamp, rookie ingestion, rank-gap).

No network calls: requests.get is mocked on every path that touches Sleeper.

See ``.planning/phases/68-sanity-check-v2/68-02-roster-drift-apikey-dqal-PLAN.md``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.sanity_check_projections as sanity  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _build_fake_top50(include_kyler_on_ari: bool = True) -> pd.DataFrame:
    """Build a mock Gold projections DataFrame top-50 with optional Kyler-on-ARI row.

    Every row except Kyler has team="KC" so a single Kyler→ARI vs Sleeper→FA row
    is the only drift when Sleeper says Kyler is FA.
    """
    rows = []
    if include_kyler_on_ari:
        rows.append(
            {
                "player_name": "Kyler Murray",
                "team": "ARI",
                "position": "QB",
                "projected_points": 280.5,
                "projected_season_points": 280.5,
                "scoring": "half_ppr",
            }
        )
        start = 1
    else:
        start = 0
    for i in range(start, 50):
        rows.append(
            {
                "player_name": f"Player {i}",
                "team": "KC",
                "position": "WR",
                "projected_points": 200.0 - i,
                "projected_season_points": 200.0 - i,
                "scoring": "half_ppr",
            }
        )
    return pd.DataFrame(rows)


def _build_fake_sleeper(kyler_team: str | None = None) -> dict:
    """Build a mock Sleeper /v1/players/nfl payload keyed by sleeper_player_id."""
    players = {
        "k_id": {
            "full_name": "Kyler Murray",
            "team": kyler_team,  # None == free agent/released
            "position": "QB",
        }
    }
    for i in range(1, 50):
        players[f"p{i}"] = {
            "full_name": f"Player {i}",
            "team": "KC",
            "position": "WR",
        }
    return players


def _mock_sleeper_response(status: int, json_data):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


# ===========================================================================
# Task 1 — Roster drift + Sleeper cache (Tests 1-6)
# ===========================================================================


# --- Test 1: all match -> no criticals ------------------------------------


def test_roster_drift_returns_empty_when_top50_all_match(tmp_path, monkeypatch):
    """Healthy state: every top-50 player's team matches Sleeper canonical."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))
    # Return the top-50 DataFrame directly, bypassing the Gold filesystem read.
    top50_df = _build_fake_top50(include_kyler_on_ari=False)
    # In this flavor every Player i has team KC in both our frame and Sleeper.
    top50_df.loc[0, "player_name"] = "Kyler Murray"
    top50_df.loc[0, "team"] = "KC"  # match Sleeper KC
    sleeper_resp = _mock_sleeper_response(200, _build_fake_sleeper(kyler_team="KC"))

    with patch.object(sanity, "_load_our_projections", return_value=top50_df), patch.object(
        sanity.requests, "get", return_value=sleeper_resp
    ):
        criticals, warnings = sanity._check_roster_drift_top50("half_ppr", 2026)

    assert criticals == []
    # No fetch warning expected; possibly no warnings at all.
    assert not any("ROSTER DRIFT" in w for w in warnings)


# --- Test 2: Kyler Murray canary — ARI→FA mismatch -> CRITICAL -----------


def test_roster_drift_flags_kyler_murray_as_critical(tmp_path, monkeypatch):
    """THE acceptance canary: Gold says ARI, Sleeper says None (FA) → CRITICAL."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))
    top50_df = _build_fake_top50(include_kyler_on_ari=True)
    sleeper_resp = _mock_sleeper_response(200, _build_fake_sleeper(kyler_team=None))

    with patch.object(sanity, "_load_our_projections", return_value=top50_df), patch.object(
        sanity.requests, "get", return_value=sleeper_resp
    ):
        criticals, warnings = sanity._check_roster_drift_top50("half_ppr", 2026)

    assert len(criticals) == 1, f"expected exactly 1 Kyler drift CRITICAL, got: {criticals}"
    crit = criticals[0]
    assert "Kyler Murray" in crit
    assert "ARI" in crit
    # Must name FA explicitly so the reviewer can see the mismatch is release-related.
    assert "FA" in crit


def test_kyler_canary(tmp_path, monkeypatch):
    """Alias test to satisfy plan's canonical canary test name in acceptance grep."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))
    top50_df = _build_fake_top50(include_kyler_on_ari=True)
    sleeper_resp = _mock_sleeper_response(200, _build_fake_sleeper(kyler_team=None))

    with patch.object(sanity, "_load_our_projections", return_value=top50_df), patch.object(
        sanity.requests, "get", return_value=sleeper_resp
    ):
        criticals, _ = sanity._check_roster_drift_top50("half_ppr", 2026)

    assert any("Kyler Murray" in c and "ARI" in c for c in criticals)


# --- Test 3: multiple mismatches aggregate one CRITICAL per player -------


def test_roster_drift_emits_one_critical_per_mismatched_player(
    tmp_path, monkeypatch
):
    """Multiple mismatches must produce one CRITICAL per player, not one combined."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))
    top50_df = pd.DataFrame(
        [
            {
                "player_name": "Kyler Murray",
                "team": "ARI",
                "position": "QB",
                "projected_points": 280.5,
                "projected_season_points": 280.5,
            },
            {
                "player_name": "Davante Adams",
                "team": "LV",
                "position": "WR",
                "projected_points": 230.0,
                "projected_season_points": 230.0,
            },
            {
                "player_name": "Saquon Barkley",
                "team": "NYG",
                "position": "RB",
                "projected_points": 210.0,
                "projected_season_points": 210.0,
            },
        ]
    )
    sleeper_players = {
        "k": {"full_name": "Kyler Murray", "team": None, "position": "QB"},  # FA
        "a": {"full_name": "Davante Adams", "team": "LA", "position": "WR"},  # moved
        "b": {"full_name": "Saquon Barkley", "team": "PHI", "position": "RB"},  # moved
    }
    sleeper_resp = _mock_sleeper_response(200, sleeper_players)

    with patch.object(sanity, "_load_our_projections", return_value=top50_df), patch.object(
        sanity.requests, "get", return_value=sleeper_resp
    ):
        criticals, _ = sanity._check_roster_drift_top50("half_ppr", 2026)

    assert len(criticals) == 3, f"expected one CRITICAL per player, got: {criticals}"
    kyler = next(c for c in criticals if "Kyler Murray" in c)
    adams = next(c for c in criticals if "Davante Adams" in c)
    barkley = next(c for c in criticals if "Saquon Barkley" in c)
    assert "FA" in kyler
    assert "LV" in adams and "LA" in adams
    assert "NYG" in barkley and "PHI" in barkley


# --- Test 4: Sleeper cache is reused on same-day re-call -----------------


def test_sleeper_cache_reused_on_same_day(tmp_path, monkeypatch):
    """Per-day disk cache: same-day second call must NOT hit the network."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))
    sleeper_payload = _build_fake_sleeper(kyler_team="ARI")
    call_count = {"n": 0}

    def _counting_get(url, *args, **kwargs):
        call_count["n"] += 1
        return _mock_sleeper_response(200, sleeper_payload)

    with patch.object(sanity.requests, "get", side_effect=_counting_get):
        first, warn1 = sanity._fetch_sleeper_canonical_cached()
        second, warn2 = sanity._fetch_sleeper_canonical_cached()

    assert call_count["n"] == 1, f"expected exactly 1 network call, got {call_count['n']}"
    assert warn1 is None
    assert warn2 is None
    assert first == sleeper_payload
    assert second == sleeper_payload


# --- Test 5: ConnectionError degrades to WARNING, never CRITICAL ---------


def test_sleeper_unreachable_returns_warning_not_critical(tmp_path, monkeypatch):
    """Upstream Sleeper outage must not block our deploys — return WARNING only."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))

    with patch.object(
        sanity.requests,
        "get",
        side_effect=requests.exceptions.ConnectionError("upstream down"),
    ):
        players, warning = sanity._fetch_sleeper_canonical_cached()

    assert players == {}
    assert warning is not None
    assert "SLEEPER API UNREACHABLE" in warning
    # Also verify the drift check does NOT emit a CRITICAL in this case.
    top50_df = _build_fake_top50(include_kyler_on_ari=True)
    with patch.object(sanity, "_load_our_projections", return_value=top50_df), patch.object(
        sanity.requests,
        "get",
        side_effect=requests.exceptions.ConnectionError("upstream down"),
    ):
        criticals, warnings = sanity._check_roster_drift_top50("half_ppr", 2026)
    assert criticals == []
    assert any("SLEEPER API UNREACHABLE" in w for w in warnings)


# --- Test 6: cache file actually written to data/.cache/sleeper_players_... ---


def test_sleeper_cache_file_written_to_expected_path(tmp_path, monkeypatch):
    """First call must persist cache at data/.cache/sleeper_players_YYYYMMDD.json."""
    from datetime import datetime, timezone

    cache_dir = tmp_path / ".cache"
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(cache_dir))
    sleeper_payload = _build_fake_sleeper(kyler_team="ARI")

    with patch.object(
        sanity.requests,
        "get",
        return_value=_mock_sleeper_response(200, sleeper_payload),
    ):
        _, _ = sanity._fetch_sleeper_canonical_cached()

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    expected = cache_dir / f"sleeper_players_{today}.json"
    assert expected.exists(), f"expected cache file at {expected}"
    with open(expected) as fh:
        loaded = json.load(fh)
    assert loaded == sleeper_payload


# ===========================================================================
# Task 2 — API key assertion + DQAL-03 checks (Tests 7-16)
# ===========================================================================


# --- Test 7: ENABLE_LLM_ENRICHMENT=true + ANTHROPIC_API_KEY unset -> CRITICAL -


def test_api_key_missing_critical_when_enrichment_enabled(monkeypatch):
    """SANITY-07: env flag on but key unset must CRITICAL-block the gate."""
    monkeypatch.setenv("ENABLE_LLM_ENRICHMENT", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    criticals, warnings = sanity._assert_api_key_when_enrichment_enabled()

    assert len(criticals) == 1
    crit = criticals[0]
    assert "ANTHROPIC_API_KEY" in crit
    assert "ENABLE_LLM_ENRICHMENT" in crit
    assert "unset" in crit.lower()
    assert warnings == []


# --- Test 8: ENABLE_LLM_ENRICHMENT=false -> no criticals ------------------


def test_api_key_ok_when_enrichment_disabled(monkeypatch):
    """SANITY-07: when flag off, key presence is irrelevant -> no criticals."""
    monkeypatch.setenv("ENABLE_LLM_ENRICHMENT", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    criticals, warnings = sanity._assert_api_key_when_enrichment_enabled()

    assert criticals == []
    assert warnings == []


# --- Test 9: both set -> no criticals ------------------------------------


def test_api_key_ok_when_both_set(monkeypatch):
    """SANITY-07: normal healthy state emits no findings."""
    monkeypatch.setenv("ENABLE_LLM_ENRICHMENT", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-fake-fake")

    criticals, warnings = sanity._assert_api_key_when_enrichment_enabled()

    assert criticals == []
    assert warnings == []


# --- Test 10: negative projection -> CRITICAL -----------------------------


def test_dqal_negative_projection_flags_below_zero(tmp_path, monkeypatch):
    """DQAL-03: any row with projected_points < 0 must CRITICAL-block."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))
    df = pd.DataFrame(
        [
            {"player_name": "Alpha QB", "position": "QB", "projected_points": 250.0},
            {"player_name": "Buggy WR", "position": "WR", "projected_points": -3.2},
            {"player_name": "Zero RB", "position": "RB", "projected_points": 0.0},
        ]
    )

    with patch.object(sanity, "_load_our_projections", return_value=df):
        criticals, warnings = sanity._check_dqal_negative_projection("half_ppr", 2026)

    assert len(criticals) == 1
    crit = criticals[0]
    assert "NEGATIVE PROJECTION" in crit
    assert "Buggy WR" in crit
    assert "-3.2" in crit or "-3.20" in crit
    assert warnings == []


# --- Test 11: all >= 0 -> no criticals -----------------------------------


def test_dqal_negative_projection_passes_when_all_nonnegative(tmp_path, monkeypatch):
    """Healthy state: every projected_points >= 0 must pass."""
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))
    df = pd.DataFrame(
        [
            {"player_name": "Alpha QB", "position": "QB", "projected_points": 250.0},
            {"player_name": "Beta WR", "position": "WR", "projected_points": 0.0},
            {"player_name": "Gamma RB", "position": "RB", "projected_points": 180.0},
        ]
    )

    with patch.object(sanity, "_load_our_projections", return_value=df):
        criticals, warnings = sanity._check_dqal_negative_projection("half_ppr", 2026)

    assert criticals == []
    assert warnings == []


# --- Test 12: rookie path missing -> CRITICAL ----------------------------


def test_dqal_rookie_ingestion_critical_when_path_missing(tmp_path, monkeypatch):
    """DQAL-03: missing 2025 rookies directory == ingestion never ran."""
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))

    criticals, warnings = sanity._check_dqal_rookie_ingestion(season=2025)

    assert len(criticals) == 1
    crit = criticals[0]
    assert "ROOKIE INGESTION MISSING" in crit
    assert "not found" in crit.lower()
    assert warnings == []


# --- Test 13: rookie parquet thin (<50) -> CRITICAL ----------------------


def test_dqal_rookie_ingestion_critical_when_under_threshold(tmp_path, monkeypatch):
    """DQAL-03: < 50 rookies indicates partial ingestion -> CRITICAL."""
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    rookies_dir = tmp_path / "data" / "bronze" / "players" / "rookies" / "season=2025"
    rookies_dir.mkdir(parents=True, exist_ok=True)
    thin_df = pd.DataFrame(
        [{"player_name": f"Rookie {i}", "team": "KC", "position": "WR"} for i in range(23)]
    )
    thin_df.to_parquet(rookies_dir / "rookies_test.parquet", index=False)

    criticals, warnings = sanity._check_dqal_rookie_ingestion(season=2025)

    assert len(criticals) == 1
    crit = criticals[0]
    assert "ROOKIE INGESTION THIN" in crit
    assert "23" in crit
    assert "50" in crit
    assert warnings == []


# --- Test 14: rookie parquet >= 50 -> PASS -------------------------------


def test_dqal_rookie_ingestion_ok_when_above_threshold(tmp_path, monkeypatch):
    """DQAL-03: >= 50 rookies is the healthy path."""
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    rookies_dir = tmp_path / "data" / "bronze" / "players" / "rookies" / "season=2025"
    rookies_dir.mkdir(parents=True, exist_ok=True)
    healthy_df = pd.DataFrame(
        [
            {"player_name": f"Rookie {i}", "team": "KC", "position": "WR"}
            for i in range(75)
        ]
    )
    healthy_df.to_parquet(rookies_dir / "rookies_test.parquet", index=False)

    criticals, warnings = sanity._check_dqal_rookie_ingestion(season=2025)

    assert criticals == []
    assert warnings == []


# --- Test 15: consecutive rank gap > 25 -> CRITICAL ----------------------


def test_dqal_rank_gap_flags_large_gap(tmp_path, monkeypatch):
    """DQAL-03: any consecutive rank gap > 25 indicates missing players."""
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    rankings_dir = tmp_path / "data" / "gold" / "rankings" / "season=2026"
    rankings_dir.mkdir(parents=True, exist_ok=True)
    # Ranks 1..12 then 45..50 — a 33-position gap between 12 and 45.
    ranks = list(range(1, 13)) + list(range(45, 51))
    rank_df = pd.DataFrame(
        [
            {"rank": r, "player_name": f"P{r}", "position": "WR", "team": "KC"}
            for r in ranks
        ]
    )
    rank_df.to_parquet(rankings_dir / "rankings_test.parquet", index=False)

    criticals, warnings = sanity._check_dqal_rank_gap(season=2026)

    assert len(criticals) == 1
    crit = criticals[0]
    assert "RANK GAP" in crit
    assert "12" in crit
    assert "45" in crit
    assert "33" in crit
    assert warnings == []


# --- Test 16: all gaps <= 25 -> PASS -------------------------------------


def test_dqal_rank_gap_passes_when_gaps_small(tmp_path, monkeypatch):
    """Healthy rankings: consecutive ranks 1..50 all <= 25 gap."""
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    rankings_dir = tmp_path / "data" / "gold" / "rankings" / "season=2026"
    rankings_dir.mkdir(parents=True, exist_ok=True)
    rank_df = pd.DataFrame(
        [
            {"rank": r, "player_name": f"P{r}", "position": "WR", "team": "KC"}
            for r in range(1, 51)
        ]
    )
    rank_df.to_parquet(rankings_dir / "rankings_test.parquet", index=False)

    criticals, warnings = sanity._check_dqal_rank_gap(season=2026)

    assert criticals == []
    assert warnings == []
