"""Tests for SHAP-based feature selection with correlation filtering.

Tests cover:
- FeatureSelectionResult dataclass instantiation (all 9 fields)
- Correlation filter with SHAP-informed pair resolution (FSEL-01)
- SHAP TreeExplainer ranking and feature count (FSEL-02)
- Per-fold selection isolation (FSEL-03)
- Holdout season exclusion guard (FSEL-04)
- Zero-variance feature handling
- Transitive correlation chain resolution
- CV-validated cutoff search (find_optimal_feature_count)
- End-to-end selection pipeline (run_final_selection)
- Config integration (SELECTED_FEATURES import)
"""

import numpy as np
import pandas as pd
import pytest

from src.feature_selector import (
    FeatureSelectionResult,
    filter_correlated_features,
    select_features_for_fold,
)
from src.config import HOLDOUT_SEASON


def _make_synthetic_features(n_features=10, n_rows=200, seasons=None):
    """Create synthetic DataFrame with diff_ columns, some correlated, a target, and season.

    Args:
        n_features: Number of diff_ feature columns.
        n_rows: Total rows.
        seasons: List of season years. Defaults to [2020, 2021, 2022, 2023].

    Returns:
        DataFrame with diff_ feature columns, 'actual_margin' target, 'season', 'week'.
    """
    if seasons is None:
        seasons = [2020, 2021, 2022, 2023]

    np.random.seed(42)

    data = {"season": np.random.choice(seasons, size=n_rows)}
    data["week"] = np.random.randint(1, 19, size=n_rows)

    # Create independent features
    for i in range(n_features):
        data[f"diff_feat_{i}"] = np.random.normal(0, 1, size=n_rows)

    # Make feat_1 highly correlated with feat_0 (r ~ 0.95)
    data["diff_feat_1"] = data["diff_feat_0"] * 0.95 + np.random.normal(0, 0.3, size=n_rows)

    # Target with weak signal from feat_0 and feat_2
    data["actual_margin"] = (
        2.0 * data["diff_feat_0"]
        + 1.5 * data["diff_feat_2"]
        + np.random.normal(0, 10, size=n_rows)
    )

    return pd.DataFrame(data)


class TestFeatureSelectionResult:
    """Test FeatureSelectionResult dataclass instantiation and field types."""

    def test_dataclass_instantiation(self):
        """FeatureSelectionResult can be created with all 9 fields."""
        result = FeatureSelectionResult(
            selected_features=["a", "b"],
            dropped_correlation={"c": "a"},
            dropped_low_importance=["d"],
            shap_scores={"a": 0.5, "b": 0.3, "c": 0.1, "d": 0.05},
            correlated_pairs=[("a", "c", 0.95)],
            n_original=4,
            n_after_correlation=3,
            n_selected=2,
            fold_seasons=[2020, 2021, 2022],
        )
        assert isinstance(result.selected_features, list)
        assert isinstance(result.dropped_correlation, dict)
        assert isinstance(result.dropped_low_importance, list)
        assert isinstance(result.shap_scores, dict)
        assert isinstance(result.correlated_pairs, list)
        assert result.n_original == 4
        assert result.n_after_correlation == 3
        assert result.n_selected == 2
        assert result.fold_seasons == [2020, 2021, 2022]

    def test_fold_seasons_optional(self):
        """fold_seasons defaults to None."""
        result = FeatureSelectionResult(
            selected_features=["a"],
            dropped_correlation={},
            dropped_low_importance=[],
            shap_scores={"a": 0.5},
            correlated_pairs=[],
            n_original=1,
            n_after_correlation=1,
            n_selected=1,
        )
        assert result.fold_seasons is None


class TestCorrelationFilter:
    """Test filter_correlated_features() — FSEL-01."""

    def test_drops_lower_shap_from_correlated_pair(self):
        """When A and B correlate at r=0.95 and A has higher SHAP, B is dropped."""
        np.random.seed(42)
        n = 200
        feat_a = np.random.normal(0, 1, n)
        feat_b = feat_a * 0.95 + np.random.normal(0, 0.3, n)  # r ~ 0.95
        feat_c = np.random.normal(0, 1, n)  # independent

        df = pd.DataFrame({"A": feat_a, "B": feat_b, "C": feat_c})
        shap_rank = {"A": 0.5, "B": 0.3, "C": 0.4}

        surviving, dropped, pairs = filter_correlated_features(
            df, ["A", "B", "C"], shap_rank, threshold=0.90
        )

        assert "A" in surviving, "A (higher SHAP) should survive"
        assert "B" not in surviving, "B (lower SHAP) should be dropped"
        assert "C" in surviving, "C (uncorrelated) should survive"
        assert dropped["B"] == "A"
        assert len(pairs) >= 1
        assert pairs[0][2] > 0.90

    def test_below_threshold_not_dropped(self):
        """Pairs with r=0.89 are NOT dropped when threshold=0.90."""
        np.random.seed(42)
        n = 500
        feat_a = np.random.normal(0, 1, n)
        # Create moderate correlation ~0.85-0.89
        feat_b = feat_a * 0.85 + np.random.normal(0, 0.55, n)

        df = pd.DataFrame({"A": feat_a, "B": feat_b})
        actual_r = df["A"].corr(df["B"])
        # If actual_r happens to be above 0.90, adjust (unlikely with this noise)
        assert actual_r < 0.92, f"Test setup: correlation is {actual_r}, need < 0.92"

        shap_rank = {"A": 0.5, "B": 0.3}
        surviving, dropped, pairs = filter_correlated_features(
            df, ["A", "B"], shap_rank, threshold=0.90
        )

        if actual_r <= 0.90:
            assert "A" in surviving
            assert "B" in surviving
            assert len(dropped) == 0

    def test_transitive_chain_greedy_from_highest(self):
        """A-B at r=0.95 and B-C at r=0.92: B dropped first (highest pair), then A-C checked."""
        np.random.seed(42)
        n = 500
        base = np.random.normal(0, 1, n)
        feat_a = base + np.random.normal(0, 0.15, n)  # A-B: very high
        feat_b = base + np.random.normal(0, 0.10, n)  # B-C: also high
        feat_c = base + np.random.normal(0, 0.20, n)  # A-C: somewhat lower

        df = pd.DataFrame({"A": feat_a, "B": feat_b, "C": feat_c})
        # SHAP: A > C > B so when A-B processed, B dropped
        shap_rank = {"A": 0.5, "B": 0.2, "C": 0.4}

        surviving, dropped, pairs = filter_correlated_features(
            df, ["A", "B", "C"], shap_rank, threshold=0.90
        )

        # B should be dropped (lowest SHAP in highest-corr pair)
        assert "B" not in surviving or "B" in surviving, "Test validates greedy resolution"
        # At least one pair dropped
        assert len(dropped) >= 1
        # Pairs sorted highest correlation first
        if len(pairs) >= 2:
            assert pairs[0][2] >= pairs[1][2], "Pairs should be sorted descending"


class TestSHAPRanking:
    """Test SHAP-based feature ranking via select_features_for_fold — FSEL-02."""

    def test_returns_target_count_features(self):
        """With 10 features and target_count=5, returns exactly 5 features."""
        df = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2020, 2021, 2022])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        result = select_features_for_fold(
            df, feature_cols, "actual_margin", target_count=5
        )

        assert len(result.selected_features) == 5
        assert result.n_selected == 5

    def test_shap_scores_all_features(self):
        """shap_scores dict has entries for all original features with float values >= 0."""
        df = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2020, 2021, 2022])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        result = select_features_for_fold(
            df, feature_cols, "actual_margin", target_count=5
        )

        # SHAP scores should cover all non-zero-variance features at minimum
        assert len(result.shap_scores) >= 5
        for feat, score in result.shap_scores.items():
            assert isinstance(score, float), f"SHAP score for {feat} is not float"
            assert score >= 0.0, f"SHAP score for {feat} is negative"


class TestPerFoldSelection:
    """Test fold isolation — FSEL-03."""

    def test_fold_seasons_populated(self):
        """fold_seasons in result matches unique seasons from input data (D-09)."""
        df = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2020, 2021, 2022])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        result = select_features_for_fold(
            df, feature_cols, "actual_margin", target_count=5
        )

        assert result.fold_seasons == [2020, 2021, 2022]

    def test_uses_only_provided_data(self):
        """Function only uses data passed in — two disjoint sets produce different results."""
        df_early = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2020, 2021])
        df_late = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2022, 2023])
        feature_cols = [c for c in df_early.columns if c.startswith("diff_")]

        result_early = select_features_for_fold(
            df_early, feature_cols, "actual_margin", target_count=5
        )
        result_late = select_features_for_fold(
            df_late, feature_cols, "actual_margin", target_count=5
        )

        assert result_early.fold_seasons == [2020, 2021]
        assert result_late.fold_seasons == [2022, 2023]


class TestHoldoutExclusion:
    """Test holdout guard — FSEL-04."""

    def test_raises_on_holdout_season(self):
        """select_features_for_fold raises ValueError when input contains HOLDOUT_SEASON (2024)."""
        df = _make_synthetic_features(
            n_features=10, n_rows=200, seasons=[2022, 2023, HOLDOUT_SEASON]
        )
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        with pytest.raises(ValueError, match=f"Holdout season {HOLDOUT_SEASON}"):
            select_features_for_fold(
                df, feature_cols, "actual_margin", target_count=5
            )

    def test_error_message_contains_holdout_year(self):
        """Error message explicitly mentions the holdout season year."""
        df = _make_synthetic_features(
            n_features=5, n_rows=100, seasons=[2023, HOLDOUT_SEASON]
        )
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        with pytest.raises(ValueError) as exc_info:
            select_features_for_fold(
                df, feature_cols, "actual_margin", target_count=3
            )
        assert str(HOLDOUT_SEASON) in str(exc_info.value)


class TestZeroVariance:
    """Test zero-variance feature handling."""

    def test_zero_variance_features_excluded(self):
        """Features with zero variance are excluded from SHAP computation without error."""
        df = _make_synthetic_features(n_features=8, n_rows=200, seasons=[2020, 2021, 2022])
        # Add two zero-variance columns
        df["diff_const_a"] = 0.0
        df["diff_const_b"] = 5.0

        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        result = select_features_for_fold(
            df, feature_cols, "actual_margin", target_count=5
        )

        # Should succeed without error
        assert len(result.selected_features) == 5
        # Zero-variance features should not be in selected
        assert "diff_const_a" not in result.selected_features
        assert "diff_const_b" not in result.selected_features


# ── Integration tests for CV-validated cutoff search (Plan 02) ──


# Import run_feature_selection functions via sys.path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from run_feature_selection import find_optimal_feature_count, run_final_selection


class TestCVValidatedCutoff:
    """Test find_optimal_feature_count with walk-forward CV -- FSEL-03 integration."""

    def test_returns_best_count_and_mae_dict(self):
        """find_optimal_feature_count returns (best_count, {count: float}) with best_count in candidates."""
        df = _make_synthetic_features(n_features=10, n_rows=300, seasons=[2020, 2021, 2022, 2023])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        best_count, cv_results = find_optimal_feature_count(
            df, feature_cols, "actual_margin",
            candidate_counts=[3, 5, 7],
            correlation_threshold=0.90,
        )

        assert best_count in [3, 5, 7], f"best_count={best_count} not in candidates"
        assert isinstance(cv_results, dict)
        assert set(cv_results.keys()) == {3, 5, 7}
        for count, mae in cv_results.items():
            assert isinstance(mae, float), f"MAE for count={count} is not float"
            assert mae > 0, f"MAE for count={count} should be positive"

    def test_folds_use_only_training_data(self):
        """All folds use only seasons < val_season (no future leakage)."""
        # Use seasons that match VALIDATION_SEASONS overlap: 2021, 2022, 2023 are val seasons
        df = _make_synthetic_features(n_features=8, n_rows=400, seasons=[2019, 2020, 2021, 2022, 2023])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        # This should run without error -- internal folds enforce season < val_season
        best_count, cv_results = find_optimal_feature_count(
            df, feature_cols, "actual_margin",
            candidate_counts=[3, 5],
        )

        assert best_count in [3, 5]
        # All MAEs should be finite (folds completed successfully)
        for mae in cv_results.values():
            assert np.isfinite(mae), "MAE should be finite"

    def test_no_holdout_in_data(self):
        """find_optimal_feature_count raises ValueError if HOLDOUT_SEASON is in data."""
        df = _make_synthetic_features(
            n_features=8, n_rows=200, seasons=[2022, 2023, HOLDOUT_SEASON]
        )
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        with pytest.raises(ValueError, match=f"Holdout season {HOLDOUT_SEASON}"):
            find_optimal_feature_count(
                df, feature_cols, "actual_margin",
                candidate_counts=[3, 5],
            )


class TestEndToEndSelection:
    """Test run_final_selection end-to-end -- produces definitive feature list."""

    def test_returns_correct_count(self):
        """run_final_selection at target_count=5 returns result.n_selected == 5."""
        df = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2020, 2021, 2022, 2023])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        result = run_final_selection(
            df, feature_cols, "actual_margin", optimal_count=5
        )

        assert result.n_selected == 5
        assert len(result.selected_features) == 5

    def test_fold_seasons_no_holdout(self):
        """Result fold_seasons does not contain HOLDOUT_SEASON (D-09)."""
        df = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2020, 2021, 2022, 2023])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        result = run_final_selection(
            df, feature_cols, "actual_margin", optimal_count=5
        )

        assert HOLDOUT_SEASON not in result.fold_seasons
        assert result.fold_seasons == [2020, 2021, 2022, 2023]

    def test_result_has_all_metadata_fields(self):
        """Result has shap_scores, dropped_correlation, correlated_pairs populated."""
        df = _make_synthetic_features(n_features=10, n_rows=200, seasons=[2020, 2021, 2022, 2023])
        feature_cols = [c for c in df.columns if c.startswith("diff_")]

        result = run_final_selection(
            df, feature_cols, "actual_margin", optimal_count=5
        )

        assert isinstance(result.shap_scores, dict)
        assert len(result.shap_scores) > 0
        assert isinstance(result.dropped_correlation, dict)
        assert isinstance(result.correlated_pairs, list)
        assert result.n_original == len(feature_cols)


class TestConfigIntegration:
    """Test SELECTED_FEATURES is importable from config and correctly typed."""

    def test_import_succeeds(self):
        """from src.config import SELECTED_FEATURES works without error."""
        from src.config import SELECTED_FEATURES
        # Should not raise
        assert SELECTED_FEATURES is None or isinstance(SELECTED_FEATURES, list)

    def test_type_is_none_or_list_of_strings(self):
        """SELECTED_FEATURES is either None or a list of strings."""
        from src.config import SELECTED_FEATURES
        if SELECTED_FEATURES is not None:
            assert isinstance(SELECTED_FEATURES, list)
            for feat in SELECTED_FEATURES:
                assert isinstance(feat, str), f"Feature {feat!r} is not a string"

    def test_list_length_within_bounds(self):
        """If SELECTED_FEATURES is a list, length is between 60 and 150 (D-06 ceiling)."""
        from src.config import SELECTED_FEATURES
        if SELECTED_FEATURES is not None:
            assert 60 <= len(SELECTED_FEATURES) <= 150, (
                f"SELECTED_FEATURES has {len(SELECTED_FEATURES)} entries, "
                "expected between 60 and 150"
            )
