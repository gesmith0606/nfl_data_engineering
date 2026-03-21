"""Tests for prediction backtester — ATS evaluation, O/U evaluation, profit accounting.

Uses synthetic DataFrames with known values for deterministic verification.
"""

import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from prediction_backtester import (
    evaluate_ats,
    evaluate_ou,
    compute_profit,
    evaluate_holdout,
    compute_season_stability,
    LEAKAGE_THRESHOLD,
)


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
        assert bool(result["home_covers"].iloc[0]) is True
        assert bool(result["push"].iloc[0]) is False
        assert bool(result["model_picks_home"].iloc[0]) is True
        assert bool(result["ats_correct"].iloc[0]) is True

    def test_away_covers(self):
        """Away team covers when actual_margin < spread_line."""
        df = pd.DataFrame({
            "actual_margin": [-2],
            "spread_line": [3],
            "predicted_margin": [5],
        })
        result = evaluate_ats(df)
        assert bool(result["home_covers"].iloc[0]) is False
        # Model picked home (5 > 3) but home didn't cover -> incorrect
        assert bool(result["model_picks_home"].iloc[0]) is True
        assert bool(result["ats_correct"].iloc[0]) is False

    def test_push(self):
        """Push when actual_margin == spread_line exactly."""
        df = pd.DataFrame({
            "actual_margin": [3],
            "spread_line": [3],
            "predicted_margin": [5],
        })
        result = evaluate_ats(df)
        assert bool(result["push"].iloc[0]) is True
        # ats_correct is False on pushes (excluded from W/L)
        assert bool(result["ats_correct"].iloc[0]) is False

    def test_model_picks_away(self):
        """Model picks away when predicted_margin < spread_line."""
        df = pd.DataFrame({
            "actual_margin": [-5],
            "spread_line": [3],
            "predicted_margin": [1],  # 1 < 3 -> model picks away
        })
        result = evaluate_ats(df)
        assert bool(result["model_picks_home"].iloc[0]) is False
        assert bool(result["home_covers"].iloc[0]) is False
        # Both say away -> correct
        assert bool(result["ats_correct"].iloc[0]) is True

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
        assert bool(result["actual_over"].iloc[0]) is True
        assert bool(result["model_picks_over"].iloc[0]) is True
        assert bool(result["ou_correct"].iloc[0]) is True

    def test_under_hits(self):
        """Under hits when actual_total < total_line."""
        df = pd.DataFrame({
            "actual_total": [38],
            "total_line": [45],
            "predicted_total": [43],
        })
        result = evaluate_ou(df)
        assert bool(result["actual_over"].iloc[0]) is False
        assert bool(result["model_picks_over"].iloc[0]) is False
        assert bool(result["ou_correct"].iloc[0]) is True

    def test_push_ou(self):
        """Push when actual_total == total_line exactly."""
        df = pd.DataFrame({
            "actual_total": [45],
            "total_line": [45],
            "predicted_total": [47],
        })
        result = evaluate_ou(df)
        assert bool(result["push_ou"].iloc[0]) is True
        assert bool(result["ou_correct"].iloc[0]) is False

    def test_model_picks_under(self):
        """Model picks under when predicted_total < total_line."""
        df = pd.DataFrame({
            "actual_total": [50],
            "total_line": [45],
            "predicted_total": [42],  # 42 < 45 -> model picks under
        })
        result = evaluate_ou(df)
        assert bool(result["model_picks_over"].iloc[0]) is False
        assert bool(result["actual_over"].iloc[0]) is True
        # Model wrong: picked under but actual was over
        assert bool(result["ou_correct"].iloc[0]) is False

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


class TestHoldoutValidation:
    """Tests for evaluate_holdout() — sealed holdout season evaluation."""

    def _make_results_df(self, seasons, n_per_season=10):
        """Create synthetic results DataFrame with ATS columns already set."""
        rows = []
        for season in seasons:
            for i in range(n_per_season):
                rows.append({
                    "season": season,
                    "actual_margin": 7 if i % 2 == 0 else -3,
                    "spread_line": 3,
                    "predicted_margin": 5,
                    "push": False,
                    "home_covers": i % 2 == 0,
                    "model_picks_home": True,
                    "ats_correct": i % 2 == 0,  # 50% accuracy
                })
        return pd.DataFrame(rows)

    def test_leakage_guard_raises(self):
        """evaluate_holdout raises ValueError if holdout_season in training_seasons."""
        df = self._make_results_df([2023, 2024])
        metadata = {"training_seasons": [2020, 2021, 2022, 2023, 2024]}
        with pytest.raises(ValueError, match="data leakage"):
            evaluate_holdout(df, metadata, holdout_season=2024)

    def test_filters_to_holdout_season(self):
        """evaluate_holdout only evaluates the holdout season rows."""
        df = self._make_results_df([2023, 2024], n_per_season=10)
        metadata = {"training_seasons": [2020, 2021, 2022, 2023]}
        result = evaluate_holdout(df, metadata, holdout_season=2024)
        assert result["n_games"] == 10
        assert result["season"] == 2024

    def test_returns_required_keys(self):
        """evaluate_holdout returns dict with ats_accuracy, profit_stats, n_games, season."""
        df = self._make_results_df([2023, 2024], n_per_season=8)
        metadata = {"training_seasons": [2020, 2021, 2022, 2023]}
        result = evaluate_holdout(df, metadata, holdout_season=2024)
        assert "ats_accuracy" in result
        assert "profit_stats" in result
        assert "n_games" in result
        assert "season" in result
        assert isinstance(result["profit_stats"], dict)

    def test_accuracy_calculation(self):
        """evaluate_holdout computes correct accuracy from non-push games."""
        df = self._make_results_df([2024], n_per_season=10)
        metadata = {"training_seasons": [2020, 2021, 2022, 2023]}
        result = evaluate_holdout(df, metadata, holdout_season=2024)
        # 50% correct (every other game)
        assert abs(result["ats_accuracy"] - 0.5) < 0.01

    def test_empty_holdout_season(self):
        """evaluate_holdout handles missing holdout season data gracefully."""
        df = self._make_results_df([2023], n_per_season=5)
        metadata = {"training_seasons": [2020, 2021, 2022, 2023]}
        result = evaluate_holdout(df, metadata, holdout_season=2024)
        assert result["n_games"] == 0
        assert result["ats_accuracy"] == 0.0


class TestStabilityAnalysis:
    """Tests for compute_season_stability() — per-season ATS breakdown."""

    def _make_multiseason_df(self):
        """Create synthetic results with known per-season accuracy.

        Season 2020: 6/10 correct = 60%
        Season 2021: 5/10 correct = 50%
        Season 2022: 4/10 correct = 40%
        """
        rows = []
        # 2020: first 6 correct
        for i in range(10):
            rows.append({
                "season": 2020,
                "ats_correct": i < 6,
                "push": False,
            })
        # 2021: first 5 correct
        for i in range(10):
            rows.append({
                "season": 2021,
                "ats_correct": i < 5,
                "push": False,
            })
        # 2022: first 4 correct
        for i in range(10):
            rows.append({
                "season": 2022,
                "ats_correct": i < 4,
                "push": False,
            })
        return pd.DataFrame(rows)

    def test_returns_per_season_df(self):
        """compute_season_stability returns DataFrame with required columns."""
        df = self._make_multiseason_df()
        per_season_df, _ = compute_season_stability(df)
        assert list(per_season_df.columns) == ["season", "games", "ats_accuracy", "profit", "roi"]
        assert len(per_season_df) == 3

    def test_per_season_accuracy(self):
        """Per-season accuracy matches known values."""
        df = self._make_multiseason_df()
        per_season_df, _ = compute_season_stability(df)
        acc = dict(zip(per_season_df["season"], per_season_df["ats_accuracy"]))
        assert abs(acc[2020] - 0.6) < 0.01
        assert abs(acc[2021] - 0.5) < 0.01
        assert abs(acc[2022] - 0.4) < 0.01

    def test_stability_summary_keys(self):
        """stability_summary dict has mean, std, min, max accuracy and leakage_warning."""
        df = self._make_multiseason_df()
        _, summary = compute_season_stability(df)
        assert "mean_accuracy" in summary
        assert "std_accuracy" in summary
        assert "min_accuracy" in summary
        assert "max_accuracy" in summary
        assert "leakage_warning" in summary

    def test_stability_summary_values(self):
        """stability_summary computes correct mean/std/min/max."""
        df = self._make_multiseason_df()
        _, summary = compute_season_stability(df)
        # mean of 0.6, 0.5, 0.4 = 0.5
        assert abs(summary["mean_accuracy"] - 0.5) < 0.01
        assert abs(summary["min_accuracy"] - 0.4) < 0.01
        assert abs(summary["max_accuracy"] - 0.6) < 0.01
        assert summary["std_accuracy"] > 0  # non-zero std

    def test_leakage_warning_triggered(self):
        """leakage_warning True when any season exceeds 58% ATS accuracy."""
        df = self._make_multiseason_df()  # 2020 is 60% > 58%
        _, summary = compute_season_stability(df)
        assert summary["leakage_warning"] is True

    def test_leakage_warning_not_triggered(self):
        """leakage_warning False when all seasons below 58%."""
        # All seasons at 50%
        rows = []
        for season in [2020, 2021, 2022]:
            for i in range(10):
                rows.append({"season": season, "ats_correct": i < 5, "push": False})
        df = pd.DataFrame(rows)
        _, summary = compute_season_stability(df)
        assert summary["leakage_warning"] is False

    def test_single_season(self):
        """compute_season_stability handles single-season input."""
        rows = [{"season": 2023, "ats_correct": i < 5, "push": False} for i in range(10)]
        df = pd.DataFrame(rows)
        per_season_df, summary = compute_season_stability(df)
        assert len(per_season_df) == 1
        assert summary["std_accuracy"] == 0.0  # single season -> 0 std


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
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main")
        assert callable(mod.main)
