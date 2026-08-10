"""Regression tests for _prepare_snap_data's name->id join.

Two real incidents:
- 2026-08-09: name-format mismatch (abbreviated vs full) made the join match
  0% of rows since inception (snap_pct all-NaN in every Silver season).
- 2026-08-10: the fix joined on display name only, which is NOT unique
  league-wide (two Aaron Brewers) -- same-name players fanned out into
  duplicate rows and 332 duplicate player_ids blocked the pipeline run.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.silver_player_transformation import _prepare_snap_data


def _weekly(rows):
    return pd.DataFrame(
        rows, columns=["player_id", "player_display_name", "recent_team"]
    )


def _snap(rows):
    return pd.DataFrame(
        rows, columns=["player", "team", "week", "offense_pct"]
    )


def test_same_name_different_teams_no_fanout():
    weekly = _weekly(
        [
            ["00-0001", "Aaron Brewer", "ARI"],
            ["00-0002", "Aaron Brewer", "TEN"],
        ]
    )
    snap = _snap([["Aaron Brewer", "ARI", 1, 0.05], ["Aaron Brewer", "TEN", 1, 0.90]])
    out = _prepare_snap_data(snap, weekly)
    assert len(out) == 2
    assert out.duplicated(subset=["player", "team", "week"]).sum() == 0
    by_team = out.set_index("team")["player_id"]
    assert by_team["ARI"] == "00-0001"
    assert by_team["TEN"] == "00-0002"


def test_full_display_name_matches():
    weekly = _weekly([["00-0003", "Cooper Kupp", "LA"]])
    snap = _snap([["Cooper Kupp", "LA", 1, 0.95]])
    out = _prepare_snap_data(snap, weekly)
    assert len(out) == 1
    assert out.iloc[0]["player_id"] == "00-0003"
    assert out.iloc[0]["snap_pct"] == 0.95


def test_unmatched_rows_dropped_not_null():
    weekly = _weekly([["00-0003", "Cooper Kupp", "LA"]])
    snap = _snap([["Unknown Guy", "LA", 1, 0.5], ["Cooper Kupp", "LA", 1, 0.95]])
    out = _prepare_snap_data(snap, weekly)
    assert len(out) == 1
    assert out["player_id"].notna().all()
