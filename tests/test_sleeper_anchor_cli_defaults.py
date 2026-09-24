"""
CLI default-wiring tests for the shipped Sleeper consensus anchor family:
WR (.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md — SHIP 2026-08-22) plus RB and
TE (.planning/SLEEPER_ANCHOR_QB_RB_TE_GATE.md — SHIPPED 2026-09-23,
user-approved), each ``blend`` w=0.5. QB stays OFF (HOLD).

Covers the surfaces the ship touched:

1. ``scripts/generate_projections.py`` — weekly mode default-ON for
   WR+RB+TE; ``--no-sleeper-anchor`` opt-out.
2. ``scripts/backtest_projections.py`` — ``run_backtest()``'s own default
   evaluation path mirrors the shipped config (per repo convention:
   backtests evaluate the shipped config); ``--no-sleeper-anchor`` opt-out.
3. Both CLIs resolve the effective config list through the one shared
   resolver and apply it through the one shared loop, so they cannot drift.

Does not exercise the full ``main()`` pipelines (heavy data I/O). This file
is argparse/signature-level: it protects the *wiring*, not the lever's math
(see ``test_sleeper_consensus_anchor.py`` for that).
"""

import inspect
import os
import subprocess
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from sleeper_consensus_anchor import SHIPPED_DEFAULT_CONFIGS  # noqa: E402

import generate_projections  # noqa: E402
import backtest_projections  # noqa: E402


def _help(module):
    return subprocess.run(
        [sys.executable, module.__file__, "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout


class TestGenerateProjectionsCLIDefaults:
    def test_help_lists_no_sleeper_anchor_flag(self):
        out = _help(generate_projections)
        assert "--no-sleeper-anchor" in out
        assert "--consensus-anchor-src" in out


class TestBacktestRunBacktestDefaults:
    """run_backtest()'s own kwarg defaults ARE the "default evaluation
    path" — an un-flagged `run_backtest(seasons=...)` call (e.g. from
    scripts/production_eval.py's production-faithful harness) must reflect
    production: WR+RB+TE blend w=0.5."""

    def test_defaults_match_shipped_config(self):
        sig = inspect.signature(backtest_projections.run_backtest)
        default = sig.parameters["sleeper_anchor_configs"].default
        assert [dict(c) for c in default] == [
            {"position": "WR", "mode": "blend", "weight": 0.5},
            {"position": "RB", "mode": "blend", "weight": 0.5},
            {"position": "TE", "mode": "blend", "weight": 0.5},
        ]
        assert [dict(c) for c in default] == [dict(c) for c in SHIPPED_DEFAULT_CONFIGS]

    def test_legacy_single_slot_kwargs_removed(self):
        """The old primary/extra kwargs let a caller silently get a WR-only
        anchor; the config list replaces them."""
        params = inspect.signature(backtest_projections.run_backtest).parameters
        for legacy in (
            "consensus_anchor_src",
            "consensus_anchor_position",
            "consensus_anchor_extra_position",
        ):
            assert legacy not in params

    def test_help_lists_no_sleeper_anchor_flag(self):
        out = _help(backtest_projections)
        assert "--no-sleeper-anchor" in out
        assert "--consensus-anchor-src" in out


class TestResolverWiredIntoBothCLIs:
    """Both scripts delegate precedence to the same shared resolver and the
    same shared apply loop rather than duplicating them — assert the source
    actually calls them, so the two scripts cannot silently drift apart."""

    def test_generate_projections_calls_shared_resolver(self):
        src = inspect.getsource(generate_projections)
        assert "resolve_sleeper_anchor_configs(" in src
        assert "apply_sleeper_anchors(" in src

    def test_backtest_projections_calls_shared_resolver(self):
        src = inspect.getsource(backtest_projections)
        assert "resolve_sleeper_anchor_configs(" in src
        assert "apply_sleeper_anchors(" in src
