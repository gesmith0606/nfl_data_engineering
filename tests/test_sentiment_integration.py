"""
Unit tests for Phase S3 — Sentiment Pipeline → Projection Engine Integration.

Tests cover:
- apply_sentiment_adjustments() behaviour across all branches
- load_latest_sentiment() graceful handling of missing data
- Edge cases: ruled-out zeroing, injury-zeroed skip, neutral multiplier,
  range clamping, and missing sentiment data tolerance.
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from projection_engine import (
    apply_sentiment_adjustments,
    load_latest_sentiment,
    _SENTIMENT_MULT_MIN,
    _SENTIMENT_MULT_MAX,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_projections(**overrides) -> pd.DataFrame:
    """Return a minimal projections DataFrame for one player."""
    base = {
        "player_id": ["P001"],
        "player_name": ["Test Player"],
        "position": ["WR"],
        "projected_points": [20.0],
        "projected_floor": [12.0],
        "projected_ceiling": [28.0],
        "injury_multiplier": [1.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _make_sentiment(**overrides) -> pd.DataFrame:
    """Return a minimal sentiment DataFrame for one player."""
    base = {
        "player_id": ["P001"],
        "sentiment_multiplier": [1.0],
        "is_ruled_out": [False],
        "is_inactive": [False],
        "is_questionable": [False],
        "is_suspended": [False],
        "is_returning": [False],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# Tests: apply_sentiment_adjustments
# ---------------------------------------------------------------------------


class TestApplySentimentAdjustments(unittest.TestCase):
    """Tests for apply_sentiment_adjustments()."""

    # ------------------------------------------------------------------
    # Basic functionality
    # ------------------------------------------------------------------

    def test_neutral_multiplier_leaves_projections_unchanged(self):
        """A sentiment_multiplier of exactly 1.0 must not alter any projection."""
        proj = _make_projections()
        sent = _make_sentiment(sentiment_multiplier=[1.0])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertAlmostEqual(result["projected_points"].iloc[0], 20.0)
        self.assertAlmostEqual(result["projected_floor"].iloc[0], 12.0)
        self.assertAlmostEqual(result["projected_ceiling"].iloc[0], 28.0)

    def test_positive_multiplier_scales_up(self):
        """A multiplier > 1.0 should increase all three projection columns."""
        proj = _make_projections()
        sent = _make_sentiment(sentiment_multiplier=[1.10])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertAlmostEqual(result["projected_points"].iloc[0], 22.0)
        self.assertAlmostEqual(result["projected_floor"].iloc[0], 13.2)
        self.assertAlmostEqual(result["projected_ceiling"].iloc[0], 30.8)

    def test_negative_multiplier_scales_down(self):
        """A multiplier < 1.0 should decrease all three projection columns."""
        proj = _make_projections()
        sent = _make_sentiment(sentiment_multiplier=[0.80])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertAlmostEqual(result["projected_points"].iloc[0], 16.0)
        self.assertAlmostEqual(result["projected_floor"].iloc[0], 9.6)
        self.assertAlmostEqual(result["projected_ceiling"].iloc[0], 22.4)

    def test_transparency_columns_added(self):
        """Result must contain sentiment_multiplier and sentiment_events columns."""
        proj = _make_projections()
        sent = _make_sentiment(sentiment_multiplier=[1.05])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertIn("sentiment_multiplier", result.columns)
        self.assertIn("sentiment_events", result.columns)

    def test_player_without_sentiment_gets_neutral_multiplier(self):
        """Players not in sentiment_df should receive a multiplier of 1.0."""
        proj = _make_projections(player_id=["UNKNOWN"])
        sent = _make_sentiment(player_id=["P001"])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertAlmostEqual(result["sentiment_multiplier"].iloc[0], 1.0)
        self.assertAlmostEqual(result["projected_points"].iloc[0], 20.0)

    # ------------------------------------------------------------------
    # Event flag handling
    # ------------------------------------------------------------------

    def test_ruled_out_zeroes_projection(self):
        """is_ruled_out=True must zero all projection columns."""
        proj = _make_projections()
        sent = _make_sentiment(is_ruled_out=[True], sentiment_multiplier=[0.9])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertEqual(result["projected_points"].iloc[0], 0.0)
        self.assertEqual(result["projected_floor"].iloc[0], 0.0)
        self.assertEqual(result["projected_ceiling"].iloc[0], 0.0)
        self.assertEqual(result["sentiment_multiplier"].iloc[0], 0.0)

    def test_inactive_zeroes_projection(self):
        """is_inactive=True must zero all projection columns."""
        proj = _make_projections()
        sent = _make_sentiment(is_inactive=[True], sentiment_multiplier=[1.1])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertEqual(result["projected_points"].iloc[0], 0.0)
        self.assertEqual(result["projected_floor"].iloc[0], 0.0)
        self.assertEqual(result["projected_ceiling"].iloc[0], 0.0)

    def test_questionable_flag_recorded_in_events(self):
        """is_questionable=True should appear in the sentiment_events string."""
        proj = _make_projections()
        sent = _make_sentiment(is_questionable=[True], sentiment_multiplier=[0.85])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertIn("is_questionable", result["sentiment_events"].iloc[0])

    def test_returning_flag_recorded_in_events(self):
        """is_returning=True should appear in the sentiment_events string."""
        proj = _make_projections()
        sent = _make_sentiment(is_returning=[True], sentiment_multiplier=[1.08])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertIn("is_returning", result["sentiment_events"].iloc[0])

    def test_no_active_flags_produces_empty_events_string(self):
        """When no event flags are set, sentiment_events should be empty string."""
        proj = _make_projections()
        sent = _make_sentiment()  # all flags False
        result = apply_sentiment_adjustments(proj, sent)

        self.assertEqual(result["sentiment_events"].iloc[0], "")

    # ------------------------------------------------------------------
    # Injury-zeroed player skip
    # ------------------------------------------------------------------

    def test_injury_zeroed_players_are_skipped(self):
        """Players zeroed by injury (projected_points=0, injury_multiplier=0)
        must not be altered by a positive sentiment multiplier."""
        proj = _make_projections(
            projected_points=[0.0],
            projected_floor=[0.0],
            projected_ceiling=[0.0],
            injury_multiplier=[0.0],
        )
        sent = _make_sentiment(sentiment_multiplier=[1.15])
        result = apply_sentiment_adjustments(proj, sent)

        # Projection must stay at zero — sentiment should not resurrect the player
        self.assertEqual(result["projected_points"].iloc[0], 0.0)
        # The sentiment_multiplier column should remain at its default (1.0),
        # since the player was skipped entirely.
        self.assertAlmostEqual(result["sentiment_multiplier"].iloc[0], 1.0)

    # ------------------------------------------------------------------
    # Multiplier range enforcement
    # ------------------------------------------------------------------

    def test_multiplier_clamped_at_maximum(self):
        """A sentiment_multiplier above _SENTIMENT_MULT_MAX is clamped."""
        proj = _make_projections()
        sent = _make_sentiment(sentiment_multiplier=[2.0])  # way above 1.15
        result = apply_sentiment_adjustments(proj, sent)

        applied_mult = result["sentiment_multiplier"].iloc[0]
        self.assertLessEqual(applied_mult, _SENTIMENT_MULT_MAX)
        self.assertAlmostEqual(applied_mult, _SENTIMENT_MULT_MAX)

    def test_multiplier_clamped_at_minimum(self):
        """A sentiment_multiplier below _SENTIMENT_MULT_MIN is clamped."""
        proj = _make_projections()
        sent = _make_sentiment(sentiment_multiplier=[0.10])  # way below 0.70
        result = apply_sentiment_adjustments(proj, sent)

        applied_mult = result["sentiment_multiplier"].iloc[0]
        self.assertGreaterEqual(applied_mult, _SENTIMENT_MULT_MIN)
        self.assertAlmostEqual(applied_mult, _SENTIMENT_MULT_MIN)

    def test_projected_points_never_go_below_zero(self):
        """projected_points must not become negative under any multiplier."""
        proj = _make_projections(projected_points=[5.0])
        sent = _make_sentiment(sentiment_multiplier=[0.70])
        result = apply_sentiment_adjustments(proj, sent)

        self.assertGreaterEqual(result["projected_points"].iloc[0], 0.0)

    # ------------------------------------------------------------------
    # Missing / empty sentiment data
    # ------------------------------------------------------------------

    def test_empty_sentiment_df_does_not_crash(self):
        """An empty sentiment DataFrame should return projections unchanged."""
        proj = _make_projections()
        sent = pd.DataFrame()
        result = apply_sentiment_adjustments(proj, sent)

        self.assertAlmostEqual(result["projected_points"].iloc[0], 20.0)
        self.assertIn("sentiment_multiplier", result.columns)

    def test_none_sentiment_df_does_not_crash(self):
        """None sentiment input should return projections unchanged."""
        proj = _make_projections()
        result = apply_sentiment_adjustments(proj, None)

        self.assertAlmostEqual(result["projected_points"].iloc[0], 20.0)

    def test_sentiment_df_missing_required_columns_skips_gracefully(self):
        """Sentiment DataFrame without player_id/sentiment_multiplier should
        leave projections unchanged and not raise."""
        proj = _make_projections()
        sent = pd.DataFrame({"doc_count": [5]})  # no required columns
        result = apply_sentiment_adjustments(proj, sent)

        self.assertAlmostEqual(result["projected_points"].iloc[0], 20.0)

    # ------------------------------------------------------------------
    # Multi-player scenarios
    # ------------------------------------------------------------------

    def test_multiple_players_each_get_correct_multiplier(self):
        """Each player receives its own multiplier; unmatched players stay at 1.0."""
        proj = pd.DataFrame({
            "player_id": ["P001", "P002", "P003"],
            "player_name": ["Alpha", "Beta", "Gamma"],
            "position": ["WR", "RB", "QB"],
            "projected_points": [20.0, 15.0, 25.0],
            "projected_floor": [10.0, 8.0, 14.0],
            "projected_ceiling": [30.0, 22.0, 36.0],
            "injury_multiplier": [1.0, 1.0, 1.0],
        })
        sent = pd.DataFrame({
            "player_id": ["P001", "P002"],  # P003 has no sentiment
            "sentiment_multiplier": [1.10, 0.90],
            "is_ruled_out": [False, False],
            "is_inactive": [False, False],
        })
        result = apply_sentiment_adjustments(proj, sent)

        # P001: 20 * 1.10 = 22
        self.assertAlmostEqual(result.loc[result["player_id"] == "P001", "projected_points"].iloc[0], 22.0)
        # P002: 15 * 0.90 = 13.5
        self.assertAlmostEqual(result.loc[result["player_id"] == "P002", "projected_points"].iloc[0], 13.5)
        # P003: no sentiment → unchanged
        self.assertAlmostEqual(result.loc[result["player_id"] == "P003", "projected_points"].iloc[0], 25.0)
        self.assertAlmostEqual(result.loc[result["player_id"] == "P003", "sentiment_multiplier"].iloc[0], 1.0)

    def test_projections_df_not_mutated_in_place(self):
        """apply_sentiment_adjustments must not modify the original DataFrame."""
        proj = _make_projections()
        original_pts = proj["projected_points"].iloc[0]
        sent = _make_sentiment(sentiment_multiplier=[0.75])
        _ = apply_sentiment_adjustments(proj, sent)

        self.assertAlmostEqual(proj["projected_points"].iloc[0], original_pts)


# ---------------------------------------------------------------------------
# Tests: load_latest_sentiment
# ---------------------------------------------------------------------------


class TestLoadLatestSentiment(unittest.TestCase):
    """Tests for load_latest_sentiment()."""

    def test_returns_empty_df_when_no_local_data(self):
        """load_latest_sentiment should return empty DataFrame when no files exist."""
        # Season/week combo guaranteed not to have data
        df = load_latest_sentiment(season=1899, week=1)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertTrue(df.empty)

    def test_returns_dataframe_from_local_parquet(self):
        """load_latest_sentiment should read a local Parquet file if present."""
        project_root = Path(__file__).resolve().parent.parent
        sentinel_dir = (
            project_root / "data" / "gold" / "sentiment"
            / "season=1900" / "week=01"
        )
        sentinel_dir.mkdir(parents=True, exist_ok=True)
        sentinel_file = sentinel_dir / "sentiment_multipliers_99991231_000000.parquet"

        sample = pd.DataFrame({
            "player_id": ["TEST_P"],
            "sentiment_multiplier": [1.05],
            "is_ruled_out": [False],
            "is_inactive": [False],
            "season": [1900],
            "week": [1],
        })
        sample.to_parquet(sentinel_file, index=False)

        try:
            result = load_latest_sentiment(season=1900, week=1)
            self.assertFalse(result.empty)
            self.assertIn("player_id", result.columns)
            self.assertIn("sentiment_multiplier", result.columns)
            self.assertEqual(result["player_id"].iloc[0], "TEST_P")
        finally:
            # Clean up sentinel files
            sentinel_file.unlink(missing_ok=True)
            try:
                sentinel_dir.rmdir()
                sentinel_dir.parent.rmdir()
            except OSError:
                pass

    def test_missing_data_does_not_crash_pipeline(self):
        """load_latest_sentiment must never raise even if paths don't exist."""
        try:
            df = load_latest_sentiment(season=9999, week=99)
        except Exception as exc:
            self.fail(f"load_latest_sentiment raised unexpectedly: {exc}")
        self.assertIsInstance(df, pd.DataFrame)


if __name__ == "__main__":
    unittest.main()
