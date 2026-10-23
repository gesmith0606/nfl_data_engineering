"""Unit tests for the per-player demand column in scripts/waiver_wire.py.

A room's median winning bid prices a *contested* player. Anchoring a specific
claim on it overpays for anyone the room does not want: in week 7 2026 Jalon
Daniels had been bought for $1, cut the week he won the starting job, and left
unrostered through three straight 13-point starts, while the league median
said $12. His own history was the right anchor and it was one API call away.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)

league_player_moves = waiver_wire.league_player_moves
demand_note = waiver_wire.demand_note


def _tx(adds=None, drops=None, bid=None, status="complete"):
    return {
        "status": status,
        "settings": {"waiver_bid": bid} if bid is not None else {},
        "adds": adds or {},
        "drops": drops or {},
    }


def _legs(monkeypatch, by_leg):
    def fake(url, timeout=None):
        leg = int(url.rstrip("/").rsplit("/", 1)[-1])
        return by_leg.get(leg, [])

    monkeypatch.setattr(waiver_wire.sleeper_http, "fetch_sleeper_json", fake)


def test_collects_adds_and_drops_in_leg_order(monkeypatch):
    _legs(
        monkeypatch, {3: [_tx(adds={"13425": 1}, bid=1)], 4: [_tx(drops={"13425": 1})]}
    )
    moves = league_player_moves("123", 7)
    # Each move carries the roster that made it, so "we cut him" is knowable.
    assert moves["13425"] == [
        {"leg": 3, "bid": 1, "kind": "add", "by": "1"},
        {"leg": 4, "bid": None, "kind": "drop", "by": "1"},
    ]


def test_incomplete_transactions_are_ignored(monkeypatch):
    _legs(monkeypatch, {2: [_tx(adds={"9": 1}, bid=50, status="failed")]})
    assert league_player_moves("123", 7) == {}


def test_a_failing_leg_does_not_sink_the_report(monkeypatch):
    def fake(url, timeout=None):
        if url.endswith("/3"):
            raise RuntimeError("sleeper down")
        return [_tx(adds={"7": 1}, bid=4)] if url.endswith("/2") else []

    monkeypatch.setattr(waiver_wire.sleeper_http, "fetch_sleeper_json", fake)
    assert "7" in league_player_moves("123", 5)


def test_never_rostered_reads_unclaimed():
    assert demand_note(None, 7) == "unclaimed"
    assert demand_note([], 7) == "unclaimed"


def test_currently_held_shows_the_price_paid():
    moves = [{"leg": 5, "bid": 36, "kind": "add"}]
    assert demand_note(moves, 7) == "held $36 wk5"


def test_free_agent_add_reads_free():
    moves = [{"leg": 5, "bid": None, "kind": "add"}]
    assert demand_note(moves, 7) == "held free wk5"


def test_cut_player_carries_last_price_and_weeks_free():
    """The Daniels case: bought for $1, cut at wk4, free ever since."""
    moves = [
        {"leg": 3, "bid": 1, "kind": "add"},
        {"leg": 4, "bid": None, "kind": "drop"},
    ]
    assert demand_note(moves, 7) == "cut wk4 (was $1), free 3wk"


def test_price_comes_from_the_most_recent_add_before_the_cut():
    moves = [
        {"leg": 1, "bid": 2, "kind": "add"},
        {"leg": 2, "bid": None, "kind": "drop"},
        {"leg": 3, "bid": 40, "kind": "add"},
        {"leg": 6, "bid": None, "kind": "drop"},
    ]
    assert demand_note(moves, 7) == "cut wk6 (was $40), free 1wk"


def test_cut_this_week_is_not_negative_weeks_free():
    moves = [
        {"leg": 7, "bid": 3, "kind": "add"},
        {"leg": 7, "bid": None, "kind": "drop"},
    ]
    assert demand_note(moves, 7).endswith("free 0wk")


# --- ESPN: the same column, re-keyed from a league_context transaction frame ---


def _by_name(pairs):
    return {(waiver_wire.normalize_name(n), pos): sid for n, pos, sid in pairs}


def test_tx_frame_rekeys_onto_sleeper_ids():
    import pandas as pd

    tx = pd.DataFrame(
        [
            {"week": 3, "add": "Tyler Allgeier", "drop": "", "bid": 40},
            {"week": 5, "add": "", "drop": "Tyler Allgeier", "bid": None},
        ]
    )
    out = waiver_wire.moves_from_tx(tx, _by_name([("Tyler Allgeier", "RB", "777")]))
    assert out["777"] == [
        {"leg": 3, "bid": 40, "kind": "add"},
        {"leg": 5, "bid": None, "kind": "drop"},
    ]
    assert demand_note(out["777"], 7) == "cut wk5 (was $40), free 2wk"


def test_unresolvable_espn_labels_are_dropped():
    import pandas as pd

    tx = pd.DataFrame([{"week": 4, "add": "espn:4431545", "drop": "", "bid": 12}])
    assert waiver_wire.moves_from_tx(tx, _by_name([("Real Player", "WR", "1")])) == {}


def test_blank_add_and_drop_are_skipped():
    import pandas as pd

    tx = pd.DataFrame([{"week": 4, "add": "", "drop": None, "bid": 1}])
    assert waiver_wire.moves_from_tx(tx, _by_name([("X", "WR", "1")])) == {}


def test_float_and_nan_bids_are_normalised():
    """A pandas column with any blank bid is float, so 40 arrives as 40.0."""
    import pandas as pd

    tx = pd.DataFrame(
        [
            {"week": 2, "add": "Some Guy", "drop": "", "bid": 40},
            {"week": 6, "add": "", "drop": "Some Guy", "bid": None},
        ]
    )
    out = waiver_wire.moves_from_tx(tx, _by_name([("Some Guy", "RB", "9")]))
    assert out["9"][0]["bid"] == 40
    assert out["9"][1]["bid"] is None
    assert demand_note(out["9"], 7) == "cut wk6 (was $40), free 1wk"
