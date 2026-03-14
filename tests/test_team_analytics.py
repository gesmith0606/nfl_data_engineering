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

from src.team_analytics import _build_opponent_schedule, compute_sos_metrics, compute_situational_splits
from src.config import TEAM_DIVISIONS


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


# ---------------------------------------------------------------------------
# Config SOS Tests (Plan 16-01)
# ---------------------------------------------------------------------------


class TestConfigSOS:
    """Tests for TEAM_DIVISIONS and SILVER_TEAM_S3_KEYS SOS entries."""

    def test_team_divisions_has_32_teams(self):
        from src.config import TEAM_DIVISIONS
        assert len(TEAM_DIVISIONS) == 32

    def test_team_divisions_8_divisions_4_teams_each(self):
        from src.config import TEAM_DIVISIONS
        from collections import Counter
        division_counts = Counter(TEAM_DIVISIONS.values())
        assert len(division_counts) == 8, f"Expected 8 divisions, got {len(division_counts)}"
        for div, count in division_counts.items():
            assert count == 4, f"Division {div} has {count} teams, expected 4"

    def test_silver_team_s3_keys_has_sos(self):
        from src.config import SILVER_TEAM_S3_KEYS
        assert "sos" in SILVER_TEAM_S3_KEYS

    def test_silver_team_s3_keys_has_situational(self):
        from src.config import SILVER_TEAM_S3_KEYS
        assert "situational" in SILVER_TEAM_S3_KEYS


# ---------------------------------------------------------------------------
# SOS Test Fixture and Tests (Plan 16-01)
# ---------------------------------------------------------------------------


def _build_four_team_three_week_sos_pbp() -> pd.DataFrame:
    """Build a synthetic PBP DataFrame with 4 teams over 3 weeks.

    Schedule:
        Week 1: A vs B, C vs D
        Week 2: A vs C, B vs D
        Week 3: A vs D, B vs C

    Each team plays one game per week with deterministic EPA values.
    EPA values are set so that SOS calculations produce predictable results.

    Team A offense EPA: W1=0.10, W2=0.20, W3=0.30
    Team B offense EPA: W1=0.40, W2=-0.10, W3=0.50
    Team C offense EPA: W1=0.60, W2=-0.20, W3=0.10
    Team D offense EPA: W1=-0.30, W2=0.80, W3=-0.40
    """
    frames = []

    # Week 1: A vs B
    frames.append(_make_pbp_rows("A", "B", 2024, 1, [
        {"play_type": "pass", "epa": 0.10, "success": 1},
        {"play_type": "run", "epa": 0.10, "success": 1},
    ]))
    frames.append(_make_pbp_rows("B", "A", 2024, 1, [
        {"play_type": "pass", "epa": 0.40, "success": 1},
        {"play_type": "run", "epa": 0.40, "success": 1},
    ]))

    # Week 1: C vs D
    frames.append(_make_pbp_rows("C", "D", 2024, 1, [
        {"play_type": "pass", "epa": 0.60, "success": 1},
        {"play_type": "run", "epa": 0.60, "success": 1},
    ]))
    frames.append(_make_pbp_rows("D", "C", 2024, 1, [
        {"play_type": "pass", "epa": -0.30, "success": 0},
        {"play_type": "run", "epa": -0.30, "success": 0},
    ]))

    # Week 2: A vs C
    frames.append(_make_pbp_rows("A", "C", 2024, 2, [
        {"play_type": "pass", "epa": 0.20, "success": 1},
        {"play_type": "run", "epa": 0.20, "success": 1},
    ]))
    frames.append(_make_pbp_rows("C", "A", 2024, 2, [
        {"play_type": "pass", "epa": -0.20, "success": 0},
        {"play_type": "run", "epa": -0.20, "success": 0},
    ]))

    # Week 2: B vs D
    frames.append(_make_pbp_rows("B", "D", 2024, 2, [
        {"play_type": "pass", "epa": -0.10, "success": 0},
        {"play_type": "run", "epa": -0.10, "success": 0},
    ]))
    frames.append(_make_pbp_rows("D", "B", 2024, 2, [
        {"play_type": "pass", "epa": 0.80, "success": 1},
        {"play_type": "run", "epa": 0.80, "success": 1},
    ]))

    # Week 3: A vs D
    frames.append(_make_pbp_rows("A", "D", 2024, 3, [
        {"play_type": "pass", "epa": 0.30, "success": 1},
        {"play_type": "run", "epa": 0.30, "success": 1},
    ]))
    frames.append(_make_pbp_rows("D", "A", 2024, 3, [
        {"play_type": "pass", "epa": -0.40, "success": 0},
        {"play_type": "run", "epa": -0.40, "success": 0},
    ]))

    # Week 3: B vs C
    frames.append(_make_pbp_rows("B", "C", 2024, 3, [
        {"play_type": "pass", "epa": 0.50, "success": 1},
        {"play_type": "run", "epa": 0.50, "success": 1},
    ]))
    frames.append(_make_pbp_rows("C", "B", 2024, 3, [
        {"play_type": "pass", "epa": 0.10, "success": 1},
        {"play_type": "run", "epa": 0.10, "success": 1},
    ]))

    pbp = pd.concat(frames, ignore_index=True)
    # Add game_id column for opponent schedule extraction
    pbp["game_id"] = pbp.apply(
        lambda r: f"{r['season']}_{r['week']:02d}_{'_'.join(sorted([r['posteam'], r['defteam']]))}",
        axis=1,
    )
    # Add home/away and score_differential for Plan 02 compatibility
    pbp["home_team"] = pbp["posteam"]
    pbp["away_team"] = pbp["defteam"]
    pbp["score_differential"] = 0.0
    return pbp


class TestSOS:
    """Tests for SOS (Strength of Schedule) computation."""

    def test_week1_adj_equals_raw(self):
        """Week 1 adjusted EPA should equal raw EPA since no opponents faced yet."""
        pbp = _build_four_team_three_week_sos_pbp()
        result = compute_sos_metrics(pbp)

        # Team A week 1: raw off_epa = 0.10, adj_off_epa should == raw
        a_w1 = result[(result["team"] == "A") & (result["week"] == 1)]
        assert len(a_w1) == 1
        assert abs(a_w1["adj_off_epa"].iloc[0] - 0.10) < 1e-6
        assert abs(a_w1["adj_def_epa"].iloc[0] - 0.40) < 1e-6  # B's off EPA is A's def EPA
        # SOS score should be NaN for week 1
        assert pd.isna(a_w1["off_sos_score"].iloc[0])
        assert pd.isna(a_w1["def_sos_score"].iloc[0])

    def test_lagged_opponent_adjustment(self):
        """Week 2+ adj_off_epa should subtract mean opponents' DEF EPA from weeks < current."""
        pbp = _build_four_team_three_week_sos_pbp()
        result = compute_sos_metrics(pbp)

        # Team A week 2: played B in W1.
        # off_sos = mean of B's def_epa in W1 = B's def EPA W1
        # B's def EPA W1 = mean EPA when B is defteam = A's off plays EPA = 0.10
        # So A's off_sos_score = 0.10
        # A's raw off_epa W2 = 0.20
        # adj_off_epa = 0.20 - 0.10 = 0.10
        a_w2 = result[(result["team"] == "A") & (result["week"] == 2)]
        assert len(a_w2) == 1
        assert abs(a_w2["off_sos_score"].iloc[0] - 0.10) < 1e-6
        assert abs(a_w2["adj_off_epa"].iloc[0] - 0.10) < 1e-6

    def test_sos_ranking(self):
        """SOS rankings should be 1-N integers with rank 1 = hardest schedule."""
        pbp = _build_four_team_three_week_sos_pbp()
        result = compute_sos_metrics(pbp)

        # Week 2 should have 4 teams with ranks 1-4
        w2 = result[result["week"] == 2]
        assert len(w2) == 4
        off_ranks = sorted(w2["off_sos_rank"].dropna().tolist())
        # Should be 1.0, 2.0, 3.0, 4.0 (or with ties)
        assert min(off_ranks) == 1.0
        assert max(off_ranks) <= 4.0

        # Week 1 should have NaN ranks (SOS score is NaN)
        w1 = result[result["week"] == 1]
        assert w1["off_sos_rank"].isna().all()

    def test_sos_separate_offense_defense(self):
        """Off SOS uses opponents' DEF EPA; def SOS uses opponents' OFF EPA."""
        pbp = _build_four_team_three_week_sos_pbp()
        result = compute_sos_metrics(pbp)

        # Team A week 2: played B in W1
        # off_sos = B's def_epa W1 = 0.10 (when B was on defense against A)
        # def_sos = B's off_epa W1 = 0.40 (when B was on offense against A)
        a_w2 = result[(result["team"] == "A") & (result["week"] == 2)]
        assert abs(a_w2["off_sos_score"].iloc[0] - 0.10) < 1e-6
        assert abs(a_w2["def_sos_score"].iloc[0] - 0.40) < 1e-6

    def test_rolling_on_sos(self):
        """SOS output should have _roll3, _roll6, _std columns on stat columns."""
        pbp = _build_four_team_three_week_sos_pbp()
        result = compute_sos_metrics(pbp)

        for col in ["off_sos_score", "def_sos_score", "adj_off_epa", "adj_def_epa"]:
            assert f"{col}_roll3" in result.columns, f"Missing {col}_roll3"
            assert f"{col}_roll6" in result.columns, f"Missing {col}_roll6"
            assert f"{col}_std" in result.columns, f"Missing {col}_std"

    def test_bye_week_skipped(self):
        """Team with no plays in a week should have no row (not NaN fill)."""
        # Create PBP where team D has a bye in week 2
        frames = []
        # Week 1: A vs B, C vs D (all play)
        frames.append(_make_pbp_rows("A", "B", 2024, 1, [
            {"play_type": "pass", "epa": 0.10, "success": 1},
        ]))
        frames.append(_make_pbp_rows("B", "A", 2024, 1, [
            {"play_type": "pass", "epa": 0.40, "success": 1},
        ]))
        frames.append(_make_pbp_rows("C", "D", 2024, 1, [
            {"play_type": "pass", "epa": 0.60, "success": 1},
        ]))
        frames.append(_make_pbp_rows("D", "C", 2024, 1, [
            {"play_type": "pass", "epa": -0.30, "success": 0},
        ]))
        # Week 2: A vs C, B plays someone (not D). D has bye.
        frames.append(_make_pbp_rows("A", "C", 2024, 2, [
            {"play_type": "pass", "epa": 0.20, "success": 1},
        ]))
        frames.append(_make_pbp_rows("C", "A", 2024, 2, [
            {"play_type": "pass", "epa": -0.20, "success": 0},
        ]))
        frames.append(_make_pbp_rows("B", "C", 2024, 2, [
            {"play_type": "pass", "epa": 0.50, "success": 1},
        ]))
        # Note: only B offense vs C, C defense - B has no defense and C is not on offense vs B in W2
        # Actually let's add C on offense vs B too for balance
        frames.append(_make_pbp_rows("C", "B", 2024, 2, [
            {"play_type": "pass", "epa": 0.10, "success": 1},
        ]))

        pbp = pd.concat(frames, ignore_index=True)
        pbp["game_id"] = pbp.apply(
            lambda r: f"{r['season']}_{r['week']:02d}_{'_'.join(sorted([r['posteam'], r['defteam']]))}",
            axis=1,
        )
        result = compute_sos_metrics(pbp)

        # D should have no row in week 2 (bye week)
        d_w2 = result[(result["team"] == "D") & (result["week"] == 2)]
        assert len(d_w2) == 0


# ---------------------------------------------------------------------------
# Situational Splits Tests (Plan 16-02)
# ---------------------------------------------------------------------------


def _build_situational_pbp() -> pd.DataFrame:
    """Build a synthetic PBP DataFrame with 4 teams from real divisions over 4 weeks.

    Teams:
        PHI, DAL (NFC East — divisional rivals)
        KC, DEN (AFC West — divisional rivals)

    Schedule:
        Week 1: PHI (home) vs DAL (away) — divisional
        Week 2: KC (home) vs DEN (away) — divisional
        Week 3: PHI (home) vs KC (away) — non-divisional
        Week 4: DAL (home) vs DEN (away) — non-divisional

    Score differentials per play set to test game script:
        Week 1 PHI offense: score_differential = 10 (leading), then -10 (trailing)
        Week 1 DAL offense: score_differential = -10 (trailing), then 3 (neutral)
        Week 2 KC offense: score_differential = 0 (neutral)
        Week 2 DEN offense: score_differential = 14 (leading)
        Week 3 PHI offense: score_differential = -3 (neutral)
        Week 3 KC offense: score_differential = 8 (leading)
        Week 4 DAL offense: score_differential = -14 (trailing)
        Week 4 DEN offense: score_differential = 0 (neutral)
    """
    frames = []

    # Week 1: PHI (home) vs DAL (away) — divisional
    frames.append(pd.DataFrame([
        {"posteam": "PHI", "defteam": "DAL", "season": 2024, "week": 1,
         "season_type": "REG", "play_type": "pass", "epa": 0.50, "success": 1,
         "home_team": "PHI", "away_team": "DAL", "score_differential": 10,
         "game_id": "2024_01_DAL_PHI"},
        {"posteam": "PHI", "defteam": "DAL", "season": 2024, "week": 1,
         "season_type": "REG", "play_type": "run", "epa": 0.20, "success": 1,
         "home_team": "PHI", "away_team": "DAL", "score_differential": -10,
         "game_id": "2024_01_DAL_PHI"},
    ]))
    frames.append(pd.DataFrame([
        {"posteam": "DAL", "defteam": "PHI", "season": 2024, "week": 1,
         "season_type": "REG", "play_type": "pass", "epa": -0.30, "success": 0,
         "home_team": "PHI", "away_team": "DAL", "score_differential": -10,
         "game_id": "2024_01_DAL_PHI"},
        {"posteam": "DAL", "defteam": "PHI", "season": 2024, "week": 1,
         "season_type": "REG", "play_type": "run", "epa": 0.10, "success": 1,
         "home_team": "PHI", "away_team": "DAL", "score_differential": 3,
         "game_id": "2024_01_DAL_PHI"},
    ]))

    # Week 2: KC (home) vs DEN (away) — divisional
    frames.append(pd.DataFrame([
        {"posteam": "KC", "defteam": "DEN", "season": 2024, "week": 2,
         "season_type": "REG", "play_type": "pass", "epa": 0.40, "success": 1,
         "home_team": "KC", "away_team": "DEN", "score_differential": 0,
         "game_id": "2024_02_DEN_KC"},
        {"posteam": "KC", "defteam": "DEN", "season": 2024, "week": 2,
         "season_type": "REG", "play_type": "run", "epa": 0.10, "success": 1,
         "home_team": "KC", "away_team": "DEN", "score_differential": 0,
         "game_id": "2024_02_DEN_KC"},
    ]))
    frames.append(pd.DataFrame([
        {"posteam": "DEN", "defteam": "KC", "season": 2024, "week": 2,
         "season_type": "REG", "play_type": "pass", "epa": 0.60, "success": 1,
         "home_team": "KC", "away_team": "DEN", "score_differential": 14,
         "game_id": "2024_02_DEN_KC"},
        {"posteam": "DEN", "defteam": "KC", "season": 2024, "week": 2,
         "season_type": "REG", "play_type": "run", "epa": 0.30, "success": 1,
         "home_team": "KC", "away_team": "DEN", "score_differential": 14,
         "game_id": "2024_02_DEN_KC"},
    ]))

    # Week 3: PHI (home) vs KC (away) — non-divisional
    frames.append(pd.DataFrame([
        {"posteam": "PHI", "defteam": "KC", "season": 2024, "week": 3,
         "season_type": "REG", "play_type": "pass", "epa": 0.30, "success": 1,
         "home_team": "PHI", "away_team": "KC", "score_differential": -3,
         "game_id": "2024_03_KC_PHI"},
        {"posteam": "PHI", "defteam": "KC", "season": 2024, "week": 3,
         "season_type": "REG", "play_type": "run", "epa": -0.10, "success": 0,
         "home_team": "PHI", "away_team": "KC", "score_differential": -3,
         "game_id": "2024_03_KC_PHI"},
    ]))
    frames.append(pd.DataFrame([
        {"posteam": "KC", "defteam": "PHI", "season": 2024, "week": 3,
         "season_type": "REG", "play_type": "pass", "epa": 0.70, "success": 1,
         "home_team": "PHI", "away_team": "KC", "score_differential": 8,
         "game_id": "2024_03_KC_PHI"},
        {"posteam": "KC", "defteam": "PHI", "season": 2024, "week": 3,
         "season_type": "REG", "play_type": "run", "epa": 0.20, "success": 1,
         "home_team": "PHI", "away_team": "KC", "score_differential": 8,
         "game_id": "2024_03_KC_PHI"},
    ]))

    # Week 4: DAL (home) vs DEN (away) — non-divisional
    frames.append(pd.DataFrame([
        {"posteam": "DAL", "defteam": "DEN", "season": 2024, "week": 4,
         "season_type": "REG", "play_type": "pass", "epa": -0.20, "success": 0,
         "home_team": "DAL", "away_team": "DEN", "score_differential": -14,
         "game_id": "2024_04_DAL_DEN"},
        {"posteam": "DAL", "defteam": "DEN", "season": 2024, "week": 4,
         "season_type": "REG", "play_type": "run", "epa": -0.40, "success": 0,
         "home_team": "DAL", "away_team": "DEN", "score_differential": -14,
         "game_id": "2024_04_DAL_DEN"},
    ]))
    frames.append(pd.DataFrame([
        {"posteam": "DEN", "defteam": "DAL", "season": 2024, "week": 4,
         "season_type": "REG", "play_type": "pass", "epa": 0.50, "success": 1,
         "home_team": "DAL", "away_team": "DEN", "score_differential": 0,
         "game_id": "2024_04_DAL_DEN"},
        {"posteam": "DEN", "defteam": "DAL", "season": 2024, "week": 4,
         "season_type": "REG", "play_type": "run", "epa": 0.10, "success": 1,
         "home_team": "DAL", "away_team": "DEN", "score_differential": 0,
         "game_id": "2024_04_DAL_DEN"},
    ]))

    return pd.concat(frames, ignore_index=True)


class TestSituational:
    """Tests for compute_situational_splits."""

    def test_home_away_split(self):
        """home_off_epa populated when team is home, away_off_epa when away; NaN for the other."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # PHI is home in week 1 (vs DAL) — home_off_epa should be populated
        phi_w1 = result[(result["team"] == "PHI") & (result["week"] == 1)]
        assert len(phi_w1) == 1
        assert not pd.isna(phi_w1["home_off_epa"].iloc[0])
        # PHI offense EPA W1: mean(0.50, 0.20) = 0.35
        assert abs(phi_w1["home_off_epa"].iloc[0] - 0.35) < 1e-6
        # PHI is not away in week 1, so away_off_epa should be NaN
        assert pd.isna(phi_w1["away_off_epa"].iloc[0])

        # DAL is away in week 1 — away_off_epa should be populated
        dal_w1 = result[(result["team"] == "DAL") & (result["week"] == 1)]
        assert not pd.isna(dal_w1["away_off_epa"].iloc[0])
        # DAL offense EPA W1: mean(-0.30, 0.10) = -0.10
        assert abs(dal_w1["away_off_epa"].iloc[0] - (-0.10)) < 1e-6
        # DAL is not home in week 1
        assert pd.isna(dal_w1["home_off_epa"].iloc[0])

    def test_home_away_defense(self):
        """home_def_epa and away_def_epa correctly assigned."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # PHI is home in week 1 — home_def_epa = mean of DAL's offensive plays EPA
        # DAL offense EPA W1: mean(-0.30, 0.10) = -0.10
        phi_w1 = result[(result["team"] == "PHI") & (result["week"] == 1)]
        assert not pd.isna(phi_w1["home_def_epa"].iloc[0])
        assert abs(phi_w1["home_def_epa"].iloc[0] - (-0.10)) < 1e-6
        assert pd.isna(phi_w1["away_def_epa"].iloc[0])

    def test_divisional_tagging(self):
        """div_off_epa populated for same-division opponents, nondiv_off_epa for cross-division."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # PHI vs DAL (week 1) = divisional (both NFC East)
        phi_w1 = result[(result["team"] == "PHI") & (result["week"] == 1)]
        assert not pd.isna(phi_w1["div_off_epa"].iloc[0])
        assert abs(phi_w1["div_off_epa"].iloc[0] - 0.35) < 1e-6
        # Non-divisional should be NaN for this week
        assert pd.isna(phi_w1["nondiv_off_epa"].iloc[0])

        # PHI vs KC (week 3) = non-divisional
        phi_w3 = result[(result["team"] == "PHI") & (result["week"] == 3)]
        assert not pd.isna(phi_w3["nondiv_off_epa"].iloc[0])
        # PHI offense EPA W3: mean(0.30, -0.10) = 0.10
        assert abs(phi_w3["nondiv_off_epa"].iloc[0] - 0.10) < 1e-6
        assert pd.isna(phi_w3["div_off_epa"].iloc[0])

    def test_game_script_leading(self):
        """leading_off_epa computed from plays where score_differential >= 7."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # PHI W1: score_differential = [10, -10]. Leading play: epa=0.50
        phi_w1 = result[(result["team"] == "PHI") & (result["week"] == 1)]
        assert not pd.isna(phi_w1["leading_off_epa"].iloc[0])
        assert abs(phi_w1["leading_off_epa"].iloc[0] - 0.50) < 1e-6

    def test_game_script_trailing(self):
        """trailing_off_epa computed from plays where score_differential <= -7."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # PHI W1: score_differential = [10, -10]. Trailing play: epa=0.20
        phi_w1 = result[(result["team"] == "PHI") & (result["week"] == 1)]
        assert not pd.isna(phi_w1["trailing_off_epa"].iloc[0])
        assert abs(phi_w1["trailing_off_epa"].iloc[0] - 0.20) < 1e-6

    def test_neutral_excluded(self):
        """Plays with -6 <= score_differential <= 6 excluded from leading/trailing splits."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # KC W2: score_differential = [0, 0]. Both neutral — leading/trailing should be NaN
        kc_w2 = result[(result["team"] == "KC") & (result["week"] == 2)]
        assert pd.isna(kc_w2["leading_off_epa"].iloc[0])
        assert pd.isna(kc_w2["trailing_off_epa"].iloc[0])

    def test_rolling_on_splits(self):
        """All situational columns have _roll3, _roll6, _std variants."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        split_cols = [
            "home_off_epa", "away_off_epa", "home_def_epa", "away_def_epa",
            "div_off_epa", "nondiv_off_epa", "div_def_epa", "nondiv_def_epa",
            "leading_off_epa", "trailing_off_epa", "leading_def_epa", "trailing_def_epa",
        ]
        for col in split_cols:
            assert f"{col}_roll3" in result.columns, f"Missing {col}_roll3"
            assert f"{col}_roll6" in result.columns, f"Missing {col}_roll6"
            assert f"{col}_std" in result.columns, f"Missing {col}_std"

    def test_nan_for_non_applicable(self):
        """Away week produces NaN for home_off_epa; non-divisional week produces NaN for div_off_epa."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # KC is away in week 3 (at PHI) — home_off_epa should be NaN
        kc_w3 = result[(result["team"] == "KC") & (result["week"] == 3)]
        assert pd.isna(kc_w3["home_off_epa"].iloc[0])

        # KC vs PHI (week 3) is non-divisional — div_off_epa should be NaN
        assert pd.isna(kc_w3["div_off_epa"].iloc[0])

    def test_wide_format(self):
        """One row per (team, season, week) in output."""
        pbp = _build_situational_pbp()
        result = compute_situational_splits(pbp)

        # Check uniqueness of (team, season, week)
        key_counts = result.groupby(["team", "season", "week"]).size()
        assert (key_counts == 1).all(), "Multiple rows for same (team, season, week)"

        # Should have 8 team-weeks total (4 teams x 2 weeks each from the fixture)
        # PHI: W1, W3; DAL: W1, W4; KC: W2, W3; DEN: W2, W4
        assert len(result) == 8


class TestIdempotency:
    """Tests for idempotent computation of SOS and situational splits."""

    def test_sos_idempotent(self):
        """compute_sos_metrics on same input twice produces identical DataFrames."""
        pbp = _build_four_team_three_week_sos_pbp()
        result1 = compute_sos_metrics(pbp)
        result2 = compute_sos_metrics(pbp)

        # Sort both for comparison
        result1 = result1.sort_values(["team", "season", "week"]).reset_index(drop=True)
        result2 = result2.sort_values(["team", "season", "week"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(result1, result2)

    def test_situational_idempotent(self):
        """compute_situational_splits on same input twice produces identical DataFrames."""
        pbp = _build_situational_pbp()
        result1 = compute_situational_splits(pbp)
        result2 = compute_situational_splits(pbp)

        result1 = result1.sort_values(["team", "season", "week"]).reset_index(drop=True)
        result2 = result2.sort_values(["team", "season", "week"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(result1, result2)
