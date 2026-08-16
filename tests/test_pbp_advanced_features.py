"""Tests for PBP-advanced player features (src/pbp_advanced_features.py).

Covers:
    - Raw player-week computation from a minimal PBP fixture (adot,
      target-share-by-zone, QB sack-rate/aggressiveness proxies)
    - Trailing feature computation: shift(1) enforcement (week 1 NaN,
      no same-week leak, trail = mean of prior weeks)
    - Leak gate: no raw pbp_advanced column appears in
      get_player_feature_columns output
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_pbp_df() -> pd.DataFrame:
    """Minimal PBP DataFrame: one team, two receivers, one QB, one week.

    Targets: P1 gets a deep target (air_yards=25), P2 gets a short target
    (air_yards=5). QB1 throws both, plus one sack.
    """
    return pd.DataFrame(
        {
            "game_id": ["G1", "G1", "G1"],
            "season": [2023, 2023, 2023],
            "week": [1, 1, 1],
            "posteam": ["BUF", "BUF", "BUF"],
            "pass_attempt": [1, 1, 0],
            "qb_dropback": [1, 1, 1],
            "sack": [0, 0, 1],
            "air_yards": [25.0, 5.0, np.nan],
            "receiver_player_id": ["P1", "P2", None],
            "passer_player_id": ["QB1", "QB1", "QB1"],
        }
    )


@pytest.fixture
def multi_week_player_df() -> pd.DataFrame:
    """Player-week pbp_advanced raw features for 4 weeks (trailing lag test)."""
    return pd.DataFrame(
        {
            "player_id": ["P1"] * 4,
            "season": [2023] * 4,
            "week": [1, 2, 3, 4],
            "position_type": ["receiver"] * 4,
            "adot": [10.0, 12.0, 8.0, 14.0],
            "deep_target_share": [0.2, 0.3, 0.1, 0.4],
            "intermediate_target_share": [0.3, 0.2, 0.4, 0.1],
            "short_target_share": [0.5, 0.5, 0.5, 0.5],
        }
    )


# ---------------------------------------------------------------------------
# Raw computation tests
# ---------------------------------------------------------------------------


class TestComputePbpAdvancedPlayerWeek:
    def test_empty_bronze_returns_empty(self, tmp_path: str) -> None:
        from pbp_advanced_features import compute_pbp_advanced_player_week

        result = compute_pbp_advanced_player_week(season=2023, bronze_dir=str(tmp_path))
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_adot_computed_correctly(
        self, tmp_path: str, minimal_pbp_df: pd.DataFrame
    ) -> None:
        from pbp_advanced_features import compute_pbp_advanced_player_week

        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(pbp_dir)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        result = compute_pbp_advanced_player_week(season=2023, bronze_dir=str(tmp_path))
        recv = result[result["position_type"] == "receiver"].set_index("player_id")

        assert recv.loc["P1", "adot"] == pytest.approx(25.0)
        assert recv.loc["P2", "adot"] == pytest.approx(5.0)

    def test_target_share_by_zone(
        self, tmp_path: str, minimal_pbp_df: pd.DataFrame
    ) -> None:
        """P1's target is the team's only deep target -> deep_target_share=1.0."""
        from pbp_advanced_features import compute_pbp_advanced_player_week

        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(pbp_dir)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        result = compute_pbp_advanced_player_week(season=2023, bronze_dir=str(tmp_path))
        recv = result[result["position_type"] == "receiver"].set_index("player_id")

        assert recv.loc["P1", "deep_target_share"] == pytest.approx(1.0)
        assert recv.loc["P1", "short_target_share"] == pytest.approx(0.0)
        assert recv.loc["P2", "short_target_share"] == pytest.approx(1.0)
        assert recv.loc["P2", "deep_target_share"] == pytest.approx(0.0)

    def test_qb_sack_rate_and_deep_ball_rate(
        self, tmp_path: str, minimal_pbp_df: pd.DataFrame
    ) -> None:
        from pbp_advanced_features import compute_pbp_advanced_player_week

        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(pbp_dir)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        result = compute_pbp_advanced_player_week(season=2023, bronze_dir=str(tmp_path))
        qb = result[result["position_type"] == "qb"].set_index("player_id")

        # 1 sack out of 3 dropbacks
        assert qb.loc["QB1", "qb_sack_rate"] == pytest.approx(1.0 / 3.0)
        # 1 of 2 pass attempts is deep (air_yards=25 >= 20)
        assert qb.loc["QB1", "qb_deep_ball_rate"] == pytest.approx(0.5)
        # avg intended air yards over the 2 pass attempts
        assert qb.loc["QB1", "qb_avg_intended_air_yards"] == pytest.approx(15.0)

    def test_rates_clipped_to_unit_interval(
        self, tmp_path: str, minimal_pbp_df: pd.DataFrame
    ) -> None:
        from pbp_advanced_features import (
            compute_pbp_advanced_player_week,
            PBP_ADV_ALL_RAW_FEATURES,
        )

        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(pbp_dir)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        result = compute_pbp_advanced_player_week(season=2023, bronze_dir=str(tmp_path))
        rate_cols = [
            c for c in PBP_ADV_ALL_RAW_FEATURES if "rate" in c or "share" in c
        ]
        for col in rate_cols:
            if col not in result.columns:
                continue
            vals = result[col].dropna()
            assert (vals >= 0).all(), f"{col} has values < 0"
            assert (vals <= 1).all(), f"{col} has values > 1"


# ---------------------------------------------------------------------------
# Trailing feature (leak) tests
# ---------------------------------------------------------------------------


class TestAddPbpAdvancedTrailingFeatures:
    def test_empty_df_returns_empty(self) -> None:
        from pbp_advanced_features import add_pbp_advanced_trailing_features

        result = add_pbp_advanced_trailing_features(pd.DataFrame())
        assert result.empty

    def test_shift1_applied_roll4_week1_nan(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """Week 1 trailing features must be NaN (no prior weeks) -- strictly-
        prior construction, the core leak-test requirement."""
        from pbp_advanced_features import add_pbp_advanced_trailing_features

        result = add_pbp_advanced_trailing_features(multi_week_player_df)
        week1 = result[result["week"] == 1]
        assert week1["adot_roll4"].isna().all()
        assert week1["adot_trail"].isna().all()
        assert week1["deep_target_share_roll4"].isna().all()

    def test_shift1_not_same_week_leak(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """roll4/trail at week 2 must not equal week 2's raw (same-week) value."""
        from pbp_advanced_features import add_pbp_advanced_trailing_features

        result = add_pbp_advanced_trailing_features(multi_week_player_df)
        week2 = result[result["week"] == 2].iloc[0]
        week2_raw_adot = multi_week_player_df[multi_week_player_df["week"] == 2][
            "adot"
        ].iloc[0]
        # roll4 at week2 has only 1 prior (shifted) observation -- below
        # min_periods=2, so NaN. Either way it must never equal week2's own
        # same-week raw value.
        assert pd.isna(week2["adot_roll4"]) or week2["adot_roll4"] != week2_raw_adot

    def test_trail_week4_is_mean_of_first_three(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        from pbp_advanced_features import add_pbp_advanced_trailing_features

        result = add_pbp_advanced_trailing_features(multi_week_player_df)
        week4 = result[result["week"] == 4].iloc[0]
        expected = np.mean([10.0, 12.0, 8.0])
        assert week4["adot_trail"] == pytest.approx(expected)

    def test_adot_slope_uses_only_prior_weeks(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """adot_slope at week 4 must be an OLS trend over weeks 1-3 only."""
        from pbp_advanced_features import add_pbp_advanced_trailing_features

        result = add_pbp_advanced_trailing_features(multi_week_player_df)
        week4 = result[result["week"] == 4].iloc[0]
        assert pd.notna(week4["adot_slope"])
        # weeks 1-3 adot = [10, 12, 8]; OLS slope of that series is -1.0
        assert week4["adot_slope"] == pytest.approx(-1.0)

    def test_no_new_raw_column_added(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        from pbp_advanced_features import add_pbp_advanced_trailing_features

        pre_cols = set(multi_week_player_df.columns)
        result = add_pbp_advanced_trailing_features(multi_week_player_df)
        new_cols = set(result.columns) - pre_cols
        for col in new_cols:
            assert col.endswith(("_roll4", "_trail", "_slope")), (
                f"Unexpected new column: {col}"
            )


# ---------------------------------------------------------------------------
# Leak gate test (must-pass per mission's "leak-test each" requirement)
# ---------------------------------------------------------------------------


class TestLeakGate:
    def test_raw_columns_registered_in_same_week_raw_stats(self) -> None:
        from player_feature_engineering import _SAME_WEEK_RAW_STATS
        from pbp_advanced_features import PBP_ADV_ALL_RAW_FEATURES

        for col in PBP_ADV_ALL_RAW_FEATURES:
            assert col in _SAME_WEEK_RAW_STATS, (
                f"Raw pbp_advanced column '{col}' is NOT in _SAME_WEEK_RAW_STATS "
                "-- it could leak into model features!"
            )

    def test_trailing_columns_not_in_same_week_raw_stats(self) -> None:
        from player_feature_engineering import _SAME_WEEK_RAW_STATS
        from pbp_advanced_features import PBP_ADVANCED_FEATURE_COLUMNS

        for col in PBP_ADVANCED_FEATURE_COLUMNS:
            assert col not in _SAME_WEEK_RAW_STATS, (
                f"Trailing column '{col}' is incorrectly in _SAME_WEEK_RAW_STATS"
            )

    def test_trailing_columns_pass_is_unlagged_leak_check(self) -> None:
        from player_feature_engineering import _is_unlagged_leak
        from pbp_advanced_features import PBP_ADVANCED_FEATURE_COLUMNS

        for col in PBP_ADVANCED_FEATURE_COLUMNS:
            assert not _is_unlagged_leak(col), (
                f"_is_unlagged_leak incorrectly flagged '{col}' as a leak"
            )

    def test_raw_columns_excluded_from_feature_set_end_to_end(self) -> None:
        from player_feature_engineering import get_player_feature_columns
        from pbp_advanced_features import (
            PBP_ADV_ALL_RAW_FEATURES,
            PBP_ADVANCED_FEATURE_COLUMNS,
        )

        n = 20
        data: dict = {
            "player_id": ["P1"] * n,
            "season": [2023] * n,
            "week": list(range(1, n + 1)),
            "position": ["WR"] * n,
        }
        rng = np.random.default_rng(0)
        for col in PBP_ADV_ALL_RAW_FEATURES:
            data[col] = rng.random(n)
        for col in PBP_ADVANCED_FEATURE_COLUMNS:
            data[col] = rng.random(n)

        df = pd.DataFrame(data)
        feature_cols = get_player_feature_columns(df)

        raw_leaked = [c for c in PBP_ADV_ALL_RAW_FEATURES if c in feature_cols]
        assert not raw_leaked, f"Raw pbp_advanced columns leaked: {raw_leaked}"

        trailing_present = [c for c in PBP_ADVANCED_FEATURE_COLUMNS if c in feature_cols]
        assert len(trailing_present) > 0, "No pbp_advanced trailing columns in feature set"


# ---------------------------------------------------------------------------
# Silver build smoke test
# ---------------------------------------------------------------------------


class TestBuildPbpAdvancedSilver:
    def test_writes_parquet_when_data_exists(
        self, tmp_path: str, minimal_pbp_df: pd.DataFrame
    ) -> None:
        from pbp_advanced_features import build_pbp_advanced_silver

        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(pbp_dir)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        saved = build_pbp_advanced_silver(
            seasons=[2023], bronze_dir=str(tmp_path), silver_dir=str(tmp_path)
        )
        assert 2023 in saved
        assert os.path.exists(saved[2023])
        written = pd.read_parquet(saved[2023])
        assert not written.empty

    def test_no_bronze_skips_season(self, tmp_path: str) -> None:
        from pbp_advanced_features import build_pbp_advanced_silver

        saved = build_pbp_advanced_silver(
            seasons=[2023], bronze_dir=str(tmp_path), silver_dir=str(tmp_path)
        )
        assert saved == {}
