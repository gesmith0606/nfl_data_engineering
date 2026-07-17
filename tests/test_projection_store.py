"""Refactor-pinning tests for ``src/projection_store.py``.

Pins the canonical preseason loader contract shared by the CLI draft
co-pilot (``scripts/draft_live.py``) and the web draft + league routers:
newest-file selection, ``recent_team → team`` normalisation, the lru
read-cache (one cache story for the ~5s live-draft polling), and the
``None``-on-missing/-corrupt failure mode.
"""

from pathlib import Path

import pandas as pd
import pytest

import src.projection_store as ps


@pytest.fixture()
def preseason_root(tmp_path, monkeypatch):
    """Point the loader at a temp preseason tree and clear the read-cache."""
    pattern = str(tmp_path / "season={season}" / "*.parquet")
    monkeypatch.setattr(ps, "_PRESEASON_PATTERN", pattern)
    ps._read_preseason_parquet.cache_clear()
    yield tmp_path
    ps._read_preseason_parquet.cache_clear()


def _write(root: Path, season: int, name: str, df: pd.DataFrame) -> None:
    """Write *df* as a parquet file under the season partition."""
    season_dir = root / f"season={season}"
    season_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(season_dir / name, index=False)


class TestLoadLatestPreseason:
    def test_returns_none_when_no_files(self, preseason_root):
        assert ps.load_latest_preseason(2026) is None

    def test_picks_newest_by_filename_timestamp(self, preseason_root):
        _write(
            preseason_root,
            2026,
            "season_proj_20260101_000000.parquet",
            pd.DataFrame({"player_name": ["Old Artifact"]}),
        )
        _write(
            preseason_root,
            2026,
            "season_proj_20260601_000000.parquet",
            pd.DataFrame({"player_name": ["New Artifact"]}),
        )
        df = ps.load_latest_preseason(2026)
        assert df is not None
        assert list(df["player_name"]) == ["New Artifact"]

    def test_renames_recent_team_to_team(self, preseason_root):
        _write(
            preseason_root,
            2026,
            "season_proj_20260601_000000.parquet",
            pd.DataFrame({"player_name": ["A"], "recent_team": ["KC"]}),
        )
        df = ps.load_latest_preseason(2026)
        assert df is not None
        assert "team" in df.columns
        assert "recent_team" not in df.columns
        assert list(df["team"]) == ["KC"]

    def test_existing_team_column_untouched(self, preseason_root):
        cols = {"player_name": ["A"], "team": ["KC"], "recent_team": ["SF"]}
        _write(
            preseason_root,
            2026,
            "season_proj_20260601_000000.parquet",
            pd.DataFrame(cols),
        )
        df = ps.load_latest_preseason(2026)
        assert df is not None
        assert list(df["team"]) == ["KC"]
        assert list(df["recent_team"]) == ["SF"]

    def test_read_is_cached_per_path(self, preseason_root):
        """Repeated loads of the same artifact serve one shared frame (lru)."""
        _write(
            preseason_root,
            2026,
            "season_proj_20260601_000000.parquet",
            pd.DataFrame({"player_name": ["A"]}),
        )
        first = ps.load_latest_preseason(2026)
        second = ps.load_latest_preseason(2026)
        assert first is second

    def test_new_artifact_busts_cache(self, preseason_root):
        _write(
            preseason_root,
            2026,
            "season_proj_20260601_000000.parquet",
            pd.DataFrame({"player_name": ["A"]}),
        )
        first = ps.load_latest_preseason(2026)
        _write(
            preseason_root,
            2026,
            "season_proj_20260701_000000.parquet",
            pd.DataFrame({"player_name": ["B"]}),
        )
        second = ps.load_latest_preseason(2026)
        assert first is not None and second is not None
        assert list(second["player_name"]) == ["B"]

    def test_returns_none_on_corrupt_file(self, preseason_root):
        season_dir = preseason_root / "season=2026"
        season_dir.mkdir(parents=True, exist_ok=True)
        (season_dir / "season_proj_20260601_000000.parquet").write_bytes(
            b"not a parquet"
        )
        assert ps.load_latest_preseason(2026) is None

    def test_seasons_are_isolated(self, preseason_root):
        _write(
            preseason_root,
            2025,
            "season_proj_20250601_000000.parquet",
            pd.DataFrame({"player_name": ["Last Year"]}),
        )
        assert ps.load_latest_preseason(2026) is None
        df = ps.load_latest_preseason(2025)
        assert df is not None
        assert list(df["player_name"]) == ["Last Year"]
