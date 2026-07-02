"""Offline tests for the live draft engine + adapter (Phase 86).

Replays the Phase 85 fixture draft deterministically; no network. The fixture's
pick draft_slots follow a 3-team snake (1,2,3,3,2,1,1,2,...), so tests override
``settings.teams`` to 3 to make slot/turn math intuitive.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from src import sleeper_draft
from src.draft_adapter import DraftAdapter, SleeperAdapter
from src.draft_models import DraftState, PickEvent
from src.live_draft_engine import LiveDraftEngine
from src.sleeper_draft import state_from_sleeper
from src import sleeper_player_map

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sleeper_draft")


def _load(name: str):
    with open(os.path.join(_FIXTURE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def draft_raw():
    d = _load("draft.json")
    d["settings"] = {**d["settings"], "teams": 3}  # 3-team snake for intuitive math
    return d


@pytest.fixture
def picks_raw():
    return _load("picks.json")


@pytest.fixture
def projections_df():
    return pd.DataFrame(_load("projections_sample.json"))


@pytest.fixture
def adapter():
    a = SleeperAdapter()
    # Pre-seed the player index from the fixture registry so map_picks does no network.
    a._player_index = sleeper_player_map.build_player_index(
        _load("sleeper_players_sample.json")
    )
    return a


def _state(draft_raw, picks, n=None):
    return state_from_sleeper(draft_raw, picks)


# ---------------------------------------------------------------------------
# ENG-05: adapter protocol
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sleeper_adapter_satisfies_protocol(adapter):
    assert isinstance(adapter, DraftAdapter)
    assert adapter.platform == "sleeper"


@pytest.mark.unit
def test_adapter_delegates_resolve_and_load(monkeypatch, adapter, draft_raw, picks_raw):
    monkeypatch.setattr(
        sleeper_draft,
        "resolve_active_draft",
        lambda *a, **k: {"found": True, "draft_id": "d1"},
    )
    monkeypatch.setattr(
        sleeper_draft, "load_draft_state", lambda d: _state(draft_raw, picks_raw)
    )
    assert adapter.resolve_draft("george", "2026")["draft_id"] == "d1"
    assert adapter.load_state("d1").n_teams == 3


# ---------------------------------------------------------------------------
# ENG-01/02: diff, rosters, turn math
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_replay_rosters_and_on_clock(adapter, draft_raw, picks_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=3)
    res = engine.update(_state(draft_raw, picks_raw))
    assert len(res.new_picks) == 8
    # Rosters grouped by draft_slot (3-team snake).
    assert {m.get("player_name") for m in engine.rosters[3]} == {
        "Travis Kelce",
        "Ja'Marr Chase",
    }
    assert len(engine.rosters[1]) == 3  # Mahomes, Harrison, SF DST
    # After 8 picks, pick 9 (round 3, odd) is slot 3 → my turn.
    assert res.turn.on_clock_pick_no == 9
    assert res.turn.on_clock_slot == 3
    assert res.turn.is_my_turn is True
    assert res.turn.my_next_pick_no == 9


@pytest.mark.unit
def test_diff_is_idempotent(adapter, draft_raw, picks_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    engine.update(_state(draft_raw, picks_raw))
    again = engine.update(_state(draft_raw, picks_raw))
    assert again.new_picks == []  # no duplicate emission


@pytest.mark.unit
def test_incremental_diff_emits_only_new(adapter, draft_raw, picks_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    first = engine.update(_state(draft_raw, picks_raw[:3]))
    assert len(first.new_picks) == 3
    second = engine.update(_state(draft_raw, picks_raw))
    assert [p.pick_no for p in second.new_picks] == [4, 5, 6, 7, 8]


@pytest.mark.unit
def test_my_slot_from_user_id(adapter, draft_raw, picks_raw, projections_df):
    # draft_order maps u_charlie -> slot 3 in the fixture.
    engine = LiveDraftEngine(adapter, projections_df, my_user_id="u_charlie")
    engine.update(_state(draft_raw, picks_raw))
    assert engine.my_slot == 3


# ---------------------------------------------------------------------------
# ENG-03: recommendations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_recommendations_nonempty_on_turn(
    adapter, draft_raw, picks_raw, projections_df
):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=3)
    engine.update(_state(draft_raw, picks_raw))
    recs, reasoning = engine.recommendations(top_n=5)
    assert not recs.empty
    # Drafted players are off the board.
    assert "Ja'Marr Chase" not in set(recs["player_name"])
    assert isinstance(reasoning, str) and reasoning


# ---------------------------------------------------------------------------
# ENG-04: key moments
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pick_grade_and_steal_reach(adapter, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    # Steal: taken at pick 15, ADP rank 3 → fell 12 spots. (rank 15 exists in pool)
    pe_steal = PickEvent(15, 2, 1, 1, "u", "x", "Some", "Player", "WR", "BUF", False)
    steal = engine._pick_moments(pe_steal, {"adp_rank": 3, "vorp": 40.0, "pick_no": 15})
    kinds = {m.kind for m in steal}
    assert "steal" in kinds
    assert "grade" in kinds  # par value exists at this pick
    # Reach: taken at pick 5, ADP rank 20 → 15 spots early.
    pe_reach = PickEvent(5, 1, 1, 1, "u", "x", "Some", "Player", "WR", "BUF", False)
    reach = engine._pick_moments(pe_reach, {"adp_rank": 20, "vorp": 40.0, "pick_no": 5})
    assert "reach" in {m.kind for m in reach}


@pytest.mark.unit
def test_positional_run_detected(adapter, draft_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    rb_picks = [
        {
            "pick_no": i,
            "round": 1,
            "draft_slot": i,
            "roster_id": i,
            "picked_by": "u",
            "player_id": f"r{i}",
            "metadata": {
                "first_name": "RB",
                "last_name": str(i),
                "position": "RB",
                "team": "NYJ",
            },
        }
        for i in range(1, 5)
    ]
    res = engine.update(state_from_sleeper(draft_raw, rb_picks))
    assert any(m.kind == "positional_run" for m in res.key_moments)


@pytest.mark.unit
def test_value_drop_detected(adapter, draft_raw, projections_df):
    # No picks yet but force a late on-clock pick: feed a long filler draft of
    # players NOT in projections so the elite board stays intact while pick_no climbs.
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    filler = [
        {
            "pick_no": i,
            "round": 1,
            "draft_slot": ((i - 1) % 3) + 1,
            "roster_id": 1,
            "picked_by": "u",
            "player_id": f"z{i}",
            "metadata": {
                "first_name": "Zz",
                "last_name": str(i),
                "position": "K",
                "team": "NYJ",
            },
        }
        for i in range(1, 21)
    ]
    res = engine.update(state_from_sleeper(draft_raw, filler))
    # Rank-1 projection player is still available at pick 21 → value drop.
    assert any(m.kind == "value_drop" for m in res.key_moments)
