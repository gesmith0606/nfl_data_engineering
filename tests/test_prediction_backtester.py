"""Tests for prediction backtester — ATS evaluation, O/U evaluation, profit accounting.

Uses synthetic DataFrames with known values for deterministic verification.
"""

import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from prediction_backtester import evaluate_ats, evaluate_ou, compute_profit


class TestATSEvaluation:
    """Tests for evaluate_ats() — ATS accuracy classification."""

    def test_home_covers(self):
        """Home team covers when actual_margin > spread_line."""
        df = pd.DataFrame({
            "actual_margin": [10],
            "spread_line": [3],
            "predicted_margin": [5],
        })
        result = evaluate_ats(df)
        assert result["home_covers"].iloc[0] is True
        assert result["push"].iloc[0] is False
        assert result["model_picks_home"].iloc[0] is True
        assert result["ats_correct"].iloc[0] is True

    def test_away_covers(self):
        """Away team covers when actual_margin < spread_line."""
        df = pd.DataFrame({
            "actual_margin": [-2],
            "spread_line": [3],
            "predicted_margin": [5],
        })
        result = evaluate_ats(df)
        assert result["home_covers"].iloc[0] is False
        # Model picked home (5 > 3) but home didn't cover -> incorrect
        assert result["model_picks_home"].iloc[0] is True
        assert result["ats_correct"].iloc[0] is False

    def test_push(self):
        """Push when actual_margin == spread_line exactly."""
        df = pd.DataFrame({
            "actual_margin": [3],
            "spread_line": [3],
            "predicted_margin": [5],
        })
        result = evaluate_ats(df)
        assert result["push"].iloc[0] is True
        # ats_correct is False on pushes (excluded from W/L)
        assert result["ats_correct"].iloc[0] is False

    def test_model_picks_away(self):
        """Model picks away when predicted_margin < spread_line."""
        df = pd.DataFrame({
            "actual_margin": [-5],
            "spread_line": [3],
            "predicted_margin": [1],  # 1 < 3 -> model picks away
        })
        result = evaluate_ats(df)
        assert result["model_picks_home"].iloc[0] is False
        assert result["home_covers"].iloc[0] is False
        # Both say away -> correct
        assert result["ats_correct"].iloc[0] is True

    def test_multiple_games(self):
        """Evaluate multiple games at once."""
        df = pd.DataFrame({
            "actual_margin": [10, -2, 3, -5, 7],
            "spread_line": [3, 3, 3, 3, 3],
            "predicted_margin": [5, 5, 5, 1, 1],
        })
        result = evaluate_ats(df)
        assert len(result) == 5
        # Game 0: home covers, model picks home -> correct
        # Game 1: away covers, model picks home -> incorrect
        # Game 2: push -> ats_correct=False
        # Game 3: away covers, model picks away -> correct
        # Game 4: home covers, model picks away -> incorrect
        assert list(result["ats_correct"]) == [True, False, False, True, False]

    def test_does_not_mutate_input(self):
        """evaluate_ats returns a copy, not mutating the input."""
        df = pd.DataFrame({
            "actual_margin": [10],
            "spread_line": [3],
            "predicted_margin": [5],
        })
        original_cols = set(df.columns)
        evaluate_ats(df)
        assert set(df.columns) == original_cols


class TestOUEvaluation:
    """Tests for evaluate_ou() — over/under classification."""

    def test_over_hits(self):
        """Over hits when actual_total > total_line."""
        df = pd.DataFrame({
            "actual_total": [50],
            "total_line": [45],
            "predicted_total": [47],
        })
        result = evaluate_ou(df)
        assert result["actual_over"].iloc[0] is True
        assert result["model_picks_over"].iloc[0] is True
        assert result["ou_correct"].iloc[0] is True

    def test_under_hits(self):
        """Under hits when actual_total < total_line."""
        df = pd.DataFrame({
            "actual_total": [38],
            "total_line": [45],
            "predicted_total": [43],
        })
        result = evaluate_ou(df)
        assert result["actual_over"].iloc[0] is False
        assert result["model_picks_over"].iloc[0] is False
        assert result["ou_correct"].iloc[0] is True

    def test_push_ou(self):
        """Push when actual_total == total_line exactly."""
        df = pd.DataFrame({
            "actual_total": [45],
            "total_line": [45],
            "predicted_total": [47],
        })
        result = evaluate_ou(df)
        assert result["push_ou"].iloc[0] is True
        assert result["ou_correct"].iloc[0] is False

    def test_model_picks_under(self):
        """Model picks under when predicted_total < total_line."""
        df = pd.DataFrame({
            "actual_total": [50],
            "total_line": [45],
            "predicted_total": [42],  # 42 < 45 -> model picks under
        })
        result = evaluate_ou(df)
        assert result["model_picks_over"].iloc[0] is False
        assert result["actual_over"].iloc[0] is True
        # Model wrong: picked under but actual was over
        assert result["ou_correct"].iloc[0] is False

    def test_does_not_mutate_input(self):
        """evaluate_ou returns a copy, not mutating the input."""
        df = pd.DataFrame({
            "actual_total": [50],
            "total_line": [45],
            "predicted_total": [47],
        })
        original_cols = set(df.columns)
        evaluate_ou(df)
        assert set(df.columns) == original_cols


class TestProfitAccounting:
    """Tests for compute_profit() — vig-adjusted profit at -110."""

    def test_six_wins_four_losses(self):
        """6W-4L-0P at -110: profit = 6*(100/110) - 4*1.0 = +1.4545 units."""
        correct = [True] * 6 + [False] * 4
        push = [False] * 10
        df = pd.DataFrame({"ats_correct": correct, "push": push})
        result = compute_profit(df)
        assert result["wins"] == 6
        assert result["losses"] == 4
        assert result["pushes"] == 0
        assert result["games_bet"] == 10
        assert abs(result["profit"] - (6 * (100.0 / 110.0) - 4.0)) < 0.001
        expected_roi = (6 * (100.0 / 110.0) - 4.0) / 10 * 100
        assert abs(result["roi"] - expected_roi) < 0.01

    def test_with_pushes(self):
        """5W-4L-1P at -110: pushes excluded from profit, games_bet=9."""
        correct = [True] * 5 + [False] * 4 + [False]  # last False is push
        push = [False] * 9 + [True]
        df = pd.DataFrame({"ats_correct": correct, "push": push})
        result = compute_profit(df)
        assert result["wins"] == 5
        assert result["losses"] == 4
        assert result["pushes"] == 1
        assert result["games_bet"] == 9
        expected_profit = 5 * (100.0 / 110.0) - 4.0
        assert abs(result["profit"] - expected_profit) < 0.001

    def test_break_even(self):
        """At 52.38% win rate (110 wins, 100 losses), profit is approximately zero."""
        correct = [True] * 110 + [False] * 100
        push = [False] * 210
        df = pd.DataFrame({"ats_correct": correct, "push": push})
        result = compute_profit(df)
        # 110 * (100/110) - 100 * 1.0 = 100 - 100 = 0
        assert abs(result["profit"]) < 0.01

    def test_custom_columns(self):
        """compute_profit works with custom column names."""
        df = pd.DataFrame({
            "ou_correct": [True, True, True, False, False],
            "push_ou": [False, False, False, False, False],
        })
        result = compute_profit(df, correct_col="ou_correct", push_col="push_ou")
        assert result["wins"] == 3
        assert result["losses"] == 2

    def test_all_pushes(self):
        """All pushes: games_bet=0, profit=0, roi=0."""
        df = pd.DataFrame({
            "ats_correct": [False, False, False],
            "push": [True, True, True],
        })
        result = compute_profit(df)
        assert result["games_bet"] == 0
        assert result["profit"] == 0.0
        assert result["roi"] == 0.0

    def test_empty_dataframe(self):
        """Empty DataFrame: games_bet=0, profit=0."""
        df = pd.DataFrame({"ats_correct": pd.Series(dtype=bool), "push": pd.Series(dtype=bool)})
        result = compute_profit(df)
        assert result["games_bet"] == 0
        assert result["profit"] == 0.0


class TestCLI:
    """Test that the CLI module exists and has a main function."""

    def test_main_exists(self):
        """scripts/backtest_predictions.py has a main() function that accepts argv."""
        scripts_dir = os.path.join(os.path.dirname(__file__), "..", "scripts")
        sys.path.insert(0, scripts_dir)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        import importlib
        spec = importlib.util.spec_from_file_location(
            "backtest_predictions",
            os.path.join(scripts_dir, "backtest_predictions.py"),
        )
        mod = importlib.util.load_module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main")
        assert callable(mod.main)
