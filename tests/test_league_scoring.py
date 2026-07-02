"""Tests for custom league scoring + roster-positions lineup (Phase 91)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.league_scoring import score_with_settings, unmodeled_offense_keys
from src.roster_optimizer import optimal_lineup

# Mirrors the user's dynasty league: full PPR + TE premium + 6-pt pass TD.
_SETTINGS = {
    "pass_yd": 0.04,
    "pass_td": 6.0,
    "pass_int": -3.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rec": 1.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "bonus_rec_te": 1.0,
    "rec_fd": 0.5,  # unmodeled
}

_PROJ = pd.DataFrame(
    [
        {
            "player_name": "QB1",
            "position": "QB",
            "passing_yards": 4500,
            "passing_tds": 40,
            "interceptions": 10,
            "rushing_yards": 0,
            "rushing_tds": 0,
            "receptions": 0,
            "receiving_yards": 0,
            "receiving_tds": 0,
            "projected_season_points": 300,
        },
        {
            "player_name": "TE1",
            "position": "TE",
            "passing_yards": 0,
            "passing_tds": 0,
            "interceptions": 0,
            "rushing_yards": 0,
            "rushing_tds": 0,
            "receptions": 90,
            "receiving_yards": 1000,
            "receiving_tds": 8,
            "projected_season_points": 150,
        },
        {
            "player_name": "WR1",
            "position": "WR",
            "passing_yards": 0,
            "passing_tds": 0,
            "interceptions": 0,
            "rushing_yards": 0,
            "rushing_tds": 0,
            "receptions": 90,
            "receiving_yards": 1000,
            "receiving_tds": 8,
            "projected_season_points": 220,
        },
    ]
)


@pytest.mark.unit
def test_score_with_settings_applies_custom_rules():
    out = score_with_settings(_PROJ, _SETTINGS)
    pts = dict(zip(out["player_name"], out["projected_season_points"]))
    # QB: 4500*.04 + 40*6 + 10*-3 = 180 + 240 - 30 = 390
    assert pts["QB1"] == pytest.approx(390.0)
    # WR: 90*1 + 1000*.1 + 8*6 = 90 + 100 + 48 = 238
    assert pts["WR1"] == pytest.approx(238.0)
    # TE: same stats as WR + TE premium (90*1 extra) = 238 + 90 = 328
    assert pts["TE1"] == pytest.approx(328.0)
    # Original preset value preserved.
    assert "base_season_points" in out.columns


@pytest.mark.unit
def test_te_premium_lifts_te_above_equal_wr():
    out = score_with_settings(_PROJ, _SETTINGS)
    te = out[out["player_name"] == "TE1"]["projected_season_points"].iloc[0]
    wr = out[out["player_name"] == "WR1"]["projected_season_points"].iloc[0]
    assert te > wr  # identical receiving stats, TE wins on the premium


@pytest.mark.unit
def test_unmodeled_keys_reported():
    assert "rec_fd" in unmodeled_offense_keys(_SETTINGS)
    assert "rec" not in unmodeled_offense_keys(_SETTINGS)  # rec IS modeled


@pytest.mark.unit
def test_optimal_lineup_honors_roster_positions():
    roster = [
        {"player_name": "QB1", "position": "QB", "projected_points": 400},
        {"player_name": "QB2", "position": "QB", "projected_points": 330},
        {"player_name": "RB1", "position": "RB", "projected_points": 280},
        {"player_name": "WR1", "position": "WR", "projected_points": 300},
        {"player_name": "WR2", "position": "WR", "projected_points": 260},
        {"player_name": "WR3", "position": "WR", "projected_points": 230},
        {"player_name": "TE1", "position": "TE", "projected_points": 250},
        {"player_name": "TE2", "position": "TE", "projected_points": 240},
    ]
    positions = ["QB", "RB", "WR", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "BN", "BN"]
    lu = optimal_lineup(roster, roster_positions=positions)
    s = lu["starters"]
    assert len(s.get("WR", [])) == 3  # exactly 3 WR slots filled
    # FLEX takes best leftover RB/WR/TE (TE2 240), SFLEX takes best leftover incl QB2.
    assert s["SFLEX"][0]["player_name"] == "QB2"
    assert s["FLEX"][0]["player_name"] == "TE2"
    # 8-man roster fills 8 of the (BN-excluded) 8 starting slots → no bench.
    assert lu["bench"] == []
