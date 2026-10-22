"""CLI/wiring tests for the dispersion-shrink lever (SHIPPED 2026-10-21).

Argparse- and signature-level only, mirroring
``test_sleeper_anchor_cli_defaults.py``: this protects the *wiring* — that
the lever is default-ON in both CLIs, opt-out-able, and placed correctly in
the pipeline — not the lever's math (see ``test_dispersion_shrink.py``).

The ordering test matters for safety rather than style: the shrink RAISES
low projections, so it must run before ``generate_projections.py``'s injury
invariant re-assertion, which is what stops a sidelined player being shrunk
back onto the board.
"""

import inspect
import os
import subprocess
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from dispersion_shrink import SHRINK_FACTOR  # noqa: E402

import backtest_projections  # noqa: E402
import generate_projections  # noqa: E402

_GENERATOR_SRC = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "generate_projections.py"
)


def _help(module):
    return subprocess.run(
        [sys.executable, module.__file__, "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout


class TestGenerateProjectionsWiring:
    def test_help_lists_the_opt_out_and_the_knob(self):
        out = _help(generate_projections)
        assert "--no-dispersion-shrink" in out
        assert "--dispersion-shrink-k" in out

    def test_shrink_runs_after_the_sleeper_anchor_and_before_the_injury_invariant(self):
        """Placement is the safety property: the anchors must have already
        run (the retro validated anchors-then-shrink), and the injury
        invariant must re-assert afterwards."""
        src = open(_GENERATOR_SRC, encoding="utf-8").read()
        anchor = src.index("projections, sleeper_stats = apply_sleeper_anchors(")
        shrink = src.index("projections, shrink_stats = apply_dispersion_shrink(")
        invariant = src.index("# --- injury invariant")
        assert anchor < shrink < invariant

    def test_lever_is_gated_off_in_preseason_mode(self):
        """Preseason projects season totals, a different magnitude scale the
        retro never measured."""
        src = open(_GENERATOR_SRC, encoding="utf-8").read()
        guard = "if not args.preseason and not args.no_dispersion_shrink:"
        assert guard in src


class TestBacktestWiring:
    """Per repo convention a backtest evaluates the SHIPPED config, so the
    lever is default-ON here too — otherwise every future gate would be
    measured against a model production does not run."""

    def test_run_backtest_defaults_mirror_production(self):
        params = inspect.signature(backtest_projections.run_backtest).parameters
        assert params["no_dispersion_shrink"].default is False
        assert params["dispersion_shrink_k"].default == SHRINK_FACTOR

    def test_help_lists_the_opt_out(self):
        out = _help(backtest_projections)
        assert "--no-dispersion-shrink" in out


class TestShippedQBAnchor:
    """QB joined the shipped Sleeper anchor set on 2026-10-21
    (.planning/SEASON_2026_MIDSEASON_RETRO.md). Both CLIs resolve through the
    one shared resolver, so neither can drift from the other."""

    def test_qb_is_in_the_default_resolved_set_for_both_clis(self):
        from sleeper_consensus_anchor import resolve_sleeper_anchor_configs

        cfgs = resolve_sleeper_anchor_configs(None, "WR", "near_tie", 0.3, False)
        qb = [c for c in cfgs if c["position"] == "QB"]
        assert qb == [{"position": "QB", "mode": "blend", "weight": 0.5}]

    def test_backtest_default_kwarg_includes_qb(self):
        default = (
            inspect.signature(backtest_projections.run_backtest)
            .parameters["sleeper_anchor_configs"]
            .default
        )
        assert {c["position"] for c in default} == {"WR", "RB", "TE", "QB"}

    def test_no_sleeper_anchor_still_disables_qb_too(self):
        from sleeper_consensus_anchor import resolve_sleeper_anchor_configs

        assert resolve_sleeper_anchor_configs(None, "WR", "blend", 0.5, True) == []
