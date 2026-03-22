"""Tests for the weekly NFL game prediction pipeline.

Tests cover:
- classify_tier() confidence tier classification
- generate_week_predictions() edge computation, sorting, schema
- Missing Vegas line handling
- Independent tier classification
"""

import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_predictions import classify_tier, generate_week_predictions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_game_features():
    """DataFrame with 4 games for season=2025, week=10."""
    return pd.DataFrame(
        {
            "game_id": [
                "2025_10_KC_BUF",
                "2025_10_SF_DAL",
                "2025_10_PHI_NYG",
                "2025_10_DEN_LV",
            ],
            "season": [2025, 2025, 2025, 2025],
            "week": [10, 10, 10, 10],
            "home_team": ["BUF", "DAL", "NYG", "LV"],
            "away_team": ["KC", "SF", "PHI", "DEN"],
            "spread_line": [-3.0, 1.5, 7.0, float("nan")],
            "total_line": [48.5, 44.0, 40.5, float("nan")],
            "actual_margin": [float("nan")] * 4,
            "actual_total": [float("nan")] * 4,
            "diff_epa_per_play": [0.05, -0.10, 0.20, 0.00],
            "diff_pass_rate": [0.02, -0.05, 0.08, 0.01],
            "diff_rush_yards_per_game": [10.0, -5.0, 15.0, 2.0],
            "diff_third_down_pct": [0.03, -0.02, 0.06, 0.00],
            "diff_turnover_margin": [0.5, -0.3, 1.0, 0.1],
        }
    )


class MockModel:
    """Simple mock that returns fixed prediction values."""

    def __init__(self, values):
        self._values = values

    def predict(self, X):
        return np.array(self._values[: len(X)])


@pytest.fixture
def mock_spread_model():
    """Spread model returning [-3.5, -7.0, 2.5, -1.0]."""
    return MockModel([-3.5, -7.0, 2.5, -1.0])


@pytest.fixture
def mock_total_model():
    """Total model returning [44.5, 48.0, 41.0, 52.5]."""
    return MockModel([44.5, 48.0, 41.0, 52.5])


@pytest.fixture
def mock_metadata():
    """Model metadata with 5 feature names."""
    return {
        "feature_names": [
            "diff_epa_per_play",
            "diff_pass_rate",
            "diff_rush_yards_per_game",
            "diff_third_down_pct",
            "diff_turnover_margin",
        ]
    }


# ---------------------------------------------------------------------------
# classify_tier tests
# ---------------------------------------------------------------------------


class TestClassifyTier:
    def test_classify_tier_high(self):
        assert classify_tier(3.0) == "high"
        assert classify_tier(5.5) == "high"

    def test_classify_tier_medium(self):
        assert classify_tier(1.5) == "medium"
        assert classify_tier(2.9) == "medium"

    def test_classify_tier_low(self):
        assert classify_tier(0.5) == "low"
        assert classify_tier(1.4) == "low"

    def test_classify_tier_nan(self):
        assert classify_tier(float("nan")) is None


# ---------------------------------------------------------------------------
# generate_week_predictions tests
# ---------------------------------------------------------------------------


class TestGenerateWeekPredictions:
    def test_predictions_generated(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        assert len(result) == 4

    def test_edge_computation(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        # Game 0: KC@BUF — spread: model=-3.5, vegas=-3.0 => edge=-0.5
        kc_buf = result[result["game_id"] == "2025_10_KC_BUF"].iloc[0]
        assert kc_buf["spread_edge"] == pytest.approx(-0.5)
        # Game 0: total: model=44.5, vegas=48.5 => edge=-4.0
        assert kc_buf["total_edge"] == pytest.approx(-4.0)

        # Game 1: SF@DAL — spread: model=-7.0, vegas=1.5 => edge=-8.5
        sf_dal = result[result["game_id"] == "2025_10_SF_DAL"].iloc[0]
        assert sf_dal["spread_edge"] == pytest.approx(-8.5)
        # total: model=48.0, vegas=44.0 => edge=4.0
        assert sf_dal["total_edge"] == pytest.approx(4.0)

    def test_missing_vegas_lines(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        den_lv = result[result["game_id"] == "2025_10_DEN_LV"].iloc[0]
        assert pd.isna(den_lv["spread_edge"])
        assert pd.isna(den_lv["total_edge"])
        assert den_lv["spread_confidence_tier"] is None
        assert den_lv["total_confidence_tier"] is None

    def test_independent_tiers(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        """A game can have spread_tier='high' and total_tier='low' simultaneously."""
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        # SF@DAL: spread_edge=-8.5 (high), total_edge=4.0 (high)
        sf_dal = result[result["game_id"] == "2025_10_SF_DAL"].iloc[0]
        assert sf_dal["spread_confidence_tier"] == "high"
        assert sf_dal["total_confidence_tier"] == "high"

        # PHI@NYG: spread_edge = 2.5 - 7.0 = -4.5 (high), total_edge = 41.0 - 40.5 = 0.5 (low)
        phi_nyg = result[result["game_id"] == "2025_10_PHI_NYG"].iloc[0]
        assert phi_nyg["spread_confidence_tier"] == "high"
        assert phi_nyg["total_confidence_tier"] == "low"

    def test_output_schema(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        expected_cols = {
            "game_id",
            "season",
            "week",
            "home_team",
            "away_team",
            "model_spread",
            "model_total",
            "vegas_spread",
            "vegas_total",
            "spread_edge",
            "total_edge",
            "spread_confidence_tier",
            "total_confidence_tier",
            "prediction_timestamp",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_sort_by_max_edge(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        # Games with NaN edges (DEN@LV) should be last
        assert result.iloc[-1]["game_id"] == "2025_10_DEN_LV"

        # Remaining games sorted by max(abs(spread_edge), abs(total_edge)) desc
        # SF@DAL: max(8.5, 4.0) = 8.5
        # PHI@NYG: max(4.5, 0.5) = 4.5
        # KC@BUF: max(0.5, 4.0) = 4.0
        non_nan = result.iloc[:-1]
        assert non_nan.iloc[0]["game_id"] == "2025_10_SF_DAL"
        assert non_nan.iloc[1]["game_id"] == "2025_10_PHI_NYG"
        assert non_nan.iloc[2]["game_id"] == "2025_10_KC_BUF"

    def test_missing_model_error(self):
        """When model files don't exist, raises FileNotFoundError."""
        # This tests the CLI path — load_model raises FileNotFoundError
        # We verify that our script would surface this correctly by testing
        # that load_model itself raises for nonexistent paths
        from model_training import load_model

        with pytest.raises(FileNotFoundError):
            load_model("spread", model_dir="/nonexistent/path")
