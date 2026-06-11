"""Tests for route participation features (plan 2.2)."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from graph_route_participation import (
    ROUTE_PARTICIPATION_FEATURES,
    compute_route_participation,
)


def _pbp(n_weeks: int = 6, dropbacks_per_week: int = 10) -> pd.DataFrame:
    rows = []
    play = 0
    for week in range(1, n_weeks + 1):
        for i in range(dropbacks_per_week):
            play += 1
            rows.append(
                {
                    "game_id": f"2024_{week:02d}_AAA_BBB",
                    "play_id": play,
                    "season": 2024,
                    "week": week,
                    "posteam": "AAA",
                    "qb_dropback": 1,
                }
            )
        # a run play that must not count
        play += 1
        rows.append(
            {
                "game_id": f"2024_{week:02d}_AAA_BBB",
                "play_id": play,
                "season": 2024,
                "week": week,
                "posteam": "AAA",
                "qb_dropback": 0,
            }
        )
    return pd.DataFrame(rows)


def _participation(pbp: pd.DataFrame, part_time_rate: float = 0.5) -> pd.DataFrame:
    """Full-time player wr_full on every play; wr_part on half the dropbacks."""
    rows = []
    for r in pbp.itertuples(index=False):
        players = ["wr_full"]
        if r.play_id % 2 == 0:
            players.append("wr_part")
        rows.append(
            {
                "game_id": r.game_id,
                "play_id": r.play_id,
                "offense_players": ";".join(players),
            }
        )
    return pd.DataFrame(rows)


class TestComputeRouteParticipation:
    def test_route_rate_values(self):
        pbp = _pbp()
        out = compute_route_participation(pbp, _participation(pbp))
        full = out[out["player_id"] == "wr_full"]
        part = out[out["player_id"] == "wr_part"]
        assert (full["route_rate"] == 1.0).all()
        assert ((part["route_rate"] > 0.3) & (part["route_rate"] < 0.7)).all()

    def test_non_dropbacks_excluded(self):
        pbp = _pbp(n_weeks=2, dropbacks_per_week=10)
        out = compute_route_participation(pbp, _participation(pbp))
        # 10 dropbacks per week, not 11 (the run play is excluded)
        assert (out["team_dropbacks"] == 10).all()

    def test_trail_features_lagged(self):
        """trail4 at week W must not include week W's own rate."""
        pbp = _pbp(n_weeks=6)
        part = _participation(pbp)
        out = compute_route_participation(pbp, part)
        full = out[out["player_id"] == "wr_full"].sort_values("week")
        # weeks 1-2: insufficient history (min_periods=2 on shifted series)
        assert full[full["week"] <= 2]["route_rate_trail4"].isna().all()
        # week 3 trail = mean of weeks 1-2 (both 1.0)
        wk3 = full[full["week"] == 3]["route_rate_trail4"].iloc[0]
        assert wk3 == pytest.approx(1.0)

    def test_delta_is_prior_weeks_only(self):
        pbp = _pbp(n_weeks=4)
        out = compute_route_participation(pbp, _participation(pbp))
        full = out[out["player_id"] == "wr_full"].sort_values("week")
        # constant 1.0 rate -> delta 0 from week 3 on; week 1-2 NaN
        assert full[full["week"] >= 3]["route_rate_delta_trail2"].eq(0).all()
        assert full[full["week"] <= 2]["route_rate_delta_trail2"].isna().all()

    def test_empty_inputs(self):
        assert compute_route_participation(pd.DataFrame(), pd.DataFrame()).empty

    def test_feature_names_are_lagged_suffixed(self):
        from player_feature_engineering import _is_unlagged_leak

        for col in ROUTE_PARTICIPATION_FEATURES:
            assert not _is_unlagged_leak(col), col

    def test_raw_columns_are_excluded_from_features(self):
        from player_feature_engineering import _SAME_WEEK_RAW_STATS

        for col in ("route_rate", "dropbacks_on_field", "team_dropbacks"):
            assert col in _SAME_WEEK_RAW_STATS, col
