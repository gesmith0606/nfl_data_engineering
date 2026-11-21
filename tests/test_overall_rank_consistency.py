"""overall_rank must be recomputed after every stage that edits projected_points."""

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import consensus_fallback as cf  # noqa: E402
from ranking_score import assign_ranks  # noqa: E402


def _stale_board() -> pd.DataFrame:
    # Engine ranked the K 2nd, then the injury invariant zeroed him.
    return pd.DataFrame(
        {
            "player_id": list("abcdef"),
            "player_name": list("ABCDEF"),
            "position": ["QB", "K", "RB", "RB", "WR", "WR"],
            "projected_points": [20.0, 0.0, 15.0, 9.0, 12.0, 0.0],
            "overall_rank": [1, 2, 3, 4, 5, 6],
            "position_rank": [1, 1, 1, 2, 1, 2],
        }
    )


def test_zeroed_player_ranks_below_every_positive_player():
    out = assign_ranks(_stale_board())
    zero_ranks = out.loc[out.projected_points == 0, "overall_rank"]
    pos_ranks = out.loc[out.projected_points > 0, "overall_rank"]
    assert zero_ranks.min() > pos_ranks.max()
    assert list(out.sort_values("overall_rank").player_id)[:4] == list("aced")


def test_overall_rank_is_dense_permutation_in_score_order():
    out = assign_ranks(_stale_board())
    assert sorted(out.overall_rank) == list(range(1, 7))
    ordered = out.sort_values("overall_rank").projected_points.tolist()
    assert ordered == sorted(ordered, reverse=True)


def test_position_rank_agrees_with_overall_rank_within_position():
    out = assign_ranks(_stale_board())
    for _, g in out.groupby("position"):
        by_overall = g.sort_values("overall_rank").position_rank.tolist()
        assert by_overall == sorted(by_overall)


def test_ranking_score_drives_both_ranks_when_present():
    df = _stale_board()
    df["ranking_score"] = df["projected_points"]
    df.loc[df.player_id == "d", "ranking_score"] = 16.0  # nudged above c
    out = assign_ranks(df).set_index("player_id")
    assert out.loc["d", "overall_rank"] < out.loc["c", "overall_rank"]
    assert out.loc["d", "position_rank"] == 1
    assert out.loc["c", "position_rank"] == 2


def test_consensus_fallback_rank_uses_same_helper():
    out = cf._rank(_stale_board())
    ref = assign_ranks(_stale_board())
    assert out.overall_rank.tolist() == ref.overall_rank.tolist()
    assert out.position_rank.tolist() == ref.position_rank.tolist()


def test_weekly_script_reranks_after_injury_invariant_and_sorts():
    src = open(os.path.join(ROOT, "scripts", "generate_projections.py")).read()
    inv = src.index("Injury invariant: re-zeroed")
    call = src.index("assign_ranks(", inv)
    assert call > inv
    assert src.index("Saved Gold ->") > call
