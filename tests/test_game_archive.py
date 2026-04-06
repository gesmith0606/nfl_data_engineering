"""
Tests for the game archive module and API endpoints.

Uses mock data so tests run without real Parquet files on disk.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

from web.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Mock data factories
# ---------------------------------------------------------------------------


def _mock_schedule_df() -> pd.DataFrame:
    """Minimal schedule DataFrame for testing."""
    return pd.DataFrame(
        {
            "game_id": ["2024_01_BAL_KC", "2024_01_GB_PHI"],
            "season": [2024, 2024],
            "game_type": ["REG", "REG"],
            "week": [1, 1],
            "gameday": ["2024-09-05", "2024-09-06"],
            "gametime": ["20:20", "20:15"],
            "away_team": ["BAL", "GB"],
            "away_score": [20, 29],
            "home_team": ["KC", "PHI"],
            "home_score": [27, 34],
            "result": [7, 5],
            "total": [47, 63],
            "overtime": [0, 0],
        }
    )


def _mock_player_weekly_df() -> pd.DataFrame:
    """Minimal player weekly DataFrame for testing."""
    return pd.DataFrame(
        {
            "player_id": [
                "00-0033873",
                "00-0034796",
                "00-0036264",
                "00-0036389",
                "00-0035228",
                "00-0037235",
            ],
            "player_name": [
                "P.Mahomes",
                "L.Jackson",
                "J.Love",
                "J.Hurts",
                "I.Pacheco",
                "D.Henry",
            ],
            "player_display_name": [
                "Patrick Mahomes",
                "Lamar Jackson",
                "Jordan Love",
                "Jalen Hurts",
                "Isiah Pacheco",
                "Derrick Henry",
            ],
            "position": ["QB", "QB", "QB", "QB", "RB", "RB"],
            "recent_team": ["KC", "BAL", "GB", "PHI", "KC", "BAL"],
            "season": [2024, 2024, 2024, 2024, 2024, 2024],
            "week": [1, 1, 1, 1, 1, 1],
            "season_type": ["REG"] * 6,
            "opponent_team": ["BAL", "KC", "PHI", "GB", "BAL", "KC"],
            "passing_yards": [241.0, 167.0, 260.0, 278.0, 0.0, 0.0],
            "passing_tds": [1.0, 1.0, 2.0, 2.0, 0.0, 0.0],
            "interceptions": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            "rushing_yards": [29.0, 122.0, 12.0, 33.0, 46.0, 46.0],
            "rushing_tds": [0.0, 1.0, 0.0, 2.0, 1.0, 0.0],
            "receptions": [0.0, 0.0, 0.0, 0.0, 2.0, 0.0],
            "receiving_yards": [0.0, 0.0, 0.0, 0.0, 14.0, 0.0],
            "receiving_tds": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "targets": [0, 0, 0, 0, 3, 0],
            "carries": [4, 16, 2, 7, 11, 13],
            "sack_fumbles_lost": [0, 0, 0, 0, 0, 0],
            "rushing_fumbles_lost": [0, 0, 0, 0, 0, 0],
            "receiving_fumbles_lost": [0, 0, 0, 0, 0, 0],
            "passing_2pt_conversions": [0, 0, 0, 0, 0, 0],
            "rushing_2pt_conversions": [0, 0, 0, 0, 0, 0],
            "receiving_2pt_conversions": [0, 0, 0, 0, 0, 0],
        }
    )


def _mock_player_weekly_multi_week() -> pd.DataFrame:
    """Player weekly data spanning multiple weeks for leader/log tests."""
    base = _mock_player_weekly_df()
    week2 = base.copy()
    week2["week"] = 2
    week2["passing_yards"] = [300.0, 200.0, 220.0, 310.0, 0.0, 0.0]
    week2["rushing_yards"] = [15.0, 80.0, 8.0, 40.0, 90.0, 120.0]
    week2["rushing_tds"] = [0.0, 0.0, 0.0, 1.0, 2.0, 1.0]
    return pd.concat([base, week2], ignore_index=True)


# ---------------------------------------------------------------------------
# Unit tests for src/game_archive.py
# ---------------------------------------------------------------------------


class TestGetGameResults:
    """Tests for get_game_results()."""

    @patch("game_archive._load_schedules")
    def test_basic_game_results(self, mock_load):
        from game_archive import get_game_results

        mock_load.return_value = _mock_schedule_df()
        result = get_game_results(2024, week=1)

        assert len(result) == 2
        assert "game_id" in result.columns
        assert "winner" in result.columns
        assert "total_points" in result.columns

        kc_game = result[result["game_id"] == "2024_01_BAL_KC"].iloc[0]
        assert kc_game["winner"] == "KC"
        assert kc_game["total_points"] == 47
        assert kc_game["point_spread_result"] == 7  # home_score - away_score

    @patch("game_archive._load_schedules")
    def test_full_season(self, mock_load):
        from game_archive import get_game_results

        mock_load.return_value = _mock_schedule_df()
        result = get_game_results(2024)
        assert len(result) == 2

    @patch("game_archive._load_schedules")
    def test_empty_week(self, mock_load):
        from game_archive import get_game_results

        mock_load.return_value = _mock_schedule_df()
        result = get_game_results(2024, week=5)
        assert len(result) == 0

    @patch("game_archive._load_schedules")
    def test_missing_season(self, mock_load):
        from game_archive import get_game_results

        mock_load.side_effect = FileNotFoundError("No data")
        with pytest.raises(FileNotFoundError):
            get_game_results(1998)


class TestGetGamePlayerStats:
    """Tests for get_game_player_stats()."""

    @patch("game_archive._load_schedules")
    @patch("game_archive._load_player_weekly")
    def test_basic_player_stats(self, mock_pw, mock_sched):
        from game_archive import get_game_player_stats

        mock_pw.return_value = _mock_player_weekly_df()
        mock_sched.return_value = _mock_schedule_df()

        result = get_game_player_stats(2024, 1)

        assert len(result) == 6
        assert "fantasy_points" in result.columns
        assert "game_id" in result.columns
        # All players should have non-negative fantasy points
        assert (result["fantasy_points"] >= 0).all()

    @patch("game_archive._load_schedules")
    @patch("game_archive._load_player_weekly")
    def test_filter_by_game_id(self, mock_pw, mock_sched):
        from game_archive import get_game_player_stats

        mock_pw.return_value = _mock_player_weekly_df()
        mock_sched.return_value = _mock_schedule_df()

        result = get_game_player_stats(2024, 1, game_id="2024_01_BAL_KC")

        # Should only have KC and BAL players
        teams = set(result["team"].tolist())
        assert teams <= {"KC", "BAL"}

    @patch("game_archive._load_schedules")
    @patch("game_archive._load_player_weekly")
    def test_scoring_format_ppr(self, mock_pw, mock_sched):
        from game_archive import get_game_player_stats

        mock_pw.return_value = _mock_player_weekly_df()
        mock_sched.return_value = _mock_schedule_df()

        ppr = get_game_player_stats(2024, 1, scoring_format="ppr")
        half = get_game_player_stats(2024, 1, scoring_format="half_ppr")
        std = get_game_player_stats(2024, 1, scoring_format="standard")

        # Pacheco has 2 receptions -- PPR > half_ppr > standard for him
        pacheco_ppr = ppr[ppr["player_id"] == "00-0035228"]["fantasy_points"].iloc[0]
        pacheco_half = half[half["player_id"] == "00-0035228"]["fantasy_points"].iloc[0]
        pacheco_std = std[std["player_id"] == "00-0035228"]["fantasy_points"].iloc[0]
        assert pacheco_ppr > pacheco_half > pacheco_std

    def test_pre_2016_raises(self):
        from game_archive import get_game_player_stats

        with pytest.raises(FileNotFoundError, match="not available before"):
            get_game_player_stats(2010, 1)


class TestGetGameDetail:
    """Tests for get_game_detail()."""

    @patch("game_archive._load_schedules")
    @patch("game_archive._load_player_weekly")
    def test_game_detail_structure(self, mock_pw, mock_sched):
        from game_archive import get_game_detail

        mock_pw.return_value = _mock_player_weekly_df()
        mock_sched.return_value = _mock_schedule_df()

        detail = get_game_detail(2024, 1, "2024_01_BAL_KC")

        assert "game_info" in detail
        assert "home_players" in detail
        assert "away_players" in detail
        assert "top_performers" in detail
        assert detail["game_info"]["home_team"] == "KC"
        assert detail["game_info"]["away_team"] == "BAL"
        assert len(detail["top_performers"]) <= 5

    @patch("game_archive._load_schedules")
    def test_game_not_found(self, mock_sched):
        from game_archive import get_game_detail

        mock_sched.return_value = _mock_schedule_df()
        with pytest.raises(ValueError, match="not found"):
            get_game_detail(2024, 1, "2024_01_FAKE_GAME")

    @patch("game_archive._load_schedules")
    def test_pre_2016_no_player_stats(self, mock_sched):
        from game_archive import get_game_detail

        sched = _mock_schedule_df()
        sched["season"] = 2010
        sched["game_id"] = ["2010_01_BAL_KC", "2010_01_GB_PHI"]
        mock_sched.return_value = sched

        detail = get_game_detail(2010, 1, "2010_01_BAL_KC")
        assert detail["home_players"] == []
        assert detail["away_players"] == []


class TestGetSeasonLeaders:
    """Tests for get_season_leaders()."""

    @patch("game_archive._load_player_weekly")
    def test_basic_leaders(self, mock_pw):
        from game_archive import get_season_leaders

        mock_pw.return_value = _mock_player_weekly_multi_week()

        result = get_season_leaders(2024)

        assert len(result) > 0
        assert "total_fantasy_points" in result.columns
        assert "ppg" in result.columns
        assert "games_played" in result.columns
        # Should be sorted descending
        assert result["total_fantasy_points"].is_monotonic_decreasing

    @patch("game_archive._load_player_weekly")
    def test_position_filter(self, mock_pw):
        from game_archive import get_season_leaders

        mock_pw.return_value = _mock_player_weekly_multi_week()

        result = get_season_leaders(2024, position="RB")
        assert all(result["position"] == "RB")

    @patch("game_archive._load_player_weekly")
    def test_limit(self, mock_pw):
        from game_archive import get_season_leaders

        mock_pw.return_value = _mock_player_weekly_multi_week()

        result = get_season_leaders(2024, limit=2)
        assert len(result) <= 2

    def test_pre_2016_raises(self):
        from game_archive import get_season_leaders

        with pytest.raises(FileNotFoundError):
            get_season_leaders(2010)


class TestGetPlayerGameLog:
    """Tests for get_player_game_log()."""

    @patch("game_archive._load_schedules")
    @patch("game_archive._load_player_weekly")
    def test_basic_game_log(self, mock_pw, mock_sched):
        from game_archive import get_player_game_log

        mock_pw.return_value = _mock_player_weekly_multi_week()
        mock_sched.return_value = _mock_schedule_df()

        result = get_player_game_log("00-0033873", 2024)

        assert len(result) == 2  # Two weeks
        assert "fantasy_points" in result.columns
        assert "opponent" in result.columns
        assert "home_away" in result.columns
        assert list(result["week"]) == [1, 2]

    @patch("game_archive._load_schedules")
    @patch("game_archive._load_player_weekly")
    def test_player_not_found(self, mock_pw, mock_sched):
        from game_archive import get_player_game_log

        mock_pw.return_value = _mock_player_weekly_multi_week()
        mock_sched.return_value = _mock_schedule_df()

        result = get_player_game_log("00-NONEXISTENT", 2024)
        assert len(result) == 0

    def test_pre_2016_raises(self):
        from game_archive import get_player_game_log

        with pytest.raises(FileNotFoundError):
            get_player_game_log("00-0033873", 2010)


class TestGetAvailableSeasons:
    """Tests for get_available_seasons()."""

    def test_available_seasons_returns_list(self):
        from game_archive import get_available_seasons

        # Uses real local data directories; just verify shape
        result = get_available_seasons()
        assert isinstance(result, list)
        if result:
            assert "season" in result[0]
            assert "game_count" in result[0]
            assert "has_player_stats" in result[0]
            # Should be sorted descending by season
            seasons = [r["season"] for r in result]
            assert seasons == sorted(seasons, reverse=True)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestGameAPIEndpoints:
    """Tests for the /api/games/* endpoints."""

    @patch("web.api.services.game_service.get_game_results")
    def test_list_games(self, mock_fn):
        mock_fn.return_value = pd.DataFrame(
            {
                "game_id": ["2024_01_BAL_KC"],
                "season": [2024],
                "week": [1],
                "home_team": ["KC"],
                "away_team": ["BAL"],
                "home_score": [27],
                "away_score": [20],
                "winner": ["KC"],
                "point_spread_result": [7],
                "total_points": [47],
                "game_date": ["2024-09-05"],
                "game_time": ["20:20"],
            }
        )

        resp = client.get("/api/games?season=2024&week=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["season"] == 2024
        assert data["week"] == 1
        assert data["count"] == 1
        assert data["games"][0]["game_id"] == "2024_01_BAL_KC"

    @patch("web.api.services.game_service.get_game_results")
    def test_list_games_not_found(self, mock_fn):
        mock_fn.side_effect = FileNotFoundError("No data")
        resp = client.get("/api/games?season=2000")
        assert resp.status_code == 404

    @patch("web.api.services.game_service.get_game_detail")
    def test_game_detail_endpoint(self, mock_fn):
        mock_fn.return_value = {
            "game_info": {
                "game_id": "2024_01_BAL_KC",
                "season": 2024,
                "week": 1,
                "home_team": "KC",
                "away_team": "BAL",
                "home_score": 27,
                "away_score": 20,
                "winner": "KC",
                "point_spread_result": 7,
                "total_points": 47,
                "game_date": "2024-09-05",
                "game_time": "20:20",
            },
            "home_players": [
                {
                    "player_id": "00-0033873",
                    "player_name": "P.Mahomes",
                    "team": "KC",
                    "position": "QB",
                    "fantasy_points": 18.5,
                    "passing_yards": 241.0,
                    "passing_tds": 1.0,
                    "rushing_yards": 29.0,
                    "rushing_tds": 0.0,
                    "receptions": None,
                    "receiving_yards": None,
                    "receiving_tds": None,
                    "targets": None,
                    "carries": 4.0,
                },
            ],
            "away_players": [],
            "top_performers": [],
        }

        resp = client.get("/api/games/2024_01_BAL_KC?season=2024&week=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game"]["game_info"]["home_team"] == "KC"
        assert len(data["game"]["home_players"]) == 1

    @patch("web.api.services.game_service.get_game_detail")
    def test_game_detail_invalid_scoring(self, mock_fn):
        resp = client.get(
            "/api/games/2024_01_BAL_KC?season=2024&week=1&scoring=invalid"
        )
        assert resp.status_code == 400

    @patch("web.api.services.game_service.season_leaders")
    def test_leaders_endpoint(self, mock_fn):
        mock_fn.return_value = [
            {
                "player_id": "00-0033873",
                "player_name": "P.Mahomes",
                "team": "KC",
                "position": "QB",
                "total_fantasy_points": 350.5,
                "games_played": 17,
                "ppg": 20.62,
                "best_week": 35.2,
                "worst_week": 8.1,
            }
        ]

        resp = client.get("/api/games/leaders?season=2024")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["leaders"]) == 1
        assert data["leaders"][0]["ppg"] == 20.62

    @patch("web.api.services.game_service.season_leaders")
    def test_leaders_position_filter(self, mock_fn):
        mock_fn.return_value = []
        resp = client.get("/api/games/leaders?season=2024&position=RB")
        assert resp.status_code == 200

    @patch("web.api.services.game_service.get_season_leaders")
    def test_leaders_invalid_position(self, mock_fn):
        resp = client.get("/api/games/leaders?season=2024&position=INVALID")
        assert resp.status_code == 400

    @patch("web.api.services.game_service.player_game_log")
    def test_player_log_endpoint(self, mock_fn):
        mock_fn.return_value = [
            {
                "week": 1,
                "opponent": "BAL",
                "home_away": "home",
                "fantasy_points": 18.5,
                "game_result": "W",
                "passing_yards": 241.0,
                "passing_tds": 1.0,
                "rushing_yards": 29.0,
                "rushing_tds": 0.0,
                "receptions": None,
                "receiving_yards": None,
                "receiving_tds": None,
                "targets": None,
                "carries": 4.0,
            }
        ]

        resp = client.get("/api/games/player-log/00-0033873?season=2024")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_id"] == "00-0033873"
        assert len(data["game_log"]) == 1

    @patch("web.api.services.game_service.available_seasons")
    def test_seasons_endpoint(self, mock_fn):
        mock_fn.return_value = [
            {"season": 2024, "game_count": 272, "has_player_stats": True},
            {"season": 2023, "game_count": 272, "has_player_stats": True},
        ]

        resp = client.get("/api/games/seasons")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["seasons"]) == 2
        assert data["seasons"][0]["season"] == 2024
        assert data["seasons"][0]["has_player_stats"] is True
