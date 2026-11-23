"""Verdict registry: rulings in .planning/ must be wired into code.

Thin tests over ``src/verdict_registry.py``.  See docs/VERDICT_REGISTRY.md.
A failing parametrized test names the verdict, ruling, doc, and what was found
vs expected.  Mark a known violation ``xfail(strict=True)`` via ``KNOWN_VIOLATIONS``
so the suite turns red the moment it is fixed-and-forgotten.
"""

import json
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import verdict_registry as vr  # noqa: E402

REG = vr.load_registry()
ASSERTIONS = [(v, a) for v, a in vr.iter_assertions(REG)]

# assertion_id -> reason/finding id.  Empty today: main complies.
KNOWN_VIOLATIONS = {}


# --------------------------------------------------------------------------
# (a) schema
# --------------------------------------------------------------------------


def test_registry_schema():
    assert vr.schema_errors(REG) == []


def test_registry_covers_all_rulings_in_use():
    assert {v["ruling"] for v in REG["verdicts"]} <= set(vr.RULINGS)


# --------------------------------------------------------------------------
# (b) one test per enforcement assertion
# --------------------------------------------------------------------------


def _param(v, a):
    aid = vr.assertion_id(v, a)
    marks = []
    if aid in KNOWN_VIOLATIONS:
        marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_VIOLATIONS[aid]))
    return pytest.param(v, a, id=aid, marks=marks)


@pytest.mark.parametrize("v,a", [_param(v, a) for v, a in ASSERTIONS])
def test_verdict_is_enforced(v, a):
    r = vr.check_assertion(v, a)
    if r.status == "SKIP":
        pytest.skip(r.detail)
    assert r.status == "PASS", r.detail


# --------------------------------------------------------------------------
# (c) completeness: every lever has a ruling or an explicit allowlist reason
# --------------------------------------------------------------------------


def test_every_lever_is_registered_or_allowlisted():
    gaps = vr.completeness_gaps(REG)
    assert not gaps, (
        "Levers with no verdict entry and no unregistered_ok reason in "
        ".planning/verdicts.json (record the ruling, or allowlist with a reason): "
        + ", ".join(f"{k} {a} {b}" for k, a, b in gaps)
    )


def test_completeness_discovers_known_levers():
    """The discovery itself must see real levers (guards against a parser that finds none)."""
    levers = set(vr.discover_levers())
    assert (
        "flag",
        "scripts/generate_projections.py",
        "--rb-tail-calibration",
    ) in levers
    assert ("flag", "scripts/generate_predictions.py", "--use-sentiment") in levers
    assert ("const", "projection_engine", "USE_WR_TPRR_COLLAPSE") in levers
    assert len(levers) >= 25


def test_unregistered_ok_entries_are_not_stale():
    live = set(vr.discover_levers())
    stale = [
        u
        for u in REG["unregistered_ok"]
        if ("flag", u["script"], u["flag"]) not in live
    ]
    assert not stale, f"allowlist entries for levers that no longer exist: {stale}"


# --------------------------------------------------------------------------
# (d) non-vacuity: the checker must be able to fail
# --------------------------------------------------------------------------

V = {"id": "fx", "ruling": "HOLD", "doc": ".planning/X.md", "date": "2026-01-01"}


def _wf(tmp_path, body, name="w.yml"):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(textwrap.dedent(body))


def _hold(flag="--hold-me"):
    return {
        "kind": "workflow_must_not_pass",
        "workflow": "*",
        "script": "scripts/generate_projections.py",
        "flag": flag,
    }


def test_workflow_checker_catches_continuation_line_flag(tmp_path):
    _wf(
        tmp_path,
        """\
        jobs:
          j:
            steps:
              - run: |
                  python scripts/generate_projections.py \\
                    --season 1 \\
                    --hold-me \\
                    --output s3
        """,
    )
    r = vr.check_assertion(V, _hold(), tmp_path)
    assert r.status == "FAIL" and "--hold-me" in r.detail and "'fx'" in r.detail


def test_workflow_checker_catches_variable_indirection(tmp_path):
    _wf(
        tmp_path,
        """\
        jobs:
          j:
            steps:
              - run: |
                  F=""
                  if true; then F="--hold-me"; fi
                  python scripts/generate_projections.py --season 1 $F
        """,
    )
    assert vr.check_assertion(V, _hold(), tmp_path).status == "FAIL"


def test_workflow_checker_exempts_shadow_runs_and_passes_clean(tmp_path):
    _wf(
        tmp_path,
        """\
        jobs:
          j:
            steps:
              - run: python scripts/generate_projections.py --hold-me --shadow-tag t
              - run: python scripts/generate_projections.py --season 1
        """,
    )
    assert vr.check_assertion(V, _hold(), tmp_path).status == "PASS"


def test_workflow_must_pass_fails_when_flag_absent(tmp_path):
    _wf(
        tmp_path,
        """\
        jobs:
          j:
            steps:
              - run: python scripts/generate_projections.py --season 1
        """,
    )
    a = dict(_hold("--ml"), kind="workflow_must_pass", workflow="w.yml")
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"


def test_module_constant_checker_catches_flipped_constant(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "fakemod.py").write_text("USE_THING: bool = True\n")
    a = {
        "kind": "module_constant",
        "module": "fakemod",
        "name": "USE_THING",
        "expected": False,
    }
    r = vr.check_assertion(V, a, tmp_path)
    assert r.status == "FAIL" and "True" in r.detail
    (tmp_path / "src" / "fakemod.py").write_text("USE_THING: bool = False\n")
    assert vr.check_assertion(V, a, tmp_path).status == "PASS"


def test_module_constant_missing_is_a_failure_not_a_pass(tmp_path):
    (tmp_path / "src").mkdir()
    a = {"kind": "module_constant", "module": "nope", "name": "X", "expected": False}
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"


def _board(tmp_path, name, vals):
    d = tmp_path / "data" / "gold" / "predictions" / "season=2026" / "week=11"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ou_pick": vals}).to_parquet(d / name)


_COL = {
    "kind": "data_column_blank",
    "column": "ou_pick",
    "enforced_since": "2026-11-17",
    "glob": "data/gold/predictions/season=2026/week=*/predictions_*.parquet",
}


def test_data_column_checker_catches_nonblank_after_enforcement(tmp_path):
    _board(tmp_path, "predictions_20261120_090000.parquet", ["Over", None])
    r = vr.check_assertion(V, _COL, tmp_path)
    assert r.status == "FAIL" and "ou_pick" in r.detail


def test_data_column_checker_skips_old_files_with_reason_and_passes_blank(tmp_path):
    _board(tmp_path, "predictions_20261117_092007.parquet", ["Over", "Under"])
    r = vr.check_assertion(V, _COL, tmp_path)
    assert r.status == "SKIP" and "after 2026-11-17" in r.detail
    _board(tmp_path, "predictions_20261124_090000.parquet", ["", None])
    assert vr.check_assertion(V, _COL, tmp_path).status == "PASS"


def test_source_checker_catches_banned_phrase(tmp_path):
    (tmp_path / "page.tsx").write_text("We beat the consensus every week")
    a = {
        "kind": "source_must_not_contain",
        "file": "page.tsx",
        "pattern": "(?i)we beat the consensus",
    }
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"
    a2 = dict(a, file="missing.tsx")
    assert vr.check_assertion(V, a2, tmp_path).status == "FAIL"  # no vacuous pass


_INLINE = """\
import argparse
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hold-me", action="store_true")
    p.add_argument("--no-thing", action="store_true", default=True)
    p.add_argument("--n", type=int, default=3)
"""


def test_argparse_checker_inline_shape(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "s.py").write_text(_INLINE)
    ok = {
        "kind": "argparse_default",
        "script": "scripts/s.py",
        "flag": "--hold-me",
        "expected": False,
    }
    assert vr.check_assertion(V, ok, tmp_path).status == "PASS"
    bad = dict(ok, flag="--no-thing")
    assert vr.check_assertion(V, bad, tmp_path).status == "FAIL"
    assert vr.check_assertion(V, dict(ok, flag="--ghost"), tmp_path).status == "FAIL"


def test_argparse_checker_build_parser_in_script(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "s.py").write_text(
        "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--hold-me', action='store_true')\n    return p\n"
        "def main():\n    build_parser().parse_args()\n"
    )
    assert "--hold-me" in vr.argparse_flags("scripts/s.py", tmp_path)


def test_argparse_checker_build_parser_extracted_to_other_module(tmp_path):
    """Refactor shape: the script imports build_parser from a sibling module."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "vr_cli_helper.py").write_text(
        "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--hold-me', action='store_true')\n"
        "    p.add_argument('--no-x', action='store_false')\n    return p\n"
    )
    (tmp_path / "scripts" / "s.py").write_text(
        "from vr_cli_helper import build_parser\ndef main():\n    build_parser().parse_args()\n"
    )
    flags = vr.argparse_flags("scripts/s.py", tmp_path)
    assert flags["--hold-me"] == {"action": "store_true", "default": False}
    assert flags["--no-x"]["default"] is True
    sys.modules.pop("vr_cli_helper", None)


def test_completeness_flags_an_unregistered_lever(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src").mkdir()
    for s in vr.COMPLETENESS_SCRIPTS:
        (tmp_path / s).write_text(_INLINE)
    (tmp_path / "src" / "m.py").write_text(
        "USE_NEW_LEVER = True\nENABLE_X: bool = False\nUSE_N = 3\n"
    )
    reg = {"verdicts": [], "unregistered_ok": []}
    gaps = vr.completeness_gaps(reg, tmp_path)
    assert ("const", "m", "USE_NEW_LEVER") in gaps and (
        "const",
        "m",
        "ENABLE_X",
    ) in gaps
    assert ("const", "m", "USE_N") not in gaps  # non-bool ignored
    assert ("flag", "scripts/generate_projections.py", "--hold-me") in gaps
    # an allowlist entry with a reason clears it
    reg["unregistered_ok"] = [
        {"kind": "module_constant", "module": "m", "name": "ENABLE_X", "reason": "r"}
    ]
    assert ("const", "m", "ENABLE_X") not in vr.completeness_gaps(reg, tmp_path)


def test_schema_rejects_bad_entries(tmp_path):
    bad = {
        "verdicts": [
            {
                "id": "a",
                "subject": "s",
                "ruling": "MAYBE",
                "date": "nope",
                "doc": "missing.md",
                "note": "n",
            }
        ],
        "unregistered_ok": [{"kind": "x", "flag": "--f"}],
    }
    errs = " | ".join(vr.schema_errors(bad, tmp_path))
    assert "MAYBE" in errs and "unparseable date" in errs and "does not exist" in errs
    assert "needs 'enforcement'" in errs and "missing reason" in errs


def test_registry_json_is_valid_json():
    json.loads(vr.REGISTRY_PATH.read_text())
