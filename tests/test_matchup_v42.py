"""Tests for the v4.2 heuristic upgrade: defensive-strength matchup factor,
TD regression, and per-position recency weights."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from player_analytics import compute_defensive_strength
from projection_engine import (
    MATCHUP_BETA,
    POSITION_RECENCY_WEIGHTS,
    TD_LEAGUE_RATES,
    TD_REGRESSION_WEIGHT,
    _apply_td_regression,
    _matchup_factor,
    _weighted_baseline,
)


# ---------------------------------------------------------------------------
# compute_defensive_strength
# ---------------------------------------------------------------------------


def _synthetic_weekly(n_weeks: int = 10) -> pd.DataFrame:
    """Two teams (AAA, BBB) playing each other every week; AAA's defense
    allows twice the WR production BBB's does."""
    rows = []
    for week in range(1, n_weeks + 1):
        # WR on AAA scores 10 receiving yards against BBB defense
        rows.append(
            {
                "player_id": "wr_a",
                "player_name": "WR A",
                "position": "WR",
                "recent_team": "AAA",
                "season": 2024,
                "week": week,
                "receiving_yards": 100.0,
                "receptions": 5.0,
            }
        )
        # WR on BBB scores 200 receiving yards against AAA defense
        rows.append(
            {
                "player_id": "wr_b",
                "player_name": "WR B",
                "position": "WR",
                "recent_team": "BBB",
                "season": 2024,
                "week": week,
                "receiving_yards": 200.0,
                "receptions": 5.0,
            }
        )
    return pd.DataFrame(rows)


def _synthetic_schedule(n_weeks: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [2024] * n_weeks,
            "week": list(range(1, n_weeks + 1)),
            "home_team": ["AAA"] * n_weeks,
            "away_team": ["BBB"] * n_weeks,
        }
    )


class TestComputeDefensiveStrength:
    def test_ratio_reflects_relative_defense(self):
        strength = compute_defensive_strength(
            _synthetic_weekly(), _synthetic_schedule(), min_games=2
        )
        wr = strength[strength["position"] == "WR"]
        assert not wr.empty
        # AAA's defense allows the 200-yard WR -> ratio > 1 (favorable)
        aaa = wr[wr["team"] == "AAA"]["ratio"]
        bbb = wr[wr["team"] == "BBB"]["ratio"]
        assert (aaa > 1.0).all()
        assert (bbb < 1.0).all()

    def test_lagged_no_same_week_leakage(self):
        # min_games=2 means the first emitted row needs 2 *prior* games:
        # nothing before week 3 (weeks 1-2 are the lookback).
        strength = compute_defensive_strength(
            _synthetic_weekly(), _synthetic_schedule(), min_games=2
        )
        assert strength["week"].min() >= 3

    def test_empty_inputs(self):
        out = compute_defensive_strength(pd.DataFrame(), pd.DataFrame())
        assert out.empty


# ---------------------------------------------------------------------------
# _matchup_factor new-style path
# ---------------------------------------------------------------------------


class TestMatchupFactorStrengthPath:
    def _strength_table(self, ratio: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["BBB"],
                "position": ["RB"],
                "ratio": [ratio],
            }
        )

    def _player_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "season": [2024],
                "week": [4],  # feature row from the prior week
                "proj_season": [2024],
                "proj_week": [5],
                "recent_team": ["AAA"],
                "opponent": ["BBB"],
            }
        )

    def test_favorable_matchup_boosts(self):
        factor = _matchup_factor(self._player_df(), self._strength_table(1.2), "RB")
        expected = 1.0 + MATCHUP_BETA["RB"] * 0.2
        assert factor.iloc[0] == pytest.approx(min(expected, 1.15))

    def test_unknown_opponent_neutral(self):
        df = self._player_df()
        df["opponent"] = ["ZZZ"]
        factor = _matchup_factor(df, self._strength_table(1.2), "RB")
        assert factor.iloc[0] == 1.0

    def test_clip_bounds(self):
        low = _matchup_factor(self._player_df(), self._strength_table(0.2), "RB")
        high = _matchup_factor(self._player_df(), self._strength_table(3.0), "RB")
        assert low.iloc[0] == pytest.approx(0.85)
        assert high.iloc[0] == pytest.approx(1.15)

    def test_missing_opponent_column_neutral(self):
        df = self._player_df().drop(columns=["opponent"])
        factor = _matchup_factor(df, self._strength_table(1.2), "RB")
        assert (factor == 1.0).all()

    def test_legacy_rank_path_still_works(self):
        rankings = pd.DataFrame(
            {
                "season": [2024],
                "week": [4],
                "team": ["BBB"],
                "position": ["RB"],
                "rank": [1],
            }
        )
        factor = _matchup_factor(self._player_df(), rankings, "RB")
        assert factor.iloc[0] == pytest.approx(1.15)


# ---------------------------------------------------------------------------
# TD regression
# ---------------------------------------------------------------------------


class TestTdRegression:
    def test_full_weight_equals_yardage_implied(self):
        proj = {
            "proj_rushing_tds": pd.Series([0.9]),
            "proj_rushing_yards": pd.Series([100.0]),
            "proj_receiving_tds": pd.Series([0.5]),
            "proj_receiving_yards": pd.Series([50.0]),
        }
        orig = TD_REGRESSION_WEIGHT.get("RB")
        TD_REGRESSION_WEIGHT["RB"] = 1.0
        try:
            out = _apply_td_regression(dict(proj), "RB")
        finally:
            TD_REGRESSION_WEIGHT["RB"] = orig
        rate = TD_LEAGUE_RATES["RB"]["rushing_tds"][1]
        assert out["proj_rushing_tds"].iloc[0] == pytest.approx(100.0 * rate, abs=1e-3)

    def test_zero_weight_is_noop(self):
        proj = {
            "proj_receiving_tds": pd.Series([0.5]),
            "proj_receiving_yards": pd.Series([50.0]),
        }
        orig = TD_REGRESSION_WEIGHT.get("WR")
        TD_REGRESSION_WEIGHT["WR"] = 0.0
        try:
            out = _apply_td_regression(dict(proj), "WR")
        finally:
            TD_REGRESSION_WEIGHT["WR"] = orig
        assert out["proj_receiving_tds"].iloc[0] == 0.5

    def test_yards_never_modified(self):
        proj = {
            "proj_receiving_tds": pd.Series([0.5]),
            "proj_receiving_yards": pd.Series([50.0]),
        }
        out = _apply_td_regression(dict(proj), "WR")
        assert out["proj_receiving_yards"].iloc[0] == 50.0


# ---------------------------------------------------------------------------
# Per-position recency weights
# ---------------------------------------------------------------------------


class TestPositionRecencyWeights:
    def test_wr_uses_pure_season_to_date(self):
        df = pd.DataFrame(
            {
                "receiving_yards_roll3": [100.0],
                "receiving_yards_roll6": [80.0],
                "receiving_yards_std": [60.0],
            }
        )
        result = _weighted_baseline(df, "receiving_yards", "WR")
        assert result.iloc[0] == pytest.approx(60.0)

    def test_no_position_falls_back_to_global(self):
        df = pd.DataFrame(
            {
                "rushing_yards_roll3": [100.0],
                "rushing_yards_roll6": [80.0],
                "rushing_yards_std": [90.0],
            }
        )
        from projection_engine import RECENCY_WEIGHTS

        result = _weighted_baseline(df, "rushing_yards")
        expected = (
            100 * RECENCY_WEIGHTS["roll3"]
            + 80 * RECENCY_WEIGHTS["roll6"]
            + 90 * RECENCY_WEIGHTS["std"]
        )
        assert result.iloc[0] == pytest.approx(expected)

    def test_missing_weighted_columns_falls_back(self):
        # WR weights are 100% std; with no _std column the baseline must
        # fall back to the global blend instead of projecting zero.
        df = pd.DataFrame(
            {
                "receiving_yards_roll3": [100.0],
                "receiving_yards_roll6": [80.0],
            }
        )
        result = _weighted_baseline(df, "receiving_yards", "WR")
        assert result.iloc[0] > 0.0

    def test_all_positions_have_weights_summing_to_one(self):
        for pos, weights in POSITION_RECENCY_WEIGHTS.items():
            assert sum(weights.values()) == pytest.approx(1.0), pos
