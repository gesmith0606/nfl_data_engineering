"""Tests for GET /api/league/{league_id}/draft-prep (pre-season view).

Fixtures are recorded once from the live Sleeper API for the MANTIS dynasty
league (league_id=1378522447686402048, user_id=997016529965223936).  The HTTP
layer is fully mocked — these tests NEVER make live network calls.

Test coverage:
    - 200 shape: all four top-level keys present and correctly typed
    - keeper ranking: descending by projected_season_points
    - taxi_eligible: respects league.settings.taxi_years logic
    - draft_info: draft_id / type / rounds / user_slot populated from fixture
    - best_available: top-30 ordered by projected_season_points descending
    - rookies: all have years_exp == 0; sorted by adp_rank (ascending)
    - 404: unknown league raises 404
    - graceful empty when user has no roster (keeper_candidates == [])
    - 400: non-numeric league_id
"""

from __future__ import annotations

import json
import os
from contextlib import ExitStack
from typing import Any, Dict, List
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from web.api.main import app

# ---------------------------------------------------------------------------
# TestClient
# ---------------------------------------------------------------------------

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
LEAGUE_ID = "1378522447686402048"
USER_ID = "997016529965223936"


def _load_fixture(name: str) -> Any:
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


_LEAGUE_FIXTURE: Dict[str, Any] = _load_fixture(f"league_{LEAGUE_ID}.json")
_ROSTERS_FIXTURE: List[Dict[str, Any]] = _load_fixture(f"rosters_{LEAGUE_ID}.json")
_DRAFTS_FIXTURE: List[Dict[str, Any]] = _load_fixture(f"drafts_{LEAGUE_ID}.json")

# ---------------------------------------------------------------------------
# Synthetic player registry
# ---------------------------------------------------------------------------

_PLAYER_REGISTRY: Dict[str, Any] = {
    # User's roster players
    "P001": {"full_name": "Patrick Mahomes", "position": "QB", "team": "KC", "years_exp": 8},
    "P002": {"full_name": "Christian McCaffrey", "position": "RB", "team": "SF", "years_exp": 9},
    "P003": {"full_name": "Justin Jefferson", "position": "WR", "team": "MIN", "years_exp": 5},
    "P004": {"full_name": "Sam LaPorta", "position": "TE", "team": "DET", "years_exp": 2},
    "P005": {"full_name": "Josh Allen", "position": "QB", "team": "BUF", "years_exp": 8},
    "P006": {"full_name": "Breece Hall", "position": "RB", "team": "NYJ", "years_exp": 4},
    # Free agents (not rostered in synthetic league)
    "P010": {"full_name": "Jordan Love", "position": "QB", "team": "GB", "years_exp": 5},
    "P011": {"full_name": "Rachaad White", "position": "RB", "team": "TB", "years_exp": 3},
    "P012": {"full_name": "Keenan Allen", "position": "WR", "team": "CHI", "years_exp": 13},
    "P013": {"full_name": "Hunter Henry", "position": "TE", "team": "NE", "years_exp": 9},
    # Rookies (free agents)
    "P020": {"full_name": "Cam Ward", "position": "QB", "team": "TEN", "years_exp": 0},
    "P021": {"full_name": "Travis Hunter", "position": "WR", "team": "JAX", "years_exp": 0},
    "P022": {"full_name": "Ashton Jeanty", "position": "RB", "team": "LV", "years_exp": 0},
    # 2nd-year player (taxi eligible when taxi_years=2)
    "P030": {"full_name": "Jayden Daniels", "position": "QB", "team": "WSH", "years_exp": 1},
}

# ---------------------------------------------------------------------------
# Synthetic rosters — user USER_ID owns P001-P006
# ---------------------------------------------------------------------------

_SYNTHETIC_ROSTERS: List[Dict[str, Any]] = [
    {
        "roster_id": 1,
        "owner_id": USER_ID,
        "starters": ["P001"],
        "players": ["P001", "P002", "P003", "P004", "P005", "P006"],
    },
    {
        "roster_id": 2,
        "owner_id": "OTHER_OWNER",
        "starters": [],
        "players": [],
    },
]

# ---------------------------------------------------------------------------
# Synthetic projection DataFrame
# ---------------------------------------------------------------------------

_PROJ_ROWS = [
    # User's players
    {"player_name": "Patrick Mahomes", "position": "QB", "team": "KC", "projected_season_points": 380.0},
    {"player_name": "Christian McCaffrey", "position": "RB", "team": "SF", "projected_season_points": 280.0},
    {"player_name": "Justin Jefferson", "position": "WR", "team": "MIN", "projected_season_points": 260.0},
    {"player_name": "Sam LaPorta", "position": "TE", "team": "DET", "projected_season_points": 160.0},
    {"player_name": "Josh Allen", "position": "QB", "team": "BUF", "projected_season_points": 360.0},
    {"player_name": "Breece Hall", "position": "RB", "team": "NYJ", "projected_season_points": 240.0},
    # Free agents
    {"player_name": "Jordan Love", "position": "QB", "team": "GB", "projected_season_points": 320.0},
    {"player_name": "Rachaad White", "position": "RB", "team": "TB", "projected_season_points": 180.0},
    {"player_name": "Keenan Allen", "position": "WR", "team": "CHI", "projected_season_points": 200.0},
    {"player_name": "Hunter Henry", "position": "TE", "team": "NE", "projected_season_points": 120.0},
    # Rookies
    {"player_name": "Cam Ward", "position": "QB", "team": "TEN", "projected_season_points": 250.0},
    {"player_name": "Travis Hunter", "position": "WR", "team": "JAX", "projected_season_points": 150.0},
    {"player_name": "Ashton Jeanty", "position": "RB", "team": "LV", "projected_season_points": 220.0},
    # 2nd-year (taxi eligible)
    {"player_name": "Jayden Daniels", "position": "QB", "team": "WSH", "projected_season_points": 290.0},
]

_PROJ_DF = pd.DataFrame(_PROJ_ROWS)


def _make_proj_df() -> pd.DataFrame:
    return _PROJ_DF.copy()


# ---------------------------------------------------------------------------
# ADP fixture (subset — covers key test players)
# ---------------------------------------------------------------------------

_ADP_FIXTURE: Dict[str, int] = {
    "ashton jeanty": 5,    # rookie, ADP rank 5
    "cam ward": 12,        # rookie QB
    "travis hunter": 18,   # rookie WR
    "jordan love": 7,      # free agent QB
    "keenan allen": 25,
    "rachaad white": 30,
    "jayden daniels": 15,  # 2nd-year
}


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_league_cache() -> Any:
    """Clear the router's in-process TTL cache before and after each test."""
    import web.api.routers.sleeper_user as mod

    mod._CACHE.clear()
    yield
    mod._CACHE.clear()


# ---------------------------------------------------------------------------
# Context manager helpers
# ---------------------------------------------------------------------------


def _patch_all(proj_df: pd.DataFrame = None, adp: Dict[str, int] = None):  # type: ignore[assignment]
    """Return a tuple of context managers patching all external I/O."""
    if proj_df is None:
        proj_df = _make_proj_df()
    if adp is None:
        adp = dict(_ADP_FIXTURE)
    return (
        patch("web.api.routers.sleeper_user.get_league", return_value=dict(_LEAGUE_FIXTURE)),
        patch("web.api.routers.sleeper_user.get_league_rosters", return_value=list(_SYNTHETIC_ROSTERS)),
        patch("web.api.routers.sleeper_user.load_sleeper_players", return_value=dict(_PLAYER_REGISTRY)),
        patch("web.api.routers.sleeper_user._load_projections", return_value=proj_df),
        patch("web.api.routers.sleeper_user.get_drafts_for_league", return_value=list(_DRAFTS_FIXTURE)),
        patch("web.api.routers.sleeper_user._load_adp", return_value=adp),
    )


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------


class TestLeagueDraftPrepShape:
    """GET /api/league/{league_id}/draft-prep — response shape."""

    def test_200_returns_expected_keys(self):
        """Response must carry all four top-level sections."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["league_id"] == LEAGUE_ID
        assert data["user_id"] == USER_ID
        assert "draft_info" in data
        assert "keeper_candidates" in data
        assert "best_available" in data
        assert "rookies" in data
        assert "rookie_note" in data

    def test_draft_info_populated(self):
        """draft_info fields come from the drafts fixture."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        di = data["draft_info"]
        assert di is not None
        assert di["draft_id"] == "1378522447694794752"
        assert di["status"] == "pre_draft"
        assert di["type"] == "snake"
        assert di["rounds"] == 3

    def test_draft_info_user_slot_from_draft_order(self):
        """user_slot is read from draft_order when set."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        # fixture draft_order has USER_ID → 5
        assert data["draft_info"]["user_slot"] == 5


# ---------------------------------------------------------------------------
# Tests: keeper_candidates ordering
# ---------------------------------------------------------------------------


class TestKeeperCandidates:
    """keeper_candidates must be sorted descending by projected_season_points."""

    def test_keeper_ranking_descending(self):
        """Keeper candidates must be ordered highest → lowest projected points."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        keepers = data["keeper_candidates"]
        assert len(keepers) > 0
        pts = [k["projected_season_points"] for k in keepers if k["projected_season_points"] is not None]
        assert pts == sorted(pts, reverse=True), "Keepers must be sorted descending by projected_season_points"

    def test_keeper_taxi_eligible_respects_taxi_years(self):
        """Players with years_exp <= taxi_years-1 must be taxi_eligible.

        The MANTIS fixture has taxi_years=2, so years_exp <= 1 → taxi_eligible.
        P004 (Sam LaPorta, years_exp=2) is NOT eligible.
        """
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        keepers = {k["player_name"]: k for k in data["keeper_candidates"]}
        # Patrick Mahomes years_exp=8 — NOT taxi eligible
        if "Patrick Mahomes" in keepers:
            assert keepers["Patrick Mahomes"]["taxi_eligible"] is False
        # Sam LaPorta years_exp=2 — NOT taxi eligible (taxi_threshold=1)
        if "Sam LaPorta" in keepers:
            assert keepers["Sam LaPorta"]["taxi_eligible"] is False

    def test_keeper_empty_when_user_has_no_roster(self):
        """When the user has no roster, keeper_candidates is empty."""
        empty_rosters = [{"roster_id": 1, "owner_id": USER_ID, "starters": [], "players": []}]
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            stack.enter_context(
                patch("web.api.routers.sleeper_user.get_league_rosters", return_value=empty_rosters)
            )
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        assert data["keeper_candidates"] == []


# ---------------------------------------------------------------------------
# Tests: best_available
# ---------------------------------------------------------------------------


class TestBestAvailable:
    """best_available must exclude rostered players and carry ADP annotation."""

    def test_best_available_non_empty(self):
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        assert len(data["best_available"]) > 0

    def test_best_available_sorted_by_projected_points(self):
        """best_available must be ordered highest → lowest projected points."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        pts = [p["projected_season_points"] for p in data["best_available"] if p["projected_season_points"] is not None]
        assert pts == sorted(pts, reverse=True)

    def test_rostered_players_excluded_from_best_available(self):
        """Players rostered by ANY team in the league must not appear in best_available."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        ba_names = {p["player_name"] for p in data["best_available"]}
        # User's rostered players must not appear
        rostered_names = {"Patrick Mahomes", "Christian McCaffrey", "Justin Jefferson",
                          "Sam LaPorta", "Josh Allen", "Breece Hall"}
        assert ba_names.isdisjoint(rostered_names), (
            f"Rostered players found in best_available: {ba_names & rostered_names}"
        )

    def test_best_available_adp_rank_and_value_populated(self):
        """Players with an ADP entry must have adp_rank and value set."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        # Jordan Love is in our ADP fixture (rank 7)
        jl = next((p for p in data["best_available"] if p["player_name"] == "Jordan Love"), None)
        if jl is not None:
            assert jl["adp_rank"] == 7
            # value = adp_rank - projection_rank; projection_rank is 1 (highest free-agent pts=320)
            assert jl["value"] is not None

    def test_best_available_max_30_entries(self):
        """best_available is capped at 30 entries."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        assert len(data["best_available"]) <= 30


# ---------------------------------------------------------------------------
# Tests: rookies
# ---------------------------------------------------------------------------


class TestRookies:
    """rookies must be a subset of best_available with years_exp==0."""

    def test_all_rookies_have_years_exp_zero(self):
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        for r in data["rookies"]:
            assert r["years_exp"] == 0, f"Non-rookie in rookies list: {r['player_name']} years_exp={r['years_exp']}"

    def test_rookies_sorted_by_adp_rank_ascending(self):
        """Rookies with an ADP entry must appear before those without, and in ascending order."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        rookies = data["rookies"]
        # Rookies with ADP must come before those without, and must be ascending within each group
        with_adp = [r for r in rookies if r["adp_rank"] is not None]
        without_adp = [r for r in rookies if r["adp_rank"] is None]
        # All with-ADP appear before without-ADP (index of last with_adp < index of first without_adp)
        if with_adp and without_adp:
            last_with = rookies.index(with_adp[-1])
            first_without = rookies.index(without_adp[0])
            assert last_with < first_without, "Rookies with ADP must precede rookies without ADP"
        # Within with-ADP group, ranks must be ascending
        adp_ranks = [r["adp_rank"] for r in with_adp]
        assert adp_ranks == sorted(adp_ranks), f"Rookie ADP ranks not ascending: {adp_ranks}"

    def test_rookies_are_subset_of_best_available(self):
        """Every rookie name must also appear in best_available."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        ba_names = {p["player_name"] for p in data["best_available"]}
        for r in data["rookies"]:
            assert r["player_name"] in ba_names, f"Rookie {r['player_name']} missing from best_available"

    def test_rookie_note_is_non_empty_string(self):
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        assert isinstance(data["rookie_note"], str) and len(data["rookie_note"]) > 0


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


class TestDraftPrepErrors:
    """Error and edge-case handling."""

    def test_404_unknown_league(self):
        """Unknown league must return 404."""
        with patch("web.api.routers.sleeper_user.get_league", return_value=None):
            resp = client.get(f"/api/league/9999999999999999999/draft-prep")
        assert resp.status_code == 404

    def test_400_non_numeric_league_id(self):
        """Non-numeric league_id must return 400."""
        resp = client.get("/api/league/not-a-number/draft-prep")
        assert resp.status_code == 400
        assert "numeric" in resp.json()["detail"].lower()

    def test_no_user_id_returns_empty_keepers(self):
        """Omitting user_id must return 200 with empty keeper_candidates."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            resp = client.get(f"/api/league/{LEAGUE_ID}/draft-prep")
        assert resp.status_code == 200
        data = resp.json()
        assert data["keeper_candidates"] == []

    def test_no_drafts_returns_null_draft_info(self):
        """When Sleeper returns no drafts, draft_info must be None."""
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            stack.enter_context(
                patch("web.api.routers.sleeper_user.get_drafts_for_league", return_value=[])
            )
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        data = resp.json()
        assert data["draft_info"] is None

    def test_projections_unavailable_still_returns_200(self):
        """When no projections are available, endpoint must still return 200 with empty lists."""
        with ExitStack() as stack:
            for cm in _patch_all(proj_df=pd.DataFrame()):
                stack.enter_context(cm)
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/draft-prep",
                params={"user_id": USER_ID},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["keeper_candidates"] == []
        assert data["best_available"] == []
        assert data["rookies"] == []
