"""Unit tests for the fantasy roster optimizer (Phase 90)."""

from __future__ import annotations

import pytest

from src.roster_optimizer import drop_candidates, optimal_lineup

_ROSTER = [
    {"player_name": "QB1", "position": "QB", "projected_points": 350, "vorp": 80},
    {"player_name": "RB1", "position": "RB", "projected_points": 300, "vorp": 70},
    {"player_name": "RB2", "position": "RB", "projected_points": 250, "vorp": 40},
    {"player_name": "RB3", "position": "RB", "projected_points": 120, "vorp": 5},
    {"player_name": "WR1", "position": "WR", "projected_points": 280, "vorp": 60},
    {"player_name": "WR2", "position": "WR", "projected_points": 260, "vorp": 45},
    {"player_name": "WR3", "position": "WR", "projected_points": 140, "vorp": 10},
    {"player_name": "TE1", "position": "TE", "projected_points": 200, "vorp": 50},
    {"player_name": "K1", "position": "K", "projected_points": 130, "vorp": 2},
    {"player_name": "DST1", "position": "DST", "projected_points": 120, "vorp": 3},
]


@pytest.mark.unit
def test_optimal_lineup_fills_base_and_flex():
    lu = optimal_lineup(_ROSTER, "standard")
    s = lu["starters"]
    assert [p["player_name"] for p in s["QB"]] == ["QB1"]
    assert [p["player_name"] for p in s["RB"]] == ["RB1", "RB2"]
    assert [p["player_name"] for p in s["WR"]] == ["WR1", "WR2"]
    assert [p["player_name"] for p in s["TE"]] == ["TE1"]
    # FLEX takes the best remaining RB/WR/TE (WR3 140 > RB3 120).
    assert [p["player_name"] for p in s["FLEX"]] == ["WR3"]
    assert {p["player_name"] for p in lu["bench"]} == {"RB3"}


@pytest.mark.unit
def test_superflex_uses_qb_eligible_slot():
    roster = _ROSTER + [
        {"player_name": "QB2", "position": "QB", "projected_points": 320, "vorp": 65}
    ]
    lu = optimal_lineup(roster, "superflex")
    assert "SFLEX" in lu["starters"]
    # The SFLEX slot should be filled by the best leftover eligible player (QB2).
    assert lu["starters"]["SFLEX"][0]["player_name"] == "QB2"


@pytest.mark.unit
def test_drop_candidates_rank_weakest_bench_first():
    drops = drop_candidates(_ROSTER, "standard", top_n=3)
    assert drops  # at least one bench player
    assert drops[0]["player"]["player_name"] == "RB3"  # lowest value, benched
    assert "reason" in drops[0] and drops[0]["value"] == 5.0


@pytest.mark.unit
def test_drop_flags_positional_redundancy():
    roster = _ROSTER + [
        {"player_name": "RB4", "position": "RB", "projected_points": 90, "vorp": 1},
        {"player_name": "RB5", "position": "RB", "projected_points": 80, "vorp": 0},
    ]
    drops = drop_candidates(roster, "standard", top_n=3)
    reasons = " ".join(d["reason"] for d in drops)
    assert "redundant" in reasons  # 5 RB rostered, 2 start


@pytest.mark.unit
def test_optimal_lineup_handles_missing_points_and_empty():
    assert optimal_lineup([], "standard")["starters"] == {}
    weird = [{"player_name": "X", "position": "RB"}]  # no points key
    lu = optimal_lineup(weird, "standard")
    assert lu["starters"]["RB"][0]["player_name"] == "X"
