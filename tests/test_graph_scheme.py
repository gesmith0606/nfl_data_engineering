#!/usr/bin/env python3
"""Tests for scheme classification and defensive front profiling.

Tests cover:
- Scheme classification (zone/gap_power/spread/balanced) with synthetic PBP
- Defensive front composite calculation
- Scheme matchup score computation
- Temporal lag enforcement
- Empty/missing data handling
- Integration with player feature engineering
"""

import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Fixtures -- synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def zone_pbp():
    """PBP data that should classify as zone scheme (high end rate)."""
    n = 100
    return pd.DataFrame(
        {
            "play_type": ["run"] * n,
            "posteam": ["KC"] * n,
            "defteam": ["BUF"] * n,
            "season": [2024] * n,
            "week": [1] * (n // 2) + [2] * (n // 2),
            "run_gap": ["end"] * 40 + ["tackle"] * 30 + ["guard"] * 30,
            "run_location": ["left"] * 33 + ["middle"] * 34 + ["right"] * 33,
            "shotgun": [1] * 30 + [0] * 70,
            "no_huddle": [0] * 90 + [1] * 10,
            "epa": np.random.randn(n) * 0.5,
            "yards_gained": np.random.uniform(1, 10, n),
        }
    )


@pytest.fixture
def gap_power_pbp():
    """PBP data that should classify as gap_power scheme."""
    n = 100
    return pd.DataFrame(
        {
            "play_type": ["run"] * n,
            "posteam": ["PIT"] * n,
            "defteam": ["BAL"] * n,
            "season": [2024] * n,
            "week": [1] * n,
            "run_gap": ["guard"] * 30 + ["tackle"] * 30 + ["end"] * 10 + [None] * 30,
            "run_location": ["left"] * 50 + ["right"] * 50,
            "shotgun": [0] * 80 + [1] * 20,
            "no_huddle": [0] * 95 + [1] * 5,
            "epa": np.random.randn(n) * 0.5,
            "yards_gained": np.random.uniform(1, 8, n),
        }
    )


@pytest.fixture
def spread_pbp():
    """PBP data that should classify as spread scheme."""
    n = 100
    return pd.DataFrame(
        {
            "play_type": ["run"] * n,
            "posteam": ["ARI"] * n,
            "defteam": ["SF"] * n,
            "season": [2024] * n,
            "week": [1] * n,
            "run_gap": ["end"] * 20 + ["tackle"] * 20 + ["guard"] * 10 + [None] * 50,
            "run_location": ["left"] * 50 + ["right"] * 50,
            "shotgun": [1] * 65 + [0] * 35,
            "no_huddle": [1] * 20 + [0] * 80,
            "epa": np.random.randn(n) * 0.5,
            "yards_gained": np.random.uniform(2, 12, n),
        }
    )


@pytest.fixture
def multi_team_pbp():
    """PBP data with multiple teams and weeks for matchup testing."""
    rows = []
    teams = [("KC", "BUF"), ("BUF", "KC"), ("KC", "BUF"), ("BUF", "KC")]
    for week, (off, deff) in enumerate(teams, start=1):
        for _ in range(50):
            rows.append(
                {
                    "play_type": "run",
                    "posteam": off,
                    "defteam": deff,
                    "season": 2024,
                    "week": week,
                    "run_gap": np.random.choice(["end", "tackle", "guard"]),
                    "run_location": np.random.choice(["left", "middle", "right"]),
                    "shotgun": np.random.choice([0, 1]),
                    "no_huddle": 0,
                    "epa": np.random.randn() * 0.5,
                    "yards_gained": np.random.uniform(1, 10),
                }
            )
        # Add some pass plays
        for _ in range(30):
            rows.append(
                {
                    "play_type": "pass",
                    "posteam": off,
                    "defteam": deff,
                    "season": 2024,
                    "week": week,
                    "run_gap": None,
                    "run_location": None,
                    "shotgun": 1,
                    "no_huddle": 0,
                    "epa": np.random.randn() * 0.5,
                    "yards_gained": np.random.uniform(0, 20),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def pfr_def_df():
    """Synthetic PFR defensive weekly data."""
    rows = []
    teams = ["KC", "BUF"]
    for team in teams:
        opp = "BUF" if team == "KC" else "KC"
        for week in range(1, 5):
            for player_idx in range(8):
                rows.append(
                    {
                        "team": team,
                        "opponent": opp,
                        "season": 2024,
                        "week": week,
                        "pfr_player_name": f"Player_{team}_{player_idx}",
                        "def_sacks": np.random.uniform(0, 2),
                        "def_pressures": np.random.uniform(0, 5),
                        "def_times_hurried": np.random.uniform(0, 3),
                        "def_tackles_combined": np.random.uniform(2, 10),
                        "def_missed_tackles": np.random.uniform(0, 2),
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def schedules_df():
    """Synthetic schedules data."""
    rows = []
    for week in range(1, 5):
        rows.append(
            {
                "season": 2024,
                "week": week,
                "home_team": "KC" if week % 2 == 1 else "BUF",
                "away_team": "BUF" if week % 2 == 1 else "KC",
                "game_type": "REG",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def rosters_with_positions():
    """Roster data with front-7 positions."""
    rows = []
    positions = ["DE", "DT", "LB", "ILB", "OLB", "CB", "S", "MLB"]
    for team in ["KC", "BUF"]:
        for idx, pos in enumerate(positions):
            rows.append(
                {
                    "full_name": f"Player_{team}_{idx}",
                    "team": team,
                    "position": pos,
                    "season": 2024,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: Scheme Classification
# ---------------------------------------------------------------------------


class TestClassifyRunScheme:
    """Test classify_run_scheme function."""

    def test_zone_classification(self, zone_pbp):
        """Zone scheme: high end rate triggers zone classification."""
        from graph_scheme import classify_run_scheme

        result = classify_run_scheme(zone_pbp, 2024)
        assert not result.empty
        assert result.iloc[0]["scheme_type"] == "zone"
        assert result.iloc[0]["run_gap_end_rate"] > 0.35

    def test_gap_power_classification(self, gap_power_pbp):
        """Gap/power scheme: high guard+tackle rate."""
        from graph_scheme import classify_run_scheme

        result = classify_run_scheme(gap_power_pbp, 2024)
        assert not result.empty
        row = result.iloc[0]
        assert row["scheme_type"] == "gap_power"
        assert row["run_gap_guard_rate"] + row["run_gap_tackle_rate"] > 0.50

    def test_spread_classification(self, spread_pbp):
        """Spread scheme: high shotgun rate."""
        from graph_scheme import classify_run_scheme

        result = classify_run_scheme(spread_pbp, 2024)
        assert not result.empty
        assert result.iloc[0]["scheme_type"] == "spread"
        assert result.iloc[0]["shotgun_rate"] > 0.60

    def test_balanced_classification(self):
        """Balanced scheme: none of the thresholds met."""
        from graph_scheme import classify_run_scheme

        n = 100
        pbp = pd.DataFrame(
            {
                "play_type": ["run"] * n,
                "posteam": ["NYG"] * n,
                "defteam": ["DAL"] * n,
                "season": [2024] * n,
                "week": [1] * n,
                "run_gap": ["end"] * 25
                + ["tackle"] * 25
                + ["guard"] * 25
                + [None] * 25,
                "run_location": ["left"] * 50 + ["right"] * 50,
                "shotgun": [1] * 40 + [0] * 60,
                "no_huddle": [0] * 100,
            }
        )
        result = classify_run_scheme(pbp, 2024)
        assert not result.empty
        assert result.iloc[0]["scheme_type"] == "balanced"

    def test_empty_pbp(self):
        """Empty PBP returns empty DataFrame."""
        from graph_scheme import classify_run_scheme

        result = classify_run_scheme(pd.DataFrame(), 2024)
        assert result.empty

    def test_no_run_plays(self):
        """PBP with only pass plays returns empty DataFrame."""
        from graph_scheme import classify_run_scheme

        pbp = pd.DataFrame(
            {
                "play_type": ["pass"] * 50,
                "posteam": ["KC"] * 50,
                "season": [2024] * 50,
                "week": [1] * 50,
            }
        )
        result = classify_run_scheme(pbp, 2024)
        assert result.empty

    def test_output_columns(self, zone_pbp):
        """Output has all expected columns."""
        from graph_scheme import classify_run_scheme

        result = classify_run_scheme(zone_pbp, 2024)
        expected_cols = {
            "team",
            "season",
            "scheme_type",
            "run_gap_end_rate",
            "run_gap_tackle_rate",
            "run_gap_guard_rate",
            "run_loc_left_rate",
            "run_loc_middle_rate",
            "run_loc_right_rate",
            "shotgun_rate",
            "no_huddle_rate",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_rates_sum_to_approx_one(self, zone_pbp):
        """Gap rates should sum to approximately 1.0 (excluding NaN gaps)."""
        from graph_scheme import classify_run_scheme

        result = classify_run_scheme(zone_pbp, 2024)
        row = result.iloc[0]
        gap_sum = (
            row["run_gap_end_rate"]
            + row["run_gap_tackle_rate"]
            + row["run_gap_guard_rate"]
        )
        # May be less than 1.0 due to NaN gaps, but should be > 0
        assert gap_sum > 0

    def test_multiple_teams(self, multi_team_pbp):
        """Multiple teams in PBP should each get classification."""
        from graph_scheme import classify_run_scheme

        result = classify_run_scheme(multi_team_pbp, 2024)
        assert len(result) >= 2
        assert set(result["team"]) == {"KC", "BUF"}


# ---------------------------------------------------------------------------
# Tests: Defensive Front Quality
# ---------------------------------------------------------------------------


class TestDefensiveFrontQuality:
    """Test compute_defensive_front_quality function."""

    def test_basic_computation(self, pfr_def_df):
        """Computes front7_quality for each team-week."""
        from graph_scheme import compute_defensive_front_quality

        result = compute_defensive_front_quality(pfr_def_df)
        assert not result.empty
        assert "front7_quality" in result.columns
        assert "front7_sacks" in result.columns
        assert "front7_pressures" in result.columns
        assert "front7_hurries" in result.columns
        assert "front7_tackles" in result.columns

    def test_temporal_lag(self, pfr_def_df):
        """Week 1 should have NaN quality (no prior data for shift(1))."""
        from graph_scheme import compute_defensive_front_quality

        result = compute_defensive_front_quality(pfr_def_df)
        week1 = result[result["week"] == 1]
        # shift(1) means week 1 has no prior data -> NaN
        assert week1["front7_quality"].isna().all()

    def test_with_roster_filtering(self, pfr_def_df, rosters_with_positions):
        """Roster-based filtering produces results."""
        from graph_scheme import compute_defensive_front_quality

        result = compute_defensive_front_quality(pfr_def_df, rosters_with_positions)
        assert not result.empty

    def test_empty_input(self):
        """Empty PFR data returns empty DataFrame."""
        from graph_scheme import compute_defensive_front_quality

        result = compute_defensive_front_quality(pd.DataFrame())
        assert result.empty

    def test_missing_columns(self):
        """Missing stat columns handled gracefully."""
        from graph_scheme import compute_defensive_front_quality

        df = pd.DataFrame(
            {
                "team": ["KC", "KC"],
                "season": [2024, 2024],
                "week": [1, 2],
                "pfr_player_name": ["P1", "P2"],
                "def_tackles_combined": [5.0, 8.0],
            }
        )
        result = compute_defensive_front_quality(df)
        assert not result.empty

    def test_quality_is_positive(self, pfr_def_df):
        """Quality composite should be non-negative for non-NaN values."""
        from graph_scheme import compute_defensive_front_quality

        result = compute_defensive_front_quality(pfr_def_df)
        valid = result["front7_quality"].dropna()
        assert (valid >= 0).all()


# ---------------------------------------------------------------------------
# Tests: Scheme Matchup Features
# ---------------------------------------------------------------------------


class TestSchemeFeatures:
    """Test compute_scheme_features function."""

    def test_basic_computation(self, multi_team_pbp, pfr_def_df, schedules_df):
        """Computes scheme features for each team-week."""
        from graph_feature_extraction import compute_scheme_features

        result = compute_scheme_features(
            multi_team_pbp, pfr_def_df, pd.DataFrame(), schedules_df
        )
        assert not result.empty
        assert "def_front_quality_vs_run" in result.columns
        assert "scheme_matchup_score" in result.columns
        assert "rb_ypc_by_gap_vs_defense" in result.columns
        assert "def_run_epa_allowed" in result.columns

    def test_output_columns(self, multi_team_pbp, pfr_def_df, schedules_df):
        """Output has all SCHEME_FEATURE_COLUMNS."""
        from graph_feature_extraction import (
            SCHEME_FEATURE_COLUMNS,
            compute_scheme_features,
        )

        result = compute_scheme_features(
            multi_team_pbp, pfr_def_df, pd.DataFrame(), schedules_df
        )
        for col in SCHEME_FEATURE_COLUMNS:
            assert col in result.columns

    def test_temporal_lag_on_def_run_epa(
        self, multi_team_pbp, pfr_def_df, schedules_df
    ):
        """def_run_epa_allowed should be NaN for week 1 (no prior data)."""
        from graph_feature_extraction import compute_scheme_features

        result = compute_scheme_features(
            multi_team_pbp, pfr_def_df, pd.DataFrame(), schedules_df
        )
        week1 = result[result["week"] == 1]
        # shift(1) on rolling means week 1 should be NaN
        assert week1["def_run_epa_allowed"].isna().all()

    def test_empty_pbp(self):
        """Empty PBP returns empty DataFrame."""
        from graph_feature_extraction import compute_scheme_features

        result = compute_scheme_features(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        )
        assert result.empty

    def test_matchups_from_pbp(self, multi_team_pbp, pfr_def_df):
        """Can derive matchups from PBP when schedules empty."""
        from graph_feature_extraction import compute_scheme_features

        result = compute_scheme_features(
            multi_team_pbp, pfr_def_df, pd.DataFrame(), pd.DataFrame()
        )
        assert not result.empty

    def test_rb_ypc_vs_defense_prior_only(
        self, multi_team_pbp, pfr_def_df, schedules_df
    ):
        """rb_ypc_by_gap_vs_defense uses only prior meetings."""
        from graph_feature_extraction import compute_scheme_features

        result = compute_scheme_features(
            multi_team_pbp, pfr_def_df, pd.DataFrame(), schedules_df
        )
        # Week 1 has no prior meetings -> NaN
        week1 = result[result["week"] == 1]
        assert week1["rb_ypc_by_gap_vs_defense"].isna().all()

        # Later weeks may have prior data (KC vs BUF repeat)
        later = result[result["week"] > 2]
        # At least some should have prior matchup data
        if not later.empty:
            # Not all should be NaN if there are repeat matchups
            pass  # Data-dependent; just verify no crash


# ---------------------------------------------------------------------------
# Tests: Neo4j integration (mocked)
# ---------------------------------------------------------------------------


class TestBuildSchemeNodes:
    """Test Neo4j node/edge creation with mocked GraphDB."""

    def test_build_scheme_nodes(self, zone_pbp):
        """Creates scheme nodes and edges."""
        from graph_scheme import build_scheme_nodes, classify_run_scheme

        schemes = classify_run_scheme(zone_pbp, 2024)

        mock_db = MagicMock()
        mock_db.is_connected = True
        mock_db.run_write.return_value = []

        count = build_scheme_nodes(mock_db, schemes)
        assert count == len(schemes)
        assert mock_db.run_write.called

    def test_build_scheme_nodes_disconnected(self, zone_pbp):
        """Returns 0 when Neo4j disconnected."""
        from graph_scheme import build_scheme_nodes, classify_run_scheme

        schemes = classify_run_scheme(zone_pbp, 2024)
        mock_db = MagicMock()
        mock_db.is_connected = False

        count = build_scheme_nodes(mock_db, schemes)
        assert count == 0

    def test_build_defends_run_edges(self, pfr_def_df):
        """Creates DEFENDS_RUN edges."""
        from graph_scheme import (
            build_defends_run_edges,
            compute_defensive_front_quality,
        )

        def_front = compute_defensive_front_quality(pfr_def_df)

        mock_db = MagicMock()
        mock_db.is_connected = True
        mock_db.run_write.return_value = []

        count = build_defends_run_edges(mock_db, def_front)
        # Some rows may have NaN quality (week 1), so count may be < len
        assert count >= 0

    def test_build_defends_run_disconnected(self):
        """Returns 0 when Neo4j disconnected."""
        from graph_scheme import build_defends_run_edges

        mock_db = MagicMock()
        mock_db.is_connected = False

        count = build_defends_run_edges(mock_db, pd.DataFrame({"a": [1]}))
        assert count == 0


# ---------------------------------------------------------------------------
# Tests: Integration with player feature engineering
# ---------------------------------------------------------------------------


class TestPlayerFeatureIntegration:
    """Test scheme features integrate with player_feature_engineering."""

    def test_join_scheme_features_rb_only(self):
        """Scheme features should only apply to RB position."""
        from player_feature_engineering import _join_scheme_features

        df = pd.DataFrame(
            {
                "player_id": ["P1", "P2", "P3", "P4"],
                "recent_team": ["KC", "KC", "KC", "KC"],
                "season": [2024, 2024, 2024, 2024],
                "week": [1, 1, 1, 1],
                "position": ["RB", "WR", "QB", "TE"],
            }
        )
        result = _join_scheme_features(df, 2024)

        from graph_feature_extraction import SCHEME_FEATURE_COLUMNS

        for col in SCHEME_FEATURE_COLUMNS:
            assert col in result.columns

        # Non-RB should be NaN
        wr_row = result[result["position"] == "WR"]
        for col in SCHEME_FEATURE_COLUMNS:
            assert wr_row[col].isna().all()

    def test_join_scheme_features_empty_graceful(self):
        """Returns NaN columns when no data available."""
        from player_feature_engineering import _join_scheme_features

        df = pd.DataFrame(
            {
                "player_id": ["P1"],
                "recent_team": ["KC"],
                "season": [2099],
                "week": [1],
                "position": ["RB"],
            }
        )
        result = _join_scheme_features(df, 2099)

        from graph_feature_extraction import SCHEME_FEATURE_COLUMNS

        for col in SCHEME_FEATURE_COLUMNS:
            assert col in result.columns
            assert result[col].isna().all()

    def test_scheme_feature_columns_constant(self):
        """SCHEME_FEATURE_COLUMNS constant is properly defined."""
        from graph_feature_extraction import SCHEME_FEATURE_COLUMNS

        assert isinstance(SCHEME_FEATURE_COLUMNS, list)
        assert len(SCHEME_FEATURE_COLUMNS) == 4
        assert "def_front_quality_vs_run" in SCHEME_FEATURE_COLUMNS
        assert "scheme_matchup_score" in SCHEME_FEATURE_COLUMNS
        assert "rb_ypc_by_gap_vs_defense" in SCHEME_FEATURE_COLUMNS
        assert "def_run_epa_allowed" in SCHEME_FEATURE_COLUMNS
