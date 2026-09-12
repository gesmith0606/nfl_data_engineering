"""Week 1 of a new season seeds rolling features from the prior season.

Regression for 2026-09-12: ``generate_projections.py --week 1 --season 2026``
loaded only current-season Silver (two games played) and emitted 47
rookie-baseline rows. The engine must instead take each player's final
regular-season row from season-1 when the caller supplies it.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from projection_engine import (  # noqa: E402
    generate_weekly_projections,
    prior_season_feature_rows,
)


def _wr_rows(pid: str, team: str, season: int, weeks, season_type="REG", yds=90.0):
    rows = []
    for w in weeks:
        rows.append(
            {
                "player_id": pid,
                "player_name": pid,
                "position": "WR",
                "recent_team": team,
                "season": season,
                "week": w,
                "season_type": season_type,
                "opponent": "NYJ",
                "receiving_yards_roll3": yds,
                "receiving_yards_roll6": yds,
                "receiving_yards_std": 20.0,
                "receiving_tds_roll3": 0.5,
                "receiving_tds_roll6": 0.5,
                "receiving_tds_std": 0.3,
                "receptions_roll3": 6.0,
                "receptions_roll6": 6.0,
                "receptions_std": 2.0,
                "targets_roll3": 9.0,
                "targets_roll6": 9.0,
                "targets_std": 3.0,
                "target_share": 0.25,
            }
        )
    return rows


@pytest.fixture
def silver_two_seasons() -> pd.DataFrame:
    prior = _wr_rows("VET", "KC", 2025, [16, 17, 18]) + _wr_rows(
        "VET", "KC", 2025, [19], season_type="POST", yds=5.0
    )
    prior += _wr_rows("NONPLAYOFF", "CAR", 2025, [17, 18])
    # Two games of the new season already played (the 47-row trap)
    current = _wr_rows("PLAYED", "SEA", 2026, [1], yds=30.0)
    return pd.DataFrame(prior + current)


def test_prior_season_feature_rows_takes_last_regular_season_row(silver_two_seasons):
    seeded = prior_season_feature_rows(silver_two_seasons, 2025)
    assert set(seeded["player_id"]) == {"VET", "NONPLAYOFF"}
    vet = seeded[seeded["player_id"] == "VET"].iloc[0]
    assert (
        vet["week"] == 18 and vet["receiving_yards_roll3"] == 90.0
    )  # not the POST row
    assert prior_season_feature_rows(silver_two_seasons, 2024).empty


def test_week1_projects_prior_season_players_not_rookie_baseline(silver_two_seasons):
    out = generate_weekly_projections(
        silver_two_seasons, pd.DataFrame(), season=2026, week=1, scoring_format="ppr"
    )
    assert {"VET", "NONPLAYOFF"} <= set(out["player_id"])
    vet = out[out["player_id"] == "VET"].iloc[0]
    assert not bool(vet["is_rookie_projection"])
    assert vet["proj_season"] == 2026 and vet["proj_week"] == 1
    # The prior-season seed replaces the partial current-season rows as source
    assert "PLAYED" not in set(out["player_id"])


def test_week1_without_prior_season_keeps_old_fallback():
    only_current = pd.DataFrame(_wr_rows("PLAYED", "SEA", 2026, [1], yds=30.0))
    out = generate_weekly_projections(
        only_current, pd.DataFrame(), season=2026, week=1, scoring_format="ppr"
    )
    assert set(out["player_id"]) == {"PLAYED"}


def test_mid_season_week_unaffected(silver_two_seasons):
    cur = pd.DataFrame(_wr_rows("MID", "SEA", 2026, [4], yds=70.0))
    df = pd.concat([silver_two_seasons, cur], ignore_index=True)
    out = generate_weekly_projections(
        df, pd.DataFrame(), season=2026, week=5, scoring_format="ppr"
    )
    assert set(out["player_id"]) == {"MID"}
    assert np.isfinite(out["projected_points"]).all()
