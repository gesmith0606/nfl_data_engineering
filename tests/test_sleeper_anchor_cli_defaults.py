"""
CLI default-wiring tests for the shipped Sleeper consensus anchor
(.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md — SHIP verdict 2026-08-22,
user-approved).

Covers the three surfaces the ship touched:

1. ``scripts/generate_projections.py`` — weekly mode default-ON for WR
   (blend, weight=0.5); ``--no-sleeper-anchor`` opt-out.
2. ``scripts/backtest_projections.py`` — ``run_backtest()``'s own default
   evaluation path mirrors the shipped config (per repo convention:
   backtests evaluate the shipped config); ``--no-sleeper-anchor`` opt-out.
3. Both CLIs still support the pre-existing ``--consensus-anchor-src``
   explicit-override machinery (QB/RB/TE, other modes/weights) unchanged.

Does not exercise the full ``main()`` pipelines (heavy data I/O) — that is
covered by the smoke runs documented in the gate doc's shipping session.
This file is argparse/signature-level: it protects the *wiring*, not the
lever's math (see ``test_sleeper_consensus_anchor.py`` for that).
"""

import inspect
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from sleeper_consensus_anchor import (  # noqa: E402
    SHIPPED_DEFAULT_MODE,
    SHIPPED_DEFAULT_POSITION,
    SHIPPED_DEFAULT_SRC,
    SHIPPED_DEFAULT_WEIGHT,
)

import generate_projections  # noqa: E402
import backtest_projections  # noqa: E402


class TestGenerateProjectionsCLIDefaults:
    def test_help_lists_no_sleeper_anchor_flag(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, generate_projections.__file__, "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "--no-sleeper-anchor" in result.stdout
        assert "--consensus-anchor-src" in result.stdout


class TestBacktestRunBacktestDefaults:
    """run_backtest()'s own kwarg defaults ARE the "default evaluation
    path" — per repo convention (mirrors how prior shipped levers made
    backtests evaluate the shipped config), these must equal the shipped
    Sleeper-anchor config so an un-flagged `run_backtest(seasons=...)` call
    (e.g. from scripts/production_eval.py's production-faithful harness)
    reflects production."""

    def test_defaults_match_shipped_config(self):
        sig = inspect.signature(backtest_projections.run_backtest)
        assert sig.parameters["consensus_anchor_src"].default == SHIPPED_DEFAULT_SRC
        assert (
            sig.parameters["consensus_anchor_position"].default
            == SHIPPED_DEFAULT_POSITION
        )
        assert sig.parameters["consensus_anchor_mode"].default == SHIPPED_DEFAULT_MODE
        assert (
            sig.parameters["consensus_anchor_weight"].default == SHIPPED_DEFAULT_WEIGHT
        )

    def test_help_lists_no_sleeper_anchor_flag(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, backtest_projections.__file__, "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "--no-sleeper-anchor" in result.stdout
        assert "--consensus-anchor-src" in result.stdout


class TestResolverWiredIntoBothCLIs:
    """Both scripts delegate precedence to the same shared resolver
    (sleeper_consensus_anchor.resolve_sleeper_anchor_config) rather than
    duplicating the if/elif/else — assert the source actually calls it,
    so the two scripts cannot silently drift apart."""

    def test_generate_projections_calls_shared_resolver(self):
        src = inspect.getsource(generate_projections)
        assert "resolve_sleeper_anchor_config(" in src

    def test_backtest_projections_calls_shared_resolver(self):
        src = inspect.getsource(backtest_projections)
        assert "resolve_sleeper_anchor_config(" in src
