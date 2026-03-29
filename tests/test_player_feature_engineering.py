#!/usr/bin/env python3
"""Tests for player-week feature vector assembly.

Validates that assemble_player_features() joins 9 Silver sources correctly,
enforces temporal integrity via shift(1), includes matchup features,
derives Vegas implied team totals, detects leakage, and filters eligible players.
"""

import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Project src/ on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import PLAYER_LABEL_COLUMNS


# ---------------------------------------------------------------------------
# Fixtures — synthetic DataFrames mimicking Silver schemas
# ---------------------------------------------------------------------------


@pytest.fixture
def usage_df():
    """Silver players/usage with 20 rows: mix of QB/RB/WR/TE/K, varying snap_pct_roll3."""
    np.random.seed(42)
    players = [
        ("P001", "QB1", "KC", "BUF", "QB", 0.80),
        ("P002", "RB1", "KC", "BUF", "RB", 0.55),
        ("P003", "WR1", "BUF", "KC", "WR", 0.65),
        ("P004", "TE1", "BUF", "KC", "TE", 0.40),
        ("P005", "K1", "KC", "BUF", "K", 0.10),   # Excluded: not skill pos
        ("P006", "RB2", "KC", "BUF", "RB", 0.15),  # Excluded: snap < 0.20
        ("P007", "WR2", "BUF", "KC", "WR", 0.30),
        ("P008", "QB2", "BUF", "KC", "QB", 0.70),
        ("P009", "TE2", "KC", "BUF", "TE", 0.25),
        ("P010", "RB3", "BUF", "KC", "RB", 0.50),
    ]
    rows = []
    for week in [1, 2]:
        for pid, name, team, opp, pos, snap in players:
            rows.append({
                "player_id": pid,
                "player_name": name,
                "recent_team": team,
                "opponent_team": opp,
                "position": pos,
                "season": 2024,
                "week": week,
                "snap_pct_roll3": snap,
                "targets_roll3": np.random.uniform(2, 10),
                "carries_roll3": np.random.uniform(0, 15),
                "passing_yards_roll3": np.random.uniform(0, 300) if pos == "QB" else 0.0,
                "rushing_yards_roll3": np.random.uniform(10, 80),
                "receiving_yards_roll3": np.random.uniform(10, 80) if pos in ("WR", "TE", "RB") else 0.0,
                # Raw stats (labels, not features)
                "targets": np.random.randint(0, 12),
                "carries": np.random.randint(0, 20),
                "passing_yards": np.random.randint(0, 400) if pos == "QB" else 0,
                "rushing_yards": np.random.randint(0, 120),
                "receiving_yards": np.random.randint(0, 120) if pos in ("WR", "TE", "RB") else 0,
                "receptions": np.random.randint(0, 10),
                "passing_tds": np.random.randint(0, 4) if pos == "QB" else 0,
                "rushing_tds": np.random.randint(0, 2),
                "receiving_tds": np.random.randint(0, 2),
                "interceptions": np.random.randint(0, 3) if pos == "QB" else 0,
                "fantasy_points_ppr": np.random.uniform(0, 35),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def advanced_df():
    """Silver players/advanced with matching player rows."""
    rows = []
    for week in [1, 2]:
        for pid in ["P001", "P002", "P003", "P004", "P005", "P006",
                     "P007", "P008", "P009", "P010"]:
            rows.append({
                "player_gsis_id": pid,
                "season": 2024,
                "week": week,
                "ngs_avg_separation": np.random.uniform(1.0, 4.0),
                "pfr_receiving_yards_per_route": np.random.uniform(0.5, 3.0),
                "qbr_total_epa": np.random.uniform(-5.0, 10.0),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def historical_df():
    """Silver players/historical — one row per player (static dimension)."""
    rows = []
    for pid in ["P001", "P002", "P003", "P004", "P005", "P006",
                 "P007", "P008", "P009", "P010"]:
        rows.append({
            "gsis_id": pid,
            "draft_round": np.random.randint(1, 8),
            "draft_pick": np.random.randint(1, 260),
            "draft_value": np.random.uniform(0.1, 10.0),
            "speed_score": np.random.uniform(70, 110),
            "burst_score": np.random.uniform(90, 130),
        })
    return pd.DataFrame(rows)


@pytest.fixture
def defense_df():
    """Silver defense/positional — 2 weeks per team/position."""
    rows = []
    teams = ["KC", "BUF"]
    positions = ["QB", "RB", "WR", "TE"]
    for team in teams:
        for pos in positions:
            for week in [1, 2]:
                rows.append({
                    "team": team,
                    "position": pos,
                    "season": 2024,
                    "week": week,
                    "avg_pts_allowed": np.random.uniform(10, 25),
                    "rank": np.random.randint(1, 33),
                })
    return pd.DataFrame(rows)


@pytest.fixture
def team_quality_df():
    """Silver teams/player_quality."""
    rows = []
    for team in ["KC", "BUF"]:
        for week in [1, 2]:
            rows.append({
                "team": team, "season": 2024, "week": week,
                "qb_passing_epa": np.random.uniform(-0.2, 0.3),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def game_context_df():
    """Silver teams/game_context."""
    rows = []
    for team in ["KC", "BUF"]:
        for week in [1, 2]:
            rows.append({
                "team": team, "season": 2024, "week": week,
                "is_home": 1 if team == "KC" else 0,
                "rest_days": 7,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def market_data_df():
    """Silver teams/market_data."""
    rows = []
    for team in ["KC", "BUF"]:
        for week in [1, 2]:
            rows.append({
                "team": team, "season": 2024, "week": week,
                "opening_spread": -3.0 if team == "KC" else 3.0,
                "opening_total": 48.5,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def pbp_metrics_df():
    """Silver teams/pbp_metrics."""
    rows = []
    for team in ["KC", "BUF"]:
        for week in [1, 2]:
            rows.append({
                "team": team, "season": 2024, "week": week,
                "off_epa_per_play": np.random.uniform(-0.1, 0.2),
                "def_epa_per_play": np.random.uniform(-0.2, 0.1),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def tendencies_df():
    """Silver teams/tendencies."""
    rows = []
    for team in ["KC", "BUF"]:
        for week in [1, 2]:
            rows.append({
                "team": team, "season": 2024, "week": week,
                "pace": np.random.uniform(25, 35),
                "pass_rate_over_expected": np.random.uniform(-0.1, 0.1),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def schedules_df():
    """Bronze schedules for implied total computation."""
    return pd.DataFrame([
        {"season": 2024, "week": 1, "home_team": "KC", "away_team": "BUF",
         "spread_line": -3.0, "total_line": 48.0, "game_type": "REG"},
        {"season": 2024, "week": 2, "home_team": "BUF", "away_team": "KC",
         "spread_line": 1.5, "total_line": 50.0, "game_type": "REG"},
    ])


def _build_mock_readers(
    usage_df, advanced_df, historical_df, defense_df,
    team_quality_df, game_context_df, market_data_df,
    pbp_metrics_df, tendencies_df, schedules_df,
):
    """Return mock functions for _read_latest_local and _read_bronze_schedules."""
    source_map = {
        "players/usage": usage_df,
        "players/advanced": advanced_df,
        "players/historical": historical_df,
        "defense/positional": defense_df,
        "teams/player_quality": team_quality_df,
        "teams/game_context": game_context_df,
        "teams/market_data": market_data_df,
        "teams/pbp_metrics": pbp_metrics_df,
        "teams/tendencies": tendencies_df,
    }

    def mock_read_latest(subdir, season):
        return source_map.get(subdir, pd.DataFrame()).copy()

    def mock_read_schedules(season):
        return schedules_df.copy()

    return mock_read_latest, mock_read_schedules


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAssemblePlayerFeatures:
    """Test core feature assembly from 9 Silver sources."""

    def test_assemble_player_features(
        self, usage_df, advanced_df, historical_df, defense_df,
        team_quality_df, game_context_df, market_data_df,
        pbp_metrics_df, tendencies_df, schedules_df,
    ):
        """assemble_player_features returns DataFrame with columns from all sources."""
        from player_feature_engineering import assemble_player_features

        mock_read, mock_sched = _build_mock_readers(
            usage_df, advanced_df, historical_df, defense_df,
            team_quality_df, game_context_df, market_data_df,
            pbp_metrics_df, tendencies_df, schedules_df,
        )

        with patch("player_feature_engineering._read_latest_local", side_effect=mock_read), \
             patch("player_feature_engineering._read_bronze_schedules", side_effect=mock_sched):
            result = assemble_player_features(2024)

        assert not result.empty, "Result should not be empty"
        # Columns from advanced source
        assert "ngs_avg_separation" in result.columns
        # Columns from team quality
        assert "qb_passing_epa" in result.columns
        # Historical columns
        assert "draft_round" in result.columns
        # Core identifier present
        assert "player_id" in result.columns

    def test_matchup_features_lagged(
        self, usage_df, advanced_df, historical_df, defense_df,
        team_quality_df, game_context_df, market_data_df,
        pbp_metrics_df, tendencies_df, schedules_df,
    ):
        """Matchup features opp_avg_pts_allowed and opp_rank use week N-1 values."""
        from player_feature_engineering import assemble_player_features

        mock_read, mock_sched = _build_mock_readers(
            usage_df, advanced_df, historical_df, defense_df,
            team_quality_df, game_context_df, market_data_df,
            pbp_metrics_df, tendencies_df, schedules_df,
        )

        with patch("player_feature_engineering._read_latest_local", side_effect=mock_read), \
             patch("player_feature_engineering._read_bronze_schedules", side_effect=mock_sched):
            result = assemble_player_features(2024)

        assert "opp_avg_pts_allowed" in result.columns
        assert "opp_rank" in result.columns

        # Week 1 should have NaN matchup features (no prior week)
        week1 = result[result["week"] == 1]
        if not week1.empty:
            assert week1["opp_avg_pts_allowed"].isna().all(), \
                "Week 1 should have NaN matchup features (no prior week data)"

        # Week 2 should have values from week 1
        week2 = result[result["week"] == 2]
        if not week2.empty:
            assert week2["opp_avg_pts_allowed"].notna().any(), \
                "Week 2 should have non-NaN matchup features from week 1"

    def test_implied_team_totals(
        self, usage_df, advanced_df, historical_df, defense_df,
        team_quality_df, game_context_df, market_data_df,
        pbp_metrics_df, tendencies_df, schedules_df,
    ):
        """implied_team_total column exists and is clipped to [5.0, 45.0]."""
        from player_feature_engineering import assemble_player_features

        mock_read, mock_sched = _build_mock_readers(
            usage_df, advanced_df, historical_df, defense_df,
            team_quality_df, game_context_df, market_data_df,
            pbp_metrics_df, tendencies_df, schedules_df,
        )

        with patch("player_feature_engineering._read_latest_local", side_effect=mock_read), \
             patch("player_feature_engineering._read_bronze_schedules", side_effect=mock_sched):
            result = assemble_player_features(2024)

        assert "implied_team_total" in result.columns
        valid = result["implied_team_total"].dropna()
        assert (valid >= 5.0).all(), "Implied total should be >= 5.0"
        assert (valid <= 45.0).all(), "Implied total should be <= 45.0"

        # Check formula for KC week 1: home team, spread=-3.0, total=48.0
        # implied_home = (48/2) - (-3/2) = 24 + 1.5 = 25.5
        kc_w1 = result[(result["recent_team"] == "KC") & (result["week"] == 1)]
        if not kc_w1.empty:
            expected = 25.5
            actual = kc_w1["implied_team_total"].iloc[0]
            assert abs(actual - expected) < 0.1, f"Expected ~{expected}, got {actual}"


class TestTemporalIntegrity:
    """Test validate_temporal_integrity()."""

    def test_temporal_integrity_passes(self):
        """Properly shifted rolling columns pass validation."""
        from player_feature_engineering import validate_temporal_integrity

        np.random.seed(123)
        n = 100
        # Raw stats are random
        raw = np.random.randn(n) * 50 + 200
        # Rolling is shifted (different distribution, moderate correlation)
        roll = np.random.randn(n) * 30 + 180
        df = pd.DataFrame({
            "passing_yards": raw,
            "passing_yards_roll3": roll,
            "rushing_yards": np.random.randn(n) * 20,
            "rushing_yards_roll3": np.random.randn(n) * 15,
            "receiving_yards": np.random.randn(n) * 20,
            "receiving_yards_roll3": np.random.randn(n) * 15,
            "targets": np.random.randn(n) * 3,
            "targets_roll3": np.random.randn(n) * 2,
            "carries": np.random.randn(n) * 5,
            "carries_roll3": np.random.randn(n) * 4,
        })
        violations = validate_temporal_integrity(df)
        assert len(violations) == 0, f"Expected no violations, got {violations}"

    def test_temporal_integrity_detects_violation(self):
        """Unshifted rolling columns (r=1.0) are flagged."""
        from player_feature_engineering import validate_temporal_integrity

        n = 100
        raw = np.random.randn(n) * 50 + 200
        df = pd.DataFrame({
            "passing_yards": raw,
            "passing_yards_roll3": raw,  # Same values = r=1.0 = leakage
            "rushing_yards": np.random.randn(n) * 20,
            "rushing_yards_roll3": np.random.randn(n) * 15,
            "receiving_yards": np.random.randn(n) * 20,
            "receiving_yards_roll3": np.random.randn(n) * 15,
            "targets": np.random.randn(n) * 3,
            "targets_roll3": np.random.randn(n) * 2,
            "carries": np.random.randn(n) * 5,
            "carries_roll3": np.random.randn(n) * 4,
        })
        violations = validate_temporal_integrity(df)
        assert len(violations) > 0, "Should detect violation when roll3 == raw"
        assert any("passing_yards" in v[0] for v in violations)


class TestLeakageDetection:
    """Test detect_leakage()."""

    def test_detect_leakage_flags_high_corr(self):
        """Feature perfectly correlated to target is flagged."""
        from player_feature_engineering import detect_leakage

        np.random.seed(42)
        n = 100
        target = np.random.randn(n) * 50 + 200
        df = pd.DataFrame({
            "leaky_feature": target * 1.0,  # r = 1.0
            "safe_feature": np.random.randn(n),
            "passing_yards": target,
        })
        warnings = detect_leakage(
            df,
            feature_cols=["leaky_feature", "safe_feature"],
            target_cols=["passing_yards"],
            threshold=0.90,
        )
        assert len(warnings) > 0, "Should flag leaky_feature"
        assert any("leaky_feature" in w[0] for w in warnings)

    def test_detect_leakage_passes_normal(self):
        """Feature with moderate correlation (r~0.5) is not flagged."""
        from player_feature_engineering import detect_leakage

        np.random.seed(42)
        n = 200
        target = np.random.randn(n) * 50 + 200
        noise = np.random.randn(n) * 50
        df = pd.DataFrame({
            "moderate_feature": target * 0.5 + noise,
            "passing_yards": target,
        })
        warnings = detect_leakage(
            df,
            feature_cols=["moderate_feature"],
            target_cols=["passing_yards"],
            threshold=0.90,
        )
        assert len(warnings) == 0, f"Should not flag moderate correlation, got {warnings}"


class TestEligibilityFilter:
    """Test player eligibility filter."""

    def test_eligibility_filter(self, usage_df):
        """Only QB/RB/WR/TE with snap_pct_roll3 >= 0.20 pass."""
        from player_feature_engineering import _filter_eligible_players

        result = _filter_eligible_players(usage_df)

        # K (P005) excluded — not skill position
        assert "K" not in result["position"].values, "Kicker should be excluded"

        # P006 (RB, snap=0.15) excluded — below threshold
        assert "P006" not in result["player_id"].values, "Low snap player excluded"

        # P001 (QB, 0.80), P002 (RB, 0.55), P003 (WR, 0.65) should pass
        for pid in ["P001", "P002", "P003"]:
            assert pid in result["player_id"].values, f"{pid} should pass filter"


class TestGetPlayerFeatureColumns:
    """Test get_player_feature_columns()."""

    def test_get_player_feature_columns(self):
        """Returns only numeric non-identifier non-label columns."""
        from player_feature_engineering import get_player_feature_columns

        df = pd.DataFrame({
            "player_id": ["P001", "P002"],
            "season": [2024, 2024],
            "week": [1, 1],
            "position": ["QB", "RB"],
            "passing_yards": [300, 0],      # label
            "targets": [0, 5],              # label
            "snap_pct_roll3": [0.8, 0.5],   # feature
            "draft_round": [1, 3],          # feature
            "qb_passing_epa": [0.15, -0.1], # feature
        })
        features = get_player_feature_columns(df)

        # Should include numeric features
        assert "snap_pct_roll3" in features
        assert "draft_round" in features
        assert "qb_passing_epa" in features

        # Should exclude identifiers and labels
        assert "player_id" not in features
        assert "season" not in features
        assert "position" not in features
        assert "passing_yards" not in features
        assert "targets" not in features
