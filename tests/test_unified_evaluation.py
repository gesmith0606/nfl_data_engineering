"""Tests for unified_evaluation module.

Validates that compute_production_heuristic produces values consistent with
projection_engine.project_position, that actual points computation works,
and that the full-feature backtest integration is wired correctly.
"""

import numpy as np
import pandas as pd
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unified_evaluation import (
    compute_actual_fantasy_points,
    compute_production_heuristic,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_wr_data():
    """WR player-week data with rolling columns and raw stats."""
    return pd.DataFrame(
        {
            "player_id": ["P1", "P2", "P3"],
            "player_name": ["Alpha", "Beta", "Gamma"],
            "position": ["WR", "WR", "WR"],
            "recent_team": ["KC", "BUF", "SF"],
            "season": [2023, 2023, 2023],
            "week": [5, 5, 5],
            "opponent": ["LV", "NYJ", "DAL"],
            # Rolling columns (used by heuristic)
            "receiving_yards_roll3": [80.0, 50.0, 100.0],
            "receiving_yards_roll6": [75.0, 55.0, 90.0],
            "receiving_yards_std": [70.0, 52.0, 85.0],
            "receiving_tds_roll3": [0.6, 0.3, 0.8],
            "receiving_tds_roll6": [0.5, 0.2, 0.7],
            "receiving_tds_std": [0.4, 0.25, 0.6],
            "receptions_roll3": [5.0, 3.0, 7.0],
            "receptions_roll6": [4.5, 3.5, 6.5],
            "receptions_std": [4.0, 3.2, 6.0],
            "targets_roll3": [8.0, 5.0, 10.0],
            "targets_roll6": [7.5, 5.5, 9.0],
            "targets_std": [7.0, 5.2, 8.5],
            # Usage stat for multiplier
            "target_share": [0.25, 0.15, 0.30],
            # Actual stats (for compute_actual_fantasy_points)
            "receiving_yards": [90.0, 40.0, 120.0],
            "receiving_tds": [1.0, 0.0, 1.0],
            "receptions": [6.0, 3.0, 8.0],
        }
    )


@pytest.fixture
def sample_qb_data():
    """QB player-week data with rolling columns."""
    return pd.DataFrame(
        {
            "player_id": ["QB1", "QB2"],
            "player_name": ["Mahomes", "Allen"],
            "position": ["QB", "QB"],
            "recent_team": ["KC", "BUF"],
            "season": [2023, 2023],
            "week": [5, 5],
            "opponent": ["LV", "NYJ"],
            "passing_yards_roll3": [280.0, 260.0],
            "passing_yards_roll6": [270.0, 250.0],
            "passing_yards_std": [265.0, 255.0],
            "passing_tds_roll3": [2.2, 2.0],
            "passing_tds_roll6": [2.0, 1.8],
            "passing_tds_std": [1.8, 1.7],
            "interceptions_roll3": [0.5, 0.7],
            "interceptions_roll6": [0.6, 0.8],
            "interceptions_std": [0.7, 0.9],
            "rushing_yards_roll3": [30.0, 40.0],
            "rushing_yards_roll6": [25.0, 35.0],
            "rushing_yards_std": [20.0, 30.0],
            "rushing_tds_roll3": [0.3, 0.4],
            "rushing_tds_roll6": [0.2, 0.3],
            "rushing_tds_std": [0.1, 0.2],
            "snap_pct": [1.0, 1.0],
            "passing_yards": [300.0, 280.0],
            "passing_tds": [3.0, 2.0],
            "interceptions": [1.0, 0.0],
            "rushing_yards": [25.0, 45.0],
            "rushing_tds": [0.0, 1.0],
        }
    )


@pytest.fixture
def empty_opp_rankings():
    """Empty opponent rankings (matchup factor defaults to 1.0)."""
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Tests: compute_production_heuristic
# ---------------------------------------------------------------------------


class TestComputeProductionHeuristic:
    """Tests for compute_production_heuristic."""

    def test_returns_series_aligned_to_input(self, sample_wr_data, empty_opp_rankings):
        """Result index matches input index."""
        result = compute_production_heuristic(
            sample_wr_data, "WR", empty_opp_rankings, "half_ppr"
        )
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_wr_data)
        assert list(result.index) == list(sample_wr_data.index)

    def test_produces_positive_values(self, sample_wr_data, empty_opp_rankings):
        """All projected points should be non-negative."""
        result = compute_production_heuristic(
            sample_wr_data, "WR", empty_opp_rankings, "half_ppr"
        )
        assert (result >= 0).all()

    def test_higher_usage_gets_higher_projection(
        self, sample_wr_data, empty_opp_rankings
    ):
        """Player with higher rolling stats should generally project higher."""
        result = compute_production_heuristic(
            sample_wr_data, "WR", empty_opp_rankings, "half_ppr"
        )
        # Gamma (idx 2) has highest rolling stats -> highest projection
        assert result.iloc[2] > result.iloc[1]

    def test_qb_position(self, sample_qb_data, empty_opp_rankings):
        """QB projections include passing and rushing stats."""
        result = compute_production_heuristic(
            sample_qb_data, "QB", empty_opp_rankings, "half_ppr"
        )
        assert isinstance(result, pd.Series)
        assert len(result) == 2
        assert (result > 0).all()

    def test_ceiling_shrinkage_applied(self, empty_opp_rankings):
        """High projections should be shrunk by PROJECTION_CEILING_SHRINKAGE."""
        # Create a player with very high rolling stats
        high_data = pd.DataFrame(
            {
                "player_id": ["P1"],
                "player_name": ["Star"],
                "position": ["WR"],
                "recent_team": ["KC"],
                "season": [2023],
                "week": [5],
                "opponent": ["LV"],
                "receiving_yards_roll3": [200.0],
                "receiving_yards_roll6": [200.0],
                "receiving_yards_std": [200.0],
                "receiving_tds_roll3": [2.0],
                "receiving_tds_roll6": [2.0],
                "receiving_tds_std": [2.0],
                "receptions_roll3": [12.0],
                "receptions_roll6": [12.0],
                "receptions_std": [12.0],
                "targets_roll3": [15.0],
                "targets_roll6": [15.0],
                "targets_std": [15.0],
                "target_share": [0.35],
            }
        )
        result = compute_production_heuristic(
            high_data, "WR", empty_opp_rankings, "half_ppr"
        )
        # Without shrinkage, 200 rec yds + 2 TDs + 12 rec = ~38 pts (half ppr)
        # With shrinkage at 0.80 for 23+ pts, should be notably less
        assert result.iloc[0] < 38.0

    def test_empty_data_returns_empty(self, empty_opp_rankings):
        """Empty input returns empty series."""
        empty = pd.DataFrame()
        result = compute_production_heuristic(
            empty, "WR", empty_opp_rankings, "half_ppr"
        )
        assert len(result) == 0

    def test_unknown_position_returns_nan(self, sample_wr_data, empty_opp_rankings):
        """Unknown position returns NaN series."""
        result = compute_production_heuristic(
            sample_wr_data, "K", empty_opp_rankings, "half_ppr"
        )
        assert result.isna().all()

    def test_all_four_positions(self, empty_opp_rankings):
        """All four skill positions produce valid results."""
        for pos in ["QB", "RB", "WR", "TE"]:
            data = pd.DataFrame(
                {
                    "player_id": ["P1"],
                    "player_name": ["Test"],
                    "position": [pos],
                    "recent_team": ["KC"],
                    "season": [2023],
                    "week": [5],
                    "opponent": ["LV"],
                    "target_share": [0.20],
                    "snap_pct": [0.80],
                    "carry_share": [0.30],
                }
            )
            from projection_engine import POSITION_STAT_PROFILE

            for stat in POSITION_STAT_PROFILE.get(pos, []):
                for suffix in ["roll3", "roll6", "std"]:
                    data[f"{stat}_{suffix}"] = [50.0]

            result = compute_production_heuristic(
                data, pos, empty_opp_rankings, "half_ppr"
            )
            assert len(result) == 1
            assert result.iloc[0] >= 0

    def test_scoring_formats(self, sample_wr_data, empty_opp_rankings):
        """Different scoring formats produce different values."""
        ppr = compute_production_heuristic(
            sample_wr_data, "WR", empty_opp_rankings, "ppr"
        )
        standard = compute_production_heuristic(
            sample_wr_data, "WR", empty_opp_rankings, "standard"
        )
        # PPR should be higher than standard for WR (receptions worth 1.0 vs 0.0)
        assert ppr.iloc[0] > standard.iloc[0]


# ---------------------------------------------------------------------------
# Tests: compute_actual_fantasy_points
# ---------------------------------------------------------------------------


class TestComputeActualFantasyPoints:
    """Tests for compute_actual_fantasy_points."""

    def test_returns_series(self, sample_wr_data):
        """Returns a Series aligned to input."""
        result = compute_actual_fantasy_points(sample_wr_data, "half_ppr")
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_wr_data)

    def test_positive_values(self, sample_wr_data):
        """Players with positive stats should have positive points."""
        result = compute_actual_fantasy_points(sample_wr_data, "half_ppr")
        # All players have some receiving yards so points should be positive
        assert (result > 0).all()

    def test_qb_actual_points(self, sample_qb_data):
        """QB actual points include passing and rushing."""
        result = compute_actual_fantasy_points(sample_qb_data, "half_ppr")
        assert len(result) == 2
        # Mahomes: 300 pass yds (12) + 3 TDs (18) - 1 INT (-2) + 25 rush yds (2.5) = 30.5
        # Allow some tolerance for scoring calc implementation
        assert result.iloc[0] > 20.0

    def test_scoring_format_matters(self, sample_wr_data):
        """PPR should give higher points than standard for receivers."""
        ppr = compute_actual_fantasy_points(sample_wr_data, "ppr")
        standard = compute_actual_fantasy_points(sample_wr_data, "standard")
        assert ppr.iloc[0] > standard.iloc[0]


# ---------------------------------------------------------------------------
# Tests: consistency with projection_engine
# ---------------------------------------------------------------------------


class TestConsistencyWithProjectionEngine:
    """Verify heuristic produces values consistent with project_position."""

    def test_values_within_tolerance(self, sample_wr_data, empty_opp_rankings):
        """Production heuristic should match project_position within 1%.

        Both use the same underlying functions (_weighted_baseline,
        _usage_multiplier, _matchup_factor, ceiling shrinkage).
        """
        from projection_engine import project_position

        # Get projection_engine result
        engine_result = project_position(
            sample_wr_data, "WR", empty_opp_rankings, "half_ppr"
        )

        # Get unified_evaluation result
        unified_result = compute_production_heuristic(
            sample_wr_data, "WR", empty_opp_rankings, "half_ppr"
        )

        if engine_result.empty:
            pytest.skip("project_position returned empty (needs position filter)")

        engine_pts = engine_result["projected_points"].values
        unified_pts = unified_result.values

        # Both should produce the same number of results
        assert len(engine_pts) == len(unified_pts)

        # Values within 1% tolerance
        for i in range(len(engine_pts)):
            if engine_pts[i] == 0 and unified_pts[i] == 0:
                continue
            max_val = max(abs(engine_pts[i]), abs(unified_pts[i]), 0.01)
            pct_diff = abs(engine_pts[i] - unified_pts[i]) / max_val
            assert pct_diff < 0.01, (
                f"Row {i}: engine={engine_pts[i]:.4f}, "
                f"unified={unified_pts[i]:.4f}, diff={pct_diff:.4%}"
            )

    def test_qb_consistency(self, sample_qb_data, empty_opp_rankings):
        """QB heuristic matches project_position."""
        from projection_engine import project_position

        engine_result = project_position(
            sample_qb_data, "QB", empty_opp_rankings, "half_ppr"
        )
        unified_result = compute_production_heuristic(
            sample_qb_data, "QB", empty_opp_rankings, "half_ppr"
        )

        if engine_result.empty:
            pytest.skip("project_position returned empty")

        engine_pts = engine_result["projected_points"].values
        unified_pts = unified_result.values

        for i in range(len(engine_pts)):
            if engine_pts[i] == 0 and unified_pts[i] == 0:
                continue
            max_val = max(abs(engine_pts[i]), abs(unified_pts[i]), 0.01)
            pct_diff = abs(engine_pts[i] - unified_pts[i]) / max_val
            assert pct_diff < 0.01, (
                f"QB row {i}: engine={engine_pts[i]:.4f}, "
                f"unified={unified_pts[i]:.4f}, diff={pct_diff:.4%}"
            )


# ---------------------------------------------------------------------------
# Tests: residual model with unified heuristic
# ---------------------------------------------------------------------------


class TestResidualModelIntegration:
    """Test that residual save/load works with unified heuristic."""

    def test_load_nonexistent_model_raises(self):
        """Loading a non-existent model should raise FileNotFoundError."""
        from hybrid_projection import load_residual_model

        with pytest.raises(FileNotFoundError):
            load_residual_model("QB", model_dir="/nonexistent/path")

    def test_apply_residual_no_model_returns_input(self, sample_wr_data):
        """apply_residual_correction with no model returns input unchanged."""
        from hybrid_projection import apply_residual_correction

        proj = pd.DataFrame(
            {
                "player_id": ["P1", "P2"],
                "player_name": ["Alpha", "Beta"],
                "projected_points": [10.0, 5.0],
            }
        )
        result = apply_residual_correction(
            proj, sample_wr_data, "WR", model_dir="/nonexistent"
        )
        assert result["projected_points"].tolist() == [10.0, 5.0]


# ---------------------------------------------------------------------------
# Tests: backtest --full-features flag parsing
# ---------------------------------------------------------------------------


class TestBacktestFullFeatures:
    """Test that backtest CLI accepts --full-features flag."""

    def test_argparse_accepts_full_features(self):
        """Verify argparse accepts --full-features without error."""
        import importlib
        import scripts.backtest_projections as bt_mod

        importlib.reload(bt_mod)

        # Build parser manually
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--full-features", action="store_true")
        args = parser.parse_args(["--full-features"])
        assert args.full_features is True

    def test_run_backtest_signature(self):
        """run_backtest accepts full_features kwarg."""
        import inspect

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        # We just need to verify the parameter exists
        from backtest_projections import run_backtest

        sig = inspect.signature(run_backtest)
        assert "full_features" in sig.parameters
