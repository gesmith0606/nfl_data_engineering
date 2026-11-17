"""Tests for src/consensus_fallback.py: every consensus>=5 player gets a board row."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import consensus_fallback as cf  # noqa: E402


def _board():
    return pd.DataFrame(
        {
            "player_id": ["a", "b", "c"],
            "player_name": ["A.One", "B.Two", "C.Three"],
            "position": ["QB", "RB", "WR"],
            "recent_team": ["AAA", "BBB", "CCC"],
            "projected_points": [18.0, 12.0, 9.0],
            "projected_floor": [8.0, 5.0, 3.0],
            "projected_ceiling": [28.0, 20.0, 16.0],
            "position_rank": [1, 1, 1],
            "overall_rank": [1, 2, 3],
            "is_bye_week": [False, False, False],
            "sleeper_anchor_flag": [True, True, True],
            "projection_source": ["hybrid"] * 3,
            "proj_season": 2026,
            "proj_week": 4,
            "week": 4,
            "season": 2026,
        }
    )


def _consensus(**over):
    rows = [
        ("a", "Aaa One", "QB", "AAA", 17.0),  # already on board
        ("d", "Dee Four", "RB", "DDD", 11.0),  # missing, startable -> added
        ("e", "Eee Five", "WR", "EEE", 5.0),  # exactly 5 -> added
        ("f", "Eff Six", "TE", "FFF", 4.9),  # below threshold
        ("g", "Gee Seven", "K", "GGG", 9.0),  # not a skill position
    ]
    return pd.DataFrame(rows, columns=["player_id", "player_name", "position", "team", "consensus"])


def test_adds_only_missing_startable_skill_players():
    out, n = cf.apply_consensus_fallback(_board(), _consensus(), season=2026, week=4)
    assert n == 2
    assert set(out.player_id) == {"a", "b", "c", "d", "e"}
    fb = out[out.projection_source == cf.FALLBACK_SOURCE].set_index("player_id")
    assert fb.loc["d", "projected_points"] == 11.0
    assert fb.loc["e", "projected_points"] == 5.0
    assert fb.loc["d", "recent_team"] == "DDD"
    assert fb.loc["d", "player_name"] == "D.Four"  # board's short-name convention
    # original rows untouched and still labelled by the route they took
    assert out.set_index("player_id").loc["a", "projection_source"] == "hybrid"
    assert out.set_index("player_id").loc["a", "projected_points"] == 18.0


def test_noop_when_nothing_missing():
    board = _board()
    cons = _consensus().iloc[:1]
    out, n = cf.apply_consensus_fallback(board, cons, season=2026, week=4)
    assert n == 0
    pd.testing.assert_frame_equal(out, board)


def test_out_player_keeps_a_zero_row():
    inj = pd.DataFrame({"gsis_id": ["d"], "report_status": ["Out"]})
    out, n = cf.apply_consensus_fallback(_board(), _consensus(), season=2026, week=4, injuries_df=inj)
    d = out.set_index("player_id").loc["d"]
    assert n == 2 and d.projected_points == 0.0 and d.injury_status == "Out"


def test_bands_ordered_and_flags_false():
    out, _ = cf.apply_consensus_fallback(_board(), _consensus(), season=2026, week=4)
    fb = out[out.projection_source == cf.FALLBACK_SOURCE]
    assert (fb.projected_floor <= fb.projected_points).all()
    assert (fb.projected_ceiling >= fb.projected_points).all()
    assert fb.projected_floor.notna().all() and fb.projected_ceiling.notna().all()
    assert not fb.sleeper_anchor_flag.any()
    assert (fb.is_bye_week == False).all()  # noqa: E712
    assert (fb.week == 4).all() and (fb.season == 2026).all()


def test_ranks_recomputed_over_the_full_board():
    out, _ = cf.apply_consensus_fallback(_board(), _consensus(), season=2026, week=4)
    o = out.set_index("player_id")
    assert o.loc["b", "position_rank"] == 1  # d (11.0) joins RB behind b (12.0)
    assert o.loc["d", "position_rank"] == 2
    assert list(out.sort_values("overall_rank").projected_points) == sorted(out.projected_points, reverse=True)


def test_missing_snapshot_is_a_loud_noop(capsys):
    out, n = cf.apply_consensus_fallback(_board(), pd.DataFrame(), season=2026, week=4)
    assert n == 0 and len(out) == 3
    assert "::warning::" in capsys.readouterr().out


def test_load_consensus_week_filters_source_scoring_and_takes_latest(tmp_path):
    d = tmp_path / "external_projections" / "season=2026" / "week=04"
    d.mkdir(parents=True)
    base = {"player_id": ["x", "y"], "player_name": ["X X", "Y Y"], "position": ["WR", "WR"], "team": ["T", "T"]}
    old = pd.DataFrame({**base, "source": "sleeper", "scoring_format": "half_ppr", "projected_points": [1.0, 2.0]})
    new = pd.DataFrame(
        {
            **{k: v + v for k, v in base.items()},
            "source": ["sleeper", "sleeper", "yahoo_proxy_fp", "sleeper"],
            "scoring_format": ["half_ppr", "ppr", "half_ppr", "half_ppr"],
            "projected_points": [9.0, 99.0, 77.0, 7.0],
        }
    )
    old.to_parquet(d / "external_projections_20261001_000000.parquet")
    new.to_parquet(d / "external_projections_20261002_000000.parquet")
    got = cf.load_consensus_week(2026, 4, "half_ppr", silver_dir=str(tmp_path))
    assert got.set_index("player_id").consensus.to_dict() == {"x": 9.0, "y": 7.0}
    assert list(got.columns) == ["player_id", "player_name", "position", "team", "consensus"]
    assert cf.load_consensus_week(2026, 5, "half_ppr", silver_dir=str(tmp_path)).empty
