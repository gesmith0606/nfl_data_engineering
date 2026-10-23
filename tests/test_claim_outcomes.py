"""Tests for scripts/backtest_claim_outcomes.py — did our claims actually help?

Everything else in the waiver pipeline is validated against a proxy (the bid
model against what the room paid, the RENTAL tag against snap share). This is
the only check that asks whether the player we added outscored the one we
dropped, so its arithmetic has to be right.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "claim_outcomes", REPO / "scripts" / "backtest_claim_outcomes.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["claim_outcomes"] = m
    spec.loader.exec_module(m)
    return m


def _tx(leg, rid, add, drop, bid, kind="waiver", status="complete"):
    return {
        "leg": leg,
        "status": status,
        "type": kind,
        "adds": {add: rid},
        "drops": {drop: rid},
        "settings": {"waiver_bid": bid},
    }


def test_only_completed_adds_with_a_matching_drop_are_claims():
    co = _mod()
    txns = [
        _tx(2, 8, "A", "B", 16),
        _tx(3, 8, "C", "D", 5, status="failed"),  # lost claim, not a move
        {"leg": 4, "status": "complete", "type": "waiver", "adds": {"E": 8}},  # no drop
        {"leg": 5, "status": "complete", "type": "waiver", "drops": {"F": 8}},  # no add
        _tx(99, 8, "G", "H", 1),  # beyond the window
    ]
    rows = co.claim_rows(txns, through_week=7)
    assert [(r["leg"], r["add"], r["drop"], r["bid"]) for r in rows] == [
        (2, "A", "B", 16)
    ]


def test_a_drop_belonging_to_another_team_is_not_paired_with_our_add():
    """Sleeper puts both sides of a trade in one record, keyed by roster."""
    co = _mod()
    txns = [
        {
            "leg": 3,
            "status": "complete",
            "type": "trade",
            "adds": {"mine": 8, "theirs": 4},
            "drops": {"mine_gone": 8, "theirs_gone": 4},
            "settings": {},
        }
    ]
    rows = co.claim_rows(txns, through_week=7)
    pairs = {(r["roster_id"], r["add"], r["drop"]) for r in rows}
    assert pairs == {("8", "mine", "mine_gone"), ("4", "theirs", "theirs_gone")}


def test_gain_counts_only_weeks_after_the_move():
    co = _mod()
    rows = [
        {
            "leg": 3,
            "roster_id": "8",
            "add": "A",
            "drop": "B",
            "bid": 10,
            "kind": "waiver",
        }
    ]
    points = {
        ("A", 2): 99.0,  # before the add — must not count
        ("A", 4): 10.0,
        ("A", 5): 12.0,
        ("B", 4): 4.0,
        ("B", 5): 3.0,
        ("B", 2): 50.0,  # before — must not count
    }
    (s,) = co.score_claims(rows, points, through_week=5, min_weeks=2)
    assert (s["add_pts"], s["drop_pts"], s["gain"], s["weeks"]) == (22.0, 7.0, 15.0, 2)


def test_a_claim_too_recent_to_judge_is_not_scored():
    """A week-7 add has had no football; scoring it as 0 would be a lie."""
    co = _mod()
    rows = [
        {
            "leg": 7,
            "roster_id": "8",
            "add": "A",
            "drop": "B",
            "bid": 10,
            "kind": "waiver",
        }
    ]
    assert co.score_claims(rows, {}, through_week=7, min_weeks=2) == []
    assert co.score_claims(rows, {}, through_week=9, min_weeks=2)


def test_verdict_compares_medians_so_one_outlier_cannot_carry_it():
    """Our mean was +20.2pt on one Brissett; our median was +1.6 vs the room's +6.3."""
    co = _mod()
    ours = [
        {"gain": 1.0, "bid": 10, "leg": 1},
        {"gain": 1.0, "bid": 10, "leg": 2},
        {"gain": 200.0, "bid": 10, "leg": 3},
    ]
    room = [
        {"gain": 6.0, "bid": 10, "leg": 1},
        {"gain": 6.0, "bid": 10, "leg": 2},
        {"gain": 6.0, "bid": 10, "leg": 3},
    ]
    lines = "\n".join(co.verdict(ours, room))
    assert "BEHIND THE ROOM" in lines, "a single outlier must not flip the verdict"

    ours_good = [{"gain": 9.0, "bid": 10, "leg": i} for i in range(3)]
    assert "BEATING THE ROOM" in "\n".join(co.verdict(ours_good, room))


def test_too_few_claims_refuses_to_render_a_verdict():
    co = _mod()
    thin = [{"gain": 5.0, "bid": 1, "leg": 1}]
    assert "too few" in "\n".join(co.verdict(thin, thin))
