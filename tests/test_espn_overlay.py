"""Tests for the in-room draft overlay (src/espn_overlay.py).

Covers the ordering rules that decide what the operator sees on a 30-second
clock: steals outrank everything, a single forced need suppresses diversity,
and otherwise positions interleave so the list shows real alternatives.
"""

import pytest

from src.espn_overlay import (
    build_html,
    diversify,
    outstanding_positions,
    rows_from_recs_enriched,
)


def _r(name, pos, adp=None):
    return {"player_name": name, "position": pos, "adp": adp}


class TestOutstandingPositions:
    def test_parses_multiple(self):
        assert outstanding_positions(
            "scored by cost | §0 starters first: QB1/TE1 outstanding"
        ) == ["QB", "TE"]

    def test_parses_single(self):
        assert outstanding_positions("§0 starters first: QB1 outstanding") == ["QB"]

    @pytest.mark.parametrize("text", ["", "no marker here", None])
    def test_absent_marker_is_empty(self, text):
        assert outstanding_positions(text) == []


class TestDiversify:
    def test_interleaves_positions(self):
        recs = [_r("A", "TE"), _r("B", "TE"), _r("C", "TE"), _r("D", "QB")]
        assert [x["position"] for x in diversify(recs)][:3] == ["TE", "TE", "QB"]

    def test_single_forced_need_keeps_engine_order(self):
        recs = [_r("A", "TE"), _r("B", "TE"), _r("C", "TE"), _r("D", "QB")]
        out = diversify(recs, reasoning="§0 starters first: TE1 outstanding")
        assert [x["player_name"] for x in out] == ["A", "B", "C", "D"]

    def test_steal_outranks_need_and_diversity(self):
        recs = [_r("Kittle", "TE", 68), _r("Chase", "WR", 3)]
        assert diversify(recs, current_pick=60)[0]["player_name"] == "Chase"

    def test_biggest_steal_first(self):
        recs = [_r("Kittle", "TE", 68), _r("Chase", "WR", 3), _r("Bijan", "RB", 2)]
        out = diversify(recs, current_pick=60)
        assert [x["player_name"] for x in out][:2] == ["Bijan", "Chase"]

    def test_no_steal_when_adp_matches_pick(self):
        recs = [_r("Kittle", "TE", 68), _r("Chase", "WR", 3)]
        # At pick 10 nobody is 18+ picks past ADP, so normal order applies.
        assert diversify(recs, current_pick=10)[0]["player_name"] == "Kittle"

    def test_respects_limit(self):
        recs = [_r(str(i), "WR") for i in range(20)]
        assert len(diversify(recs, limit=5)) == 5

    def test_missing_adp_never_raises(self):
        assert diversify([_r("X", "WR"), _r("Y", "TE", None)], current_pick=60)


class TestRendering:
    def test_note_carries_market_and_news(self):
        market = {"georgekittle": {"ours": 30, "ESPN": 68, "news": "PUP"}}
        row = rows_from_recs_enriched([_r("George Kittle", "TE")], market)[0]
        assert "ours #30" in row["note"] and "ESPN 68" in row["note"]
        assert "!PUP" in row["note"]

    def test_html_escapes_but_keeps_line_break(self):
        html = build_html("H", [{"name": "A<script>", "pos": "TE", "note": "a<br>b"}])
        assert "&lt;script&gt;" in html
        assert "a<br>b" in html
