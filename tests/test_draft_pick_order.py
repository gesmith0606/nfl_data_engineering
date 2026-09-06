"""Explicit custom pick order (traded picks + keeper slots) — Feetball 2026.

Covers the parser on the committed Feetball file, the engine's turn / next-pick
/ picks-remaining math under that order, manual-mode slot assignment, and that
the default (no order) snake behaviour is unchanged.
"""

from __future__ import annotations

import importlib.util
import json
import os

import pandas as pd
import pytest

from src.draft_models import DraftState, PickEvent
from src.draft_pick_order import apply_pick_order, load_pick_order, parse_pick_order
from src.live_draft_engine import LiveDraftEngine

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_ORDER_FILE = os.path.join(_ROOT, "data", "draft", "feetball_2026_pick_order.txt")
_SCRIPT = os.path.join(_ROOT, "scripts", "draft_live.py")
_spec = importlib.util.spec_from_file_location("draft_live", _SCRIPT)
draft_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_live)

# docs/FEETBALL_2026_DRAFT_ORDER.md — The Oracle (slot 6) pick inventory.
ORACLE_LIVE = (6, 13, 15, 21, 26, 34, 35, 46, 55, 66, 75, 106, 115, 146, 155)
ORACLE_KEEPER_SLOTS = (86, 126)  # 9.06 Burden, 13.06 Loveland
ORACLE = 6


@pytest.fixture(scope="module")
def order():
    return load_pick_order(_ORDER_FILE)


def _proj() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_name": ["A", "B"],
            "position": ["WR", "RB"],
            "team": ["FA", "FA"],
            "projected_points": [10.0, 9.0],
        }
    )


def _engine(order, picks_made: int, my_slot: int = ORACLE, use_order: bool = True):
    """Engine at ``picks_made`` picks in, with (or without) the Feetball order."""
    n = order.n_teams
    state = DraftState(
        draft_id="t",
        status="drafting",
        draft_type="snake",
        season="2026",
        n_teams=n,
        rounds=order.rounds,
        scoring_format="half_ppr",
        roster_format="yahoo_feetball",
        draft_order={},
        slot_to_roster_id={},
        picks=tuple(
            PickEvent(
                pick_no=s.pick_no,
                round=s.round,
                draft_slot=s.draft_slot,
                roster_id=None,
                picked_by="",
                sleeper_player_id=str(s.pick_no),
                first_name="P",
                last_name=str(s.pick_no),
                position="WR",
                team="FA",
                is_keeper=s.is_keeper,
            )
            for s in order.slots[:picks_made]
        ),
        pick_order=order.slots if use_order else (),
    )
    eng = LiveDraftEngine(
        adapter=draft_live._DummyAdapter(), projections_df=_proj(), my_slot=my_slot
    )
    eng.state = state
    eng._seen_pick_no = picks_made
    return eng


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_feetball_file_matches_doc_inventory(order):
    assert order.n_teams == 10
    assert order.rounds == 17
    assert len(order.slots) == 170
    assert len(order.keeper_slots) == 25
    assert order.labels[ORACLE] == "Oracle"
    assert order.live_picks_for(ORACLE) == ORACLE_LIVE
    assert tuple(s.pick_no for s in order.keeper_slots if s.draft_slot == ORACLE) == (
        ORACLE_KEEPER_SLOTS
    )
    # Overall numbering counts keeper slots (Yahoo: 4.06 == overall 36).
    assert order.slots[35] == order.slots[35].__class__(36, 4, 5, True)
    # pick_no is contiguous 1..N so the engine may index by pick_no - 1.
    assert [s.pick_no for s in order.slots] == list(range(1, 171))


@pytest.mark.unit
def test_parser_accepts_comments_bold_and_keeper_names():
    text = [
        "# comment",
        "R1: A, B, **C**",
        "R2: C(K=Somebody), b, A  # trailing comment",
    ]
    o = parse_pick_order(text)
    assert o.n_teams == 3 and o.rounds == 2
    assert [s.draft_slot for s in o.slots] == [1, 2, 3, 3, 2, 1]
    assert [s.is_keeper for s in o.slots] == [False] * 3 + [True, False, False]


@pytest.mark.unit
@pytest.mark.parametrize(
    "lines,msg",
    [
        (["R1: A, B", "R2: A"], "expected 2"),
        (["R1: A, B", "R2: A, Z"], "not in round 1"),
        (["R1: A, B", "R3: A, B"], "rounds must be"),
        (["R1: A, A"], "exactly once"),
        (["A, B"], "expected 'R<n>:"),
    ],
)
def test_parser_validation(lines, msg):
    with pytest.raises(ValueError, match=msg):
        parse_pick_order(lines)


# ---------------------------------------------------------------------------
# Engine — turn detection, next pick, picks remaining under the order
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("on_clock", [13, 15, 34, 35])
def test_is_my_turn_on_traded_picks(order, on_clock):
    eng = _engine(order, picks_made=on_clock - 1)
    turn = eng.turn_info()
    assert turn.on_clock_pick_no == on_clock
    assert turn.on_clock_slot == ORACLE
    assert turn.is_my_turn is True


@pytest.mark.unit
def test_not_my_turn_at_pick_14(order):
    turn = _engine(order, picks_made=13).turn_info()
    assert turn.on_clock_pick_no == 14
    assert turn.on_clock_slot == 7  # Achane at 2.04
    assert turn.is_my_turn is False
    assert turn.my_next_pick_no == 15


@pytest.mark.unit
@pytest.mark.parametrize(
    "start,expected",
    [(7, 13), (14, 15), (16, 21), (36, 46), (76, 106), (107, 115), (156, None)],
)
def test_my_next_pick_no_skips_keepers_and_traded_rounds(order, start, expected):
    """From 76: skip the 9.06 keeper slot (86) and the traded-away R10 -> 106."""
    eng = _engine(order, picks_made=start - 1)
    assert eng._my_next_pick_no(start, order.n_teams) == expected


@pytest.mark.unit
def test_clock_skips_keeper_slot(order):
    """Pick 36 (4.06) is Murtaugh's keeper — after pick 35 the clock is at 37."""
    eng = _engine(order, picks_made=35)
    turn = eng.turn_info()
    assert turn.on_clock_pick_no == 37
    assert turn.on_clock_slot == 4  # One Giant Mess at 4.07
    assert turn.is_my_turn is False
    assert turn.my_next_pick_no == 46
    # A platform that reports keeper picks as picks lands on the same clock.
    eng2 = _engine(order, picks_made=36)
    assert eng2.turn_info().on_clock_pick_no == 37


@pytest.mark.unit
def test_my_keeper_slot_is_never_my_turn(order):
    eng = _engine(order, picks_made=85)  # 9.06 (#86) is the Burden keeper slot
    turn = eng.turn_info()
    assert turn.on_clock_pick_no == 87
    assert turn.is_my_turn is False
    assert turn.my_next_pick_no == 106


@pytest.mark.unit
def test_back_to_back_picks_next_pick_is_the_adjacent_one(order):
    """On the clock at 34, my next pick is 35 (opportunity cost ~0)."""
    eng = _engine(order, picks_made=33)
    kw = eng._turn_kwargs()
    assert kw["next_pick_no"] == 35
    assert kw["my_picks_remaining"] == 10  # 34,35,46,55,66,75,106,115,146,155


@pytest.mark.unit
def test_picks_remaining_counts_live_picks_only(order):
    assert _engine(order, picks_made=0)._turn_kwargs()["my_picks_remaining"] == 15
    assert _engine(order, picks_made=105)._turn_kwargs()["my_picks_remaining"] == 4


@pytest.mark.unit
def test_opponent_needs_excludes_keeper_slots(order):
    """After my pick 35, before my 46: live opponents only (36 Murtaugh(K) is
    not a live pick, but Murtaugh still picks live at 45 so is counted once)."""
    eng = _engine(order, picks_made=35)
    eng.update(eng.state)  # builds the board
    turn = eng.turn_info()
    assert not turn.is_my_turn and turn.on_clock_pick_no == 37
    assert turn.my_next_pick_no == 46
    live_slots = {
        eng._slot_at(p) for p in range(37, 46) if not eng._is_keeper_slot(p)
    } - {ORACLE}
    # 37 One Giant Mess, 39 Dude, 44 Billiever, 45 Murtaugh (36/38/40-43 keepers)
    assert live_slots == {2, 4, 5, 9}
    needs = draft_live.opponent_needs(eng)
    assert needs["RB"] == len(live_slots)  # nobody has drafted (blank rosters)


# ---------------------------------------------------------------------------
# Default (no order) behaviour unchanged
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_without_order_snake_arithmetic_is_used(order):
    eng = _engine(order, picks_made=12, use_order=False)
    n = order.n_teams
    for p in range(1, 41):
        assert eng._slot_at(p) == LiveDraftEngine._slot_on_clock(p, n, "snake")
        assert eng._is_keeper_slot(p) is False
    turn = eng.turn_info()
    assert turn.on_clock_pick_no == 13
    assert turn.on_clock_slot == 8  # plain snake: pick 13 is slot 8 of 10
    assert turn.is_my_turn is False
    assert turn.my_next_pick_no == 15  # slot 6 in round 2 of a 10-team snake
    assert eng._turn_kwargs()["my_picks_remaining"] == 16  # 17 rounds, 1 used


# ---------------------------------------------------------------------------
# apply_pick_order — platform states
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_pick_order_rederives_slot_and_round(order):
    """A platform draft_slot (team id) is replaced by the order's round-1 slot."""
    pick = PickEvent(
        pick_no=13,
        round=2,
        draft_slot=99,
        roster_id=None,
        picked_by="",
        sleeper_player_id="x",
        first_name="P",
        last_name="13",
        position="WR",
        team="FA",
        is_keeper=False,
    )
    state = DraftState(
        draft_id="y",
        status="drafting",
        draft_type="snake",
        season="2026",
        n_teams=0,
        rounds=0,
        scoring_format="half_ppr",
        roster_format="yahoo_feetball",
        draft_order={},
        slot_to_roster_id={},
        picks=(pick,),
    )
    new = apply_pick_order(state, order)
    assert new.n_teams == 10 and new.rounds == 17
    assert new.picks[0].draft_slot == ORACLE and new.picks[0].round == 2
    assert len(new.pick_order) == 170
    assert state.picks[0].draft_slot == 99  # original untouched (frozen)


# ---------------------------------------------------------------------------
# Manual mode — --add-pick fills live slots in order
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_manual_state_assigns_live_slots_from_order(order):
    names = [f"Player {i}" for i in range(1, 13)]
    state = draft_live.build_manual_state(
        names,
        _proj(),
        12,
        "snake",
        "half_ppr",
        "yahoo_feetball",
        "2026",
        pick_order=order,
    )
    assert state.n_teams == 10 and state.rounds == 17
    assert [p.pick_no for p in state.picks] == list(range(1, 13))
    assert state.picks[5].draft_slot == ORACLE  # 1.06
    assert state.picks[11].draft_slot == 9 and state.picks[11].round == 2  # 2.02
    eng = LiveDraftEngine(
        adapter=draft_live._DummyAdapter(), projections_df=_proj(), my_slot=ORACLE
    )
    turn = eng.update(state).turn
    assert turn.on_clock_pick_no == 13 and turn.on_clock_slot == ORACLE
    assert turn.is_my_turn is True
    assert turn.my_next_pick_no == 13


@pytest.mark.unit
def test_manual_state_skips_keeper_slots(order):
    """35 typed picks: the 36th live slot is 37 (4.07), never the 4.06 keeper."""
    names = [f"Player {i}" for i in range(1, 36)]
    state = draft_live.build_manual_state(
        names,
        _proj(),
        12,
        "snake",
        "half_ppr",
        "yahoo_feetball",
        "2026",
        pick_order=order,
    )
    assert state.picks[-1].pick_no == 35
    more = draft_live.build_manual_state(
        names + ["Player 36"],
        _proj(),
        12,
        "snake",
        "half_ppr",
        "yahoo_feetball",
        "2026",
        pick_order=order,
    )
    assert more.picks[-1].pick_no == 37 and more.picks[-1].draft_slot == 4
    with pytest.raises(ValueError, match="live slots"):
        draft_live.build_manual_state(
            [f"P{i}" for i in range(146)],
            _proj(),
            12,
            "snake",
            "half_ppr",
            "yahoo_feetball",
            "2026",
            pick_order=order,
        )


@pytest.mark.unit
def test_cli_manual_with_pick_order_and_keepers(tmp_path, capsys):
    """End-to-end: 12 typed picks -> pick 13 is mine; keepers file applied in
    manual mode (it used to be silently ignored there)."""
    fixture = os.path.join(
        _ROOT, "tests", "fixtures", "sleeper_draft", "projections_sample.json"
    )
    with open(fixture, encoding="utf-8") as fh:
        proj = pd.DataFrame(json.load(fh))
    proj_csv = tmp_path / "proj.csv"
    proj.to_csv(proj_csv, index=False)
    keepers = tmp_path / "keepers.txt"
    keepers.write_text(
        "# mine\n*Ja'Marr Chase\nChristian McCaffrey\n", encoding="utf-8"
    )
    argv = [
        "--manual",
        "--my-slot",
        str(ORACLE),
        "--pick-order-file",
        _ORDER_FILE,
        "--keepers-file",
        str(keepers),
        "--projections-file",
        str(proj_csv),
        "--adp-file",
        str(tmp_path / "no_adp.csv"),
        "--json",
    ]
    for i in range(1, 13):
        argv += ["--add-pick", f"Player {i}"]
    assert draft_live.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["on_clock_pick"] == 13
    assert out["on_clock_slot"] == ORACLE
    assert out["is_my_turn"] is True
    assert out["my_next_pick_no"] == 13
    # Keepers left the recommendation pool (the file was applied in manual mode).
    recs = [r["player_name"] for r in out["recommendations"]]
    assert "Ja'Marr Chase" not in recs and "Christian McCaffrey" not in recs


@pytest.mark.unit
def test_apply_keepers_file_marks_board(tmp_path):
    fixture = os.path.join(
        _ROOT, "tests", "fixtures", "sleeper_draft", "projections_sample.json"
    )
    with open(fixture, encoding="utf-8") as fh:
        proj = pd.DataFrame(json.load(fh))
    keepers = tmp_path / "keepers.txt"
    keepers.write_text("*Ja'Marr Chase\nChristian McCaffrey\n", encoding="utf-8")
    eng = LiveDraftEngine(
        adapter=draft_live._DummyAdapter(), projections_df=proj, my_slot=1
    )
    eng.update(draft_live._empty_state("standard", "half_ppr", "2026"))
    draft_live._apply_keepers_file(eng, str(keepers), as_json=True)
    assert "Ja'Marr Chase" in [p.get("player_name") for p in eng.board.my_roster]
    avail = set(eng.board.available["player_name"])
    assert "Ja'Marr Chase" not in avail and "Christian McCaffrey" not in avail
