"""Unit tests for waiver_wire.roster_mechanics.

Every claim is two questions — is he worth it, and where does he go. The
second went wrong twice in one session: a player was recommended for an IR
slot his league does not allow (Mantis runs reserve_allow_out = 0, so merely
"Out" is not stashable), and a genuinely IR-eligible bench player sat
unnoticed while the roster read as full.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)

roster_mechanics = waiver_wire.roster_mechanics

POSITIONS = ["QB", "RB", "RB", "WR", "WR", "BN", "BN"]
REGISTRY = {
    "1": {"full_name": "Healthy Starter", "injury_status": None},
    "2": {"full_name": "Out Guy", "injury_status": "Out"},
    "3": {"full_name": "IR Guy", "injury_status": "IR"},
    "4": {"full_name": "Questionable Guy", "injury_status": "Questionable"},
}


def _league(reserve_slots=3, taxi_slots=0, **allows):
    return {
        "roster_positions": POSITIONS,
        "settings": {
            "reserve_slots": reserve_slots,
            "taxi_slots": taxi_slots,
            **allows,
        },
    }


def test_counts_active_against_roster_positions():
    out = roster_mechanics(
        _league(), {"players": ["1", "2", "3"], "reserve": ["3"]}, REGISTRY
    )
    assert "active 2/7 (5 open" in out[0]
    assert "IR 1/3" in out[0]


def test_taxi_players_do_not_count_as_active():
    out = roster_mechanics(
        _league(taxi_slots=2), {"players": ["1", "2"], "taxi": ["2"]}, REGISTRY
    )
    assert "active 1/7" in out[0]
    assert "taxi 1/2" in out[0]


def test_full_roster_says_a_claim_needs_a_drop():
    players = [str(i) for i in range(1, 8)]
    out = roster_mechanics(_league(), {"players": players}, {})
    assert "(0 open — a claim needs a drop when 0)" in out[0]


def test_ir_accepts_only_ir_by_default():
    """Mantis: reserve_allow_out is 0, so an 'Out' player is not stashable."""
    out = roster_mechanics(_league(), {"players": ["1", "2"]}, REGISTRY)
    assert "IR accepts: IR" in out[1]
    assert "none" in out[2]


def test_allowed_statuses_widen_the_ir_slot():
    out = roster_mechanics(
        _league(reserve_allow_out=1, reserve_allow_doubtful=1),
        {"players": ["1", "2"]},
        REGISTRY,
    )
    assert "Out" in out[1] and "Doubtful" in out[1]
    assert "Out Guy" in out[2]


def test_eligible_bench_player_is_named():
    """The Feetball miss: an IR-tagged player sitting on the bench."""
    out = roster_mechanics(_league(), {"players": ["1", "3"]}, REGISTRY)
    assert "IR Guy" in out[2]


def test_no_free_ir_slot_means_no_stash_line():
    out = roster_mechanics(
        _league(reserve_slots=1), {"players": ["1", "3"], "reserve": ["3"]}, REGISTRY
    )
    assert not any("IR-eligible" in line for line in out)


def test_league_without_ir_slots_says_nothing_about_ir():
    out = roster_mechanics(_league(reserve_slots=0), {"players": ["1"]}, REGISTRY)
    assert len(out) == 1


def test_unusable_league_object_is_silent():
    assert roster_mechanics({}, {"players": ["1"]}, REGISTRY) == []
