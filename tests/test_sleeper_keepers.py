"""Offline tests for keeper-league support (Phase 90).

Covers Sleeper league-roster fetch, SleeperAdapter.get_keepers, and
LiveDraftEngine.preload_keepers. No network — registry index is pre-seeded and
roster fetch is monkeypatched.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from src import sleeper_http, sleeper_player_map
from src.draft_adapter import SleeperAdapter
from src.live_draft_engine import LiveDraftEngine
from src.sleeper_draft import state_from_sleeper

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sleeper_draft")


def _load(name: str):
    with open(os.path.join(_FIXTURE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def projections_df():
    return pd.DataFrame(_load("projections_sample.json"))


@pytest.fixture
def adapter():
    a = SleeperAdapter()
    a._player_index = sleeper_player_map.build_player_index(
        _load("sleeper_players_sample.json")
    )
    return a


@pytest.fixture
def draft_raw():
    d = _load("draft.json")
    d["settings"] = {**d["settings"], "teams": 3}
    return d


@pytest.mark.unit
def test_get_league_rosters_failopen(monkeypatch):
    monkeypatch.setattr(sleeper_http, "fetch_sleeper_json", lambda *a, **k: {})
    assert sleeper_http.get_league_rosters("L1") == []
    assert sleeper_http.get_league_rosters("") == []


@pytest.mark.unit
def test_get_keepers_builds_all_and_mine(monkeypatch, adapter):
    monkeypatch.setattr(
        sleeper_http, "get_league_rosters", lambda lid: _load("league_rosters.json")
    )
    info = adapter.get_keepers("L1", my_user_id="u_alpha")
    assert len(info["all"]) == 6
    assert {p.full_name for p in info["mine"]} == {
        "Patrick Mahomes",
        "Marvin Harrison Jr.",
    }
    # Keepers are flagged and carry resolved position from the registry.
    assert all(p.is_keeper for p in info["all"])
    assert {p.position for p in info["mine"]} == {"QB", "WR"}


@pytest.mark.unit
def test_preload_keepers_marks_board_and_my_roster(
    monkeypatch, adapter, projections_df, draft_raw
):
    monkeypatch.setattr(
        sleeper_http, "get_league_rosters", lambda lid: _load("league_rosters.json")
    )
    engine = LiveDraftEngine(adapter, projections_df, my_user_id="u_alpha", my_slot=1)
    engine.update(state_from_sleeper(draft_raw, []))  # builds the board (no picks yet)

    n = engine.preload_keepers(adapter.get_keepers("L1", "u_alpha"))
    assert n == 6  # all six kept players mapped + marked off
    # My two keepers are recorded.
    assert {m["player_name"] for m in engine.my_keepers} == {
        "Patrick Mahomes",
        "Marvin Harrison",
    }
    # Kept players are no longer recommendable.
    recs, _ = engine.recommendations(top_n=10)
    drafted_names = {"Patrick Mahomes", "Christian McCaffrey", "Ja'Marr Chase"}
    assert drafted_names.isdisjoint(set(recs["player_name"]))
    # Remaining needs reflect my keepers (QB filled, so QB no longer a need).
    assert engine.board.remaining_needs().get("QB", 0) == 0


@pytest.mark.unit
def test_my_full_roster_combines_keepers_and_picks(
    monkeypatch, adapter, projections_df, draft_raw
):
    monkeypatch.setattr(
        sleeper_http, "get_league_rosters", lambda lid: _load("league_rosters.json")
    )
    engine = LiveDraftEngine(adapter, projections_df, my_user_id="u_alpha", my_slot=1)
    engine.update(state_from_sleeper(draft_raw, []))
    engine.preload_keepers(adapter.get_keepers("L1", "u_alpha"))
    full = engine.my_full_roster()
    assert {m["player_name"] for m in full} == {"Patrick Mahomes", "Marvin Harrison"}
