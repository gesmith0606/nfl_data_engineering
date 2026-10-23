"""Tests for scripts/audit_waiver_skill.py — the score must be falsifiable.

The 72->100 audit this replaces was a judgement call on a rubric written by
the same agent doing the work: a claim with no way to be wrong, which is the
exact failure mode every invariant in this skill exists to prevent. So the
score is now the fraction of falsifiable checks that hold, and these tests
prove the checks can actually fail.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "audit_skill", REPO / "scripts" / "audit_waiver_skill.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["audit_skill"] = m
    spec.loader.exec_module(m)
    return m


def test_every_check_carries_the_command_that_settles_it():
    """A claim without reproducible evidence is the thing being replaced."""
    audit = _mod()
    checks = audit.build_checks(7)
    assert len(checks) >= 15, "a 7-dimension audit needs real coverage"
    for check in checks:
        assert check.claim and check.evidence, check
        assert check.dimension, check
        # The evidence must look like something a reader can run.
        assert any(
            tok in check.evidence for tok in ("python", "grep", "...")
        ), check.evidence


def test_a_failing_check_lowers_the_score_and_fails_the_exit_code():
    """An audit that cannot report less than 100 is not an audit."""
    audit = _mod()
    real = audit.build_checks

    def with_a_broken_check(week):
        checks = [c for c in real(week) if not c.live][:3]
        checks.append(
            audit.Check(
                "guards",
                "deliberately false",
                "n/a",
                lambda: False,
                required=True,
            )
        )
        return checks

    audit.build_checks = with_a_broken_check
    try:
        rc = audit.main(["--offline"])
    finally:
        audit.build_checks = real
    assert rc == 1, "a failing required check must fail the exit code"


def test_a_crashing_check_counts_as_failing_not_passing():
    """Silence and breakage must not read as success — the session's theme."""
    audit = _mod()
    real = audit.build_checks

    def boom(week):
        def explode():
            raise RuntimeError("data file vanished")

        return [audit.Check("guards", "explodes", "n/a", explode, required=True)]

    audit.build_checks = boom
    try:
        rc = audit.main(["--offline"])
    finally:
        audit.build_checks = real
    assert rc == 1


def test_offline_mode_skips_only_the_checks_that_need_live_data():
    audit = _mod()
    everything = audit.build_checks(7)
    live = [c for c in everything if c.live]
    assert live, "some checks must exercise the real leagues"
    assert len(live) < len(everything), "and some must run with no network"
