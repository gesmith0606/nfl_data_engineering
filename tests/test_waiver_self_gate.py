"""The waiver report checks itself before anyone can act on it.

A gate you have to remember to run is a gate that gets skipped — which is
exactly what happened the day an hour of hand-rolled analysis went out while
scripts/waiver_wire.py sat unused. So the check runs at the end of the report
itself and takes the exit code with it.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)


def test_the_report_runs_its_own_sanity_check():
    src = inspect.getsource(waiver_wire.main)
    assert "from src.waiver_sanity import check_report" in src
    assert "SANITY FAIL" in src


def test_a_critical_finding_takes_the_exit_code():
    """Exit 1 is what lets a cron or a pre-claim step stop on bad advice."""
    src = inspect.getsource(waiver_wire.main)
    cut = src.index("if args.no_gate")
    gate = src[cut:]
    assert "return 1" in gate
    # and the clean path still returns 0 after the gate
    assert gate.rstrip().endswith("return 0")


def test_the_gate_can_be_skipped_explicitly():
    src = inspect.getsource(waiver_wire.main)
    assert '"--no-gate"' in src
    assert "if args.no_gate:\n        return 0" in src


def test_printing_is_captured_for_the_gate_to_read():
    """The gate reads the report it just printed, so output must be kept."""
    src = inspect.getsource(waiver_wire.main)
    assert "transcript: List[str] = []" in src
    assert "builtins.print" in src
    assert "transcript.append" in src


def test_bye_teams_are_derived_for_the_gate():
    src = inspect.getsource(waiver_wire.main)
    assert "all_teams" in src
    assert "bye_teams=" in src


def test_budget_and_room_record_bound_the_gate():
    src = inspect.getsource(waiver_wire.main)
    assert "faab_left=" in src
    assert "room_max_bid=" in src
