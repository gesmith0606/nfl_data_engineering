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


# ---------------------------------------------------------------------------
# Live ESPN lineup (2026-10-24): cookies turned "we can only recommend" into
# "we can diff against what is actually set".
# ---------------------------------------------------------------------------


def test_espn_live_lineup_reads_the_lineup_that_is_set(monkeypatch):
    """The starters come from ESPN's own slots, not from our optimizer.

    Before cookies the tool had nothing to compare against, so the SWAP rule
    could never fire for ESPN and the table was a recommendation. This is the
    read that changed that, so it is worth pinning: QB/RB/WR slots map onto the
    preset's slot order, and a bench player must not appear among the starters.
    """
    m = _mod()

    payload = {
        "teams": [
            {
                "id": 1,
                "roster": {
                    "entries": [
                        {"playerId": 10, "lineupSlotId": 0,
                         "playerPoolEntry": {"id": 10, "player": {"fullName": "Brock Purdy", "defaultPositionId": 1}}},
                        {"playerId": 11, "lineupSlotId": 2,
                         "playerPoolEntry": {"id": 11, "player": {"fullName": "Derrick Henry", "defaultPositionId": 2}}},
                        {"playerId": 12, "lineupSlotId": 20,
                         "playerPoolEntry": {"id": 12, "player": {"fullName": "Benched Guy", "defaultPositionId": 3}}},
                    ]
                },
            }
        ]
    }

    monkeypatch.setenv("ESPN_S2", "x")
    monkeypatch.setenv("ESPN_SWID", "{S}")
    monkeypatch.setattr(m, "build_id_maps", lambda reg: ({}, {
        ("brock purdy", "QB"): "sid_qb",
        ("derrick henry", "RB"): "sid_rb",
        ("benched guy", "WR"): "sid_bn",
    }))

    import src.espn_league as espn_league

    monkeypatch.setattr(espn_league, "cookies_from_env", lambda: {"SWID": "{S}", "espn_s2": "x"})
    monkeypatch.setattr(espn_league, "fetch_league", lambda *a, **k: payload)
    monkeypatch.setattr(espn_league, "find_my_team_id", lambda *a, **k: 1)

    out = m.espn_live_lineup(123, 2026, {}, ["QB", "RB", "WR"])

    assert out is not None
    assert out["team_id"] == 1
    assert out["starters"][0] == "sid_qb"
    assert out["starters"][1] == "sid_rb"
    assert out["starters"][2] == "0", "no WR is started, so the slot is unfilled"
    assert "sid_bn" in out["players"], "the bench player is still on the roster"


def test_espn_live_lineup_returns_none_without_cookies(monkeypatch):
    """No cookies means fall back to the pasted file, not a half-read lineup."""
    m = _mod()
    monkeypatch.delenv("ESPN_S2", raising=False)
    monkeypatch.delenv("ESPN_SWID", raising=False)
    monkeypatch.setattr(m, "load_dotenv", lambda *a, **k: None, raising=False)

    import src.espn_league as espn_league

    monkeypatch.setattr(espn_league, "cookies_from_env", lambda: {})
    assert m.espn_live_lineup(123, 2026, {}, ["QB"]) is None
