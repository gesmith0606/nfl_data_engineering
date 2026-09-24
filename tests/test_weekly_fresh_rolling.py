"""Which games feed the week-W weekly projection (double-lag regression).

Silver usage rows carry rolling columns built with ``shift(1)``: the week-k
row's ``*_roll3`` / ``*_std`` describe games strictly BEFORE week k. The
weekly engine projects week W from the week W-1 row, so by default those
columns stop at game W-2 — the most recent game never counts (2026-09-23
diagnosis, ``.planning/WEEKLY_DOUBLE_LAG_GATE.md``).

``fresh_rolling=True`` (the shipped default) re-derives the rolling columns
so the week-W projection uses games 1..W-1 exactly: never game W (no
same-week leakage), never stopping at W-2. ``include_bye_returns=True`` keeps
players whose team was on bye in W-1 on the board (they have no W-1 row and
were dropped).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from player_analytics import compute_rolling_averages  # noqa: E402
from projection_engine import (  # noqa: E402
    advance_rolling_features,
    bye_return_feature_rows,
    generate_weekly_projections,
)
import veteran_prior  # noqa: E402

# Per-game targets for the rising WR: game 4 is the role jump.
TARGETS = {1: 2.0, 2: 4.0, 3: 6.0, 4: 20.0}


def _game_rows(pid, team, season, stats_by_week, season_type="REG"):
    rows = []
    for w, tgt in stats_by_week.items():
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
                "targets": tgt,
                "receptions": tgt * 0.6,
                "receiving_yards": tgt * 8.0,
                "receiving_tds": 0.0,
                "target_share": tgt / 40.0,
                "snap_pct": 0.8,
            }
        )
    return rows


def _silver(rows) -> pd.DataFrame:
    """Build Silver exactly like the transformation does (shift(1) rolling)."""
    return compute_rolling_averages(pd.DataFrame(rows), windows=[3, 6])


@pytest.fixture
def silver() -> pd.DataFrame:
    return _silver(_game_rows("RISER", "SEA", 2025, TARGETS))


def test_silver_row_is_lagged_through_previous_game(silver):
    """Pins the Silver contract the engine builds on."""
    row4 = silver[silver["week"] == 4].iloc[0]
    assert row4["targets_roll3"] == pytest.approx(np.mean([2, 4, 6]))
    assert row4["targets_std"] == pytest.approx(np.mean([2, 4, 6]))


def test_advance_includes_the_feature_rows_own_game(silver):
    target = silver[silver["week"] == 4]
    out = advance_rolling_features(target, silver)
    row = out.iloc[0]
    # Week 5 projection must see games 2-4 (roll3) and 1-4 (std / roll6).
    assert row["targets_roll3"] == pytest.approx(np.mean([4, 6, 20]))
    assert row["targets_roll6"] == pytest.approx(np.mean([2, 4, 6, 20]))
    assert row["targets_std"] == pytest.approx(np.mean([2, 4, 6, 20]))
    assert row["target_share_roll3"] == pytest.approx(np.mean([4, 6, 20]) / 40)
    # Raw (unlagged) game-4 columns are untouched.
    assert row["targets"] == 20.0 and row["week"] == 4


def test_advance_ignores_later_games_and_other_seasons(silver):
    """No leakage: a week-5 game row and prior-season rows never count."""
    extra = _silver(
        _game_rows("RISER", "SEA", 2025, {**TARGETS, 5: 99.0})
        + _game_rows("RISER", "SEA", 2024, {17: 50.0})
    )
    out = advance_rolling_features(extra[(extra["week"] == 4)], extra)
    assert out.iloc[0]["targets_std"] == pytest.approx(np.mean([2, 4, 6, 20]))


def test_advance_equals_shifted_value_on_the_next_game_row():
    """Fresh week-W features == the Silver week-W row the models train on."""
    s = _silver(_game_rows("P", "SEA", 2025, {**TARGETS, 5: 11.0}))
    adv = advance_rolling_features(s[s["week"] == 4], s).iloc[0]
    nxt = s[s["week"] == 5].iloc[0]
    for col in ("targets_roll3", "targets_roll6", "targets_std", "snap_pct_roll3"):
        assert adv[col] == pytest.approx(nxt[col])


def test_fresh_rolling_is_the_default(silver):
    """SHIPPED default-on (gate passed); False reproduces the old double lag."""
    default = generate_weekly_projections(
        silver, pd.DataFrame(), season=2025, week=5, scoring_format="ppr"
    )
    fresh = generate_weekly_projections(
        silver,
        pd.DataFrame(),
        season=2025,
        week=5,
        scoring_format="ppr",
        fresh_rolling=True,
    )
    pd.testing.assert_frame_equal(default, fresh)


def test_fresh_rolling_projection_reflects_last_game(silver):
    stale = generate_weekly_projections(
        silver,
        pd.DataFrame(),
        season=2025,
        week=5,
        scoring_format="ppr",
        fresh_rolling=False,
    )
    fresh = generate_weekly_projections(
        silver,
        pd.DataFrame(),
        season=2025,
        week=5,
        scoring_format="ppr",
        fresh_rolling=True,
    )
    assert fresh["projected_points"].iloc[0] > stale["projected_points"].iloc[0]


def test_fresh_rolling_never_reads_the_projected_weeks_game():
    """A week-W row present in silver_df must not change the week-W projection."""
    without = _silver(_game_rows("P", "SEA", 2025, TARGETS))
    with_w = _silver(_game_rows("P", "SEA", 2025, {**TARGETS, 5: 99.0}))
    a = generate_weekly_projections(
        without,
        pd.DataFrame(),
        season=2025,
        week=5,
        scoring_format="ppr",
        fresh_rolling=True,
    )
    b = generate_weekly_projections(
        with_w,
        pd.DataFrame(),
        season=2025,
        week=5,
        scoring_format="ppr",
        fresh_rolling=True,
    )
    assert a["projected_points"].iloc[0] == pytest.approx(b["projected_points"].iloc[0])


def test_week1_seed_advances_through_the_final_regular_season_game():
    prior = _silver(
        _game_rows("VET", "KC", 2025, {16: 4.0, 17: 6.0, 18: 20.0})
        + _game_rows("VET", "KC", 2025, {19: 1.0}, season_type="POST")
    )
    fresh = generate_weekly_projections(
        prior,
        pd.DataFrame(),
        season=2026,
        week=1,
        scoring_format="ppr",
        fresh_rolling=True,
    )
    stale = generate_weekly_projections(
        prior,
        pd.DataFrame(),
        season=2026,
        week=1,
        scoring_format="ppr",
        fresh_rolling=False,
    )
    assert fresh["projected_points"].iloc[0] > stale["projected_points"].iloc[0]


# ---------------------------------------------------------------------------
# Bye returns: no W-1 row because the team did not play in W-1
# ---------------------------------------------------------------------------


@pytest.fixture
def bye_silver() -> pd.DataFrame:
    rows = (
        _game_rows("BYE_WR", "PHI", 2025, {1: 8.0, 2: 8.0, 3: 8.0})  # PHI bye wk4
        + _game_rows("PHI_WR2", "PHI", 2025, {1: 3.0, 2: 3.0})  # hurt wk3
        + _game_rows("HURT_WR", "SEA", 2025, {1: 9.0, 2: 9.0, 3: 9.0})  # misses wk4
        + _game_rows("SEA_WR", "SEA", 2025, {1: 5.0, 2: 5.0, 3: 5.0, 4: 5.0})
    )
    return _silver(rows)


def test_bye_return_rows_pick_players_who_played_their_teams_last_game(bye_silver):
    rows = bye_return_feature_rows(bye_silver, season=2025, week=5)
    assert set(rows["player_id"]) == {"BYE_WR"}
    assert int(rows.iloc[0]["week"]) == 3


def test_bye_returns_are_projected_by_default(bye_silver):
    off = generate_weekly_projections(
        bye_silver,
        pd.DataFrame(),
        season=2025,
        week=5,
        scoring_format="ppr",
        include_bye_returns=False,
    )
    assert set(off["player_id"]) == {"SEA_WR"}  # the pre-fix gap
    on = generate_weekly_projections(
        bye_silver, pd.DataFrame(), season=2025, week=5, scoring_format="ppr"
    )
    assert set(on["player_id"]) == {"SEA_WR", "BYE_WR"}
    assert (on["projected_points"] > 0).all()
    # Fresh rolling advances the bye player's week-3 row through game 3.
    assert not on.set_index("player_id").loc["BYE_WR", "is_rookie_projection"]


# ---------------------------------------------------------------------------
# Veteran prior game count follows the rolling window
# ---------------------------------------------------------------------------


def test_veteran_prior_lookback_follows_the_rolling_window():
    weekly = pd.DataFrame(
        {
            "player_id": ["P"] * 4,
            "season": [2025] * 4,
            "week": [1, 2, 3, 4],
            "targets": [5, 5, 5, 5],
        }
    )
    # Pre-fix window (and the residual-training path): games 1..W-2 -> 3.
    assert veteran_prior.count_games_in_lookback("P", 2025, 5, weekly) == 3
    # Fresh rolling covers 1..W-1 -> 4 games.
    assert (
        veteran_prior.count_games_in_lookback("P", 2025, 5, weekly, fresh_rolling=True)
        == 4
    )
