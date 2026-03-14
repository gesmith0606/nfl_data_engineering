#!/usr/bin/env python3
"""Unit tests for team_analytics PBP metric and tendency computation functions."""

import pandas as pd
import numpy as np
import pytest
from typing import Dict, List

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.team_analytics import (
    _filter_valid_plays,
    apply_team_rolling,
    compute_team_epa,
    compute_team_success_rate,
    compute_team_cpoe,
    compute_red_zone_metrics,
    compute_pbp_metrics,
    compute_pace,
    compute_proe,
    compute_fourth_down_aggressiveness,
    compute_early_down_run_rate,
    compute_tendency_metrics,
)


def _make_pbp_rows(
    posteam: str,
    defteam: str,
    season: int,
    week: int,
    plays: List[Dict],
) -> pd.DataFrame:
    """Helper to create synthetic PBP rows for a team-week."""
    rows = []
    for i, play in enumerate(plays):
        row = {
            "posteam": posteam,
            "defteam": defteam,
            "season": season,
            "week": week,
            "season_type": "REG",
            "play_type": play.get("play_type", "pass"),
            "epa": play.get("epa", 0.0),
            "success": play.get("success", 0),
            "cpoe": play.get("cpoe", None),
            "pass_attempt": play.get("pass_attempt", 1 if play.get("play_type", "pass") == "pass" else 0),
            "yardline_100": play.get("yardline_100", 50),
            "drive": play.get("drive", 1),
            "touchdown": play.get("touchdown", 0),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _build_two_team_three_week_pbp() -> pd.DataFrame:
    """Build a synthetic PBP DataFrame with 2 teams over 3 weeks.

    Team A on offense vs Team B on defense, and vice versa.
    Known EPA values for deterministic test assertions.
    """
    frames = []

    # Week 1: A offense vs B defense
    frames.append(_make_pbp_rows("A", "B", 2024, 1, [
        {"play_type": "pass", "epa": 0.5, "success": 1, "cpoe": 3.0, "pass_attempt": 1},
        {"play_type": "pass", "epa": -0.3, "success": 0, "cpoe": -2.0, "pass_attempt": 1},
        {"play_type": "run", "epa": 0.2, "success": 1, "cpoe": None, "pass_attempt": 0},
        {"play_type": "run", "epa": -0.1, "success": 0, "cpoe": None, "pass_attempt": 0},
    ]))
    # Week 1: B offense vs A defense
    frames.append(_make_pbp_rows("B", "A", 2024, 1, [
        {"play_type": "pass", "epa": 0.8, "success": 1, "cpoe": 5.0, "pass_attempt": 1},
        {"play_type": "run", "epa": -0.4, "success": 0, "cpoe": None, "pass_attempt": 0},
    ]))

    # Week 2: A offense vs B defense
    frames.append(_make_pbp_rows("A", "B", 2024, 2, [
        {"play_type": "pass", "epa": 0.1, "success": 1, "cpoe": 1.0, "pass_attempt": 1},
        {"play_type": "run", "epa": 0.3, "success": 1, "cpoe": None, "pass_attempt": 0},
    ]))
    # Week 2: B offense vs A defense
    frames.append(_make_pbp_rows("B", "A", 2024, 2, [
        {"play_type": "pass", "epa": -0.2, "success": 0, "cpoe": -1.0, "pass_attempt": 1},
        {"play_type": "pass", "epa": 0.6, "success": 1, "cpoe": 4.0, "pass_attempt": 1},
    ]))

    # Week 3: A offense vs B defense
    frames.append(_make_pbp_rows("A", "B", 2024, 3, [
        {"play_type": "pass", "epa": 0.4, "success": 1, "cpoe": 2.0, "pass_attempt": 1},
        {"play_type": "run", "epa": -0.2, "success": 0, "cpoe": None, "pass_attempt": 0},
    ]))
    # Week 3: B offense vs A defense
    frames.append(_make_pbp_rows("B", "A", 2024, 3, [
        {"play_type": "pass", "epa": 0.3, "success": 1, "cpoe": 2.5, "pass_attempt": 1},
        {"play_type": "run", "epa": 0.1, "success": 1, "cpoe": None, "pass_attempt": 0},
    ]))

    return pd.concat(frames, ignore_index=True)


class TestEPA:
    """Tests for compute_team_epa."""

    def test_returns_one_row_per_team_week(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_epa(valid)

        # 2 teams x 3 weeks = 6 rows
        assert len(result) == 6
        assert set(result.columns) & {"team", "season", "week", "off_epa_per_play", "def_epa_per_play"}

    def test_offense_epa_equals_mean(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_epa(valid)

        # Team A, week 1: plays have EPA [0.5, -0.3, 0.2, -0.1] -> mean = 0.075
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert len(a_w1) == 1
        assert abs(a_w1["off_epa_per_play"].iloc[0] - 0.075) < 1e-6

    def test_defense_epa_equals_opponent_offense(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_epa(valid)

        # Team A's defense in week 1 = when B has ball: EPA [0.8, -0.4] -> mean = 0.2
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["def_epa_per_play"].iloc[0] - 0.2) < 1e-6

    def test_pass_rush_splits(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_epa(valid)

        # Team A, week 1: pass EPA [0.5, -0.3] -> 0.1; rush EPA [0.2, -0.1] -> 0.05
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert "off_pass_epa" in result.columns
        assert "off_rush_epa" in result.columns
        assert abs(a_w1["off_pass_epa"].iloc[0] - 0.1) < 1e-6
        assert abs(a_w1["off_rush_epa"].iloc[0] - 0.05) < 1e-6


class TestSuccessRate:
    """Tests for compute_team_success_rate."""

    def test_offense_success_rate(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_success_rate(valid)

        # Team A, week 1: success [1, 0, 1, 0] -> 0.5
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["off_success_rate"].iloc[0] - 0.5) < 1e-6

    def test_defense_success_rate(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_success_rate(valid)

        # Team A's defense in week 1 = B offense: success [1, 0] -> 0.5
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["def_success_rate"].iloc[0] - 0.5) < 1e-6

    def test_returns_all_team_weeks(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_success_rate(valid)
        assert len(result) == 6


class TestCPOE:
    """Tests for compute_team_cpoe."""

    def test_cpoe_excludes_nan(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_cpoe(valid)

        # Team A, week 1: cpoe [3.0, -2.0, NaN, NaN] -> only [3.0, -2.0] -> mean = 0.5
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["off_cpoe"].iloc[0] - 0.5) < 1e-6

    def test_cpoe_is_offense_only(self):
        pbp = _build_two_team_three_week_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_team_cpoe(valid)

        # CPOE is offense-only: no def_cpoe column
        assert "def_cpoe" not in result.columns
        assert "off_cpoe" in result.columns


class TestRedZone:
    """Tests for compute_red_zone_metrics."""

    def _make_rz_pbp(self) -> pd.DataFrame:
        """Create PBP with known red zone plays across 2 drives."""
        frames = []
        # Team A offense, week 1: 2 drives enter RZ
        # Drive 1: 3 RZ plays, 1 TD
        frames.append(_make_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.5, "success": 1, "cpoe": 1.0,
             "pass_attempt": 1, "yardline_100": 15, "drive": 1, "touchdown": 0},
            {"play_type": "run", "epa": 0.3, "success": 1, "cpoe": None,
             "pass_attempt": 0, "yardline_100": 10, "drive": 1, "touchdown": 0},
            {"play_type": "pass", "epa": 1.5, "success": 1, "cpoe": 5.0,
             "pass_attempt": 1, "yardline_100": 5, "drive": 1, "touchdown": 1},
        ]))
        # Drive 2: 2 RZ plays, 0 TDs
        frames.append(_make_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": -0.2, "success": 0, "cpoe": -3.0,
             "pass_attempt": 1, "yardline_100": 18, "drive": 2, "touchdown": 0},
            {"play_type": "run", "epa": -0.5, "success": 0, "cpoe": None,
             "pass_attempt": 0, "yardline_100": 20, "drive": 2, "touchdown": 0},
        ]))
        # Non-RZ plays (should be excluded from RZ metrics)
        frames.append(_make_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.1, "success": 1, "cpoe": 2.0,
             "pass_attempt": 1, "yardline_100": 50, "drive": 3, "touchdown": 0},
        ]))

        # Team B offense (for defense RZ stats for A)
        frames.append(_make_pbp_rows("B", "A", 2024, 1, [
            {"play_type": "pass", "epa": 0.8, "success": 1, "cpoe": 4.0,
             "pass_attempt": 1, "yardline_100": 12, "drive": 4, "touchdown": 1},
        ]))

        return pd.concat(frames, ignore_index=True)

    def test_td_rate_uses_drive_denominator(self):
        pbp = self._make_rz_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_red_zone_metrics(valid)

        # Team A offense RZ: 1 TD across 2 drives -> td_rate = 0.5
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["off_rz_td_rate"].iloc[0] - 0.5) < 1e-6

    def test_rz_columns_exist(self):
        pbp = self._make_rz_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_red_zone_metrics(valid)

        expected_cols = [
            "off_rz_epa", "off_rz_success_rate", "off_rz_pass_rate", "off_rz_td_rate",
            "def_rz_epa", "def_rz_success_rate", "def_rz_pass_rate", "def_rz_td_rate",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_defense_rz_metrics(self):
        pbp = self._make_rz_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_red_zone_metrics(valid)

        # Team A defense RZ: B's plays at yard_100<=20 -> 1 play, 1 TD, 1 drive -> td_rate = 1.0
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["def_rz_td_rate"].iloc[0] - 1.0) < 1e-6

    def test_rz_success_rate(self):
        pbp = self._make_rz_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_red_zone_metrics(valid)

        # Team A offense RZ: success [1,1,1,0,0] -> 3/5 = 0.6
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["off_rz_success_rate"].iloc[0] - 0.6) < 1e-6

    def test_rz_pass_rate(self):
        pbp = self._make_rz_pbp()
        valid = _filter_valid_plays(pbp)
        result = compute_red_zone_metrics(valid)

        # Team A offense RZ: pass_attempt [1,0,1,1,0] -> 3/5 = 0.6
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert abs(a_w1["off_rz_pass_rate"].iloc[0] - 0.6) < 1e-6


class TestRedZoneZeroTrips:
    """Test that teams with no RZ plays get NaN metrics."""

    def test_no_rz_plays_gives_nan(self):
        # All plays at yardline_100 > 20
        pbp = _make_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.5, "success": 1, "cpoe": 2.0,
             "pass_attempt": 1, "yardline_100": 50, "drive": 1, "touchdown": 0},
        ])
        valid = _filter_valid_plays(pbp)
        result = compute_red_zone_metrics(valid)

        # Team A should have NaN RZ metrics (no RZ plays)
        if len(result) > 0:
            a_row = result[result["team"] == "A"]
            if len(a_row) > 0:
                assert pd.isna(a_row["off_rz_td_rate"].iloc[0])
            else:
                # No rows for team A is also acceptable (empty DataFrame)
                pass
        else:
            # Empty result is acceptable
            pass


def _build_six_week_single_team_pbp() -> pd.DataFrame:
    """Build 6 weeks of PBP for a single team with known EPA values."""
    epa_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    frames = []
    for week, epa_val in enumerate(epa_values, start=1):
        # Team X on offense vs Y defense, 2 plays per week
        frames.append(_make_pbp_rows("X", "Y", 2024, week, [
            {"play_type": "pass", "epa": epa_val, "success": 1,
             "cpoe": epa_val * 10, "pass_attempt": 1},
            {"play_type": "run", "epa": epa_val - 0.05, "success": 0,
             "cpoe": None, "pass_attempt": 0},
        ]))
        # Y on offense vs X defense (so X has defense stats too)
        frames.append(_make_pbp_rows("Y", "X", 2024, week, [
            {"play_type": "pass", "epa": -epa_val, "success": 0,
             "cpoe": -epa_val * 5, "pass_attempt": 1},
        ]))
    return pd.concat(frames, ignore_index=True)


class TestPBPRolling:
    """Integration tests for rolling window behavior on PBP metrics."""

    def test_week1_rolling_is_nan(self):
        """Week 1 rolling values should be NaN (no prior data)."""
        pbp = _build_six_week_single_team_pbp()
        result = compute_pbp_metrics(pbp)

        x_w1 = result[(result["team"] == "X") & (result["week"] == 1)]
        assert len(x_w1) == 1
        assert pd.isna(x_w1["off_epa_per_play_roll3"].iloc[0])
        assert pd.isna(x_w1["off_epa_per_play_roll6"].iloc[0])
        assert pd.isna(x_w1["off_epa_per_play_std"].iloc[0])

    def test_week2_roll3_equals_week1_raw(self):
        """Week 2 roll3 should equal week 1 raw value (shift(1) + 1 data point)."""
        pbp = _build_six_week_single_team_pbp()
        result = compute_pbp_metrics(pbp)

        x_w1 = result[(result["team"] == "X") & (result["week"] == 1)]
        x_w2 = result[(result["team"] == "X") & (result["week"] == 2)]

        w1_raw = x_w1["off_epa_per_play"].iloc[0]
        w2_roll3 = x_w2["off_epa_per_play_roll3"].iloc[0]
        assert abs(w2_roll3 - w1_raw) < 1e-6

    def test_week4_roll3_equals_mean_weeks1_to_3(self):
        """Week 4 roll3 should be mean of weeks 1-3 raw values."""
        pbp = _build_six_week_single_team_pbp()
        result = compute_pbp_metrics(pbp)

        x = result[result["team"] == "X"].sort_values("week")
        raw_w1_to_w3 = x[x["week"].isin([1, 2, 3])]["off_epa_per_play"].values
        expected_roll3 = np.mean(raw_w1_to_w3)

        w4_roll3 = x[x["week"] == 4]["off_epa_per_play_roll3"].iloc[0]
        assert abs(w4_roll3 - expected_roll3) < 1e-6

    def test_week4_roll6_equals_mean_weeks1_to_3(self):
        """Week 4 roll6 with only 3 prior points (min_periods=1) = mean of weeks 1-3."""
        pbp = _build_six_week_single_team_pbp()
        result = compute_pbp_metrics(pbp)

        x = result[result["team"] == "X"].sort_values("week")
        raw_w1_to_w3 = x[x["week"].isin([1, 2, 3])]["off_epa_per_play"].values
        expected_roll6 = np.mean(raw_w1_to_w3)

        w4_roll6 = x[x["week"] == 4]["off_epa_per_play_roll6"].iloc[0]
        assert abs(w4_roll6 - expected_roll6) < 1e-6

    def test_week4_std_equals_mean_weeks1_to_3(self):
        """Week 4 STD (expanding average) should equal mean of weeks 1-3."""
        pbp = _build_six_week_single_team_pbp()
        result = compute_pbp_metrics(pbp)

        x = result[result["team"] == "X"].sort_values("week")
        raw_w1_to_w3 = x[x["week"].isin([1, 2, 3])]["off_epa_per_play"].values
        expected_std = np.mean(raw_w1_to_w3)

        w4_std = x[x["week"] == 4]["off_epa_per_play_std"].iloc[0]
        assert abs(w4_std - expected_std) < 1e-6


class TestPBPCrossSeason:
    """Test that rolling windows reset at season boundaries."""

    def test_new_season_week1_rolling_is_nan(self):
        """2024 week 1 rolling values should be NaN even if 2023 data exists."""
        frames = []
        # 2023 weeks 16-18
        for week in [16, 17, 18]:
            frames.append(_make_pbp_rows("X", "Y", 2023, week, [
                {"play_type": "pass", "epa": 0.5, "success": 1, "cpoe": 3.0, "pass_attempt": 1},
                {"play_type": "run", "epa": 0.3, "success": 1, "cpoe": None, "pass_attempt": 0},
            ]))
            frames.append(_make_pbp_rows("Y", "X", 2023, week, [
                {"play_type": "pass", "epa": -0.2, "success": 0, "cpoe": -1.0, "pass_attempt": 1},
            ]))
        # 2024 weeks 1-3
        for week in [1, 2, 3]:
            frames.append(_make_pbp_rows("X", "Y", 2024, week, [
                {"play_type": "pass", "epa": 0.8, "success": 1, "cpoe": 5.0, "pass_attempt": 1},
                {"play_type": "run", "epa": 0.1, "success": 0, "cpoe": None, "pass_attempt": 0},
            ]))
            frames.append(_make_pbp_rows("Y", "X", 2024, week, [
                {"play_type": "pass", "epa": -0.3, "success": 0, "cpoe": -2.0, "pass_attempt": 1},
            ]))

        pbp = pd.concat(frames, ignore_index=True)
        result = compute_pbp_metrics(pbp)

        # 2024 week 1 rolling should be NaN (no cross-season leakage)
        x_2024_w1 = result[
            (result["team"] == "X") & (result["season"] == 2024) & (result["week"] == 1)
        ]
        assert len(x_2024_w1) == 1
        assert pd.isna(x_2024_w1["off_epa_per_play_roll3"].iloc[0])
        assert pd.isna(x_2024_w1["off_epa_per_play_std"].iloc[0])

    def test_new_season_week2_uses_only_current_season(self):
        """2024 week 2 roll3 should only use 2024 week 1 data."""
        frames = []
        # 2023 weeks 16-18 with different EPA
        for week in [16, 17, 18]:
            frames.append(_make_pbp_rows("X", "Y", 2023, week, [
                {"play_type": "pass", "epa": 0.5, "success": 1, "cpoe": 3.0, "pass_attempt": 1},
            ]))
            frames.append(_make_pbp_rows("Y", "X", 2023, week, [
                {"play_type": "pass", "epa": -0.2, "success": 0, "cpoe": -1.0, "pass_attempt": 1},
            ]))
        # 2024 weeks 1-3 with distinct EPA
        epa_2024 = [0.8, 0.6, 0.4]
        for week, epa_val in zip([1, 2, 3], epa_2024):
            frames.append(_make_pbp_rows("X", "Y", 2024, week, [
                {"play_type": "pass", "epa": epa_val, "success": 1, "cpoe": 5.0, "pass_attempt": 1},
            ]))
            frames.append(_make_pbp_rows("Y", "X", 2024, week, [
                {"play_type": "pass", "epa": -0.3, "success": 0, "cpoe": -2.0, "pass_attempt": 1},
            ]))

        pbp = pd.concat(frames, ignore_index=True)
        result = compute_pbp_metrics(pbp)

        x_2024_w1 = result[
            (result["team"] == "X") & (result["season"] == 2024) & (result["week"] == 1)
        ]
        x_2024_w2 = result[
            (result["team"] == "X") & (result["season"] == 2024) & (result["week"] == 2)
        ]

        # Week 2 roll3 should equal week 1 raw value (only 1 prior data point in 2024)
        w1_raw = x_2024_w1["off_epa_per_play"].iloc[0]
        w2_roll3 = x_2024_w2["off_epa_per_play_roll3"].iloc[0]
        assert abs(w2_roll3 - w1_raw) < 1e-6


# ---------------------------------------------------------------------------
# Tendency Metric Tests (Plan 03)
# ---------------------------------------------------------------------------


def _make_tendency_pbp_rows(
    posteam: str,
    defteam: str,
    season: int,
    week: int,
    plays: List[Dict],
) -> pd.DataFrame:
    """Helper to create synthetic PBP rows with tendency-relevant columns."""
    rows = []
    for play in plays:
        row = {
            "posteam": posteam,
            "defteam": defteam,
            "season": season,
            "week": week,
            "season_type": play.get("season_type", "REG"),
            "play_type": play.get("play_type", "pass"),
            "epa": play.get("epa", 0.0),
            "success": play.get("success", 0),
            "cpoe": play.get("cpoe", None),
            "pass_attempt": play.get("pass_attempt", 1 if play.get("play_type", "pass") == "pass" else 0),
            "rush_attempt": play.get("rush_attempt", 1 if play.get("play_type", "pass") == "run" else 0),
            "xpass": play.get("xpass", None),
            "down": play.get("down", 1),
            "fourth_down_converted": play.get("fourth_down_converted", 0),
            "fourth_down_failed": play.get("fourth_down_failed", 0),
            "yardline_100": play.get("yardline_100", 50),
            "drive": play.get("drive", 1),
            "touchdown": play.get("touchdown", 0),
        }
        rows.append(row)
    return pd.DataFrame(rows)


class TestPace:
    """Tests for compute_pace."""

    def test_pace_counts_pass_run_plays(self):
        """Pace should equal count of pass+run plays per team-week."""
        valid = _filter_valid_plays(
            _make_tendency_pbp_rows("A", "B", 2024, 1, [
                {"play_type": "pass", "epa": 0.1, "pass_attempt": 1, "rush_attempt": 0},
                {"play_type": "pass", "epa": 0.2, "pass_attempt": 1, "rush_attempt": 0},
                {"play_type": "run", "epa": -0.1, "pass_attempt": 0, "rush_attempt": 1},
            ])
        )
        result = compute_pace(valid)
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert len(a_w1) == 1
        assert a_w1["pace"].iloc[0] == 3

    def test_pace_per_team_week(self):
        """Different teams should have independent pace counts."""
        frames = []
        # Team A: 4 plays
        frames.append(_make_tendency_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.1}, {"play_type": "run", "epa": 0.1},
            {"play_type": "pass", "epa": 0.1}, {"play_type": "run", "epa": 0.1},
        ]))
        # Team B: 2 plays
        frames.append(_make_tendency_pbp_rows("B", "A", 2024, 1, [
            {"play_type": "pass", "epa": 0.1}, {"play_type": "run", "epa": 0.1},
        ]))
        valid = _filter_valid_plays(pd.concat(frames, ignore_index=True))
        result = compute_pace(valid)
        assert result[result["team"] == "A"]["pace"].iloc[0] == 4
        assert result[result["team"] == "B"]["pace"].iloc[0] == 2

    def test_pace_columns(self):
        """Result should have team, season, week, pace columns."""
        valid = _filter_valid_plays(
            _make_tendency_pbp_rows("A", "B", 2024, 1, [
                {"play_type": "pass", "epa": 0.1},
            ])
        )
        result = compute_pace(valid)
        assert set(result.columns) == {"team", "season", "week", "pace"}


class TestPROE:
    """Tests for compute_proe."""

    def test_proe_basic(self):
        """PROE = actual_pass_rate - mean(xpass)."""
        valid = _filter_valid_plays(
            _make_tendency_pbp_rows("A", "B", 2024, 1, [
                {"play_type": "pass", "epa": 0.1, "pass_attempt": 1, "rush_attempt": 0, "xpass": 0.6},
                {"play_type": "pass", "epa": 0.2, "pass_attempt": 1, "rush_attempt": 0, "xpass": 0.7},
                {"play_type": "run", "epa": -0.1, "pass_attempt": 0, "rush_attempt": 1, "xpass": 0.5},
            ])
        )
        result = compute_proe(valid)
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        # actual_pass_rate = 2/3 = 0.6667
        # mean_xpass = (0.6 + 0.7 + 0.5) / 3 = 0.6
        # proe = 0.6667 - 0.6 = 0.0667
        expected_proe = (2.0 / 3.0) - 0.6
        assert abs(a_w1["proe"].iloc[0] - expected_proe) < 1e-4

    def test_proe_xpass_nan_excluded_from_mean(self):
        """NaN xpass rows excluded from mean(xpass) but included in total play count."""
        valid = _filter_valid_plays(
            _make_tendency_pbp_rows("A", "B", 2024, 1, [
                {"play_type": "pass", "epa": 0.1, "pass_attempt": 1, "rush_attempt": 0, "xpass": 0.5},
                {"play_type": "pass", "epa": 0.2, "pass_attempt": 1, "rush_attempt": 0, "xpass": None},
                {"play_type": "run", "epa": -0.1, "pass_attempt": 0, "rush_attempt": 1, "xpass": 0.4},
            ])
        )
        result = compute_proe(valid)
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        # actual_pass_rate = 2/3 = 0.6667
        # mean_xpass = (0.5 + 0.4) / 2 = 0.45 (NaN excluded by pandas mean)
        expected_proe = (2.0 / 3.0) - 0.45
        assert abs(a_w1["proe"].iloc[0] - expected_proe) < 1e-4

    def test_proe_columns(self):
        """Result should have team, season, week, proe columns."""
        valid = _filter_valid_plays(
            _make_tendency_pbp_rows("A", "B", 2024, 1, [
                {"play_type": "pass", "epa": 0.1, "xpass": 0.5},
            ])
        )
        result = compute_proe(valid)
        assert set(result.columns) == {"team", "season", "week", "proe"}


class TestFourthDown:
    """Tests for compute_fourth_down_aggressiveness."""

    def test_go_rate(self):
        """Go rate = (pass+run on 4th) / (pass+run+punt+FG on 4th)."""
        pbp = _make_tendency_pbp_rows("A", "B", 2024, 1, [
            # 4th down plays
            {"play_type": "pass", "epa": 0.5, "down": 4, "fourth_down_converted": 1, "fourth_down_failed": 0},
            {"play_type": "run", "epa": -0.2, "down": 4, "fourth_down_converted": 0, "fourth_down_failed": 1},
            {"play_type": "punt", "epa": 0.0, "down": 4, "fourth_down_converted": 0, "fourth_down_failed": 0},
            {"play_type": "field_goal", "epa": 0.0, "down": 4, "fourth_down_converted": 0, "fourth_down_failed": 0},
            # Non-4th-down plays (should be ignored)
            {"play_type": "pass", "epa": 0.1, "down": 1},
            {"play_type": "run", "epa": 0.2, "down": 2},
        ])
        result = compute_fourth_down_aggressiveness(pbp)
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        # go_rate = 2 / 4 = 0.5
        assert abs(a_w1["fourth_down_go_rate"].iloc[0] - 0.5) < 1e-6

    def test_success_rate(self):
        """Success rate = converted / (converted + failed) on go attempts."""
        pbp = _make_tendency_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.5, "down": 4, "fourth_down_converted": 1, "fourth_down_failed": 0},
            {"play_type": "run", "epa": -0.2, "down": 4, "fourth_down_converted": 0, "fourth_down_failed": 1},
            {"play_type": "punt", "epa": 0.0, "down": 4},
        ])
        result = compute_fourth_down_aggressiveness(pbp)
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        # success_rate = 1 / (1 + 1) = 0.5
        assert abs(a_w1["fourth_down_success_rate"].iloc[0] - 0.5) < 1e-6

    def test_zero_attempts_gives_nan(self):
        """Team with zero 4th down attempts in a week gets NaN."""
        pbp = _make_tendency_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.1, "down": 1},
            {"play_type": "run", "epa": 0.2, "down": 2},
        ])
        result = compute_fourth_down_aggressiveness(pbp)
        # Team A has no 4th down plays, should be absent or NaN
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        if len(a_w1) > 0:
            assert pd.isna(a_w1["fourth_down_go_rate"].iloc[0])
        else:
            # No row is also acceptable
            pass

    def test_fourth_down_columns(self):
        """Result should have correct columns."""
        pbp = _make_tendency_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.5, "down": 4, "fourth_down_converted": 1, "fourth_down_failed": 0},
            {"play_type": "punt", "epa": 0.0, "down": 4},
        ])
        result = compute_fourth_down_aggressiveness(pbp)
        expected = {"team", "season", "week", "fourth_down_go_rate", "fourth_down_success_rate"}
        assert expected.issubset(set(result.columns))


class TestEarlyDownRunRate:
    """Tests for compute_early_down_run_rate."""

    def test_early_down_uses_down_le_2(self):
        """Early-down run rate uses only down <= 2 plays."""
        valid = _filter_valid_plays(
            _make_tendency_pbp_rows("A", "B", 2024, 1, [
                # Early downs (1 and 2)
                {"play_type": "run", "epa": 0.1, "down": 1, "pass_attempt": 0, "rush_attempt": 1},
                {"play_type": "run", "epa": 0.2, "down": 2, "pass_attempt": 0, "rush_attempt": 1},
                {"play_type": "pass", "epa": 0.3, "down": 1, "pass_attempt": 1, "rush_attempt": 0},
                # Late downs (3 and 4) -- should be excluded
                {"play_type": "run", "epa": -0.1, "down": 3, "pass_attempt": 0, "rush_attempt": 1},
                {"play_type": "pass", "epa": -0.2, "down": 4, "pass_attempt": 1, "rush_attempt": 0},
            ])
        )
        result = compute_early_down_run_rate(valid)
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        # Early-down plays: down 1 run, down 2 run, down 1 pass -> 3 plays
        # Rush attempts on early downs = 2
        # early_down_run_rate = 2/3 = 0.6667
        assert abs(a_w1["early_down_run_rate"].iloc[0] - (2.0 / 3.0)) < 1e-4

    def test_early_down_columns(self):
        """Result should have team, season, week, early_down_run_rate columns."""
        valid = _filter_valid_plays(
            _make_tendency_pbp_rows("A", "B", 2024, 1, [
                {"play_type": "run", "epa": 0.1, "down": 1, "pass_attempt": 0, "rush_attempt": 1},
            ])
        )
        result = compute_early_down_run_rate(valid)
        assert set(result.columns) == {"team", "season", "week", "early_down_run_rate"}


class TestTendencyMetricsOrchestrator:
    """Tests for compute_tendency_metrics orchestrator."""

    def test_tendency_metrics_has_all_columns(self):
        """Orchestrator should produce all tendency columns plus rolling variants."""
        frames = []
        for week in range(1, 4):
            frames.append(_make_tendency_pbp_rows("A", "B", 2024, week, [
                {"play_type": "pass", "epa": 0.1, "down": 1, "pass_attempt": 1, "rush_attempt": 0, "xpass": 0.6},
                {"play_type": "run", "epa": 0.2, "down": 2, "pass_attempt": 0, "rush_attempt": 1, "xpass": 0.4},
                {"play_type": "pass", "epa": 0.3, "down": 4, "pass_attempt": 1, "rush_attempt": 0,
                 "fourth_down_converted": 1, "fourth_down_failed": 0},
                {"play_type": "punt", "epa": 0.0, "down": 4},
            ]))
            frames.append(_make_tendency_pbp_rows("B", "A", 2024, week, [
                {"play_type": "pass", "epa": -0.1, "down": 1, "pass_attempt": 1, "rush_attempt": 0, "xpass": 0.5},
                {"play_type": "run", "epa": -0.2, "down": 2, "pass_attempt": 0, "rush_attempt": 1, "xpass": 0.5},
            ]))
        pbp = pd.concat(frames, ignore_index=True)
        result = compute_tendency_metrics(pbp)

        # Base columns should exist
        for col in ["pace", "proe", "fourth_down_go_rate", "fourth_down_success_rate", "early_down_run_rate"]:
            assert col in result.columns, f"Missing column: {col}"

        # Rolling columns should exist
        for col in ["pace", "proe", "early_down_run_rate"]:
            assert f"{col}_roll3" in result.columns, f"Missing {col}_roll3"
            assert f"{col}_roll6" in result.columns, f"Missing {col}_roll6"
            assert f"{col}_std" in result.columns, f"Missing {col}_std"

    def test_tendency_week1_rolling_is_nan(self):
        """Week 1 rolling values should be NaN (no prior data)."""
        frames = []
        for week in range(1, 4):
            frames.append(_make_tendency_pbp_rows("A", "B", 2024, week, [
                {"play_type": "pass", "epa": 0.1, "down": 1, "pass_attempt": 1, "rush_attempt": 0, "xpass": 0.6},
                {"play_type": "run", "epa": 0.2, "down": 2, "pass_attempt": 0, "rush_attempt": 1, "xpass": 0.4},
            ]))
            frames.append(_make_tendency_pbp_rows("B", "A", 2024, week, [
                {"play_type": "pass", "epa": -0.1, "down": 1, "pass_attempt": 1, "rush_attempt": 0, "xpass": 0.5},
            ]))
        pbp = pd.concat(frames, ignore_index=True)
        result = compute_tendency_metrics(pbp)

        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert len(a_w1) == 1
        assert pd.isna(a_w1["pace_roll3"].iloc[0])
        assert pd.isna(a_w1["pace_std"].iloc[0])
