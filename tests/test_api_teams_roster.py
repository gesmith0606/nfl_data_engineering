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

    def test_fallback_when_season_missing(self, tmp_path):
        """Request for a season with no roster parquet falls back to latest available.

        Hermetic: points _ROSTERS_ROOT at a temp dir containing only a 2024
        roster file, so the test no longer depends on which seasons exist in
        the real data lake (2026 rosters now exist, which broke the original
        version of this test).
        """
        import shutil

        src_dir = (
            _PROJECT_ROOT / "data" / "bronze" / "players" / "rosters" / "season=2024"
        )
        src_file = sorted(src_dir.glob("rosters_*.parquet"))[-1]
        dst_dir = tmp_path / "season=2024"
        dst_dir.mkdir()
        shutil.copy(src_file, dst_dir / src_file.name)

        with patch.object(team_roster_service, "_ROSTERS_ROOT", tmp_path):
            resp = team_roster_service.load_team_roster("BUF", 2026, 1, "defense")
        assert resp.fallback is True
        assert resp.fallback_season == 2024
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
        """An offseason date with no current schedule should return a fallback.

        Prefers ``source="projections-fallback"`` anchored to the latest
        Gold projections slice. If no projections are bundled, the legacy
        schedule fallback returns ``source="fallback"``.
        """
        resp = team_roster_service.get_current_week(today=date(2026, 5, 1))
        assert resp.source in ("projections-fallback", "fallback")
        assert 2016 <= resp.season <= 2030
        assert 1 <= resp.week <= 22

    def test_offseason_fallback_clamped_to_regular_season(self):
        """The fallback path must clamp to the regular-season ceiling (18).

        Schedule parquets carry postseason weeks 19-22, but the matchups /
        lineups / predictions UIs only render weeks 1-18 in their Week
        dropdowns. Returning week=22 leaves resolvedWeek invisible to the
        user because no dropdown entry matches.
        """
        resp = team_roster_service.get_current_week(today=date(2026, 5, 1))
        assert resp.source in ("projections-fallback", "fallback")
        assert resp.week <= 18, (
            f"fallback week {resp.week} exceeded reg-season ceiling — "
            "the matchups page Week dropdown won't display a value above 18"
        )

    def test_offseason_prefers_projections_fallback(self):
        """When Gold projections are bundled, fallback anchors to that slice.

        Regression for the matchups blanking bug: schedule fallback returned
        ``2025/W18`` even though no projections for that week existed, so the
        UI rendered a blank week. The projections-aware fallback aligns
        ``current-week`` with what's actually renderable.
        """
        from web.api.services import projection_service

        latest = projection_service.get_latest_slice()
        if latest.week is None:
            return  # no projections bundled — legacy fallback path is fine
        resp = team_roster_service.get_current_week(today=date(2026, 5, 1))
        assert resp.source == "projections-fallback"
        assert resp.season == latest.season
        assert resp.week == min(latest.week, 18)


# ---------------------------------------------------------------------------
# FastAPI endpoint integration tests
# ---------------------------------------------------------------------------


class TestTeamsEndpoints:
    def test_endpoint_current_week_returns_200(self):
        resp = client.get("/api/teams/current-week")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"season", "week", "source"}
        assert body["source"] in {"schedule", "projections-fallback", "fallback"}
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

    def test_endpoint_fallback_flag_set_for_missing_season(self, tmp_path):
        """A season with no roster parquet should carry fallback=true in the response.

        Hermetic: patches _ROSTERS_ROOT to a temp dir with only a 2024 file
        (2026 rosters now exist in the real data lake, so the original
        unpatched version of this test no longer exercised the fallback).
        """
        import shutil

        src_dir = (
            _PROJECT_ROOT / "data" / "bronze" / "players" / "rosters" / "season=2024"
        )
        src_file = sorted(src_dir.glob("rosters_*.parquet"))[-1]
        dst_dir = tmp_path / "season=2024"
        dst_dir.mkdir()
        shutil.copy(src_file, dst_dir / src_file.name)

        with patch.object(team_roster_service, "_ROSTERS_ROOT", tmp_path):
            resp = client.get("/api/teams/BUF/roster?season=2026&week=1&side=defense")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fallback"] is True
        assert body["fallback_season"] == 2024
