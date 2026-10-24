"""Tests for `espn_lineup` — recommended lineup -> ESPN slot moves.

The planner's job is a diff, and the ways a diff goes wrong here are specific:
a name that does not match quietly leaves a starter benched, and a slot the
plan cannot fill (we carry no D/ST or K in the registry) must not be read as
"bench the incumbent". Both are silent point-losers, so both are pinned here.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from espn_lineup import (  # noqa: E402
    BENCH_SLOT,
    SLOT_LABEL_TO_ID,
    espn_names_by_id,
    espn_roster_index,
    normalize_name,
    plan_moves,
    resolve_players,
)

QB, RB, WR, TE, DST, FLEX = (
    SLOT_LABEL_TO_ID["QB"],
    SLOT_LABEL_TO_ID["RB"],
    SLOT_LABEL_TO_ID["WR"],
    SLOT_LABEL_TO_ID["TE"],
    SLOT_LABEL_TO_ID["DST"],
    SLOT_LABEL_TO_ID["FLEX"],
)


def _payload(entries):
    return {"teams": [{"id": 1, "roster": {"entries": entries}}]}


def _entry(pid, name, slot, pos=3):
    return {
        "playerId": pid,
        "lineupSlotId": slot,
        "playerPoolEntry": {"id": pid, "player": {"fullName": name, "defaultPositionId": pos}},
    }


class TestNameNormalisation:
    @pytest.mark.parametrize(
        "espn_name,our_name",
        [
            ("James Cook III", "James Cook"),
            ("Omar Cooper Jr.", "Omar Cooper"),
            ("A.J. Brown", "AJ Brown"),
            ("Marvin Harrison Jr.", "Marvin Harrison Jr"),
        ],
    )
    def test_suffixes_and_punctuation_collapse(self, espn_name, our_name):
        assert normalize_name(espn_name) == normalize_name(our_name)

    def test_different_players_do_not_collapse(self):
        assert normalize_name("Keenan Allen") != normalize_name("Braelon Allen")


class TestResolution:
    def test_defence_resolves_by_team_abbreviation(self):
        idx = espn_roster_index(_payload([_entry(-16010, "Titans D/ST", DST, pos=16)]), 1)
        resolved, unresolved = resolve_players(["TEN"], idx)
        assert resolved == {"TEN": -16010} and unresolved == []

    def test_unmatched_name_is_reported_not_dropped(self):
        idx = espn_roster_index(_payload([_entry(1, "Derrick Henry", RB, pos=2)]), 1)
        resolved, unresolved = resolve_players(["Derrick Henry", "Ghost Player"], idx)
        assert "Derrick Henry" in resolved and unresolved == ["Ghost Player"]


class TestPlanMoves:
    def test_noop_plan_produces_no_moves(self):
        """The control: planning the lineup that is already set changes nothing."""
        current = {1: QB, 2: RB, 3: BENCH_SLOT}
        moves, problems = plan_moves(
            [("QB", "Purdy"), ("RB", "Henry")], {"Purdy": 1, "Henry": 2}, current
        )
        assert moves == [] and problems == []

    def test_promotion_and_demotion_are_both_emitted(self):
        current = {1: WR, 2: BENCH_SLOT}
        moves, problems = plan_moves([("WR", "Vele")], {"Vele": 2}, current)
        assert problems == []
        assert sorted(moves) == sorted([(2, BENCH_SLOT, WR), (1, WR, BENCH_SLOT)])

    def test_unfillable_slot_leaves_its_incumbent_alone(self):
        """We carry no D/ST, so DST never appears in a plan — benching the
        incumbent would empty the slot for the week."""
        current = {1: QB, 99: DST}
        moves, problems = plan_moves([("QB", "Purdy")], {"Purdy": 1}, current)
        assert problems == []
        assert moves == [], "the defence must not be touched"

    def test_unresolved_name_blocks_the_plan(self):
        moves, problems = plan_moves([("WR", "Ghost")], {}, {1: WR})
        assert any("Ghost" in p for p in problems)

    def test_unknown_slot_label_blocks_the_plan(self):
        moves, problems = plan_moves([("SUPERFLEX", "X")], {"X": 1}, {1: BENCH_SLOT})
        assert any("unknown slot" in p for p in problems)

    def test_same_player_in_two_slots_blocks(self):
        moves, problems = plan_moves(
            [("RB", "Henry"), ("FLEX", "Henry")], {"Henry": 1}, {1: BENCH_SLOT}
        )
        assert any("two slots" in p for p in problems)


class TestNames:
    def test_names_by_id_round_trips(self):
        payload = _payload([_entry(7, "Tee Higgins", WR), _entry(-16010, "Titans D/ST", DST, 16)])
        assert espn_names_by_id(payload, 1) == {7: "Tee Higgins", -16010: "Titans D/ST"}
