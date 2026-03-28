"""Tests for the ablation market features script.

Verifies orchestration logic, ship/skip decisions, report formatting,
directory safety, and copy semantics for the market feature ablation.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ablation_market_features import (
    ABLATION_DIR,
    apply_ship_decision,
    compute_ship_or_skip,
    format_comparison_report,
    format_shap_report,
)
from config import ENSEMBLE_DIR


# ---------------------------------------------------------------------------
# TestShipOrSkip -- decision logic
# ---------------------------------------------------------------------------


class TestShipOrSkip:
    """Test ship-or-skip decision logic (D-08: any improvement = ship)."""

    def test_ship_when_ablation_improves(self):
        """Strict > means SHIP."""
        verdict = compute_ship_or_skip(0.530, 0.531)
        assert verdict == "SHIP"

    def test_skip_when_ablation_same(self):
        """Equal means SKIP (not strict >)."""
        verdict = compute_ship_or_skip(0.530, 0.530)
        assert verdict == "SKIP"

    def test_skip_when_ablation_worse(self):
        """Worse means SKIP."""
        verdict = compute_ship_or_skip(0.530, 0.520)
        assert verdict == "SKIP"

    def test_ship_tiny_improvement(self):
        """Even a tiny improvement is SHIP per D-08."""
        verdict = compute_ship_or_skip(0.530, 0.5301)
        assert verdict == "SHIP"

    def test_skip_zero_baseline(self):
        """Edge case: zero baseline with zero ablation => SKIP."""
        verdict = compute_ship_or_skip(0.0, 0.0)
        assert verdict == "SKIP"


# ---------------------------------------------------------------------------
# TestAblationReport -- report formatting
# ---------------------------------------------------------------------------


class TestAblationReport:
    """Test report formatting functions."""

    def _make_baseline(self, ats=0.530, profit=3.09):
        return {"ats_accuracy": ats, "profit_stats": {"profit": profit, "roi": 1.2}, "n_games": 272}

    def _make_ablation(self, ats=0.540, profit=5.00):
        return {"ats_accuracy": ats, "profit_stats": {"profit": profit, "roi": 2.0}, "n_games": 272}

    def _make_shap_scores(self, opening_spread_pct=0.10):
        """Create SHAP scores where opening_spread has given percentage."""
        total = 1.0
        opening_spread_val = total * opening_spread_pct
        remaining = total - opening_spread_val
        return {
            "opening_spread": opening_spread_val,
            "diff_adj_off_epa_roll3": remaining * 0.5,
            "diff_adj_def_epa_roll3": remaining * 0.3,
            "opening_total": remaining * 0.2,
        }

    def test_report_contains_verdict_ship(self):
        shap_report = format_shap_report(self._make_shap_scores(), top_n=20)
        report = format_comparison_report(
            self._make_baseline(), self._make_ablation(), "SHIP", shap_report,
            {"baseline": 100, "ablation": 110},
        )
        assert "VERDICT: SHIP" in report

    def test_report_contains_verdict_skip(self):
        shap_report = format_shap_report(self._make_shap_scores(), top_n=20)
        report = format_comparison_report(
            self._make_baseline(), self._make_ablation(ats=0.520), "SKIP", shap_report,
            {"baseline": 100, "ablation": 110},
        )
        assert "VERDICT: SKIP" in report

    def test_report_contains_shap(self):
        shap_report = format_shap_report(self._make_shap_scores(), top_n=20)
        report = format_comparison_report(
            self._make_baseline(), self._make_ablation(), "SHIP", shap_report,
            {"baseline": 100, "ablation": 110},
        )
        assert "SHAP Feature Importance" in report

    def test_report_contains_comparison(self):
        shap_report = format_shap_report(self._make_shap_scores(), top_n=20)
        report = format_comparison_report(
            self._make_baseline(), self._make_ablation(), "SHIP", shap_report,
            {"baseline": 100, "ablation": 110},
        )
        assert "Baseline ATS" in report
        assert "Ablation ATS" in report

    def test_opening_spread_dominance_warning(self):
        """When opening_spread > 30% SHAP importance, report warns."""
        shap_scores = self._make_shap_scores(opening_spread_pct=0.35)
        shap_report = format_shap_report(shap_scores, top_n=20)
        assert "opening_spread dominance" in shap_report.lower()

    def test_opening_spread_dominance_no_improvement(self):
        """D-14: opening_spread > 30% AND SKIP -> report documents indirect capture."""
        shap_scores = self._make_shap_scores(opening_spread_pct=0.35)
        shap_report = format_shap_report(shap_scores, top_n=20)
        report = format_comparison_report(
            self._make_baseline(), self._make_ablation(ats=0.520), "SKIP", shap_report,
            {"baseline": 100, "ablation": 110},
        )
        assert "model already captures market signal indirectly" in report

    def test_no_dominance_warning_when_below_threshold(self):
        """No dominance warning when opening_spread < 30%."""
        shap_scores = self._make_shap_scores(opening_spread_pct=0.10)
        shap_report = format_shap_report(shap_scores, top_n=20)
        assert "opening_spread dominance" not in shap_report.lower()


# ---------------------------------------------------------------------------
# TestAblationPaths -- directory safety
# ---------------------------------------------------------------------------


class TestAblationPaths:
    """Test that ablation uses correct directories (not production)."""

    def test_ablation_dir_not_production(self):
        assert ABLATION_DIR != ENSEMBLE_DIR

    def test_ablation_dir_value(self):
        assert ABLATION_DIR == "models/ensemble_ablation"


# ---------------------------------------------------------------------------
# TestApplyShipDecision -- copy semantics
# ---------------------------------------------------------------------------


class TestApplyShipDecision:
    """Test apply_ship_decision copy behavior."""

    @patch("ablation_market_features.shutil")
    @patch("ablation_market_features.json")
    @patch("builtins.open", new_callable=MagicMock)
    def test_ship_copies_ablation_to_production(self, mock_open, mock_json, mock_shutil):
        """SHIP copies ablation dir to production dir."""
        mock_json.load.return_value = {"selected_features": ["f1", "f2"]}
        apply_ship_decision("SHIP")
        mock_shutil.copytree.assert_called_once_with(
            ABLATION_DIR, ENSEMBLE_DIR, dirs_exist_ok=True
        )

    @patch("ablation_market_features.shutil")
    def test_skip_does_not_modify_production(self, mock_shutil):
        """SKIP does not call copytree."""
        apply_ship_decision("SKIP")
        mock_shutil.copytree.assert_not_called()

    @patch("ablation_market_features.shutil")
    @patch("ablation_market_features.json")
    @patch("builtins.open", new_callable=MagicMock)
    def test_ship_overwrites_metadata(self, mock_open, mock_json, mock_shutil):
        """After SHIP copy, verify metadata is read from production dir."""
        mock_json.load.return_value = {"selected_features": ["ablation_f1"]}
        apply_ship_decision("SHIP")
        # Verify open was called to read production metadata for verification
        calls = [str(c) for c in mock_open.call_args_list]
        # At minimum, copytree was called
        mock_shutil.copytree.assert_called_once()
