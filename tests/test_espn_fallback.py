"""Offline proof that ESPN drafts are assistable via the manual-entry fallback.

Phase 89 (ESPN-01/03, NO-GO path). The ESPN-01 spike returned NO-GO for automated
live capture (see ``.planning/phases/89-espn-draft-adapter/89-SPIKE-FINDINGS.md``),
so ESPN's supported path is the D-09 manual-entry fallback in
``scripts/draft_live.py``. These tests drive an ESPN-style draft through
``build_manual_state(...)`` + :class:`~src.live_draft_engine.LiveDraftEngine` and
assert correct board/roster/turn state and skill-position mapping — proving ESPN is
fully assistable without any ESPN network call or cookie.

100% offline: ``@pytest.mark.unit``, no network, no real ESPN cookies.
"""

from __future__ import annotations

import importlib.util
import json
import os

import pandas as pd
import pytest

from src.live_draft_engine import LiveDraftEngine

# Load scripts/draft_live.py as a module (scripts/ is not a package) — same
# importlib pattern as tests/test_draft_live.py.
_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "draft_live.py")
_spec = importlib.util.spec_from_file_location("draft_live", _SCRIPT)
draft_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_live)

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sleeper_draft")

# A plausible ESPN snake-draft opening: 12-team, first 13 picks (start of round 2).
# Names are typed exactly as an operator would enter them for an ESPN draft.
_ESPN_PICKS = [
    "Ja'Marr Chase",
    "Justin Jefferson",
    "CeeDee Lamb",
    "Christian McCaffrey",
    "Bijan Robinson",
    "Saquon Barkley",
    "Amon-Ra St. Brown",
    "Jahmyr Gibbs",
    "Tyreek Hill",
    "Breece Hall",
    "Puka Nacua",
    "Jonathan Taylor",  # pick 12 -> slot 12 (end of round 1)
    "Garrett Wilson",  # pick 13 -> snake turns, slot 12 again (round 2)
]


@pytest.fixture
def projections_df():
    with open(
        os.path.join(_FIXTURE_DIR, "projections_sample.json"), encoding="utf-8"
    ) as fh:
        return pd.DataFrame(json.load(fh))


@pytest.mark.unit
def test_espn_style_manual_state_builds_correct_picks(projections_df):
    """build_manual_state turns ESPN operator picks into a correct DraftState."""
    state = draft_live.build_manual_state(
        _ESPN_PICKS,
        projections_df,
        n_teams=12,
        draft_type="snake",
        scoring="half_ppr",
        roster="standard",
        season="2026",
    )
    assert len(state.picks) == 13
    assert state.status == "drafting"
    # Round 1 runs slots 1..12 in order.
    assert state.picks[0].draft_slot == 1
    assert state.picks[11].draft_slot == 12  # pick 12
    # Snake: pick 13 wraps back to slot 12 in round 2.
    assert state.picks[12].round == 2
    assert state.picks[12].draft_slot == 12
    # Positions/teams are resolved from projections for known names.
    chase = state.picks[0]
    assert chase.position == "WR" and chase.team == "CIN"


@pytest.mark.unit
def test_espn_fallback_engine_tracks_board_roster_and_turn(projections_df):
    """The shared engine produces correct state from an ESPN-style manual draft."""
    state = draft_live.build_manual_state(
        _ESPN_PICKS,
        projections_df,
        n_teams=12,
        draft_type="snake",
        scoring="half_ppr",
        roster="standard",
        season="2026",
    )
    engine = LiveDraftEngine(
        adapter=draft_live._DummyAdapter(),
        projections_df=projections_df,
        my_slot=12,
    )
    poll = engine.update(state)

    # All 13 picks ingested as new this tick.
    assert len(poll.new_picks) == 13

    # After 13 picks in a 12-team snake, pick 14 is on the clock at slot 11.
    assert poll.turn is not None
    assert poll.turn.on_clock_pick_no == 14
    assert poll.turn.on_clock_slot == 11

    # Slot 12 (our slot) made picks 12 and 13 -> two players on our roster.
    my_roster = engine.rosters.get(12, [])
    my_names = {r.get("player_name") for r in my_roster}
    assert "Jonathan Taylor" in my_names
    assert "Garrett Wilson" in my_names


@pytest.mark.unit
def test_espn_fallback_maps_skill_positions_at_least_90pct(projections_df):
    """>=90% of ESPN skill-position picks map onto projections (ESPN-02 bar)."""
    state = draft_live.build_manual_state(
        _ESPN_PICKS,
        projections_df,
        n_teams=12,
        draft_type="snake",
        scoring="half_ppr",
        roster="standard",
        season="2026",
    )
    engine = LiveDraftEngine(
        adapter=draft_live._DummyAdapter(),
        projections_df=projections_df,
        my_slot=12,
    )
    engine.update(state)
    # Every typed name is a real skill-position player present in the fixture, so
    # none should land in the unmatched bucket.
    matched, unmatched = draft_live._DummyAdapter().map_picks(
        state.picks, engine.enriched
    )
    skill = [p for p in state.picks if p.position in {"QB", "RB", "WR", "TE"}]
    mapped_skill = [
        m
        for m in matched
        if str(m.get("position", "")).upper() in {"QB", "RB", "WR", "TE"}
    ]
    assert len(skill) == 13
    assert len(mapped_skill) / len(skill) >= 0.90
    assert unmatched == []


@pytest.mark.unit
def test_espn_fallback_drops_drafted_players_off_recommendations(projections_df):
    """Drafted ESPN players leave the recommendation board (no double-suggest)."""
    state = draft_live.build_manual_state(
        _ESPN_PICKS,
        projections_df,
        n_teams=12,
        draft_type="snake",
        scoring="half_ppr",
        roster="standard",
        season="2026",
    )
    engine = LiveDraftEngine(
        adapter=draft_live._DummyAdapter(),
        projections_df=projections_df,
        my_slot=12,
    )
    engine.update(state)
    recs, _reasoning = engine.recommendations(top_n=8)
    rec_names = set(recs.get("player_name", [])) if not recs.empty else set()
    for drafted in _ESPN_PICKS:
        assert drafted not in rec_names
