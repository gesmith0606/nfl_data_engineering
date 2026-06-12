"""Tests for odds_snapshot_loader — Bronze Parquet snapshot → open/close lines.

Synthetic-fixture test path: fabricated snapshot Parquet files covering:
  - Normal case: multiple books, multiple snapshots → correct open/close consensus
  - Missing-book case: only one book present for open, two for close
  - Line-move case: line moves significantly between open and close
  - No-pre-kickoff-snapshot case: all snapshots are after commence_time
  - Empty snapshot directory
  - Missing season directory
  - Mixed market rows filtered correctly
  - Consensus median across bookmakers
  - Totals market (open_total / close_total)
  - Season inference / partition directories
  - Timestamp coercion edge cases
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from odds_snapshot_loader import (
    load_open_close_lines,
    _load_season_snapshots,
    _coerce_timestamps,
    _derive_open_close,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _utc_iso(dt: datetime) -> str:
    """Format a datetime as ISO-8601 UTC string (Z suffix)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_snapshot_df(
    games: list,
    snapshot_ts: str,
) -> pd.DataFrame:
    """Build a snapshot DataFrame from a list of game dicts.

    Each game dict may have keys:
        game_id_ext, commence_time, home_team_nfl, away_team_nfl,
        bookmaker, market, home_spread (or total_points), season.
    """
    rows = []
    for g in games:
        row = {
            "snapshot_ts": snapshot_ts,
            "game_id_ext": g.get("game_id_ext", "game_001"),
            "commence_time": g.get("commence_time", "2026-09-10T20:00:00Z"),
            "home_team": g.get("home_team", "Kansas City Chiefs"),
            "away_team": g.get("away_team", "Baltimore Ravens"),
            "home_team_nfl": g.get("home_team_nfl", "KC"),
            "away_team_nfl": g.get("away_team_nfl", "BAL"),
            "bookmaker": g.get("bookmaker", "fanduel"),
            "market": g.get("market", "spreads"),
            "home_spread": g.get("home_spread", None),
            "total_points": g.get("total_points", None),
            "price_home": g.get("price_home", -110),
            "price_away": g.get("price_away", -110),
            "season": g.get("season", 2026),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _write_snapshot(df: pd.DataFrame, season_dir: str, filename: str) -> str:
    """Write a snapshot DataFrame to a Parquet file in the given directory."""
    os.makedirs(season_dir, exist_ok=True)
    path = os.path.join(season_dir, filename)
    df.to_parquet(path, index=False)
    return path


def _season_dir(root: str, season: int) -> str:
    """Return the season partition directory path."""
    return os.path.join(root, f"season={season}")


# ---------------------------------------------------------------------------
# Normal case: multiple books, multiple snapshots
# ---------------------------------------------------------------------------

class TestNormalCase:
    """Standard capture: 2 snapshots × 2 books → correct open/close consensus."""

    def test_spread_open_close_consensus(self, tmp_path):
        """Median across 2 books; first snapshot is open, last is close."""
        commence = "2026-09-10T20:00:00Z"
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)

        # Open snapshot (08:00 UTC — morning)
        open_ts = "2026-09-10T08:00:00Z"
        open_games = [
            {"bookmaker": "fanduel",  "home_spread": -3.5, "home_team_nfl": "KC",
             "away_team_nfl": "BAL", "commence_time": commence, "market": "spreads", "season": season},
            {"bookmaker": "draftkings", "home_spread": -4.0, "home_team_nfl": "KC",
             "away_team_nfl": "BAL", "commence_time": commence, "market": "spreads", "season": season},
        ]
        _write_snapshot(_make_snapshot_df(open_games, open_ts), sdir, "odds_20260910_080000.parquet")

        # Close snapshot (19:00 UTC — evening)
        close_ts = "2026-09-10T19:00:00Z"
        close_games = [
            {"bookmaker": "fanduel",  "home_spread": -5.0, "home_team_nfl": "KC",
             "away_team_nfl": "BAL", "commence_time": commence, "market": "spreads", "season": season},
            {"bookmaker": "draftkings", "home_spread": -5.5, "home_team_nfl": "KC",
             "away_team_nfl": "BAL", "commence_time": commence, "market": "spreads", "season": season},
        ]
        _write_snapshot(_make_snapshot_df(close_games, close_ts), sdir, "odds_20260910_190000.parquet")

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)

        assert len(result) == 1
        row = result.iloc[0]
        # Open consensus: median(-3.5, -4.0) = -3.75
        assert abs(row["open_spread"] - (-3.75)) < 1e-9
        # Close consensus: median(-5.0, -5.5) = -5.25
        assert abs(row["close_spread"] - (-5.25)) < 1e-9
        assert row["n_books_open"] == 2
        assert row["n_books_close"] == 2

    def test_spread_columns_present(self, tmp_path):
        """Result has all expected spread columns."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        ts = "2026-09-10T08:00:00Z"
        games = [{"bookmaker": "fanduel", "home_spread": -3.5, "home_team_nfl": "KC",
                  "away_team_nfl": "BAL", "commence_time": "2026-09-10T20:00:00Z",
                  "market": "spreads", "season": season}]
        _write_snapshot(_make_snapshot_df(games, ts), sdir, "odds_001.parquet")

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)
        for col in ["home_team_nfl", "away_team_nfl", "commence_time",
                    "open_spread", "close_spread", "n_books_open", "n_books_close"]:
            assert col in result.columns

    def test_totals_market(self, tmp_path):
        """Totals market returns open_total/close_total columns."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        commence = "2026-09-10T20:00:00Z"

        ts1 = "2026-09-10T08:00:00Z"
        ts2 = "2026-09-10T19:00:00Z"
        games1 = [{"bookmaker": "fanduel", "total_points": 45.5, "home_team_nfl": "KC",
                   "away_team_nfl": "BAL", "commence_time": commence,
                   "market": "totals", "season": season}]
        games2 = [{"bookmaker": "fanduel", "total_points": 47.0, "home_team_nfl": "KC",
                   "away_team_nfl": "BAL", "commence_time": commence,
                   "market": "totals", "season": season}]
        _write_snapshot(_make_snapshot_df(games1, ts1), sdir, "odds_001.parquet")
        _write_snapshot(_make_snapshot_df(games2, ts2), sdir, "odds_002.parquet")

        result = load_open_close_lines(season=season, market="totals", snapshot_dir=root)
        assert len(result) == 1
        row = result.iloc[0]
        assert abs(row["open_total"] - 45.5) < 1e-9
        assert abs(row["close_total"] - 47.0) < 1e-9

    def test_totals_columns_present(self, tmp_path):
        """Totals result has open_total, close_total columns."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        ts = "2026-09-10T08:00:00Z"
        games = [{"bookmaker": "fanduel", "total_points": 45.5, "home_team_nfl": "KC",
                  "away_team_nfl": "BAL", "commence_time": "2026-09-10T20:00:00Z",
                  "market": "totals", "season": season}]
        _write_snapshot(_make_snapshot_df(games, ts), sdir, "odds_001.parquet")

        result = load_open_close_lines(season=season, market="totals", snapshot_dir=root)
        for col in ["home_team_nfl", "away_team_nfl", "commence_time",
                    "open_total", "close_total", "n_books_open", "n_books_close"]:
            assert col in result.columns


# ---------------------------------------------------------------------------
# Missing-book case: unequal book counts across open/close
# ---------------------------------------------------------------------------

class TestMissingBookCase:
    """Consensus still computed when book counts differ between open and close."""

    def test_single_book_open_two_books_close(self, tmp_path):
        """Open has 1 book, close has 2 books — both consensuses are valid."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        commence = "2026-09-10T20:00:00Z"

        ts_open = "2026-09-10T08:00:00Z"
        open_games = [
            {"bookmaker": "fanduel", "home_spread": -3.5, "home_team_nfl": "KC",
             "away_team_nfl": "BAL", "commence_time": commence, "market": "spreads", "season": season},
        ]
        _write_snapshot(_make_snapshot_df(open_games, ts_open), sdir, "odds_open.parquet")

        ts_close = "2026-09-10T19:00:00Z"
        close_games = [
            {"bookmaker": "fanduel",   "home_spread": -5.0, "home_team_nfl": "KC",
             "away_team_nfl": "BAL", "commence_time": commence, "market": "spreads", "season": season},
            {"bookmaker": "draftkings","home_spread": -4.5, "home_team_nfl": "KC",
             "away_team_nfl": "BAL", "commence_time": commence, "market": "spreads", "season": season},
        ]
        _write_snapshot(_make_snapshot_df(close_games, ts_close), sdir, "odds_close.parquet")

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)
        assert len(result) == 1
        row = result.iloc[0]
        assert abs(row["open_spread"] - (-3.5)) < 1e-9   # single book
        assert row["n_books_open"] == 1
        # close = median(-5.0, -4.5) = -4.75
        assert abs(row["close_spread"] - (-4.75)) < 1e-9
        assert row["n_books_close"] == 2


# ---------------------------------------------------------------------------
# Line-move case: large spread movement
# ---------------------------------------------------------------------------

class TestLineMoveCase:
    """Large spread movement is captured accurately."""

    def test_large_line_move_preserved(self, tmp_path):
        """Line moving from -3.0 to -8.0 (e.g., starting QB announced out) is preserved."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        commence = "2026-09-10T20:00:00Z"

        ts_open = "2026-09-10T06:00:00Z"
        ts_close = "2026-09-10T19:30:00Z"

        for ts, spread, fname in [
            (ts_open, -3.0, "odds_open.parquet"),
            (ts_close, -8.0, "odds_close.parquet"),
        ]:
            games = [{"bookmaker": "fanduel", "home_spread": spread, "home_team_nfl": "KC",
                      "away_team_nfl": "BAL", "commence_time": commence,
                      "market": "spreads", "season": season}]
            _write_snapshot(_make_snapshot_df(games, ts), sdir, fname)

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)
        row = result.iloc[0]
        assert abs(row["open_spread"] - (-3.0)) < 1e-9
        assert abs(row["close_spread"] - (-8.0)) < 1e-9

    def test_line_move_of_half_point(self, tmp_path):
        """Half-point line move is preserved exactly."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        commence = "2026-09-10T20:00:00Z"

        for ts, spread, fname in [
            ("2026-09-10T08:00:00Z", -6.5, "odds_open.parquet"),
            ("2026-09-10T19:00:00Z", -7.0, "odds_close.parquet"),
        ]:
            games = [{"bookmaker": "fanduel", "home_spread": spread, "home_team_nfl": "KC",
                      "away_team_nfl": "BAL", "commence_time": commence,
                      "market": "spreads", "season": season}]
            _write_snapshot(_make_snapshot_df(games, ts), sdir, fname)

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)
        row = result.iloc[0]
        assert abs(row["open_spread"] - (-6.5)) < 1e-9
        assert abs(row["close_spread"] - (-7.0)) < 1e-9


# ---------------------------------------------------------------------------
# No-pre-kickoff-snapshot case
# ---------------------------------------------------------------------------

class TestNoPreKickoffSnapshot:
    """When all snapshots are after commence_time, open/close are NaN."""

    def test_all_post_kickoff_snapshots_yield_nan(self, tmp_path):
        """Snapshots taken after kickoff are excluded; open/close should be NaN."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        commence = "2026-09-10T20:00:00Z"

        # Both snapshots are AFTER kickoff
        for ts, fname in [
            ("2026-09-10T21:00:00Z", "odds_post1.parquet"),
            ("2026-09-10T22:00:00Z", "odds_post2.parquet"),
        ]:
            games = [{"bookmaker": "fanduel", "home_spread": -3.5, "home_team_nfl": "KC",
                      "away_team_nfl": "BAL", "commence_time": commence,
                      "market": "spreads", "season": season}]
            _write_snapshot(_make_snapshot_df(games, ts), sdir, fname)

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)
        # Game row exists but open/close are NaN
        assert len(result) == 1
        row = result.iloc[0]
        import numpy as np
        assert np.isnan(row["open_spread"])
        assert np.isnan(row["close_spread"])
        assert row["n_books_open"] == 0
        assert row["n_books_close"] == 0

    def test_mixed_pre_and_post_kickoff(self, tmp_path):
        """Only pre-kickoff snapshots are used; post-kickoff are excluded."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        commence = "2026-09-10T20:00:00Z"

        snapshots = [
            ("2026-09-10T08:00:00Z", -3.5, "odds_open.parquet"),    # pre-kick
            ("2026-09-10T19:00:00Z", -4.5, "odds_close.parquet"),   # pre-kick
            ("2026-09-10T21:00:00Z", -2.0, "odds_post.parquet"),    # post-kick (should be ignored)
        ]
        for ts, spread, fname in snapshots:
            games = [{"bookmaker": "fanduel", "home_spread": spread, "home_team_nfl": "KC",
                      "away_team_nfl": "BAL", "commence_time": commence,
                      "market": "spreads", "season": season}]
            _write_snapshot(_make_snapshot_df(games, ts), sdir, fname)

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)
        row = result.iloc[0]
        # Close should be the 19:00 snapshot (-4.5), NOT the post-kick -2.0
        assert abs(row["open_spread"] - (-3.5)) < 1e-9
        assert abs(row["close_spread"] - (-4.5)) < 1e-9


# ---------------------------------------------------------------------------
# Empty / missing data cases
# ---------------------------------------------------------------------------

class TestEmptyMissingData:
    """Empty directories and missing seasons return empty DataFrames."""

    def test_empty_directory_returns_empty_df_with_spread_schema(self, tmp_path):
        """Non-existent season directory → empty DataFrame with spread columns."""
        root = str(tmp_path / "snapshots")
        result = load_open_close_lines(season=2026, market="spreads", snapshot_dir=root)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert "open_spread" in result.columns
        assert "close_spread" in result.columns

    def test_empty_directory_returns_empty_df_with_total_schema(self, tmp_path):
        """Non-existent season directory → empty DataFrame with totals columns."""
        root = str(tmp_path / "snapshots")
        result = load_open_close_lines(season=2026, market="totals", snapshot_dir=root)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert "open_total" in result.columns
        assert "close_total" in result.columns

    def test_season_dir_exists_but_empty_returns_empty_df(self, tmp_path):
        """Season directory exists but has no parquet files → empty DataFrame."""
        root = str(tmp_path / "snapshots")
        os.makedirs(os.path.join(root, "season=2026"), exist_ok=True)
        result = load_open_close_lines(season=2026, market="spreads", snapshot_dir=root)
        assert len(result) == 0

    def test_invalid_market_raises_value_error(self, tmp_path):
        """Unknown market raises ValueError immediately."""
        root = str(tmp_path / "snapshots")
        with pytest.raises(ValueError, match="market"):
            load_open_close_lines(season=2026, market="moneyline", snapshot_dir=root)

    def test_wrong_market_filter_returns_empty(self, tmp_path):
        """Snapshot files contain only spreads; requesting totals → empty result."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        ts = "2026-09-10T08:00:00Z"
        games = [{"bookmaker": "fanduel", "home_spread": -3.5, "home_team_nfl": "KC",
                  "away_team_nfl": "BAL", "commence_time": "2026-09-10T20:00:00Z",
                  "market": "spreads", "season": season}]
        _write_snapshot(_make_snapshot_df(games, ts), sdir, "odds_001.parquet")

        result = load_open_close_lines(season=season, market="totals", snapshot_dir=root)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Multiple games in the same snapshot
# ---------------------------------------------------------------------------

class TestMultipleGames:
    """Multiple games per snapshot file are handled correctly."""

    def test_two_games_produce_two_rows(self, tmp_path):
        """Two separate game_id_ext values produce two output rows."""
        season = 2026
        root = str(tmp_path / "snapshots")
        sdir = _season_dir(root, season)
        ts = "2026-09-10T08:00:00Z"
        games = [
            {"game_id_ext": "game_001", "bookmaker": "fanduel", "home_spread": -3.5,
             "home_team_nfl": "KC", "away_team_nfl": "BAL",
             "commence_time": "2026-09-10T20:00:00Z", "market": "spreads", "season": season},
            {"game_id_ext": "game_002", "bookmaker": "fanduel", "home_spread": -7.0,
             "home_team_nfl": "SF", "away_team_nfl": "SEA",
             "commence_time": "2026-09-10T23:00:00Z", "market": "spreads", "season": season},
        ]
        _write_snapshot(_make_snapshot_df(games, ts), sdir, "odds_001.parquet")

        result = load_open_close_lines(season=season, market="spreads", snapshot_dir=root)
        assert len(result) == 2
        teams = set(zip(result["home_team_nfl"], result["away_team_nfl"]))
        assert ("KC", "BAL") in teams
        assert ("SF", "SEA") in teams


# ---------------------------------------------------------------------------
# _load_season_snapshots unit tests
# ---------------------------------------------------------------------------

class TestLoadSeasonSnapshots:
    """Unit tests for the internal snapshot loader."""

    def test_returns_empty_df_for_missing_dir(self, tmp_path):
        """Non-existent directory → empty DataFrame."""
        df = _load_season_snapshots(str(tmp_path / "nope"), 2026)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_concatenates_multiple_files(self, tmp_path):
        """Multiple parquet files are concatenated into one DataFrame."""
        sdir = str(tmp_path / "season=2026")
        os.makedirs(sdir, exist_ok=True)
        season = 2026
        for i, ts in enumerate(["2026-09-10T08:00:00Z", "2026-09-10T19:00:00Z"]):
            games = [{"bookmaker": "fanduel", "home_spread": -3.5 - i,
                      "home_team_nfl": "KC", "away_team_nfl": "BAL",
                      "commence_time": "2026-09-10T20:00:00Z",
                      "market": "spreads", "season": season}]
            df = _make_snapshot_df(games, ts)
            df.to_parquet(os.path.join(sdir, f"odds_{i:03d}.parquet"), index=False)

        result = _load_season_snapshots(str(tmp_path), 2026)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _coerce_timestamps unit tests
# ---------------------------------------------------------------------------

class TestCoerceTimestamps:
    """Unit tests for ISO-8601 timestamp coercion."""

    def test_z_suffix_parsed(self):
        """Timestamps with Z suffix are parsed to timezone-aware datetime."""
        df = pd.DataFrame({
            "snapshot_ts": ["2026-09-10T08:00:00Z"],
            "commence_time": ["2026-09-10T20:00:00Z"],
        })
        result = _coerce_timestamps(df)
        assert pd.api.types.is_datetime64_any_dtype(result["snapshot_ts"])
        assert result["snapshot_ts"].dt.tz is not None

    def test_plus_utc_suffix_parsed(self):
        """Timestamps with +00:00 suffix are parsed."""
        df = pd.DataFrame({
            "snapshot_ts": ["2026-09-10T08:00:00+00:00"],
            "commence_time": ["2026-09-10T20:00:00+00:00"],
        })
        result = _coerce_timestamps(df)
        assert pd.api.types.is_datetime64_any_dtype(result["snapshot_ts"])

    def test_empty_dataframe_is_safe(self):
        """Empty DataFrame is returned as-is."""
        df = pd.DataFrame({
            "snapshot_ts": pd.Series(dtype=str),
            "commence_time": pd.Series(dtype=str),
        })
        result = _coerce_timestamps(df)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _derive_open_close unit tests
# ---------------------------------------------------------------------------

class TestDeriveOpenClose:
    """Unit tests for the per-game open/close derivation."""

    def _make_game_df(self, snap_times, spreads, commence):
        """Build a game DataFrame with the given snapshot times and spreads."""
        rows = []
        for ts, spread in zip(snap_times, spreads):
            rows.append({
                "snapshot_ts": pd.Timestamp(ts.replace("Z", "+00:00")),
                "commence_time": pd.Timestamp(commence.replace("Z", "+00:00")),
                "home_spread": spread,
                "game_id_ext": "game_001",
            })
        df = pd.DataFrame(rows)
        # Ensure timestamp columns are timezone-aware
        for col in ["snapshot_ts", "commence_time"]:
            if df[col].dt.tz is None:
                df[col] = df[col].dt.tz_localize("UTC")
        return df.sort_values("snapshot_ts")

    def test_first_and_last_snapshot_selected(self):
        """First snapshot = open-proxy, last snapshot = close."""
        ts1 = "2026-09-10T08:00:00Z"
        ts2 = "2026-09-10T14:00:00Z"
        ts3 = "2026-09-10T19:00:00Z"
        commence = "2026-09-10T20:00:00Z"
        df = self._make_game_df([ts1, ts2, ts3], [-3.5, -4.0, -5.0], commence)
        result = _derive_open_close(df, "home_spread")
        assert abs(result["open_line"] - (-3.5)) < 1e-9
        assert abs(result["close_line"] - (-5.0)) < 1e-9

    def test_single_snapshot_open_equals_close(self):
        """When only one pre-kickoff snapshot exists, open == close."""
        ts = "2026-09-10T08:00:00Z"
        commence = "2026-09-10T20:00:00Z"
        df = self._make_game_df([ts], [-4.0], commence)
        result = _derive_open_close(df, "home_spread")
        assert abs(result["open_line"] - (-4.0)) < 1e-9
        assert abs(result["close_line"] - (-4.0)) < 1e-9

    def test_no_pre_kickoff_snapshots_returns_nan(self):
        """Post-kickoff only snapshots → NaN open/close."""
        ts = "2026-09-10T21:00:00Z"  # after kickoff at 20:00
        commence = "2026-09-10T20:00:00Z"
        df = self._make_game_df([ts], [-3.5], commence)
        result = _derive_open_close(df, "home_spread")
        import numpy as np
        assert np.isnan(result["open_line"])
        assert np.isnan(result["close_line"])
        assert result["n_books_open"] == 0

    def test_empty_game_df_returns_nan(self):
        """Empty game DataFrame → NaN open/close."""
        df = pd.DataFrame({
            "snapshot_ts": pd.Series(dtype="datetime64[ns, UTC]"),
            "commence_time": pd.Series(dtype="datetime64[ns, UTC]"),
            "home_spread": pd.Series(dtype=float),
            "game_id_ext": pd.Series(dtype=str),
        })
        result = _derive_open_close(df, "home_spread")
        import numpy as np
        assert np.isnan(result["open_line"])
