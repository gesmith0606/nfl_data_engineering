"""Unit tests for src/league_pools.py + scripts/refresh_league_pools.py glue."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

from src.league_pools import (
    dst_abbr,
    espn_pool_files,
    first_projection,
    yahoo_pool_files,
)

DAY = dt.date(2026, 10, 3)


def _entry(name, pos_id, inj="ACTIVE"):
    return {
        "playerPoolEntry": {
            "player": {
                "fullName": name,
                "defaultPositionId": pos_id,
                "injuryStatus": inj,
            }
        }
    }


ESPN_PAYLOAD = {
    "teams": [
        {
            "id": 1,
            "name": "The Oracle ",
            "record": {"overall": {"wins": 2, "losses": 2}},
            "roster": {
                "entries": [
                    _entry("Brock Purdy", 1),
                    _entry("Mike Evans", 3, "QUESTIONABLE"),
                    _entry("Bears D/ST", 16),
                ]
            },
        },
        {
            "id": 2,
            "location": "Chase-ing",
            "nickname": "Waterfalls",
            "record": {"overall": {"wins": 1, "losses": 3}},
            "roster": {"entries": [_entry("Ja'Marr Chase", 3), _entry("Some K", 5)]},
        },
    ]
}


def test_dst_abbr_handles_espn_and_yahoo_names():
    assert dst_abbr("Giants D/ST") == "NYG"
    assert dst_abbr("Steelers") == "PIT"
    assert dst_abbr("49ers D/ST") == "SF"
    assert dst_abbr("Nope") is None


def test_espn_pool_files():
    files = espn_pool_files(
        ESPN_PAYLOAD,
        1,
        "la_liga",
        5,
        fa_dst=[("Lions D/ST", 5.19), ("Unknown D/ST", 3.0)],
        my_dst_proj={"Bears D/ST": 4.58},
        today=DAY,
    )
    roster = files["la_liga_2026_roster.txt"].splitlines()
    assert roster[2:] == ["Brock Purdy", "Mike Evans"]
    assert files["la_liga_2026_all_rostered.txt"].split() == [
        "Brock",
        "Purdy",
        "Mike",
        "Evans",
        "Ja'Marr",
        "Chase",
    ]
    lr = files["la_liga_2026_league_rosters.txt"].splitlines()
    assert lr[0] == "The Oracle [2-2]: Brock Purdy (QB), Mike Evans (WR,Q)"
    assert lr[1].startswith("Chase-ing Waterfalls [1-3]: Ja'Marr Chase (WR)")
    pool = files["la_liga_2026_dstk_pool.txt"].splitlines()
    assert "MINE|DEF|CHI|4.6" in pool and "DEF|DET|5.2" in pool
    assert not any("Unknown" in line for line in pool)


def test_yahoo_pool_files():
    my = [
        {"slot": "QB", "name": "Jalen Hurts"},
        {"slot": "BN", "name": "MarShawn Lloyd"},
        {"slot": "IR", "name": "Jadarian Price"},
        {"slot": "K", "name": "Tyler Loop"},
        {"slot": "DEF", "name": "Steelers"},
    ]
    avail = {
        "QB": [{"name": "Malik Willis", "proj": 20.6}],
        "RB": [{"name": "Tyler Allgeier", "proj": 6.3}],
        "DEF": [{"name": "Jets", "proj": 8.99}],
        "K": [{"name": "Will Reichard", "proj": 10.34}],
    }
    files = yahoo_pool_files(my, avail, "feetball", 5, "/f1/658684/10", today=DAY)
    roster = files["feetball_2026_roster.txt"].splitlines()
    assert "# IR slot: Jadarian Price" in roster
    assert roster[-3:] == ["Jalen Hurts", "MarShawn Lloyd", "Jadarian Price"]
    assert files["feetball_2026_available.txt"].splitlines()[1:] == [
        "Malik Willis",
        "Tyler Allgeier",
    ]
    pool = files["feetball_2026_dstk_pool.txt"].splitlines()
    assert pool[2:] == [
        "MINE|K|Tyler Loop|",
        "MINE|DEF|PIT|",
        "DEF|NYJ|9.0",
        "K|Will Reichard|10.3",
    ]


def test_first_projection_skips_non_projection_cells():
    assert first_projection(["", "W (Oct 7)", "-", "11", "9.60", "189"]) == 9.6
    assert first_projection(["a", "b"]) is None


def _load_script():
    path = (
        Path(__file__).resolve().parent.parent / "scripts" / "refresh_league_pools.py"
    )
    spec = importlib.util.spec_from_file_location("refresh_league_pools", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_refresh_espn_writes_files_from_cdp(tmp_path, monkeypatch):
    mod = _load_script()
    monkeypatch.setattr(mod, "DRAFT_DIR", tmp_path)
    monkeypatch.setattr(mod, "ESPN_JSON_DIR", tmp_path / "espn")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    payload = {"payload": ESPN_PAYLOAD, "fa_dst": [["Lions D/ST", 5.2]], "my_dst": {}}
    monkeypatch.setattr(
        mod.ChromeDraftPage, "evaluate", lambda self, *a, **k: json.dumps(payload)
    )
    mod.refresh_espn("la_liga", 5, 2026, "http://x")
    assert (tmp_path / "la_liga_2026_roster.txt").exists()
    assert json.loads((tmp_path / "espn" / "la_liga_2026_league.json").read_text())[
        "teams"
    ]
