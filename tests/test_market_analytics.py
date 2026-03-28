#!/usr/bin/env python3
"""Tests for market_analytics.py -- line movement features and per-team reshape."""

import sys
import os
import math

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from market_analytics import compute_movement_features, reshape_to_per_team


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_odds_df(n=5, **overrides):
    """Create a minimal Bronze odds DataFrame with realistic defaults.

    Args:
        n: Number of game rows to generate.
        **overrides: Column-level overrides (value or list of length n).

    Returns:
        DataFrame matching Bronze odds schema (14 columns).
    """
    teams = [
        ("KC", "BUF"), ("SF", "DAL"), ("PHI", "NYG"),
        ("DET", "GB"), ("BAL", "CIN"),
    ]
    data = {
        "game_id": [f"2020_01_GAME{i}" for i in range(n)],
        "season": [2020] * n,
        "week": [1] * n,
        "game_type": ["REG"] * n,
        "home_team": [teams[i % len(teams)][0] for i in range(n)],
        "away_team": [teams[i % len(teams)][1] for i in range(n)],
        "opening_spread": [-3.0, -7.0, 2.5, -1.0, -4.5][:n],
        "closing_spread": [-3.5, -6.5, 3.0, -1.5, -5.0][:n],
        "opening_total": [45.0, 48.0, 42.5, 50.0, 44.0][:n],
        "closing_total": [44.0, 47.5, 43.0, 49.5, 44.5][:n],
        "home_moneyline": [-150, -350, 120, -110, -200][:n],
        "away_moneyline": [130, 280, -140, -110, 170][:n],
        "nflverse_spread_line": [-3.5, -6.5, 3.0, -1.5, -5.0][:n],
        "nflverse_total_line": [44.0, 47.5, 43.0, 49.5, 44.5][:n],
    }
    df = pd.DataFrame(data)
    for col, val in overrides.items():
        df[col] = val
    return df


# ---------------------------------------------------------------------------
# TestMovementComputation
# ---------------------------------------------------------------------------


class TestMovementComputation:
    """Tests for compute_movement_features() shift and absolute computations."""

    def test_spread_shift(self):
        df = _make_odds_df(1, opening_spread=[-3.0], closing_spread=[-3.5])
        result = compute_movement_features(df)
        assert result["spread_shift"].iloc[0] == pytest.approx(-0.5)

    def test_total_shift(self):
        df = _make_odds_df(1, opening_total=[45.0], closing_total=[44.0])
        result = compute_movement_features(df)
        assert result["total_shift"].iloc[0] == pytest.approx(-1.0)

    def test_absolute_movement(self):
        df = _make_odds_df(1, opening_spread=[-3.0], closing_spread=[-3.5])
        result = compute_movement_features(df)
        assert result["spread_move_abs"].iloc[0] == pytest.approx(0.5)

    def test_all_columns_present(self):
        result = compute_movement_features(_make_odds_df())
        expected_cols = [
            "spread_shift", "total_shift",
            "spread_move_abs", "total_move_abs",
            "spread_magnitude", "total_magnitude",
            "crosses_key_spread", "crosses_key_total",
            "is_steam_move",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"
        # Plus original 14 columns = 14 + 9 = 23 minimum
        # (closing_spread/total already in original; spread_shift etc are new)
        assert len(result.columns) >= 23


# ---------------------------------------------------------------------------
# TestMagnitudeBuckets
# ---------------------------------------------------------------------------


class TestMagnitudeBuckets:
    """Tests for magnitude bucket computation (ordinal 0-3)."""

    def test_none_bucket(self):
        df = _make_odds_df(1, opening_spread=[-3.0], closing_spread=[-3.0])
        result = compute_movement_features(df)
        assert result["spread_magnitude"].iloc[0] == 0.0

    def test_small_bucket(self):
        df = _make_odds_df(1, opening_spread=[-3.0], closing_spread=[-3.5])
        result = compute_movement_features(df)
        assert result["spread_magnitude"].iloc[0] == 1.0

    def test_medium_bucket(self):
        df = _make_odds_df(1, opening_spread=[-3.0], closing_spread=[-4.5])
        result = compute_movement_features(df)
        assert result["spread_magnitude"].iloc[0] == 2.0

    def test_large_bucket(self):
        df = _make_odds_df(1, opening_spread=[-3.0], closing_spread=[-5.5])
        result = compute_movement_features(df)
        assert result["spread_magnitude"].iloc[0] == 3.0

    def test_magnitude_is_float_not_string(self):
        result = compute_movement_features(_make_odds_df())
        assert result["spread_magnitude"].dtype == np.float64
        assert result["total_magnitude"].dtype == np.float64


# ---------------------------------------------------------------------------
# TestKeyNumberCrossing
# ---------------------------------------------------------------------------


class TestKeyNumberCrossing:
    """Tests for crosses_key_spread and crosses_key_total booleans."""

    def test_crosses_3(self):
        df = _make_odds_df(1, opening_spread=[2.5], closing_spread=[3.5])
        result = compute_movement_features(df)
        assert result["crosses_key_spread"].iloc[0] is True or result["crosses_key_spread"].iloc[0] == True

    def test_no_crossing(self):
        df = _make_odds_df(1, opening_spread=[4.0], closing_spread=[4.5])
        result = compute_movement_features(df)
        assert result["crosses_key_spread"].iloc[0] is False or result["crosses_key_spread"].iloc[0] == False

    def test_total_crossing_44(self):
        df = _make_odds_df(1, opening_total=[43.5], closing_total=[44.5])
        result = compute_movement_features(df)
        assert result["crosses_key_total"].iloc[0] is True or result["crosses_key_total"].iloc[0] == True


# ---------------------------------------------------------------------------
# TestSteamMove
# ---------------------------------------------------------------------------


class TestSteamMove:
    """Tests for is_steam_move placeholder column."""

    def test_is_steam_move_all_nan(self):
        result = compute_movement_features(_make_odds_df())
        assert result["is_steam_move"].isna().all()

    def test_column_exists(self):
        result = compute_movement_features(_make_odds_df())
        assert "is_steam_move" in result.columns


# ---------------------------------------------------------------------------
# TestPerTeamReshape
# ---------------------------------------------------------------------------


class TestPerTeamReshape:
    """Tests for reshape_to_per_team() unpivot logic."""

    def _get_reshaped(self, n=5):
        odds = _make_odds_df(n)
        with_features = compute_movement_features(odds)
        return reshape_to_per_team(with_features), odds

    def test_row_count_doubles(self):
        reshaped, _ = self._get_reshaped(5)
        assert len(reshaped) == 10  # 5 games -> 10 per-team rows

    def test_home_row_has_is_home_true(self):
        reshaped, odds = self._get_reshaped(1)
        home_row = reshaped[reshaped["team"] == odds["home_team"].iloc[0]]
        assert home_row["is_home"].iloc[0] == True

    def test_away_spread_negated(self):
        odds = _make_odds_df(1, opening_spread=[-3.0])
        with_features = compute_movement_features(odds)
        reshaped = reshape_to_per_team(with_features)
        away_row = reshaped[reshaped["is_home"] == False]
        # Away opening_spread should be negated: -(-3.0) = 3.0
        assert away_row["opening_spread"].iloc[0] == pytest.approx(3.0)

    def test_symmetric_totals_same(self):
        reshaped, odds = self._get_reshaped(1)
        home_row = reshaped[reshaped["is_home"] == True]
        away_row = reshaped[reshaped["is_home"] == False]
        assert home_row["opening_total"].iloc[0] == away_row["opening_total"].iloc[0]

    def test_symmetric_magnitude_same(self):
        reshaped, odds = self._get_reshaped(1)
        home_row = reshaped[reshaped["is_home"] == True]
        away_row = reshaped[reshaped["is_home"] == False]
        assert home_row["spread_magnitude"].iloc[0] == away_row["spread_magnitude"].iloc[0]

    def test_output_columns(self):
        reshaped, _ = self._get_reshaped()
        required = [
            "team", "opponent", "season", "week", "game_id", "game_type",
            "is_home", "opening_spread", "closing_spread", "spread_shift",
            "opening_total", "closing_total", "total_shift",
            "spread_move_abs", "total_move_abs",
            "spread_magnitude", "total_magnitude",
            "crosses_key_spread", "crosses_key_total", "is_steam_move",
        ]
        for col in required:
            assert col in reshaped.columns, f"Missing column: {col}"
