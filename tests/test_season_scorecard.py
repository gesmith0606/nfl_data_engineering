"""Tests for scripts/season_scorecard.py (published board vs consensus vs trailing-3)."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import season_scorecard as sc  # noqa: E402


def _actuals(rows):
    return pd.DataFrame(
        rows, columns=["player_id", "season", "week", "position", "recent_team", "actual_points"]
    )


def test_trailing3_uses_only_prior_games_across_seasons():
    a = _actuals(
        [
            ("p1", 2025, 17, "WR", "AAA", 10.0),
            ("p1", 2025, 18, "WR", "AAA", 20.0),
            ("p1", 2026, 1, "WR", "AAA", 30.0),
            ("p1", 2026, 2, "WR", "AAA", 0.0),
            ("p1", 2026, 3, "WR", "AAA", 6.0),
        ]
    )
    out = sc.add_trailing3(a).set_index(["season", "week"])["t3"]
    assert np.isnan(out[(2025, 17)])  # no history -> NaN, never leaks own game
    assert out[(2025, 18)] == 10.0
    assert out[(2026, 1)] == 15.0
    assert out[(2026, 2)] == pytest.approx(20.0)  # mean(10, 20, 30)
    assert out[(2026, 3)] == pytest.approx(50 / 3)  # mean(20, 30, 0): window is 3


def _fixture():
    """One position-week with 12 eligible players, ours = actual + 1 on most."""
    n = 12
    ids = [f"p{i}" for i in range(n)]
    actual = np.arange(n, dtype=float) + 5
    pw = pd.DataFrame(
        {
            "week": 3,
            "position": "WR",
            "player_id": ids,
            "player_name": ids,
            "recent_team": "AAA",
            "actual_points": actual,
            "consensus": actual + 2.0,
            "ours": actual + 1.0,
            "floor": actual - 1.0,
            "ceiling": actual + 0.5,
            "t3": actual + 3.0,
        }
    )
    pw["on_board"] = True
    return pw


def test_scorecard_row_metrics():
    pw = _fixture()
    rows = sc.scorecard_rows(pw)
    r = rows[(rows.week == "3") & (rows.position == "WR")].iloc[0]
    assert r.n_eligible == 12 and r.n_missing == 0 and r.n_matched == 12
    assert r.mae_ours == pytest.approx(1.0)
    assert r.mae_sleeper == pytest.approx(2.0)
    assert r.mae_t3 == pytest.approx(3.0)
    assert r.bias_ours == pytest.approx(1.0)
    assert r.rho_ours == pytest.approx(1.0)
    # band: floor = actual-1 <= actual <= actual+0.5 -> inside for every row
    assert r.band_coverage == pytest.approx(1.0)
    # ours and consensus are both shifted copies of actual -> identical spread
    assert r.sd_ratio == pytest.approx(1.0)


def test_missing_rows_counted_and_scored_as_zero_in_filled_gap():
    pw = _fixture()
    pw.loc[pw.player_id == "p11", ["ours", "floor", "ceiling"]] = np.nan
    pw.loc[pw.player_id == "p11", "on_board"] = False
    rows = sc.scorecard_rows(pw)
    r = rows[(rows.week == "3") & (rows.position == "WR")].iloc[0]
    assert r.n_eligible == 12 and r.n_missing == 1 and r.n_matched == 11
    # matched-only MAE ignores the hole; the zero-filled gap does not.
    assert r.mae_ours == pytest.approx(1.0)
    assert r.mae_ours_filled > r.mae_ours
    assert r.gap_filled > r.gap


def test_pooled_rows_use_all_matched_rows_and_mean_weekly_spearman():
    a = _fixture()
    b = _fixture().assign(week=4)
    b["ours"] = b["actual_points"].iloc[::-1].to_numpy()  # perfectly anti-correlated
    rows = sc.scorecard_rows(pd.concat([a, b], ignore_index=True))
    pooled = rows[(rows.week == "ALL") & (rows.position == "WR")].iloc[0]
    assert pooled.n_matched == 24
    assert pooled.rho_ours == pytest.approx(0.0)  # mean of +1 and -1
    allall = rows[(rows.week == "ALL") & (rows.position == "ALL")].iloc[0]
    assert allall.n_eligible == 24


def test_small_groups_have_no_spearman():
    pw = _fixture().head(5)
    r = sc.scorecard_rows(pw)
    wk = r[(r.week == "3") & (r.position == "WR")].iloc[0]
    assert np.isnan(wk.rho_ours)  # <10 players: not meaningful


def test_build_player_weeks_marks_missing_and_filters_consensus_threshold():
    actuals = _actuals(
        [
            ("a", 2026, 1, "WR", "AAA", 10.0),  # on board
            ("b", 2026, 1, "RB", "BBB", 8.0),  # eligible, off board
            ("c", 2026, 1, "TE", "CCC", 2.0),  # consensus < 5 -> not eligible
            ("d", 2026, 1, "K", "DDD", 9.0),  # kicker never eligible
            ("e", 2026, 1, "QB", "EEE", 12.0),  # no consensus row -> not eligible
        ]
    )
    actuals["t3"] = np.nan
    board = pd.DataFrame(
        {
            "player_id": ["a", "c"],
            "week": [1, 1],
            "projected_points": [9.0, 1.0],
            "projected_floor": [3.0, 0.0],
            "projected_ceiling": [15.0, 4.0],
            "projection_source": ["hybrid", "hybrid"],
        }
    )
    cons = pd.DataFrame(
        {"player_id": ["a", "b", "c", "d"], "week": [1] * 4, "consensus": [9.5, 7.0, 4.0, 9.0]}
    )
    pw = sc.build_player_weeks(board, cons, actuals, min_consensus=5.0)
    assert sorted(pw.player_id) == ["a", "b"]
    assert pw.set_index("player_id").on_board.to_dict() == {"a": True, "b": False}
    assert np.isnan(pw.set_index("player_id").loc["b", "ours"])


def test_zero_row_counts_as_on_board():
    """An Out player carries an explicit 0.0 row; that is a row, not a hole."""
    actuals = _actuals([("a", 2026, 2, "WR", "AAA", 7.0)])
    actuals["t3"] = np.nan
    board = pd.DataFrame(
        {"player_id": ["a"], "week": [2], "projected_points": [0.0], "projected_floor": [0.0],
         "projected_ceiling": [0.0]}
    )
    cons = pd.DataFrame({"player_id": ["a"], "week": [2], "consensus": [8.0]})
    pw = sc.build_player_weeks(board, cons, actuals)
    assert bool(pw.on_board.iloc[0]) is True


def test_markdown_mentions_weeks_without_board(tmp_path):
    pw = _fixture()
    rows = sc.scorecard_rows(pw)
    md = sc.render_markdown(rows, weeks_without_board=[8], season=2026, scoring="half_ppr")
    assert "Week 8" in md and "no published board" in md.lower()
    assert "| WR |" in md


def test_fallback_rows_flatter_the_gap_and_are_counted():
    """Fallback rows carry Sleeper's number: gap(all rows) < gap(no fallback), count reported."""
    pw = _fixture()  # ours = actual+1 (MAE 1), consensus = actual+2 (MAE 2): gap -1.0
    pw["projection_source"] = "hybrid"
    pw["is_fallback"] = False
    # make 4 rows consensus-fallback: ours == consensus
    fb = pw.player_id.isin(["p0", "p1", "p2", "p3"])
    pw.loc[fb, "ours"] = pw.loc[fb, "consensus"]
    pw.loc[fb, "projection_source"] = "consensus_fallback"
    pw.loc[fb, "is_fallback"] = True
    rows = sc.scorecard_rows(pw)
    r = rows[(rows.week == "3") & (rows.position == "WR")].iloc[0]
    assert r.n_fallback == 4
    assert r.gap_no_fallback == pytest.approx(-1.0)  # the 8 real rows: 1.0 - 2.0
    assert r.gap > r.gap_no_fallback  # (8*-1 + 4*0)/12 = -0.667: flattered toward zero
    assert r.gap == pytest.approx(-2 / 3)


def test_build_player_weeks_flags_fallback_rows():
    actuals = _actuals([("a", 2026, 1, "WR", "AAA", 10.0), ("b", 2026, 1, "RB", "BBB", 8.0)])
    actuals["t3"] = np.nan
    board = pd.DataFrame(
        {
            "player_id": ["a", "b"],
            "week": [1, 1],
            "projected_points": [9.0, 7.0],
            "projection_source": ["hybrid", "consensus_fallback"],
        }
    )
    cons = pd.DataFrame({"player_id": ["a", "b"], "week": [1, 1], "consensus": [9.5, 7.0]})
    pw = sc.build_player_weeks(board, cons, actuals).set_index("player_id")
    assert pw.loc["a", "is_fallback"] == False and pw.loc["b", "is_fallback"] == True  # noqa: E712
