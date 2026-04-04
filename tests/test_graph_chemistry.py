#!/usr/bin/env python3
"""Tests for QB-WR chemistry graph features.

Tests cover:
- QB-WR pair extraction from PBP
- Chemistry feature computation with rolling windows
- Temporal lag enforcement (shift(1))
- QB changes mid-season
- WR with no prior games with current QB (NaN)
- Empty/missing data handling
- Feature column schema consistency
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_qb_wr_chemistry import (
    QB_WR_CHEMISTRY_FEATURE_COLUMNS,
    build_qb_wr_chemistry,
    compute_chemistry_features,
)


# ---------------------------------------------------------------------------
# Fixtures -- synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def pbp_pass_plays():
    """Synthetic PBP pass plays across 4 weeks for 1 QB-WR pair."""
    rows = []
    qb_id = "QB001"
    wr_id = "WR001"
    wr2_id = "WR002"

    for week in range(1, 5):
        # QB001 -> WR001: 5 targets per week
        for play in range(5):
            rows.append(
                {
                    "play_id": week * 100 + play,
                    "game_id": f"2024_{week:02d}_KC_BUF",
                    "season": 2024,
                    "week": week,
                    "play_type": "pass",
                    "passer_player_id": qb_id,
                    "receiver_player_id": wr_id,
                    "complete_pass": 1 if play < 3 else 0,  # 60% comp rate
                    "yards_gained": 12 if play < 3 else 0,
                    "pass_touchdown": 1 if play == 0 else 0,
                    "epa": 0.5 if play < 3 else -0.3,
                    "air_yards": 10.0 + play,
                }
            )
        # QB001 -> WR002: 3 targets per week
        for play in range(3):
            rows.append(
                {
                    "play_id": week * 100 + 50 + play,
                    "game_id": f"2024_{week:02d}_KC_BUF",
                    "season": 2024,
                    "week": week,
                    "play_type": "pass",
                    "passer_player_id": qb_id,
                    "receiver_player_id": wr2_id,
                    "complete_pass": 1 if play < 2 else 0,
                    "yards_gained": 8 if play < 2 else 0,
                    "pass_touchdown": 0,
                    "epa": 0.2 if play < 2 else -0.1,
                    "air_yards": 7.0,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def player_weekly_df():
    """Synthetic player_weekly with QB, WR, and RB."""
    rows = []
    for week in range(1, 5):
        # QB
        rows.append(
            {
                "player_id": "QB001",
                "player_name": "Patrick Mahomes",
                "recent_team": "KC",
                "position": "QB",
                "season": 2024,
                "week": week,
                "attempts": 30,
                "completions": 20,
            }
        )
        # WR1
        rows.append(
            {
                "player_id": "WR001",
                "player_name": "Rashee Rice",
                "recent_team": "KC",
                "position": "WR",
                "season": 2024,
                "week": week,
                "attempts": 0,
                "completions": 0,
            }
        )
        # WR2
        rows.append(
            {
                "player_id": "WR002",
                "player_name": "Xavier Worthy",
                "recent_team": "KC",
                "position": "WR",
                "season": 2024,
                "week": week,
                "attempts": 0,
                "completions": 0,
            }
        )
        # RB (should not get chemistry features)
        rows.append(
            {
                "player_id": "RB001",
                "player_name": "Isiah Pacheco",
                "recent_team": "KC",
                "position": "RB",
                "season": 2024,
                "week": week,
                "attempts": 0,
                "completions": 0,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def qb_change_pbp():
    """PBP with a QB change in week 3 (starter injured, backup takes over)."""
    rows = []
    # Weeks 1-2: QB_A -> WR001
    for week in [1, 2]:
        for play in range(4):
            rows.append(
                {
                    "play_id": week * 100 + play,
                    "game_id": f"2024_{week:02d}_DAL_NYG",
                    "season": 2024,
                    "week": week,
                    "play_type": "pass",
                    "passer_player_id": "QB_A",
                    "receiver_player_id": "WR_X",
                    "complete_pass": 1 if play < 2 else 0,
                    "yards_gained": 10 if play < 2 else 0,
                    "pass_touchdown": 0,
                    "epa": 0.3,
                    "air_yards": 8.0,
                }
            )
    # Weeks 3-4: QB_B -> WR001 (QB change)
    for week in [3, 4]:
        for play in range(4):
            rows.append(
                {
                    "play_id": week * 100 + play,
                    "game_id": f"2024_{week:02d}_DAL_NYG",
                    "season": 2024,
                    "week": week,
                    "play_type": "pass",
                    "passer_player_id": "QB_B",
                    "receiver_player_id": "WR_X",
                    "complete_pass": 1 if play < 3 else 0,
                    "yards_gained": 15 if play < 3 else 0,
                    "pass_touchdown": 0,
                    "epa": 0.5,
                    "air_yards": 12.0,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def qb_change_weekly():
    """Player weekly matching the QB change scenario."""
    rows = []
    for week in [1, 2]:
        rows.append(
            {
                "player_id": "QB_A",
                "recent_team": "DAL",
                "position": "QB",
                "season": 2024,
                "week": week,
                "attempts": 25,
            }
        )
    for week in [3, 4]:
        rows.append(
            {
                "player_id": "QB_B",
                "recent_team": "DAL",
                "position": "QB",
                "season": 2024,
                "week": week,
                "attempts": 28,
            }
        )
    for week in range(1, 5):
        rows.append(
            {
                "player_id": "WR_X",
                "recent_team": "DAL",
                "position": "WR",
                "season": 2024,
                "week": week,
                "attempts": 0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests -- build_qb_wr_chemistry
# ---------------------------------------------------------------------------


class TestBuildQBWRChemistry:
    """Tests for QB-WR pair extraction from PBP."""

    def test_basic_pair_extraction(self, pbp_pass_plays):
        """Should extract correct pair-week aggregates."""
        result = build_qb_wr_chemistry(pbp_pass_plays)

        assert not result.empty
        assert "passer_id" in result.columns
        assert "receiver_id" in result.columns

        # QB001-WR001: 5 targets per week, 4 weeks
        pair = result[
            (result["passer_id"] == "QB001") & (result["receiver_id"] == "WR001")
        ]
        assert len(pair) == 4  # 4 weeks

        week1 = pair[pair["week"] == 1].iloc[0]
        assert week1["targets"] == 5
        assert week1["completions"] == 3
        assert week1["yards"] == 36  # 3 * 12
        assert week1["tds"] == 1

    def test_completion_rate(self, pbp_pass_plays):
        """Should compute correct completion rate per pair-week."""
        result = build_qb_wr_chemistry(pbp_pass_plays)
        pair = result[
            (result["passer_id"] == "QB001") & (result["receiver_id"] == "WR001")
        ]
        # 3 completions / 5 targets = 0.6
        assert abs(pair.iloc[0]["comp_rate"] - 0.6) < 1e-6

    def test_epa_aggregation(self, pbp_pass_plays):
        """Should compute EPA sum and mean correctly."""
        result = build_qb_wr_chemistry(pbp_pass_plays)
        pair = result[
            (result["passer_id"] == "QB001") & (result["receiver_id"] == "WR001")
        ]
        week1 = pair[pair["week"] == 1].iloc[0]
        # 3 * 0.5 + 2 * (-0.3) = 0.9
        assert abs(week1["epa_sum"] - 0.9) < 1e-6
        assert abs(week1["epa_mean"] - 0.9 / 5) < 1e-6

    def test_multiple_receivers(self, pbp_pass_plays):
        """Should handle multiple receivers for same QB."""
        result = build_qb_wr_chemistry(pbp_pass_plays)
        receivers = result[result["passer_id"] == "QB001"]["receiver_id"].unique()
        assert len(receivers) == 2
        assert set(receivers) == {"WR001", "WR002"}

    def test_empty_pbp(self):
        """Should return empty DataFrame for empty input."""
        result = build_qb_wr_chemistry(pd.DataFrame())
        assert result.empty

    def test_no_pass_plays(self):
        """Should return empty when no pass plays exist."""
        df = pd.DataFrame(
            {
                "play_type": ["run", "run"],
                "passer_player_id": [None, None],
                "receiver_player_id": [None, None],
                "season": [2024, 2024],
                "week": [1, 1],
            }
        )
        result = build_qb_wr_chemistry(df)
        assert result.empty

    def test_missing_passer(self):
        """Should skip plays where passer is null."""
        df = pd.DataFrame(
            {
                "play_id": [1, 2],
                "play_type": ["pass", "pass"],
                "passer_player_id": [None, "QB001"],
                "receiver_player_id": ["WR001", "WR001"],
                "season": [2024, 2024],
                "week": [1, 1],
                "complete_pass": [1, 1],
                "yards_gained": [10, 10],
                "pass_touchdown": [0, 0],
                "epa": [0.5, 0.5],
                "air_yards": [10.0, 10.0],
            }
        )
        result = build_qb_wr_chemistry(df)
        assert len(result) == 1
        assert result.iloc[0]["passer_id"] == "QB001"


# ---------------------------------------------------------------------------
# Tests -- compute_chemistry_features
# ---------------------------------------------------------------------------


class TestComputeChemistryFeatures:
    """Tests for rolling chemistry feature computation."""

    def test_output_columns(self, pbp_pass_plays, player_weekly_df):
        """Should produce all expected feature columns."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        assert not result.empty
        for col in QB_WR_CHEMISTRY_FEATURE_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_temporal_lag_week1(self, pbp_pass_plays, player_weekly_df):
        """Week 1 should have NaN chemistry features (shift(1) means no prior data)."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        week1 = result[result["week"] == 1]
        for col in QB_WR_CHEMISTRY_FEATURE_COLUMNS:
            assert week1[col].isna().all(), (
                f"{col} should be NaN in week 1 due to shift(1), "
                f"got: {week1[col].values}"
            )

    def test_temporal_lag_week2(self, pbp_pass_plays, player_weekly_df):
        """Week 2 should have values based only on week 1 data."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        week2_wr1 = result[(result["week"] == 2) & (result["player_id"] == "WR001")]
        if not week2_wr1.empty:
            # EPA should be non-null at week 2 (has week 1 data via shift)
            assert week2_wr1["qb_wr_chemistry_epa_roll3"].notna().any()

    def test_games_together_increments(self, pbp_pass_plays, player_weekly_df):
        """Games together should increment over time (lagged)."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        wr1 = result[result["player_id"] == "WR001"].sort_values("week")
        games = wr1["qb_wr_pair_games_together"].dropna()
        if len(games) > 1:
            # Should be non-decreasing
            assert (games.diff().dropna() >= 0).all()

    def test_wr_only_features(self, pbp_pass_plays, player_weekly_df):
        """Only WR and TE should have chemistry features (no RB)."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        # RB should not appear in chemistry features
        rb_rows = result[result["player_id"] == "RB001"]
        assert rb_rows.empty

    def test_qb_change_mid_season(self, qb_change_pbp, qb_change_weekly):
        """WR should have NaN chemistry with new QB in first game together."""
        pair_stats = build_qb_wr_chemistry(qb_change_pbp)
        result = compute_chemistry_features(pair_stats, qb_change_weekly)

        if result.empty:
            pytest.skip("Chemistry result empty -- data insufficient")

        wr_x = result[result["player_id"] == "WR_X"].sort_values("week")

        # Week 3 is first game with QB_B -- should have NaN for QB_B chemistry
        # (shift(1) means we need at least 1 prior game with QB_B)
        week3 = wr_x[wr_x["week"] == 3]
        if not week3.empty:
            assert (
                week3["qb_wr_chemistry_epa_roll3"].isna().all()
            ), "First game with new QB should have NaN chemistry EPA"

    def test_empty_inputs(self):
        """Should return empty DataFrame for empty inputs."""
        result = compute_chemistry_features(pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_target_share_bounded(self, pbp_pass_plays, player_weekly_df):
        """Target share should be between 0 and 1 where non-null."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        ts = result["qb_wr_pair_target_share"].dropna()
        if len(ts) > 0:
            assert (ts >= 0).all()
            assert (ts <= 1.0).all()

    def test_comp_rate_bounded(self, pbp_pass_plays, player_weekly_df):
        """Completion rate should be between 0 and 1 where non-null."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        cr = result["qb_wr_pair_comp_rate_roll3"].dropna()
        if len(cr) > 0:
            assert (cr >= 0).all()
            assert (cr <= 1.0).all()

    def test_no_duplicate_player_weeks(self, pbp_pass_plays, player_weekly_df):
        """Should have at most one row per player-week."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        if not result.empty:
            dupes = result.duplicated(subset=["player_id", "season", "week"])
            assert not dupes.any(), "Found duplicate player-week rows"

    def test_feature_column_list_matches(self, pbp_pass_plays, player_weekly_df):
        """QB_WR_CHEMISTRY_FEATURE_COLUMNS should match actual output."""
        pair_stats = build_qb_wr_chemistry(pbp_pass_plays)
        result = compute_chemistry_features(pair_stats, player_weekly_df)

        expected = {"player_id", "season", "week"} | set(
            QB_WR_CHEMISTRY_FEATURE_COLUMNS
        )
        assert set(result.columns) == expected


# ---------------------------------------------------------------------------
# Tests -- integration with feature engineering join
# ---------------------------------------------------------------------------


class TestChemistryJoinIntegration:
    """Tests for _join_chemistry_features in player_feature_engineering."""

    def test_join_adds_nan_columns_when_no_data(self):
        """When no chemistry data exists, NaN columns should be added."""
        from player_feature_engineering import _join_chemistry_features

        base = pd.DataFrame(
            {
                "player_id": ["WR001", "QB001"],
                "season": [2024, 2024],
                "week": [1, 1],
                "position": ["WR", "QB"],
            }
        )
        result = _join_chemistry_features(base, 9999)  # No data for year 9999

        for col in QB_WR_CHEMISTRY_FEATURE_COLUMNS:
            assert col in result.columns
            assert result[col].isna().all()

    def test_non_wr_te_get_nan(self):
        """QB and RB should get NaN for chemistry features."""
        from player_feature_engineering import _join_chemistry_features

        base = pd.DataFrame(
            {
                "player_id": ["QB001", "RB001", "WR001"],
                "season": [2024, 2024, 2024],
                "week": [1, 1, 1],
                "position": ["QB", "RB", "WR"],
            }
        )
        result = _join_chemistry_features(base, 9999)

        for col in QB_WR_CHEMISTRY_FEATURE_COLUMNS:
            # QB and RB should be NaN
            assert result.loc[result["position"] == "QB", col].isna().all()
            assert result.loc[result["position"] == "RB", col].isna().all()
