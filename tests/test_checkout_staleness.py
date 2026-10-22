"""Unit tests for waiver_wire.checkout_age_warning.

A 7-week-old checkout once produced two confident wrong answers in one
session: that the weekly pipeline had died (the crons were green) and that the
waiver-claim tooling did not exist (it was on origin/main). The weekly crons
commit the upcoming board and the day's Bronze snapshots, so commit age is a
cheap, network-free proxy for "these numbers are stale".
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)

checkout_age_warning = waiver_wire.checkout_age_warning


class _Result:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _at(monkeypatch, epoch_seconds, now):
    monkeypatch.setattr(
        waiver_wire.subprocess,
        "run",
        lambda *a, **k: _Result(0, f"{epoch_seconds}\n"),
    )
    monkeypatch.setattr(waiver_wire.time, "time", lambda: now)


def test_fresh_checkout_is_silent(monkeypatch):
    now = 1_000_000_000
    _at(monkeypatch, now - 3600, now)
    assert checkout_age_warning() is None


def test_stale_checkout_warns_with_the_age(monkeypatch):
    now = 1_000_000_000
    _at(monkeypatch, now - 49 * 86400, now)
    msg = checkout_age_warning()
    assert msg is not None
    assert "49 days old" in msg
    assert "git pull" in msg


def test_threshold_is_configurable(monkeypatch):
    now = 1_000_000_000
    _at(monkeypatch, now - 2 * 86400, now)
    assert checkout_age_warning() is None  # default 3 days
    assert checkout_age_warning(max_age_days=1) is not None


def test_not_a_git_repo_is_silent(monkeypatch):
    monkeypatch.setattr(waiver_wire.subprocess, "run", lambda *a, **k: _Result(128, ""))
    assert checkout_age_warning() is None


def test_git_failure_never_breaks_the_report(monkeypatch):
    def boom(*a, **k):
        raise subprocess.SubprocessError("git exploded")

    monkeypatch.setattr(waiver_wire.subprocess, "run", boom)
    assert checkout_age_warning() is None


def test_unparseable_output_is_silent(monkeypatch):
    monkeypatch.setattr(
        waiver_wire.subprocess, "run", lambda *a, **k: _Result(0, "not-a-timestamp")
    )
    assert checkout_age_warning() is None
