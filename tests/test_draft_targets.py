"""Tests for src/draft_targets.py — pick-slot-aware value flags.

Covers the three gaps the 2026-08-28 ESPN mock exposed: no personal watchlist,
no way to tell which flagged players are reachable at YOUR picks, and flags
that never reached the live co-pilot.
"""

import os

import pandas as pd
import pytest

from src.draft_targets import (
    build_target_sheet,
    load_my_guys,
    my_pick_numbers,
    reachable_at,
    tag_players,
)


@pytest.fixture()
def board():
    """Small labeled board shaped like draft_value.label_board output."""
    return pd.DataFrame(
        {
            "player_name": [
                "Josh Allen",
                "Brian Thomas Jr.",
                "Derrick Henry",
                "AJ Dillon",
                "Kenny Gainwell",
                "Nate Carter",
            ],
            "position": ["QB", "WR", "RB", "RB", "RB", "RB"],
            "recent_team": ["BUF", "JAX", "BAL", "CAR", "TB", "ATL"],
            "adp_rank": [19, 30, 14, 140, 108, 200],
            "flag_value": [True, True, False, False, False, False],
            "flag_bust": [False, False, False, False, True, False],
            "flag_breakout": [False, True, False, False, False, False],
            "flag_deep_sleeper": [False, False, False, True, False, True],
            "reasons": [
                "§10 value",
                "§30 breakout",
                "",
                "§29 sleeper",
                "§27 inflation",
                "§29",
            ],
        }
    )


class TestMyPickNumbers:
    def test_snake_slot_12_of_12(self):
        """The slot that exposed the lookahead bug: 12, 13 back-to-back."""
        assert my_pick_numbers(12, 12, 5) == [12, 13, 36, 37, 60]

    def test_snake_slot_1_of_12(self):
        assert my_pick_numbers(1, 12, 4) == [1, 24, 25, 48]

    def test_linear_draft_has_even_spacing(self):
        assert my_pick_numbers(3, 12, 4, draft_type="linear") == [3, 15, 27, 39]

    def test_invalid_slot_returns_empty(self):
        assert my_pick_numbers(0, 12, 5) == []
        assert my_pick_numbers(13, 12, 5) == []


class TestLoadMyGuys:
    def test_missing_file_is_not_an_error(self, tmp_path):
        assert load_my_guys(str(tmp_path / "nope.txt")) == []

    def test_reads_names_strips_comments_and_dedupes(self, tmp_path):
        p = tmp_path / "my_guys.txt"
        p.write_text(
            "# my guys 2026\n"
            "Brian Thomas Jr.   # breakout\n"
            "\n"
            "Josh Allen\n"
            "brian thomas\n"  # same player, suffix-blind duplicate
        )
        assert load_my_guys(str(p)) == ["brian thomas", "josh allen"]

    def test_suffix_blind_keys(self, tmp_path):
        p = tmp_path / "g.txt"
        p.write_text("Kenneth Walker III\n")
        assert load_my_guys(str(p)) == ["kenneth walker"]


class TestTagPlayers:
    def test_tags_each_flag(self, board):
        tags = tag_players(board, my_guys=[])
        assert "VALUE" in tags["josh allen"]
        assert "BUST" in tags["kenny gainwell"]
        assert "SLEEPER" in tags["aj dillon"]
        assert "BREAKOUT" in tags["brian thomas"]

    def test_untagged_players_are_omitted(self, board):
        assert "derrick henry" not in tag_players(board, my_guys=[])

    def test_my_guy_wins_top_billing(self, board):
        tags = tag_players(board, my_guys=["josh allen"])
        assert tags["josh allen"][0] == "MY GUY"

    def test_my_guy_tagged_even_when_absent_from_board(self, board):
        """A watchlist name the board never scored must still surface."""
        tags = tag_players(board, my_guys=["some rookie"])
        assert tags["some rookie"] == ["MY GUY"]

    def test_empty_board_still_tags_the_watchlist(self):
        assert tag_players(pd.DataFrame(), my_guys=["josh allen"]) == {
            "josh allen": ["MY GUY"]
        }


class TestReachableAt:
    def test_excludes_players_long_gone(self, board):
        """Henry (ADP 14) is not a plan for pick 60."""
        names = set(reachable_at(board, 60)["player_name"])
        assert "Derrick Henry" not in names

    def test_includes_players_around_the_pick(self, board):
        names = set(reachable_at(board, 30)["player_name"])
        assert "Brian Thomas Jr." in names

    def test_deep_sleeper_surfaces_at_a_late_pick(self, board):
        assert "AJ Dillon" in set(reachable_at(board, 140)["player_name"])

    def test_empty_board_is_safe(self):
        assert reachable_at(pd.DataFrame(), 12).empty


class TestBuildTargetSheet:
    def test_one_entry_per_pick_in_order(self, board):
        # Slot 12 of 12 picks 12 (r1), 13 (r2), 36 (r3) — 37 is round 4.
        sheet = build_target_sheet(board, slot=12, n_teams=12, rounds=4)
        assert [s["pick"] for s in sheet] == [12, 13, 36, 37]

    def test_rounds_are_labeled(self, board):
        sheet = build_target_sheet(board, slot=12, n_teams=12, rounds=3)
        assert {s["pick"]: s["round"] for s in sheet}[36] == 3

    def test_each_pick_lists_only_flagged_reachable_players(self, board):
        sheet = build_target_sheet(board, slot=1, n_teams=12, rounds=2)
        first = {p["player_name"] for p in sheet[0]["players"]}
        # Henry carries no flag at all, so he never appears on a target sheet.
        assert "Derrick Henry" not in first

    def test_per_pick_cap_is_respected(self, board):
        sheet = build_target_sheet(board, slot=1, n_teams=12, rounds=2, per_pick=1)
        assert all(len(s["players"]) <= 1 for s in sheet)

    def test_players_carry_tags_and_reasons(self, board):
        sheet = build_target_sheet(board, slot=12, n_teams=12, rounds=1)
        flat = [p for s in sheet for p in s["players"]]
        assert flat, "expected at least one flagged player near picks 12/13"
        assert all("tags" in p and "reasons" in p for p in flat)


class TestWatchlistFades:
    """A fade rendered as "MY GUY" reads as a recommendation — the opposite."""

    def test_leading_dash_marks_a_fade(self, tmp_path):
        from src.draft_targets import load_watchlist

        p = tmp_path / "g.txt"
        p.write_text("Garrett Wilson\n- Josh Jacobs   # legal risk\n")
        wl = load_watchlist(str(p))
        assert wl["targets"] == ["garrett wilson"]
        assert wl["fades"] == ["josh jacobs"]

    def test_fade_tags_as_avoid_not_my_guy(self, board):
        tags = tag_players(board, my_guys=[], fades=["josh allen"])
        assert "AVOID" in tags["josh allen"]
        assert "MY GUY" not in tags["josh allen"]

    def test_avoid_outranks_other_flags(self, board):
        """AVOID must lead — it is a veto, not one signal among several."""
        tags = tag_players(board, my_guys=[], fades=["kenny gainwell"])
        assert tags["kenny gainwell"][0] == "AVOID"

    def test_fade_absent_from_board_still_surfaces(self, board):
        assert tag_players(board, my_guys=[], fades=["some guy"])["some guy"] == [
            "AVOID"
        ]

    def test_load_my_guys_returns_targets_only(self, tmp_path):
        p = tmp_path / "g.txt"
        p.write_text("Garrett Wilson\n- Josh Jacobs\n")
        assert load_my_guys(str(p)) == ["garrett wilson"]
