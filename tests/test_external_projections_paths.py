"""read_ours must find Gold boards under the UNPADDED week dir that
generate_projections.py writes, and pick the newest file by filename stamp."""

import os
from pathlib import Path

import pandas as pd
import pytest

from src.external_projections import SilverConsolidator, _latest_parquet


def _board(path: Path, pts: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "player_id": ["p1"],
            "player_name": ["A"],
            "position": ["WR"],
            "recent_team": ["KC"],
            "projected_points": [pts],
        }
    ).to_parquet(path, index=False)


@pytest.mark.parametrize("week", [3, 11])
def test_read_ours_finds_unpadded_week_dir(tmp_path: Path, week: int) -> None:
    name = "projections_half_ppr_20261001_010101.parquet"
    _board(tmp_path / "season=2026" / f"week={week}" / name, 7.0)
    df = SilverConsolidator(
        season=2026, week=week, gold_root=tmp_path, bronze_root=tmp_path / "b"
    ).read_ours()
    assert len(df) == 1 and df["projected_points"].iloc[0] == 7.0


def test_read_ours_still_finds_padded_week_dir(tmp_path: Path) -> None:
    _board(tmp_path / "season=2026" / "week=03" / "p_20261001_010101.parquet", 5.0)
    df = SilverConsolidator(
        season=2026, week=3, gold_root=tmp_path, bronze_root=tmp_path / "b"
    ).read_ours()
    assert len(df) == 1


def test_latest_parquet_uses_filename_not_mtime(tmp_path: Path) -> None:
    old = tmp_path / "x_20261001_000000.parquet"
    new = tmp_path / "x_20261108_120000.parquet"
    for f in (old, new):
        f.write_bytes(b"")
    # Invert mtimes: the older-named file looks newest on disk.
    os.utime(new, (1_000, 1_000))
    os.utime(old, (2_000, 2_000))
    assert _latest_parquet(tmp_path) == new
