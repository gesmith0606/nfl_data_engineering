"""The Sleeper consensus anchor must not re-deal values across rows that stay zero."""

import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from sleeper_consensus_anchor import (  # noqa: E402
    apply_consensus_anchor_blend,
    build_sleeper_lookup,
)


def _old_blend(proj_df, lookup_df, weight, position, points_col="projected_points"):
    """Frozen copy of the pre-fix algorithm (pins the no-zero-rows no-op)."""
    proj = proj_df.copy()
    if "sleeper_anchor_flag" not in proj.columns:
        proj["sleeper_anchor_flag"] = False
    is_pos = proj["position"] == position
    pool = proj.loc[is_pos].copy()
    pool["_our_rank"] = pool[points_col].rank(ascending=False, method="first")
    lookup = lookup_df.drop_duplicates("player_id").set_index("player_id")[
        "sleeper_pos_rank"
    ]
    sleeper_rank = pool["player_id"].astype(str).map(lookup)
    matched = sleeper_rank.notna()
    matched_idx = pool.index[matched]
    blended = (1.0 - weight) * pool.loc[
        matched_idx, "_our_rank"
    ] + weight * sleeper_rank[matched_idx]
    vals = pool.loc[matched_idx, points_col].sort_values(ascending=False).to_numpy()
    order = blended.sort_values(ascending=True).index
    proj.loc[order, points_col] = np.round(vals, 2)
    proj.loc[matched_idx, "sleeper_anchor_flag"] = True
    return proj


def _board(points, extra=None):
    ids = list("abcdefgh")[: len(points)]
    df = pd.DataFrame(
        {
            "player_id": ids,
            "position": "WR",
            "projected_points": points,
            "projected_floor": [p * 0.5 for p in points],
            "projected_ceiling": [p * 1.5 for p in points],
        }
    )
    if extra:
        for k, v in extra.items():
            df[k] = v
    return df


def _lookup(ranks):
    return pd.DataFrame(
        {"player_id": list("abcdefgh")[: len(ranks)], "sleeper_pos_rank": ranks}
    )


def test_zeroed_rows_stay_zero_and_live_values_are_permuted_among_live_rows():
    # e and f are Out (0.0). Sleeper (weight 1.0) ranks them best -> the old
    # code dealt them 10.0 / 8.0 and a live player got 0.0.
    board = _board(
        [10.0, 8.0, 6.0, 4.0, 0.0, 0.0],
        extra={"injury_multiplier": [1, 1, 1, 1, 0.0, 0.0]},
    )
    lookup = _lookup([3, 4, 5, 6, 1, 2])
    old = _old_blend(board, lookup, 1.0, "WR")
    assert old.set_index("player_id").loc["e", "projected_points"] == 10.0  # bug

    out = apply_consensus_anchor_blend(board, lookup, 1.0, "WR").set_index("player_id")
    assert out.loc["e", "projected_points"] == 0.0
    assert out.loc["f", "projected_points"] == 0.0
    live = out.loc[list("abcd"), "projected_points"]
    assert (live > 0).all()
    assert sorted(live) == [4.0, 6.0, 8.0, 10.0]
    # the zero rows are untouched: not flagged, band intact
    assert not out.loc["e", "sleeper_anchor_flag"]
    assert out.loc["e", "projected_ceiling"] == 0.0


def test_live_rows_are_still_reordered_by_sleeper_rank():
    board = _board([10.0, 8.0, 6.0, 0.0])
    lookup = _lookup([3, 2, 1, 4])  # sleeper: c best
    out = apply_consensus_anchor_blend(board, lookup, 1.0, "WR").set_index("player_id")
    assert out.loc["c", "projected_points"] == 10.0
    assert out.loc["a", "projected_points"] == 6.0
    assert out.loc["d", "projected_points"] == 0.0


def test_pure_zero_rows_without_injury_column_are_excluded():
    board = _board([9.0, 7.0, 0.0])
    out = apply_consensus_anchor_blend(board, _lookup([3, 2, 1]), 1.0, "WR").set_index(
        "player_id"
    )
    assert out.loc["c", "projected_points"] == 0.0
    assert out.loc["a", "projected_points"] == 7.0
    assert out.loc["b", "projected_points"] == 9.0


def test_no_zero_rows_is_byte_identical_to_old_behaviour():
    board = _board(
        [12.34, 10.1, 9.0, 7.77, 5.5, 3.21],
        extra={"injury_multiplier": [1.0, 0.85, 1.0, 1.0, 1.0, 0.5]},
    )
    lookup = _lookup([4, 1, 6, 2, 3, 5])
    for w in (0.25, 0.5, 1.0):
        new = apply_consensus_anchor_blend(board, lookup, w, "WR")
        old = _old_blend(board, lookup, w, "WR")
        pd.testing.assert_frame_equal(new, old, check_exact=True)


def test_lookup_coverage_denominator_counts_live_rows_only(tmp_path):
    proj = pd.DataFrame(
        {
            "player_id": ["A", "B", "C", "D"],
            "position": "WR",
            "projected_points": [20.0, 15.0, 0.0, 0.0],
        }
    )
    week_dir = tmp_path / "sleeper" / "season=2026" / "week=05"
    week_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "player_id": ["A", "B", "C", "D"],
            "position": "WR",
            "projected_points": [18.0, 14.0, 1.0, 0.5],
            "scoring_format": "half_ppr",
        }
    ).to_parquet(week_dir / "s_20260101_000000.parquet", index=False)
    lookup, stats = build_sleeper_lookup(
        proj, 2026, 5, "WR", bronze_dir=str(tmp_path / "sleeper")
    )
    assert stats["n_proj_pos_rows"] == 2
    assert stats["n_final_matched"] == 2
    assert stats["n_startable_matched"] == 2
    assert sorted(lookup["player_id"]) == ["A", "B"]
