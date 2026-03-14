#!/usr/bin/env python3
"""Unit tests for team_analytics PBP metric computation functions."""

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
