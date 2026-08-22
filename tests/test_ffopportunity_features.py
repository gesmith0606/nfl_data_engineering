"""Tests for ffopportunity EP trailing features (src/ffopportunity_features.py).

Covers:
    - Raw player-week loading + total_opportunities derivation from a
      minimal Silver fixture
    - Trailing feature computation: shift(1) enforcement (short-history
      NaN, no same-week leak, trail = mean of prior weeks, roll3/roll5
      window math)
    - Empty-history / missing-Silver fail-safe (no crash, no fabricated
      signal)
    - Join correctness end-to-end via
      build_ffopportunity_features_for_season and the
      player_feature_engineering._join_ffopportunity_features wiring
    - Leak gate: no raw ffopportunity column appears in
      get_player_feature_columns output; trailing columns pass
      _is_unlagged_leak
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


def _write_silver_fixture(tmp_path, season: int, rows: dict) -> str:
    season_dir = os.path.join(str(tmp_path), "ffopportunity_features", f"season={season}")
    os.makedirs(season_dir, exist_ok=True)
    df = pd.DataFrame(rows)
    path = os.path.join(season_dir, f"ffopportunity_features_{season}.parquet")
    df.to_parquet(path, index=False)
    return path


@pytest.fixture
def four_week_silver_rows() -> dict:
    """4 weeks of one player: targets/carries/pass_attempts + EP columns."""
    return {
        "player_id": ["P1"] * 4,
        "season": [2023] * 4,
        "week": [1, 2, 3, 4],
        "team": ["BUF"] * 4,
        "position": ["RB"] * 4,
        "pass_attempts": [0, 0, 0, 0],
        "targets": [2, 4, 3, 5],
        "carries": [10, 12, 8, 14],
        "exp_fantasy_points_total": [8.0, 10.0, 6.0, 12.0],
        "fantasy_points_over_expected": [1.0, -2.0, 3.0, 0.5],
    }


# ---------------------------------------------------------------------------
# Raw computation tests
# ---------------------------------------------------------------------------


class TestComputeFfopportunityPlayerWeek:
    def test_missing_silver_returns_empty(self, tmp_path) -> None:
        from ffopportunity_features import compute_ffopportunity_player_week

        result = compute_ffopportunity_player_week(season=2023, silver_dir=str(tmp_path))
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_total_opportunities_derived_correctly(
        self, tmp_path, four_week_silver_rows: dict
    ) -> None:
        from ffopportunity_features import compute_ffopportunity_player_week

        _write_silver_fixture(tmp_path, 2023, four_week_silver_rows)
        result = compute_ffopportunity_player_week(season=2023, silver_dir=str(tmp_path))

        assert "total_opportunities" in result.columns
        # week 1: 0 pass_attempts + 2 targets + 10 carries = 12
        assert result.loc[result["week"] == 1, "total_opportunities"].iat[0] == 12
        # week 4: 0 + 5 + 14 = 19
        assert result.loc[result["week"] == 4, "total_opportunities"].iat[0] == 19

    def test_missing_opportunity_columns_returns_empty(self, tmp_path) -> None:
        """Silver schema without targets/carries/pass_attempts -> empty, no crash."""
        from ffopportunity_features import compute_ffopportunity_player_week

        _write_silver_fixture(
            tmp_path,
            2023,
            {"player_id": ["P1"], "season": [2023], "week": [1]},
        )
        result = compute_ffopportunity_player_week(season=2023, silver_dir=str(tmp_path))
        assert result.empty


# ---------------------------------------------------------------------------
# Trailing feature (leak) tests
# ---------------------------------------------------------------------------


class TestAddFfopportunityTrailingFeatures:
    def test_empty_df_returns_empty(self) -> None:
        from ffopportunity_features import add_ffopportunity_trailing_features

        result = add_ffopportunity_trailing_features(pd.DataFrame())
        assert result.empty

    def test_missing_key_columns_returns_input_unchanged(self) -> None:
        from ffopportunity_features import add_ffopportunity_trailing_features

        df = pd.DataFrame({"foo": [1, 2, 3]})
        result = add_ffopportunity_trailing_features(df)
        assert list(result.columns) == ["foo"]

    def test_short_history_is_nan_fail_safe(
        self, four_week_silver_rows: dict
    ) -> None:
        """Weeks 1-2 have <2 shifted prior observations -> NaN (min_periods=2)."""
        from ffopportunity_features import (
            add_ffopportunity_trailing_features,
            compute_ffopportunity_player_week,
        )

        raw = pd.DataFrame(four_week_silver_rows)
        raw["total_opportunities"] = (
            raw["pass_attempts"] + raw["targets"] + raw["carries"]
        )
        result = add_ffopportunity_trailing_features(raw)

        week1 = result[result["week"] == 1].iloc[0]
        week2 = result[result["week"] == 2].iloc[0]
        assert pd.isna(week1["ffopp_exp_fantasy_points_total_roll3"])
        assert pd.isna(week1["ffopp_exp_fantasy_points_total_trail"])
        # week 2 has exactly 1 shifted prior obs -- still below min_periods=2
        assert pd.isna(week2["ffopp_exp_fantasy_points_total_roll3"])

    def test_no_same_week_leak(self, four_week_silver_rows: dict) -> None:
        from ffopportunity_features import add_ffopportunity_trailing_features

        raw = pd.DataFrame(four_week_silver_rows)
        raw["total_opportunities"] = (
            raw["pass_attempts"] + raw["targets"] + raw["carries"]
        )
        result = add_ffopportunity_trailing_features(raw)

        week3 = result[result["week"] == 3].iloc[0]
        week3_raw = raw[raw["week"] == 3]["exp_fantasy_points_total"].iat[0]
        assert pd.isna(week3["ffopp_exp_fantasy_points_total_roll3"]) or (
            week3["ffopp_exp_fantasy_points_total_roll3"] != week3_raw
        )

    def test_trail_week4_is_mean_of_first_three(
        self, four_week_silver_rows: dict
    ) -> None:
        from ffopportunity_features import add_ffopportunity_trailing_features

        raw = pd.DataFrame(four_week_silver_rows)
        raw["total_opportunities"] = (
            raw["pass_attempts"] + raw["targets"] + raw["carries"]
        )
        result = add_ffopportunity_trailing_features(raw)

        week4 = result[result["week"] == 4].iloc[0]
        expected = np.mean([8.0, 10.0, 6.0])
        assert week4["ffopp_exp_fantasy_points_total_trail"] == pytest.approx(expected)

    def test_roll3_week4_is_mean_of_weeks_1_to_3(
        self, four_week_silver_rows: dict
    ) -> None:
        """roll3 at week 4 = mean of the 3 shifted prior weeks (1,2,3)."""
        from ffopportunity_features import add_ffopportunity_trailing_features

        raw = pd.DataFrame(four_week_silver_rows)
        raw["total_opportunities"] = (
            raw["pass_attempts"] + raw["targets"] + raw["carries"]
        )
        result = add_ffopportunity_trailing_features(raw)

        week4 = result[result["week"] == 4].iloc[0]
        expected = np.mean([8.0, 10.0, 6.0])
        assert week4["ffopp_exp_fantasy_points_total_roll3"] == pytest.approx(expected)

    def test_fantasy_points_over_expected_trailing_computed(
        self, four_week_silver_rows: dict
    ) -> None:
        from ffopportunity_features import add_ffopportunity_trailing_features

        raw = pd.DataFrame(four_week_silver_rows)
        raw["total_opportunities"] = (
            raw["pass_attempts"] + raw["targets"] + raw["carries"]
        )
        result = add_ffopportunity_trailing_features(raw)

        week4 = result[result["week"] == 4].iloc[0]
        expected = np.mean([1.0, -2.0, 3.0])
        assert week4["ffopp_fantasy_points_over_expected_trail"] == pytest.approx(
            expected
        )

    def test_volume_ablation_columns_computed(
        self, four_week_silver_rows: dict
    ) -> None:
        """Ablation-control (volume-only) trailing columns are also produced."""
        from ffopportunity_features import add_ffopportunity_trailing_features

        raw = pd.DataFrame(four_week_silver_rows)
        raw["total_opportunities"] = (
            raw["pass_attempts"] + raw["targets"] + raw["carries"]
        )
        result = add_ffopportunity_trailing_features(raw)

        week4 = result[result["week"] == 4].iloc[0]
        expected_targets_trail = np.mean([2, 4, 3])
        assert week4["ffopp_vol_targets_trail"] == pytest.approx(expected_targets_trail)

    def test_no_unexpected_new_columns(self, four_week_silver_rows: dict) -> None:
        from ffopportunity_features import add_ffopportunity_trailing_features

        raw = pd.DataFrame(four_week_silver_rows)
        raw["total_opportunities"] = (
            raw["pass_attempts"] + raw["targets"] + raw["carries"]
        )
        pre_cols = set(raw.columns)
        result = add_ffopportunity_trailing_features(raw)
        new_cols = set(result.columns) - pre_cols
        for col in new_cols:
            assert col.endswith(("_roll3", "_roll5", "_trail")), (
                f"Unexpected new column: {col}"
            )


# ---------------------------------------------------------------------------
# build_ffopportunity_features_for_season / end-to-end join tests
# ---------------------------------------------------------------------------


class TestBuildFfopportunityFeaturesForSeason:
    def test_missing_season_returns_empty(self, tmp_path) -> None:
        from ffopportunity_features import build_ffopportunity_features_for_season

        result = build_ffopportunity_features_for_season(2023, silver_dir=str(tmp_path))
        assert result.empty

    def test_returns_keys_plus_ep_columns_by_default(
        self, tmp_path, four_week_silver_rows: dict
    ) -> None:
        from ffopportunity_features import (
            FFOPPORTUNITY_EP_FEATURE_COLUMNS,
            FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS,
            build_ffopportunity_features_for_season,
        )

        _write_silver_fixture(tmp_path, 2023, four_week_silver_rows)
        result = build_ffopportunity_features_for_season(2023, silver_dir=str(tmp_path))

        assert not result.empty
        for col in ["player_id", "season", "week"]:
            assert col in result.columns
        assert any(c in result.columns for c in FFOPPORTUNITY_EP_FEATURE_COLUMNS)
        # Ablation columns excluded by default (include_ablation=False is the
        # production-join default; this call uses the function default=True,
        # so it SHOULD include them here)
        assert any(c in result.columns for c in FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS)

    def test_include_ablation_false_excludes_volume_columns(
        self, tmp_path, four_week_silver_rows: dict
    ) -> None:
        from ffopportunity_features import (
            FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS,
            build_ffopportunity_features_for_season,
        )

        _write_silver_fixture(tmp_path, 2023, four_week_silver_rows)
        result = build_ffopportunity_features_for_season(
            2023, silver_dir=str(tmp_path), include_ablation=False
        )
        assert not any(c in result.columns for c in FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS)


class TestJoinWiring:
    def test_join_ffopportunity_features_missing_silver_nan_fills(self) -> None:
        """No Silver data at all -> join is a no-op that NaN-fills the schema."""
        from player_feature_engineering import _join_ffopportunity_features
        from ffopportunity_features import FFOPPORTUNITY_EP_FEATURE_COLUMNS

        df = pd.DataFrame(
            {
                "player_id": ["P1", "P2"],
                "season": [2099, 2099],
                "week": [1, 1],
            }
        )
        result = _join_ffopportunity_features(df, season=2099)
        for col in FFOPPORTUNITY_EP_FEATURE_COLUMNS:
            assert col in result.columns
            assert result[col].isna().all()

    def test_join_ffopportunity_features_merges_real_rows(self, tmp_path, monkeypatch) -> None:
        from ffopportunity_features import FFOPPORTUNITY_EP_FEATURE_COLUMNS

        rows = {
            "player_id": ["P1"] * 5,
            "season": [2023] * 5,
            "week": [1, 2, 3, 4, 5],
            "team": ["BUF"] * 5,
            "position": ["WR"] * 5,
            "pass_attempts": [0] * 5,
            "targets": [4, 6, 5, 7, 8],
            "carries": [0] * 5,
            "exp_fantasy_points_total": [5.0, 6.0, 4.0, 7.0, 9.0],
            "fantasy_points_over_expected": [0.5, -1.0, 2.0, 0.0, 1.5],
        }
        _write_silver_fixture(tmp_path, 2023, rows)

        import ffopportunity_features as ff

        monkeypatch.setattr(ff, "_default_silver_dir", lambda: str(tmp_path))

        import player_feature_engineering as pfe

        df = pd.DataFrame(
            {
                "player_id": ["P1"] * 5,
                "season": [2023] * 5,
                "week": [1, 2, 3, 4, 5],
            }
        )
        result = pfe._join_ffopportunity_features(df, season=2023)

        # Week 5 should have a real (non-NaN) trailing value -- 4 prior weeks
        # of history clears min_periods=2.
        week5 = result[result["week"] == 5].iloc[0]
        assert pd.notna(week5["ffopp_exp_fantasy_points_total_trail"])
        expected = np.mean([5.0, 6.0, 4.0, 7.0])
        assert week5["ffopp_exp_fantasy_points_total_trail"] == pytest.approx(expected)
        # Week 1 must be NaN (no prior weeks) -- leak-safety at the join level too.
        week1 = result[result["week"] == 1].iloc[0]
        assert pd.isna(week1["ffopp_exp_fantasy_points_total_trail"])
        for col in FFOPPORTUNITY_EP_FEATURE_COLUMNS:
            assert col in result.columns


# ---------------------------------------------------------------------------
# Leak gate test (must-pass, matches the pbp_advanced_features precedent)
# ---------------------------------------------------------------------------


class TestLeakGate:
    def test_trailing_columns_pass_is_unlagged_leak_check(self) -> None:
        from player_feature_engineering import _is_unlagged_leak
        from ffopportunity_features import FFOPPORTUNITY_EP_FEATURE_COLUMNS

        for col in FFOPPORTUNITY_EP_FEATURE_COLUMNS:
            assert not _is_unlagged_leak(col), (
                f"_is_unlagged_leak incorrectly flagged '{col}' as a leak"
            )

    def test_raw_columns_never_appear_in_join_output(self) -> None:
        """The join only ever returns trailing columns -- raw ffopp columns
        (exp_fantasy_points_total, fantasy_points_over_expected,
        total_opportunities) must never appear unlagged in the joined df."""
        from player_feature_engineering import _join_ffopportunity_features

        df = pd.DataFrame(
            {"player_id": ["P1"], "season": [2099], "week": [1]}
        )
        result = _join_ffopportunity_features(df, season=2099)
        for raw_col in (
            "exp_fantasy_points_total",
            "fantasy_points_over_expected",
            "total_opportunities",
        ):
            assert raw_col not in result.columns

    def test_ep_columns_end_to_end_in_feature_set(self) -> None:
        from player_feature_engineering import get_player_feature_columns
        from ffopportunity_features import FFOPPORTUNITY_EP_FEATURE_COLUMNS

        n = 10
        data: dict = {
            "player_id": ["P1"] * n,
            "season": [2023] * n,
            "week": list(range(1, n + 1)),
            "position": ["WR"] * n,
        }
        rng = np.random.default_rng(0)
        for col in FFOPPORTUNITY_EP_FEATURE_COLUMNS:
            data[col] = rng.random(n)

        df = pd.DataFrame(data)
        feature_cols = get_player_feature_columns(df)

        present = [c for c in FFOPPORTUNITY_EP_FEATURE_COLUMNS if c in feature_cols]
        assert len(present) == len(FFOPPORTUNITY_EP_FEATURE_COLUMNS)
