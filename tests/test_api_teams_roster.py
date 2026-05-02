"""
Tests for the teams API endpoints (/api/teams/*) and team_roster_service.

Covers:
- Defensive roster loading (real NFL names, depth chart positions).
- Offensive OL slots (LT/LG/C/RG/RT assignment).
- Fallback when requested season has no roster parquet (2026 -> latest available).
- Unknown-team validation (ValueError / HTTP 404).
- Current-week helper: in-season schedule match + offseason fallback.
- FastAPI integration for GET /api/teams/current-week and /api/teams/{team}/roster.
"""

import re
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from web.api.main import app  # noqa: E402
from web.api.services import team_roster_service  # noqa: E402


client = TestClient(app)

PLACEHOLDER_PATTERN = re.compile(r"^[A-Z]{2,3} (DE|DT|LB|CB|SS|FS)$")


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------


class TestLoadTeamRoster:
    def test_defense_roster_returns_real_names(self):
        """BUF 2024 defense should have >=11 real NFL players (no placeholder names)."""
        resp = team_roster_service.load_team_roster("BUF", 2024, 1, "defense")
        assert resp.team == "BUF"
        assert resp.side == "defense"
        assert (
            len(resp.roster) >= 11
        ), f"expected >=11 defensive players, got {len(resp.roster)}"
        for p in resp.roster:
            assert not PLACEHOLDER_PATTERN.match(
                p.player_name
            ), f"placeholder-style name leaked: {p.player_name}"
            assert p.depth_chart_position is not None and p.depth_chart_position != ""

    def test_offense_ol_slots_present(self):
        """BUF 2024 offense should include >=5 OL rows in T/G/C group with real names."""
        resp = team_roster_service.load_team_roster("BUF", 2024, 1, "offense")
        ol_rows = [
            p
            for p in resp.roster
            if p.depth_chart_position in {"LT", "LG", "C", "RG", "RT", "T", "G"}
        ]
        assert len(ol_rows) >= 5, f"expected >=5 OL rows, got {len(ol_rows)}"
        for r in ol_rows:
            # player_name must not equal the slot label
            assert r.player_name not in {
                "LT",
                "LG",
                "C",
                "RG",
                "RT",
                "T",
                "G",
            }, f"placeholder OL name leaked: {r.player_name}"
            assert r.player_name != f"BUF-{r.depth_chart_position}"

    def test_fallback_when_season_missing(self):
        """Request for 2026 (absent locally) should fall back to latest available season."""
        resp = team_roster_service.load_team_roster("BUF", 2026, 1, "defense")
        assert resp.fallback is True
        assert resp.fallback_season is not None
        assert resp.fallback_season < 2026
        assert len(resp.roster) >= 1

    def test_unknown_team_raises(self):
        with pytest.raises(ValueError):
            team_roster_service.load_team_roster("ZZZ", 2024, 1, "all")

    def test_ol_slot_hint_assigned_when_data_available(self):
        """At least C should be slot-tagged when OL snap data is present."""
        resp = team_roster_service.load_team_roster("BUF", 2024, 1, "offense")
        slot_hints = {p.slot_hint for p in resp.roster if p.slot_hint}
        # With 2024 week-1 snaps available, we expect QB1 and a C at minimum.
        assert "C" in slot_hints or any(
            h in slot_hints for h in ("LT", "RT", "LG", "RG")
        ), f"expected OL slot_hint among LT/LG/C/RG/RT, got: {slot_hints}"


class TestGetCurrentWeek:
    def test_current_week_in_season(self):
        """A date inside the 2025 schedule window resolves to schedule source."""
        resp = team_roster_service.get_current_week(today=date(2025, 9, 10))
        assert resp.source == "schedule"
        assert resp.season == 2025
        assert resp.week == 1

    def test_current_week_offseason(self):
        """An offseason date with no current schedule should return fallback from latest season."""
        resp = team_roster_service.get_current_week(today=date(2026, 5, 1))
        assert resp.source == "fallback"
        assert resp.season == 2025  # latest available season in data/bronze/schedules/
        assert 1 <= resp.week <= 22


# ---------------------------------------------------------------------------
# FastAPI endpoint integration tests
# ---------------------------------------------------------------------------


class TestTeamsEndpoints:
    def test_endpoint_current_week_returns_200(self):
        resp = client.get("/api/teams/current-week")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"season", "week", "source"}
        assert body["source"] in {"schedule", "fallback"}
        assert 2016 <= body["season"] <= 2030
        assert 1 <= body["week"] <= 22

    def test_endpoint_defense_roster_returns_real_data(self):
        resp = client.get("/api/teams/BUF/roster?season=2024&week=1&side=defense")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["team"] == "BUF"
        assert body["side"] == "defense"
        assert len(body["roster"]) >= 11
        for p in body["roster"]:
            assert p["player_name"]
            assert not PLACEHOLDER_PATTERN.match(p["player_name"])

    def test_endpoint_unknown_team_returns_404(self):
        resp = client.get("/api/teams/ZZZ/roster?season=2024&week=1&side=all")
        assert resp.status_code == 404

    def test_endpoint_invalid_week_returns_422(self):
        resp = client.get("/api/teams/BUF/roster?season=2024&week=99&side=all")
        assert resp.status_code == 422

    def test_endpoint_fallback_flag_set_for_2026(self):
        """2026 roster parquet is absent at execution time; response should carry fallback=true.

        Note: if 2026 parquet is added to the data lake after this test was written,
        this assertion must flip — inspect `data/bronze/players/rosters/season=2026/`.
        """
        resp = client.get("/api/teams/BUF/roster?season=2026&week=1&side=defense")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fallback"] is True
        assert body["fallback_season"] is not None
