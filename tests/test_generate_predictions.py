"""Tests for the weekly NFL game prediction pipeline.

Tests cover:
- classify_tier() confidence tier classification
- generate_week_predictions() edge computation, sorting, schema
- Missing Vegas line handling
- Independent tier classification
"""

import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import generate_predictions as gp
from generate_predictions import (
    OU_PICK_RETIRED,
    _normalize_prediction_columns,
    classify_tier,
    classify_tier_prob,
    derive_ats_pick,
    generate_week_predictions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_game_features():
    """DataFrame with 4 games for season=2025, week=10."""
    return pd.DataFrame(
        {
            "game_id": [
                "2025_10_KC_BUF",
                "2025_10_SF_DAL",
                "2025_10_PHI_NYG",
                "2025_10_DEN_LV",
            ],
            "season": [2025, 2025, 2025, 2025],
            "week": [10, 10, 10, 10],
            "home_team": ["BUF", "DAL", "NYG", "LV"],
            "away_team": ["KC", "SF", "PHI", "DEN"],
            "spread_line": [-3.0, 1.5, 7.0, float("nan")],
            "total_line": [48.5, 44.0, 40.5, float("nan")],
            "actual_margin": [float("nan")] * 4,
            "actual_total": [float("nan")] * 4,
            "diff_epa_per_play": [0.05, -0.10, 0.20, 0.00],
            "diff_pass_rate": [0.02, -0.05, 0.08, 0.01],
            "diff_rush_yards_per_game": [10.0, -5.0, 15.0, 2.0],
            "diff_third_down_pct": [0.03, -0.02, 0.06, 0.00],
            "diff_turnover_margin": [0.5, -0.3, 1.0, 0.1],
        }
    )


class MockModel:
    """Simple mock that returns fixed prediction values."""

    def __init__(self, values):
        self._values = values

    def predict(self, X):
        return np.array(self._values[: len(X)])


@pytest.fixture
def mock_spread_model():
    """Spread model returning [-3.5, -7.0, 2.5, -1.0]."""
    return MockModel([-3.5, -7.0, 2.5, -1.0])


@pytest.fixture
def mock_total_model():
    """Total model returning [44.5, 48.0, 41.0, 52.5]."""
    return MockModel([44.5, 48.0, 41.0, 52.5])


@pytest.fixture
def mock_metadata():
    """Model metadata with 5 feature names."""
    return {
        "feature_names": [
            "diff_epa_per_play",
            "diff_pass_rate",
            "diff_rush_yards_per_game",
            "diff_third_down_pct",
            "diff_turnover_margin",
        ]
    }


# ---------------------------------------------------------------------------
# classify_tier tests
# ---------------------------------------------------------------------------


class TestClassifyTier:
    def test_classify_tier_high(self):
        assert classify_tier(3.0) == "high"
        assert classify_tier(5.5) == "high"

    def test_classify_tier_medium(self):
        assert classify_tier(1.5) == "medium"
        assert classify_tier(2.9) == "medium"

    def test_classify_tier_low(self):
        assert classify_tier(0.5) == "low"
        assert classify_tier(1.4) == "low"

    def test_classify_tier_nan(self):
        assert classify_tier(float("nan")) is None


class TestClassifyTierProb:
    """Ensemble path: tier = calibrated probability the picked side wins."""

    def test_thresholds_bracket_breakeven(self):
        assert classify_tier_prob(0.56) == "high"
        assert classify_tier_prob(0.53) == "medium"
        # -110 breakeven is 52.4%: anything at or below it is low.
        assert classify_tier_prob(0.524) == "low"
        assert classify_tier_prob(0.50) == "low"

    def test_nan(self):
        assert classify_tier_prob(float("nan")) is None

    def test_big_edge_without_skill_is_low(self):
        # The shipped totals calibrator maps a 5-pt edge to ~0.495: a large
        # raw edge must not be advertised as confidence.
        assert classify_tier(5.0) == "high"
        assert classify_tier_prob(0.505) == "low"


# ---------------------------------------------------------------------------
# generate_week_predictions tests
# ---------------------------------------------------------------------------


class TestGenerateWeekPredictions:
    def test_predictions_generated(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        assert len(result) == 4

    def test_edge_computation(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        # Game 0: KC@BUF — spread: model=-3.5, vegas=-3.0 => edge=-0.5
        kc_buf = result[result["game_id"] == "2025_10_KC_BUF"].iloc[0]
        assert kc_buf["spread_edge"] == pytest.approx(-0.5)
        # Game 0: total: model=44.5, vegas=48.5 => edge=-4.0
        assert kc_buf["total_edge"] == pytest.approx(-4.0)

        # Game 1: SF@DAL — spread: model=-7.0, vegas=1.5 => edge=-8.5
        sf_dal = result[result["game_id"] == "2025_10_SF_DAL"].iloc[0]
        assert sf_dal["spread_edge"] == pytest.approx(-8.5)
        # total: model=48.0, vegas=44.0 => edge=4.0
        assert sf_dal["total_edge"] == pytest.approx(4.0)

    def test_missing_vegas_lines(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        den_lv = result[result["game_id"] == "2025_10_DEN_LV"].iloc[0]
        assert pd.isna(den_lv["spread_edge"])
        assert pd.isna(den_lv["total_edge"])
        # confidence_tier should be "low" when edges are NaN (collapsed tier)
        assert den_lv["confidence_tier"] == "low"

    def test_confidence_tier_is_the_spread_tier(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        """Confidence tier describes the ATS pick -- the only pick served."""
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        # SF@DAL: spread_edge=-8.5 (high), total_edge=4.0 (high) => high
        sf_dal = result[result["game_id"] == "2025_10_SF_DAL"].iloc[0]
        assert sf_dal["confidence_tier"] == "high"

        # PHI@NYG: spread_edge=-4.5 (high), total_edge=0.5 (low) => high
        phi_nyg = result[result["game_id"] == "2025_10_PHI_NYG"].iloc[0]
        assert phi_nyg["confidence_tier"] == "high"

        # KC@BUF: spread_edge=-0.5 (low), total_edge=-4.0 (high) => LOW.
        # This is the case the old max(spread, total) collapse got wrong: a
        # retired totals edge badged the game "high" next to an ATS pick with
        # half a point of edge. Reverting makes this assertion fail.
        kc_buf = result[result["game_id"] == "2025_10_KC_BUF"].iloc[0]
        assert kc_buf["spread_edge"] == pytest.approx(-0.5)
        assert abs(kc_buf["total_edge"]) >= 3.0
        assert kc_buf["confidence_tier"] == "low"

    def test_output_schema(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        expected_cols = {
            "game_id",
            "season",
            "week",
            "home_team",
            "away_team",
            "predicted_spread",
            "predicted_total",
            "vegas_spread",
            "vegas_total",
            "spread_edge",
            "total_edge",
            "confidence_tier",
            "ats_pick",
            "ou_pick",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_sort_by_max_edge(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        # Games with NaN edges (DEN@LV) should be last
        assert result.iloc[-1]["game_id"] == "2025_10_DEN_LV"

        # Remaining games sorted by max(abs(spread_edge), abs(total_edge)) desc
        # SF@DAL: max(8.5, 4.0) = 8.5
        # PHI@NYG: max(4.5, 0.5) = 4.5
        # KC@BUF: max(0.5, 4.0) = 4.0
        non_nan = result.iloc[:-1]
        assert non_nan.iloc[0]["game_id"] == "2025_10_SF_DAL"
        assert non_nan.iloc[1]["game_id"] == "2025_10_PHI_NYG"
        assert non_nan.iloc[2]["game_id"] == "2025_10_KC_BUF"

    def test_missing_model_error(self):
        """When model files don't exist, raises FileNotFoundError."""
        # This tests the CLI path — load_model raises FileNotFoundError
        # We verify that our script would surface this correctly by testing
        # that load_model itself raises for nonexistent paths
        from model_training import load_model

        with pytest.raises(FileNotFoundError):
            load_model("spread", model_dir="/nonexistent/path")


# ---------------------------------------------------------------------------
# Retired O/U betting surface (.planning/TOTALS_VERDICT.md, VERDICT: KILL)
# ---------------------------------------------------------------------------


class TestOuPickRetired:
    """``ou_pick`` can never carry a side.

    Non-vacuity: ``mock_game_features`` + the mock total model produce
    total_edge = [-4.0, +4.0, +0.5, NaN] -- both signs plus a NaN -- so the
    old rule ("over" if edge > 0 else "under") would label two games "over"
    and two "under". Every assertion below fails if the fix is reverted.
    """

    def test_no_side_is_emitted(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        # Fixture guard: the old rule would have had something to say here.
        signs = result["total_edge"].dropna()
        assert (signs > 0).any() and (signs < 0).any()

        assert set(result["ou_pick"]) == {OU_PICK_RETIRED}
        assert not result["ou_pick"].str.lower().isin({"over", "under"}).any()

    def test_an_upstream_side_is_overwritten(self):
        """The blanking is unconditional, not an "if absent" default.

        A frame reaching _normalize_prediction_columns with a real side -- a
        legacy caller, or a board regenerated from an old parquet -- must
        still come out blank. Reverting to the ``if "ou_pick" not in
        out.columns`` guard makes this fail with 'over'.
        """
        df = pd.DataFrame(
            {
                "home_team": ["BUF"],
                "away_team": ["KC"],
                "spread_edge": [1.0],
                "total_edge": [5.0],
                "ou_pick": ["over"],
            }
        )
        out = _normalize_prediction_columns(df)
        assert out["ou_pick"].tolist() == [OU_PICK_RETIRED]

    def test_market_tracking_columns_retained(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        """The verdict keeps the totals as content, just not as a bet."""
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        for col in ("predicted_total", "vegas_total", "total_edge", "over_prob"):
            assert col in result.columns, col
        # And they carry real numbers, not placeholders.
        assert result["predicted_total"].notna().all()
        assert result["total_edge"].notna().any()

    def test_schema_unchanged(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        """ou_pick stays a column -- the DB DDL and API schema depend on it."""
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        assert "ou_pick" in result.columns
        assert result["ou_pick"].dtype == object


# ---------------------------------------------------------------------------
# ATS pick follows the calibrated probability
# ---------------------------------------------------------------------------


class TestAtsPickFollowsProbability:
    """``ats_pick`` and ``home_cover_prob`` can never disagree.

    They contradicted on 1 of 14 games on the served 2026 wk7 board, because
    the pick read the edge sign while the tier and the site read the
    calibrator.
    """

    @staticmethod
    def _frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "home_team": ["BUF", "DAL", "NYG", "LV"],
                "away_team": ["KC", "SF", "PHI", "DEN"],
                # Row 0 and row 1 are the contradictions: the edge sign and
                # the calibrator point at opposite sides.
                "spread_edge": [2.0, -2.0, 4.0, -4.0],
                "total_edge": [1.0, -1.0, 2.0, -2.0],
                "home_cover_prob": [0.4469, 0.5243, 0.5100, 0.4900],
            }
        )

    def test_probability_wins_over_the_edge_sign(self):
        picks = derive_ats_pick(self._frame())
        # edge +2.0 says home (BUF), prob 0.4469 says away -> KC
        assert picks.iloc[0] == "KC"
        # edge -2.0 says away (SF), prob 0.5243 says home -> DAL
        assert picks.iloc[1] == "DAL"
        # the two that already agreed are unchanged
        assert picks.iloc[2] == "NYG"
        assert picks.iloc[3] == "DEN"

    def test_pick_and_prob_never_contradict(self):
        df = self._frame()
        picks = derive_ats_pick(df)
        picked_home = picks.eq(df["home_team"])
        assert (picked_home == (df["home_cover_prob"] >= 0.50)).all()

    def test_falls_back_to_edge_sign_without_a_calibrator(self):
        """Single-XGBoost path: no probability, so the old rule stands."""
        df = pd.DataFrame(
            {
                "home_team": ["BUF", "DAL", "LV"],
                "away_team": ["KC", "SF", "DEN"],
                "spread_edge": [2.0, -2.0, float("nan")],
                "home_cover_prob": [float("nan")] * 3,
            }
        )
        picks = derive_ats_pick(df)
        # NaN edge picked home before this change and still does.
        assert picks.tolist() == ["BUF", "SF", "LV"]

    def test_exact_coin_flip_picks_home(self):
        df = pd.DataFrame(
            {
                "home_team": ["BUF"],
                "away_team": ["KC"],
                "spread_edge": [0.0],
                "home_cover_prob": [0.50],
            }
        )
        assert derive_ats_pick(df).tolist() == ["BUF"]

    def test_normalize_wires_the_probability_through(self):
        """End-to-end through _normalize_prediction_columns, not just the helper."""
        out = _normalize_prediction_columns(self._frame())
        assert out["ats_pick"].tolist() == ["KC", "DAL", "NYG", "DEN"]

    def test_publication_threshold_is_off(self):
        """No pick is withheld by default -- that is the user's product call.

        On the served 2026 wk7 board only 4 of 14 picked sides clear the -110
        break-even (52.38%), so gating on it would strip most of the board.
        The constant exists so it can be switched on deliberately.
        """
        assert gp.ATS_PUBLISH_MIN_PROB is None

        df = self._frame()
        picks = derive_ats_pick(df)
        # Every picked side here is a near coin flip (max 0.5531)...
        assert gp.picked_side_prob(df).max() < 0.5238 + 0.05
        # ...and every row still publishes a team.
        assert (picks != "").all()

    def test_publication_threshold_suppresses_when_switched_on(self, monkeypatch):
        """Documents the flip: set the constant and sub-break-even picks blank."""
        monkeypatch.setattr(gp, "ATS_PUBLISH_MIN_PROB", 0.5238)
        df = self._frame()
        picks = derive_ats_pick(df)
        pick_prob = gp.picked_side_prob(df)
        assert (picks == "").tolist() == (pick_prob < 0.5238).tolist()
        # Sanity: the fixture has rows on both sides of the threshold.
        assert (picks == "").any() and (picks != "").any()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_gold_parquet_output(
        self,
        tmp_path,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        """Gold Parquet round-trip: write predictions, read back, verify schema."""
        result = generate_week_predictions(
            mock_game_features, 10, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )

        # Write to Gold path structure
        gold_dir = tmp_path / "predictions" / "season=2025" / "week=10"
        gold_dir.mkdir(parents=True)
        gold_path = gold_dir / "predictions_test.parquet"
        result.to_parquet(gold_path, index=False)

        # Read back and verify
        loaded = pd.read_parquet(gold_path)
        assert len(loaded) == 4

        # Check key columns present
        for col in [
            "game_id",
            "predicted_spread",
            "vegas_spread",
            "spread_edge",
            "confidence_tier",
            "predicted_total",
            "vegas_total",
            "total_edge",
            "ats_pick",
            "ou_pick",
        ]:
            assert col in loaded.columns, f"Missing column: {col}"

        # Check data types
        assert loaded["predicted_spread"].dtype == np.float64
        assert loaded["predicted_total"].dtype == np.float64
        assert loaded["confidence_tier"].dtype == object

    def test_empty_week(
        self,
        mock_game_features,
        mock_spread_model,
        mock_total_model,
        mock_metadata,
    ):
        """Requesting a week with no games returns empty DataFrame."""
        result = generate_week_predictions(
            mock_game_features, 99, mock_spread_model, mock_metadata, mock_total_model, mock_metadata
        )
        assert len(result) == 0
        assert isinstance(result, pd.DataFrame)
