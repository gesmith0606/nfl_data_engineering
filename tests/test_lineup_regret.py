"""Tests for scripts/backtest_lineups.py — points left on the bench.

George, 2026-10-23: "our current ones have not been good." Before building a
fourth lineup path alongside lineup_setter, roster_optimizer and
lineup_builder, measure the ones that exist. The metric's own optimum has to
be exact, or the regret it reports is noise.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "backtest_lineups", REPO / "scripts" / "backtest_lineups.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["backtest_lineups"] = m
    spec.loader.exec_module(m)
    return m


POS = {"qb": "QB", "qb2": "QB", "rb": "RB", "rb2": "RB", "wr": "WR", "te": "TE"}


def test_crossing_flex_slots_need_an_exact_solve_not_a_greedy_fill():
    """WRRB_FLEX(RB/WR) + REC_FLEX(WR/TE): greedy scores 24, the optimum is 25.

    A greedy fill is order-dependent here, and a regret metric whose own
    optimum depends on iteration order is not worth measuring against.
    """
    bl = _mod()
    pts = {"wr": 20.0, "rb": 5.0, "te": 4.0}
    assert bl.optimal_points(["WRRB_FLEX", "REC_FLEX"], list(pts), pts, POS) == 25.0


def test_a_flex_takes_the_best_player_it_is_allowed():
    bl = _mod()
    pts = {"rb": 5.0, "wr": 9.0, "qb": 30.0}
    # FLEX excludes QB, so the 30 is unreachable from that slot alone.
    assert bl.optimal_points(["FLEX"], list(pts), pts, POS) == 9.0
    # SUPER_FLEX does accept him.
    assert bl.optimal_points(["SUPER_FLEX"], list(pts), pts, POS) == 30.0


def test_a_player_can_only_fill_one_slot():
    bl = _mod()
    pts = {"wr": 20.0}
    assert bl.optimal_points(["WR", "FLEX"], ["wr"], pts, POS) == 20.0


def test_unknown_slots_and_empty_pools_score_zero_not_crash():
    bl = _mod()
    assert bl.optimal_points(["BN"], ["wr"], {"wr": 5.0}, POS) == 0.0
    assert bl.optimal_points(["WR"], [], {}, POS) == 0.0


def test_a_bye_week_is_not_counted_as_a_perfect_lineup():
    """Zero points everywhere is a bye or a pre-kickoff read, not a mistake."""
    bl = _mod()
    assert (
        bl.week_regret(
            {"players_points": {}, "starters": [], "players": []}, ["WR"], POS
        )
        is None
    )
    assert (
        bl.week_regret(
            {"players_points": {"wr": 0.0}, "starters": ["wr"], "players": ["wr"]},
            ["WR"],
            POS,
        )
        is None
    )


def test_regret_is_optimal_minus_what_was_actually_started():
    bl = _mod()
    roster = {
        "players_points": {"wr": 20.0, "te": 4.0},
        "starters": ["te"],  # started the wrong one
        "players": ["wr", "te"],
    }
    actual, best = bl.week_regret(roster, ["FLEX"], POS)
    assert (actual, best) == (4.0, 20.0)


def test_a_starter_who_scored_nothing_still_counts_as_started():
    """Otherwise a zeroed starter would look like an empty slot, not a loss."""
    bl = _mod()
    roster = {
        "players_points": {"wr": 0.0, "te": 9.0},
        "starters": ["wr"],
        "players": ["wr", "te"],
    }
    actual, best = bl.week_regret(roster, ["FLEX"], POS)
    assert actual == 0.0 and best == 9.0
