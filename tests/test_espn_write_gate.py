"""The ESPN lineup writer's gate: which verdicts may reach submit_lineup.

Invariant (scripts/set_lineups.py ``espn_write``): ``--apply`` files ONLY
MUST FIX moves and SWAPs at P >= WRITE_P (0.60), never LEAN or CHECK STATUS,
never a SWAP with no probability; without ``--apply`` nothing is ever submitted.
No network: ``submit_lineup`` and ``current_lineup_slots`` are fakes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.lineup_setter import Delta, PlayerRow  # noqa: E402


@pytest.fixture()
def sl():
    spec = importlib.util.spec_from_file_location(
        "set_lineups_gate", REPO / "scripts" / "set_lineups.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["set_lineups_gate"] = m
    spec.loader.exec_module(m)
    return m


# Names carry no digits: the name matcher strips them.
NAMES = ["Aaron", "Bobby", "Cedric", "Dexter", "Elliot", "Felix", "Gavin"]
CASES = [
    ("MUST FIX", None, True),
    ("SWAP", 0.75, True),
    ("SWAP", 0.59, False),
    ("SWAP", 0.60, True),
    ("LEAN", 0.80, False),
    ("CHECK STATUS", 0.90, False),
    ("SWAP", None, False),
]


def _payload():
    """One starter (slot 4 = WR) and one bench player (slot 20) per case."""

    def entry(pid, name, slot):
        return {
            "playerId": pid,
            "lineupSlotId": slot,
            "playerPoolEntry": {
                "id": pid,
                "player": {"fullName": name, "defaultPositionId": 3},
            },
        }

    entries = []
    for i in range(len(CASES)):
        entries.append(entry(100 + i, f"{NAMES[i]} Starter", 4))
        entries.append(entry(200 + i, f"{NAMES[i]} Bench", 20))
    return {"teams": [{"id": 1, "roster": {"entries": entries}}]}


def _delta(i, verdict, p):
    out = PlayerRow(f"o{i}", f"{NAMES[i]} Starter", "WR", "BUF", ours=5, sleeper=5, slot="WR")
    inn = PlayerRow(f"i{i}", f"{NAMES[i]} Bench", "WR", "BUF", ours=9, sleeper=9)
    return Delta(verdict, "WR", out, inn, p=p, gap=4.0)


@pytest.fixture()
def fakes(monkeypatch):
    import dotenv
    import src.espn_league as el

    submitted = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)  # never read .env
    monkeypatch.setattr(el, "cookies_from_env", lambda: {"SWID": "{X}", "espn_s2": "x"})

    def fake_submit(league_id, season, team_id, week, moves, cookies):
        submitted.append(list(moves))
        return {"status": 200}

    def fake_slots(league_id, season, team_id, week, cookies):
        done = {}
        for moves in submitted:
            for pid, _from, to in moves:
                done[pid] = to
        return done

    monkeypatch.setattr(el, "submit_lineup", fake_submit)
    monkeypatch.setattr(el, "current_lineup_slots", fake_slots)
    return submitted


def _run(sl, deltas, apply_changes):
    return sl.espn_write(
        preset={"league_id": "123"},
        deltas=deltas,
        espn_live={"team_id": 1, "payload": _payload()},
        season=2026,
        week=11,
        apply_changes=apply_changes,
    )


@pytest.mark.parametrize("i,case", list(enumerate(CASES)))
def test_apply_files_only_what_the_gate_allows(sl, fakes, i, case):
    verdict, p, fileable = case
    _run(sl, [_delta(i, verdict, p)], apply_changes=True)
    if fileable:
        assert fakes == [[(100 + i, 4, 20), (200 + i, 20, 4)]]
    else:
        assert fakes == []


@pytest.mark.parametrize("i,case", list(enumerate(CASES)))
def test_without_apply_nothing_is_ever_submitted(sl, fakes, i, case):
    verdict, p, _ = case
    _run(sl, [_delta(i, verdict, p)], apply_changes=False)
    assert fakes == []


def test_all_verdicts_together_file_exactly_the_allowed_ones(sl, fakes):
    deltas = [_delta(i, v, p) for i, (v, p, _f) in enumerate(CASES)]
    _run(sl, deltas, apply_changes=True)
    assert len(fakes) == 1  # one transaction
    moved_out = {m[0] for m in fakes[0] if m[2] == 20}
    assert moved_out == {100 + i for i, (_v, _p, f) in enumerate(CASES) if f}
