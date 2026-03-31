"""Tests for ship gate verdict logic, heuristic comparison, and safety floor.

Validates the ship-or-skip decision framework that determines whether ML
player models replace the heuristic baseline per position.
"""

import json
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from player_model_training import (
    build_ship_gate_report,
    compute_position_mae,
    generate_heuristic_predictions,
    ship_gate_verdict,
)


class TestShipGateVerdict:
    """Tests for ship_gate_verdict decision logic."""

    def test_ship_gate_verdict_ship(self):
        """ML MAE 4.50 vs heuristic 5.00 (10% improvement) on both OOF and holdout -> SHIP."""
        per_stat = [
            {"stat": "rushing_yards", "ml_mae": 18.0, "heuristic_mae": 20.0},
            {"stat": "rushing_tds", "ml_mae": 0.4, "heuristic_mae": 0.5},
        ]
        result = ship_gate_verdict(
            position="RB",
            ml_mae=4.50,
            heuristic_mae=5.00,
            oof_ml_mae=4.60,
            oof_heuristic_mae=5.10,
            per_stat_results=per_stat,
        )
        assert result["verdict"] == "SHIP"
        assert result["holdout_improvement_pct"] == pytest.approx(10.0, abs=0.1)
        assert result["oof_improvement_pct"] == pytest.approx(9.8, abs=0.2)
        assert result["safety_violation"] is False

    def test_ship_gate_verdict_skip_insufficient(self):
        """ML MAE 4.90 vs heuristic 5.00 (2% improvement, below 4% threshold) -> SKIP."""
        per_stat = [
            {"stat": "rushing_yards", "ml_mae": 19.0, "heuristic_mae": 20.0},
        ]
        result = ship_gate_verdict(
            position="RB",
            ml_mae=4.90,
            heuristic_mae=5.00,
            oof_ml_mae=4.85,
            oof_heuristic_mae=5.00,
            per_stat_results=per_stat,
        )
        assert result["verdict"] == "SKIP"
        assert result["holdout_improvement_pct"] == pytest.approx(2.0, abs=0.1)

    def test_ship_gate_verdict_skip_disagreement(self):
        """OOF shows 5% improvement but holdout shows 3% -> SKIP (dual agreement fails)."""
        per_stat = [
            {"stat": "receiving_yards", "ml_mae": 15.0, "heuristic_mae": 17.0},
        ]
        result = ship_gate_verdict(
            position="WR",
            ml_mae=4.85,
            heuristic_mae=5.00,  # 3% holdout improvement (below 4%)
            oof_ml_mae=4.50,
            oof_heuristic_mae=4.74,  # ~5% OOF improvement (above 4%)
            per_stat_results=per_stat,
        )
        assert result["verdict"] == "SKIP"
        # OOF passes but holdout does not
        assert result["oof_improvement_pct"] > 4.0
        assert result["holdout_improvement_pct"] < 4.0

    def test_safety_floor(self):
        """One stat model 12% worse than heuristic -> SKIP even if overall MAE improved."""
        per_stat = [
            {"stat": "rushing_yards", "ml_mae": 16.0, "heuristic_mae": 20.0},  # Good
            {"stat": "rushing_tds", "ml_mae": 0.56, "heuristic_mae": 0.50},  # 12% worse -> violation
        ]
        result = ship_gate_verdict(
            position="RB",
            ml_mae=4.00,
            heuristic_mae=5.00,  # 20% overall improvement
            oof_ml_mae=4.00,
            oof_heuristic_mae=5.00,
            per_stat_results=per_stat,
        )
        assert result["verdict"] == "SKIP"
        assert result["safety_violation"] is True


class TestHeuristicBaseline:
    """Tests for heuristic prediction generation on identical rows."""

    def test_heuristic_baseline_on_identical_rows(self):
        """Heuristic predictions generated on same DataFrame produce non-NaN fantasy points."""
        # Build a minimal DataFrame with the rolling columns the heuristic expects
        n = 20
        data = {
            "season": [2023] * n,
            "week": list(range(1, n + 1)),
            "position": ["WR"] * n,
            "player_id": [f"P{i}" for i in range(n)],
            "team": ["KC"] * n,
        }
        # Add rolling columns for WR stats: targets, receptions, receiving_yards, receiving_tds
        for stat in ["targets", "receptions", "receiving_yards", "receiving_tds"]:
            data[f"{stat}_roll3"] = np.random.uniform(1, 10, n)
            data[f"{stat}_roll6"] = np.random.uniform(1, 10, n)
            data[f"{stat}_std"] = np.random.uniform(0, 2, n)

        # Add usage columns
        data["target_share"] = np.random.uniform(0.1, 0.3, n)
        data["snap_pct"] = np.random.uniform(0.5, 1.0, n)

        df = pd.DataFrame(data)
        result = generate_heuristic_predictions(df, "WR")

        # Should have pred_ columns for all WR stats
        for stat in ["targets", "receptions", "receiving_yards", "receiving_tds"]:
            col = f"pred_{stat}"
            assert col in result.columns, f"Missing column {col}"
            assert result[col].notna().all(), f"NaN values in {col}"


class TestShipGateReport:
    """Tests for ship gate report generation."""

    def test_ship_gate_report_json(self):
        """ship_gate_report produces dict with required keys."""
        position_results = [
            {
                "position": "QB",
                "ml_mae": 6.00,
                "heuristic_mae": 6.58,
                "holdout_improvement_pct": 8.81,
                "oof_improvement_pct": 7.50,
                "safety_violation": False,
                "verdict": "SHIP",
            },
            {
                "position": "RB",
                "ml_mae": 5.10,
                "heuristic_mae": 5.06,
                "holdout_improvement_pct": -0.79,
                "oof_improvement_pct": 1.20,
                "safety_violation": False,
                "verdict": "SKIP",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            report = build_ship_gate_report(position_results, output_dir=tmpdir)

            assert "positions" in report
            assert "summary" in report
            assert "timestamp" in report
            assert len(report["positions"]) == 2
            assert "1/2" in report["summary"] or "1 of 2" in report["summary"]

            # Check JSON file was saved
            json_path = os.path.join(tmpdir, "ship_gate_report.json")
            assert os.path.exists(json_path)
            with open(json_path) as f:
                saved = json.load(f)
            assert saved["positions"] == report["positions"]
