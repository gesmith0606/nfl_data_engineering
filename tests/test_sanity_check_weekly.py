"""Unit tests for the SANITY-M6 weekly projection gate.

Covers the 2026-06-12 incident class: a 42-day-old weekly parquet (generated
2026-05-01 by pre-fix code) was baked into the deploy image and served by the
website's weekly view with Christian McCaffrey at RB118, Drake Maye at QB29,
season-scale totals (Lamar Jackson 483.1 "weekly" points), and duplicate
rookie-fallback rows.

Tests are synthetic — no dependency on real Gold/Silver partitions on disk.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.sanity_check_projections as sanity  # noqa: E402


SEASON = 2026
WEEK = 1


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _weekly_df(
    points_scale: float = 1.0,
    duplicate_rows: bool = False,
    cmc_rank_buried: bool = False,
    negative_points: bool = False,
) -> pd.DataFrame:
    """Build a synthetic weekly Gold projections DataFrame.

    Default output is healthy: weekly-scale points, unique player_ids, and
    every consensus star near the top of their position.
    """
    rows = []
    star_points = {
        "QB": [("Star QB1", 24.0), ("Star QB2", 22.0)],
        "RB": [("Christian McCaffrey", 19.0), ("Star RB2", 17.0)],
        "WR": [("Star WR1", 16.0), ("Star WR2", 15.0)],
        "TE": [("Star TE1", 13.0), ("Star TE2", 11.0)],
    }
    pid = 0
    for pos, players in star_points.items():
        for name, pts in players:
            pid += 1
            if cmc_rank_buried and name == "Christian McCaffrey":
                pts = 0.4  # buries him below the 120 filler players
            rows.append(
                {
                    "player_id": f"00-{pid:04d}",
                    "player_name": name,
                    "position": pos,
                    "projected_points": pts * points_scale,
                }
            )
        # Filler players so each position has a deep rank table.
        for i in range(30):
            pid += 1
            rows.append(
                {
                    "player_id": f"00-{pid:04d}",
                    "player_name": f"Filler {pos}{i}",
                    "position": pos,
                    "projected_points": (10.0 - i * 0.3) * points_scale,
                }
            )

    if duplicate_rows:
        rows.append(dict(rows[0]))
        rows.append(dict(rows[1]))
    if negative_points:
        pid += 1
        rows.append(
            {
                "player_id": f"00-{pid:04d}",
                "player_name": "Negative Guy",
                "position": "WR",
                "projected_points": -1.5,
            }
        )
    return pd.DataFrame(rows)


def _consensus_df() -> pd.DataFrame:
    """Synthetic Silver external_projections with the same stars on top."""
    rows = []
    stars = {
        "QB": ["Star QB1", "Star QB2"],
        "RB": ["Christian McCaffrey", "Star RB2"],
        "WR": ["Star WR1", "Star WR2"],
        "TE": ["Star TE1", "Star TE2"],
    }
    for pos, names in stars.items():
        for rank, name in enumerate(names):
            rows.append(
                {
                    "player_name": name,
                    "position": pos,
                    "projected_points": 25.0 - rank,
                }
            )
    return pd.DataFrame(rows)


def _fname(age_days: int) -> str:
    ts = (datetime.now() - timedelta(days=age_days)).strftime("%Y%m%d_%H%M%S")
    return f"projections_half_ppr_{ts}.parquet"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect GOLD_DIR and PROJECT_ROOT into a temp sandbox."""
    gold = tmp_path / "data" / "gold"
    gold.mkdir(parents=True)
    monkeypatch.setattr(sanity, "GOLD_DIR", str(gold))
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    return tmp_path


def _write_weekly(tmp_path: Path, df: pd.DataFrame, age_days: int = 0) -> Path:
    week_dir = (
        tmp_path / "data" / "gold" / "projections"
        / f"season={SEASON}" / f"week={WEEK}"
    )
    week_dir.mkdir(parents=True, exist_ok=True)
    path = week_dir / _fname(age_days)
    df.to_parquet(path, index=False)
    return path


def _write_consensus(tmp_path: Path) -> Path:
    ext_dir = (
        tmp_path / "data" / "silver" / "external_projections"
        / f"season={SEASON}" / f"week={WEEK:02d}"
    )
    ext_dir.mkdir(parents=True, exist_ok=True)
    path = ext_dir / f"external_{_fname(0).replace('projections_half_ppr_', '')}"
    _consensus_df().to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMissingPartition:
    def test_missing_partition_is_skip_not_failure(self, sandbox):
        criticals, warnings = sanity.run_weekly_projection_check(
            SEASON, WEEK, "half_ppr"
        )
        assert criticals == []
        assert warnings == []


class TestFreshness:
    def test_stale_file_is_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df(), age_days=42)
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("STALE WEEKLY FILE" in c for c in criticals)

    def test_fresh_file_passes_freshness(self, sandbox):
        _write_weekly(sandbox, _weekly_df(), age_days=0)
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert not any("STALE WEEKLY FILE" in c for c in criticals)


class TestDuplicates:
    def test_duplicate_player_ids_are_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df(duplicate_rows=True))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("DUPLICATE player_id" in c for c in criticals)


class TestScaleSanity:
    def test_season_scale_points_are_critical(self, sandbox):
        # 20x weekly scale: top QB at 480 pts mimics the incident file.
        _write_weekly(sandbox, _weekly_df(points_scale=20.0))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("season-scale" in c.lower() for c in criticals)

    def test_negative_points_are_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df(negative_points=True))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("negative" in c.lower() for c in criticals)


class TestStarRank:
    def test_buried_consensus_star_is_critical(self, sandbox):
        # CMC buried below 30 filler RBs — the RB118 incident in miniature.
        _write_weekly(sandbox, _weekly_df(cmc_rank_buried=True))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("McCaffrey" in c for c in criticals)

    def test_no_consensus_data_is_warning_not_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df())

        criticals, warnings = sanity.run_weekly_projection_check(
            SEASON, WEEK, "half_ppr"
        )

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STAR-RANK SKIPPED" in w for w in warnings)


class TestHealthyFile:
    def test_healthy_fresh_file_has_no_criticals(self, sandbox):
        _write_weekly(sandbox, _weekly_df())
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert criticals == []
