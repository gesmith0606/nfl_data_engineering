"""ppr / standard weekly boards are deterministic re-scores of the half_ppr board."""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scoring_derivation import derive_board, derive_week_dir  # noqa: E402


def _board() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": ["wr", "qb", "te_fb", "rb_nan", "wr_low"],
            "player_name": ["WR One", "QB One", "TE Fall", "RB Nan", "WR Low"],
            "position": ["WR", "QB", "TE", "RB", "WR"],
            "season": [2026] * 5,
            "week": [11] * 5,
            "proj_receptions": [6.0, 0.0, 0.0, None, 1.0],
            "projected_points": [15.0, 20.0, 5.0, 9.0, 1.0],
            "projected_floor": [8.0, 12.0, 2.0, 4.0, 0.5],
            "projected_ceiling": [24.0, 30.0, 9.0, 15.0, 3.0],
            "projection_source": [
                "hybrid",
                "hybrid",
                "consensus_fallback",
                "hybrid",
                "hybrid",
            ],
            "position_rank": [1, 1, 1, 1, 2],
            "overall_rank": [2, 1, 4, 3, 5],
            "ranking_score": [15.0, 20.0, 5.0, 9.0, 1.0],
        }
    )


def _row(df, pid):
    return df.set_index("player_id").loc[pid]


def test_ppr_adds_half_a_point_per_reception():
    out = derive_board(_board(), "ppr", derived_from="src.parquet")
    wr = _row(out, "wr")
    assert wr.projected_points == pytest.approx(18.0)
    assert wr.projected_floor == pytest.approx(11.0)
    assert wr.projected_ceiling == pytest.approx(27.0)
    assert wr.scoring_format == "ppr"
    assert wr.derived_from == "src.parquet"
    assert not wr.scoring_derivation_flag


def test_standard_subtracts_and_floors_at_zero():
    out = derive_board(_board(), "standard")
    assert _row(out, "wr").projected_points == pytest.approx(12.0)
    low = _row(out, "wr_low")  # 1.0 - 0.5*1 = 0.5 ; floor 0.5-0.5 = 0.0
    assert low.projected_points == pytest.approx(0.5)
    assert low.projected_floor == pytest.approx(0.0)
    assert (out.projected_points >= 0).all()


def test_qb_without_receptions_unchanged_and_unflagged():
    for fmt in ("ppr", "standard"):
        qb = _row(derive_board(_board(), fmt), "qb")
        assert qb.projected_points == 20.0
        assert not qb.scoring_derivation_flag


def test_missing_or_fallback_receptions_keep_half_ppr_and_are_flagged():
    for fmt in ("ppr", "standard"):
        out = derive_board(_board(), fmt)
        for pid, pts in (("rb_nan", 9.0), ("te_fb", 5.0)):
            r = _row(out, pid)
            assert r.projected_points == pts
            assert bool(r.scoring_derivation_flag)
        assert int(out.scoring_derivation_flag.sum()) == 2


def test_bands_ordered_and_ranks_dense_and_consistent_with_points():
    for fmt in ("ppr", "standard"):
        out = derive_board(_board(), fmt)
        assert (out.projected_floor <= out.projected_points).all()
        assert (out.projected_points <= out.projected_ceiling).all()
        assert sorted(out.overall_rank) == [1, 2, 3, 4, 5]
        assert list(out.projected_points) == sorted(out.projected_points, reverse=True)
        for _, g in out.groupby("position"):
            assert sorted(g.position_rank) == list(range(1, len(g) + 1))
            assert list(g.sort_values("position_rank").projected_points) == sorted(
                g.projected_points, reverse=True
            )


def test_ppr_ge_half_ge_standard_for_every_row():
    b = _board()
    p = derive_board(b, "ppr").set_index("player_id").projected_points
    s = derive_board(b, "standard").set_index("player_id").projected_points
    h = b.set_index("player_id").projected_points
    p, s = p.reindex(h.index), s.reindex(h.index)
    assert (p >= h).all() and (h >= s).all()


def test_input_not_mutated_and_bad_target_rejected():
    b = _board()
    derive_board(b, "ppr")
    assert b.projected_points.tolist() == [15.0, 20.0, 5.0, 9.0, 1.0]
    with pytest.raises(ValueError):
        derive_board(b, "half_ppr")


def test_derive_week_dir_reuses_source_timestamp(tmp_path):
    wd = tmp_path / "week=11"
    wd.mkdir()
    _board().to_parquet(
        wd / "projections_half_ppr_20261117_092008.parquet", index=False
    )
    _board().to_parquet(
        wd / "projections_half_ppr_20261122_190745.parquet", index=False
    )
    written = derive_week_dir(wd)
    assert sorted(p.name for p in written) == [
        "projections_ppr_20261122_190745.parquet",
        "projections_standard_20261122_190745.parquet",
    ]
    df = pd.read_parquet(written[0])
    assert (df.derived_from == "projections_half_ppr_20261122_190745.parquet").all()
    assert derive_week_dir(tmp_path / "week=99") == []
