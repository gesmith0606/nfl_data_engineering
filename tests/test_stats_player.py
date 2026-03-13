"""Tests for stats_player adapter (2025+ player data via nflverse stats_player tag)."""

import io
import os
from unittest.mock import MagicMock, patch

import pandas as pd

from src.config import STATS_PLAYER_COLUMN_MAP, STATS_PLAYER_MIN_SEASON


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_stats_player_weekly_df(season: int = 2025) -> pd.DataFrame:
    """Build a 10-row mock DataFrame mimicking the stats_player_week schema.

    Contains the *new* column names (before mapping) plus a handful of
    representative counting-stat columns used in aggregation.

    Layout: 3 QBs (KC weeks 1-3), 3 RBs (KC weeks 1-2 + BUF week 3),
    4 WRs (BUF weeks 1-4) -- 10 rows total.
    """
    n = 10
    return pd.DataFrame({
        "player_id": (
            ["QB01"] * 3 + ["RB01"] * 2 + ["RB02"] + ["WR01"] * 2 + ["WR02"] * 2
        ),
        "player_name": (
            ["P Mahomes"] * 3 + ["I Pacheco"] * 2 + ["J Cook"]
            + ["S Diggs"] * 2 + ["G Davis"] * 2
        ),
        "player_display_name": (
            ["Patrick Mahomes"] * 3 + ["Isiah Pacheco"] * 2 + ["James Cook"]
            + ["Stefon Diggs"] * 2 + ["Gabe Davis"] * 2
        ),
        "position": ["QB"] * 3 + ["RB"] * 3 + ["WR"] * 4,
        "position_group": ["QB"] * 3 + ["RB"] * 3 + ["WR"] * 4,
        "headshot_url": ["http://img"] * n,
        # New column names that need mapping
        "team": ["KC"] * 5 + ["BUF"] * 5,
        "passing_interceptions": [1, 0, 2, 0, 0, 0, 0, 0, 0, 0],
        "sacks_suffered": [2, 1, 3, 0, 0, 0, 0, 0, 0, 0],
        "sack_yards_lost": [14, 7, 21, 0, 0, 0, 0, 0, 0, 0],
        "passing_cpoe": [3.5, 1.2, -0.5, None, None, None, None, None, None, None],
        # Standard columns present in both schemas
        "season": [season] * n,
        "week": [1, 2, 3, 1, 2, 3, 1, 2, 1, 2],
        "season_type": ["REG"] * 8 + ["POST"] * 2,
        "attempts": [30, 25, 35, 0, 0, 0, 0, 0, 0, 0],
        "completions": [20, 18, 22, 0, 0, 0, 0, 0, 0, 0],
        "passing_yards": [280, 210, 350, 0, 0, 0, 0, 0, 0, 0],
        "passing_tds": [2, 1, 3, 0, 0, 0, 0, 0, 0, 0],
        "carries": [0, 0, 0, 15, 12, 18, 0, 0, 0, 0],
        "rushing_yards": [0, 0, 0, 75, 60, 90, 0, 0, 0, 0],
        "rushing_tds": [0, 0, 0, 1, 0, 2, 0, 0, 0, 0],
        "receptions": [0, 0, 0, 2, 3, 1, 5, 7, 6, 4],
        "targets": [0, 0, 0, 3, 4, 2, 8, 10, 9, 6],
        "receiving_yards": [0, 0, 0, 15, 25, 10, 70, 95, 80, 50],
        "receiving_tds": [0, 0, 0, 0, 1, 0, 1, 2, 1, 0],
        "receiving_air_yards": [0, 0, 0, 5, 8, 3, 30, 40, 35, 20],
        "receiving_yards_after_catch": [0, 0, 0, 10, 17, 7, 40, 55, 45, 30],
        "receiving_first_downs": [0, 0, 0, 1, 2, 0, 3, 5, 4, 2],
        "receiving_epa": [0.0, 0.0, 0.0, 0.5, 1.2, -0.3, 2.1, 3.5, 2.8, 1.0],
        "receiving_2pt_conversions": [0] * n,
        "rushing_fumbles": [0] * n,
        "rushing_fumbles_lost": [0] * n,
        "rushing_first_downs": [0, 0, 0, 3, 2, 4, 0, 0, 0, 0],
        "rushing_epa": [0.0, 0.0, 0.0, 1.5, 0.8, 2.3, 0.0, 0.0, 0.0, 0.0],
        "rushing_2pt_conversions": [0] * n,
        "receiving_fumbles": [0] * n,
        "receiving_fumbles_lost": [0] * n,
        "sack_fumbles": [0] * n,
        "sack_fumbles_lost": [0] * n,
        "passing_air_yards": [40, 35, 50, 0, 0, 0, 0, 0, 0, 0],
        "passing_yards_after_catch": [20, 15, 25, 0, 0, 0, 0, 0, 0, 0],
        "passing_first_downs": [10, 8, 12, 0, 0, 0, 0, 0, 0, 0],
        "passing_epa": [5.0, 3.0, 8.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "passing_2pt_conversions": [0] * n,
        "special_teams_tds": [0] * n,
        "fantasy_points": [15.0, 10.0, 20.0, 12.0, 10.0, 16.0, 8.0, 12.5, 10.5, 6.0],
        "fantasy_points_ppr": [15.0, 10.0, 20.0, 14.0, 13.0, 17.0, 13.0, 19.5, 16.5, 10.0],
    })


# ---------------------------------------------------------------------------
# Task 1 Tests: Config constants and column mapping
# ---------------------------------------------------------------------------

class TestConfigConstants:
    """Verify stats_player config constants exist and have correct values."""

    def test_min_season_equals_2025(self):
        assert STATS_PLAYER_MIN_SEASON == 2025

    def test_column_map_has_all_five_renames(self):
        expected_keys = {
            "passing_interceptions",
            "sacks_suffered",
            "sack_yards_lost",
            "team",
            "passing_cpoe",
        }
        assert set(STATS_PLAYER_COLUMN_MAP.keys()) == expected_keys

    def test_column_map_target_names(self):
        assert STATS_PLAYER_COLUMN_MAP["passing_interceptions"] == "interceptions"
        assert STATS_PLAYER_COLUMN_MAP["sacks_suffered"] == "sacks"
        assert STATS_PLAYER_COLUMN_MAP["sack_yards_lost"] == "sack_yards"
        assert STATS_PLAYER_COLUMN_MAP["team"] == "recent_team"
        assert STATS_PLAYER_COLUMN_MAP["passing_cpoe"] == "dakota"


class TestColumnMapping:
    """Verify column mapping applied to a DataFrame renames correctly."""

    def test_rename_all_five_columns(self):
        df = _make_stats_player_weekly_df()
        mapped = df.rename(columns=STATS_PLAYER_COLUMN_MAP)

        # Old (new-schema) names should be gone
        assert "passing_interceptions" not in mapped.columns
        assert "sacks_suffered" not in mapped.columns
        assert "sack_yards_lost" not in mapped.columns
        assert "team" not in mapped.columns
        assert "passing_cpoe" not in mapped.columns

        # Backward-compatible names should be present
        assert "interceptions" in mapped.columns
        assert "sacks" in mapped.columns
        assert "sack_yards" in mapped.columns
        assert "recent_team" in mapped.columns
        assert "dakota" in mapped.columns

    def test_mapping_preserves_values(self):
        df = _make_stats_player_weekly_df()
        original_ints = df["passing_interceptions"].tolist()
        mapped = df.rename(columns=STATS_PLAYER_COLUMN_MAP)
        assert mapped["interceptions"].tolist() == original_ints


class TestRoutingLogic:
    """Verify season routing based on STATS_PLAYER_MIN_SEASON threshold."""

    def test_seasons_below_threshold_not_routed_to_stats_player(self):
        """Seasons < 2025 should go through old nfl.import_weekly_data path."""
        seasons = [2022, 2023, 2024]
        old = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]
        assert old == [2022, 2023, 2024]
        assert new == []

    def test_seasons_at_threshold_routed_to_stats_player(self):
        """Season 2025 should go through stats_player path."""
        seasons = [2025]
        old = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]
        assert old == []
        assert new == [2025]

    def test_mixed_seasons_split_correctly(self):
        """Mixed list should split at the threshold."""
        seasons = [2023, 2024, 2025, 2026]
        old = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]
        assert old == [2023, 2024]
        assert new == [2025, 2026]


# ---------------------------------------------------------------------------
# Helpers for Task 2 tests
# ---------------------------------------------------------------------------

def _mock_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to in-memory Parquet bytes for mock HTTP responses."""
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


def _make_urlopen_mock(parquet_bytes: bytes) -> MagicMock:
    """Create a mock that mimics urllib.request.urlopen context manager."""
    resp = MagicMock()
    resp.read.return_value = parquet_bytes
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# Task 2 Tests: Adapter methods and conditional routing
# ---------------------------------------------------------------------------

class TestFetchStatsPlayer:
    """Tests for NFLDataAdapter._fetch_stats_player()."""

    def test_downloads_and_applies_column_mapping(self):
        """_fetch_stats_player returns DataFrame with old column names."""
        from src.nfl_data_adapter import NFLDataAdapter

        raw_df = _make_stats_player_weekly_df()
        mock_resp = _make_urlopen_mock(_mock_parquet_bytes(raw_df))

        adapter = NFLDataAdapter()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = adapter._fetch_stats_player(2025)

        assert not result.empty
        # Mapped columns present
        assert "interceptions" in result.columns
        assert "sacks" in result.columns
        assert "sack_yards" in result.columns
        assert "recent_team" in result.columns
        assert "dakota" in result.columns
        # Original new-schema names gone
        assert "passing_interceptions" not in result.columns
        assert "sacks_suffered" not in result.columns
        assert "team" not in result.columns

    def test_uses_github_token_when_set(self):
        """Auth header set when GITHUB_TOKEN env var present."""
        from src.nfl_data_adapter import NFLDataAdapter

        raw_df = _make_stats_player_weekly_df()
        mock_resp = _make_urlopen_mock(_mock_parquet_bytes(raw_df))

        adapter = NFLDataAdapter()
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"}, clear=False):
            with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
                adapter._fetch_stats_player(2025)

                # Inspect the Request object passed to urlopen
                call_args = mock_url.call_args
                req = call_args[0][0]
                assert req.get_header("Authorization") == "token ghp_test123"

    def test_falls_back_without_token(self):
        """No auth header when GITHUB_TOKEN not set; logs warning."""
        from src.nfl_data_adapter import NFLDataAdapter

        raw_df = _make_stats_player_weekly_df()
        mock_resp = _make_urlopen_mock(_mock_parquet_bytes(raw_df))

        adapter = NFLDataAdapter()
        env = {k: v for k, v in os.environ.items()
               if k not in ("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN")}
        with patch.dict(os.environ, env, clear=True):
            with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
                result = adapter._fetch_stats_player(2025)

                req = mock_url.call_args[0][0]
                assert not req.has_header("Authorization")
                assert not result.empty

    def test_returns_empty_on_http_error(self):
        """HTTP errors return empty DataFrame (matches _safe_call pattern)."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        with patch("urllib.request.urlopen", side_effect=Exception("HTTP 404")):
            result = adapter._fetch_stats_player(2025)

        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestFetchWeeklyDataRouting:
    """Tests for conditional routing in fetch_weekly_data."""

    def test_2025_delegates_to_stats_player(self):
        """fetch_weekly_data([2025]) should call _fetch_stats_player."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        mock_df = _make_stats_player_weekly_df().rename(
            columns=STATS_PLAYER_COLUMN_MAP
        )

        with patch.object(adapter, "_fetch_stats_player", return_value=mock_df) as mock_fetch:
            result = adapter.fetch_weekly_data([2025])

        mock_fetch.assert_called_once_with(2025)
        assert not result.empty

    def test_2024_delegates_to_import_weekly_data(self):
        """fetch_weekly_data([2024]) should NOT call _fetch_stats_player."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        mock_df = pd.DataFrame({"player_id": ["A"], "season": [2024]})

        with patch.object(adapter, "_fetch_stats_player") as mock_sp:
            with patch.object(adapter, "_import_nfl") as mock_nfl:
                mock_nfl_mod = MagicMock()
                mock_nfl_mod.import_weekly_data.return_value = mock_df
                mock_nfl.return_value = mock_nfl_mod
                adapter.fetch_weekly_data([2024])

        mock_sp.assert_not_called()
        mock_nfl_mod.import_weekly_data.assert_called_once()

    def test_mixed_seasons_splits_and_concatenates(self):
        """fetch_weekly_data([2024, 2025]) uses both paths and concats."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        old_df = pd.DataFrame({"player_id": ["OLD1"], "season": [2024]})
        new_df = pd.DataFrame({"player_id": ["NEW1"], "season": [2025]})

        with patch.object(adapter, "_fetch_stats_player", return_value=new_df) as mock_sp:
            with patch.object(adapter, "_import_nfl") as mock_nfl:
                mock_nfl_mod = MagicMock()
                mock_nfl_mod.import_weekly_data.return_value = old_df
                mock_nfl.return_value = mock_nfl_mod
                result = adapter.fetch_weekly_data([2024, 2025])

        mock_sp.assert_called_once_with(2025)
        assert len(result) == 2
        assert set(result["season"].tolist()) == {2024, 2025}


class TestAggregateSeasonalFromWeekly:
    """Tests for _aggregate_seasonal_from_weekly."""

    def test_produces_correct_schema_with_games(self):
        """Aggregated seasonal has games column and sum columns."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        weekly = _make_stats_player_weekly_df()
        # Apply column mapping first (as the real flow does)
        weekly = weekly.rename(columns=STATS_PLAYER_COLUMN_MAP)

        result = adapter._aggregate_seasonal_from_weekly(weekly)

        assert "games" in result.columns
        assert "season_type" in result.columns
        # All seasonal share columns should be present
        for col in ["tgt_sh", "ay_sh", "ry_sh"]:
            assert col in result.columns, f"Missing share column: {col}"

    def test_filters_to_reg_only(self):
        """Only REG season_type rows included in aggregation."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        weekly = _make_stats_player_weekly_df()
        weekly = weekly.rename(columns=STATS_PLAYER_COLUMN_MAP)

        result = adapter._aggregate_seasonal_from_weekly(weekly)

        # POST rows from fixture should be excluded
        assert (result["season_type"] == "REG").all()

    def test_games_count_from_distinct_weeks(self):
        """games column equals distinct week count per player in REG."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        weekly = _make_stats_player_weekly_df()
        weekly = weekly.rename(columns=STATS_PLAYER_COLUMN_MAP)

        result = adapter._aggregate_seasonal_from_weekly(weekly)

        # QB01 has weeks 1,2,3 all REG -> 3 games
        qb_row = result[result["player_id"] == "QB01"]
        assert len(qb_row) == 1
        assert qb_row.iloc[0]["games"] == 3


class TestFetchSeasonalDataRouting:
    """Tests for conditional routing in fetch_seasonal_data."""

    def test_2025_delegates_to_aggregation(self):
        """fetch_seasonal_data([2025]) should use _fetch_stats_player + aggregation."""
        from src.nfl_data_adapter import NFLDataAdapter

        adapter = NFLDataAdapter()
        weekly_mapped = _make_stats_player_weekly_df().rename(
            columns=STATS_PLAYER_COLUMN_MAP
        )
        seasonal_mock = pd.DataFrame({"player_id": ["A"], "games": [3]})

        with patch.object(adapter, "_fetch_stats_player", return_value=weekly_mapped):
            with patch.object(
                adapter, "_aggregate_seasonal_from_weekly", return_value=seasonal_mock
            ) as mock_agg:
                result = adapter.fetch_seasonal_data([2025])

        mock_agg.assert_called_once()
        assert not result.empty
