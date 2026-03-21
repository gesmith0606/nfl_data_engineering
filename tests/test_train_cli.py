#!/usr/bin/env python3
"""Tests for the training CLI script (train_prediction_model.py).

Validates argparse configuration, TARGET_MAP, Optuna objective wiring,
and end-to-end --no-tune training with feature importance output.
"""

import argparse
import glob
import os
import sys

import pytest

# Project src/ on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SILVER_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "silver")


def _silver_data_available() -> bool:
    """Check if Silver team data is available for at least one training season."""
    files = glob.glob(
        os.path.join(SILVER_DIR, "teams", "game_context", "season=2020", "*.parquet")
    )
    return len(files) > 0


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


class TestImports:
    """Verify the training script can be imported without errors."""

    def test_target_map_importable(self):
        """TARGET_MAP should be importable from the training script."""
        from scripts.train_prediction_model import TARGET_MAP

        assert isinstance(TARGET_MAP, dict)

    def test_target_map_spread(self):
        """TARGET_MAP['spread'] should map to 'actual_margin'."""
        from scripts.train_prediction_model import TARGET_MAP

        assert TARGET_MAP["spread"] == "actual_margin"

    def test_target_map_total(self):
        """TARGET_MAP['total'] should map to 'actual_total'."""
        from scripts.train_prediction_model import TARGET_MAP

        assert TARGET_MAP["total"] == "actual_total"

    def test_optuna_importable(self):
        """Optuna should be importable (dependency installed)."""
        import optuna  # noqa: F401

    def test_build_parser_importable(self):
        """build_parser function should be importable."""
        from scripts.train_prediction_model import build_parser

        assert callable(build_parser)


# ---------------------------------------------------------------------------
# Argparse tests
# ---------------------------------------------------------------------------


class TestArgparse:
    """Verify CLI argument parsing."""

    def test_target_spread(self):
        """--target spread should parse correctly."""
        from scripts.train_prediction_model import build_parser

        parser = build_parser()
        args = parser.parse_args(["--target", "spread"])
        assert args.target == "spread"

    def test_target_total(self):
        """--target total should parse correctly."""
        from scripts.train_prediction_model import build_parser

        parser = build_parser()
        args = parser.parse_args(["--target", "total"])
        assert args.target == "total"

    def test_trials_default(self):
        """--trials should default to 50."""
        from scripts.train_prediction_model import build_parser

        parser = build_parser()
        args = parser.parse_args(["--target", "spread"])
        assert args.trials == 50

    def test_trials_custom(self):
        """--trials 100 should override default."""
        from scripts.train_prediction_model import build_parser

        parser = build_parser()
        args = parser.parse_args(["--target", "spread", "--trials", "100"])
        assert args.trials == 100

    def test_no_tune_flag(self):
        """--no-tune should be accepted and default to False."""
        from scripts.train_prediction_model import build_parser

        parser = build_parser()
        args_default = parser.parse_args(["--target", "spread"])
        assert args_default.no_tune is False

        args_notune = parser.parse_args(["--target", "spread", "--no-tune"])
        assert args_notune.no_tune is True

    def test_seasons_optional(self):
        """--seasons should accept multiple ints."""
        from scripts.train_prediction_model import build_parser

        parser = build_parser()
        args = parser.parse_args(["--target", "spread", "--seasons", "2020", "2021"])
        assert args.seasons == [2020, 2021]

    def test_target_required(self):
        """Omitting --target should raise SystemExit."""
        from scripts.train_prediction_model import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


# ---------------------------------------------------------------------------
# Integration test (requires Silver data)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _silver_data_available(),
    reason="Silver data not available for training seasons",
)
class TestIntegration:
    """End-to-end tests requiring Silver data on disk."""

    def test_no_tune_spread(self, tmp_path):
        """--target spread --no-tune should train and save model artifacts."""
        from scripts.train_prediction_model import main

        exit_code = main([
            "--target", "spread",
            "--no-tune",
            "--model-dir", str(tmp_path),
        ])
        assert exit_code == 0

        # Model artifacts should exist
        assert os.path.exists(os.path.join(tmp_path, "spread", "model.json"))
        assert os.path.exists(os.path.join(tmp_path, "spread", "metadata.json"))
        assert os.path.exists(
            os.path.join(tmp_path, "spread", "feature_importance.csv")
        )

    def test_feature_importance_csv_content(self, tmp_path):
        """Feature importance CSV should have feature and importance columns."""
        import pandas as pd
        from scripts.train_prediction_model import main

        main([
            "--target", "total",
            "--no-tune",
            "--model-dir", str(tmp_path),
        ])

        csv_path = os.path.join(tmp_path, "total", "feature_importance.csv")
        assert os.path.exists(csv_path)
        df = pd.read_csv(csv_path)
        assert "feature" in df.columns
        assert "importance" in df.columns
        assert len(df) > 0
        # Should be sorted descending by importance
        assert df["importance"].is_monotonic_decreasing
