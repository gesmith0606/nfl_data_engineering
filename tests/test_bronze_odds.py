"""
Tests for Bronze odds ingestion: FinnedAI JSON download, parse, map, join, validate.

Covers ODDS-01 (parse, sign convention, cross-validation, schema) and
ODDS-02 (team mapping, corrupt entries, NewYork disambiguation, zero orphans).
"""

import datetime
import os
import sys
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

# Ensure project root on path so scripts.bronze_odds_ingestion is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_odds_ingestion import (
    FINNEDAI_TO_NFLVERSE,
    align_spreads,
    download_finnedai,
    join_to_nflverse,
    parse_finnedai,
    resolve_newyork,
    validate_cross_correlation,
    validate_odds_schema,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_finnedai_json():
    """6 entries: 4 valid 2020, 1 corrupt (team=0), 1 out-of-range (2015)."""
    return [
        {
            "season": 2020,
            "date": 20200910.0,
            "home_team": "Chiefs",
            "away_team": "Texans",
            "home_open_spread": -10.0,
            "home_close_spread": -10.5,
            "open_over_under": 53.5,
            "close_over_under": 54.0,
            "home_close_ml": -350,
            "away_close_ml": 290,
            "home_final": "34",
            "away_final": "20",
        },
        {
            "season": 2020,
            "date": 20200913.0,
            "home_team": "Fortyniners",
            "away_team": "Cardinals",
            "home_open_spread": -7.5,
            "home_close_spread": -7.0,
            "open_over_under": 47.5,
            "close_over_under": 48.0,
            "home_close_ml": -300,
            "away_close_ml": 250,
            "home_final": "20",
            "away_final": "24",
        },
        {
            "season": 2020,
            "date": 20200920.0,
            "home_team": "NewYork",
            "away_team": "Bills",
            "home_open_spread": 6.0,
            "home_close_spread": 5.5,
            "open_over_under": 41.5,
            "close_over_under": 42.0,
            "home_close_ml": 200,
            "away_close_ml": -240,
            "home_final": "13",
            "away_final": "27",
        },
        {
            "season": 2020,
            "date": 20200927.0,
            "home_team": "Packers",
            "away_team": "Saints",
            "home_open_spread": -3.0,
            "home_close_spread": -3.5,
            "open_over_under": 51.0,
            "close_over_under": 52.0,
            "home_close_ml": -170,
            "away_close_ml": 150,
            "home_final": "37",
            "away_final": "30",
        },
        # Corrupt entry: team=0
        {
            "season": 2020,
            "date": 20200202.0,
            "home_team": 0,
            "away_team": 0,
            "home_open_spread": -1.5,
            "home_close_spread": -1.0,
            "open_over_under": 54.5,
            "close_over_under": 54.0,
            "home_close_ml": -120,
            "away_close_ml": 100,
            "home_final": "31",
            "away_final": "20",
        },
        # Out-of-range season
        {
            "season": 2015,
            "date": 20150910.0,
            "home_team": "Patriots",
            "away_team": "Steelers",
            "home_open_spread": -7.0,
            "home_close_spread": -7.5,
            "open_over_under": 55.0,
            "close_over_under": 55.5,
            "home_close_ml": -300,
            "away_close_ml": 250,
            "home_final": "28",
            "away_final": "21",
        },
    ]


@pytest.fixture
def mock_nflverse_schedule():
    """nflverse schedule rows matching mock FinnedAI entries."""
    return pd.DataFrame(
        {
            "game_id": [
                "2020_01_HOU_KC",
                "2020_01_ARI_SF",
                "2020_02_BUF_NYJ",
                "2020_02_BUF_NYG",
                "2020_03_NO_GB",
            ],
            "season": [2020, 2020, 2020, 2020, 2020],
            "week": [1, 1, 2, 2, 3],
            "game_type": ["REG", "REG", "REG", "REG", "REG"],
            "home_team": ["KC", "SF", "NYJ", "NYG", "GB"],
            "away_team": ["HOU", "ARI", "BUF", "BUF", "NO"],
            "gameday": [
                "2020-09-10",
                "2020-09-13",
                "2020-09-20",
                "2020-09-20",
                "2020-09-27",
            ],
            "spread_line": [10.5, 7.0, -5.5, 3.0, 3.5],
            "total_line": [54.0, 48.0, 42.0, 44.0, 52.0],
        }
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestTeamMapping:
    """ODDS-02: Team name mapping tests."""

    def test_team_mapping_complete(self):
        """All 44 known FinnedAI names are in the mapping dict."""
        assert len(FINNEDAI_TO_NFLVERSE) >= 44

        # All values except NewYork should be valid 2-3 char strings
        for name, abbr in FINNEDAI_TO_NFLVERSE.items():
            if name == "NewYork":
                assert abbr is None, "NewYork should map to None (ambiguous)"
            else:
                assert isinstance(abbr, str), f"{name} maps to non-string {abbr}"
                assert 2 <= len(abbr) <= 3, f"{name} maps to invalid abbr '{abbr}'"

        # Spot-check known mappings
        assert FINNEDAI_TO_NFLVERSE["Packers"] == "GB"
        assert FINNEDAI_TO_NFLVERSE["Fortyniners"] == "SF"
        assert FINNEDAI_TO_NFLVERSE["Washingtom"] == "WAS"
        assert FINNEDAI_TO_NFLVERSE["KCChiefs"] == "KC"
        assert FINNEDAI_TO_NFLVERSE["LVRaiders"] == "LV"


class TestParsing:
    """ODDS-01 / ODDS-02: Parsing and filtering tests."""

    def test_corrupt_entries_dropped(self, mock_finnedai_json, tmp_path):
        """parse_finnedai drops corrupt team=0 entries."""
        import json

        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(mock_finnedai_json))

        result = parse_finnedai(str(json_path), seasons=[2020])
        # 4 valid 2020 entries (corrupt team=0 dropped, out-of-range 2015 filtered)
        assert len(result) == 4, f"Expected 4 rows, got {len(result)}"

    def test_parse_finnedai(self, mock_finnedai_json, tmp_path):
        """parse_finnedai converts date float to datetime.date and maps teams."""
        import json

        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(mock_finnedai_json))

        result = parse_finnedai(str(json_path), seasons=[2020])

        # Check date conversion
        assert all(
            isinstance(d, datetime.date) for d in result["gameday"]
        ), "gameday should be datetime.date"

        # First row: 20200910.0 -> 2020-09-10
        first_date = result.iloc[0]["gameday"]
        assert first_date == datetime.date(2020, 9, 10)

        # Check team mapping (Chiefs -> KC)
        assert result.iloc[0]["home_team_nfl"] == "KC"
        assert result.iloc[0]["away_team_nfl"] == "HOU"


class TestSignConvention:
    """ODDS-01: Sign convention alignment."""

    def test_sign_convention(self):
        """align_spreads negates FinnedAI spreads to nflverse convention."""
        df = pd.DataFrame(
            {
                "home_open_spread": [-4.5],
                "home_close_spread": [-10.5],
                "open_over_under": [53.5],
                "close_over_under": [54.0],
                "home_close_ml": [-350],
                "away_close_ml": [290],
            }
        )
        result = align_spreads(df.copy())

        assert result["opening_spread"].iloc[0] == 4.5
        assert result["closing_spread"].iloc[0] == 10.5
        assert result["opening_total"].iloc[0] == 53.5
        assert result["closing_total"].iloc[0] == 54.0
        assert result["home_moneyline"].iloc[0] == -350
        assert result["away_moneyline"].iloc[0] == 290


class TestNewYorkDisambiguation:
    """ODDS-02: NewYork -> NYG/NYJ resolution."""

    def test_newyork_disambiguation(self, mock_nflverse_schedule):
        """resolve_newyork matches NewYork to correct NYJ by checking schedule."""
        # Create odds row with NewYork as home team on 2020-09-20
        odds_df = pd.DataFrame(
            {
                "season": [2020],
                "home_team": ["NewYork"],
                "away_team": ["Bills"],
                "home_team_nfl": [None],  # NewYork maps to None
                "away_team_nfl": ["BUF"],
                "gameday": [datetime.date(2020, 9, 20)],
            }
        )

        schedules = {2020: mock_nflverse_schedule}
        result = resolve_newyork(odds_df, schedules)

        # NYJ is the home team playing BUF on 2020-09-20
        assert result.iloc[0]["home_team_nfl"] == "NYJ"


class TestOutputSchema:
    """ODDS-01: Output schema validation."""

    def test_output_schema(self):
        """Final DataFrame must have all 14 required columns."""
        required = [
            "game_id",
            "season",
            "week",
            "game_type",
            "home_team",
            "away_team",
            "opening_spread",
            "closing_spread",
            "opening_total",
            "closing_total",
            "home_moneyline",
            "away_moneyline",
            "nflverse_spread_line",
            "nflverse_total_line",
        ]
        # Create a DataFrame with all required columns
        df = pd.DataFrame({col: [1] for col in required})
        # Should not raise
        validate_odds_schema(df)

    def test_schema_validation(self):
        """validate_odds_schema raises ValueError when columns missing."""
        df = pd.DataFrame({"game_id": [1], "season": [2020]})
        with pytest.raises(ValueError, match="Missing required columns"):
            validate_odds_schema(df)


class TestCrossValidation:
    """ODDS-01: Cross-validation gate."""

    def test_cross_validation_gate_passes(self):
        """validate_cross_correlation passes when r > 0.95."""
        np.random.seed(42)
        base = np.random.uniform(-14, 14, 100)
        df = pd.DataFrame(
            {
                "closing_spread": base,
                "nflverse_spread_line": base + np.random.normal(0, 0.3, 100),
            }
        )
        # Should not raise
        validate_cross_correlation(df)

    def test_cross_validation_gate_fails(self):
        """validate_cross_correlation raises ValueError when r < 0.95."""
        np.random.seed(42)
        df = pd.DataFrame(
            {
                "closing_spread": np.random.uniform(-14, 14, 100),
                "nflverse_spread_line": np.random.uniform(-14, 14, 100),
            }
        )
        with pytest.raises(ValueError):
            validate_cross_correlation(df)


class TestDownload:
    """ODDS-01: Download idempotency."""

    def test_download_idempotent(self, tmp_path):
        """download_finnedai skips download when file already exists."""
        # Create the raw dir and file
        raw_dir = tmp_path / "data" / "raw" / "sbro"
        raw_dir.mkdir(parents=True)
        existing = raw_dir / "nfl_archive_10Y.json"
        existing.write_text('["test"]')

        with patch("scripts.bronze_odds_ingestion.RAW_DIR", str(raw_dir)):
            with patch("scripts.bronze_odds_ingestion.requests") as mock_req:
                result = download_finnedai(force=False)
                mock_req.get.assert_not_called()


class TestConfigRegistration:
    """ODDS-03: Config registration."""

    def test_config_registration(self):
        """DATA_TYPE_SEASON_RANGES contains 'odds' with range 2016-2021."""
        from src.config import DATA_TYPE_SEASON_RANGES

        assert "odds" in DATA_TYPE_SEASON_RANGES
        min_season, max_fn = DATA_TYPE_SEASON_RANGES["odds"]
        assert min_season == 2016
        assert max_fn() == 2021


class TestValidateSeasonForTypeOdds:
    """ODDS-03: Season boundary validation via config."""

    def test_validate_season_for_type_odds(self):
        """validate_season_for_type returns True for 2016-2021, False outside."""
        from src.config import validate_season_for_type
        assert validate_season_for_type("odds", 2016) is True
        assert validate_season_for_type("odds", 2021) is True
        assert validate_season_for_type("odds", 2015) is False
        assert validate_season_for_type("odds", 2022) is False


class TestZeroOrphans:
    """ODDS-02: Zero orphan tolerance."""

    def test_zero_orphans(self, mock_nflverse_schedule):
        """join_to_nflverse produces zero orphan rows for properly mapped data."""
        # Create mapped odds rows matching the schedule
        odds_df = pd.DataFrame(
            {
                "season": [2020, 2020, 2020],
                "home_team_nfl": ["KC", "SF", "GB"],
                "away_team_nfl": ["HOU", "ARI", "NO"],
                "gameday": [
                    datetime.date(2020, 9, 10),
                    datetime.date(2020, 9, 13),
                    datetime.date(2020, 9, 27),
                ],
                "home_open_spread": [-10.0, -7.5, -3.0],
                "home_close_spread": [-10.5, -7.0, -3.5],
                "open_over_under": [53.5, 47.5, 51.0],
                "close_over_under": [54.0, 48.0, 52.0],
                "home_close_ml": [-350, -300, -170],
                "away_close_ml": [290, 250, 150],
            }
        )

        with patch("scripts.bronze_odds_ingestion.nfl") as mock_nfl:
            mock_nfl.import_schedules.return_value = mock_nflverse_schedule
            result = join_to_nflverse(odds_df, 2020)

        assert (
            result["game_id"].isna().sum() == 0
        ), "Every odds row must join to exactly one nflverse game"
