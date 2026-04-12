"""Contract test: all heuristic computation paths produce identical results.

This test prevents the class of bugs that caused the v4.1 QB residual bias
(+14 pts) where training, WFCV, and production heuristics diverged silently
because three separate implementations existed:

1. generate_weekly_projections() in projection_engine — production
2. generate_heuristic_predictions() in player_model_training — WFCV
3. compute_production_heuristic() in unified_evaluation — residual training

All three now delegate to the single canonical function
``projection_engine.compute_heuristic_baseline``, which this test verifies.
"""

import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from projection_engine import (
    POSITION_STAT_PROFILE,
    PROJECTION_CEILING_SHRINKAGE,
    compute_heuristic_baseline,
    _usage_multiplier,
    _weighted_baseline,
)
from unified_evaluation import compute_production_heuristic
from player_model_training import generate_heuristic_predictions


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_wr_data(n: int = 5) -> pd.DataFrame:
    """Minimal WR player-week fixture with rolling columns and usage stats."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "player_id": [f"P{i}" for i in range(n)],
            "player_name": [f"Player {i}" for i in range(n)],
            "position": ["WR"] * n,
            "recent_team": ["KC", "BUF", "SF", "DAL", "MIA"],
            "season": [2023] * n,
            "week": [8] * n,
            "opponent": ["LV", "NYJ", "PHI", "NYG", "NE"],
            # Rolling columns
            "receiving_yards_roll3": rng.uniform(40, 120, n),
            "receiving_yards_roll6": rng.uniform(35, 110, n),
            "receiving_yards_std": rng.uniform(30, 100, n),
            "receiving_tds_roll3": rng.uniform(0.1, 0.9, n),
            "receiving_tds_roll6": rng.uniform(0.1, 0.8, n),
            "receiving_tds_std": rng.uniform(0.1, 0.7, n),
            "receptions_roll3": rng.uniform(2, 8, n),
            "receptions_roll6": rng.uniform(2, 7, n),
            "receptions_std": rng.uniform(2, 6, n),
            "targets_roll3": rng.uniform(4, 12, n),
            "targets_roll6": rng.uniform(3, 11, n),
            "targets_std": rng.uniform(3, 10, n),
            # Usage stat for _usage_multiplier
            "target_share": rng.uniform(0.10, 0.35, n),
        }
    )


def _make_qb_data(n: int = 4) -> pd.DataFrame:
    """Minimal QB player-week fixture — exercises the snap_pct all-NaN guard."""
    rng = np.random.default_rng(7)
    df = pd.DataFrame(
        {
            "player_id": [f"QB{i}" for i in range(n)],
            "player_name": [f"QB {i}" for i in range(n)],
            "position": ["QB"] * n,
            "recent_team": ["KC", "BUF", "LAR", "SF"],
            "season": [2023] * n,
            "week": [5] * n,
            "opponent": ["LV", "NYJ", "SEA", "PHI"],
            "passing_yards_roll3": rng.uniform(220, 320, n),
            "passing_yards_roll6": rng.uniform(210, 300, n),
            "passing_yards_std": rng.uniform(200, 290, n),
            "passing_tds_roll3": rng.uniform(1.5, 3.0, n),
            "passing_tds_roll6": rng.uniform(1.4, 2.8, n),
            "passing_tds_std": rng.uniform(1.2, 2.5, n),
            "interceptions_roll3": rng.uniform(0.3, 1.0, n),
            "interceptions_roll6": rng.uniform(0.3, 0.9, n),
            "interceptions_std": rng.uniform(0.3, 0.9, n),
            "rushing_yards_roll3": rng.uniform(5, 40, n),
            "rushing_yards_roll6": rng.uniform(5, 35, n),
            "rushing_yards_std": rng.uniform(5, 30, n),
            "rushing_tds_roll3": rng.uniform(0.0, 0.5, n),
            "rushing_tds_roll6": rng.uniform(0.0, 0.4, n),
            "rushing_tds_std": rng.uniform(0.0, 0.4, n),
            # snap_pct intentionally all-NaN to exercise the QB NaN guard
            "snap_pct": [np.nan] * n,
        }
    )
    return df


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


class TestAllHeuristicPathsAgree:
    """compute_heuristic_baseline, compute_production_heuristic, and
    generate_heuristic_predictions must all produce numerically identical
    fantasy-point totals for the same player-week input (within float tolerance).
    """

    def test_wr_paths_agree_no_opp_rankings(self):
        """WR: all three paths agree when no opponent rankings are provided."""
        data = _make_wr_data()
        empty_opp = pd.DataFrame()

        canonical = compute_heuristic_baseline(data, "WR", empty_opp)
        production = compute_production_heuristic(data, "WR", empty_opp)
        heur_df = generate_heuristic_predictions(data, "WR")
        from_wrapper = heur_df["heuristic_pts"]

        np.testing.assert_allclose(
            canonical.reset_index(drop=True).values,
            production.reset_index(drop=True).values,
            rtol=1e-5,
            err_msg="compute_heuristic_baseline vs compute_production_heuristic diverge for WR",
        )
        np.testing.assert_allclose(
            canonical.reset_index(drop=True).values,
            from_wrapper.reset_index(drop=True).values,
            rtol=1e-5,
            err_msg="compute_heuristic_baseline vs generate_heuristic_predictions diverge for WR",
        )

    def test_qb_paths_agree_no_opp_rankings(self):
        """QB: all three paths agree even when snap_pct is entirely NaN."""
        data = _make_qb_data()
        empty_opp = pd.DataFrame()

        canonical = compute_heuristic_baseline(data, "QB", empty_opp)
        production = compute_production_heuristic(data, "QB", empty_opp)
        heur_df = generate_heuristic_predictions(data, "QB")
        from_wrapper = heur_df["heuristic_pts"]

        np.testing.assert_allclose(
            canonical.reset_index(drop=True).values,
            production.reset_index(drop=True).values,
            rtol=1e-5,
            err_msg="compute_heuristic_baseline vs compute_production_heuristic diverge for QB",
        )
        np.testing.assert_allclose(
            canonical.reset_index(drop=True).values,
            from_wrapper.reset_index(drop=True).values,
            rtol=1e-5,
            err_msg="compute_heuristic_baseline vs generate_heuristic_predictions diverge for QB",
        )

    def test_paths_agree_with_opp_rankings(self):
        """When opponent rankings are supplied, canonical and production still agree."""
        data = _make_wr_data()
        opp_rankings = pd.DataFrame(
            {
                "team": ["LV", "NYJ", "PHI", "NYG", "NE"],
                "week": [8, 8, 8, 8, 8],
                "season": [2023, 2023, 2023, 2023, 2023],
                "position": ["WR"] * 5,
                "rank": [5, 12, 20, 28, 16],
            }
        )

        canonical = compute_heuristic_baseline(data, "WR", opp_rankings)
        production = compute_production_heuristic(data, "WR", opp_rankings)

        np.testing.assert_allclose(
            canonical.reset_index(drop=True).values,
            production.reset_index(drop=True).values,
            rtol=1e-5,
            err_msg="canonical vs production diverge when opp_rankings are supplied",
        )

    @pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE"])
    def test_all_positions_nonnegative(self, position: str):
        """Heuristic fantasy points must never be negative for any position."""
        rng = np.random.default_rng(99)
        n = 6
        base = {
            "player_id": [f"P{i}" for i in range(n)],
            "position": [position] * n,
            "recent_team": ["KC"] * n,
            "season": [2023] * n,
            "week": [5] * n,
            "opponent": ["LV"] * n,
            "target_share": rng.uniform(0.05, 0.35, n),
            "carry_share": rng.uniform(0.05, 0.35, n),
            "snap_pct": rng.uniform(0.3, 1.0, n),
        }
        for stat in POSITION_STAT_PROFILE.get(position, []):
            for suffix in ("roll3", "roll6", "std"):
                base[f"{stat}_{suffix}"] = rng.uniform(0, 50, n)

        df = pd.DataFrame(base)
        pts = compute_heuristic_baseline(df, position, pd.DataFrame())
        assert (pts >= 0).all(), f"Negative projections for {position}: {pts.values}"

    def test_ceiling_shrinkage_applied(self):
        """Values above threshold must be shrunk — verifying shrinkage is included."""
        # Build a WR row whose rolling average will project well above 23 pts
        data = pd.DataFrame(
            {
                "player_id": ["P1"],
                "position": ["WR"],
                "recent_team": ["KC"],
                "season": [2023],
                "week": [5],
                "opponent": ["LV"],
                "receiving_yards_roll3": [200.0],
                "receiving_yards_roll6": [190.0],
                "receiving_yards_std": [180.0],
                "receiving_tds_roll3": [2.0],
                "receiving_tds_roll6": [1.8],
                "receiving_tds_std": [1.6],
                "receptions_roll3": [12.0],
                "receptions_roll6": [11.0],
                "receptions_std": [10.0],
                "targets_roll3": [15.0],
                "targets_roll6": [14.0],
                "targets_std": [13.0],
                "target_share": [0.40],
            }
        )
        pts = compute_heuristic_baseline(data, "WR", pd.DataFrame())
        # Without shrinkage the raw points would be much higher; confirm the
        # max shrinkage factor (0.80) is applied to anything above 23 pts.
        assert pts.iloc[0] > 0
        # The shrinkage factor at 23 pts is 0.80 — raw projection is high
        # enough that shrinkage must reduce it below the unshrunk value.
        from scoring_calculator import calculate_fantasy_points_df

        unshrunk_input = data[
            ["receiving_yards_roll3", "receiving_tds_roll3", "receptions_roll3", "targets_roll3"]
        ].rename(
            columns={
                "receiving_yards_roll3": "receiving_yards",
                "receiving_tds_roll3": "receiving_tds",
                "receptions_roll3": "receptions",
                "targets_roll3": "targets",
            }
        )
        raw_pts = calculate_fantasy_points_df(
            unshrunk_input.copy(), scoring_format="half_ppr", output_col="pts"
        )["pts"].iloc[0]
        assert pts.iloc[0] < raw_pts, (
            f"Ceiling shrinkage not applied: shrunk={pts.iloc[0]:.2f}, "
            f"raw={raw_pts:.2f}"
        )


# ---------------------------------------------------------------------------
# Regression tests for Phase v4.1-p3 bugs
# ---------------------------------------------------------------------------


class TestUsageMultiplierEdgeCases:
    """Regression tests for the QB NaN bug and column-missing path."""

    def test_usage_multiplier_handles_all_nan(self):
        """When snap_pct is entirely NaN, _usage_multiplier must return 1.0.

        Regression test for Phase v4.1-p3 QB residual bias: all-NaN snap_pct
        used to propagate NaN through median() → fillna() no-op → NaN in
        every projection → residual model learned residual=actual (+14 pts bias).
        """
        df = pd.DataFrame(
            {
                "snap_pct": [np.nan, np.nan, np.nan],
                "other_col": [1.0, 2.0, 3.0],
            }
        )
        result = _usage_multiplier(df, "QB")
        assert (result == 1.0).all(), (
            f"Expected all 1.0 for all-NaN snap_pct, got {result.values}"
        )

    def test_usage_multiplier_missing_column(self):
        """When the usage column is absent entirely, returns neutral 1.0."""
        df = pd.DataFrame({"other_col": [1.0, 2.0, 3.0]})
        result = _usage_multiplier(df, "QB")
        assert (result == 1.0).all(), (
            f"Expected all 1.0 for missing snap_pct column, got {result.values}"
        )

    def test_usage_multiplier_partial_nan_fills_with_median(self):
        """Partial NaN in usage column: NaN rows filled with median, no NaN output."""
        df = pd.DataFrame({"target_share": [0.10, np.nan, 0.30, np.nan, 0.20]})
        result = _usage_multiplier(df, "WR")
        assert result.notna().all(), f"NaN in usage multiplier output: {result.values}"
        assert (result >= 0.80).all() and (result <= 1.15).all(), (
            f"Multiplier out of [0.80, 1.15] range: {result.values}"
        )

    def test_compute_heuristic_baseline_qb_all_nan_snap_pct(self):
        """compute_heuristic_baseline must return finite values for QB with all-NaN snap_pct.

        End-to-end regression for the QB NaN bug: if the fix in _usage_multiplier
        were ever reverted, this test would catch it before residual training.
        """
        data = _make_qb_data()  # all snap_pct = NaN
        pts = compute_heuristic_baseline(data, "QB", pd.DataFrame())
        assert pts.notna().all(), (
            f"NaN projections for QB with all-NaN snap_pct: {pts.values}"
        )
        assert (pts > 0).all(), (
            f"Zero/negative projections for QB with all-NaN snap_pct: {pts.values}"
        )

    def test_weighted_baseline_all_missing_columns(self):
        """_weighted_baseline returns 0.0 Series when no rolling columns exist."""
        df = pd.DataFrame({"player_id": ["P1", "P2"], "other": [1.0, 2.0]})
        result = _weighted_baseline(df, "passing_yards")
        assert (result == 0.0).all(), f"Expected 0.0 for missing columns: {result.values}"
