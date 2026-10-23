"""Unit tests for src/yahoo_transactions_page and the Yahoo demand path.

Yahoo's Fantasy API is approval-gated — 401 for read scope, no write scope for
new apps — so the league's own Transactions page is the only source of what
the room has paid for a player. Without it Feetball priced claims off the
league-wide median alone, the statistic that produced three overbids in one
session. The fixture is a real capture of Feetball's page on 2026-10-22.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from src.yahoo_transactions_page import PLAYER_RE, parse_yahoo_transactions

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "yahoo_transactions_feetball_wk7.txt"
)

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)


def _rows():
    return parse_yahoo_transactions(FIXTURE.read_text(encoding="utf-8"))


# --- the player line ---------------------------------------------------------


def test_player_line_parses_name_team_and_position():
    m = PLAYER_RE.match("Evan McPherson Cin - K")
    assert m.group("name") == "Evan McPherson"
    assert m.group("team") == "Cin"
    assert m.group("pos") == "K"


def test_status_suffixes_do_not_break_the_name():
    for line, name in [
        ("Joe Mixon Hou - RB NA", "Joe Mixon"),
        ("Blake Grupe LAR - K IR", "Blake Grupe"),
        ("Christian Kirk SF - WR IR-R", "Christian Kirk"),
    ]:
        assert PLAYER_RE.match(line).group("name") == name


def test_team_defenses_parse():
    m = PLAYER_RE.match("Jets NYJ - DEF")
    assert (m.group("name"), m.group("pos")) == ("Jets", "DEF")


# --- whole records -----------------------------------------------------------


def test_parses_every_record_in_the_capture():
    assert len(_rows()) == 9


def test_waiver_record_carries_the_winning_bid():
    rec = next(r for r in _rows() if r["add"] and r["add"]["name"] == "Evan McPherson")
    assert rec["bid"] == 1
    assert rec["drop"]["name"] == "Cam Little"
    assert rec["team"] == "Teez Nutz"


def test_free_agent_add_has_no_bid():
    rec = next(r for r in _rows() if r["add"] and r["add"]["name"] == "Chris Boswell")
    assert rec["bid"] is None


def test_zero_dollar_waiver_is_a_bid_of_zero_not_missing():
    rec = next(
        r for r in _rows() if r["add"] and r["add"]["name"] == "Tyrone Tracy Jr."
    )
    assert rec["bid"] == 0


def test_drop_only_record_has_no_add():
    rec = next(r for r in _rows() if r["drop"] and r["drop"]["name"] == "Najee Harris")
    assert rec["add"] is None
    assert rec["team"] == "One Giant Mess"


def test_our_own_defense_swap_is_captured():
    rec = next(r for r in _rows() if r["team"] == "The Oracle")
    assert rec["add"]["name"] == "Jets"
    assert rec["drop"]["name"] == "Colts"
    assert rec["bid"] == 1


def test_empty_and_junk_text_yield_nothing():
    assert parse_yahoo_transactions("") == []
    assert parse_yahoo_transactions("no records here\njust prose\n") == []


# --- the demand history built from it ---------------------------------------


def _by_name(pairs):
    from src.sleeper_player_map import normalize_name

    return {(normalize_name(n), pos): sid for n, pos, sid in pairs}


def test_same_leg_moves_keep_page_order():
    """Tracy was added then cut in the same week; the page lists newest first."""
    moves = waiver_wire.moves_from_yahoo(
        FIXTURE.read_text(encoding="utf-8"),
        _by_name([("Tyrone Tracy Jr.", "RB", "3")]),
        2026,
    )
    assert [m["kind"] for m in moves["3"]] == ["add", "drop"]
    assert waiver_wire.demand_note(moves["3"], 7).startswith("cut wk6")


def test_a_held_player_reads_as_held_at_his_price():
    moves = waiver_wire.moves_from_yahoo(
        FIXTURE.read_text(encoding="utf-8"),
        _by_name([("Evan McPherson", "K", "1")]),
        2026,
    )
    assert waiver_wire.demand_note(moves["1"], 7) == "held $1 wk6"


def test_unknown_players_are_dropped_not_guessed():
    moves = waiver_wire.moves_from_yahoo(
        FIXTURE.read_text(encoding="utf-8"),
        _by_name([("Nobody Here", "WR", "9")]),
        2026,
    )
    assert moves == {}


# --- date to week ------------------------------------------------------------


def test_transaction_dates_map_to_the_nfl_week():
    """Matches Sleeper's own convention: a Tuesday claim files under the prior leg."""
    assert waiver_wire.nfl_week_for_date("Sep 12, 1:00 pm", 2026) == 1
    assert waiver_wire.nfl_week_for_date("Oct 21, 4:52 am", 2026) == 6


def test_january_dates_roll_into_the_next_calendar_year():
    assert waiver_wire.nfl_week_for_date("Jan 3, 1:00 pm", 2026) == 17


def test_unparseable_date_is_skipped_not_fatal():
    assert waiver_wire.nfl_week_for_date("sometime last week", 2026) is None
