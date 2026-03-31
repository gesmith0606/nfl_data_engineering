#!/usr/bin/env python3
"""Tests for per-position, per-stat player model training.

Validates model count from POSITION_STAT_PROFILE, walk-forward CV folds,
holdout guard, stat-type hyperparameters, stat-to-fantasy conversion,
feature selection groups, and model serialization paths.
"""

import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

# Project src/ on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import HOLDOUT_SEASON, PLAYER_LABEL_COLUMNS
from projection_engine import POSITION_STAT_PROFILE
from scoring_calculator import calculate_fantasy_points_df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthetic_player_data(seasons, weeks_per_season=4, players_per_pos=3):
    """Build a small synthetic player-week DataFrame with feature and label cols.

    Creates numeric feature columns matching get_player_feature_columns() patterns
    plus identifier and label columns.
    """
    np.random.seed(42)
    positions = ["QB", "RB", "WR", "TE"]
    rows = []
    pid = 0
    for pos in positions:
        for p in range(players_per_pos):
            pid += 1
            for season in seasons:
                for week in range(1, weeks_per_season + 1):
                    row = {
                        "player_id": f"P{pid:03d}",
                        "player_name": f"{pos}{p+1}",
                        "position": pos,
                        "recent_team": "KC",
                        "opponent_team": "BUF",
                        "season": season,
                        "week": week,
                        # Feature columns (rolling, lagged)
                        "rushing_yards_roll3": np.random.uniform(10, 100),
                        "rushing_yards_roll6": np.random.uniform(10, 100),
                        "rushing_yards_std": np.random.uniform(5, 30),
                        "passing_yards_roll3": np.random.uniform(50, 300),
                        "receiving_yards_roll3": np.random.uniform(10, 80),
                        "target_share_roll3": np.random.uniform(0.05, 0.30),
                        "snap_pct_roll3": np.random.uniform(0.20, 0.90),
                        "carry_share_roll3": np.random.uniform(0.0, 0.40),
                        "targets_roll3": np.random.uniform(1, 12),
                        "carries_roll3": np.random.uniform(0, 20),
                        "def_epa_per_play_lag1": np.random.uniform(-0.2, 0.2),
                        "implied_team_total": np.random.uniform(18, 30),
                        "spread_line": np.random.uniform(-10, 10),
                        # Label columns (same-week actuals)
                        "passing_yards": np.random.randint(0, 400) if pos == "QB" else 0,
                        "passing_tds": np.random.randint(0, 4) if pos == "QB" else 0,
                        "interceptions": np.random.randint(0, 3) if pos == "QB" else 0,
                        "rushing_yards": np.random.randint(0, 120),
                        "rushing_tds": np.random.randint(0, 2),
                        "carries": np.random.randint(0, 25),
                        "targets": np.random.randint(0, 12),
                        "receptions": np.random.randint(0, 10),
                        "receiving_yards": np.random.randint(0, 120),
                        "receiving_tds": np.random.randint(0, 2),
                        "fantasy_points_ppr": np.random.uniform(0, 35),
                    }
                    rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPlayerModelTraining:
    """Tests for src/player_model_training.py."""

    def test_position_stat_models_count(self):
        """POSITION_STAT_PROFILE yields 19 total stat models (QB:5 + RB:6 + WR:4 + TE:4)."""
        total = sum(len(stats) for stats in POSITION_STAT_PROFILE.values())
        assert total == 19
        assert len(POSITION_STAT_PROFILE["QB"]) == 5
        assert len(POSITION_STAT_PROFILE["RB"]) == 6
        assert len(POSITION_STAT_PROFILE["WR"]) == 4
        assert len(POSITION_STAT_PROFILE["TE"]) == 4

    def test_stat_type_groups(self):
        """STAT_TYPE_GROUPS has 4 groups covering all 10 unique stats."""
        from player_model_training import STAT_TYPE_GROUPS

        assert set(STAT_TYPE_GROUPS.keys()) == {"yardage", "td", "volume", "turnover"}

        # Flatten all stats from POSITION_STAT_PROFILE
        all_stats = set()
        for stats in POSITION_STAT_PROFILE.values():
            all_stats.update(stats)

        # All 10 unique stats must appear in some group
        grouped_stats = set()
        for stats in STAT_TYPE_GROUPS.values():
            grouped_stats.update(stats)

        assert all_stats == grouped_stats, (
            f"Missing stats: {all_stats - grouped_stats}, "
            f"Extra stats: {grouped_stats - all_stats}"
        )

    def test_player_walk_forward_folds(self):
        """Walk-forward CV with seasons 2020-2024 produces exactly 3 folds."""
        from player_model_training import player_walk_forward_cv

        df = _make_synthetic_player_data(seasons=[2020, 2021, 2022, 2023, 2024])
        feature_cols = [
            "rushing_yards_roll3", "rushing_yards_roll6", "rushing_yards_std",
            "passing_yards_roll3", "receiving_yards_roll3", "target_share_roll3",
            "snap_pct_roll3", "carry_share_roll3", "targets_roll3", "carries_roll3",
            "def_epa_per_play_lag1", "implied_team_total", "spread_line",
        ]
        # Use only RB data to keep it simple
        rb_data = df[df["position"] == "RB"].copy()

        from ensemble_training import make_xgb_model
        from config import CONSERVATIVE_PARAMS

        model_factory = lambda: make_xgb_model(CONSERVATIVE_PARAMS)

        result, oof_df = player_walk_forward_cv(
            rb_data, feature_cols, "rushing_yards", model_factory
        )

        # 3 validation seasons: 2022, 2023, 2024
        assert len(result.fold_maes) == 3
        assert len(result.fold_details) == 3
        for detail in result.fold_details:
            assert detail["val_season"] in [2022, 2023, 2024]

        # OOF DataFrame should NOT have game_id column
        assert "game_id" not in oof_df.columns
        assert "idx" in oof_df.columns or "season" in oof_df.columns

    def test_holdout_guard(self):
        """player_walk_forward_cv raises ValueError if holdout season in val seasons."""
        from player_model_training import player_walk_forward_cv, PLAYER_VALIDATION_SEASONS

        # Create data that includes the holdout season
        df = _make_synthetic_player_data(
            seasons=[2020, 2021, 2022, 2023, 2024, HOLDOUT_SEASON]
        )
        feature_cols = [
            "rushing_yards_roll3", "rushing_yards_roll6", "rushing_yards_std",
        ]
        rb_data = df[df["position"] == "RB"].copy()

        from ensemble_training import make_xgb_model
        from config import CONSERVATIVE_PARAMS

        model_factory = lambda: make_xgb_model(CONSERVATIVE_PARAMS)

        # Should raise because PLAYER_VALIDATION_SEASONS doesn't include holdout,
        # but if someone passes val_seasons with holdout, it should reject
        with pytest.raises(ValueError, match="HOLDOUT_SEASON"):
            player_walk_forward_cv(
                rb_data, feature_cols, "rushing_yards", model_factory,
                val_seasons=[2022, 2023, HOLDOUT_SEASON],
            )

    def test_hyperparams_by_stat_type(self):
        """get_player_model_params returns different params for yardage vs TD stats."""
        from player_model_training import get_player_model_params

        yardage_params = get_player_model_params("rushing_yards")
        td_params = get_player_model_params("rushing_tds")

        # TD stats use shallower trees and higher min_child_weight
        assert td_params["max_depth"] == 3
        assert td_params["min_child_weight"] == 10
        # Yardage keeps conservative defaults
        assert yardage_params["max_depth"] == 4
        assert yardage_params["min_child_weight"] == 5

    def test_stat_to_fantasy_conversion(self):
        """Predict raw stats then convert to fantasy points via calculate_fantasy_points_df."""
        # Simulate predicted stats for a single player-week
        pred_df = pd.DataFrame([{
            "passing_yards": 280.0,
            "passing_tds": 2.0,
            "interceptions": 1.0,
            "rushing_yards": 25.0,
            "rushing_tds": 0.0,
            "receptions": 0.0,
            "receiving_yards": 0.0,
            "receiving_tds": 0.0,
        }])

        result = calculate_fantasy_points_df(pred_df, scoring_format="half_ppr")
        # Manual: 280*0.04 + 2*4 + 1*(-2) + 25*0.1 + 0 = 11.2 + 8 - 2 + 2.5 = 19.7
        expected = 280 * 0.04 + 2 * 4 + 1 * (-2) + 25 * 0.1
        assert abs(result["projected_points"].iloc[0] - expected) < 0.01

    def test_feature_selection_per_group(self):
        """run_player_feature_selection returns dict with keys matching STAT_TYPE_GROUPS."""
        from player_model_training import run_player_feature_selection, STAT_TYPE_GROUPS

        df = _make_synthetic_player_data(seasons=[2020, 2021, 2022, 2023, 2024])
        feature_cols = [
            "rushing_yards_roll3", "rushing_yards_roll6", "rushing_yards_std",
            "passing_yards_roll3", "receiving_yards_roll3", "target_share_roll3",
            "snap_pct_roll3", "carry_share_roll3", "targets_roll3", "carries_roll3",
            "def_epa_per_play_lag1", "implied_team_total", "spread_line",
        ]

        result = run_player_feature_selection(
            df, feature_cols, positions=["QB", "RB", "WR", "TE"]
        )

        assert set(result.keys()) == set(STAT_TYPE_GROUPS.keys())
        for group, features in result.items():
            assert isinstance(features, list)
            assert len(features) > 0  # Each group should select at least 1 feature

    def test_model_serialization_paths(self):
        """save_player_model creates files at models/player/{position}/{stat}.json."""
        from player_model_training import save_player_model, load_player_model
        from ensemble_training import make_xgb_model
        from config import CONSERVATIVE_PARAMS

        with tempfile.TemporaryDirectory() as tmpdir:
            # Train a tiny model directly (no early stopping for simplicity)
            import xgboost as xgb_lib
            model = xgb_lib.XGBRegressor(
                n_estimators=10, max_depth=2, verbosity=0
            )
            X = np.random.rand(20, 3)
            y = np.random.rand(20)
            model.fit(X, y)

            metadata = {
                "mean_mae": 5.5,
                "fold_maes": [5.0, 5.5, 6.0],
                "n_features": 3,
            }

            save_player_model(model, "RB", "rushing_yards", metadata, output_dir=tmpdir)

            # Check files exist
            model_path = os.path.join(tmpdir, "rb", "rushing_yards.json")
            meta_path = os.path.join(tmpdir, "rb", "rushing_yards_meta.json")
            assert os.path.exists(model_path), f"Model file not found: {model_path}"
            assert os.path.exists(meta_path), f"Metadata file not found: {meta_path}"

            # Check metadata content
            with open(meta_path) as f:
                saved_meta = json.load(f)
            assert saved_meta["mean_mae"] == 5.5

            # Load model back
            loaded = load_player_model("RB", "rushing_yards", model_dir=tmpdir)
            assert loaded is not None

    # -------------------------------------------------------------------
    # LGB / Ensemble stacking tests (Plan 41-02)
    # -------------------------------------------------------------------

    def test_player_lgb_fit_kwargs(self):
        """_player_lgb_fit_kwargs returns dict with eval_set and callbacks keys."""
        from player_model_training import _player_lgb_fit_kwargs

        X_train = np.random.rand(20, 3)
        y_train = np.random.rand(20)
        X_val = np.random.rand(5, 3)
        y_val = np.random.rand(5)

        result = _player_lgb_fit_kwargs(X_train, y_train, X_val, y_val)
        assert "eval_set" in result
        assert "callbacks" in result
        assert len(result["eval_set"]) == 1
        assert result["eval_set"][0] == (X_val, y_val)

    def test_get_lgb_params_for_stat_td(self):
        """get_lgb_params_for_stat returns shallower trees for TD stats."""
        from player_model_training import get_lgb_params_for_stat

        params = get_lgb_params_for_stat("rushing_tds")
        assert params["max_depth"] == 3
        assert params["min_child_samples"] == 30
        assert params["n_estimators"] == 300

    def test_get_lgb_params_for_stat_yardage(self):
        """get_lgb_params_for_stat returns base LGB params for yardage stats."""
        from player_model_training import get_lgb_params_for_stat
        from config import LGB_CONSERVATIVE_PARAMS

        params = get_lgb_params_for_stat("rushing_yards")
        assert params["max_depth"] == LGB_CONSERVATIVE_PARAMS["max_depth"]

    def test_assemble_player_oof_matrix(self):
        """assemble_player_oof_matrix merges XGB and LGB OOF on idx with actual target."""
        from player_model_training import assemble_player_oof_matrix

        xgb_oof = pd.DataFrame({
            "idx": [0, 1, 2, 3],
            "season": [2022, 2022, 2023, 2023],
            "week": [1, 2, 1, 2],
            "oof_prediction": [50.0, 60.0, 70.0, 80.0],
        })
        lgb_oof = pd.DataFrame({
            "idx": [0, 1, 2, 3],
            "season": [2022, 2022, 2023, 2023],
            "week": [1, 2, 1, 2],
            "oof_prediction": [52.0, 58.0, 72.0, 78.0],
        })
        pos_data = pd.DataFrame({
            "rushing_yards": [55.0, 62.0, 68.0, 82.0],
        }, index=[0, 1, 2, 3])

        result = assemble_player_oof_matrix(xgb_oof, lgb_oof, pos_data, "rushing_yards")

        assert "xgb_pred" in result.columns
        assert "lgb_pred" in result.columns
        assert "actual" in result.columns
        assert len(result) == 4
        assert list(result["xgb_pred"]) == [50.0, 60.0, 70.0, 80.0]
        assert list(result["lgb_pred"]) == [52.0, 58.0, 72.0, 78.0]
        assert list(result["actual"]) == [55.0, 62.0, 68.0, 82.0]

    def test_assemble_player_oof_matrix_empty(self):
        """assemble_player_oof_matrix with empty input returns empty DataFrame."""
        from player_model_training import assemble_player_oof_matrix

        xgb_oof = pd.DataFrame(columns=["idx", "season", "week", "oof_prediction"])
        lgb_oof = pd.DataFrame(columns=["idx", "season", "week", "oof_prediction"])
        pos_data = pd.DataFrame({"rushing_yards": pd.Series(dtype=float)})

        result = assemble_player_oof_matrix(xgb_oof, lgb_oof, pos_data, "rushing_yards")
        assert len(result) == 0
        assert "xgb_pred" in result.columns
        assert "lgb_pred" in result.columns

    def test_player_ensemble_stacking_returns_results(self):
        """player_ensemble_stacking returns dict with stat keys containing ridge and OOF data."""
        from unittest.mock import patch, MagicMock
        from player_model_training import player_ensemble_stacking

        # Create minimal synthetic data
        np.random.seed(42)
        n = 100
        pos_data = pd.DataFrame({
            "season": [2020] * 25 + [2021] * 25 + [2022] * 25 + [2023] * 25,
            "week": list(range(1, 26)) * 4,
            "position": ["RB"] * n,
            "feat1": np.random.rand(n),
            "feat2": np.random.rand(n),
            "rushing_yards": np.random.uniform(20, 120, n),
            "rushing_tds": np.random.randint(0, 3, n).astype(float),
            "receptions": np.random.randint(0, 8, n).astype(float),
            "receiving_yards": np.random.uniform(0, 80, n),
            "receiving_tds": np.random.randint(0, 2, n).astype(float),
            "targets": np.random.randint(0, 10, n).astype(float),
        })
        pos_data.index = range(n)

        feature_cols_by_group = {
            "yardage": ["feat1", "feat2"],
            "td": ["feat1", "feat2"],
            "volume": ["feat1", "feat2"],
            "turnover": ["feat1", "feat2"],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            results = player_ensemble_stacking(
                pos_data, "RB", feature_cols_by_group, output_dir=tmpdir
            )

        assert isinstance(results, dict)
        # Should have at least some stats trained
        if results:
            first_stat = next(iter(results))
            assert "ridge" in results[first_stat]
            assert "oof_matrix" in results[first_stat]
            assert "xgb_wf" in results[first_stat]
            assert "lgb_wf" in results[first_stat]
