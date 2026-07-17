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


# ---------------------------------------------------------------------------
# UC3: stack-aware recommendations
# ---------------------------------------------------------------------------


def _corr_pairs_fixture():
    return pd.DataFrame(
        [
            {
                "level": "pair",
                "relation": "qb_stack",
                "player_id_a": "p_chase",
                "player_id_b": "p_mahomes",
                "player_name_a": "Ja'Marr Chase",
                "player_name_b": "Patrick Mahomes",
                "rho": 0.55,
                "n_games": 40,
            },
            {
                "level": "pair",
                "relation": "same_backfield",
                "player_id_a": "p_cmc",
                "player_id_b": "p_chase",
                "player_name_a": "Christian McCaffrey",
                "player_name_b": "Ja'Marr Chase",
                "rho": -0.30,
                "n_games": 25,
            },
        ]
    )


@pytest.mark.unit
def test_stack_note_positive_edge_vs_roster(adapter, draft_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    engine._corr_pairs = _corr_pairs_fixture()
    engine.rosters[1] = [{"player_id": "p_mahomes", "player_name": "Patrick Mahomes"}]
    note = engine.stack_note("p_chase")
    assert "stacks with Patrick Mahomes" in note
    assert "+0.55" in note


@pytest.mark.unit
def test_stack_note_negative_edge_wording(adapter, draft_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    engine._corr_pairs = _corr_pairs_fixture()
    engine.rosters[1] = [{"player_id": "p_cmc", "player_name": "Christian McCaffrey"}]
    note = engine.stack_note("p_chase")
    assert "shares ceiling with Christian McCaffrey" in note
    assert "-0.30" in note


@pytest.mark.unit
def test_stack_note_strongest_edge_wins(adapter, draft_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    engine._corr_pairs = _corr_pairs_fixture()
    engine.rosters[1] = [
        {"player_id": "p_mahomes", "player_name": "Patrick Mahomes"},
        {"player_id": "p_cmc", "player_name": "Christian McCaffrey"},
    ]
    # |+0.55| > |-0.30| -> Mahomes edge wins
    assert "Patrick Mahomes" in engine.stack_note("p_chase")


@pytest.mark.unit
def test_stack_note_empty_without_edges_or_roster(adapter, draft_raw, projections_df):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=1)
    engine._corr_pairs = pd.DataFrame()
    assert engine.stack_note("p_chase") == ""
    engine._corr_pairs = _corr_pairs_fixture()
    engine.rosters[1] = []
    assert engine.stack_note("p_chase") == ""


@pytest.mark.unit
def test_recommendations_carry_stack_note_column(
    adapter, draft_raw, picks_raw, projections_df
):
    engine = LiveDraftEngine(adapter, projections_df, my_slot=3)
    engine._corr_pairs = _corr_pairs_fixture()
    engine.update(_state(draft_raw, picks_raw))
    recs, _ = engine.recommendations(top_n=5)
    if not recs.empty and "player_id" in recs.columns:
        assert "stack_note" in recs.columns


# ---------------------------------------------------------------------------
# MANTIS 2026-07-11 fixes: KM-1 phantom availability, KM-2 rookie-draft ADP
# noise, low-sample market filter
# ---------------------------------------------------------------------------


class _NoMapAdapter:
    """Adapter stub whose mapping always fails — exercises the KM-1 path."""

    platform = "sleeper"

    def map_picks(self, picks, projections_df):
        return [], list(picks)


def _mini_proj(with_flags=False):
    rows = [
        {
            "player_id": "P1",
            "player_name": "Trey McBride",
            "position": "TE",
            "recent_team": "ARI",
            "projected_season_points": 280.0,
        },
        {
            "player_id": "P2",
            "player_name": "Kenneth Gainwell",
            "position": "RB",
            "recent_team": "TB",
            "projected_season_points": 150.0,
        },
        {
            "player_id": "P3",
            "player_name": "Two Game Vet",
            "position": "WR",
            "recent_team": "KC",
            "projected_season_points": 260.0,
        },
        {
            "player_id": "P4",
            "player_name": "Solid Veteran",
            "position": "WR",
            "recent_team": "PHI",
            "projected_season_points": 200.0,
        },
    ]
    df = pd.DataFrame(rows)
    if with_flags:
        df["is_low_sample_projection"] = [False, False, True, False]
        df["consensus_pos_rank"] = [1.0, 20.0, float("nan"), 5.0]
    return df


def _bare_state(rounds=15, picks=()):
    return DraftState(
        draft_id="d1",
        status="drafting",
        draft_type="snake",
        season="2026",
        n_teams=3,
        rounds=rounds,
        scoring_format="half_ppr",
        roster_format="standard",
        draft_order={},
        slot_to_roster_id={},
        picks=tuple(picks),
    )


@pytest.mark.unit
def test_km1_unmatched_keepers_leave_the_board():
    """Rostered players whose mapping fails must still exit the pool (KM-1)."""
    engine = LiveDraftEngine(_NoMapAdapter(), _mini_proj(), my_slot=1)
    engine.update(_bare_state())
    keeper = PickEvent(
        0, 0, 2, 2, "owner", "sid1", "Trey", "McBride", "TE", "ARI", True
    )
    n = engine.preload_keepers({"all": [keeper], "mine": []})
    assert n == 1
    names = set(engine.board.available["player_name"])
    assert "Trey McBride" not in names
    # No phantom pick recorded — snake math untouched.
    assert engine.board.picks_taken() == 0


@pytest.mark.unit
def test_km1_keeper_removal_is_nickname_tolerant():
    """'Kenny' keeper removes 'Kenneth' from the board (name-join fix)."""
    engine = LiveDraftEngine(_NoMapAdapter(), _mini_proj(), my_slot=1)
    engine.update(_bare_state())
    keeper = PickEvent(
        0, 0, 2, 2, "owner", "sid2", "Kenny", "Gainwell", "RB", "TB", True
    )
    assert engine.preload_keepers({"all": [keeper], "mine": []}) == 1
    assert "Kenneth Gainwell" not in set(engine.board.available["player_name"])


@pytest.mark.unit
def test_km2_rookie_draft_suppresses_adp_moments():
    """A 3-round draft is a rookie draft — no redraft-ADP steals/grades (KM-2)."""
    engine = LiveDraftEngine(_NoMapAdapter(), _mini_proj(), my_slot=1)
    engine.update(_bare_state(rounds=3))
    assert engine.adp_moments is False
    pe = PickEvent(15, 2, 1, 1, "u", "x", "Some", "Player", "WR", "BUF", False)
    assert engine._pick_moments(pe, {"adp_rank": 3, "vorp": 40.0, "pick_no": 15}) == []


@pytest.mark.unit
def test_km2_redraft_keeps_adp_moments_and_override_wins():
    """15 rounds → moments on; explicit adp_moments=True beats the auto-off."""
    engine = LiveDraftEngine(_NoMapAdapter(), _mini_proj(), my_slot=1)
    engine.update(_bare_state(rounds=15))
    assert engine.adp_moments is True

    forced = LiveDraftEngine(_NoMapAdapter(), _mini_proj(), my_slot=1, adp_moments=True)
    forced.update(_bare_state(rounds=3))
    pe = PickEvent(15, 2, 1, 1, "u", "x", "Some", "Player", "WR", "BUF", False)
    kinds = {m.kind for m in forced._pick_moments(pe, {"adp_rank": 3, "vorp": 40.0})}
    assert "steal" in kinds


@pytest.mark.unit
def test_low_sample_unranked_players_hidden_from_surfaces():
    """A low-sample vet the market doesn't rank never occupies a rec slot."""
    engine = LiveDraftEngine(_NoMapAdapter(), _mini_proj(with_flags=True), my_slot=1)
    engine.update(_bare_state())
    recs, _ = engine.recommendations(top_n=4)
    assert "Two Game Vet" not in set(recs["player_name"])
    # Still draftable — only hidden from recommendation surfaces.
    assert "Two Game Vet" in set(engine.board.available["player_name"])
    avail = engine.best_available(top_n=4)
    assert "Two Game Vet" not in set(avail["player_name"])
