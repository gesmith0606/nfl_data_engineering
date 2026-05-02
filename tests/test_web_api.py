"""
Tests for the NFL Data Engineering FastAPI web API.

Uses FastAPI TestClient with mocked services so tests run without
real Parquet data on disk.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from web.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures -- mock DataFrames mimicking Gold Parquet schemas
# ---------------------------------------------------------------------------


def _mock_projections_df() -> pd.DataFrame:
    """Minimal DataFrame matching the Gold projections schema."""
    return pd.DataFrame(
        {
            "player_id": ["00-001", "00-002", "00-003"],
            "player_name": ["Patrick Mahomes", "Travis Kelce", "Isiah Pacheco"],
            "position": ["QB", "TE", "RB"],
            "team": ["KC", "KC", "KC"],
            "season": [2024, 2024, 2024],
            "week": [17, 17, 17],
            "proj_pass_yards": [280.0, float("nan"), float("nan")],
            "proj_pass_tds": [2.1, float("nan"), float("nan")],
            "proj_rush_yards": [25.0, float("nan"), 85.0],
            "proj_rush_tds": [0.2, float("nan"), 0.7],
            "proj_rec": [float("nan"), 6.0, 2.5],
            "proj_rec_yards": [float("nan"), 65.0, 18.0],
            "proj_rec_tds": [float("nan"), 0.5, 0.1],
            "projected_points": [22.5, 14.3, 16.8],
            "projected_floor": [14.0, 8.0, 10.0],
            "projected_ceiling": [31.0, 22.0, 25.0],
            "scoring_format": ["half_ppr", "half_ppr", "half_ppr"],
            "position_rank": [1, 3, 5],
            "injury_status": [None, "Questionable", None],
        }
    )


def _mock_predictions_df() -> pd.DataFrame:
    """Minimal DataFrame matching the Gold predictions schema."""
    return pd.DataFrame(
        {
            "game_id": ["2024_17_KC_PIT", "2024_17_BUF_NE"],
            "season": [2024, 2024],
            "week": [17, 17],
            "home_team": ["KC", "BUF"],
            "away_team": ["PIT", "NE"],
            "predicted_spread": [-6.5, -10.0],
            "predicted_total": [45.5, 42.0],
            "vegas_spread": [-7.0, -9.5],
            "vegas_total": [46.0, 43.0],
            "spread_edge": [0.5, -0.5],
            "total_edge": [-0.5, -1.0],
            "confidence_tier": ["medium", "high"],
            "ats_pick": ["home", "home"],
            "ou_pick": ["under", "under"],
        }
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_ok(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


class TestVersion:
    """Phase 79 DQ-02 -- /api/version contract tests.

    - Full 40-char git_sha (no [:8] truncation) -- D-04
    - llm_enrichment_ready mirrors /api/health, never leaks the key -- D-05
    - Seven-key shape locked for Phase 84 DEPLOY-02 consumer
    """

    EXPECTED_KEYS = {
        "version",
        "git_sha",
        "build_id",
        "deployed_at",
        "llm_enrichment_ready",
        "has_team_events_route",
        "has_player_badges_route",
    }

    def test_version_shape_has_seven_keys(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        resp = client.get("/api/version")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == self.EXPECTED_KEYS, list(body.keys())

    def test_git_sha_is_full_40_chars_when_env_set(self, monkeypatch):
        full_sha = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
        assert len(full_sha) == 40
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", full_sha)
        resp = client.get("/api/version")
        assert resp.status_code == 200
        body = resp.json()
        assert body["git_sha"] == full_sha
        assert len(body["git_sha"]) == 40

    def test_git_sha_is_unknown_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json()["git_sha"] == "unknown"

    def test_llm_enrichment_ready_reflects_anthropic_key_bool_only(
        self, monkeypatch
    ):
        secret = "sk-ant-VERY-SECRET-VALUE-NEVER-LEAK"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        resp = client.get("/api/version")
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_enrichment_ready"] is True
        # CRITICAL: the secret value MUST NOT appear in the response body.
        assert (
            secret not in resp.text
        ), "ANTHROPIC_API_KEY value leaked into /api/version response"

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        resp2 = client.get("/api/version")
        assert resp2.status_code == 200
        assert resp2.json()["llm_enrichment_ready"] is False


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------


class TestProjections:
    @patch("web.api.services.projection_service.get_projections")
    def test_list_projections(self, mock_get):
        mock_get.return_value = _mock_projections_df()
        resp = client.get("/api/projections?season=2024&week=17&scoring=half_ppr")
        assert resp.status_code == 200
        body = resp.json()
        assert body["season"] == 2024
        assert body["week"] == 17
        assert body["scoring_format"] == "half_ppr"
        assert len(body["projections"]) == 3
        assert body["projections"][0]["player_name"] == "Patrick Mahomes"

    @patch("web.api.services.projection_service.get_projections")
    def test_position_filter(self, mock_get):
        mock_get.return_value = _mock_projections_df()[
            _mock_projections_df()["position"] == "QB"
        ]
        resp = client.get(
            "/api/projections?season=2024&week=17&scoring=half_ppr&position=QB"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert all(p["position"] == "QB" for p in body["projections"])

    @patch("web.api.services.projection_service.get_projections")
    def test_team_filter(self, mock_get):
        mock_get.return_value = _mock_projections_df()
        resp = client.get(
            "/api/projections?season=2024&week=17&scoring=half_ppr&team=KC"
        )
        assert resp.status_code == 200

    def test_invalid_scoring_format(self):
        resp = client.get("/api/projections?season=2024&week=17&scoring=xyz")
        assert resp.status_code == 400
        assert "Invalid scoring format" in resp.json()["detail"]

    def test_invalid_position(self):
        resp = client.get(
            "/api/projections?season=2024&week=17&scoring=half_ppr&position=DL"
        )
        assert resp.status_code == 400

    @patch(
        "web.api.services.projection_service.get_projections",
        side_effect=FileNotFoundError("No projection data"),
    )
    def test_missing_season_week_404(self, mock_get):
        resp = client.get("/api/projections?season=2025&week=1&scoring=half_ppr")
        assert resp.status_code == 404

    @patch("web.api.services.projection_service.get_projections")
    def test_top_endpoint(self, mock_get):
        mock_get.return_value = _mock_projections_df()
        resp = client.get(
            "/api/projections/top?season=2024&week=17&scoring=half_ppr&limit=2"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["projections"]) <= 3  # mock has 3 rows

    @patch("web.api.services.projection_service.get_projections")
    def test_nan_values_become_null(self, mock_get):
        mock_get.return_value = _mock_projections_df()
        resp = client.get("/api/projections?season=2024&week=17&scoring=half_ppr")
        body = resp.json()
        # Kelce (TE) should have null pass yards
        kelce = next(
            p for p in body["projections"] if p["player_name"] == "Travis Kelce"
        )
        assert kelce["proj_pass_yards"] is None
        assert kelce["proj_rec"] == 6.0

    @patch("web.api.services.projection_service.get_projections")
    def test_default_limit_is_full_slate(self, mock_get):
        """Unfiltered /api/projections must default to 1000 rows.

        Regression for the matchups blanking bug: a 200-row default truncated
        the global top-N by projected_points and silently dropped mid-tier
        starters on lower-projected teams (NYJ TE, MIN WR3, etc.), leaving
        their cards empty. The matchups page builds 32 team rosters from a
        single fetch, so the default must be the API ceiling.
        """
        mock_get.return_value = _mock_projections_df()
        client.get("/api/projections?season=2024&week=17&scoring=half_ppr")
        _, kwargs = mock_get.call_args
        assert kwargs["limit"] == 1000, (
            "Default limit must be 1000 to keep all 32 teams represented in "
            "an unfiltered fetch."
        )


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------


class TestPredictions:
    @patch("web.api.services.prediction_service.get_predictions")
    def test_list_predictions(self, mock_get):
        mock_get.return_value = _mock_predictions_df()
        resp = client.get("/api/predictions?season=2024&week=17")
        assert resp.status_code == 200
        body = resp.json()
        assert body["season"] == 2024
        assert len(body["predictions"]) == 2
        assert body["predictions"][0]["game_id"] == "2024_17_KC_PIT"

    @patch(
        "web.api.services.prediction_service.get_predictions",
        side_effect=FileNotFoundError("No prediction data"),
    )
    def test_missing_predictions_returns_empty_envelope(self, mock_get):
        """Advisor contract: offseason/missing data returns 200 with empty list,
        not 404. See plan 63-02 Task 1 behavior spec."""
        resp = client.get("/api/predictions?season=2025&week=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["predictions"] == []
        assert body["season"] == 2025
        assert body["week"] == 1

    @patch("web.api.services.prediction_service.get_prediction_by_game")
    def test_single_game(self, mock_get):
        row = _mock_predictions_df().iloc[0]
        mock_get.return_value = row
        resp = client.get("/api/predictions/2024_17_KC_PIT?season=2024&week=17")
        assert resp.status_code == 200
        body = resp.json()
        assert body["game_id"] == "2024_17_KC_PIT"
        assert body["home_team"] == "KC"

    @patch("web.api.services.prediction_service.get_prediction_by_game")
    def test_game_not_found(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/api/predictions/FAKE_GAME?season=2024&week=17")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


class TestPlayers:
    @patch("web.api.services.projection_service.search_players")
    def test_search(self, mock_search):
        mock_search.return_value = pd.DataFrame(
            {
                "player_id": ["00-001"],
                "player_name": ["Patrick Mahomes"],
                "team": ["KC"],
                "position": ["QB"],
            }
        )
        resp = client.get("/api/players/search?q=mahomes&season=2024&week=17")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["player_name"] == "Patrick Mahomes"

    def test_search_too_short(self):
        resp = client.get("/api/players/search?q=m")
        assert resp.status_code == 422  # validation error

    @patch("web.api.services.projection_service.get_projections")
    def test_player_detail(self, mock_get):
        mock_get.return_value = _mock_projections_df()
        resp = client.get("/api/players/00-001?season=2024&week=17&scoring=half_ppr")
        assert resp.status_code == 200
        body = resp.json()
        assert body["player_id"] == "00-001"
        assert body["player_name"] == "Patrick Mahomes"
        assert body["projected_points"] == 22.5

    @patch("web.api.services.projection_service.get_projections")
    def test_player_not_found(self, mock_get):
        mock_get.return_value = _mock_projections_df()
        resp = client.get("/api/players/NOPE?season=2024&week=17&scoring=half_ppr")
        assert resp.status_code == 404
