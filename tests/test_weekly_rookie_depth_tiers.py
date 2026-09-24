"""Weekly rookie fallback takes its starter/backup tier from the depth chart.

Regression for 2026 weeks 1-2 (.planning/SEASON_2026_WEEKS_1_2_RETRO.md):

* Week 2: every 2026 rookie was projected at the 25% "unknown" tier (3.1-3.4
  pts; Jadarian Price was SEA's RB1). ``_determine_usage_role`` reads
  ``snap_pct_std`` / ``target_share_std``, which come from the same
  ``shift(1)`` window as the rolling stat columns — so on exactly the rows
  that hit the fallback (all rolling stats NaN) they are NaN too, and the
  role was always "unknown". Weekly mode had no depth-chart join at all.
* Week 1: the prior-season seed only carries players with a prior-season
  row, so rookies were absent from the board entirely.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from projection_engine import (  # noqa: E402
    _ROLE_SCALE,
    _STARTER_BASELINES,
    depth_chart_roles,
    generate_weekly_projections,
)

_OLD, _NEW = "2026-09-01T06:00:00Z", "2026-09-08T06:00:00Z"


def _dc(team, pos, rank, gsis, name, dt=_NEW):
    return {
        "dt": dt,
        "team": team,
        "player_name": name,
        "gsis_id": gsis,
        "pos_abb": pos,
        "pos_rank": rank,
    }


@pytest.fixture
def depth_charts() -> pd.DataFrame:
    rows = [
        # Stale snapshot: rookie was RB2 a week earlier -> must be ignored
        _dc("SEA", "RB", 2, "ROOKIE_RB", "Jadarian Price", dt=_OLD),
        _dc("SEA", "RB", 1, "VET_RB", "Zach Charbonnet", dt=_OLD),
        _dc("SEA", "RB", 1, "ROOKIE_RB", "Jadarian Price"),
        _dc("SEA", "RB", 2, "VET_RB", "Zach Charbonnet"),
        _dc("SEA", "RB", 3, "DEEP_RB", "George Holani"),
        _dc("MIA", "WR", 1, "MIA_WR1", "Jaylen Waddle"),
        _dc("MIA", "WR", 2, "ROOKIE_WR", "Caleb Douglas"),
        _dc("MIA", "WR", 3, "MIA_WR3", "Somebody Else"),
        _dc("MIA", "WR", 4, "MIA_WR4", "Fourth Receiver"),
        _dc("MIA", "WR", 5, "MIA_WR5", "Fifth Receiver"),
        _dc("MIA", "QB", 1, "MIA_QB1", "Malik Willis"),
        _dc("MIA", "QB", 2, "MIA_QB2", "Backup Passer"),
        _dc("MIA", "LT", 1, "MIA_LT", "Left Tackle"),  # non-fantasy: ignored
        _dc("MIA", "TE", 1, None, "No Gsis"),  # no id: ignored
    ]
    return pd.DataFrame(rows)


def test_depth_chart_roles_latest_snapshot_and_position_slots(depth_charts):
    roles = depth_chart_roles(depth_charts).set_index("player_id")["depth_role"]
    assert roles["ROOKIE_RB"] == "starter"  # latest snapshot, not the stale RB2
    assert roles["VET_RB"] == "backup"
    assert roles["DEEP_RB"] == "unknown"
    # Base personnel is 3 WR: WR1-3 start, WR4 is the backup, WR5+ unknown
    assert roles["ROOKIE_WR"] == "starter"
    assert roles["MIA_WR3"] == "starter"
    assert roles["MIA_WR4"] == "backup"
    assert roles["MIA_WR5"] == "unknown"
    assert roles["MIA_QB2"] == "backup"
    assert "MIA_LT" not in roles.index
    assert len(roles) == 10


def test_depth_chart_roles_empty_inputs():
    assert depth_chart_roles(None).empty
    assert depth_chart_roles(pd.DataFrame()).empty
    assert depth_chart_roles(pd.DataFrame({"team": ["SEA"]})).empty


# ---------------------------------------------------------------------------
# Week 2+: rookie row exists (played last week) but has no rolling history
# ---------------------------------------------------------------------------


def _rookie_rb_row(pid="ROOKIE_RB", team="SEA", week=1):
    # A week-1 Silver row: raw game stats present, every shift(1) column NaN.
    return {
        "player_id": pid,
        "player_name": "J.Price",
        "position": "RB",
        "recent_team": team,
        "season": 2026,
        "week": week,
        "season_type": "REG",
        "rushing_yards": 60.0,
        "carries": 14.0,
        "carry_share": 0.55,
        "snap_pct": 0.52,
        "rushing_yards_roll3": np.nan,
        "rushing_yards_std": np.nan,
        "carries_roll3": np.nan,
        "snap_pct_std": np.nan,
        "carry_share_std": np.nan,
    }


def _vet_rb_row(pid="VET_RB", team="SEA", week=1):
    return {
        "player_id": pid,
        "player_name": "Z.Charbonnet",
        "position": "RB",
        "recent_team": team,
        "season": 2026,
        "week": week,
        "season_type": "REG",
        "carry_share": 0.35,
        "snap_pct": 0.40,
        "rushing_yards_roll3": 50.0,
        "rushing_yards_roll6": 48.0,
        "rushing_yards_std": 45.0,
        "rushing_tds_roll3": 0.4,
        "rushing_tds_roll6": 0.4,
        "rushing_tds_std": 0.3,
        "carries_roll3": 12.0,
        "carries_roll6": 12.0,
        "carries_std": 11.0,
        "receptions_roll3": 2.0,
        "receptions_roll6": 2.0,
        "receptions_std": 2.0,
        "receiving_yards_roll3": 15.0,
        "receiving_yards_roll6": 15.0,
        "receiving_yards_std": 14.0,
        "snap_pct_std": 0.45,
    }


def _project(silver, week=2, depth=None, fresh_rolling=False):
    # fresh_rolling=False: these tests pin the no-history fallback path. With
    # the shipped default (fresh rolling, WEEKLY_DOUBLE_LAG_GATE.md) a rookie
    # who played week 1 has real history in week 2 and skips the fallback —
    # see test_week2_rookie_with_a_game_is_projected_from_it below.
    return generate_weekly_projections(
        silver,
        pd.DataFrame(),
        season=2026,
        week=week,
        scoring_format="half_ppr",
        depth_charts_df=depth,
        fresh_rolling=fresh_rolling,
    ).set_index("player_id")


def test_week2_rookie_with_a_game_is_projected_from_it(depth_charts):
    """Default fresh rolling: the week-1 game is history, not a fallback."""
    silver = pd.DataFrame([_rookie_rb_row(), _vet_rb_row()])
    out = _project(silver, depth=depth_charts, fresh_rolling=True)
    assert not bool(out.loc["ROOKIE_RB", "is_rookie_projection"])
    assert out.loc["ROOKIE_RB", "proj_carries"] > 0


def test_week2_rookie_uses_depth_chart_starter_tier(depth_charts):
    silver = pd.DataFrame([_rookie_rb_row(), _vet_rb_row()])
    before = _project(silver)
    after = _project(silver, depth=depth_charts)

    assert bool(after.loc["ROOKIE_RB", "is_rookie_projection"])
    # Without a depth chart: unchanged legacy behaviour (25% unknown tier)
    unknown_yds = before.loc["ROOKIE_RB", "proj_rushing_yards"]
    starter_yds = after.loc["ROOKIE_RB", "proj_rushing_yards"]
    expected_ratio = _ROLE_SCALE["starter"] / _ROLE_SCALE["unknown"]
    assert starter_yds == pytest.approx(unknown_yds * expected_ratio, rel=0.01)
    assert (
        after.loc["ROOKIE_RB", "projected_points"]
        > before.loc["ROOKIE_RB", "projected_points"] + 5
    )


def test_week2_veterans_unchanged_by_depth_chart(depth_charts):
    # VET_RB is the depth-chart RB2 but has rolling history — no change.
    silver = pd.DataFrame([_rookie_rb_row(), _vet_rb_row()])
    before = _project(silver)
    after = _project(silver, depth=depth_charts)
    cols = [
        c for c in before.columns if c.startswith("proj_") or c == "projected_points"
    ]
    pd.testing.assert_series_equal(
        before.loc["VET_RB", cols], after.loc["VET_RB", cols], check_names=False
    )
    assert not bool(after.loc["VET_RB", "is_rookie_projection"])


def test_rookie_missing_from_depth_chart_keeps_usage_role(depth_charts):
    silver = pd.DataFrame([_rookie_rb_row(pid="UNLISTED")])
    before = _project(silver)
    after = _project(silver, depth=depth_charts)
    assert after.loc["UNLISTED", "projected_points"] == pytest.approx(
        before.loc["UNLISTED", "projected_points"]
    )


# ---------------------------------------------------------------------------
# Week 1: rookies have no prior-season row -> inject from the depth chart
# ---------------------------------------------------------------------------


def _prior_season_rows():
    rows = []
    for pid, team, pos in (("VET_RB", "SEA", "RB"), ("MIA_WR1", "MIA", "WR")):
        for w in (17, 18):
            row = _vet_rb_row(pid=pid, team=team, week=w)
            row.update(season=2025, position=pos)
            if pos == "WR":
                row.update(
                    receiving_yards_roll3=70.0,
                    receiving_yards_roll6=70.0,
                    receiving_yards_std=65.0,
                    targets_roll3=7.0,
                    targets_roll6=7.0,
                    targets_std=7.0,
                    target_share=0.22,
                )
            rows.append(row)
    return pd.DataFrame(rows)


def test_week1_injects_depth_chart_rookies(depth_charts):
    prior = _prior_season_rows()
    without = _project(prior, week=1)
    assert "ROOKIE_RB" not in without.index  # the 2026 bug

    out = _project(prior, week=1, depth=depth_charts)
    # Starter/backup newcomers are injected ...
    for pid in ("ROOKIE_RB", "ROOKIE_WR", "MIA_WR3", "MIA_WR4", "MIA_QB1", "MIA_QB2"):
        assert pid in out.index, pid
    # ... deep depth (25% tier) is not, and seeded veterans are not duplicated
    assert "DEEP_RB" not in out.index and "MIA_WR5" not in out.index
    assert out.index.is_unique

    rb = out.loc["ROOKIE_RB"]
    assert bool(rb["is_rookie_projection"])
    assert rb["position"] == "RB" and rb["recent_team"] == "SEA"
    assert rb["player_name"] == "J.Price"
    assert rb["proj_season"] == 2026 and rb["proj_week"] == 1
    assert rb["proj_rushing_yards"] == pytest.approx(
        _STARTER_BASELINES["RB"]["rushing_yards"], rel=0.25
    )
    # WR2 on the chart = starter tier; WR4 = backup tier
    assert out.loc["ROOKIE_WR", "proj_receiving_yards"] > (
        2 * out.loc["MIA_WR4", "proj_receiving_yards"]
    )
    # Veterans' week-1 projections are untouched by the injection
    cols = [
        c for c in without.columns if c.startswith("proj_") or c == "projected_points"
    ]
    for pid in ("VET_RB", "MIA_WR1"):
        pd.testing.assert_series_equal(
            without.loc[pid, cols], out.loc[pid, cols], check_names=False
        )
