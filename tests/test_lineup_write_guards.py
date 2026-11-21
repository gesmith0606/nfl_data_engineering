"""Inputs that can wrongly produce a MUST FIX (which the ESPN writer files).

MUST FIX bypasses the probability gate, so a bad schedule row or a crossed
name match must never read as "on bye" / "Out" for a healthy starter.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.lineup_setter import (
    ET,
    build_id_maps,
    build_rows,
    kickoffs_for_week,
)  # noqa: E402

SCORING = {"rec": 1.0, "rec_yd": 0.1}


def _sched(gameday, gametime, home="GB", away="NE"):
    return pd.DataFrame(
        {
            "week": [1],
            "gameday": [gameday],
            "gametime": [gametime],
            "home_team": [home],
            "away_team": [away],
        }
    )


def test_nan_gametime_keeps_the_game_and_is_not_a_bye(capsys):
    # NaN is truthy: "nan" failed to parse, the whole game was skipped, and both
    # teams then read as BYE.
    ko = kickoffs_for_week(_sched("2026-09-13", float("nan")), 1)
    assert ko["GB"] == dt.datetime(2026, 9, 13, 13, 0, tzinfo=ET)
    assert ko["NE"] == ko["GB"]
    assert "gametime" in capsys.readouterr().out  # surfaced, not silent


def test_garbled_gametime_keeps_the_game(capsys):
    ko = kickoffs_for_week(_sched("2026-09-13", "TBD"), 1)
    assert ko["GB"].hour == 13
    assert "WARNING" in capsys.readouterr().out


def test_unreadable_gameday_is_not_a_bye_either(capsys):
    sched = pd.concat(
        [_sched("garbage", "13:00"), _sched("2026-09-13", "13:00", "BUF", "MIA")]
    )
    ko = kickoffs_for_week(sched, 1)
    reg = {"1": {"full_name": "Christian Watson", "position": "WR", "team": "GB"}}
    rows = build_rows(["1"], ["1"], ["WR"], reg, {}, {}, SCORING, ko)
    assert not rows[0].bye  # GB has a game row we could not read
    assert "WARNING" in capsys.readouterr().out


def test_a_team_with_no_game_row_is_still_a_bye():
    ko = kickoffs_for_week(_sched("2026-09-13", "13:00", "BUF", "MIA"), 1)
    reg = {"1": {"full_name": "Christian Watson", "position": "WR", "team": "GB"}}
    rows = build_rows(["1"], ["1"], ["WR"], reg, {}, {}, SCORING, ko)
    assert rows[0].bye


# --- same-name players are never guessed between -----------------------------

TWINS = {
    "10": {
        "full_name": "Mike Williams",
        "position": "WR",
        "team": "NYJ",
        "active": True,
    },
    "11": {
        "full_name": "Mike Williams",
        "position": "WR",
        "team": "SEA",
        "active": True,
    },
    "12": {"full_name": "Cooper Kupp", "position": "WR", "team": "LAR", "active": True},
}


@pytest.fixture()
def sl():
    spec = importlib.util.spec_from_file_location(
        "set_lineups_guard", REPO / "scripts" / "set_lineups.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["set_lineups_guard"] = m
    spec.loader.exec_module(m)
    return m


def test_same_name_same_position_is_ambiguous_without_a_team(sl, capsys):
    _g, by_name = build_id_maps(TWINS)
    assert sl.resolve_sleeper_id("Mike Williams", TWINS, by_name, position="WR") is None
    assert "AMBIGUOUS NAME" in capsys.readouterr().out


def test_team_picks_the_right_twin(sl):
    _g, by_name = build_id_maps(TWINS)
    pick = sl.resolve_sleeper_id
    assert pick("Mike Williams", TWINS, by_name, team="SEA", position="WR") == "11"
    assert pick("Mike Williams", TWINS, by_name, team="NYJ", position="WR") == "10"


def test_a_unique_name_still_resolves_and_unknown_team_does_not_block(sl):
    _g, by_name = build_id_maps(TWINS)
    assert sl.resolve_sleeper_id("Cooper Kupp", TWINS, by_name) == "12"
    assert (
        sl.resolve_sleeper_id("Cooper Kupp", TWINS, by_name, team="XXX", position="WR")
        == "12"
    )
