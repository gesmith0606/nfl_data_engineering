"""Tests for player_advanced_analytics module.

Covers PROF-01 through PROF-06:
  - NGS receiving, passing, rushing profiles
  - PFR pressure rate (player-level) and team blitz rate
  - QBR profile
  - Rolling window behavior (min_periods=3, no cross-season leakage)
  - Missing column graceful handling
  - NaN coverage logging
"""

import logging

import numpy as np
import pandas as pd
import pytest

from player_advanced_analytics import (
    apply_player_rolling,
    compute_ngs_receiving_profile,
    compute_ngs_passing_profile,
    compute_ngs_rushing_profile,
    compute_pfr_pressure_rate,
    compute_pfr_team_blitz_rate,
    compute_qbr_profile,
    log_nan_coverage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def player_weekly_df():
    """Two players, 2 seasons, 6 weeks each -- enough for rolling verification."""
    rows = []
    for pid in ["P001", "P002"]:
        for season in [2023, 2024]:
            for week in range(1, 7):
                rows.append(
                    {
                        "player_gsis_id": pid,
                        "season": season,
                        "week": week,
                        "stat_a": float(week),
                        "stat_b": float(week * 2),
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def ngs_receiving_df():
    """Synthetic NGS receiving data with week 0 (seasonal aggregate) rows."""
    rows = []
    for pid in ["P001", "P002"]:
        for season in [2023, 2024]:
            # Week 0 = seasonal aggregate (should be filtered)
            rows.append(
                {
                    "player_gsis_id": pid,
                    "season": season,
                    "week": 0,
                    "avg_separation": 3.0,
                    "catch_percentage": 70.0,
                    "avg_intended_air_yards": 10.0,
                    "avg_cushion": 5.0,
                    "avg_yac": 4.0,
                    "avg_expected_yac": 3.5,
                    "avg_yac_above_expectation": 0.5,
                }
            )
            for week in range(1, 7):
                rows.append(
                    {
                        "player_gsis_id": pid,
                        "season": season,
                        "week": week,
                        "avg_separation": 2.5 + week * 0.1,
                        "catch_percentage": 60.0 + week,
                        "avg_intended_air_yards": 8.0 + week * 0.5,
                        "avg_cushion": 4.0 + week * 0.2,
                        "avg_yac": 3.0 + week * 0.3,
                        "avg_expected_yac": 2.8 + week * 0.2,
                        "avg_yac_above_expectation": 0.2 + week * 0.1,
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def ngs_passing_df():
    """Synthetic NGS passing data."""
    rows = []
    for pid in ["QB01"]:
        for season in [2023]:
            for week in range(1, 7):
                rows.append(
                    {
                        "player_gsis_id": pid,
                        "season": season,
                        "week": week,
                        "avg_time_to_throw": 2.5 + week * 0.1,
                        "aggressiveness": 15.0 + week,
                        "avg_completed_air_yards": 5.0 + week * 0.5,
                        "avg_intended_air_yards": 8.0 + week * 0.3,
                        "avg_air_yards_differential": -3.0 + week * 0.2,
                        "completion_percentage_above_expectation": 1.0 + week * 0.5,
                        "expected_completion_percentage": 62.0 + week,
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def ngs_rushing_df():
    """Synthetic NGS rushing data."""
    rows = []
    for pid in ["RB01"]:
        for season in [2023]:
            for week in range(1, 7):
                rows.append(
                    {
                        "player_gsis_id": pid,
                        "season": season,
                        "week": week,
                        "rush_yards_over_expected": 5.0 + week,
                        "rush_yards_over_expected_per_att": 0.5 + week * 0.1,
                        "efficiency": 3.5 + week * 0.2,
                        "avg_time_to_los": 2.0 + week * 0.05,
                        "rush_pct_over_expected": 2.0 + week * 0.3,
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def pfr_pressure_df():
    """Synthetic PFR passing pressure data (player-level)."""
    rows = []
    for pid in ["QB01"]:
        for season in [2023]:
            for week in range(1, 7):
                rows.append(
                    {
                        "player_gsis_id": pid,
                        "player": "Joe QB",
                        "team": "KC",
                        "season": season,
                        "week": week,
                        "times_pressured_pct": 20.0 + week,
                        "times_sacked": 2 + (week % 3),
                        "times_hurried": 3 + week,
                        "times_hit": 1 + (week % 2),
                        "times_blitzed": 5 + week,
                        "passing_bad_throw_pct": 12.0 + week * 0.5,
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def pfr_def_blitz_df():
    """Synthetic PFR defender-level blitz data."""
    rows = []
    for season in [2023]:
        for week in range(1, 7):
            for team in ["KC", "BUF"]:
                # 3 defenders per team per week
                for d in range(3):
                    rows.append(
                        {
                            "team": team,
                            "season": season,
                            "week": week,
                            "def_times_blitzed": 2 + d,
                            "def_times_hurried": 1 + d,
                            "def_sacks": d,
                            "def_pressures": 3 + d,
                        }
                    )
    return pd.DataFrame(rows)


@pytest.fixture
def qbr_df():
    """Synthetic ESPN QBR data."""
    rows = []
    for pid in ["QB01"]:
        for season in [2023]:
            for week in range(1, 7):
                rows.append(
                    {
                        "player_gsis_id": pid,
                        "player": "Joe QB",
                        "team": "KC",
                        "season": season,
                        "week": week,
                        "qbr_total": 55.0 + week * 2,
                        "pts_added": 1.5 + week * 0.5,
                        "qb_plays": 30 + week,
                        "epa_total": 5.0 + week,
                    }
                )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: apply_player_rolling
# ---------------------------------------------------------------------------


class TestApplyPlayerRolling:
    def test_creates_rolling_columns(self, player_weekly_df):
        result = apply_player_rolling(player_weekly_df, ["stat_a", "stat_b"])
        for col in ["stat_a", "stat_b"]:
            assert f"{col}_roll3" in result.columns
            assert f"{col}_roll6" in result.columns
            assert f"{col}_std" in result.columns

    def test_first_three_weeks_nan(self, player_weekly_df):
        """shift(1) + min_periods=3 means weeks 1-3 produce NaN for roll3."""
        result = apply_player_rolling(player_weekly_df, ["stat_a"])
        p1_s2023 = result[
            (result["player_gsis_id"] == "P001") & (result["season"] == 2023)
        ].sort_values("week")
        # Weeks 1, 2, 3: shift(1) gives [NaN, 1, 2], rolling(3, min_periods=3) needs 3 non-NaN
        # Week 1: shift produces NaN -> NaN
        # Week 2: shift produces [NaN, 1.0] -> only 1 value -> NaN
        # Week 3: shift produces [NaN, 1.0, 2.0] -> only 2 values -> NaN
        for week in [1, 2, 3]:
            val = p1_s2023[p1_s2023["week"] == week]["stat_a_roll3"].iloc[0]
            assert pd.isna(val), f"Week {week} roll3 should be NaN, got {val}"

    def test_no_cross_season_leakage(self, player_weekly_df):
        """Week 1 of season 2024 should not see season 2023 data."""
        result = apply_player_rolling(player_weekly_df, ["stat_a"])
        p1_s2024_w1 = result[
            (result["player_gsis_id"] == "P001")
            & (result["season"] == 2024)
            & (result["week"] == 1)
        ]
        assert pd.isna(
            p1_s2024_w1["stat_a_roll3"].iloc[0]
        ), "Season boundary should reset rolling"

    def test_row_count_preserved(self, player_weekly_df):
        result = apply_player_rolling(player_weekly_df, ["stat_a"])
        assert len(result) == len(player_weekly_df)


# ---------------------------------------------------------------------------
# Tests: NGS Receiving
# ---------------------------------------------------------------------------


class TestNgsReceivingProfile:
    def test_column_prefix(self, ngs_receiving_df):
        result = compute_ngs_receiving_profile(ngs_receiving_df)
        ngs_cols = [c for c in result.columns if c.startswith("ngs_")]
        assert len(ngs_cols) > 0, "Should have ngs_ prefixed columns"

    def test_week0_filtered(self, ngs_receiving_df):
        result = compute_ngs_receiving_profile(ngs_receiving_df)
        assert (result["week"] > 0).all(), "Week 0 rows should be filtered out"

    def test_rolling_applied(self, ngs_receiving_df):
        result = compute_ngs_receiving_profile(ngs_receiving_df)
        roll_cols = [c for c in result.columns if "_roll3" in c]
        assert len(roll_cols) > 0, "Rolling columns should be created"

    def test_row_count(self, ngs_receiving_df):
        """Output should have same rows as input minus week 0 rows."""
        expected = len(ngs_receiving_df[ngs_receiving_df["week"] > 0])
        result = compute_ngs_receiving_profile(ngs_receiving_df)
        assert len(result) == expected


# ---------------------------------------------------------------------------
# Tests: NGS Passing
# ---------------------------------------------------------------------------


class TestNgsPassingProfile:
    def test_column_prefix(self, ngs_passing_df):
        result = compute_ngs_passing_profile(ngs_passing_df)
        ngs_cols = [c for c in result.columns if c.startswith("ngs_")]
        assert len(ngs_cols) > 0

    def test_rolling_applied(self, ngs_passing_df):
        result = compute_ngs_passing_profile(ngs_passing_df)
        roll_cols = [c for c in result.columns if "_roll3" in c]
        assert len(roll_cols) > 0


# ---------------------------------------------------------------------------
# Tests: NGS Rushing
# ---------------------------------------------------------------------------


class TestNgsRushingProfile:
    def test_column_prefix(self, ngs_rushing_df):
        result = compute_ngs_rushing_profile(ngs_rushing_df)
        ngs_cols = [c for c in result.columns if c.startswith("ngs_")]
        assert len(ngs_cols) > 0

    def test_rolling_applied(self, ngs_rushing_df):
        result = compute_ngs_rushing_profile(ngs_rushing_df)
        roll_cols = [c for c in result.columns if "_roll3" in c]
        assert len(roll_cols) > 0


# ---------------------------------------------------------------------------
# Tests: PFR Pressure Rate
# ---------------------------------------------------------------------------


class TestPfrPressureRate:
    def test_column_prefix(self, pfr_pressure_df):
        result = compute_pfr_pressure_rate(pfr_pressure_df)
        pfr_cols = [c for c in result.columns if c.startswith("pfr_")]
        assert len(pfr_cols) > 0, "Should have pfr_ prefixed columns"

    def test_rolling_applied(self, pfr_pressure_df):
        result = compute_pfr_pressure_rate(pfr_pressure_df)
        roll_cols = [c for c in result.columns if "_roll3" in c]
        assert len(roll_cols) > 0

    def test_row_count_preserved(self, pfr_pressure_df):
        result = compute_pfr_pressure_rate(pfr_pressure_df)
        assert len(result) == len(pfr_pressure_df)


# ---------------------------------------------------------------------------
# Tests: PFR Team Blitz Rate
# ---------------------------------------------------------------------------


class TestPfrTeamBlitzRate:
    def test_aggregation_to_team_level(self, pfr_def_blitz_df):
        result = compute_pfr_team_blitz_rate(pfr_def_blitz_df)
        # 2 teams * 6 weeks * 1 season = 12 rows
        assert len(result) == 12, f"Expected 12 team-week rows, got {len(result)}"

    def test_column_prefix(self, pfr_def_blitz_df):
        result = compute_pfr_team_blitz_rate(pfr_def_blitz_df)
        pfr_def_cols = [c for c in result.columns if c.startswith("pfr_def_")]
        assert len(pfr_def_cols) > 0, "Should have pfr_def_ prefixed columns"

    def test_sum_aggregation(self, pfr_def_blitz_df):
        """Verify defender-level rows are summed to team level."""
        result = compute_pfr_team_blitz_rate(pfr_def_blitz_df)
        kc_w1 = result[(result["team"] == "KC") & (result["week"] == 1)]
        # 3 defenders: def_times_blitzed = 2+3+4 = 9
        assert kc_w1["pfr_def_times_blitzed"].iloc[0] == 9


# ---------------------------------------------------------------------------
# Tests: QBR Profile
# ---------------------------------------------------------------------------


class TestQbrProfile:
    def test_column_prefix(self, qbr_df):
        result = compute_qbr_profile(qbr_df)
        qbr_cols = [c for c in result.columns if c.startswith("qbr_")]
        assert len(qbr_cols) > 0

    def test_rolling_applied(self, qbr_df):
        result = compute_qbr_profile(qbr_df)
        roll_cols = [c for c in result.columns if "_roll3" in c]
        assert len(roll_cols) > 0

    def test_row_count_preserved(self, qbr_df):
        result = compute_qbr_profile(qbr_df)
        assert len(result) == len(qbr_df)


# ---------------------------------------------------------------------------
# Tests: log_nan_coverage
# ---------------------------------------------------------------------------


class TestLogNanCoverage:
    def test_logs_coverage(self, caplog):
        df = pd.DataFrame(
            {
                "ngs_avg_separation": [1.0, np.nan, 3.0, 4.0],
                "ngs_catch_percentage": [np.nan, np.nan, 70.0, 80.0],
            }
        )
        with caplog.at_level(logging.INFO):
            log_nan_coverage(df, ["ngs_avg_separation", "ngs_catch_percentage"])
        assert "ngs_avg_separation" in caplog.text
        assert "ngs_catch_percentage" in caplog.text


# ---------------------------------------------------------------------------
# Tests: Missing Column Handling
# ---------------------------------------------------------------------------


class TestMissingColumnHandling:
    def test_ngs_receiving_missing_cols(self):
        """Pass DataFrame with none of the expected columns."""
        df = pd.DataFrame(
            {
                "player_gsis_id": ["P1"],
                "season": [2023],
                "week": [1],
                "irrelevant_col": [42],
            }
        )
        result = compute_ngs_receiving_profile(df)
        assert isinstance(result, pd.DataFrame)
        # Should return a DataFrame (possibly empty or with NaN schema)
        assert len(result) >= 0

    def test_ngs_passing_missing_cols(self):
        df = pd.DataFrame(
            {
                "player_gsis_id": ["P1"],
                "season": [2023],
                "week": [1],
            }
        )
        result = compute_ngs_passing_profile(df)
        assert isinstance(result, pd.DataFrame)

    def test_pfr_pressure_missing_cols(self):
        df = pd.DataFrame(
            {
                "player_gsis_id": ["P1"],
                "season": [2023],
                "week": [1],
            }
        )
        result = compute_pfr_pressure_rate(df)
        assert isinstance(result, pd.DataFrame)

    def test_qbr_missing_cols(self):
        df = pd.DataFrame(
            {
                "player_gsis_id": ["P1"],
                "season": [2023],
                "week": [1],
            }
        )
        result = compute_qbr_profile(df)
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Tests: Left-join preservation (row count)
# ---------------------------------------------------------------------------


class TestRowPreservation:
    def test_ngs_receiving_preserves_rows(self, ngs_receiving_df):
        """No silent row drops."""
        input_valid = ngs_receiving_df[ngs_receiving_df["week"] > 0]
        result = compute_ngs_receiving_profile(ngs_receiving_df)
        assert len(result) == len(input_valid)

    def test_pfr_pressure_preserves_rows(self, pfr_pressure_df):
        result = compute_pfr_pressure_rate(pfr_pressure_df)
        assert len(result) == len(pfr_pressure_df)
