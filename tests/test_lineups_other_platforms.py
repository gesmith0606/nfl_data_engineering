"""Tests for the ESPN/Yahoo lineup path in scripts/set_lineups.py.

George, 2026-10-23: "I have 2 other teams?" — and `set_lineups.py` answered
"only Sleeper rosters are supported yet", so two of his three teams had no
lineup tool at all. Nothing was missing but the wiring: the slot shape and
scoring are in LEAGUE_PRESETS, the projections are our board plus Sleeper's,
and the roster is the same pasted file the waiver report already takes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "set_lineups_other", REPO / "scripts" / "set_lineups.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["set_lineups_other"] = m
    spec.loader.exec_module(m)
    return m


def test_the_slot_shape_comes_from_the_preset_not_a_live_feed():
    """Sleeper publishes roster_positions; ESPN and Yahoo do not."""
    sl = _mod()
    from src import config

    espn = sl.slots_from_shape(config.our_league("la_liga"))
    yahoo = sl.slots_from_shape(config.our_league("feetball"))
    # One entry per slot, bench excluded, and DST renamed to Sleeper's DEF.
    assert espn.count("RB") == 2 and espn.count("FLEX") == 2
    assert "DEF" in espn and "DST" not in espn and "BN" not in espn
    assert yahoo.count("WR") == 3 and "K" in yahoo
    assert len(espn) == 9 and len(yahoo) == 10


def test_scoring_comes_from_the_preset_in_sleeper_keys():
    sl = _mod()
    from src import config

    scoring = sl.scoring_for_preset(config.our_league("la_liga"))
    # half-PPR, keyed the way score_with_settings expects.
    assert scoring["rec"] == 0.5
    assert scoring["pass_td"] == 4.0
    assert "reception" not in scoring, "must be translated, not raw config keys"


def test_an_unfillable_slot_is_marked_rather_than_silently_dropped():
    """Our registry has no D/ST or K, so those slots cannot be allocated.

    Dropping them would make a 9-slot lineup look complete at 8.
    """
    sl = _mod()

    class Row:
        def __init__(self, sid, pos, pts):
            self.sleeper_id, self.pos, self.pts = sid, pos, pts

        def as_optimizer_dict(self, _source):
            return {
                "sleeper_id": self.sleeper_id,
                "position": self.pos,
                "points": self.pts,
                "projected_points": self.pts,
            }

    rows = [Row("qb1", "QB", 20.0), Row("rb1", "RB", 10.0)]
    out = sl.recommended_starters(rows, ["QB", "RB", "DEF"])
    assert out[0] == "qb1" and out[1] == "rb1"
    assert out[2] == "0", "an unfillable slot is '0', not absent"
    assert len(out) == 3


def test_non_sleeper_output_says_it_is_a_recommendation():
    """ "No changes" would read as "your lineup is fine" — we cannot see it."""
    body = (REPO / "scripts" / "set_lineups.py").read_text(encoding="utf-8")
    assert "what we RECOMMEND, not what you have set" in body
    assert "stream_dst_k.py" in body, "point at the tool that does fill those slots"
    # And the refusal must name the flag rather than just declining.
    assert "--roster-file with your roster" in body
