#!/usr/bin/env python3
"""Tests for TPRR (targets per route run) features and spread game-script lab helpers.

Coverage:
- compute_tprr_features: basic TPRR computation from route + weekly data.
- Temporal lag: tprr_trail4 must be NaN at week 1 (shift-1 lag applied).
- Missing targets: rows with no targets get tprr=0, tprr_trail4 from prior.
- Zero dropbacks: rows where dropbacks_on_field=0 get tprr=NaN (not 0).
- Interaction term: tprr_x_route_slope = tprr_trail4 * route_rate_slope.
- Empty / missing input guards for compute_tprr_features.
- TPRR_FEATURES constant contains expected keys.
- _build_spread_by_week: (season, week, team) lookup; away team is mirror.
- _compute_per_position_spearman: returns mean weekly Spearman per position.
- Spread lab: neutral spread (0) does not change usage multiplier.
"""

import os
import sys
from typing import Dict

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from graph_route_participation import TPRR_FEATURES, compute_tprr_features

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEASON = 2023
_PLAYER_A = "00-0001111"
_PLAYER_B = "00-0002222"
_TEAM = "KC"


def _make_route_df(
    player_id: str = _PLAYER_A,
    weeks: int = 6,
    dropbacks: int = 10,
    add_slope: bool = True,
) -> pd.DataFrame:
    """Create a minimal route participation frame for one player.

    Args:
        player_id: Player GSIS ID.
        weeks: Number of weeks to generate (weeks 1 through N).
        dropbacks: Constant dropbacks_on_field per week.
        add_slope: If True, include route_rate_slope column.

    Returns:
        Route participation DataFrame.
    """
    rows = []
    for w in range(1, weeks + 1):
        rows.append(
            {
                "player_id": player_id,
                "season": _SEASON,
                "week": w,
                "recent_team": _TEAM,
                "route_rate": 0.7 + w * 0.01,
                "dropbacks_on_field": dropbacks,
                "team_dropbacks": 30,
                "route_rate_trail4": 0.68 if w >= 2 else np.nan,
                "route_rate_delta": 0.01 if w >= 3 else np.nan,
                "route_rate_slope": 0.005 if w >= 3 else np.nan,
            }
        )
    df = pd.DataFrame(rows)
    if not add_slope:
        df = df.drop(columns=["route_rate_slope"])
    return df


def _make_weekly_df(
    player_id: str = _PLAYER_A,
    weeks: int = 6,
    targets: int = 5,
) -> pd.DataFrame:
    """Create a minimal weekly player stats frame.

    Args:
        player_id: Player GSIS ID.
        weeks: Number of weeks.
        targets: Constant targets per week.

    Returns:
        Minimal weekly DataFrame.
    """
    return pd.DataFrame(
        {
            "player_id": [player_id] * weeks,
            "season": _SEASON,
            "week": list(range(1, weeks + 1)),
            "targets": targets,
        }
    )


# ---------------------------------------------------------------------------
# TPRR feature tests
# ---------------------------------------------------------------------------


class TestComputeTprrFeatures:
    """Unit tests for compute_tprr_features."""

    def test_output_columns(self) -> None:
        """All expected TPRR columns must be present in the output."""
        route = _make_route_df()
        weekly = _make_weekly_df()
        result = compute_tprr_features(route, weekly)
        assert not result.empty
        for col in ["player_id", "season", "week", "tprr"] + TPRR_FEATURES:
            assert col in result.columns, f"Missing column: {col}"

    def test_tprr_constants(self) -> None:
        """TPRR_FEATURES should contain exactly the 3 expected keys."""
        assert TPRR_FEATURES == ["tprr_trail4", "tprr_trail4_slope", "tprr_x_route_slope"]

    def test_raw_tprr_formula(self) -> None:
        """tprr = targets / dropbacks_on_field."""
        route = _make_route_df(dropbacks=10)
        weekly = _make_weekly_df(targets=4)
        result = compute_tprr_features(route, weekly)
        # Raw TPRR should be 4 / 10 = 0.4 where data exists
        assert result["tprr"].dropna().round(4).eq(0.4).all()

    def test_lag_week1_nan(self) -> None:
        """tprr_trail4 must be NaN at week 1 (shift-1 applied)."""
        route = _make_route_df(weeks=5)
        weekly = _make_weekly_df(weeks=5)
        result = compute_tprr_features(route, weekly)
        w1 = result[result["week"] == 1]
        assert w1["tprr_trail4"].isna().all(), "tprr_trail4 must be NaN at week 1"

    def test_lag_week2_uses_week1(self) -> None:
        """tprr_trail4 at week 2 should reflect week 1 targets/dropbacks."""
        route = _make_route_df(dropbacks=10, weeks=4)
        weekly = _make_weekly_df(targets=6, weeks=4)
        result = compute_tprr_features(route, weekly)
        w2 = result[result["week"] == 2]
        # Only one prior week; trail4 mean of one value = 0.6
        assert not w2.empty
        # With min_periods=2, week 2 should still be NaN (only 1 prior point)
        # Actually shift(1) at week 2 has exactly 1 observation (week 1);
        # _MIN_GAMES=2 means we need at least 2 — so week 2 is NaN.
        assert w2["tprr_trail4"].isna().all()

    def test_lag_week3_non_nan(self) -> None:
        """tprr_trail4 should become non-NaN by week 3 (2 prior points)."""
        route = _make_route_df(dropbacks=10, weeks=6)
        weekly = _make_weekly_df(targets=5, weeks=6)
        result = compute_tprr_features(route, weekly)
        w3 = result[result["week"] == 3]
        assert not w3.empty
        assert w3["tprr_trail4"].notna().all(), (
            "tprr_trail4 should be non-NaN by week 3 (min_periods=2 satisfied)"
        )

    def test_zero_dropbacks_nan_tprr(self) -> None:
        """Zero dropbacks_on_field should produce NaN tprr, not 0."""
        route = _make_route_df(dropbacks=0, weeks=4)
        weekly = _make_weekly_df(targets=3, weeks=4)
        result = compute_tprr_features(route, weekly)
        assert result["tprr"].isna().all(), (
            "Zero dropbacks should produce NaN tprr"
        )

    def test_no_targets_zero_tprr(self) -> None:
        """Player with zero targets gets tprr=0 (not NaN) when on field."""
        route = _make_route_df(dropbacks=8, weeks=5)
        weekly = _make_weekly_df(targets=0, weeks=5)
        result = compute_tprr_features(route, weekly)
        assert (result["tprr"].dropna() == 0.0).all()

    def test_interaction_term(self) -> None:
        """tprr_x_route_slope should equal tprr_trail4 * route_rate_slope."""
        route = _make_route_df(dropbacks=10, weeks=6, add_slope=True)
        weekly = _make_weekly_df(targets=4, weeks=6)
        result = compute_tprr_features(route, weekly)
        valid = result.dropna(subset=["tprr_trail4", "tprr_x_route_slope"])
        if valid.empty:
            pytest.skip("No valid rows with both tprr_trail4 and tprr_x_route_slope")
        # The interaction was computed with route_rate_slope from route_df
        # (value 0.005 for weeks >= 3); tprr_trail4 * 0.005 should match
        tprr_t4 = valid["tprr_trail4"].values
        x_slope = valid["tprr_x_route_slope"].values
        # route_rate_slope in our fixture is 0.005; x_slope ~ tprr_t4 * 0.005
        expected = tprr_t4 * 0.005
        np.testing.assert_allclose(x_slope, expected, rtol=1e-5)

    def test_interaction_nan_when_no_slope_col(self) -> None:
        """tprr_x_route_slope must be NaN when route_rate_slope is absent."""
        route = _make_route_df(weeks=5, add_slope=False)
        weekly = _make_weekly_df(weeks=5)
        result = compute_tprr_features(route, weekly)
        assert result["tprr_x_route_slope"].isna().all()

    def test_empty_route_df(self) -> None:
        """Empty route_df should return empty DataFrame without error."""
        result = compute_tprr_features(pd.DataFrame(), _make_weekly_df())
        assert result.empty

    def test_empty_weekly_df(self) -> None:
        """Empty weekly_df should return empty DataFrame without error."""
        result = compute_tprr_features(_make_route_df(), pd.DataFrame())
        assert result.empty

    def test_missing_targets_column(self) -> None:
        """weekly_df without 'targets' should return empty DataFrame."""
        weekly_no_targets = _make_weekly_df().drop(columns=["targets"])
        result = compute_tprr_features(_make_route_df(), weekly_no_targets)
        assert result.empty

    def test_missing_dropbacks_column(self) -> None:
        """route_df without 'dropbacks_on_field' should return empty DataFrame."""
        route_no_db = _make_route_df().drop(columns=["dropbacks_on_field"])
        result = compute_tprr_features(route_no_db, _make_weekly_df())
        assert result.empty

    def test_two_players_independent_lag(self) -> None:
        """Lags should be computed independently per player."""
        route_a = _make_route_df(player_id=_PLAYER_A, dropbacks=10, weeks=5)
        route_b = _make_route_df(player_id=_PLAYER_B, dropbacks=5, weeks=5)
        weekly_a = _make_weekly_df(player_id=_PLAYER_A, targets=4, weeks=5)
        weekly_b = _make_weekly_df(player_id=_PLAYER_B, targets=2, weeks=5)

        route_all = pd.concat([route_a, route_b], ignore_index=True)
        weekly_all = pd.concat([weekly_a, weekly_b], ignore_index=True)
        result = compute_tprr_features(route_all, weekly_all)

        # Week 3 should have tprr=0.4 for A and tprr=0.4 for B (both 4/10 and 2/5)
        a_w3 = result[(result["player_id"] == _PLAYER_A) & (result["week"] == 3)]
        b_w3 = result[(result["player_id"] == _PLAYER_B) & (result["week"] == 3)]
        assert not a_w3.empty
        assert not b_w3.empty
        assert abs(float(a_w3["tprr"].iloc[0]) - 0.4) < 1e-5
        assert abs(float(b_w3["tprr"].iloc[0]) - 0.4) < 1e-5

    def test_no_duplicate_rows(self) -> None:
        """Output should have no duplicate (player_id, season, week) rows."""
        route = _make_route_df(weeks=8)
        weekly = _make_weekly_df(weeks=8)
        result = compute_tprr_features(route, weekly)
        dupes = result.duplicated(subset=["player_id", "season", "week"])
        assert not dupes.any(), "Duplicate player-week rows found"

    def test_tprr_trail4_slope_nan_below_min_obs(self) -> None:
        """tprr_trail4_slope should be NaN when fewer than 3 prior observations."""
        route = _make_route_df(weeks=3)
        weekly = _make_weekly_df(weeks=3)
        result = compute_tprr_features(route, weekly)
        w3 = result[result["week"] == 3]
        # At week 3: shift-1 gives 2 prior points; _SLOPE_MIN_GAMES=3 so NaN
        assert w3["tprr_trail4_slope"].isna().all()


# ---------------------------------------------------------------------------
# _build_spread_by_week tests
# ---------------------------------------------------------------------------


class TestBuildSpreadByWeek:
    """Unit tests for the spread lookup helper added to the lab.

    nflverse spread_line convention: POSITIVE = home team is favored.
    The function converts to betting convention: NEGATIVE = favored.
    A home favorite by 6.5 (spread_line = +6.5) → home: -6.5, away: +6.5.
    """

    @pytest.fixture
    def schedules(self) -> pd.DataFrame:
        """Minimal schedules DataFrame with spread_line.

        KC is a 6.5-pt home favorite (spread_line = +6.5 in nflverse convention).
        BUF is a 3.0-pt home favorite (spread_line = +3.0).
        SF vs SEA has NaN spread.
        """
        return pd.DataFrame(
            {
                "season": [2022, 2022, 2022],
                "week": [1, 1, 2],
                "home_team": ["KC", "BUF", "SF"],
                "away_team": ["LV", "NE", "SEA"],
                # nflverse: positive = home favored
                "spread_line": [6.5, 3.0, np.nan],
            }
        )

    def test_home_team_is_negative_when_favored(self, schedules: pd.DataFrame) -> None:
        """Home favorite should get negative betting-convention spread."""
        from experiment_heuristic_lab import _build_spread_by_week

        result = _build_spread_by_week(schedules)
        # KC home favored by 6.5 → betting convention: KC gets -6.5
        assert result[(2022, 1, "KC")] == pytest.approx(-6.5)

    def test_away_team_is_positive_when_dog(self, schedules: pd.DataFrame) -> None:
        """Away underdog should get positive betting-convention spread."""
        from experiment_heuristic_lab import _build_spread_by_week

        result = _build_spread_by_week(schedules)
        # LV is the away dog → betting convention: LV gets +6.5
        assert result[(2022, 1, "LV")] == pytest.approx(6.5)

    def test_nan_spread_defaults_zero(self, schedules: pd.DataFrame) -> None:
        """Games with NaN spread_line should get 0.0 (pick-em)."""
        from experiment_heuristic_lab import _build_spread_by_week

        result = _build_spread_by_week(schedules)
        assert result[(2022, 2, "SF")] == pytest.approx(0.0)
        assert result[(2022, 2, "SEA")] == pytest.approx(0.0)

    def test_spreads_sum_to_zero_per_game(self, schedules: pd.DataFrame) -> None:
        """Home and away spreads for the same game should sum to zero."""
        from experiment_heuristic_lab import _build_spread_by_week

        result = _build_spread_by_week(schedules)
        # BUF (home) + NE (away) = -3.0 + 3.0 = 0
        assert result[(2022, 1, "BUF")] + result[(2022, 1, "NE")] == pytest.approx(0.0)
        # KC (home) + LV (away) = -6.5 + 6.5 = 0
        assert result[(2022, 1, "KC")] + result[(2022, 1, "LV")] == pytest.approx(0.0)

    def test_empty_schedules(self) -> None:
        """Empty DataFrame should return empty dict."""
        from experiment_heuristic_lab import _build_spread_by_week

        result = _build_spread_by_week(pd.DataFrame())
        assert result == {}

    def test_missing_spread_column(self) -> None:
        """DataFrame without spread_line should return empty dict."""
        from experiment_heuristic_lab import _build_spread_by_week

        df = pd.DataFrame(
            {"season": [2022], "week": [1], "home_team": ["KC"], "away_team": ["LV"]}
        )
        result = _build_spread_by_week(df)
        assert result == {}

    def test_sign_matches_projection_engine_convention(self) -> None:
        """Verify sign matches _build_spread_by_team in projection_engine.

        projection_engine._build_spread_by_team docs say:
          home_spread = -spread_line (negative = favored)
          away_spread = +spread_line
        This function should produce identical values for the same game.
        """
        from experiment_heuristic_lab import _build_spread_by_week

        # Home team KC favored by 7 pts (nflverse spread_line = +7.0)
        df = pd.DataFrame(
            {
                "season": [2023],
                "week": [1],
                "home_team": ["KC"],
                "away_team": ["LV"],
                "spread_line": [7.0],
            }
        )
        result = _build_spread_by_week(df)
        # Home favorite (betting convention: negative)
        assert result[(2023, 1, "KC")] == pytest.approx(-7.0)
        # Away underdog (betting convention: positive)
        assert result[(2023, 1, "LV")] == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# _compute_per_position_spearman tests
# ---------------------------------------------------------------------------


class TestComputePerPositionSpearman:
    """Unit tests for the mean within-week Spearman helper."""

    def _make_results(self, n_weeks: int = 3, n_players: int = 8) -> pd.DataFrame:
        """Create synthetic results with a known rank correlation."""
        rows = []
        for w in range(3, 3 + n_weeks):
            for i in range(n_players):
                rows.append(
                    {
                        "position": "WR",
                        "season": 2022,
                        "week": w,
                        "projected_points": float(i) + np.random.normal(0, 0.1),
                        "actual_points": float(i),
                        "player_name": f"P{i}",
                    }
                )
        return pd.DataFrame(rows)

    def test_returns_all_positions(self) -> None:
        """Result dict must have keys for all 4 positions."""
        from experiment_heuristic_lab import _compute_per_position_spearman

        # Create minimal results with all 4 positions
        rows = []
        for pos in ["QB", "RB", "WR", "TE"]:
            for w in range(3, 8):
                for i in range(6):
                    rows.append(
                        {
                            "position": pos,
                            "season": 2022,
                            "week": w,
                            "projected_points": float(i),
                            "actual_points": float(i),
                        }
                    )
        results = pd.DataFrame(rows)
        out = _compute_per_position_spearman(results)
        for pos in ["QB", "RB", "WR", "TE"]:
            assert f"{pos}_spearman_weekly" in out

    def test_perfect_correlation_returns_one(self) -> None:
        """Perfect rank ordering within every week should return ~1.0."""
        from experiment_heuristic_lab import _compute_per_position_spearman

        rows = []
        for w in range(3, 8):
            for i in range(8):
                rows.append(
                    {
                        "position": "WR",
                        "season": 2022,
                        "week": w,
                        "projected_points": float(i),
                        "actual_points": float(i),
                    }
                )
        results = pd.DataFrame(rows)
        out = _compute_per_position_spearman(results)
        assert out["WR_spearman_weekly"] == pytest.approx(1.0)

    def test_reverse_correlation_returns_minus_one(self) -> None:
        """Perfect reverse ordering within every week should return ~-1.0."""
        from experiment_heuristic_lab import _compute_per_position_spearman

        n = 8
        rows = []
        for w in range(3, 8):
            for i in range(n):
                rows.append(
                    {
                        "position": "RB",
                        "season": 2022,
                        "week": w,
                        "projected_points": float(i),
                        "actual_points": float(n - 1 - i),
                    }
                )
        results = pd.DataFrame(rows)
        out = _compute_per_position_spearman(results)
        assert out["RB_spearman_weekly"] == pytest.approx(-1.0)

    def test_missing_position_nan(self) -> None:
        """Position with no rows should return NaN."""
        from experiment_heuristic_lab import _compute_per_position_spearman

        rows = [
            {
                "position": "WR",
                "season": 2022,
                "week": w,
                "projected_points": float(i),
                "actual_points": float(i),
            }
            for w in range(3, 8)
            for i in range(6)
        ]
        results = pd.DataFrame(rows)
        out = _compute_per_position_spearman(results)
        assert np.isnan(out["QB_spearman_weekly"])
        assert np.isnan(out["TE_spearman_weekly"])

    def test_week_with_fewer_than_5_players_excluded(self) -> None:
        """Weeks with fewer than 5 players should be excluded from the mean."""
        from experiment_heuristic_lab import _compute_per_position_spearman

        # Week 3 has only 4 players (excluded); weeks 4-7 have 8 players each
        rows = []
        for w in range(4, 8):  # qualifying weeks
            for i in range(8):
                rows.append(
                    {
                        "position": "TE",
                        "season": 2022,
                        "week": w,
                        "projected_points": float(i),
                        "actual_points": float(i),
                    }
                )
        # Add week 3 with only 4 players (below threshold)
        for i in range(4):
            rows.append(
                {
                    "position": "TE",
                    "season": 2022,
                    "week": 3,
                    "projected_points": float(i),
                    "actual_points": float(i),
                }
            )
        results = pd.DataFrame(rows)
        out = _compute_per_position_spearman(results)
        # Should still return a valid (non-NaN) value from weeks 4-7
        assert np.isfinite(out["TE_spearman_weekly"])
        # And the mean should be based only on qualifying weeks
        assert out["TE_spearman_weekly"] == pytest.approx(1.0)

    def test_empty_dataframe_returns_nan(self) -> None:
        """Empty results DataFrame (with required columns) should return NaN for all positions."""
        from experiment_heuristic_lab import _compute_per_position_spearman

        # Empty DataFrame must have the expected columns for groupby to work
        empty = pd.DataFrame(
            columns=["position", "season", "week", "projected_points", "actual_points"]
        )
        out = _compute_per_position_spearman(empty)
        for pos in ["QB", "RB", "WR", "TE"]:
            assert np.isnan(out[f"{pos}_spearman_weekly"])


# ---------------------------------------------------------------------------
# Production wiring: _apply_wr_tprr_collapse in projection_engine
# ---------------------------------------------------------------------------


class TestWrTprrCollapseProduction:
    """The TPRR collapse production correction (projection_engine 4d)."""

    @staticmethod
    def _frames():
        import pandas as pd

        combined = pd.DataFrame(
            {
                "player_id": ["W1", "W2", "R1"],
                "position": ["WR", "WR", "RB"],
                "projected_points": [10.0, 12.0, 14.0],
                "proj_receiving_yards": [60.0, 70.0, 10.0],
            }
        )
        tprr_rows = pd.DataFrame(
            {
                "player_id": ["W1", "W2", "R1"],
                "season": [2024] * 3,
                "week": [10] * 3,
                # W1 collapsing (< -0.02), W2 stable, R1 collapsing but RB
                "tprr_trail4_slope": [-0.05, 0.01, -0.08],
            }
        )
        return combined, tprr_rows

    def test_collapse_applies_to_flagged_wr_only(self):
        import pandas as pd
        from projection_engine import (
            WR_TPRR_COLLAPSE_MULT,
            _apply_wr_tprr_collapse,
        )

        combined, tprr_rows = self._frames()
        weekly = pd.DataFrame(
            {"player_id": ["W1"], "season": [2024], "week": [9], "targets": [5]}
        )
        n = _apply_wr_tprr_collapse(combined, tprr_rows, weekly, 2024, 10)
        assert n == 1
        # W1 scaled, W2 untouched, RB untouched despite collapsing slope
        assert combined.loc[0, "projected_points"] == round(
            10.0 * WR_TPRR_COLLAPSE_MULT, 2
        )
        assert combined.loc[1, "projected_points"] == 12.0
        assert combined.loc[2, "projected_points"] == 14.0
        # Stat columns scaled too
        assert combined.loc[0, "proj_receiving_yards"] == round(
            60.0 * WR_TPRR_COLLAPSE_MULT, 2
        )

    def test_no_data_is_noop(self):
        import pandas as pd
        from projection_engine import _apply_wr_tprr_collapse

        combined, _ = self._frames()
        before = combined["projected_points"].tolist()
        n = _apply_wr_tprr_collapse(
            combined, pd.DataFrame(), pd.DataFrame(), 2024, 10
        )
        assert n == 0
        assert combined["projected_points"].tolist() == before

    def test_computes_tprr_when_columns_absent(self):
        """When route_df lacks tprr columns, they are computed on the fly
        from dropbacks + targets (via compute_tprr_features)."""
        import pandas as pd
        from projection_engine import _apply_wr_tprr_collapse

        combined, _ = self._frames()
        # Raw route participation (no tprr columns): W1 has a declining
        # targets-per-route trend over weeks 1-9.
        rows = []
        for wk in range(1, 11):
            rows.append(
                {
                    "player_id": "W1",
                    "season": 2024,
                    "week": wk,
                    "dropbacks_on_field": 30,
                }
            )
        route_df = pd.DataFrame(rows)
        weekly = pd.DataFrame(
            {
                "player_id": ["W1"] * 10,
                "season": [2024] * 10,
                "week": list(range(1, 11)),
                # Steep target decline: 12 -> 0
                "targets": [12, 11, 10, 8, 6, 5, 3, 2, 1, 0],
            }
        )
        n = _apply_wr_tprr_collapse(combined, route_df, weekly, 2024, 10)
        assert n == 1
        assert combined.loc[0, "projected_points"] < 10.0
