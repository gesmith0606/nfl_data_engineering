"""Tests for SilverConsolidator (Plan 73-02)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.external_projections import SilverConsolidator, _SILVER_COLUMNS


def _write_bronze(
    bronze_root: Path,
    source: str,
    season: int,
    week: int,
    rows: list,
) -> Path:
    week_dir = bronze_root / source / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    p = week_dir / f"{source}_test.parquet"
    df = pd.DataFrame(rows)
    df.to_parquet(p, index=False)
    return p


def _write_gold(gold_root: Path, season: int, week: int, rows: list) -> Path:
    week_dir = gold_root / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    p = week_dir / "projections_test.parquet"
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


def _make_bronze_row(player_id, name, team, pos, pts, source, scoring="half_ppr"):
    return {
        "player_name": name,
        "player_id": player_id,
        "team": team,
        "position": pos,
        "projected_points": pts,
        "scoring_format": scoring,
        "source": source,
        "season": 2025,
        "week": 1,
        "projected_at": "2026-04-25T00:00:00+00:00",
        "raw_payload": "",
    }


class TestReadBronzeSource:
    def test_returns_empty_when_partition_missing(self, tmp_path):
        c = SilverConsolidator(season=2025, week=1, bronze_root=tmp_path)
        df = c.read_bronze_source("espn")
        assert df.empty
        assert list(df.columns) == _SILVER_COLUMNS

    def test_reads_existing_partition(self, tmp_path):
        _write_bronze(
            tmp_path,
            "espn",
            2025,
            1,
            [_make_bronze_row("00-001", "Mahomes", "KC", "QB", 22.4, "espn")],
        )
        c = SilverConsolidator(season=2025, week=1, bronze_root=tmp_path)
        df = c.read_bronze_source("espn")
        assert len(df) == 1
        assert df.iloc[0]["projected_points"] == 22.4
        assert df.iloc[0]["source"] == "espn"

    def test_filters_by_scoring_format(self, tmp_path):
        _write_bronze(
            tmp_path,
            "espn",
            2025,
            1,
            [
                _make_bronze_row("00-001", "M", "KC", "QB", 22.4, "espn", "half_ppr"),
                _make_bronze_row("00-002", "A", "BUF", "QB", 24.1, "espn", "ppr"),
            ],
        )
        c = SilverConsolidator(
            season=2025, week=1, scoring_format="ppr", bronze_root=tmp_path
        )
        df = c.read_bronze_source("espn")
        assert len(df) == 1
        assert df.iloc[0]["scoring_format"] == "ppr"


class TestReadOurs:
    def test_returns_empty_when_gold_missing(self, tmp_path):
        c = SilverConsolidator(
            season=2025, week=1, gold_root=tmp_path, bronze_root=tmp_path
        )
        df = c.read_ours()
        assert df.empty

    def test_normalizes_recent_team_to_team(self, tmp_path):
        _write_gold(
            tmp_path,
            2025,
            1,
            [
                {
                    "player_id": "00-001",
                    "player_name": "Mahomes",
                    "recent_team": "KC",
                    "position": "QB",
                    "projected_points": 25.0,
                }
            ],
        )
        c = SilverConsolidator(
            season=2025, week=1, gold_root=tmp_path, bronze_root=tmp_path
        )
        df = c.read_ours()
        assert len(df) == 1
        assert df.iloc[0]["team"] == "KC"
        assert df.iloc[0]["source"] == "ours"


class TestToLongFormat:
    def test_concats_multiple_sources(self, tmp_path):
        c = SilverConsolidator(season=2025, week=1, bronze_root=tmp_path)
        f1 = pd.DataFrame(
            [_make_bronze_row("00-001", "Mahomes", "KC", "QB", 22.4, "espn")]
        )[_SILVER_COLUMNS]
        f2 = pd.DataFrame(
            [_make_bronze_row("00-001", "Mahomes", "KC", "QB", 21.8, "sleeper")]
        )[_SILVER_COLUMNS]
        merged = c.to_long_format([f1, f2])
        assert len(merged) == 2
        assert set(merged["source"].values) == {"espn", "sleeper"}

    def test_empty_frames_yields_empty_with_columns(self, tmp_path):
        c = SilverConsolidator(season=2025, week=1, bronze_root=tmp_path)
        merged = c.to_long_format([pd.DataFrame(), pd.DataFrame()])
        assert merged.empty
        assert list(merged.columns) == _SILVER_COLUMNS


class TestConsolidate:
    def test_consolidates_all_3_external_sources(self, tmp_path):
        bronze = tmp_path / "bronze"
        gold = tmp_path / "gold"
        for source, pts in (("espn", 22.4), ("sleeper", 21.8), ("yahoo_proxy_fp", 23.1)):
            _write_bronze(
                bronze,
                source,
                2025,
                1,
                [_make_bronze_row("00-001", "Mahomes", "KC", "QB", pts, source)],
            )
        c = SilverConsolidator(
            season=2025, week=1, bronze_root=bronze, gold_root=gold
        )
        df = c.consolidate()
        assert len(df) == 3  # 3 external sources, no "ours" since gold missing
        assert set(df["source"].values) == {"espn", "sleeper", "yahoo_proxy_fp"}

    def test_returns_empty_when_all_sources_missing(self, tmp_path):
        c = SilverConsolidator(
            season=2025,
            week=1,
            bronze_root=tmp_path / "bronze",
            gold_root=tmp_path / "gold",
        )
        df = c.consolidate()
        assert df.empty
        assert list(df.columns) == _SILVER_COLUMNS


class TestWriteSilver:
    def test_writes_parquet_at_canonical_path(self, tmp_path):
        c = SilverConsolidator(season=2025, week=1, bronze_root=tmp_path)
        df = pd.DataFrame(
            [_make_bronze_row("00-001", "Mahomes", "KC", "QB", 22.4, "espn")]
        )[_SILVER_COLUMNS]
        out = c.write_silver(df, silver_root=tmp_path / "silver")
        assert out is not None
        assert out.exists()
        assert "season=2025" in str(out)
        assert "week=01" in str(out)

    def test_skips_write_on_empty(self, tmp_path):
        c = SilverConsolidator(season=2025, week=1, bronze_root=tmp_path)
        out = c.write_silver(
            pd.DataFrame(columns=_SILVER_COLUMNS), silver_root=tmp_path / "silver"
        )
        assert out is None
