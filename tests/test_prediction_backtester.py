"""Tests for prediction backtester — ATS evaluation, O/U evaluation, profit accounting.

Uses synthetic DataFrames with known values for deterministic verification.
"""

import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.config import HOLDOUT_SEASON, TRAINING_SEASONS

from prediction_backtester import (
    evaluate_ats,
    evaluate_ou,
    evaluate_clv,
    compute_clv_by_tier,
    compute_clv_by_season,
    compute_profit,
    evaluate_holdout,
    compute_season_stability,
    print_holdout_comparison,
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
        df = self._make_results_df([HOLDOUT_SEASON - 1, HOLDOUT_SEASON])
        metadata = {"training_seasons": TRAINING_SEASONS + [HOLDOUT_SEASON]}
        with pytest.raises(ValueError, match="data leakage"):
            evaluate_holdout(df, metadata, holdout_season=HOLDOUT_SEASON)

    def test_filters_to_holdout_season(self):
        """evaluate_holdout only evaluates the holdout season rows."""
        df = self._make_results_df([HOLDOUT_SEASON - 1, HOLDOUT_SEASON], n_per_season=10)
        metadata = {"training_seasons": TRAINING_SEASONS}
        result = evaluate_holdout(df, metadata, holdout_season=HOLDOUT_SEASON)
        assert result["n_games"] == 10
        assert result["season"] == HOLDOUT_SEASON

    def test_returns_required_keys(self):
        """evaluate_holdout returns dict with ats_accuracy, profit_stats, n_games, season."""
        df = self._make_results_df([HOLDOUT_SEASON - 1, HOLDOUT_SEASON], n_per_season=8)
        metadata = {"training_seasons": TRAINING_SEASONS}
        result = evaluate_holdout(df, metadata, holdout_season=HOLDOUT_SEASON)
        assert "ats_accuracy" in result
        assert "profit_stats" in result
        assert "n_games" in result
        assert "season" in result
        assert isinstance(result["profit_stats"], dict)

    def test_accuracy_calculation(self):
        """evaluate_holdout computes correct accuracy from non-push games."""
        df = self._make_results_df([HOLDOUT_SEASON], n_per_season=10)
        metadata = {"training_seasons": TRAINING_SEASONS}
        result = evaluate_holdout(df, metadata, holdout_season=HOLDOUT_SEASON)
        # 50% correct (every other game)
        assert abs(result["ats_accuracy"] - 0.5) < 0.01

    def test_empty_holdout_season(self):
        """evaluate_holdout handles missing holdout season data gracefully."""
        df = self._make_results_df([HOLDOUT_SEASON - 1], n_per_season=5)
        metadata = {"training_seasons": TRAINING_SEASONS}
        result = evaluate_holdout(df, metadata, holdout_season=HOLDOUT_SEASON)
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


class TestHoldoutComparison:
    """Tests for print_holdout_comparison() -- three-way holdout comparison table."""

    def _make_config_results(self, season, n_games=10, accuracy_pct=50):
        """Create synthetic ATS+O/U evaluated results for a given config.

        Args:
            season: Season year for all rows.
            n_games: Number of games.
            accuracy_pct: Approximate ATS accuracy percentage (0-100).
        """
        rows = []
        n_correct = int(n_games * accuracy_pct / 100)
        for i in range(n_games):
            margin = 7 if i < n_correct else -3
            pred_margin = 5  # always picks home
            total_actual = 50 if i % 2 == 0 else 38
            total_pred = 47
            rows.append({
                "season": season,
                "week": i + 1,
                "game_id": f"{season}_{i:02d}",
                "predicted_margin": pred_margin,
                "actual_margin": margin,
                "spread_line": 3.0,
                "predicted_total": total_pred,
                "actual_total": total_actual,
                "total_line": 45.0,
            })
        df = pd.DataFrame(rows)
        # Apply ATS and O/U evaluation
        df = evaluate_ats(df)
        df = evaluate_ou(df)
        return df

    def test_returns_dict_with_three_configs(self):
        """print_holdout_comparison returns dict keyed by three config names."""
        xgb = self._make_config_results(HOLDOUT_SEASON, 10, 50)
        ens = self._make_config_results(HOLDOUT_SEASON, 10, 55)
        full = self._make_config_results(HOLDOUT_SEASON, 10, 60)
        result = print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        assert isinstance(result, dict)
        assert "v1.4 XGB" in result
        assert "P30 Ensemble" in result
        assert "P31 Full" in result

    def test_output_contains_config_labels(self, capsys):
        """Printed output contains all three config labels."""
        xgb = self._make_config_results(HOLDOUT_SEASON, 10, 50)
        ens = self._make_config_results(HOLDOUT_SEASON, 10, 55)
        full = self._make_config_results(HOLDOUT_SEASON, 10, 60)
        print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        captured = capsys.readouterr()
        assert "v1.4 XGB" in captured.out
        assert "P30 Ensemble" in captured.out
        assert "P31 Full" in captured.out

    def test_output_contains_metric_rows(self, capsys):
        """Printed output includes ATS Accuracy, MAE, Profit, ROI rows."""
        xgb = self._make_config_results(HOLDOUT_SEASON, 10, 50)
        ens = self._make_config_results(HOLDOUT_SEASON, 10, 55)
        full = self._make_config_results(HOLDOUT_SEASON, 10, 60)
        print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        captured = capsys.readouterr()
        assert "ATS Accuracy" in captured.out
        assert "Profit" in captured.out
        assert "ROI" in captured.out

    def test_best_indicator_present(self, capsys):
        """Output includes a Best indicator showing which config wins."""
        xgb = self._make_config_results(HOLDOUT_SEASON, 10, 50)
        ens = self._make_config_results(HOLDOUT_SEASON, 10, 55)
        full = self._make_config_results(HOLDOUT_SEASON, 10, 60)
        print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        captured = capsys.readouterr()
        assert "Best" in captured.out or "BEST" in captured.out or "best" in captured.out

    def test_filters_to_holdout_season(self):
        """Only holdout_season rows are used for comparison metrics."""
        # Mix non-holdout and holdout data -- only holdout should count
        xgb_prev = self._make_config_results(HOLDOUT_SEASON - 1, 10, 80)
        xgb_holdout = self._make_config_results(HOLDOUT_SEASON, 10, 50)
        xgb = pd.concat([xgb_prev, xgb_holdout], ignore_index=True)
        ens = self._make_config_results(HOLDOUT_SEASON, 10, 55)
        full = self._make_config_results(HOLDOUT_SEASON, 10, 60)
        result = print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        # v1.4 XGB should show ~50% accuracy (from holdout), not 80% (from prior season)
        xgb_ats = result["v1.4 XGB"]["ats_accuracy"]
        assert xgb_ats < 0.6  # should be around 0.5, not 0.8

    def test_handles_missing_predictions(self):
        """Gracefully handles one config with fewer games."""
        xgb = self._make_config_results(HOLDOUT_SEASON, 10, 50)
        ens = self._make_config_results(HOLDOUT_SEASON, 5, 60)  # fewer games
        full = self._make_config_results(HOLDOUT_SEASON, 10, 55)
        result = print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        assert result["v1.4 XGB"]["n_games"] == 10
        assert result["P30 Ensemble"]["n_games"] == 5
        assert result["P31 Full"]["n_games"] == 10

    def test_metrics_values_reasonable(self):
        """Returned metric values are within expected ranges."""
        xgb = self._make_config_results(HOLDOUT_SEASON, 20, 55)
        ens = self._make_config_results(HOLDOUT_SEASON, 20, 60)
        full = self._make_config_results(HOLDOUT_SEASON, 20, 65)
        result = print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        for config_name, metrics in result.items():
            assert 0.0 <= metrics["ats_accuracy"] <= 1.0
            assert isinstance(metrics["profit"], float)
            assert isinstance(metrics["roi"], float)
            assert isinstance(metrics["mae"], float)
            assert metrics["mae"] >= 0.0

    def test_header_contains_season(self, capsys):
        """Output header includes the holdout season year."""
        xgb = self._make_config_results(HOLDOUT_SEASON, 10, 50)
        ens = self._make_config_results(HOLDOUT_SEASON, 10, 55)
        full = self._make_config_results(HOLDOUT_SEASON, 10, 60)
        print_holdout_comparison(xgb, ens, full, holdout_season=HOLDOUT_SEASON)
        captured = capsys.readouterr()
        assert str(HOLDOUT_SEASON) in captured.out


class TestCLVEvaluation:
    """Tests for evaluate_clv() — CLV (Closing Line Value) computation."""

    def test_clv_computation(self):
        """CLV = predicted_margin - spread_line."""
        df = pd.DataFrame({
            "predicted_margin": [7, -2, 3],
            "spread_line": [-3, 1, 5],
        })
        result = evaluate_clv(df)
        assert list(result["clv"]) == [10, -3, -2]

    def test_clv_preserves_columns(self):
        """All original columns are preserved in the output."""
        df = pd.DataFrame({
            "predicted_margin": [7, -2],
            "spread_line": [-3, 1],
            "extra_col": ["a", "b"],
        })
        result = evaluate_clv(df)
        assert "predicted_margin" in result.columns
        assert "spread_line" in result.columns
        assert "extra_col" in result.columns
        assert "clv" in result.columns

    def test_clv_returns_copy(self):
        """evaluate_clv returns a copy, not mutating the input."""
        df = pd.DataFrame({
            "predicted_margin": [7],
            "spread_line": [-3],
        })
        original_cols = set(df.columns)
        evaluate_clv(df)
        assert set(df.columns) == original_cols
        assert "clv" not in df.columns


class TestCLVByTier:
    """Tests for compute_clv_by_tier() — CLV breakdown by confidence tier."""

    def _make_clv_df(self):
        """3 games: high edge (4.0), medium edge (2.0), low edge (0.5)."""
        return pd.DataFrame({
            "predicted_margin": [7, 3, 2],
            "spread_line": [3, 1, 1.5],
            "clv": [2.0, -1.0, 0.5],
        })

    def test_tier_assignment(self):
        """Games are assigned to correct tiers based on edge magnitude."""
        df = self._make_clv_df()
        result = compute_clv_by_tier(df)
        tiers = set(result["tier"].tolist())
        assert "high" in tiers
        assert "medium" in tiers
        assert "low" in tiers

    def test_tier_metrics(self):
        """Verify mean_clv, median_clv, pct_beating_close per tier."""
        df = self._make_clv_df()
        result = compute_clv_by_tier(df)
        result_dict = {row["tier"]: row for _, row in result.iterrows()}

        # High tier: edge=4.0, clv=2.0 -> mean=2.0, pct=1.0
        assert abs(result_dict["high"]["mean_clv"] - 2.0) < 0.01
        assert abs(result_dict["high"]["pct_beating_close"] - 1.0) < 0.01

        # Medium tier: edge=2.0, clv=-1.0 -> mean=-1.0, pct=0.0
        assert abs(result_dict["medium"]["mean_clv"] - (-1.0)) < 0.01
        assert abs(result_dict["medium"]["pct_beating_close"] - 0.0) < 0.01

        # Low tier: edge=0.5, clv=0.5 -> mean=0.5, pct=1.0
        assert abs(result_dict["low"]["mean_clv"] - 0.5) < 0.01
        assert abs(result_dict["low"]["pct_beating_close"] - 1.0) < 0.01

    def test_all_columns_present(self):
        """Result has columns: tier, games, mean_clv, median_clv, pct_beating_close."""
        df = self._make_clv_df()
        result = compute_clv_by_tier(df)
        expected_cols = {"tier", "games", "mean_clv", "median_clv", "pct_beating_close"}
        assert set(result.columns) == expected_cols


class TestCLVBySeason:
    """Tests for compute_clv_by_season() — CLV breakdown by season."""

    def _make_season_clv_df(self):
        """4 games in 2022 (clv=[1, -2, 3, -1]) + 2 games in 2023 (clv=[2, 4])."""
        return pd.DataFrame({
            "season": [2022, 2022, 2022, 2022, 2023, 2023],
            "clv": [1, -2, 3, -1, 2, 4],
        })

    def test_season_groupby(self):
        """Games are correctly grouped by season."""
        df = self._make_season_clv_df()
        result = compute_clv_by_season(df)
        assert len(result) == 2
        seasons = set(result["season"].tolist())
        assert 2022 in seasons
        assert 2023 in seasons

    def test_season_metrics(self):
        """Verify mean_clv, pct_beating_close per season."""
        df = self._make_season_clv_df()
        result = compute_clv_by_season(df)
        result_dict = {int(row["season"]): row for _, row in result.iterrows()}

        # 2022: clv=[1, -2, 3, -1] -> mean=0.25, pct=0.5 (2 of 4 positive)
        assert abs(result_dict[2022]["mean_clv"] - 0.25) < 0.01
        assert result_dict[2022]["games"] == 4
        assert abs(result_dict[2022]["pct_beating_close"] - 0.5) < 0.01

        # 2023: clv=[2, 4] -> mean=3.0, pct=1.0
        assert abs(result_dict[2023]["mean_clv"] - 3.0) < 0.01
        assert result_dict[2023]["games"] == 2
        assert abs(result_dict[2023]["pct_beating_close"] - 1.0) < 0.01

    def test_all_columns_present(self):
        """Result has columns: season, games, mean_clv, median_clv, pct_beating_close."""
        df = self._make_season_clv_df()
        result = compute_clv_by_season(df)
        expected_cols = {"season", "games", "mean_clv", "median_clv", "pct_beating_close"}
        assert set(result.columns) == expected_cols


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
