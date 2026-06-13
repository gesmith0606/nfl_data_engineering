"""
Tests for the weekly-projections preseason fallback in the web API service.

Covers the incident class from 2026-06-12 where the website's "2026 Week 1"
view served a 6-week-stale weekly parquet (Drake Maye QB29, CMC RB118)
while fresh preseason projections existed. The service now falls back to
preseason data when the weekly parquet for a current/future season is
missing or stale, and labels the response ``source="preseason_fallback"``.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.api.services import projection_service as ps  # noqa: E402

CURRENT_YEAR = datetime.now(tz=timezone.utc).year
PAST_SEASON = CURRENT_YEAR - 2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _weekly_df(season: int, week: int) -> pd.DataFrame:
    """Minimal DataFrame matching the Gold weekly projections schema."""
    return pd.DataFrame(
        {
            "player_id": ["00-001", "00-002"],
            "player_name": ["Weekly QB", "Weekly RB"],
            "position": ["QB", "RB"],
            "recent_team": ["KC", "SF"],
            "season": [season, season],
            "week": [week, week],
            "passing_yards": [280.0, 0.0],
            "rushing_yards": [20.0, 90.0],
            "projected_points": [22.5, 16.8],
            "projected_floor": [14.0, 10.0],
            "projected_ceiling": [31.0, 25.0],
        }
    )


def _preseason_df(season: int) -> pd.DataFrame:
    """Minimal DataFrame matching the Gold preseason projections schema."""
    return pd.DataFrame(
        {
            "player_id": ["00-101", "00-102"],
            "player_name": ["Preseason QB", "Preseason RB"],
            "position": ["QB", "RB"],
            "recent_team": ["NE", "SF"],
            "passing_yards": [3900.0, 0.0],
            "rushing_yards": [480.0, 1100.0],
            "projected_season_points": [316.0, 259.1],
            "proj_season": [season, season],
            "position_rank": [8, 6],
        }
    )


@pytest.fixture()
def gold_dir(tmp_path, monkeypatch):
    """Point the service at a temp Gold projections dir, Parquet backend."""
    root = tmp_path / "projections"
    root.mkdir()
    monkeypatch.setattr(ps, "GOLD_PROJECTIONS_DIR", root)
    monkeypatch.setattr(ps, "is_db_enabled", lambda: False)
    return root


def _write_weekly(root: Path, season: int, week: int, stale: bool = False) -> Path:
    week_dir = root / f"season={season}" / f"week={week}"
    week_dir.mkdir(parents=True, exist_ok=True)
    # Staleness is read from the filename-embedded timestamp (mtime is
    # unreliable in clone deployments), so encode the age in the name.
    age_days = (ps.WEEKLY_STALENESS_THRESHOLD_DAYS + 30) if stale else 0
    ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).strftime(
        "%Y%m%d_%H%M%S"
    )
    path = week_dir / f"projections_half_ppr_{ts}.parquet"
    _weekly_df(season, week).to_parquet(path, index=False)
    if stale:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


def _write_preseason(root: Path, season: int) -> Path:
    ps_dir = root / "preseason" / f"season={season}"
    ps_dir.mkdir(parents=True, exist_ok=True)
    path = ps_dir / "season_proj_20260612_152045.parquet"
    _preseason_df(season).to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Fallback triggers
# ---------------------------------------------------------------------------


class TestFallbackTriggers:
    def test_missing_weekly_file_falls_back_to_preseason(self, gold_dir):
        _write_preseason(gold_dir, CURRENT_YEAR)

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
        )

        assert set(df["player_name"]) == {"Preseason QB", "Preseason RB"}

    def test_stale_weekly_file_falls_back_to_preseason(self, gold_dir):
        _write_weekly(gold_dir, CURRENT_YEAR, 1, stale=True)
        _write_preseason(gold_dir, CURRENT_YEAR)

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
        )

        assert "Preseason QB" in set(df["player_name"])
        assert "Weekly QB" not in set(df["player_name"])

    def test_fresh_weekly_file_is_served_normally(self, gold_dir):
        _write_weekly(gold_dir, CURRENT_YEAR, 1, stale=False)
        _write_preseason(gold_dir, CURRENT_YEAR)

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
        )

        assert set(df["player_name"]) == {"Weekly QB", "Weekly RB"}

    def test_stale_weekly_without_preseason_serves_stale_file(self, gold_dir):
        _write_weekly(gold_dir, CURRENT_YEAR, 1, stale=True)

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
        )

        assert set(df["player_name"]) == {"Weekly QB", "Weekly RB"}

    def test_missing_weekly_without_preseason_raises(self, gold_dir):
        with pytest.raises(FileNotFoundError):
            ps.get_projections(
                season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
            )


class TestHistoricalSeasonsExempt:
    def test_stale_historical_file_is_served_without_fallback(self, gold_dir):
        _write_weekly(gold_dir, PAST_SEASON, 10, stale=True)
        _write_preseason(gold_dir, PAST_SEASON)

        df = ps.get_projections(
            season=PAST_SEASON, week=10, scoring_format="half_ppr"
        )

        assert set(df["player_name"]) == {"Weekly QB", "Weekly RB"}

    def test_missing_historical_file_raises_without_fallback(self, gold_dir):
        _write_preseason(gold_dir, PAST_SEASON)

        with pytest.raises(FileNotFoundError):
            ps.get_projections(
                season=PAST_SEASON, week=10, scoring_format="half_ppr"
            )


# ---------------------------------------------------------------------------
# Response shape and metadata
# ---------------------------------------------------------------------------


class TestFallbackResponseShape:
    def test_fallback_normalizes_to_weekly_schema(self, gold_dir):
        _write_preseason(gold_dir, CURRENT_YEAR)

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
        )

        # projected_season_points renamed; season/week stamped from request
        assert "projected_points" in df.columns
        assert (df["season"] == CURRENT_YEAR).all()
        assert (df["week"] == 1).all()
        assert (df["scoring_format"] == "half_ppr").all()
        # floor/ceiling synthesized and ordered around the point estimate
        assert (df["projected_floor"] <= df["projected_points"]).all()
        assert (df["projected_ceiling"] >= df["projected_points"]).all()
        assert (df["projected_points"] >= 0).all()

    def test_fallback_respects_position_filter(self, gold_dir):
        _write_preseason(gold_dir, CURRENT_YEAR)

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr", position="RB"
        )

        assert set(df["position"]) == {"RB"}

    def test_meta_reports_preseason_fallback_source(self, gold_dir):
        preseason_path = _write_preseason(gold_dir, CURRENT_YEAR)

        meta = ps.get_projection_meta(season=CURRENT_YEAR, week=1)

        assert meta.source == "preseason_fallback"
        assert meta.data_as_of is not None
        assert preseason_path.name in (meta.source_path or "")

    def test_meta_reports_weekly_source_for_fresh_file(self, gold_dir):
        _write_weekly(gold_dir, CURRENT_YEAR, 1, stale=False)
        _write_preseason(gold_dir, CURRENT_YEAR)

        meta = ps.get_projection_meta(season=CURRENT_YEAR, week=1)

        assert meta.source == "weekly"

    def test_meta_reports_weekly_source_for_historical_season(self, gold_dir):
        _write_weekly(gold_dir, PAST_SEASON, 10, stale=True)
        _write_preseason(gold_dir, PAST_SEASON)

        meta = ps.get_projection_meta(season=PAST_SEASON, week=10)

        assert meta.source == "weekly"


# ---------------------------------------------------------------------------
# File selection — clone-mtime and scoring-format regressions
# ---------------------------------------------------------------------------


class TestLatestParquetSelection:
    def test_latest_by_filename_timestamp_when_mtimes_identical(self, gold_dir):
        """HF Spaces clones the repo fresh, so every file shares one mtime.

        The newest file by embedded filename timestamp must win regardless.
        This reproduces the 2026-06-12 incident where the Space served the
        oldest (2026-04-10) preseason parquet as 'latest'.
        """
        ps_dir = gold_dir / "preseason" / f"season={CURRENT_YEAR}"
        ps_dir.mkdir(parents=True)
        old = ps_dir / "season_proj_20260410_184651.parquet"
        new = ps_dir / "season_proj_20260612_152045.parquet"
        df_old = _preseason_df(CURRENT_YEAR)
        df_old["player_name"] = ["Old QB", "Old RB"]
        df_old.to_parquet(old, index=False)
        _preseason_df(CURRENT_YEAR).to_parquet(new, index=False)
        # Equalize mtimes to simulate a fresh git clone.
        clone_time = time.time()
        os.utime(old, (clone_time, clone_time))
        os.utime(new, (clone_time, clone_time))

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
        )

        assert set(df["player_name"]) == {"Preseason QB", "Preseason RB"}

    def test_weekly_read_prefers_requested_scoring_format(self, gold_dir):
        week_dir = gold_dir / f"season={CURRENT_YEAR}" / "week=1"
        week_dir.mkdir(parents=True)
        half = _weekly_df(CURRENT_YEAR, 1)
        half.to_parquet(
            week_dir / "projections_half_ppr_20260612_100000.parquet", index=False
        )
        std = _weekly_df(CURRENT_YEAR, 1)
        std["player_name"] = ["Std QB", "Std RB"]
        # Standard file has a NEWER timestamp — must still not be served
        # for a half_ppr request.
        std.to_parquet(
            week_dir / "projections_standard_20260612_110000.parquet", index=False
        )

        df = ps.get_projections(
            season=CURRENT_YEAR, week=1, scoring_format="half_ppr"
        )

        assert set(df["player_name"]) == {"Weekly QB", "Weekly RB"}
