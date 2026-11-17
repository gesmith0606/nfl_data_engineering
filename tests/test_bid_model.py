"""Unit tests for the waiver bid model in scripts/waiver_wire.py.

Three bids in one session were sized off the room's median winning bid and
all three were wrong: Omar Cooper at $22 (needed $10), Kendre Miller at $55
(lost anyway), Jalon Daniels at $8 (won at $1). The median prices a
*contested* player; most claims are not contested. Backtested on 51 real
Mantis winning bids the model's median absolute error is $6 against the
median rule's $22.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)

starters_required = waiver_wire.starters_required
suggest_bid = waiver_wire.suggest_bid
team_bid_stats = waiver_wire.team_bid_stats
thin_at = waiver_wire.thin_at


# --- starting requirements ---------------------------------------------------


def test_counts_dedicated_slots_and_ignores_flex():
    need = starters_required(
        ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "BN"]
    )
    assert need == {"QB": 1, "RB": 2, "WR": 3, "TE": 1}


# --- can a rival field the position this week? -------------------------------
#
# This used to ask "does the team lack a surplus" (healthy <= required). In a
# one-QB league that is true of nearly every team by construction, so week 8
# 2026 the model reported three La Liga rivals "thin at QB" whose quarterbacks
# all played, and escalated the bid to $14 — a quarter of the budget — for a
# bye-week fill. The correct count that week was zero. The test is now whether
# he is short THIS week; a rival who might need the spot after some future
# injury is not bidding against you now.

REG = {
    "1": {"position": "RB", "injury_status": None, "team": "BAL"},
    "2": {"position": "RB", "injury_status": None, "team": "BUF"},
    "3": {"position": "RB", "injury_status": "Out", "team": "CIN"},
    "4": {"position": "RB", "injury_status": None, "team": "DAL"},
    "5": {"position": "WR", "injury_status": None, "team": "DEN"},
    "6": {"position": "QB", "injury_status": None, "team": "SF"},
    "7": {"position": "QB", "injury_status": None, "team": "DAL"},
}
#: Everyone in REG except SF, who are on bye.
PLAYING = {"BAL", "BUF", "CIN", "DAL", "DEN"}


def test_team_at_exactly_its_requirement_can_field_it():
    """Two healthy RBs against a two-RB requirement is not a need."""
    assert thin_at({"players": ["1", "2"]}, REG, "RB", 2) is False


def test_team_one_body_short_is_not_a_rival():
    """It fills from flex or streams cheaply; it is not bidding against us.

    Counting these put most of a 10-team dynasty league in the market during
    a four-bye week and priced no-help wideouts at $94.
    """
    assert thin_at({"players": ["1"]}, REG, "RB", 2) is False


def test_team_with_nobody_to_start_is_a_rival():
    assert thin_at({"players": []}, REG, "RB", 2) is True


def test_team_with_surplus_is_not_thin():
    assert thin_at({"players": ["1", "2", "4"]}, REG, "RB", 2) is False
    assert thin_at({"players": ["1", "2", "4", "5"]}, REG, "RB", 1) is False


def test_injured_reserve_and_taxi_players_do_not_count():
    """A stashed body cannot start, so a team holding only one has nobody."""
    assert thin_at({"players": ["1"]}, REG, "RB", 1) is False
    assert thin_at({"players": ["1"], "reserve": ["1"]}, REG, "RB", 1) is True
    assert thin_at({"players": ["1"], "taxi": ["1"]}, REG, "RB", 1) is True


def test_blocked_players_do_not_count_as_depth():
    """ "3" is Out, so a team holding only him has nobody to start."""
    assert thin_at({"players": ["3"]}, REG, "RB", 1) is True
    assert thin_at({"players": ["1"]}, REG, "RB", 1) is False


def test_a_quarterback_on_bye_cannot_fill_the_slot():
    """The La Liga week-8 case, both sides of it.

    Our only QB was Brock Purdy and San Francisco were on bye; every rival's
    quarterback played. Before this, both read "thin".
    """
    mine = {"players": ["6"]}  # SF QB, on bye
    rival = {"players": ["7"]}  # DAL QB, playing
    assert thin_at(mine, REG, "QB", 1, PLAYING) is True
    assert thin_at(rival, REG, "QB", 1, PLAYING) is False


def test_without_a_playing_set_a_bye_still_counts_as_available():
    """Callers that cannot resolve kickoffs keep the old, looser behaviour."""
    assert thin_at({"players": ["6"]}, REG, "QB", 1) is False


# --- per-team bid history ----------------------------------------------------


def _tx(rid, bid, pid="99"):
    return {
        "status": "complete",
        "roster_ids": [rid],
        "adds": {pid: rid},
        "settings": {"waiver_bid": bid},
    }


def test_team_bid_stats_summarises_each_team():
    stats = team_bid_stats([_tx(1, 10), _tx(1, 30), _tx(1, 50), _tx(2, 4)])
    assert stats["1"]["n"] == 3
    assert stats["1"]["median"] == 30
    assert stats["1"]["max"] == 50
    assert stats["2"]["median"] == 4


def test_zero_and_missing_bids_are_not_history():
    assert team_bid_stats([_tx(1, 0), {"status": "complete", "roster_ids": [1]}]) == {}


# --- the bid itself ----------------------------------------------------------

CUT_CHEAP = [
    {"leg": 3, "bid": 1, "kind": "add"},
    {"leg": 4, "bid": None, "kind": "drop"},
]


def test_a_player_this_room_cut_cheaply_costs_what_it_paid():
    """The Daniels case: bought $1, cut, three weeks free. Won at $1."""
    bid, why = suggest_bid(CUT_CHEAP, [], room_median=12, my_faab=380, current_leg=7)
    assert bid == 1
    assert "cut him" in why


def test_no_credible_rival_prices_well_under_the_room_median():
    """A fifth of the median: swept on 51 real bids, it halves wasted FAAB."""
    bid, why = suggest_bid(None, [], room_median=25, my_faab=400, current_leg=7)
    assert bid == 5
    assert "thin here and able to spend" in why


def test_credible_rivals_push_the_bid_above_their_top_median():
    bid, why = suggest_bid(None, [20, 30], room_median=12, my_faab=1000, current_leg=7)
    assert bid == 36
    assert "2 rival(s)" in why


def test_never_spends_more_than_a_quarter_of_the_budget():
    bid, _ = suggest_bid(None, [400], room_median=50, my_faab=200, current_leg=7)
    assert bid == 50


def test_a_recently_cut_player_is_not_chased_to_the_moon():
    """Rivals may be rich, but the room just cut him for nothing."""
    bid, _ = suggest_bid(CUT_CHEAP, [90], room_median=12, my_faab=1000, current_leg=7)
    assert bid == 12


def test_a_bid_is_never_zero():
    bid, _ = suggest_bid(None, [], room_median=0, my_faab=100, current_leg=7)
    assert bid >= 1


# --- the tail: context, not prediction --------------------------------------


def test_room_max_is_surfaced_when_it_dwarfs_the_suggestion():
    """Escalating toward the tail made the backtest worse, so say it instead."""
    bid, why = suggest_bid(
        None, [10], room_median=12, my_faab=1000, current_leg=7, room_max=450
    )
    assert bid == 12
    assert "gone as high as $450" in why


def test_room_max_is_silent_when_the_bid_is_already_in_range():
    _bid, why = suggest_bid(
        None, [100], room_median=12, my_faab=1000, current_leg=7, room_max=200
    )
    assert "as high as" not in why


def test_room_max_never_changes_the_number():
    plain, _ = suggest_bid(None, [10], room_median=12, my_faab=1000, current_leg=7)
    noted, _ = suggest_bid(
        None, [10], room_median=12, my_faab=1000, current_leg=7, room_max=450
    )
    assert plain == noted


def test_a_player_we_cut_is_re_bought_at_the_minimum_only():
    """Week 7 2026: the model wanted $55 for Drew Lock, whom we cut for $55."""
    moves = [
        {"leg": 1, "bid": 55, "kind": "add", "by": "6"},
        {"leg": 4, "bid": None, "kind": "drop", "by": "6"},
    ]
    bid, why = suggest_bid(
        moves, [40], room_median=23, my_faab=1000, current_leg=7, my_roster_id="6"
    )
    assert bid == 1
    assert "WE cut him" in why


def test_another_team_cutting_him_does_not_trigger_the_rule():
    moves = [
        {"leg": 1, "bid": 55, "kind": "add", "by": "9"},
        {"leg": 4, "bid": None, "kind": "drop", "by": "9"},
    ]
    bid, why = suggest_bid(
        moves, [], room_median=23, my_faab=1000, current_leg=7, my_roster_id="6"
    )
    assert "WE cut him" not in why
    assert bid == 55


def test_without_a_roster_id_the_rule_cannot_fire():
    moves = [{"leg": 4, "bid": 55, "kind": "drop", "by": "6"}]
    _bid, why = suggest_bid(moves, [], room_median=23, my_faab=1000, current_leg=7)
    assert "WE cut him" not in why
