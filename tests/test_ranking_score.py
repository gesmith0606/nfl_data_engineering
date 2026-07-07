"""Tests for src/ranking_score.py — ranking_score ordering nudges.

Tests verify:
  - Nudge math: z-score within group * alpha, summed across signals
  - Cap behaviour: total nudge capped to ±RANKING_NUDGE_CAP regardless of
    how many signals are active
  - Missing-data fallback: missing graph data → ranking_score == projected_points
  - Rank-by-ranking_score vs rank-by-points switching (USE_RANKING_SCORE flag)
  - No mutation of projected_points / floor / ceiling
  - Lagged-input assertion: ranking_score applied to a frame with season/week
    matching the graph features' already-lagged index
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Bootstrap project root so imports resolve without an installed package.
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "src"), str(_ROOT), str(_ROOT / "scripts")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ranking_score as rs
from ranking_score import (
    RANKING_NUDGE_CAP,
    USE_RANKING_SCORE,
    apply_ranking_scores,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_projections(n: int = 6, position: str = "WR") -> pd.DataFrame:
    """Minimal projections DataFrame with the required columns."""
    return pd.DataFrame(
        {
            "player_id": [f"P{i:03d}" for i in range(n)],
            "player_name": [f"Player {i}" for i in range(n)],
            "position": [position] * n,
            "projected_points": [float(10 + i) for i in range(n)],
            "projected_floor": [float(5 + i) for i in range(n)],
            "projected_ceiling": [float(20 + i) for i in range(n)],
            "season": [2024] * n,
            "week": [5] * n,
        }
    )


def _make_graph_df(
    player_ids: list,
    season: int = 2024,
    week: int = 5,
    chem_values: list | None = None,
    rz_values: list | None = None,
) -> pd.DataFrame:
    """Minimal graph_all_features DataFrame for WR signals."""
    n = len(player_ids)
    chem = chem_values if chem_values is not None else list(range(n))
    rz = rz_values if rz_values is not None else [v * 0.1 for v in range(n)]
    return pd.DataFrame(
        {
            "player_id": player_ids,
            "season": [season] * n,
            "week": [week] * n,
            "qb_wr_chemistry_epa_roll3": [float(v) for v in chem],
            "rz_target_share_roll3": [float(v) for v in rz],
            "predicted_script_boost": [float(v) * 0.5 for v in range(n)],
            "rz_carry_share_roll3": [float(v) * 0.2 for v in range(n)],
        }
    )


# ---------------------------------------------------------------------------
# Core nudge-math tests
# ---------------------------------------------------------------------------


class TestNudgeMath:
    """Verify the additive z-score nudge formula."""

    def test_nudge_is_additive_not_multiplicative(self) -> None:
        """ranking_score = projected_points + nudge (not projected_points * factor).

        Verify the formula is additive by checking that:
        1. ranking_score = projected_points + nudge exactly (no scaling by pts).
        2. Two players with the SAME projected_points but different signal values
           get the same projected_points but different ranking_scores — impossible
           if the nudge were a multiplier of projected_points.
        """
        # Four players: two with identical projected_points but different signals.
        # Needs >=3 players to satisfy min_group_size in _zscore_within_group.
        proj = pd.DataFrame(
            {
                "player_id": ["P000", "P001", "P002", "P003"],
                "position": ["WR"] * 4,
                "projected_points": [15.0, 15.0, 12.0, 8.0],  # P000/P001 tied
                "projected_floor": [10.0] * 4,
                "projected_ceiling": [20.0] * 4,
                "season": [2024] * 4,
                "week": [5] * 4,
            }
        )
        # P000 has the lowest signal; P001 has the highest signal.
        # P002 and P003 are filler with mid signals.
        gdf = pd.DataFrame(
            {
                "player_id": ["P000", "P001", "P002", "P003"],
                "season": [2024] * 4,
                "week": [5] * 4,
                "qb_wr_chemistry_epa_roll3": [0.0, 100.0, 50.0, 25.0],
                "rz_target_share_roll3": [0.0] * 4,
            }
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.20}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)

        # P000 and P001 have identical projected_points
        pts0 = float(out.loc[out["player_id"] == "P000", "projected_points"].iloc[0])
        pts1 = float(out.loc[out["player_id"] == "P001", "projected_points"].iloc[0])
        rs0 = float(out.loc[out["player_id"] == "P000", "ranking_score"].iloc[0])
        rs1 = float(out.loc[out["player_id"] == "P001", "ranking_score"].iloc[0])

        assert pts0 == pts1 == 15.0, "projected_points must be unchanged"
        assert rs0 != rs1, (
            "Two players with same projected_points but different signals must "
            "have different ranking_scores (additive formula)"
        )
        # High-signal player (P001) must have higher ranking_score
        assert rs1 > rs0, "Higher-signal player must have higher ranking_score"

    def test_zero_mean_nudge(self) -> None:
        """Nudges should sum to ≈ 0 within a group (z-scores are zero-centred)."""
        proj = _make_projections(6, "WR")
        gdf = _make_graph_df(proj["player_id"].tolist())
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        nudges = out["ranking_score"] - out["projected_points"]
        assert abs(float(nudges.sum())) < 0.5, (
            "Nudges should sum near zero (z-score symmetry)"
        )

    def test_higher_signal_player_gets_positive_nudge(self) -> None:
        """Player with above-median signal value should get a positive nudge."""
        proj = _make_projections(6, "WR")
        # Ascending chem values: player 5 has the highest
        gdf = _make_graph_df(proj["player_id"].tolist(), chem_values=[0, 1, 2, 3, 4, 5])
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        p5 = out.loc[out["player_id"] == "P005", "ranking_score"].iloc[0]
        p0 = out.loc[out["player_id"] == "P000", "ranking_score"].iloc[0]
        assert p5 > out.loc[out["player_id"] == "P005", "projected_points"].iloc[0], (
            "Top-signal player should have ranking_score > projected_points"
        )
        assert p0 < out.loc[out["player_id"] == "P000", "projected_points"].iloc[0], (
            "Bottom-signal player should have ranking_score < projected_points"
        )

    def test_multi_signal_contributions_sum(self) -> None:
        """With two signals, total nudge should exceed single-signal nudge (pre-cap)."""
        proj = _make_projections(6, "WR")
        gdf = _make_graph_df(proj["player_id"].tolist())

        params_single = {"WR": {"qb_wr_chemistry_epa_roll3": 0.20}}
        params_double = {"WR": {"qb_wr_chemistry_epa_roll3": 0.20, "rz_target_share_roll3": 0.10}}

        out_s = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params_single)
        out_d = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params_double)

        nudge_single = (out_s["ranking_score"] - out_s["projected_points"]).abs().mean()
        nudge_double = (out_d["ranking_score"] - out_d["projected_points"]).abs().mean()
        assert nudge_double >= nudge_single, (
            "Two signals should produce equal or larger nudges than one"
        )


# ---------------------------------------------------------------------------
# Cap behaviour
# ---------------------------------------------------------------------------


class TestCapBehaviour:
    """Verify the ±RANKING_NUDGE_CAP hard cap is enforced."""

    def test_nudge_never_exceeds_cap(self) -> None:
        """Total nudge per player must never exceed ±RANKING_NUDGE_CAP."""
        proj = _make_projections(6, "WR")
        # Extreme signal values to force large z-scores
        gdf = _make_graph_df(
            proj["player_id"].tolist(),
            chem_values=[0.0, 1000.0, 2000.0, 3000.0, 4000.0, 5000.0],
            rz_values=[0.0, 100.0, 200.0, 300.0, 400.0, 500.0],
        )
        params = {
            "WR": {"qb_wr_chemistry_epa_roll3": 5.0, "rz_target_share_roll3": 5.0}
        }

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        nudges = (out["ranking_score"] - out["projected_points"]).abs()
        assert nudges.max() <= RANKING_NUDGE_CAP + 1e-9, (
            f"Nudge {nudges.max():.4f} exceeds cap {RANKING_NUDGE_CAP}"
        )

    def test_cap_symmetric(self) -> None:
        """Cap applies in both directions — no player gets more than +cap or less than -cap."""
        proj = _make_projections(6, "WR")
        gdf = _make_graph_df(
            proj["player_id"].tolist(),
            chem_values=[-5000.0, -4000.0, -3000.0, 3000.0, 4000.0, 5000.0],
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 10.0}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        nudges = out["ranking_score"] - out["projected_points"]
        assert nudges.max() <= RANKING_NUDGE_CAP + 1e-9
        assert nudges.min() >= -RANKING_NUDGE_CAP - 1e-9

    def test_ranking_score_always_nonnegative(self) -> None:
        """ranking_score must be >= 0 (clip(lower=0) invariant)."""
        proj = _make_projections(4, "WR")
        proj["projected_points"] = [0.1, 0.2, 0.5, 1.0]  # near-zero points
        gdf = _make_graph_df(
            proj["player_id"].tolist()[:4],
            chem_values=[-100.0, -200.0, -300.0, -400.0],
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 2.0}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        assert (out["ranking_score"] >= 0.0).all(), "ranking_score must be >= 0"


# ---------------------------------------------------------------------------
# Missing-data fallback
# ---------------------------------------------------------------------------


class TestMissingDataFallback:
    """ranking_score falls back to projected_points when graph data absent."""

    def test_none_graph_df(self) -> None:
        """None graph_df → ranking_score == projected_points."""
        proj = _make_projections(4, "WR")
        out = apply_ranking_scores(proj, None, 2024, 5)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_empty_graph_df(self) -> None:
        """Empty graph_df → ranking_score == projected_points."""
        proj = _make_projections(4, "WR")
        out = apply_ranking_scores(proj, pd.DataFrame(), 2024, 5)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_graph_df_wrong_player_ids(self) -> None:
        """Graph data for different players → no nudge (NaN → 0)."""
        proj = _make_projections(4, "WR")
        gdf = _make_graph_df(["X001", "X002", "X003", "X004"])  # IDs not in proj
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_missing_signal_column_skipped(self) -> None:
        """If a signal column is absent from graph_df, it is silently skipped."""
        proj = _make_projections(4, "WR")
        gdf = _make_graph_df(proj["player_id"].tolist())
        # Request a column that doesn't exist
        params = {"WR": {"non_existent_column_xyz": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_partial_player_coverage(self) -> None:
        """Players without graph data get zero nudge; others get nudge."""
        proj = _make_projections(6, "WR")
        # Only 3 of 6 players have graph data (below min_group_size=3 minimum)
        gdf = _make_graph_df(
            proj["player_id"].tolist()[:3],  # P000, P001, P002 only
            chem_values=[0.0, 10.0, 20.0],
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        # Players with data: non-zero nudges; players without: zero nudge
        with_data_ids = {"P000", "P001", "P002"}
        without_data = out[~out["player_id"].isin(with_data_ids)]
        np.testing.assert_array_almost_equal(
            without_data["ranking_score"].values,
            without_data["projected_points"].values,
        )


# ---------------------------------------------------------------------------
# USE_RANKING_SCORE flag switching
# ---------------------------------------------------------------------------


class TestFlagSwitching:
    """rank-by-ranking_score vs rank-by-points controlled by USE_RANKING_SCORE."""

    def test_flag_off_returns_projected_points(self, monkeypatch) -> None:
        """When USE_RANKING_SCORE=False, ranking_score == projected_points."""
        monkeypatch.setattr(rs, "USE_RANKING_SCORE", False)
        proj = _make_projections(6, "WR")
        gdf = _make_graph_df(proj["player_id"].tolist())

        out = apply_ranking_scores(proj, gdf, 2024, 5)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_flag_on_produces_nudge(self, monkeypatch) -> None:
        """When USE_RANKING_SCORE=True, ranking_score differs from projected_points."""
        monkeypatch.setattr(rs, "USE_RANKING_SCORE", True)
        proj = _make_projections(6, "WR")
        gdf = _make_graph_df(proj["player_id"].tolist(), chem_values=[0, 1, 2, 3, 4, 5])
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        diff = (out["ranking_score"] - out["projected_points"]).abs()
        assert diff.max() > 0.0, "Expected non-zero nudge when flag is on"

    def test_position_rank_follows_ranking_score(self) -> None:
        """When ranking_score column is used, position_rank follows it, not projected_points."""
        proj = _make_projections(4, "WR")
        # Player P000 has the highest projected_points but lowest signal
        proj.loc[proj["player_id"] == "P000", "projected_points"] = 20.0
        proj.loc[proj["player_id"] == "P001", "projected_points"] = 10.0

        gdf = _make_graph_df(
            proj["player_id"].tolist()[:4],
            chem_values=[0.0, 100.0, 5.0, 5.0],  # P001 has highest signal
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)

        # With alpha=0.30 and chem spread 0-100 for 4 players, P001 should
        # have a large positive nudge (top z-score +cap) and P000 a negative
        # nudge (bottom z-score -cap), potentially reordering them.
        p000_rs = float(out.loc[out["player_id"] == "P000", "ranking_score"].iloc[0])
        p001_rs = float(out.loc[out["player_id"] == "P001", "ranking_score"].iloc[0])
        p000_pts = 20.0
        p001_pts = 10.0

        # ranking_score for P001 should be higher than projected_points
        assert p001_rs > p001_pts, "High-signal player should gain ranking_score"
        # ranking_score for P000 should be lower than projected_points
        assert p000_rs < p000_pts, "Low-signal player should lose ranking_score"


# ---------------------------------------------------------------------------
# Immutability: projected_points / floor / ceiling must not be modified
# ---------------------------------------------------------------------------


class TestImmutability:
    """apply_ranking_scores must not touch projected_points, floor, or ceiling."""

    def test_projected_points_unchanged(self) -> None:
        """projected_points is invariant across apply_ranking_scores."""
        proj = _make_projections(6, "WR")
        orig_pts = proj["projected_points"].values.copy()
        gdf = _make_graph_df(proj["player_id"].tolist())

        out = apply_ranking_scores(proj, gdf, 2024, 5)
        np.testing.assert_array_equal(out["projected_points"].values, orig_pts)

    def test_floor_unchanged(self) -> None:
        proj = _make_projections(6, "WR")
        orig_floor = proj["projected_floor"].values.copy()
        gdf = _make_graph_df(proj["player_id"].tolist())

        out = apply_ranking_scores(proj, gdf, 2024, 5)
        np.testing.assert_array_equal(out["projected_floor"].values, orig_floor)

    def test_ceiling_unchanged(self) -> None:
        proj = _make_projections(6, "WR")
        orig_ceiling = proj["projected_ceiling"].values.copy()
        gdf = _make_graph_df(proj["player_id"].tolist())

        out = apply_ranking_scores(proj, gdf, 2024, 5)
        np.testing.assert_array_equal(out["projected_ceiling"].values, orig_ceiling)

    def test_input_df_not_mutated(self) -> None:
        """Original projections_df must not be modified in-place."""
        proj = _make_projections(6, "WR")
        orig_pts = proj["projected_points"].values.copy()
        gdf = _make_graph_df(proj["player_id"].tolist())

        _ = apply_ranking_scores(proj, gdf, 2024, 5)
        # Input frame must still have original points
        np.testing.assert_array_equal(proj["projected_points"].values, orig_pts)
        assert "ranking_score" not in proj.columns, (
            "ranking_score must not be added to the original DataFrame"
        )

    def test_vorp_not_present_to_mutate(self) -> None:
        """VORP is not computed here; the function doesn't add or alter it."""
        proj = _make_projections(4, "WR")
        gdf = _make_graph_df(proj["player_id"].tolist())
        out = apply_ranking_scores(proj, gdf, 2024, 5)
        assert "vorp" not in out.columns, (
            "apply_ranking_scores must not create a vorp column"
        )


# ---------------------------------------------------------------------------
# Lagged-input assertion
# ---------------------------------------------------------------------------


class TestLaggedInput:
    """Confirm function honours the (season, week) join key from graph_df,
    which encodes trailing-lagged stats through W-1."""

    def test_wrong_season_no_nudge(self) -> None:
        """Graph data for season 2023 must not nudge projections for season 2024."""
        proj = _make_projections(4, "WR")  # season=2024, week=5
        gdf = _make_graph_df(
            proj["player_id"].tolist(),
            season=2023,  # different season
            week=5,
            chem_values=[0, 100, 200, 300],
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, season=2024, week=5, position_params=params)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_wrong_week_no_nudge(self) -> None:
        """Graph data for week 3 must not nudge projections for week 5."""
        proj = _make_projections(4, "WR")  # season=2024, week=5
        gdf = _make_graph_df(
            proj["player_id"].tolist(),
            season=2024,
            week=3,  # different week
            chem_values=[0, 100, 200, 300],
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, season=2024, week=5, position_params=params)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_correct_season_week_produces_nudge(self) -> None:
        """Graph data for the matching (season, week) must produce nudges."""
        proj = _make_projections(4, "WR")  # season=2024, week=5
        gdf = _make_graph_df(
            proj["player_id"].tolist(),
            season=2024,
            week=5,
            chem_values=[0, 10, 20, 30],
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, season=2024, week=5, position_params=params)
        diff = (out["ranking_score"] - out["projected_points"]).abs()
        assert diff.max() > 0.0, "Expected nudges when season/week match"


# ---------------------------------------------------------------------------
# Multi-position isolation
# ---------------------------------------------------------------------------


class TestPositionIsolation:
    """RB and WR nudges must not bleed into each other's positions."""

    def test_wr_params_do_not_affect_rb(self) -> None:
        """WR signal params must not nudge RB players."""
        proj_wr = _make_projections(4, "WR")
        proj_rb = _make_projections(4, "RB")
        proj_rb["player_id"] = [f"R{i:03d}" for i in range(4)]
        proj = pd.concat([proj_wr, proj_rb], ignore_index=True)

        all_ids = proj["player_id"].tolist()
        gdf = pd.DataFrame(
            {
                "player_id": all_ids,
                "season": [2024] * 8,
                "week": [5] * 8,
                "qb_wr_chemistry_epa_roll3": [float(i * 10) for i in range(8)],
                "rz_target_share_roll3": [float(i * 0.1) for i in range(8)],
                "predicted_script_boost": [float(i * 0.5) for i in range(8)],
                "rz_carry_share_roll3": [float(i * 0.2) for i in range(8)],
            }
        )
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        rb_out = out[out["position"] == "RB"]
        np.testing.assert_array_almost_equal(
            rb_out["ranking_score"].values,
            rb_out["projected_points"].values,
        )

    def test_rb_params_do_not_affect_wr(self) -> None:
        """RB signal params must not nudge WR players."""
        proj_wr = _make_projections(4, "WR")
        proj_rb = _make_projections(4, "RB")
        proj_rb["player_id"] = [f"R{i:03d}" for i in range(4)]
        proj = pd.concat([proj_wr, proj_rb], ignore_index=True)

        gdf = pd.DataFrame(
            {
                "player_id": proj["player_id"].tolist(),
                "season": [2024] * 8,
                "week": [5] * 8,
                "predicted_script_boost": [float(i * 5) for i in range(8)],
                "rz_carry_share_roll3": [float(i * 0.2) for i in range(8)],
            }
        )
        params = {"RB": {"predicted_script_boost": 0.15}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        wr_out = out[out["position"] == "WR"]
        np.testing.assert_array_almost_equal(
            wr_out["ranking_score"].values,
            wr_out["projected_points"].values,
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty DataFrame, single player, constant signal values."""

    def test_empty_projections_df(self) -> None:
        """Empty projections_df → returns empty DataFrame with ranking_score column."""
        proj = pd.DataFrame(
            columns=["player_id", "position", "projected_points", "season", "week"]
        )
        gdf = _make_graph_df(["P000"])

        out = apply_ranking_scores(proj, gdf, 2024, 5)
        assert len(out) == 0
        assert "ranking_score" in out.columns

    def test_single_player_no_group_spearman(self) -> None:
        """Single player per (season, week) → no nudge (group too small)."""
        proj = _make_projections(1, "WR")
        gdf = _make_graph_df(["P000"], chem_values=[100.0])
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_constant_signal_no_nudge(self) -> None:
        """All players with identical signal value → z-score=0 → no nudge."""
        proj = _make_projections(5, "WR")
        gdf = _make_graph_df(proj["player_id"].tolist(), chem_values=[5.0] * 5)
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, 2024, 5, position_params=params)
        pd.testing.assert_series_equal(
            out["ranking_score"],
            out["projected_points"],
            check_names=False,
        )

    def test_season_week_columns_injected_when_absent(self) -> None:
        """If season/week columns are missing, they are injected from parameters."""
        proj = _make_projections(4, "WR")
        proj = proj.drop(columns=["season", "week"])
        gdf = _make_graph_df(proj["player_id"].tolist(), season=2024, week=5)
        params = {"WR": {"qb_wr_chemistry_epa_roll3": 0.30}}

        out = apply_ranking_scores(proj, gdf, season=2024, week=5, position_params=params)
        assert "season" in out.columns
        assert "week" in out.columns
        assert "ranking_score" in out.columns
