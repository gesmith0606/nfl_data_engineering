"""
Tests for bronze_odds_api_ingestion.py

Covers:
  - Season inference (regular season, January boundary, February boundary)
  - Team name → nflverse abbreviation mapping (all 32 teams)
  - normalize_game: spreads market row structure
  - normalize_game: totals market row structure
  - normalize_response: tidy DataFrame shape and dtypes
  - normalize_response: empty API response (off-season)
  - normalize_response: unmapped team name emits WARNING log
  - Fail-open: requests.RequestException is caught and returns exit 0
  - Fail-open: missing ODDS_API_KEY exits 0 (no crash)
  - --dry-run: parquet is NOT written even when data is present
  - write_parquet dry_run: no file created
  - log_quota: handles missing headers gracefully
  - Full round-trip: mocked fetch → normalize → write (non-dry-run)
"""

import os
import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_odds_api_ingestion import (
    ODDS_API_TO_NFLVERSE,
    fetch_odds,
    infer_nfl_season,
    log_quota,
    normalize_game,
    normalize_response,
    run,
    validate_config,
    write_parquet,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_GAME: dict = {
    "id": "abc123",
    "sport_key": "americanfootball_nfl",
    "sport_title": "NFL",
    "commence_time": "2026-09-10T20:00:00Z",
    "home_team": "Kansas City Chiefs",
    "away_team": "Baltimore Ravens",
    "bookmakers": [
        {
            "key": "fanduel",
            "title": "FanDuel",
            "markets": [
                {
                    "key": "spreads",
                    "outcomes": [
                        {"name": "Kansas City Chiefs", "price": -110, "point": -3.5},
                        {"name": "Baltimore Ravens", "price": -110, "point": 3.5},
                    ],
                },
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "price": -110, "point": 47.5},
                        {"name": "Under", "price": -110, "point": 47.5},
                    ],
                },
            ],
        }
    ],
}

SAMPLE_GAME_JAN: dict = {
    "id": "def456",
    "commence_time": "2027-01-15T21:00:00Z",
    "home_team": "Kansas City Chiefs",
    "away_team": "Houston Texans",
    "bookmakers": [],
}

SNAPSHOT_TS = "2026-09-10T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Season inference tests
# ---------------------------------------------------------------------------

class TestInferNflSeason:
    """Season inference logic."""

    def test_regular_season_september(self):
        assert infer_nfl_season("2026-09-10T20:00:00Z") == 2026

    def test_regular_season_december(self):
        assert infer_nfl_season("2026-12-20T18:00:00Z") == 2026

    def test_january_playoff_is_prior_season(self):
        # A January 2027 game belongs to the 2026 NFL season
        assert infer_nfl_season("2027-01-15T21:00:00Z") == 2026

    def test_february_super_bowl_is_prior_season(self):
        # Super Bowl in February 2027 belongs to the 2026 NFL season
        assert infer_nfl_season("2027-02-02T23:30:00Z") == 2026

    def test_march_is_new_year(self):
        # March is the off-season; returns current year
        assert infer_nfl_season("2027-03-01T00:00:00Z") == 2027

    def test_preseason_august(self):
        assert infer_nfl_season("2026-08-14T23:00:00Z") == 2026


# ---------------------------------------------------------------------------
# Team mapping tests
# ---------------------------------------------------------------------------

class TestOddsApiToNflverse:
    """All 32 current franchises must map correctly."""

    EXPECTED_MAPPINGS = {
        "Buffalo Bills": "BUF",
        "Miami Dolphins": "MIA",
        "New England Patriots": "NE",
        "New York Jets": "NYJ",
        "Baltimore Ravens": "BAL",
        "Cincinnati Bengals": "CIN",
        "Cleveland Browns": "CLE",
        "Pittsburgh Steelers": "PIT",
        "Houston Texans": "HOU",
        "Indianapolis Colts": "IND",
        "Jacksonville Jaguars": "JAX",
        "Tennessee Titans": "TEN",
        "Kansas City Chiefs": "KC",
        "Las Vegas Raiders": "LV",
        "Los Angeles Chargers": "LAC",
        "Denver Broncos": "DEN",
        "Dallas Cowboys": "DAL",
        "New York Giants": "NYG",
        "Philadelphia Eagles": "PHI",
        "Washington Commanders": "WAS",
        "Chicago Bears": "CHI",
        "Detroit Lions": "DET",
        "Green Bay Packers": "GB",
        "Minnesota Vikings": "MIN",
        "Atlanta Falcons": "ATL",
        "Carolina Panthers": "CAR",
        "New Orleans Saints": "NO",
        "Tampa Bay Buccaneers": "TB",
        "Arizona Cardinals": "ARI",
        "Los Angeles Rams": "LA",
        "San Francisco 49ers": "SF",
        "Seattle Seahawks": "SEA",
    }

    @pytest.mark.parametrize("full_name,abbr", list(EXPECTED_MAPPINGS.items()))
    def test_all_32_teams(self, full_name: str, abbr: str):
        assert ODDS_API_TO_NFLVERSE[full_name] == abbr

    def test_historical_washington_redskins(self):
        assert ODDS_API_TO_NFLVERSE["Washington Redskins"] == "WAS"

    def test_historical_oakland_raiders(self):
        assert ODDS_API_TO_NFLVERSE["Oakland Raiders"] == "OAK"


# ---------------------------------------------------------------------------
# normalize_game tests
# ---------------------------------------------------------------------------

class TestNormalizeGame:
    """Per-game row expansion."""

    def test_spreads_row_shape(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        spread_rows = [r for r in rows if r["market"] == "spreads"]
        assert len(spread_rows) == 1

    def test_totals_row_shape(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        totals_rows = [r for r in rows if r["market"] == "totals"]
        assert len(totals_rows) == 1

    def test_spreads_fields_populated(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        spread = next(r for r in rows if r["market"] == "spreads")
        assert spread["home_spread"] == -3.5
        assert spread["price_home"] == -110
        assert spread["price_away"] == -110
        assert spread["total_points"] is None

    def test_totals_fields_populated(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        total = next(r for r in rows if r["market"] == "totals")
        assert total["total_points"] == 47.5
        assert total["price_home"] == -110   # over price
        assert total["price_away"] == -110   # under price
        assert total["home_spread"] is None

    def test_team_abbreviations_set(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        assert all(r["home_team_nfl"] == "KC" for r in rows)
        assert all(r["away_team_nfl"] == "BAL" for r in rows)

    def test_season_inferred_correctly(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        assert all(r["season"] == 2026 for r in rows)

    def test_bookmaker_key_set(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        assert all(r["bookmaker"] == "fanduel" for r in rows)

    def test_snapshot_ts_propagated(self):
        rows = normalize_game(SAMPLE_GAME, SNAPSHOT_TS)
        assert all(r["snapshot_ts"] == SNAPSHOT_TS for r in rows)

    def test_empty_bookmakers_returns_no_rows(self):
        game_no_bm = {**SAMPLE_GAME, "bookmakers": []}
        rows = normalize_game(game_no_bm, SNAPSHOT_TS)
        assert rows == []

    def test_unmapped_team_sets_none(self, caplog):
        game_unknown = {
            **SAMPLE_GAME,
            "home_team": "Springfield Isotopes",
        }
        with caplog.at_level(logging.WARNING):
            rows = normalize_game(game_unknown, SNAPSHOT_TS)
        home_nfl_values = [r["home_team_nfl"] for r in rows]
        assert all(v is None for v in home_nfl_values)


# ---------------------------------------------------------------------------
# normalize_response tests
# ---------------------------------------------------------------------------

class TestNormalizeResponse:
    """Full-response normalisation."""

    def test_returns_dataframe(self):
        df = normalize_response([SAMPLE_GAME], SNAPSHOT_TS)
        assert isinstance(df, pd.DataFrame)

    def test_correct_column_count(self):
        df = normalize_response([SAMPLE_GAME], SNAPSHOT_TS)
        expected_cols = {
            "snapshot_ts", "game_id_ext", "commence_time",
            "home_team", "away_team", "home_team_nfl", "away_team_nfl",
            "bookmaker", "market", "home_spread", "total_points",
            "price_home", "price_away", "season",
        }
        assert expected_cols == set(df.columns)

    def test_row_count_one_game_one_book_two_markets(self):
        # SAMPLE_GAME has 1 bookmaker × 2 markets = 2 rows
        df = normalize_response([SAMPLE_GAME], SNAPSHOT_TS)
        assert len(df) == 2

    def test_empty_games_returns_empty_dataframe_with_schema(self):
        df = normalize_response([], SNAPSHOT_TS)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "snapshot_ts" in df.columns
        assert "market" in df.columns

    def test_multiple_games(self):
        # Two games, each with 1 book and 2 markets = 4 rows total
        df = normalize_response([SAMPLE_GAME, SAMPLE_GAME], SNAPSHOT_TS)
        assert len(df) == 4

    def test_unmapped_team_warning_logged(self, caplog):
        game_unknown = {
            **SAMPLE_GAME,
            "away_team": "Springfield Isotopes",
            "bookmakers": [
                {
                    "key": "fanduel",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Kansas City Chiefs", "price": -110, "point": -3.5},
                                {"name": "Springfield Isotopes", "price": -110, "point": 3.5},
                            ],
                        }
                    ],
                }
            ],
        }
        with caplog.at_level(logging.WARNING):
            normalize_response([game_unknown], SNAPSHOT_TS)
        assert any("Springfield Isotopes" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# write_parquet tests
# ---------------------------------------------------------------------------

class TestWriteParquet:
    """Parquet output."""

    def test_dry_run_does_not_write_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_odds_api_ingestion.BRONZE_DIR",
            str(tmp_path / "odds_api" / "snapshots"),
        )
        df = normalize_response([SAMPLE_GAME], SNAPSHOT_TS)
        write_parquet(df, season=2026, dry_run=True)
        assert list(tmp_path.rglob("*.parquet")) == []

    def test_writes_parquet_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_odds_api_ingestion.BRONZE_DIR",
            str(tmp_path / "odds_api" / "snapshots"),
        )
        df = normalize_response([SAMPLE_GAME], SNAPSHOT_TS)
        out_path = write_parquet(df, season=2026, dry_run=False)
        assert os.path.exists(out_path)
        loaded = pd.read_parquet(out_path)
        assert len(loaded) == len(df)

    def test_parquet_season_partition_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_odds_api_ingestion.BRONZE_DIR",
            str(tmp_path / "odds_api" / "snapshots"),
        )
        df = normalize_response([SAMPLE_GAME], SNAPSHOT_TS)
        out_path = write_parquet(df, season=2026, dry_run=False)
        assert "season=2026" in out_path


# ---------------------------------------------------------------------------
# log_quota tests
# ---------------------------------------------------------------------------

class TestLogQuota:
    """Quota header parsing."""

    def test_logs_known_headers(self, caplog):
        headers = {
            "x-requests-used": "42",
            "x-requests-remaining": "458",
        }
        with caplog.at_level(logging.INFO):
            log_quota(headers)
        combined = " ".join(caplog.messages)
        assert "42" in combined
        assert "458" in combined

    def test_handles_missing_headers_gracefully(self, caplog):
        with caplog.at_level(logging.INFO):
            log_quota({})
        combined = " ".join(caplog.messages)
        assert "unknown" in combined.lower()

    def test_case_insensitive_header_lookup(self, caplog):
        headers = {
            "X-Requests-Remaining": "100",
            "X-Requests-Used": "10",
        }
        with caplog.at_level(logging.INFO):
            log_quota(headers)
        combined = " ".join(caplog.messages)
        assert "100" in combined


# ---------------------------------------------------------------------------
# run() fail-open tests
# ---------------------------------------------------------------------------

class TestRunFailOpen:
    """The run() function must exit 0 on API failure."""

    def test_network_error_returns_zero(self, monkeypatch):
        import requests as req_module
        def bad_get(*args, **kwargs):
            raise req_module.ConnectionError("timeout")
        monkeypatch.setattr("scripts.bronze_odds_api_ingestion.requests.get", bad_get)
        exit_code = run(api_key="fake_key")
        assert exit_code == 0

    def test_http_error_returns_zero(self, monkeypatch):
        import requests as req_module
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_module.HTTPError("403")
        monkeypatch.setattr("scripts.bronze_odds_api_ingestion.requests.get",
                            lambda *a, **kw: mock_resp)
        exit_code = run(api_key="fake_key")
        assert exit_code == 0

    def test_empty_response_returns_zero(self, monkeypatch, tmp_path):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = []
        mock_resp.headers = {}
        monkeypatch.setattr("scripts.bronze_odds_api_ingestion.requests.get",
                            lambda *a, **kw: mock_resp)
        exit_code = run(api_key="fake_key")
        assert exit_code == 0


# ---------------------------------------------------------------------------
# Full round-trip test
# ---------------------------------------------------------------------------

class TestRunRoundTrip:
    """Mocked API → normalize → write parquet."""

    def test_full_pipeline_writes_parquet(self, tmp_path, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [SAMPLE_GAME]
        mock_resp.headers = {
            "x-requests-remaining": "499",
            "x-requests-used": "1",
        }
        monkeypatch.setattr("scripts.bronze_odds_api_ingestion.requests.get",
                            lambda *a, **kw: mock_resp)
        monkeypatch.setattr(
            "scripts.bronze_odds_api_ingestion.BRONZE_DIR",
            str(tmp_path / "odds_api" / "snapshots"),
        )

        exit_code = run(api_key="test_key", dry_run=False)
        assert exit_code == 0

        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert len(parquet_files) == 1
        df = pd.read_parquet(parquet_files[0])
        # 1 bookmaker × 2 markets = 2 rows
        assert len(df) == 2
        assert set(df["market"]) == {"spreads", "totals"}

    def test_full_pipeline_dry_run_no_files(self, tmp_path, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [SAMPLE_GAME]
        mock_resp.headers = {}
        monkeypatch.setattr("scripts.bronze_odds_api_ingestion.requests.get",
                            lambda *a, **kw: mock_resp)
        monkeypatch.setattr(
            "scripts.bronze_odds_api_ingestion.BRONZE_DIR",
            str(tmp_path / "odds_api" / "snapshots"),
        )

        exit_code = run(api_key="test_key", dry_run=True)
        assert exit_code == 0
        assert list(tmp_path.rglob("*.parquet")) == []

    def test_january_game_season_inference_in_full_pipeline(self, tmp_path, monkeypatch):
        """January game (playoff) should partition into season=YYYY-1 directory."""
        jan_game = {
            "id": "playoff123",
            "commence_time": "2027-01-19T21:05:00Z",
            "home_team": "Kansas City Chiefs",
            "away_team": "Buffalo Bills",
            "bookmakers": [
                {
                    "key": "fanduel",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Kansas City Chiefs", "price": -115, "point": -2.5},
                                {"name": "Buffalo Bills", "price": -105, "point": 2.5},
                            ],
                        }
                    ],
                }
            ],
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [jan_game]
        mock_resp.headers = {}
        monkeypatch.setattr("scripts.bronze_odds_api_ingestion.requests.get",
                            lambda *a, **kw: mock_resp)
        monkeypatch.setattr(
            "scripts.bronze_odds_api_ingestion.BRONZE_DIR",
            str(tmp_path / "odds_api" / "snapshots"),
        )

        run(api_key="test_key", dry_run=False)

        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert len(parquet_files) == 1
        # The playoff game (Jan 2027) belongs to the 2026 season
        assert "season=2026" in str(parquet_files[0])


# ---------------------------------------------------------------------------
# validate_config tests
# ---------------------------------------------------------------------------

class TestValidateConfig:
    """Config validator."""

    def test_returns_false_when_key_missing(self, monkeypatch):
        monkeypatch.delenv("ODDS_API_KEY", raising=False)
        result = validate_config()
        assert result is False

    def test_returns_true_when_key_present(self, monkeypatch):
        monkeypatch.setenv("ODDS_API_KEY", "test123")
        result = validate_config()
        assert result is True
