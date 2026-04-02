"""Tests for team-level fantasy projection constraints.

Validates that ``_compute_team_fantasy_budget()`` and
``apply_team_constraints()`` correctly normalise player projections
to align with implied team totals.
"""

import sys
import os

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from projection_engine import (  # noqa: E402
    _IMPLIED_TO_FANTASY_MULT,
    _compute_team_fantasy_budget,
    apply_team_constraints,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_projections(
    teams: dict,
    add_bye: bool = False,
    add_injury: bool = False,
    add_floor_ceil: bool = False,
) -> pd.DataFrame:
    """Build a minimal projections DataFrame.

    Args:
        teams: Dict of {team: [(player_name, position, projected_points), ...]}.
        add_bye: If True, add ``is_bye_week`` column (all False by default).
        add_injury: If True, add ``injury_status`` column (all 'Active').
        add_floor_ceil: If True, add ``projected_floor`` and ``projected_ceiling``.
    """
    rows = []
    for team, players in teams.items():
        for name, pos, pts in players:
            row = {
                "player_name": name,
                "position": pos,
                "recent_team": team,
                "projected_points": pts,
                "proj_rushing_yards": pts * 3.0,  # dummy stat proportional to pts
                "proj_receiving_yards": pts * 2.0,
            }
            if add_bye:
                row["is_bye_week"] = False
            if add_injury:
                row["injury_status"] = "Active"
            if add_floor_ceil:
                row["projected_floor"] = round(pts * 0.6, 2)
                row["projected_ceiling"] = round(pts * 1.4, 2)
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: _compute_team_fantasy_budget
# ---------------------------------------------------------------------------


class TestComputeTeamFantasyBudget:
    """Tests for ``_compute_team_fantasy_budget``."""

    def test_all_formats(self) -> None:
        """Budget should use the correct multiplier for each scoring format."""
        implied = 24.0
        for fmt, mult in _IMPLIED_TO_FANTASY_MULT.items():
            result = _compute_team_fantasy_budget(implied, fmt)
            expected = round(implied * mult, 2)
            assert result == expected, f"{fmt}: {result} != {expected}"

    def test_unknown_format_falls_back_to_half_ppr(self) -> None:
        """Unknown scoring format should default to half_ppr multiplier."""
        result = _compute_team_fantasy_budget(24.0, "unknown_format")
        expected = round(24.0 * _IMPLIED_TO_FANTASY_MULT["half_ppr"], 2)
        assert result == expected


# ---------------------------------------------------------------------------
# Tests: apply_team_constraints
# ---------------------------------------------------------------------------


class TestApplyTeamConstraints:
    """Tests for ``apply_team_constraints``."""

    def test_scales_down_overproduction(self) -> None:
        """When team sum exceeds budget by >10%, projections should scale down."""
        # Budget for KC at implied=20: 20 * 3.36 = 67.2
        # Team sum = 100, ratio = 67.2/100 = 0.672, outside dead zone
        # scale = 1.0 + 0.6 * (0.672 - 1.0) = 1.0 - 0.1968 = 0.8032
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 30.0),
                    ("RB1", "RB", 25.0),
                    ("WR1", "WR", 25.0),
                    ("TE1", "TE", 20.0),
                ]
            }
        )
        implied = {"KC": 20.0}
        result = apply_team_constraints(df, implied, "half_ppr")

        # All points should be reduced
        for _, row in result.iterrows():
            orig = df.loc[
                df["player_name"] == row["player_name"], "projected_points"
            ].iloc[0]
            assert row["projected_points"] < orig

    def test_scales_up_underproduction(self) -> None:
        """When team sum is far below budget, projections should scale up."""
        # Budget for KC at implied=30: 30 * 3.36 = 100.8
        # Team sum = 50, ratio = 100.8/50 = 2.016
        # scale = 1.0 + 0.6 * (2.016 - 1.0) = 1.0 + 0.6096 = 1.6096
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 20.0),
                    ("RB1", "RB", 15.0),
                    ("WR1", "WR", 10.0),
                    ("TE1", "TE", 5.0),
                ]
            }
        )
        implied = {"KC": 30.0}
        result = apply_team_constraints(df, implied, "half_ppr")

        for _, row in result.iterrows():
            orig = df.loc[
                df["player_name"] == row["player_name"], "projected_points"
            ].iloc[0]
            assert row["projected_points"] > orig

    def test_dead_zone_no_change(self) -> None:
        """When team sum is within +-10% of budget, no adjustment should occur."""
        # Budget for KC at implied=24: 24 * 3.36 = 80.64
        # Team sum = 80 (ratio ~1.008), within 10% dead zone
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 25.0),
                    ("RB1", "RB", 20.0),
                    ("WR1", "WR", 20.0),
                    ("TE1", "TE", 15.0),
                ]
            }
        )
        implied = {"KC": 24.0}
        result = apply_team_constraints(df, implied, "half_ppr")

        pd.testing.assert_series_equal(
            result["projected_points"],
            df["projected_points"],
            check_names=False,
        )

    def test_preserves_relative_shares(self) -> None:
        """Player shares within a team should remain proportional after scaling."""
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 30.0),
                    ("RB1", "RB", 20.0),
                    ("WR1", "WR", 10.0),
                ]
            }
        )
        implied = {"KC": 10.0}  # Force a big scale-down
        result = apply_team_constraints(df, implied, "half_ppr")

        pts = result["projected_points"].values
        # QB1 should still have the highest, WR1 the lowest
        assert pts[0] > pts[1] > pts[2]
        # Ratios should be preserved
        orig_ratio = 30.0 / 20.0
        new_ratio = pts[0] / pts[1]
        assert abs(orig_ratio - new_ratio) < 0.01

    def test_skips_bye_week_players(self) -> None:
        """Players on bye should not be included in team sum or scaled."""
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 20.0),
                    ("RB1", "RB", 15.0),
                ]
            },
            add_bye=True,
        )
        # Put QB1 on bye
        df.loc[df["player_name"] == "QB1", "is_bye_week"] = True
        df.loc[df["player_name"] == "QB1", "projected_points"] = 0.0

        implied = {"KC": 10.0}  # Force scale-down based on RB1's 15 pts
        result = apply_team_constraints(df, implied, "half_ppr")

        # Bye player should remain at 0
        bye_pts = result.loc[result["player_name"] == "QB1", "projected_points"].iloc[0]
        assert bye_pts == 0.0

    def test_skips_injured_out_players(self) -> None:
        """Players with Out/IR status should not be scaled."""
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 20.0),
                    ("RB1", "RB", 15.0),
                ]
            },
            add_injury=True,
        )
        df.loc[df["player_name"] == "QB1", "injury_status"] = "Out"
        df.loc[df["player_name"] == "QB1", "projected_points"] = 0.0

        implied = {"KC": 10.0}
        result = apply_team_constraints(df, implied, "half_ppr")

        # Out player should remain at 0
        out_pts = result.loc[result["player_name"] == "QB1", "projected_points"].iloc[0]
        assert out_pts == 0.0

    def test_no_implied_totals_noop(self) -> None:
        """When implied_totals is None, projections should be unchanged."""
        df = _make_projections({"KC": [("QB1", "QB", 20.0)]})
        result = apply_team_constraints(df, None, "half_ppr")
        assert result["projected_points"].iloc[0] == 20.0
        assert result["team_constraint_factor"].iloc[0] == 1.0

    def test_empty_implied_totals_noop(self) -> None:
        """When implied_totals is empty dict, projections should be unchanged."""
        df = _make_projections({"KC": [("QB1", "QB", 20.0)]})
        result = apply_team_constraints(df, {}, "half_ppr")
        assert result["projected_points"].iloc[0] == 20.0

    def test_missing_team_in_implied(self) -> None:
        """Teams not in implied_totals should be left unchanged."""
        df = _make_projections(
            {
                "KC": [("QB1", "QB", 20.0)],
                "SF": [("QB2", "QB", 18.0)],
            }
        )
        implied = {"KC": 10.0}  # Only KC has implied
        result = apply_team_constraints(df, implied, "half_ppr")

        sf_pts = result.loc[result["recent_team"] == "SF", "projected_points"].iloc[0]
        assert sf_pts == 18.0

    def test_projected_points_floor_zero(self) -> None:
        """Projected points should never go below 0.0 after scaling."""
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 0.5),
                    ("RB1", "RB", 0.3),
                ]
            }
        )
        # Very low implied forces heavy scale-down, but floor is 0
        implied = {"KC": 0.01}
        result = apply_team_constraints(df, implied, "half_ppr")

        assert (result["projected_points"] >= 0.0).all()

    def test_column_added(self) -> None:
        """``team_constraint_factor`` column should always be present."""
        df = _make_projections({"KC": [("QB1", "QB", 20.0)]})

        # With implied totals
        result = apply_team_constraints(df, {"KC": 10.0}, "half_ppr")
        assert "team_constraint_factor" in result.columns

        # Without implied totals
        result2 = apply_team_constraints(df, None, "half_ppr")
        assert "team_constraint_factor" in result2.columns

    def test_floor_ceiling_recalculated(self) -> None:
        """Floor and ceiling should be recalculated after constraint scaling."""
        df = _make_projections(
            {
                "KC": [
                    ("QB1", "QB", 30.0),
                    ("RB1", "RB", 25.0),
                    ("WR1", "WR", 25.0),
                    ("TE1", "TE", 20.0),
                ]
            },
            add_floor_ceil=True,
        )
        implied = {"KC": 10.0}  # Force scale-down
        result = apply_team_constraints(df, implied, "half_ppr")

        # Floor and ceiling should match new projected_points, not original
        for _, row in result.iterrows():
            pts = row["projected_points"]
            if pts > 0:
                # Floor should be less than points
                assert row["projected_floor"] < pts
                # Ceiling should be greater than points
                assert row["projected_ceiling"] > pts
                # Floor should not equal original
                orig = df.loc[
                    df["player_name"] == row["player_name"], "projected_floor"
                ].iloc[0]
                assert row["projected_floor"] != orig
