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
    """A slot nobody eligible can fill is "0", not absent.

    Dropping it would make a 9-slot lineup look complete at 8.
    """
    sl = _mod()
    from src.lineup_setter import PlayerRow

    rows = [
        PlayerRow("qb1", "Q1", "QB", "BUF", ours=20.0, sleeper=20.0),
        PlayerRow("rb1", "R1", "RB", "BUF", ours=10.0, sleeper=10.0),
    ]
    out = sl.recommended_starters(rows, ["QB", "RB", "DEF"])
    assert out[0] == "qb1" and out[1] == "rb1"
    assert out[2] == "0", "an unfillable slot is '0', not absent"
    assert len(out) == 3


def test_recommended_starters_fill_super_flex_k_and_def_and_skip_a_bye():
    """The old allocation keyed slots by display name: SUPER_FLEX stayed empty,
    and K/DEF could never be filled because the roster never resolved them."""
    sl = _mod()
    from src.lineup_setter import PlayerRow

    rows = [
        PlayerRow("qb1", "Q1", "QB", "BUF", ours=20.0, sleeper=20.0),
        PlayerRow("qb2", "Q2", "QB", "BUF", ours=15.0, sleeper=15.0),
        PlayerRow("k1", "K1", "K", "BUF", ours=None, sleeper=8.0),
        PlayerRow("HOU", "Houston Texans", "DEF", "HOU", ours=None, sleeper=7.0),
        PlayerRow("qb3", "Q3 on bye", "QB", "SF", ours=40.0, sleeper=40.0, bye=True),
    ]
    out = sl.recommended_starters(rows, ["QB", "SUPER_FLEX", "K", "DEF", "BN"])
    assert out == ["qb1", "qb2", "k1", "HOU"]


def test_a_defence_resolves_by_team_code_not_by_a_site_specific_name():
    sl = _mod()
    reg = {
        "HOU": {"position": "DEF", "first_name": "Houston", "last_name": "Texans", "team": "HOU"},
        "LAR": {"position": "DEF", "first_name": "Los Angeles", "last_name": "Rams", "team": "LAR"},
        "11533": {"position": "K", "full_name": "Brandon Aubrey", "team": "DAL", "active": True},
    }
    from src.lineup_setter import build_id_maps

    _g, by_name = build_id_maps(reg)
    assert sl.resolve_sleeper_id("Texans D/ST", reg, by_name) == "HOU"  # ESPN
    assert sl.resolve_sleeper_id("Houston", reg, by_name, team="Hou", position="DEF") == "HOU"  # Yahoo
    assert sl.resolve_sleeper_id("Los Angeles Rams", reg, by_name, team="LA", position="DEF") == "LAR"
    assert sl.resolve_sleeper_id("Brandon Aubrey", reg, by_name) == "11533"
    assert sl.resolve_sleeper_id("Nobody D/ST", reg, by_name) is None


def test_preset_scoring_carries_kicker_and_defence_rules():
    """Without them every K and DEF scores 0 and ties for the slot."""
    sl = _mod()
    from src import config

    scoring = sl.scoring_for_preset(config.our_league("la_liga"))
    assert scoring["fgm_40_49"] == 4.0 and scoring["pts_allow_0"] > 0 and scoring["sack"] == 1.0
    assert scoring["rec"] == 0.5  # offensive rules untouched


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


def test_espn_live_lineup_finds_the_dst_in_a_def_slot(monkeypatch):
    """ESPN labels slot 16 ``DST``; the preset's slot list calls it ``DEF``.

    ``slots_from_shape`` renames ROSTER_CONFIGS' DST to Sleeper's DEF, but the
    ESPN read kept ESPN's label, so the D/ST George had started was never
    matched: the report said "DEF slot is empty -> start Carolina" and then
    "Could not fill: DEF" every week (2026 week 11), with the Panthers in
    slot 16 the whole time.
    """
    m = _mod()
    from src.config import LEAGUE_PRESETS

    payload = {
        "teams": [
            {
                "id": 1,
                "roster": {
                    "entries": [
                        {"playerId": 10, "lineupSlotId": 0,
                         "playerPoolEntry": {"id": 10, "player": {"fullName": "Brock Purdy", "defaultPositionId": 1}}},
                        {"playerId": -16029, "lineupSlotId": 16,
                         "playerPoolEntry": {"id": -16029, "player": {"fullName": "Panthers D/ST", "defaultPositionId": 16}}},
                    ]
                },
            }
        ]
    }
    ids = {"Brock Purdy": "sid_qb", "Panthers D/ST": "CAR"}

    monkeypatch.setattr(m, "build_id_maps", lambda reg: ({}, {}))
    monkeypatch.setattr(m, "resolve_sleeper_id", lambda name, *a, **k: ids.get(name))

    import src.espn_league as espn_league

    monkeypatch.setattr(espn_league, "cookies_from_env", lambda: {"SWID": "{S}", "espn_s2": "x"})
    monkeypatch.setattr(espn_league, "fetch_league", lambda *a, **k: payload)
    monkeypatch.setattr(espn_league, "find_my_team_id", lambda *a, **k: 1)

    slots = m.slots_from_shape(LEAGUE_PRESETS["la_liga"])
    assert slots[-1] == "DEF", "the preset names the slot DEF, ESPN names it DST"

    out = m.espn_live_lineup(123, 2026, {}, slots)

    assert out["starters"][0] == "sid_qb"
    assert out["starters"][-1] == "CAR", "the started D/ST must fill the DEF slot"


def test_espn_live_lineup_returns_none_without_cookies(monkeypatch):
    """No cookies means fall back to the pasted file, not a half-read lineup."""
    m = _mod()
    monkeypatch.delenv("ESPN_S2", raising=False)
    monkeypatch.delenv("ESPN_SWID", raising=False)
    monkeypatch.setattr(m, "load_dotenv", lambda *a, **k: None, raising=False)

    import src.espn_league as espn_league

    monkeypatch.setattr(espn_league, "cookies_from_env", lambda: {})
    assert m.espn_live_lineup(123, 2026, {}, ["QB"]) is None
