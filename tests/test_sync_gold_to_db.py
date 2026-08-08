"""
Regression test for _build_projected_stats_json column-name mismatch.

_upsert_projections() renames projection columns (e.g. proj_passing_yards ->
proj_pass_yards) BEFORE calling _build_projected_stats_json() on each row.
_build_projected_stats_json() previously looked up the pre-rename names, so
`col in row.index` never matched and `projected_stats` was always None.
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.sync_gold_to_db import _build_projected_stats_json


def _renamed_row() -> pd.Series:
    """A row shaped like what _upsert_projections passes in — i.e. AFTER
    its rename_map has already renamed proj_passing_yards -> proj_pass_yards
    etc."""
    return pd.Series(
        {
            "player_id": "00-0012345",
            "player_name": "Test Player",
            "position": "QB",
            "team": "KC",
            "season": 2026,
            "week": 1,
            "scoring_format": "half_ppr",
            "projected_points": 21.4,
            "proj_pass_yards": 275.0,
            "proj_pass_tds": 2.0,
            "proj_interceptions": 0.5,
            "proj_rush_yards": 15.0,
            "proj_rush_tds": 0.1,
            "proj_carries": 3.0,
            "proj_rec": 0.0,
            "proj_rec_yards": 0.0,
            "proj_rec_tds": 0.0,
            "proj_targets": 0.0,
        }
    )


def test_build_projected_stats_json_populates_from_renamed_columns():
    """A realistic post-rename row must produce a populated JSON, not None."""
    result = _build_projected_stats_json(_renamed_row())

    assert result is not None
    stats = json.loads(result)
    assert stats == {
        "passing_yards": 275.0,
        "passing_tds": 2.0,
        "interceptions": 0.5,
        "rushing_yards": 15.0,
        "rushing_tds": 0.1,
        "carries": 3.0,
        "receptions": 0.0,
        "receiving_yards": 0.0,
        "receiving_tds": 0.0,
        "targets": 0.0,
    }


def test_build_projected_stats_json_none_when_no_stat_columns_present():
    """A row with none of the expected (post-rename) stat columns yields None."""
    row = pd.Series({"player_id": "00-0012345", "projected_points": 21.4})
    assert _build_projected_stats_json(row) is None
