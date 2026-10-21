"""Unit tests for the RENTAL tag in scripts/waiver_wire.py.

The tag exists because a candidate whose snaps jumped while a better
same-position team-mate sat hurt is renting the role, not earning it. Week 7
of 2026 produced three such candidates in one session (Huntley behind Lamar
Jackson, Jalon Daniels behind Baker Mayfield, Roschon Johnson behind Kyle
Monangai), all of which read as league-winning adds without this context.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)

injured_teammates = waiver_wire.injured_teammates
UNRANKED = waiver_wire.UNRANKED


def _p(name, pos, team, status=None, rank=None):
    return {
        "full_name": name,
        "position": pos,
        "team": team,
        "injury_status": status,
        "search_rank": rank,
    }


REGISTRY = {
    "1": _p("Lamar Jackson", "QB", "BAL", "Out", 10),
    "2": _p("Tyler Huntley", "QB", "BAL", None, 310),
    "3": _p("Adam Randall", "RB", "BAL", "IR", 408),
    "4": _p("Justice Hill", "RB", "BAL", None, 220),
    "5": _p("Baker Mayfield", "QB", "TB", "Out", 75),
    "6": _p("Jalon Daniels", "QB", "TB", None, 401),
    "7": _p("Healthy Starter", "WR", "NYJ", None, 40),
    "8": _p("Questionable Guy", "WR", "NYJ", "Questionable", 50),
    "9": _p("Unranked Backup", "TE", "LV", "Out", None),
    "10": _p("Interior Lineman", "G", "ARI", "Out", 900),
}


def test_blocking_statuses_only():
    """Out/IR count; Questionable and healthy do not."""
    m = injured_teammates(REGISTRY)
    assert ("BAL", "QB") in m
    assert ("TB", "QB") in m
    # Questionable is not a blocking status, so the Jets have no entry.
    assert ("NYJ", "WR") not in m


def test_non_skill_positions_ignored():
    m = injured_teammates(REGISTRY)
    assert not any(pos == "G" for _team, pos in m)


def test_entries_carry_rank_and_sort_best_first():
    m = injured_teammates(REGISTRY)
    assert m[("BAL", "QB")] == [(10, "Lamar Jackson")]
    assert m[("TB", "QB")] == [(75, "Baker Mayfield")]


def test_unranked_injured_player_sorts_last():
    m = injured_teammates(REGISTRY)
    assert m[("LV", "TE")] == [(UNRANKED, "Unranked Backup")]


def _blocked_for(registry, candidate_name):
    """Mirror the filter scripts/waiver_wire.py applies when building a row."""
    m = injured_teammates(registry)
    meta = next(v for v in registry.values() if v["full_name"] == candidate_name)
    own = meta.get("search_rank")
    own = int(own) if isinstance(own, (int, float)) else UNRANKED
    return [
        n
        for rank, n in m.get((meta["team"], meta["position"]), [])
        if n != meta["full_name"] and rank < own
    ]


def test_more_notable_teammate_flags_the_candidate():
    """Huntley (310) is renting Lamar Jackson's job (10)."""
    assert _blocked_for(REGISTRY, "Tyler Huntley") == ["Lamar Jackson"]
    assert _blocked_for(REGISTRY, "Jalon Daniels") == ["Baker Mayfield"]


def test_less_notable_teammate_is_not_a_rental_signal():
    """Justice Hill (220) does not owe his role to Adam Randall (408)."""
    assert _blocked_for(REGISTRY, "Justice Hill") == []


def test_candidate_never_flags_himself():
    reg = dict(REGISTRY)
    reg["11"] = _p("Hurt Starter", "WR", "SEA", "Out", 30)
    assert _blocked_for(reg, "Hurt Starter") == []


def test_empty_registry_is_safe():
    assert injured_teammates({}) == {}
    assert injured_teammates({"x": None, "y": "junk"}) == {}
