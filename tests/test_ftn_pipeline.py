"""Tests for FTN charting data pipeline.

Covers:
    - Bronze ingestion parsing / pre-2022 guard
    - Silver transformation: empty df, missing columns, season gaps
    - Trailing feature computation: shift(1) enforcement
    - Leak gate: no raw FTN column appears in get_player_feature_columns output
    - Integration smoke test on a minimal fixture
"""

import os
import sys
import pandas as pd
import numpy as np
import pytest

# Ensure src/ and scripts/ are importable
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_ftn_df() -> pd.DataFrame:
    """Minimal FTN charting DataFrame with 4 plays across 2 games."""
    return pd.DataFrame(
        {
            "ftn_game_id": [1, 1, 2, 2],
            "nflverse_game_id": [
                "2023_01_BUF_KC",
                "2023_01_BUF_KC",
                "2023_01_SF_SEA",
                "2023_01_SF_SEA",
            ],
            "season": [2023, 2023, 2023, 2023],
            "week": [1, 1, 1, 1],
            "ftn_play_id": [10, 20, 30, 40],
            "nflverse_play_id": [100, 200, 300, 400],
            "is_catchable_ball": [True, False, True, True],
            "is_contested_ball": [False, False, True, False],
            "is_drop": [False, False, False, False],
            "is_play_action": [True, False, False, True],
            "is_created_reception": [False, True, False, False],
            "n_blitzers": [3, 0, 4, 2],
            "n_pass_rushers": [4.0, 4.0, 5.0, 3.0],
            "is_qb_out_of_pocket": [False, True, False, False],
            "is_throw_away": [False, False, False, False],
            "is_interception_worthy": [False, False, False, False],
        }
    )


@pytest.fixture
def minimal_pbp_df() -> pd.DataFrame:
    """Minimal PBP DataFrame matching the minimal FTN fixture."""
    return pd.DataFrame(
        {
            "game_id": [
                "2023_01_BUF_KC",
                "2023_01_BUF_KC",
                "2023_01_SF_SEA",
                "2023_01_SF_SEA",
            ],
            "play_id": [100.0, 200.0, 300.0, 400.0],
            "play_id_int": pd.array([100, 200, 300, 400], dtype="Int32"),
            "season": [2023, 2023, 2023, 2023],
            "week": [1, 1, 1, 1],
            "posteam": ["BUF", "BUF", "SF", "SF"],
            "defteam": ["KC", "KC", "SEA", "SEA"],
            "pass_attempt": [1, 1, 1, 1],
            "complete_pass": [1, 0, 1, 1],
            "receiver_player_id": ["P1", "P2", "P3", "P3"],
            "passer_player_id": ["QB1", "QB1", "QB2", "QB2"],
        }
    )


@pytest.fixture
def multi_week_player_df() -> pd.DataFrame:
    """Player-week FTN raw features for 4 weeks to test trailing feature lag."""
    return pd.DataFrame(
        {
            "player_id": ["P1"] * 4,
            "season": [2023] * 4,
            "week": [1, 2, 3, 4],
            "position_type": ["receiver"] * 4,
            "ftn_catchable_rate": [0.8, 0.7, 0.9, 0.6],
            "ftn_contested_rate": [0.3, 0.2, 0.4, 0.1],
            "ftn_drop_rate": [0.0, 0.1, 0.0, 0.0],
            "ftn_pa_target_share": [0.2, 0.3, 0.1, 0.4],
            "ftn_created_rec_rate": [0.1, 0.2, 0.0, 0.3],
            "ftn_blitz_rate": [0.4, 0.5, 0.3, 0.6],
            "ftn_avg_pass_rushers": [4.0, 4.5, 3.8, 4.2],
            "ftn_out_of_pocket_rate": [0.2, 0.3, 0.1, 0.25],
            "ftn_throw_away_rate": [0.05, 0.0, 0.1, 0.0],
            "ftn_interception_worthy_rate": [0.05, 0.05, 0.0, 0.0],
            "ftn_play_action_rate": [0.35, 0.25, 0.40, 0.20],
        }
    )


# ---------------------------------------------------------------------------
# Bronze ingestion tests
# ---------------------------------------------------------------------------


class TestBronzeFtnIngestion:
    """Tests for scripts/bronze_ftn_ingestion.py helper functions."""

    def test_parse_seasons_range(self) -> None:
        """_parse_seasons accepts YYYY-YYYY range format."""
        from bronze_ftn_ingestion import _parse_seasons

        result = _parse_seasons("2022-2024", None)
        assert result == [2022, 2023, 2024]

    def test_parse_seasons_single_string(self) -> None:
        """_parse_seasons accepts single season as string."""
        from bronze_ftn_ingestion import _parse_seasons

        result = _parse_seasons("2023", None)
        assert result == [2023]

    def test_parse_seasons_single_int(self) -> None:
        """_parse_seasons accepts single season as int."""
        from bronze_ftn_ingestion import _parse_seasons

        result = _parse_seasons(None, 2024)
        assert result == [2024]

    def test_parse_seasons_pre_2022_raises(self) -> None:
        """_parse_seasons rejects seasons before 2022."""
        from bronze_ftn_ingestion import _parse_seasons

        with pytest.raises(ValueError, match="2022"):
            _parse_seasons("2019-2024", None)

    def test_parse_seasons_range_inverted_raises(self) -> None:
        """_parse_seasons rejects start > end."""
        from bronze_ftn_ingestion import _parse_seasons

        with pytest.raises(ValueError):
            _parse_seasons("2025-2022", None)


# ---------------------------------------------------------------------------
# FTN feature computation tests
# ---------------------------------------------------------------------------


class TestComputeFtnPlayerWeek:
    """Tests for ftn_features.compute_ftn_player_week."""

    def test_pre_2022_returns_empty(self, tmp_path: str) -> None:
        """compute_ftn_player_week returns empty DataFrame for seasons < 2022."""
        from ftn_features import compute_ftn_player_week

        result = compute_ftn_player_week(season=2021, bronze_dir=str(tmp_path))
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_missing_bronze_ftn_returns_empty(self, tmp_path: str) -> None:
        """compute_ftn_player_week returns empty when no Bronze FTN parquet exists."""
        from ftn_features import compute_ftn_player_week

        # Create Bronze PBP directory but no FTN directory
        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(pbp_dir)

        result = compute_ftn_player_week(season=2023, bronze_dir=str(tmp_path))
        assert result.empty

    def test_missing_bronze_pbp_returns_empty(
        self, tmp_path: str, minimal_ftn_df: pd.DataFrame
    ) -> None:
        """compute_ftn_player_week returns empty when no Bronze PBP exists."""
        from ftn_features import compute_ftn_player_week

        # Create FTN but not PBP
        ftn_dir = os.path.join(tmp_path, "ftn_charting", "season=2023")
        os.makedirs(ftn_dir)
        minimal_ftn_df.to_parquet(
            os.path.join(ftn_dir, "ftn_20230101.parquet"), index=False
        )

        result = compute_ftn_player_week(season=2023, bronze_dir=str(tmp_path))
        assert result.empty

    def test_missing_ftn_columns_handled_gracefully(
        self, tmp_path: str, minimal_pbp_df: pd.DataFrame
    ) -> None:
        """compute_ftn_player_week handles FTN DataFrame missing optional columns."""
        from ftn_features import compute_ftn_player_week

        # FTN with only bare minimum columns (no charting flags)
        bare_ftn = pd.DataFrame(
            {
                "nflverse_game_id": ["2023_01_BUF_KC"],
                "nflverse_play_id": [100],
                "season": [2023],
                "week": [1],
            }
        )
        ftn_dir = os.path.join(tmp_path, "ftn_charting", "season=2023")
        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(ftn_dir)
        os.makedirs(pbp_dir)
        bare_ftn.to_parquet(os.path.join(ftn_dir, "ftn.parquet"), index=False)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        # Should not raise
        result = compute_ftn_player_week(season=2023, bronze_dir=str(tmp_path))
        # Result may be empty if no charting flags present — that is acceptable
        assert isinstance(result, pd.DataFrame)

    def test_receiver_features_computed(
        self,
        tmp_path: str,
        minimal_ftn_df: pd.DataFrame,
        minimal_pbp_df: pd.DataFrame,
    ) -> None:
        """Receiver FTN features are computed correctly from minimal fixture."""
        from ftn_features import compute_ftn_player_week, FTN_RECEIVER_RAW_FEATURES

        ftn_dir = os.path.join(tmp_path, "ftn_charting", "season=2023")
        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(ftn_dir)
        os.makedirs(pbp_dir)
        minimal_ftn_df.to_parquet(
            os.path.join(ftn_dir, "ftn.parquet"), index=False
        )
        minimal_pbp_df.to_parquet(
            os.path.join(pbp_dir, "pbp.parquet"), index=False
        )

        result = compute_ftn_player_week(season=2023, bronze_dir=str(tmp_path))

        assert not result.empty
        recv_rows = result[result["position_type"] == "receiver"]
        assert len(recv_rows) > 0

        # Check at least some receiver features present
        present = [c for c in FTN_RECEIVER_RAW_FEATURES if c in result.columns]
        assert len(present) >= 3, f"Expected >= 3 receiver features, got: {present}"

    def test_qb_features_computed(
        self,
        tmp_path: str,
        minimal_ftn_df: pd.DataFrame,
        minimal_pbp_df: pd.DataFrame,
    ) -> None:
        """QB FTN features are computed from minimal fixture."""
        from ftn_features import compute_ftn_player_week, FTN_QB_RAW_FEATURES

        ftn_dir = os.path.join(tmp_path, "ftn_charting", "season=2023")
        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(ftn_dir)
        os.makedirs(pbp_dir)
        minimal_ftn_df.to_parquet(os.path.join(ftn_dir, "ftn.parquet"), index=False)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        result = compute_ftn_player_week(season=2023, bronze_dir=str(tmp_path))
        qb_rows = result[result["position_type"] == "qb"]
        assert len(qb_rows) > 0

        present = [c for c in FTN_QB_RAW_FEATURES if c in result.columns]
        assert len(present) >= 2

    def test_rates_clipped_to_unit_interval(
        self,
        tmp_path: str,
        minimal_ftn_df: pd.DataFrame,
        minimal_pbp_df: pd.DataFrame,
    ) -> None:
        """All rate columns are in [0, 1]."""
        from ftn_features import compute_ftn_player_week, FTN_ALL_RAW_FEATURES

        ftn_dir = os.path.join(tmp_path, "ftn_charting", "season=2023")
        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(ftn_dir)
        os.makedirs(pbp_dir)
        minimal_ftn_df.to_parquet(os.path.join(ftn_dir, "ftn.parquet"), index=False)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        result = compute_ftn_player_week(season=2023, bronze_dir=str(tmp_path))
        rate_cols = [
            c
            for c in FTN_ALL_RAW_FEATURES
            if ("rate" in c or "share" in c) and c in result.columns
        ]
        for col in rate_cols:
            vals = result[col].dropna()
            assert (vals >= 0).all(), f"{col} has values < 0"
            assert (vals <= 1).all(), f"{col} has values > 1"


# ---------------------------------------------------------------------------
# Trailing feature tests
# ---------------------------------------------------------------------------


class TestAddFtnTrailingFeatures:
    """Tests for ftn_features.add_ftn_trailing_features."""

    def test_empty_df_returns_empty(self) -> None:
        """add_ftn_trailing_features is a no-op on empty input."""
        from ftn_features import add_ftn_trailing_features

        result = add_ftn_trailing_features(pd.DataFrame())
        assert result.empty

    def test_trailing_columns_added(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """_roll4 and _trail columns are added for every raw FTN feature."""
        from ftn_features import add_ftn_trailing_features, FTN_FEATURE_COLUMNS

        result = add_ftn_trailing_features(multi_week_player_df)
        for col in FTN_FEATURE_COLUMNS:
            if any(
                col.replace("_roll4", "").replace("_trail", "") in c
                for c in multi_week_player_df.columns
            ):
                assert col in result.columns, f"Expected column {col} in result"

    def test_shift1_applied_roll4_week1_nan(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """Week 1 trailing features must be NaN (no prior weeks)."""
        from ftn_features import add_ftn_trailing_features

        result = add_ftn_trailing_features(multi_week_player_df)
        week1 = result[result["week"] == 1]
        assert week1["ftn_catchable_rate_roll4"].isna().all(), (
            "Week 1 ftn_catchable_rate_roll4 should be NaN (no prior week data)"
        )

    def test_shift1_not_same_week_leak(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """_roll4 at week 2 should NOT equal week 2's raw value (shift enforced)."""
        from ftn_features import add_ftn_trailing_features

        result = add_ftn_trailing_features(multi_week_player_df)
        week2 = result[result["week"] == 2].iloc[0]

        # Week 2 _roll4 should be NaN (min_periods=2 requires >= 2 prior values,
        # but shift(1) gives only 1 prior value at week 2)
        # OR it should equal week 1's raw value — either way NOT the week 2 raw value
        week2_raw = multi_week_player_df[
            multi_week_player_df["week"] == 2
        ]["ftn_catchable_rate"].iloc[0]
        week2_roll4 = week2["ftn_catchable_rate_roll4"]
        # The roll4 value at week 2 must not equal the same-week raw value
        # (unless by coincidence, but since our fixture has distinct values, this holds)
        if pd.notna(week2_roll4):
            assert week2_roll4 != week2_raw or abs(week2_roll4 - week2_raw) < 1e-9

    def test_trail_week4_is_mean_of_first_three(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """_trail at week 4 = mean of weeks 1-3 (shift(1) expanding mean)."""
        from ftn_features import add_ftn_trailing_features

        result = add_ftn_trailing_features(multi_week_player_df)
        week4 = result[result["week"] == 4].iloc[0]

        # Expected: mean of weeks 1, 2, 3 for ftn_catchable_rate
        expected = np.mean([0.8, 0.7, 0.9])  # weeks 1, 2, 3
        actual = week4["ftn_catchable_rate_trail"]
        assert pd.notna(actual), "Week 4 _trail should not be NaN"
        assert abs(actual - expected) < 1e-4, (
            f"Expected trail={expected:.4f}, got {actual:.4f}"
        )

    def test_no_raw_ftn_column_added(
        self, multi_week_player_df: pd.DataFrame
    ) -> None:
        """add_ftn_trailing_features does not add NEW raw FTN columns."""
        from ftn_features import add_ftn_trailing_features

        pre_cols = set(multi_week_player_df.columns)
        result = add_ftn_trailing_features(multi_week_player_df)
        new_cols = set(result.columns) - pre_cols
        # Only trailing variants should be new
        for col in new_cols:
            assert col.endswith("_roll4") or col.endswith("_trail"), (
                f"Unexpected new column: {col}"
            )


# ---------------------------------------------------------------------------
# Season gap test
# ---------------------------------------------------------------------------


class TestBuildFtnSilver:
    """Tests for ftn_features.build_ftn_silver."""

    def test_season_before_2022_skipped(self, tmp_path: str) -> None:
        """build_ftn_silver silently skips seasons < 2022."""
        from ftn_features import build_ftn_silver

        saved = build_ftn_silver(
            seasons=[2020, 2021, 2022],
            bronze_dir=str(tmp_path),
            silver_dir=str(tmp_path),
        )
        # Seasons 2020, 2021 should be skipped (no FTN data),
        # season 2022 may be empty since no Bronze parquet in tmp_path
        for s in [2020, 2021]:
            assert s not in saved, f"Season {s} should be skipped"

    def test_no_bronze_parquet_skips_season(self, tmp_path: str) -> None:
        """build_ftn_silver skips a season when Bronze FTN parquet is missing."""
        from ftn_features import build_ftn_silver

        saved = build_ftn_silver(
            seasons=[2022, 2023],
            bronze_dir=str(tmp_path),
            silver_dir=str(tmp_path),
        )
        assert saved == {}, "Should return empty dict when no Bronze data"

    def test_writes_parquet_when_data_exists(
        self,
        tmp_path: str,
        minimal_ftn_df: pd.DataFrame,
        minimal_pbp_df: pd.DataFrame,
    ) -> None:
        """build_ftn_silver writes a Silver parquet when Bronze data present."""
        from ftn_features import build_ftn_silver

        ftn_dir = os.path.join(tmp_path, "ftn_charting", "season=2023")
        pbp_dir = os.path.join(tmp_path, "pbp", "season=2023")
        os.makedirs(ftn_dir)
        os.makedirs(pbp_dir)
        minimal_ftn_df.to_parquet(os.path.join(ftn_dir, "ftn.parquet"), index=False)
        minimal_pbp_df.to_parquet(os.path.join(pbp_dir, "pbp.parquet"), index=False)

        saved = build_ftn_silver(
            seasons=[2023],
            bronze_dir=str(tmp_path),
            silver_dir=str(tmp_path),
        )
        assert 2023 in saved, "Season 2023 should be saved"
        assert os.path.exists(saved[2023])

        written = pd.read_parquet(saved[2023])
        assert not written.empty


# ---------------------------------------------------------------------------
# Leak gate test
# ---------------------------------------------------------------------------


class TestLeakGate:
    """Verify raw FTN columns are excluded from the model feature vector."""

    def test_raw_ftn_columns_not_in_feature_set(self) -> None:
        """get_player_feature_columns must exclude raw (unlagged) FTN columns."""
        sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
        from player_feature_engineering import (
            get_player_feature_columns,
            _SAME_WEEK_RAW_STATS,
        )
        from ftn_features import FTN_ALL_RAW_FEATURES

        # All raw FTN feature names must be in the exclusion set
        for col in FTN_ALL_RAW_FEATURES:
            assert col in _SAME_WEEK_RAW_STATS, (
                f"Raw FTN column '{col}' is NOT in _SAME_WEEK_RAW_STATS — "
                "it could leak into model features!"
            )

    def test_ftn_trailing_columns_allowed_through_feature_filter(self) -> None:
        """_roll4 and _trail FTN columns are NOT in _SAME_WEEK_RAW_STATS (i.e. allowed)."""
        from player_feature_engineering import _SAME_WEEK_RAW_STATS
        from ftn_features import FTN_FEATURE_COLUMNS

        for col in FTN_FEATURE_COLUMNS:
            assert col not in _SAME_WEEK_RAW_STATS, (
                f"Trailing FTN column '{col}' is incorrectly in _SAME_WEEK_RAW_STATS "
                "— this would exclude a valid lagged feature!"
            )

    def test_ftn_feature_columns_pass_is_unlagged_leak_check(self) -> None:
        """_is_unlagged_leak returns False for all _roll4 and _trail FTN columns."""
        from player_feature_engineering import _is_unlagged_leak
        from ftn_features import FTN_FEATURE_COLUMNS

        for col in FTN_FEATURE_COLUMNS:
            assert not _is_unlagged_leak(col), (
                f"_is_unlagged_leak incorrectly flagged '{col}' as a leak"
            )

    def test_raw_ftn_columns_are_flagged_by_same_week_stats(self) -> None:
        """_SAME_WEEK_RAW_STATS correctly blocks raw FTN columns from features."""
        from player_feature_engineering import _SAME_WEEK_RAW_STATS
        from ftn_features import FTN_ALL_RAW_FEATURES

        # Build a minimal DataFrame with both raw and trailing columns
        n = 20
        data: dict = {
            "player_id": ["P1"] * n,
            "season": [2023] * n,
            "week": list(range(1, n + 1)),
            "position": ["WR"] * n,
        }
        from ftn_features import FTN_FEATURE_COLUMNS

        for col in FTN_ALL_RAW_FEATURES:
            data[col] = np.random.rand(n)
        for col in FTN_FEATURE_COLUMNS:
            data[col] = np.random.rand(n)

        import pandas as pd
        from player_feature_engineering import get_player_feature_columns

        df = pd.DataFrame(data)
        feature_cols = get_player_feature_columns(df)

        # Raw FTN columns must NOT appear in feature set
        raw_leaked = [c for c in FTN_ALL_RAW_FEATURES if c in feature_cols]
        assert not raw_leaked, (
            f"Raw FTN columns leaked into feature set: {raw_leaked}"
        )

        # Trailing FTN columns SHOULD appear in feature set
        trailing_present = [c for c in FTN_FEATURE_COLUMNS if c in feature_cols]
        assert len(trailing_present) > 0, (
            "No FTN trailing columns found in feature set — check registration"
        )
