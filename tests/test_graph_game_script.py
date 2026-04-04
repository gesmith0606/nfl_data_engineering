#!/usr/bin/env python3
"""Tests for game script role shift features.

Tests cover:
- Script zone bucketing (5 zones)
- Per-player script usage computation from PBP
- Rolling feature computation with shift(1) lag
- Predicted script boost with various spreads
- Temporal safety (shift(1) compliance)
- Players with limited data (few games)
- Empty/missing data handling
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Fixtures — synthetic PBP data
# ---------------------------------------------------------------------------


def _make_pbp(
    n_pass: int = 50,
    n_run: int = 50,
    posteam: str = "KC",
    defteam: str = "BUF",
    season: int = 2024,
    week: int = 1,
    score_diff: float = 0.0,
    receiver_id: str = "00-0001",
    rusher_id: str = "00-0002",
) -> pd.DataFrame:
    """Build a synthetic PBP DataFrame for one game."""
    rows = []
    for i in range(n_pass):
        rows.append(
            {
                "play_type": "pass",
                "posteam": posteam,
                "defteam": defteam,
                "season": season,
                "week": week,
                "score_differential": score_diff,
                "receiver_player_id": receiver_id,
                "rusher_player_id": None,
                "passer_player_id": "00-0010",
                "yards_gained": np.random.uniform(0, 15),
                "complete_pass": 1 if i % 3 != 0 else 0,
                "pass_touchdown": 1 if i == 0 else 0,
                "rush_touchdown": 0,
                "touchdown": 1 if i == 0 else 0,
            }
        )
    for i in range(n_run):
        rows.append(
            {
                "play_type": "run",
                "posteam": posteam,
                "defteam": defteam,
                "season": season,
                "week": week,
                "score_differential": score_diff,
                "receiver_player_id": None,
                "rusher_player_id": rusher_id,
                "passer_player_id": None,
                "yards_gained": np.random.uniform(0, 10),
                "complete_pass": 0,
                "pass_touchdown": 0,
                "rush_touchdown": 1 if i == 0 else 0,
                "touchdown": 1 if i == 0 else 0,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def close_game_pbp():
    """PBP where all plays occur in close game script zone."""
    return _make_pbp(score_diff=0.0)


@pytest.fixture
def blowout_leading_pbp():
    """PBP where team is dominating (leading_big)."""
    return _make_pbp(score_diff=21.0)


@pytest.fixture
def trailing_big_pbp():
    """PBP where team is being blown out."""
    return _make_pbp(score_diff=-17.0)


@pytest.fixture
def mixed_game_pbp():
    """PBP with plays across multiple script zones in one game."""
    dfs = []
    # 20 plays close
    dfs.append(_make_pbp(n_pass=10, n_run=10, score_diff=0.0, week=1))
    # 20 plays leading
    dfs.append(_make_pbp(n_pass=10, n_run=10, score_diff=10.0, week=1))
    # 20 plays trailing
    dfs.append(_make_pbp(n_pass=15, n_run=5, score_diff=-10.0, week=1))
    return pd.concat(dfs, ignore_index=True)


@pytest.fixture
def multi_week_pbp():
    """PBP data spanning 5 weeks for rolling feature tests."""
    dfs = []
    # Week 1: close game
    dfs.append(_make_pbp(n_pass=20, n_run=20, score_diff=3.0, week=1))
    # Week 2: leading big
    dfs.append(_make_pbp(n_pass=15, n_run=25, score_diff=17.0, week=2))
    # Week 3: trailing
    dfs.append(_make_pbp(n_pass=25, n_run=15, score_diff=-10.0, week=3))
    # Week 4: close
    dfs.append(_make_pbp(n_pass=20, n_run=20, score_diff=-2.0, week=4))
    # Week 5: leading
    dfs.append(_make_pbp(n_pass=18, n_run=22, score_diff=9.0, week=5))
    return pd.concat(dfs, ignore_index=True)


@pytest.fixture
def schedules_df():
    """Bronze schedules with spread lines."""
    return pd.DataFrame(
        {
            "season": [2024] * 5,
            "week": [1, 2, 3, 4, 5],
            "home_team": ["KC"] * 5,
            "away_team": ["BUF"] * 5,
            "spread_line": [-7.0, -3.0, 2.5, -14.0, 0.0],
            "total_line": [48.0, 45.0, 42.0, 51.0, 44.0],
            "game_type": ["REG"] * 5,
        }
    )


# ---------------------------------------------------------------------------
# Tests: zone classification
# ---------------------------------------------------------------------------


class TestScriptZoneClassification:
    """Test _classify_script_zone bucketing."""

    def test_leading_big(self):
        from graph_game_script import _classify_script_zone

        assert _classify_script_zone(14) == "leading_big"
        assert _classify_script_zone(21) == "leading_big"
        assert _classify_script_zone(35) == "leading_big"

    def test_leading(self):
        from graph_game_script import _classify_script_zone

        assert _classify_script_zone(7) == "leading"
        assert _classify_script_zone(10) == "leading"
        assert _classify_script_zone(13) == "leading"

    def test_close(self):
        from graph_game_script import _classify_script_zone

        assert _classify_script_zone(0) == "close"
        assert _classify_script_zone(6) == "close"
        assert _classify_script_zone(-6) == "close"
        assert _classify_script_zone(3) == "close"

    def test_trailing(self):
        from graph_game_script import _classify_script_zone

        assert _classify_script_zone(-7) == "trailing"
        assert _classify_script_zone(-10) == "trailing"
        assert _classify_script_zone(-13) == "trailing"

    def test_trailing_big(self):
        from graph_game_script import _classify_script_zone

        assert _classify_script_zone(-14) == "trailing_big"
        assert _classify_script_zone(-21) == "trailing_big"
        assert _classify_script_zone(-35) == "trailing_big"

    def test_boundary_values(self):
        """Test exact boundary transitions."""
        from graph_game_script import _classify_script_zone

        # 14 boundary
        assert _classify_script_zone(13) == "leading"
        assert _classify_script_zone(14) == "leading_big"

        # 7 boundary
        assert _classify_script_zone(6) == "close"
        assert _classify_script_zone(7) == "leading"

        # -6 boundary
        assert _classify_script_zone(-6) == "close"
        assert _classify_script_zone(-7) == "trailing"

        # -13 boundary
        assert _classify_script_zone(-13) == "trailing"
        assert _classify_script_zone(-14) == "trailing_big"


# ---------------------------------------------------------------------------
# Tests: compute_game_script_usage
# ---------------------------------------------------------------------------


class TestComputeGameScriptUsage:
    """Test per-player per-game script usage computation."""

    def test_close_game_all_usage_in_close_zone(self, close_game_pbp):
        from graph_game_script import compute_game_script_usage

        result = compute_game_script_usage(close_game_pbp)

        assert not result.empty
        # WR should have all targets in close zone
        wr = result[result["player_id"] == "00-0001"]
        assert len(wr) == 1
        assert wr.iloc[0]["targets_close"] == wr.iloc[0]["total_targets"]
        assert wr.iloc[0]["targets_leading_big"] == 0

    def test_blowout_all_usage_in_leading_big(self, blowout_leading_pbp):
        from graph_game_script import compute_game_script_usage

        result = compute_game_script_usage(blowout_leading_pbp)

        rb = result[result["player_id"] == "00-0002"]
        assert len(rb) == 1
        assert rb.iloc[0]["carries_leading_big"] == rb.iloc[0]["total_carries"]
        assert rb.iloc[0]["carries_close"] == 0

    def test_trailing_big_usage(self, trailing_big_pbp):
        from graph_game_script import compute_game_script_usage

        result = compute_game_script_usage(trailing_big_pbp)

        wr = result[result["player_id"] == "00-0001"]
        assert wr.iloc[0]["targets_trailing_big"] == wr.iloc[0]["total_targets"]

    def test_mixed_game_distributes_across_zones(self, mixed_game_pbp):
        from graph_game_script import compute_game_script_usage

        result = compute_game_script_usage(mixed_game_pbp)

        wr = result[result["player_id"] == "00-0001"]
        assert len(wr) == 1
        # Should have targets in close, leading, and trailing zones
        assert wr.iloc[0]["targets_close"] > 0
        assert wr.iloc[0]["targets_leading"] > 0
        assert wr.iloc[0]["targets_trailing"] > 0

    def test_zone_shares_sum_to_one(self, mixed_game_pbp):
        from graph_game_script import compute_game_script_usage

        result = compute_game_script_usage(mixed_game_pbp)

        for _, row in result.iterrows():
            if row["total_targets"] > 0:
                target_shares = sum(
                    row[f"targets_share_{z}"]
                    for z in [
                        "leading_big",
                        "leading",
                        "close",
                        "trailing",
                        "trailing_big",
                    ]
                )
                assert abs(target_shares - 1.0) < 1e-6

    def test_empty_pbp(self):
        from graph_game_script import compute_game_script_usage

        result = compute_game_script_usage(pd.DataFrame())
        assert result.empty

    def test_pbp_without_score_differential(self):
        """Should compute from posteam_score - defteam_score."""
        from graph_game_script import compute_game_script_usage

        pbp = _make_pbp(score_diff=0.0)
        pbp = pbp.drop(columns=["score_differential"])
        pbp["posteam_score"] = 21
        pbp["defteam_score"] = 7
        result = compute_game_script_usage(pbp)

        assert not result.empty
        # Score diff = 14, so all plays should be leading_big
        wr = result[result["player_id"] == "00-0001"]
        assert wr.iloc[0]["targets_leading_big"] == wr.iloc[0]["total_targets"]

    def test_output_columns(self, close_game_pbp):
        from graph_game_script import compute_game_script_usage

        result = compute_game_script_usage(close_game_pbp)

        assert "player_id" in result.columns
        assert "season" in result.columns
        assert "week" in result.columns
        assert "recent_team" in result.columns
        assert "total_targets" in result.columns
        assert "total_carries" in result.columns
        assert "targets_close" in result.columns
        assert "carries_leading_big" in result.columns


# ---------------------------------------------------------------------------
# Tests: compute_game_script_features
# ---------------------------------------------------------------------------


class TestComputeGameScriptFeatures:
    """Test rolling game script feature computation."""

    def test_rolling_features_exist(self, multi_week_pbp):
        from graph_game_script import (
            GAME_SCRIPT_FEATURE_COLUMNS,
            compute_game_script_features,
            compute_game_script_usage,
        )

        usage = compute_game_script_usage(multi_week_pbp)
        result = compute_game_script_features(usage)

        assert not result.empty
        for col in GAME_SCRIPT_FEATURE_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_temporal_lag_week1_is_nan(self, multi_week_pbp):
        """Week 1 should have NaN for all rolling features (no prior data)."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        usage = compute_game_script_usage(multi_week_pbp)
        result = compute_game_script_features(usage)

        week1 = result[result["week"] == 1]
        for _, row in week1.iterrows():
            assert pd.isna(
                row["usage_when_trailing_roll3"]
            ), "Week 1 trailing should be NaN (shift(1))"
            assert pd.isna(
                row["usage_when_leading_roll3"]
            ), "Week 1 leading should be NaN (shift(1))"

    def test_temporal_lag_week2_uses_only_week1(self, multi_week_pbp):
        """Week 2 features should reflect only week 1 data."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        usage = compute_game_script_usage(multi_week_pbp)
        result = compute_game_script_features(usage)

        # Week 1 is a close game (score_diff=3), so trailing/leading share ~ 0
        wr_w2 = result[(result["week"] == 2) & (result["player_id"] == "00-0001")]
        if not wr_w2.empty:
            # All usage in week 1 was in 'close' zone, so trailing/leading ~ 0
            assert wr_w2.iloc[0]["usage_when_trailing_roll3"] == pytest.approx(
                0.0, abs=0.01
            )

    def test_predicted_script_boost_with_schedules(self, multi_week_pbp, schedules_df):
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        usage = compute_game_script_usage(multi_week_pbp)
        result = compute_game_script_features(usage, schedules_df)

        assert "predicted_script_boost" in result.columns
        # All boosts should be in [0.90, 1.10]
        boosts = result["predicted_script_boost"].dropna()
        assert (boosts >= 0.90).all()
        assert (boosts <= 1.10).all()

    def test_predicted_script_boost_big_favorite(self):
        """7-point home favorite should get boost > 1.0."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        pbp = _make_pbp(score_diff=0.0, week=2)
        # Add week 1 for rolling to have data
        pbp_w1 = _make_pbp(score_diff=0.0, week=1)
        pbp_all = pd.concat([pbp_w1, pbp], ignore_index=True)
        usage = compute_game_script_usage(pbp_all)

        schedules = pd.DataFrame(
            {
                "season": [2024, 2024],
                "week": [1, 2],
                "home_team": ["KC", "KC"],
                "away_team": ["BUF", "BUF"],
                "spread_line": [-7.0, -7.0],
                "total_line": [48.0, 48.0],
                "game_type": ["REG", "REG"],
            }
        )
        result = compute_game_script_features(usage, schedules)

        kc_rows = result[result["recent_team"] == "KC"]
        # Home favorite with -7 spread: boost = 1.0 + ((-7) * -0.01) = 1.07
        boosts = kc_rows["predicted_script_boost"].dropna()
        assert (boosts > 1.0).all()

    def test_predicted_script_boost_big_underdog(self):
        """7-point away underdog should get boost < 1.0."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        pbp = _make_pbp(score_diff=0.0, week=2, posteam="BUF", defteam="KC")
        pbp_w1 = _make_pbp(score_diff=0.0, week=1, posteam="BUF", defteam="KC")
        pbp_all = pd.concat([pbp_w1, pbp], ignore_index=True)
        usage = compute_game_script_usage(pbp_all)

        schedules = pd.DataFrame(
            {
                "season": [2024, 2024],
                "week": [1, 2],
                "home_team": ["KC", "KC"],
                "away_team": ["BUF", "BUF"],
                "spread_line": [-7.0, -7.0],
                "total_line": [48.0, 48.0],
                "game_type": ["REG", "REG"],
            }
        )
        result = compute_game_script_features(usage, schedules)

        buf_rows = result[result["recent_team"] == "BUF"]
        boosts = buf_rows["predicted_script_boost"].dropna()
        # Away team: spread flipped to +7 -> boost = 1.0 + (7 * -0.01) = 0.93
        assert (boosts < 1.0).all()

    def test_predicted_script_boost_no_schedules(self, multi_week_pbp):
        """Without schedules, boost should be 1.0."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        usage = compute_game_script_usage(multi_week_pbp)
        result = compute_game_script_features(usage, schedules_df=None)

        boosts = result["predicted_script_boost"].dropna()
        assert (boosts == 1.0).all()

    def test_script_volatility_nonzero_for_mixed_games(self):
        """Players with varied zone usage should have non-zero volatility."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        # Week 1: mixed zones
        dfs = []
        dfs.append(_make_pbp(n_pass=10, n_run=10, score_diff=0.0, week=1))
        dfs.append(_make_pbp(n_pass=10, n_run=10, score_diff=15.0, week=1))
        dfs.append(_make_pbp(n_pass=10, n_run=10, score_diff=-15.0, week=1))
        # Week 2 to see week 1 rolling
        dfs.append(_make_pbp(n_pass=10, n_run=10, score_diff=0.0, week=2))
        pbp = pd.concat(dfs, ignore_index=True)

        usage = compute_game_script_usage(pbp)
        result = compute_game_script_features(usage)

        w2 = result[result["week"] == 2]
        vol = w2["script_volatility"].dropna()
        assert len(vol) > 0
        assert (vol > 0).all(), "Volatility should be > 0 for mixed zone usage"

    def test_clock_killer_share_for_rb_in_blowout(self):
        """RB with heavy carries in leading_big should have high clock_killer."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        # Week 1: leading big, RB gets many carries
        pbp_w1 = _make_pbp(n_pass=5, n_run=40, score_diff=21.0, week=1)
        # Week 2 to see rolling
        pbp_w2 = _make_pbp(n_pass=5, n_run=40, score_diff=21.0, week=2)
        pbp = pd.concat([pbp_w1, pbp_w2], ignore_index=True)

        usage = compute_game_script_usage(pbp)
        result = compute_game_script_features(usage)

        rb_w2 = result[(result["week"] == 2) & (result["player_id"] == "00-0002")]
        assert not rb_w2.empty
        # All carries in leading_big -> clock_killer_share should be 1.0
        assert rb_w2.iloc[0]["clock_killer_share_roll3"] == pytest.approx(1.0, abs=0.01)

    def test_empty_input(self):
        from graph_game_script import compute_game_script_features

        result = compute_game_script_features(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# Tests: limited data / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test behavior with limited data and edge cases."""

    def test_single_game_player(self):
        """Player with only one game should get NaN for week 1 features."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        pbp = _make_pbp(score_diff=5.0, week=1)
        usage = compute_game_script_usage(pbp)
        result = compute_game_script_features(usage)

        assert not result.empty
        # Only week 1 — all rolling features should be NaN
        for col in [
            "usage_when_trailing_roll3",
            "usage_when_leading_roll3",
        ]:
            assert result[col].isna().all()

    def test_player_with_two_games(self):
        """Player with two games: week 2 should use week 1 data only."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        pbp = pd.concat(
            [
                _make_pbp(score_diff=-10.0, week=1),  # trailing
                _make_pbp(score_diff=10.0, week=2),  # leading
            ],
            ignore_index=True,
        )
        usage = compute_game_script_usage(pbp)
        result = compute_game_script_features(usage)

        wr_w2 = result[(result["week"] == 2) & (result["player_id"] == "00-0001")]
        # Week 2 should reflect week 1 (trailing game) — trailing share > 0
        if not wr_w2.empty:
            assert wr_w2.iloc[0]["usage_when_trailing_roll3"] > 0

    def test_no_score_columns_returns_empty(self):
        """PBP without any score column should return empty."""
        from graph_game_script import compute_game_script_usage

        pbp = _make_pbp(score_diff=0.0)
        pbp = pbp.drop(columns=["score_differential"])
        result = compute_game_script_usage(pbp)
        assert result.empty

    def test_only_pass_plays(self):
        """Game with only pass plays should still work."""
        from graph_game_script import compute_game_script_usage

        pbp = _make_pbp(n_pass=50, n_run=0, score_diff=3.0)
        result = compute_game_script_usage(pbp)

        assert not result.empty
        # Only WR should appear
        assert len(result) == 1
        assert result.iloc[0]["player_id"] == "00-0001"
        assert result.iloc[0]["total_carries"] == 0

    def test_only_run_plays(self):
        """Game with only run plays should still work."""
        from graph_game_script import compute_game_script_usage

        pbp = _make_pbp(n_pass=0, n_run=50, score_diff=-3.0)
        result = compute_game_script_usage(pbp)

        assert not result.empty
        assert len(result) == 1
        assert result.iloc[0]["player_id"] == "00-0002"
        assert result.iloc[0]["total_targets"] == 0

    def test_garbage_time_share_in_blowout_loss(self):
        """Yards in trailing_big should drive garbage_time_share."""
        from graph_game_script import (
            compute_game_script_features,
            compute_game_script_usage,
        )

        # Week 1: trailing big — all production is "garbage time"
        pbp_w1 = _make_pbp(score_diff=-21.0, week=1)
        # Week 2: to access week 1 features
        pbp_w2 = _make_pbp(score_diff=0.0, week=2)
        pbp = pd.concat([pbp_w1, pbp_w2], ignore_index=True)

        usage = compute_game_script_usage(pbp)
        result = compute_game_script_features(usage)

        wr_w2 = result[(result["week"] == 2) & (result["player_id"] == "00-0001")]
        if not wr_w2.empty:
            # All yards in week 1 were trailing_big = garbage time
            assert wr_w2.iloc[0]["garbage_time_share_roll3"] == pytest.approx(
                1.0, abs=0.01
            )


# ---------------------------------------------------------------------------
# Tests: feature column constants
# ---------------------------------------------------------------------------


class TestFeatureColumns:
    """Test GAME_SCRIPT_FEATURE_COLUMNS constant."""

    def test_column_count(self):
        from graph_game_script import GAME_SCRIPT_FEATURE_COLUMNS

        assert len(GAME_SCRIPT_FEATURE_COLUMNS) == 6

    def test_column_names(self):
        from graph_game_script import GAME_SCRIPT_FEATURE_COLUMNS

        expected = {
            "usage_when_trailing_roll3",
            "usage_when_leading_roll3",
            "garbage_time_share_roll3",
            "clock_killer_share_roll3",
            "script_volatility",
            "predicted_script_boost",
        }
        assert set(GAME_SCRIPT_FEATURE_COLUMNS) == expected


# ---------------------------------------------------------------------------
# Tests: integration with feature engineering
# ---------------------------------------------------------------------------


class TestFeatureEngineeringIntegration:
    """Test that game script features wire into player_feature_engineering."""

    def test_join_function_exists(self):
        """_join_game_script_features should be importable."""
        from player_feature_engineering import _join_game_script_features

        assert callable(_join_game_script_features)

    def test_join_with_empty_data(self):
        """Join on a DataFrame when no cached data exists should add NaN cols."""
        from graph_game_script import GAME_SCRIPT_FEATURE_COLUMNS
        from player_feature_engineering import _join_game_script_features

        df = pd.DataFrame(
            {
                "player_id": ["00-0001", "00-0002"],
                "season": [2024, 2024],
                "week": [1, 1],
                "recent_team": ["KC", "KC"],
                "position": ["WR", "RB"],
            }
        )
        # Season 9999 should have no cached data
        result = _join_game_script_features(df, 9999)

        for col in GAME_SCRIPT_FEATURE_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"
            assert result[col].isna().all(), f"Column {col} should be NaN with no data"
