"""Tests for src/draft_paste_sync.py — the ESPN paste-sync parser.

The parser must be format-agnostic: ESPN pick history, Yahoo draft results,
and hand-typed lists all reduce to "one pick per line, find the player name".
"""

import pytest

from src.draft_paste_sync import ParsedPick, build_name_lookup, parse_pick_log

_POOL = [
    ("Bijan Robinson", "p1"),
    ("Jahmyr Gibbs", "p2"),
    ("Amon-Ra St. Brown", "p3"),
    ("Justin Jefferson", "p4"),
    ("Marvin Harrison Jr.", "p5"),
    ("Kenneth Gainwell", "p6"),
    ("Michael Pittman Jr.", "p7"),
]


@pytest.fixture()
def lookup():
    return build_name_lookup(_POOL)


class TestBuildNameLookup:
    def test_normalizes_suffixes_and_punctuation(self, lookup):
        assert lookup["marvin harrison"] == ("p5", "Marvin Harrison Jr.")
        assert lookup["amonra st brown"] == ("p3", "Amon-Ra St. Brown")

    def test_first_duplicate_wins(self):
        dup = build_name_lookup([("Josh Allen", "qb"), ("Josh Allen", "wr")])
        assert dup["josh allen"] == ("qb", "Josh Allen")


class TestParsePickLog:
    def test_espn_style_history(self, lookup):
        text = (
            "R1, P1  Bijan Robinson, RB  ATL  Team Gforce\n"
            "R1, P2  Jahmyr Gibbs, RB  DET  Team Two\n"
            "R1, P3  Amon-Ra St. Brown, WR  DET  Team Three\n"
        )
        result = parse_pick_log(text, lookup)
        assert [p.player_id for p in result.picks] == ["p1", "p2", "p3"]
        assert result.unmatched_lines == []

    def test_yahoo_style_results(self, lookup):
        text = (
            "1. (1) Bijan Robinson (RB - ATL)\n" "2. (2) Justin Jefferson (WR - MIN)\n"
        )
        result = parse_pick_log(text, lookup)
        assert [p.player_id for p in result.picks] == ["p1", "p4"]

    def test_hand_typed_names(self, lookup):
        result = parse_pick_log("bijan robinson\nkenny gainwell\n", lookup)
        # Exact-normalized names match; nicknames ("Kenny") are reported, not guessed.
        assert [p.player_id for p in result.picks] == ["p1"]
        assert result.unmatched_lines == ["kenny gainwell"]

    def test_suffix_variants_match(self, lookup):
        result = parse_pick_log(
            "1.05 Marvin Harrison WR ARI\n1.06 Michael Pittman Jr. WR IND\n",
            lookup,
        )
        assert [p.player_id for p in result.picks] == ["p5", "p7"]

    def test_blank_and_junk_lines(self, lookup):
        text = "\n\nDraft Order\n1.01 Bijan Robinson RB\nTimeouts remaining: 2\n"
        result = parse_pick_log(text, lookup)
        assert [p.player_id for p in result.picks] == ["p1"]
        assert "Draft Order" in result.unmatched_lines
        assert "Timeouts remaining: 2" in result.unmatched_lines

    def test_one_pick_per_line_takes_leftmost(self, lookup):
        # A line naming two players keeps the first (the picked player).
        result = parse_pick_log(
            "Bijan Robinson drafted ahead of Jahmyr Gibbs\n", lookup
        )
        assert [p.player_id for p in result.picks] == ["p1"]

    def test_preserves_order_and_line_numbers(self, lookup):
        result = parse_pick_log("Jahmyr Gibbs\n\nBijan Robinson\n", lookup)
        assert [(p.line_no, p.player_id) for p in result.picks] == [
            (1, "p2"),
            (3, "p1"),
        ]

    def test_empty_text(self, lookup):
        result = parse_pick_log("", lookup)
        assert result.picks == [] and result.unmatched_lines == []
