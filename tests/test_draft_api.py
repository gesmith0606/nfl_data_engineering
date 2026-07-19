"""
Tests for the Draft API endpoints (/api/draft/*).

Uses mock projection data to avoid network dependencies on nfl-data-py.
"""

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from web.api.main import app

# Captured at import time, before the autouse fixture patches the module
# attribute — lets the strategy-order tests exercise the real logic.
from web.api.routers.draft import _load_draft_data as _real_load_draft_data

# Ensure src/ is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

client = TestClient(app)


# ---------------------------------------------------------------------------
# Synthetic data for mocking
# ---------------------------------------------------------------------------


def _make_mock_projections() -> pd.DataFrame:
    """Create a small synthetic projection DataFrame."""
    players = [
        ("P001", "Patrick Mahomes", "QB", "KC", 380.0),
        ("P002", "Josh Allen", "QB", "BUF", 370.0),
        ("P003", "Jalen Hurts", "QB", "PHI", 350.0),
        ("P004", "Christian McCaffrey", "RB", "SF", 320.0),
        ("P005", "Breece Hall", "RB", "NYJ", 280.0),
        ("P006", "Bijan Robinson", "RB", "ATL", 275.0),
        ("P007", "Jahmyr Gibbs", "RB", "DET", 260.0),
        ("P008", "Ja'Marr Chase", "WR", "CIN", 300.0),
        ("P009", "Tyreek Hill", "WR", "MIA", 290.0),
        ("P010", "CeeDee Lamb", "WR", "DAL", 285.0),
        ("P011", "Amon-Ra St. Brown", "WR", "DET", 270.0),
        ("P012", "Travis Kelce", "TE", "KC", 250.0),
        ("P013", "Sam LaPorta", "TE", "DET", 200.0),
        ("P014", "Saquon Barkley", "RB", "PHI", 270.0),
        ("P015", "Davante Adams", "WR", "NYJ", 260.0),
        ("P016", "Lamar Jackson", "QB", "BAL", 360.0),
        ("P017", "Jonathan Taylor", "RB", "IND", 265.0),
        ("P018", "A.J. Brown", "WR", "PHI", 275.0),
        ("P019", "George Kittle", "TE", "SF", 195.0),
        ("P020", "Kyren Williams", "RB", "LAR", 255.0),
    ]
    df = pd.DataFrame(
        players,
        columns=[
            "player_id",
            "player_name",
            "position",
            "recent_team",
            "projected_season_points",
        ],
    )
    return df


def _mock_load_draft_data(
    scoring: str, season: int, adp_source: Optional[str] = None
) -> pd.DataFrame:
    """Mock replacement for _load_draft_data that returns synthetic data."""
    from draft_optimizer import compute_value_scores

    return compute_value_scores(_make_mock_projections())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_load_draft_data():
    """Patch _load_draft_data to avoid network calls."""
    with patch(
        "web.api.routers.draft._load_draft_data", side_effect=_mock_load_draft_data
    ):
        yield


@pytest.fixture(scope="function")
def draft_session(_patch_load_draft_data):
    """Create a draft session. Returns the full JSON response."""
    # Clear sessions between tests
    from web.api.routers import draft as draft_module

    draft_module._sessions.clear()

    resp = client.get(
        "/api/draft/board",
        params={
            "scoring": "half_ppr",
            "roster_format": "standard",
            "n_teams": 12,
            "season": 2026,
        },
    )
    assert resp.status_code == 200, f"Board creation failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test: GET /api/draft/board
# ---------------------------------------------------------------------------


class TestDraftBoard:
    """Tests for the draft board endpoint."""

    def test_creates_session(self, draft_session):
        """GET /api/draft/board creates a new session with players."""
        assert draft_session["session_id"]
        assert isinstance(draft_session["players"], list)
        assert len(draft_session["players"]) > 0
        assert draft_session["my_roster"] == []
        assert draft_session["picks_taken"] == 0
        assert draft_session["scoring_format"] == "half_ppr"
        assert draft_session["roster_format"] == "standard"
        assert draft_session["n_teams"] == 12

    def test_player_fields(self, draft_session):
        """Each player has the expected schema fields."""
        player = draft_session["players"][0]
        assert "player_id" in player
        assert "player_name" in player
        assert "position" in player
        assert "projected_points" in player
        assert "model_rank" in player
        assert "vorp" in player
        assert "value_tier" in player

    def test_reuse_session(self, draft_session):
        """GET /api/draft/board with existing session_id returns same state."""
        sid = draft_session["session_id"]
        resp = client.get("/api/draft/board", params={"session_id": sid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert len(data["players"]) == len(draft_session["players"])


# ---------------------------------------------------------------------------
# Test: POST /api/draft/pick
# ---------------------------------------------------------------------------


class TestDraftPick:
    """Tests for the draft pick endpoint."""

    def test_pick_valid_player(self, draft_session):
        """POST /api/draft/pick with valid player_id records the pick."""
        sid = draft_session["session_id"]
        player_id = draft_session["players"][0]["player_id"]

        resp = client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": player_id, "by_me": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["player"]["player_id"] == player_id
        assert "Drafted" in data["message"]

    def test_pick_updates_board(self, draft_session):
        """After a pick, the board reflects the change."""
        sid = draft_session["session_id"]
        player_id = draft_session["players"][0]["player_id"]
        original_count = len(draft_session["players"])

        client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": player_id, "by_me": True},
        )

        resp = client.get("/api/draft/board", params={"session_id": sid})
        data = resp.json()
        assert len(data["players"]) == original_count - 1
        assert data["my_pick_count"] == 1
        assert data["picks_taken"] == 1
        assert len(data["my_roster"]) == 1

    def test_pick_invalid_session(self):
        """POST /api/draft/pick with fake session_id returns 404."""
        resp = client.post(
            "/api/draft/pick",
            json={
                "session_id": "nonexistent_session_id",
                "player_id": "X",
                "by_me": True,
            },
        )
        assert resp.status_code == 404

    def test_pick_invalid_player(self, draft_session):
        """POST /api/draft/pick with bad player_id returns 400."""
        sid = draft_session["session_id"]
        resp = client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": "ZZZZZ_NOT_REAL", "by_me": True},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: GET /api/draft/recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    """Tests for the recommendations endpoint."""

    def test_recommendations(self, draft_session):
        """GET /api/draft/recommendations returns non-empty list."""
        sid = draft_session["session_id"]
        resp = client.get(
            "/api/draft/recommendations", params={"session_id": sid, "top_n": 5}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) > 0
        assert isinstance(data["reasoning"], str)
        assert isinstance(data["remaining_needs"], dict)

    def test_recommendations_with_position(self, draft_session):
        """GET /api/draft/recommendations with position filter works."""
        sid = draft_session["session_id"]
        resp = client.get(
            "/api/draft/recommendations",
            params={"session_id": sid, "top_n": 3, "position": "QB"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for rec in data["recommendations"]:
            assert rec["position"] == "QB"

    def test_recommendations_invalid_session(self):
        """GET /api/draft/recommendations with bad session returns 404."""
        resp = client.get(
            "/api/draft/recommendations",
            params={"session_id": "bad_session", "top_n": 5},
        )
        assert resp.status_code == 404

    def test_recommendation_fields(self, draft_session):
        """Recommendations include all expected fields."""
        sid = draft_session["session_id"]
        resp = client.get(
            "/api/draft/recommendations", params={"session_id": sid, "top_n": 1}
        )
        rec = resp.json()["recommendations"][0]
        assert "player_id" in rec
        assert "player_name" in rec
        assert "position" in rec
        assert "projected_points" in rec
        assert "model_rank" in rec
        assert "vorp" in rec
        assert "recommendation_score" in rec


# ---------------------------------------------------------------------------
# Test: POST /api/draft/mock/start & POST /api/draft/mock/pick
# ---------------------------------------------------------------------------


class TestMockDraft:
    """Tests for mock draft start and pick advancement."""

    def test_mock_start(self):
        """POST /api/draft/mock/start returns a session_id."""
        resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 1, "season": 2026},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "message" in data
        assert "12 teams" in data["message"]

    def test_mock_start_invalid_pick(self):
        """POST /api/draft/mock/start with user_pick > n_teams returns 400."""
        resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 15},
        )
        assert resp.status_code == 400

    def test_mock_pick_advances(self):
        """POST /api/draft/mock/pick advances the pick number."""
        start_resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 1, "season": 2026},
        )
        sid = start_resp.json()["session_id"]

        resp = client.post("/api/draft/mock/pick", json={"session_id": sid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["pick_number"] >= 1
        assert data["round_number"] >= 1
        assert data["player_name"] is not None

    def test_mock_pick_multiple(self):
        """Multiple mock picks advance sequentially."""
        start_resp = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 4, "user_pick": 1, "season": 2026},
        )
        sid = start_resp.json()["session_id"]

        pick_numbers = []
        for _ in range(4):
            resp = client.post("/api/draft/mock/pick", json={"session_id": sid})
            assert resp.status_code == 200
            pick_numbers.append(resp.json()["pick_number"])

        assert pick_numbers == [1, 2, 3, 4]

    def test_mock_pick_invalid_session(self):
        """POST /api/draft/mock/pick with bad session returns 404."""
        resp = client.post(
            "/api/draft/mock/pick", json={"session_id": "no_such_session"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: GET /api/draft/adp
# ---------------------------------------------------------------------------


class TestAdp:
    """Tests for the ADP endpoint."""

    def test_adp_response(self):
        """GET /api/draft/adp returns 200 or 404 depending on file existence."""
        resp = client.get("/api/draft/adp")
        # No ADP file in test env -- expect 404
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data["players"], list)
            assert data["source"] == "adp_latest.csv"

    def test_source_param_reads_per_source_file(self, tmp_path):
        """source=ffc reads data/adp/adp_ffc_half_ppr.csv, not adp_latest.csv."""
        from web.api.routers import draft as draft_module

        adp_dir = tmp_path / "data" / "adp"
        adp_dir.mkdir(parents=True)
        (adp_dir / "adp_ffc_half_ppr.csv").write_text(
            "adp_rank,player_name,position,team,adp,stdev,source,scoring_format\n"
            "1,Bijan Robinson,RB,ATL,1.5,0.4,ffc,half_ppr\n"
        )
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            resp = client.get(
                "/api/draft/adp", params={"source": "ffc", "scoring": "half_ppr"}
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["source"] == "adp_ffc_half_ppr.csv"
        assert data["players"][0]["player_name"] == "Bijan Robinson"
        assert data["players"][0]["stdev"] == pytest.approx(0.4)

    def test_source_param_falls_back_to_adp_latest_when_missing(self, tmp_path):
        """A requested source file that doesn't exist falls back to adp_latest.csv."""
        from web.api.routers import draft as draft_module

        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "adp_latest.csv").write_text(
            "adp_rank,player_name,position,team\n1,Fallback Guy,WR,KC\n"
        )
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            resp = client.get("/api/draft/adp", params={"source": "espn"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["source"] == "adp_latest.csv"
        assert data["players"][0]["player_name"] == "Fallback Guy"

    def test_no_file_anywhere_returns_404(self, tmp_path):
        from web.api.routers import draft as draft_module

        (tmp_path / "data").mkdir(parents=True)
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            resp = client.get("/api/draft/adp", params={"source": "ffc"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: GET /api/draft/platforms
# ---------------------------------------------------------------------------


class TestPlatformPresets:
    """Tests for GET /api/draft/platforms."""

    def test_returns_all_platform_keys(self):
        resp = client.get("/api/draft/platforms")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["platforms"].keys()) == {"espn", "sleeper", "yahoo", "custom"}

    def test_espn_preset_fields_and_roster_slots(self):
        resp = client.get("/api/draft/platforms")
        espn = resp.json()["platforms"]["espn"]
        assert espn["scoring_format"] == "half_ppr"
        assert espn["roster_format"] == "espn_default"
        assert espn["rounds"] == 16
        assert espn["timer_seconds"] == 30
        assert espn["adp_source"] == "espn"
        assert espn["roster_slots"]["QB"] == 1
        assert espn["roster_slots"]["FLEX"] == 1
        assert sum(espn["roster_slots"].values()) > 0

    def test_sleeper_preset_uses_sleeper_adp_source(self):
        """Sleeper rooms draft against Sleeper's own crowd ADP."""
        resp = client.get("/api/draft/platforms")
        sleeper = resp.json()["platforms"]["sleeper"]
        assert sleeper["adp_source"] == "sleeper"
        assert sleeper["roster_format"] == "sleeper_default"
        assert sleeper["rounds"] == 15
        assert sleeper["timer_seconds"] == 60

    def test_yahoo_preset(self):
        resp = client.get("/api/draft/platforms")
        yahoo = resp.json()["platforms"]["yahoo"]
        assert yahoo["scoring_format"] == "half_ppr"
        assert yahoo["roster_format"] == "yahoo_default"
        assert yahoo["adp_source"] == "ffc"

    def test_custom_preset_is_all_none(self):
        resp = client.get("/api/draft/platforms")
        custom = resp.json()["platforms"]["custom"]
        assert custom["scoring_format"] is None
        assert custom["roster_format"] is None
        assert custom["rounds"] is None
        assert custom["timer_seconds"] is None
        assert custom["adp_source"] is None
        assert custom["roster_slots"] == {}


# ---------------------------------------------------------------------------
# Test: GET /api/draft/board?platform=... defaults scoring/roster_format
# ---------------------------------------------------------------------------


class TestBoardPlatformDefaulting:
    def test_platform_defaults_scoring_and_roster_format(self, _patch_load_draft_data):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        resp = client.get("/api/draft/board", params={"platform": "espn"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scoring_format"] == "half_ppr"
        assert data["roster_format"] == "espn_default"

    def test_explicit_scoring_overrides_platform_preset(self, _patch_load_draft_data):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        resp = client.get(
            "/api/draft/board",
            # sleeper preset defaults to ppr; explicit standard should win.
            params={"platform": "sleeper", "scoring": "standard"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scoring_format"] == "standard"
        assert data["roster_format"] == "sleeper_default"

    def test_no_platform_keeps_legacy_defaults(self, _patch_load_draft_data):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        resp = client.get("/api/draft/board")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scoring_format"] == "half_ppr"
        assert data["roster_format"] == "standard"


# ---------------------------------------------------------------------------
# Test: _load_adp_df source resolution (per-source file / glob / fallback)
# ---------------------------------------------------------------------------


class TestLoadAdpDfSourceResolution:
    """_load_adp_df(source, scoring) file-resolution order."""

    def test_exact_source_scoring_file(self, tmp_path):
        from web.api.routers import draft as draft_module

        adp_dir = tmp_path / "data" / "adp"
        adp_dir.mkdir(parents=True)
        (adp_dir / "adp_ffc_half_ppr.csv").write_text("player_name\nFoo\n")
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            df = draft_module._load_adp_df("ffc", "half_ppr")
        assert df is not None
        assert df.iloc[0]["player_name"] == "Foo"

    def test_glob_fallback_when_exact_scoring_missing(self, tmp_path):
        """The source exists but not for this scoring format -- glob any adp_{source}_*.csv."""
        from web.api.routers import draft as draft_module

        adp_dir = tmp_path / "data" / "adp"
        adp_dir.mkdir(parents=True)
        (adp_dir / "adp_ffc_ppr.csv").write_text("player_name\nBar\n")
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            df = draft_module._load_adp_df("ffc", "standard")
        assert df is not None
        assert df.iloc[0]["player_name"] == "Bar"

    def test_falls_back_to_adp_latest_when_source_missing_entirely(self, tmp_path):
        from web.api.routers import draft as draft_module

        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "adp_latest.csv").write_text("player_name\nLegacy\n")
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            df = draft_module._load_adp_df("espn", "half_ppr")
        assert df is not None
        assert df.iloc[0]["player_name"] == "Legacy"

    def test_none_source_uses_adp_latest_directly(self, tmp_path):
        from web.api.routers import draft as draft_module

        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "adp_latest.csv").write_text("player_name\nConsensus\n")
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            df = draft_module._load_adp_df(None, "half_ppr")
        assert df is not None
        assert df.iloc[0]["player_name"] == "Consensus"

    def test_never_raises_when_nothing_exists(self, tmp_path):
        from web.api.routers import draft as draft_module

        (tmp_path / "data").mkdir(parents=True)
        with patch.object(draft_module, "_PROJECT_ROOT", tmp_path):
            df = draft_module._load_adp_df("ffc", "half_ppr")
        assert df is None


# ---------------------------------------------------------------------------
# Test: adp_source threading -- platform default + explicit override
# ---------------------------------------------------------------------------


class TestAdpSourceThreading:
    """adp_source flows from the platform preset (or an explicit param) into
    _load_draft_data, and is echoed back on the board response."""

    def test_board_platform_defaults_adp_source(self, _patch_load_draft_data):
        from draft_optimizer import compute_value_scores
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        captured = {}

        def _capture(scoring, season, adp_source=None):
            captured["adp_source"] = adp_source
            return compute_value_scores(_make_mock_projections())

        with patch.object(draft_module, "_load_draft_data", side_effect=_capture):
            resp = client.get("/api/draft/board", params={"platform": "espn"})
        assert resp.status_code == 200, resp.text
        assert captured["adp_source"] == "espn"
        assert resp.json()["adp_source"] == "espn"

    def test_board_sleeper_platform_defaults_to_sleeper_adp(self, _patch_load_draft_data):
        from draft_optimizer import compute_value_scores
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        captured = {}

        def _capture(scoring, season, adp_source=None):
            captured["adp_source"] = adp_source
            return compute_value_scores(_make_mock_projections())

        with patch.object(draft_module, "_load_draft_data", side_effect=_capture):
            resp = client.get("/api/draft/board", params={"platform": "sleeper"})
        assert resp.status_code == 200, resp.text
        assert captured["adp_source"] == "sleeper"
        assert resp.json()["adp_source"] == "sleeper"

    def test_board_explicit_adp_source_overrides_platform_preset(
        self, _patch_load_draft_data
    ):
        from draft_optimizer import compute_value_scores
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        captured = {}

        def _capture(scoring, season, adp_source=None):
            captured["adp_source"] = adp_source
            return compute_value_scores(_make_mock_projections())

        with patch.object(draft_module, "_load_draft_data", side_effect=_capture):
            resp = client.get(
                "/api/draft/board",
                # espn preset defaults adp_source=espn; explicit ffc should win.
                params={"platform": "espn", "adp_source": "ffc"},
            )
        assert resp.status_code == 200, resp.text
        assert captured["adp_source"] == "ffc"
        assert resp.json()["adp_source"] == "ffc"

    def test_board_no_platform_no_adp_source_is_none(self, _patch_load_draft_data):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        resp = client.get("/api/draft/board")
        assert resp.status_code == 200, resp.text
        assert resp.json()["adp_source"] is None

    def test_mock_start_platform_defaults_adp_source(self, _patch_load_draft_data):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        resp = client.post(
            "/api/draft/mock/start",
            json={"platform": "sleeper", "user_pick": 3, "n_teams": 10},
        )
        assert resp.status_code == 200, resp.text
        sid = resp.json()["session_id"]

        board_resp = client.get("/api/draft/board", params={"session_id": sid})
        assert board_resp.status_code == 200, board_resp.text
        assert board_resp.json()["adp_source"] == "sleeper"

    def test_mock_start_explicit_adp_source_overrides_platform(
        self, _patch_load_draft_data
    ):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        resp = client.post(
            "/api/draft/mock/start",
            json={
                "platform": "sleeper",
                "adp_source": "espn",
                "user_pick": 3,
                "n_teams": 10,
            },
        )
        assert resp.status_code == 200, resp.text
        sid = resp.json()["session_id"]

        board_resp = client.get("/api/draft/board", params={"session_id": sid})
        assert board_resp.json()["adp_source"] == "espn"


# ---------------------------------------------------------------------------
# Test: DST NaN-safety on the live board endpoint
# ---------------------------------------------------------------------------


class TestDstNanSafetyOnBoard:
    """A DST row with no projection (ADP-only) must appear on the board and
    never crash JSON serialization -- projected_points/vorp come back null."""

    def test_dst_without_projection_appears_with_null_points_and_vorp(self):
        from draft_optimizer import compute_value_scores
        from web.api.routers import draft as draft_module

        proj = _make_mock_projections()
        dst_row = pd.DataFrame(
            [
                {
                    "player_id": "DST1",
                    "player_name": "San Francisco",
                    "position": "DST",
                    "recent_team": "SF",
                    "projected_season_points": np.nan,
                }
            ]
        )
        proj_with_dst = pd.concat([proj, dst_row], ignore_index=True)

        def _mock_with_dst(scoring, season, adp_source=None):
            return compute_value_scores(proj_with_dst)

        draft_module._sessions.clear()
        with patch.object(draft_module, "_load_draft_data", side_effect=_mock_with_dst):
            resp = client.get("/api/draft/board")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        dst_players = [p for p in data["players"] if p["position"] == "DST"]
        assert len(dst_players) == 1
        assert dst_players[0]["projected_points"] is None
        assert dst_players[0]["vorp"] is None
        assert dst_players[0]["player_name"] == "San Francisco"

        # Advisor recommendations must not crash either, even filtered to DST.
        sid = data["session_id"]
        recs_resp = client.get(
            "/api/draft/recommendations",
            params={"session_id": sid, "top_n": 5, "position": "DST"},
        )
        assert recs_resp.status_code == 200, recs_resp.text
        recs = recs_resp.json()["recommendations"]
        assert len(recs) == 1
        assert recs[0]["projected_points"] is None
        assert recs[0]["vorp"] is None


# ---------------------------------------------------------------------------
# Test: _load_draft_data strategy order (cache-first)
# ---------------------------------------------------------------------------


class TestLoadDraftDataStrategyOrder:
    """The Gold cached artifact must be preferred over live regeneration.

    Live regeneration produces abbreviated player names (e.g. ``J.Allen``)
    from nfl-data-py seasonal data, which silently breaks the ADP name merge
    and skips the consensus anchor. See 2026-07-12 live-draft verification.
    """

    def test_cached_projections_preferred_over_live_fetch(self):
        """When a cached artifact exists, no live fetch is attempted."""
        from web.api.routers import draft as draft_module

        cached = _make_mock_projections()
        with patch.object(
            draft_module, "_load_cached_projections", return_value=cached
        ) as mock_cache, patch.object(draft_module, "NFLDataFetcher") as mock_fetcher:
            result = _real_load_draft_data("half_ppr", 2026)

        mock_cache.assert_called_once()
        mock_fetcher.assert_not_called()
        assert len(result) == len(cached)
        assert "vorp" in result.columns

    def test_live_fetch_used_when_no_cache(self):
        """When no cached artifact exists, fall back to live generation."""
        from web.api.routers import draft as draft_module

        live = _make_mock_projections()
        with patch.object(
            draft_module, "_load_cached_projections", return_value=None
        ), patch.object(draft_module, "NFLDataFetcher") as mock_fetcher, patch.object(
            draft_module, "generate_preseason_projections", return_value=live
        ):
            mock_fetcher.return_value.fetch_player_seasonal.return_value = live
            result = _real_load_draft_data("half_ppr", 2026)

        mock_fetcher.assert_called_once()
        assert len(result) == len(live)
        assert "vorp" in result.columns


# ---------------------------------------------------------------------------
# Test: GET /api/draft/live  (live Sleeper draft sync — our engine drives recs)
# ---------------------------------------------------------------------------

from src.draft_models import DraftState, PickEvent  # noqa: E402


def _fake_live_state(picks=()):
    """Build a minimal DraftState mimicking a live Sleeper draft."""
    return DraftState(
        draft_id="123456789",
        status="drafting",
        draft_type="snake",
        season="2026",
        n_teams=10,
        rounds=15,
        scoring_format="half_ppr",
        roster_format="standard",
        draft_order={},
        slot_to_roster_id={},
        picks=tuple(picks),
    )


class TestLiveDraftSync:
    """The /live endpoint reads live picks and returns OUR recommendations."""

    def test_requires_draft_id_or_username(self):
        resp = client.get("/api/draft/live", params={"season": 2026})
        assert resp.status_code == 400

    def test_live_sync_returns_our_recommendations(self):
        """Given a live draft with 2 picks, our engine recommends the next pick."""
        from web.api.routers import draft as draft_module

        p1 = PickEvent(
            1, 1, 1, 1, "u1", "4034", "Bijan", "Robinson", "RB", "ATL", False
        )
        p2 = PickEvent(2, 1, 2, 2, "u2", "9999", "Jahmyr", "Gibbs", "RB", "DET", False)
        state = _fake_live_state([p1, p2])

        with patch.object(
            draft_module,
            "_load_cached_projections",
            return_value=_make_mock_projections(),
        ), patch.object(draft_module, "load_draft_state", return_value=state):
            resp = client.get(
                "/api/draft/live",
                params={"draft_id": "123456789", "my_slot": 5, "season": 2026},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["draft_id"] == "123456789"
        assert data["status"] == "drafting"
        assert data["picks_made"] == 2
        assert data["my_slot"] == 5
        # Our engine returns real, roster-aware recommendations.
        assert len(data["recommendations"]) > 0
        top = data["recommendations"][0]
        assert top["player_name"]
        assert "fills_need" in top
        assert isinstance(data["remaining_needs"], dict)
        # Premium context: ADP steal gap, key-moments ticker, next pick number.
        assert "adp_rank" in top and "adp_diff" in top
        assert isinstance(data["key_moments"], list)
        for moment in data["key_moments"]:
            assert {"kind", "pick_no", "player", "detail"} <= set(moment)
        # Slot 5 in a 10-team snake with 2 picks made → next pick is #5.
        assert data["my_next_pick_no"] == 5


# ---------------------------------------------------------------------------
# Test: GET /api/draft/live?platform=yahoo  (server-side OAuth auto-sync)
# ---------------------------------------------------------------------------


class _FakeOAuthDisconnected:
    def has_credentials(self):
        return False

    def get_access_token(self):
        return None


class _FakeOAuthConnected:
    def has_credentials(self):
        return True

    def get_access_token(self):
        return "tok"


class TestLiveDraftYahoo:
    """Yahoo auto-sync on the web: OAuth-gated, mirror mode as fallback."""

    def test_yahoo_503_when_not_connected(self):
        """Without a server-side OAuth grant, Yahoo returns 503 with guidance."""
        from web.api.routers import draft as draft_module

        with patch.object(draft_module, "YahooOAuth", _FakeOAuthDisconnected):
            resp = client.get(
                "/api/draft/live",
                params={"draft_id": "nfl.l.12345", "platform": "yahoo"},
            )
        assert resp.status_code == 503
        assert "mirror mode" in resp.json()["detail"].lower()

    def test_yahoo_503_when_credentials_but_refresh_fails(self):
        """Creds present but no usable token (failed refresh) also gates 503."""
        from web.api.routers import draft as draft_module

        class _FakeOAuthCredsNoToken:
            def has_credentials(self):
                return True

            def get_access_token(self):
                return None

        with patch.object(draft_module, "YahooOAuth", _FakeOAuthCredsNoToken):
            resp = client.get(
                "/api/draft/live",
                params={"draft_id": "nfl.l.12345", "platform": "yahoo"},
            )
        assert resp.status_code == 503
        assert "mirror mode" in resp.json()["detail"].lower()

    def test_yahoo_live_sync_returns_recommendations(self):
        """With a granted token, Yahoo drafts flow through the same engine."""
        from web.api.routers import draft as draft_module
        from src.yahoo_adapter import YahooAdapter as RealYahooAdapter

        p1 = PickEvent(1, 1, 1, 1, "u1", "y1", "Bijan", "Robinson", "RB", "ATL", False)
        p2 = PickEvent(2, 1, 2, 2, "u2", "y2", "Jahmyr", "Gibbs", "RB", "DET", False)
        state = _fake_live_state([p1, p2])

        class _FakeYahooAdapter(RealYahooAdapter):
            # The endpoint passes its shared oauth instance (token-rotation
            # safety) — accept and forward it like the real adapter.
            def __init__(self, oauth=None):
                super().__init__(oauth=oauth)

            def load_state(self, draft_id):
                return state

        with patch.object(
            draft_module, "YahooOAuth", _FakeOAuthConnected
        ), patch.object(draft_module, "YahooAdapter", _FakeYahooAdapter), patch.object(
            draft_module,
            "_load_cached_projections",
            return_value=_make_mock_projections(),
        ):
            resp = client.get(
                "/api/draft/live",
                params={
                    "draft_id": "nfl.l.12345",
                    "platform": "yahoo",
                    "my_slot": 5,
                    "season": 2026,
                },
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["platform"] == "yahoo"
        assert data["picks_made"] == 2
        assert len(data["recommendations"]) > 0
        # Slot 5 in a 10-team snake with 2 picks made → next pick is #5.
        assert data["my_next_pick_no"] == 5

    def test_sleeper_default_platform_unchanged(self):
        """Omitting platform keeps the Sleeper behavior (regression guard)."""
        resp = client.get("/api/draft/live", params={"season": 2026})
        assert resp.status_code == 400  # missing draft_id/username, not 503


# ---------------------------------------------------------------------------
# Test: POST /api/draft/sync-log  (ESPN paste-sync)
# ---------------------------------------------------------------------------


class TestSyncLog:
    """Paste a pick log once; the whole board catches up."""

    def test_applies_picks_in_order_with_slot_attribution(self, draft_session):
        sid = draft_session["session_id"]
        text = (
            "R1, P1  Bijan Robinson, RB  ATL\n"
            "R1, P2  Jahmyr Gibbs, RB  DET\n"
            "On the Clock: Team Three\n"
        )
        resp = client.post(
            "/api/draft/sync-log",
            json={"session_id": sid, "text": text, "my_slot": 2},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["matched"] == 2
        assert data["applied"] == 2
        assert data["already_drafted"] == 0
        # 12-team snake: pick 2 belongs to slot 2 → it's the user's pick.
        assert data["my_picks_applied"] == 1
        assert data["picks_taken"] == 2
        assert data["unmatched_lines"] == ["On the Clock: Team Three"]

    def test_full_history_repaste_is_idempotent(self, draft_session):
        sid = draft_session["session_id"]
        text = "Bijan Robinson\nJahmyr Gibbs\n"
        first = client.post(
            "/api/draft/sync-log", json={"session_id": sid, "text": text}
        )
        assert first.json()["applied"] == 2
        second = client.post(
            "/api/draft/sync-log", json={"session_id": sid, "text": text}
        )
        data = second.json()
        assert data["applied"] == 0
        assert data["already_drafted"] == 2
        assert data["picks_taken"] == 2

    def test_unknown_session_404(self):
        resp = client.post(
            "/api/draft/sync-log",
            json={"session_id": "nope", "text": "Bijan Robinson"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Feature 1: cost of waiting (position_wait / wait_cost on recommendations)
# ---------------------------------------------------------------------------


def _adp_loader_factory(adp_lookup):
    """Build a _load_draft_data replacement that merges an explicit
    player_name -> adp_rank map into the synthetic mock projections
    (the plain draft_session fixture has no ADP data at all)."""

    def _loader(scoring, season, adp_source=None):
        from draft_optimizer import compute_value_scores

        adp_df = pd.DataFrame(
            {
                "player_name": list(adp_lookup.keys()),
                "adp_rank": list(adp_lookup.values()),
            }
        )
        return compute_value_scores(_make_mock_projections(), adp_df)

    return _loader


class TestPositionWait:
    """GET /api/draft/recommendations?user_pick=N -> position_wait + wait_cost."""

    def _banded_adp_session(self):
        """A fresh session whose players carry adp_rank (ADP-aware, unlike
        the plain draft_session fixture) so gone-probability/cost-of-waiting
        has something to compute over."""
        from web.api.routers import draft as draft_module

        proj = _make_mock_projections()
        adp_lookup = {
            name: float(i + 1) for i, name in enumerate(proj["player_name"])
        }
        draft_module._sessions.clear()
        with patch.object(
            draft_module, "_load_draft_data", side_effect=_adp_loader_factory(adp_lookup)
        ):
            resp = client.get("/api/draft/board")
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_position_wait_present_when_user_pick_given(self):
        session = self._banded_adp_session()
        sid = session["session_id"]
        resp = client.get(
            "/api/draft/recommendations",
            params={"session_id": sid, "top_n": 5, "user_pick": 1},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data["position_wait"], list)
        assert len(data["position_wait"]) > 0
        for pw in data["position_wait"]:
            assert {"position", "best_now_vorp", "expected_best_next_vorp", "wait_cost"} <= set(
                pw
            )
            assert pw["wait_cost"] == pytest.approx(
                pw["best_now_vorp"] - pw["expected_best_next_vorp"], abs=0.05
            )
        # Each recommendation's wait_cost matches its position's entry.
        by_pos = {pw["position"]: pw["wait_cost"] for pw in data["position_wait"]}
        for rec in data["recommendations"]:
            if rec["position"] in by_pos:
                assert rec["wait_cost"] == pytest.approx(by_pos[rec["position"]], abs=0.05)

    def test_position_wait_empty_without_user_pick(self, draft_session):
        """No user_pick and no mock-draft slot -- next pick number unknown,
        so position_wait degrades to empty and wait_cost to None (never a
        fabricated number)."""
        sid = draft_session["session_id"]
        resp = client.get(
            "/api/draft/recommendations", params={"session_id": sid, "top_n": 5}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["position_wait"] == []
        for rec in data["recommendations"]:
            assert rec["wait_cost"] is None

    def test_position_wait_matches_hand_computed_expected_best_vorp(self):
        """Cross-check the API's position_wait against directly calling
        expected_best_vorp_at_pick on the same board snapshot."""
        from draft_availability import expected_best_vorp_at_pick

        session = self._banded_adp_session()
        sid = session["session_id"]
        resp = client.get(
            "/api/draft/recommendations",
            params={"session_id": sid, "top_n": 5, "user_pick": 1},
        )
        data = resp.json()

        from web.api.routers import draft as draft_module

        board = draft_module._sessions[sid]["board"]
        # 12-team snake, 0 picks taken so far -> user's next pick is #1.
        expected = expected_best_vorp_at_pick(board.available, 1)
        by_pos = {pw["position"]: pw for pw in data["position_wait"]}
        for pos, expected_vorp in expected.items():
            if pos not in by_pos:
                continue
            assert by_pos[pos]["expected_best_next_vorp"] == pytest.approx(
                round(expected_vorp, 1), abs=0.05
            )


# ---------------------------------------------------------------------------
# Feature 2: floor/ceiling bands, strategy re-rank, roster_risk
# ---------------------------------------------------------------------------


class TestFloorCeilingProxy:
    """Unit tests for _add_floor_ceiling_proxy -- the documented in-repo
    proxy used when the projection source has no real quantile bands."""

    def test_passthrough_when_bands_already_present(self):
        from web.api.routers.draft import _add_floor_ceiling_proxy

        df = pd.DataFrame(
            {
                "position": ["RB"],
                "projected_season_points": [200.0],
                "projected_floor": [150.0],
                "projected_ceiling": [250.0],
            }
        )
        out = _add_floor_ceiling_proxy(df)
        assert out["projected_floor"].iloc[0] == 150.0
        assert out["projected_ceiling"].iloc[0] == 250.0

    def test_derives_proxy_using_position_multiplier(self):
        from web.api.routers.draft import _add_floor_ceiling_proxy
        from projection_engine import _FLOOR_CEILING_MULT

        df = pd.DataFrame(
            {"position": ["RB"], "projected_season_points": [200.0]}
        )
        out = _add_floor_ceiling_proxy(df)
        mult = _FLOOR_CEILING_MULT["RB"]
        assert out["projected_floor"].iloc[0] == pytest.approx(
            round(200.0 * (1 - mult), 2)
        )
        assert out["projected_ceiling"].iloc[0] == pytest.approx(
            round(200.0 * (1 + mult), 2)
        )

    def test_unknown_position_uses_default_multiplier(self):
        from web.api.routers.draft import _add_floor_ceiling_proxy

        df = pd.DataFrame({"position": ["DST"], "projected_season_points": [50.0]})
        out = _add_floor_ceiling_proxy(df)
        assert out["projected_floor"].iloc[0] == pytest.approx(round(50.0 * 0.60, 2))
        assert out["projected_ceiling"].iloc[0] == pytest.approx(round(50.0 * 1.40, 2))

    def test_nan_points_row_yields_nan_bands_not_zero(self):
        from web.api.routers.draft import _add_floor_ceiling_proxy

        df = pd.DataFrame(
            {"position": ["DST"], "projected_season_points": [np.nan]}
        )
        out = _add_floor_ceiling_proxy(df)
        assert pd.isna(out["projected_floor"].iloc[0])
        assert pd.isna(out["projected_ceiling"].iloc[0])

    def test_missing_points_or_position_column_never_raises(self):
        from web.api.routers.draft import _add_floor_ceiling_proxy

        df = pd.DataFrame({"player_name": ["Foo"]})
        out = _add_floor_ceiling_proxy(df)
        assert out["projected_floor"].isna().all()
        assert out["projected_ceiling"].isna().all()


class TestStrategyReorder:
    """Unit tests for _reorder_by_strategy."""

    def test_balanced_is_a_no_op(self):
        from web.api.routers.draft import _reorder_by_strategy

        df = pd.DataFrame({"projected_floor": [1.0, 3.0, 2.0]})
        out = _reorder_by_strategy(df, "balanced")
        assert list(out["projected_floor"]) == [1.0, 3.0, 2.0]

    def test_floor_sorts_descending(self):
        from web.api.routers.draft import _reorder_by_strategy

        df = pd.DataFrame(
            {
                "player_name": ["A", "B", "C"],
                "projected_floor": [10.0, 30.0, 20.0],
            }
        )
        out = _reorder_by_strategy(df, "floor")
        assert list(out["player_name"]) == ["B", "C", "A"]

    def test_ceiling_sorts_descending(self):
        from web.api.routers.draft import _reorder_by_strategy

        df = pd.DataFrame(
            {
                "player_name": ["A", "B", "C"],
                "projected_ceiling": [5.0, 50.0, 25.0],
            }
        )
        out = _reorder_by_strategy(df, "ceiling")
        assert list(out["player_name"]) == ["B", "C", "A"]

    def test_no_op_when_band_column_absent(self):
        from web.api.routers.draft import _reorder_by_strategy

        df = pd.DataFrame({"player_name": ["A", "B"]})
        out = _reorder_by_strategy(df, "floor")
        assert list(out["player_name"]) == ["A", "B"]

    def test_no_op_when_band_column_all_nan(self):
        from web.api.routers.draft import _reorder_by_strategy

        df = pd.DataFrame(
            {"player_name": ["A", "B"], "projected_floor": [np.nan, np.nan]}
        )
        out = _reorder_by_strategy(df, "floor")
        assert list(out["player_name"]) == ["A", "B"]


class TestRosterRisk:
    """Unit tests for _compute_roster_risk."""

    def test_empty_roster_returns_none(self):
        from web.api.routers.draft import _compute_roster_risk

        assert _compute_roster_risk([]) is None

    def test_roster_without_bands_returns_none(self):
        from web.api.routers.draft import _compute_roster_risk

        roster = [{"player_name": "A", "projected_season_points": 100.0}]
        assert _compute_roster_risk(roster) is None

    def test_roster_with_bands_computes_sums_and_volatility(self):
        from web.api.routers.draft import _compute_roster_risk

        roster = [
            {
                "player_name": "A",
                "projected_season_points": 100.0,
                "projected_floor": 60.0,
                "projected_ceiling": 140.0,
            },
            {
                "player_name": "B",
                "projected_season_points": 200.0,
                "projected_floor": 150.0,
                "projected_ceiling": 250.0,
            },
        ]
        risk = _compute_roster_risk(roster)
        assert risk is not None
        assert risk.floor_sum == pytest.approx(210.0)
        assert risk.ceiling_sum == pytest.approx(390.0)
        assert risk.projected_sum == pytest.approx(300.0)
        # volatility = mean((ceiling-floor)/projected) = mean(0.80, 0.50) = 0.65
        expected_vol = ((140.0 - 60.0) / 100.0 + (250.0 - 150.0) / 200.0) / 2
        assert risk.volatility_index == pytest.approx(round(expected_vol, 3))

    def test_partial_bands_excludes_unbanded_players_from_volatility(self):
        from web.api.routers.draft import _compute_roster_risk

        roster = [
            {
                "player_name": "A",
                "projected_season_points": 100.0,
                "projected_floor": 60.0,
                "projected_ceiling": 140.0,
            },
            {"player_name": "DST1", "projected_season_points": np.nan},
        ]
        risk = _compute_roster_risk(roster)
        assert risk is not None
        # Only A contributes a ratio: (140-60)/100 = 0.80
        assert risk.volatility_index == pytest.approx(0.8)


class TestStrategyAndRosterRiskEndpoints:
    """API-level: GET /draft/board?strategy=... + roster_risk on the response."""

    def _banded_loader(self, scoring, season, adp_source=None):
        from draft_optimizer import compute_value_scores
        from web.api.routers.draft import _add_floor_ceiling_proxy

        enriched = compute_value_scores(_make_mock_projections())
        return _add_floor_ceiling_proxy(enriched)

    def test_board_floor_strategy_reorders_players(self):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        with patch.object(draft_module, "_load_draft_data", side_effect=self._banded_loader):
            resp = client.get("/api/draft/board", params={"strategy": "floor"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["strategy"] == "floor"
        floors = [p["floor"] for p in data["players"]]
        assert floors == sorted(floors, reverse=True)

    def test_board_ceiling_strategy_reorders_players(self):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        with patch.object(draft_module, "_load_draft_data", side_effect=self._banded_loader):
            resp = client.get("/api/draft/board", params={"strategy": "ceiling"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        ceilings = [p["ceiling"] for p in data["players"]]
        assert ceilings == sorted(ceilings, reverse=True)

    def test_board_default_strategy_is_balanced(self, draft_session):
        assert draft_session["strategy"] == "balanced"

    def test_roster_risk_none_before_any_pick(self):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        with patch.object(draft_module, "_load_draft_data", side_effect=self._banded_loader):
            resp = client.get("/api/draft/board")
        assert resp.json()["roster_risk"] is None

    def test_roster_risk_populated_after_a_pick(self):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        with patch.object(draft_module, "_load_draft_data", side_effect=self._banded_loader):
            board_resp = client.get("/api/draft/board")
            sid = board_resp.json()["session_id"]
            player_id = board_resp.json()["players"][0]["player_id"]
            client.post(
                "/api/draft/pick",
                json={"session_id": sid, "player_id": player_id, "by_me": True},
            )
            resp = client.get("/api/draft/board", params={"session_id": sid})
        risk = resp.json()["roster_risk"]
        assert risk is not None
        assert risk["floor_sum"] > 0
        assert risk["ceiling_sum"] >= risk["floor_sum"]
        assert risk["volatility_index"] is not None


# ---------------------------------------------------------------------------
# Feature 3: post-draft report with receipts
# ---------------------------------------------------------------------------


class TestMockDraftReport:
    def test_report_requires_mock_session(self, draft_session):
        """A plain board session (no simulator) -> 400."""
        sid = draft_session["session_id"]
        resp = client.get("/api/draft/mock/report", params={"session_id": sid})
        assert resp.status_code == 400

    def test_report_unknown_session_404(self):
        resp = client.get(
            "/api/draft/mock/report", params={"session_id": "nope-nope"}
        )
        assert resp.status_code == 404

    def test_report_empty_before_any_pick(self):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        start = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 1, "season": 2026},
        )
        sid = start.json()["session_id"]
        resp = client.get("/api/draft/mock/report", params={"session_id": sid})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["picks"] == []
        assert data["summary"]["total_projected"] == 0
        assert data["summary"]["total_vorp"] == 0
        assert data["summary"]["letter_grade"] in ("A", "B", "C", "D")

    def test_report_first_pick_best_alternative_is_correct(self):
        """Hand-verify best_alternative + vorp_delta against an independent
        recomputation of the highest-VORP player excluding the one drafted."""
        from web.api.routers import draft as draft_module
        from draft_optimizer import compute_value_scores

        draft_module._sessions.clear()
        start = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 2, "user_pick": 1, "season": 2026},
        )
        sid = start.json()["session_id"]
        pick_resp = client.post("/api/draft/mock/pick", json={"session_id": sid})
        assert pick_resp.status_code == 200, pick_resp.text
        first = pick_resp.json()
        assert first["is_user_turn"] is True
        picked_name = first["player_name"]

        report_resp = client.get("/api/draft/mock/report", params={"session_id": sid})
        assert report_resp.status_code == 200, report_resp.text
        data = report_resp.json()
        assert len(data["picks"]) == 1
        row = data["picks"][0]
        assert row["player_name"] == picked_name
        assert row["overall_pick"] == 1
        assert row["round"] == 1

        full = compute_value_scores(_make_mock_projections())
        remaining = full[full["player_name"] != picked_name]
        expected_alt = remaining.loc[remaining["vorp"].idxmax()]

        assert row["best_alternative"] is not None
        assert row["best_alternative"]["player_name"] == expected_alt["player_name"]
        assert row["best_alternative"]["vorp"] == pytest.approx(
            float(expected_alt["vorp"]), abs=0.05
        )
        assert row["vorp_delta"] == pytest.approx(
            row["vorp"] - row["best_alternative"]["vorp"], abs=0.05
        )

    def test_adp_delta_sign_convention_steal_vs_reach(self):
        """adp_delta = overall_pick - adp_rank: positive => steal (fell past
        ADP), negative => reach (taken ahead of ADP)."""
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        proj = _make_mock_projections()
        adp_lookup = {name: float(i + 1) for i, name in enumerate(proj["player_name"])}

        def _loader(scoring, season, adp_source=None):
            from draft_optimizer import compute_value_scores

            adp_df = pd.DataFrame(
                {
                    "player_name": list(adp_lookup.keys()),
                    "adp_rank": list(adp_lookup.values()),
                }
            )
            return compute_value_scores(proj, adp_df)

        with patch.object(draft_module, "_load_draft_data", side_effect=_loader):
            start = client.post(
                "/api/draft/mock/start",
                json={
                    "scoring": "half_ppr",
                    "n_teams": 2,
                    "user_pick": 1,
                    "season": 2026,
                },
            )
            sid = start.json()["session_id"]
            pick_resp = client.post("/api/draft/mock/pick", json={"session_id": sid})
            report_resp = client.get(
                "/api/draft/mock/report", params={"session_id": sid}
            )

        picked_name = pick_resp.json()["player_name"]
        expected_adp = adp_lookup[picked_name]
        row = report_resp.json()["picks"][0]
        assert row["adp_rank"] == pytest.approx(expected_adp, abs=0.05)
        assert row["adp_delta"] == pytest.approx(1 - expected_adp, abs=0.05)

    def test_summary_grade_notes_mention_position_balance(self):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        start = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 1, "season": 2026},
        )
        sid = start.json()["session_id"]
        client.post("/api/draft/mock/pick", json={"session_id": sid})
        resp = client.get("/api/draft/mock/report", params={"session_id": sid})
        notes = resp.json()["summary"]["grade_notes"]
        assert any("needed" in n.lower() or "filled" in n.lower() for n in notes)

    def test_summary_letter_grade_matches_pick_grade_logic(self):
        """letter_grade must be produced by the same _pick_grade single
        source of truth used by POST /draft/mock/pick's completion path."""
        from web.api.routers import draft as draft_module
        from draft_optimizer import _pick_grade

        draft_module._sessions.clear()
        start = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 2, "user_pick": 1, "season": 2026},
        )
        sid = start.json()["session_id"]
        client.post("/api/draft/mock/pick", json={"session_id": sid})

        session = draft_module._sessions[sid]
        board = session["board"]
        simulator = session["simulator"]
        total_picks = board.n_teams * sum(board.roster_config.values())
        expected_vorp = simulator._estimate_expected_vorp(total_picks)
        total_vorp = sum(
            float(p.get("vorp", 0) or 0) for p in board.my_roster
        )
        expected_grade = _pick_grade(round(total_vorp, 1), expected_vorp)

        resp = client.get("/api/draft/mock/report", params={"session_id": sid})
        assert resp.json()["summary"]["letter_grade"] == expected_grade


# ---------------------------------------------------------------------------
# Feature 4: undo
# ---------------------------------------------------------------------------


class TestManualUndo:
    def test_undo_restores_board_and_roster(self, draft_session):
        sid = draft_session["session_id"]
        player_id = draft_session["players"][0]["player_id"]
        client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": player_id, "by_me": True},
        )
        mid = client.get("/api/draft/board", params={"session_id": sid}).json()
        assert mid["picks_taken"] == 1
        assert mid["my_pick_count"] == 1

        resp = client.post("/api/draft/undo", json={"session_id": sid})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["player"]["player_id"] == player_id

        after = client.get("/api/draft/board", params={"session_id": sid}).json()
        assert after["picks_taken"] == 0
        assert after["my_pick_count"] == 0
        assert len(after["players"]) == len(draft_session["players"])
        assert any(p["player_id"] == player_id for p in after["players"])
        assert after["my_roster"] == []

    def test_undo_opponent_pick_restores_drafted_by_others(self, draft_session):
        sid = draft_session["session_id"]
        player_id = draft_session["players"][1]["player_id"]
        client.post(
            "/api/draft/pick",
            json={"session_id": sid, "player_id": player_id, "by_me": False},
        )
        from web.api.routers import draft as draft_module

        board = draft_module._sessions[sid]["board"]
        assert player_id in board.drafted_by_others

        resp = client.post("/api/draft/undo", json={"session_id": sid})
        assert resp.status_code == 200
        assert player_id not in board.drafted_by_others
        assert board.picks_taken() == 0

    def test_undo_no_picks_returns_409(self, draft_session):
        sid = draft_session["session_id"]
        resp = client.post("/api/draft/undo", json={"session_id": sid})
        assert resp.status_code == 409

    def test_undo_unknown_session_404(self):
        resp = client.post("/api/draft/undo", json={"session_id": "nope"})
        assert resp.status_code == 404


class TestMockUndo:
    def test_mock_undo_reverts_to_before_last_user_pick_and_redo_is_deterministic(
        self,
    ):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        start = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 2, "user_pick": 1, "season": 2026},
        )
        sid = start.json()["session_id"]

        # n_teams=2 snake: user picks land at overall_pick 1 and 4.
        picks = [
            client.post("/api/draft/mock/pick", json={"session_id": sid}).json()
            for _ in range(4)
        ]
        assert picks[0]["is_user_turn"] is True  # pick 1
        assert picks[3]["is_user_turn"] is True  # pick 4
        original_pick4_player = picks[3]["player_name"]

        board_before = client.get(
            "/api/draft/board", params={"session_id": sid}
        ).json()
        assert board_before["picks_taken"] == 4
        assert board_before["my_pick_count"] == 2

        undo_resp = client.post("/api/draft/mock/undo", json={"session_id": sid})
        assert undo_resp.status_code == 200, undo_resp.text
        undo_data = undo_resp.json()
        assert undo_data["success"] is True
        assert undo_data["pick_number"] == 3

        board_after = client.get(
            "/api/draft/board", params={"session_id": sid}
        ).json()
        assert board_after["picks_taken"] == 3
        assert board_after["my_pick_count"] == 1  # only pick 1 remains

        # Redo: replaying pick 4 from the exact restored state must yield
        # the identical player -- proof the simulator/board state is a true
        # rebuild, not an approximation.
        redo = client.post("/api/draft/mock/pick", json={"session_id": sid})
        assert redo.status_code == 200
        redo_data = redo.json()
        assert redo_data["pick_number"] == 4
        assert redo_data["is_user_turn"] is True
        assert redo_data["player_name"] == original_pick4_player

    def test_mock_undo_requires_simulator(self, draft_session):
        sid = draft_session["session_id"]
        resp = client.post("/api/draft/mock/undo", json={"session_id": sid})
        assert resp.status_code == 400

    def test_mock_undo_no_user_pick_returns_409(self):
        from web.api.routers import draft as draft_module

        draft_module._sessions.clear()
        start = client.post(
            "/api/draft/mock/start",
            json={"scoring": "half_ppr", "n_teams": 12, "user_pick": 5, "season": 2026},
        )
        sid = start.json()["session_id"]
        resp = client.post("/api/draft/mock/undo", json={"session_id": sid})
        assert resp.status_code == 409

    def test_mock_undo_unknown_session_404(self):
        resp = client.post("/api/draft/mock/undo", json={"session_id": "nope"})
        assert resp.status_code == 404
