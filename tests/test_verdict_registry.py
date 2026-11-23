"""Verdict registry: rulings in .planning/ must be wired into code.

Thin tests over ``src/verdict_registry.py``.  See docs/VERDICT_REGISTRY.md.
A failing parametrized test names the verdict, ruling, doc, and what was found
vs expected.  Mark a known violation ``xfail(strict=True)`` via ``KNOWN_VIOLATIONS``
so the suite turns red the moment it is fixed-and-forgotten.

Section (d) is non-vacuity: every evasion the adversarial review found is fed to
the checker as a fixture and must be reported as a violation.
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

# assertion_id -> reason/finding id.  Empty today: the hardened checker found no
# real violation on this tree (see the report that accompanied the hardening).
KNOWN_VIOLATIONS = {}


# --------------------------------------------------------------------------
# (a) schema, shape, exact-case paths
# --------------------------------------------------------------------------


def test_registry_schema():
    assert vr.schema_errors(REG) == []


def test_registry_shape_by_ruling():
    """Falsifiable per-ruling structure (not implied by the schema test)."""
    assert vr.shape_errors(REG) == []


def _registry_paths(reg):
    """Every literal path / glob the registry names."""
    paths = []
    for v in reg["verdicts"]:
        paths.append(v["doc"])
    for _, a in vr.iter_assertions(reg):
        for k in ("script", "glob"):
            if k in a:
                paths.append(a[k])
        if isinstance(a.get("file"), str):
            paths.append(a["file"])
        if "workflow" in a and a["workflow"] != "*":
            paths.append(f".github/workflows/{a['workflow']}")
        for s in a.get("scripts", []):
            paths.append(s)
    for u in list(reg.get("unregistered_ok", [])) + list(reg.get("value_levers", [])):
        if "script" in u:
            paths.append(u["script"])
    return paths


def _module_paths(reg):
    mods = {a["module"] for _, a in vr.iter_assertions(reg) if "module" in a}
    mods |= {
        u["module"]
        for u in list(reg.get("unregistered_ok", []))
        + list(reg.get("value_levers", []))
        if "module" in u
    }
    return mods


def test_every_registry_path_resolves_against_git_with_exact_case():
    """Compared to the TRACKED name set, so a case mismatch fails on macOS too
    (README.md vs the tracked README.MD passed locally and broke Linux CI)."""
    tracked = vr.git_tracked()
    if tracked is None:
        pytest.skip("not a git checkout")
    bad = [p for p in _registry_paths(REG) if not vr.match_tracked(p, tracked)]
    assert not bad, f"registry paths with no tracked file (exact case): {bad}"
    # a LIST of globs (claim bans) may include a type with no file today (.md); the
    # list as a whole must match something, or the checker itself fails "no file matches"
    for v, a in vr.iter_assertions(REG):
        if isinstance(a.get("file"), list):
            assert any(
                vr.match_tracked(p, tracked) for p in a["file"]
            ), vr.assertion_id(v, a)
    tset = set(tracked)
    for m in _module_paths(REG):
        cands = (
            [m.replace(".", "/") + ".py"]
            if "." in m
            else [f"src/{m}.py", f"scripts/{m}.py"]
        )
        assert any(c in tset for c in cands), f"module {m} not tracked as {cands}"


def test_case_mismatch_is_detected_even_on_a_case_insensitive_filesystem(tmp_path):
    assert vr.match_tracked("README.md", ["README.MD"]) == []
    assert vr.match_tracked("README.MD", ["README.MD"]) == ["README.MD"]
    assert vr.match_tracked("web/**/*.tsx", ["web/a/b/c.tsx", "Web/a.tsx"]) == [
        "web/a/b/c.tsx"
    ]
    (tmp_path / "README.MD").write_text("53.0% ATS")
    assert vr.expand(tmp_path, "README.md") == []  # exact case only
    a = {"kind": "source_must_not_contain", "file": "README.md", "pattern": "ATS"}
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"  # "no file matches"
    assert vr.check_assertion(V, dict(a, file="README.MD"), tmp_path).status == "FAIL"
    assert (
        "README.MD" in vr.check_assertion(V, dict(a, file="README.MD"), tmp_path).detail
    )
    # doc references are exact-case too
    reg = {
        "verdicts": [
            dict(V, subject="s", note="n", doc="readme.md", enforcement_gap="g")
        ]
    }
    assert any("does not exist" in e for e in vr.schema_errors(reg, tmp_path))


def test_registry_json_is_valid_json():
    json.loads(vr.REGISTRY_PATH.read_text())


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


def test_no_cross_module_lever_writes():
    assert vr.attribute_write_violations(REG) == []


# --------------------------------------------------------------------------
# (c) completeness
# --------------------------------------------------------------------------


def test_every_lever_is_registered_or_allowlisted():
    gaps = vr.completeness_gaps(REG)
    assert not gaps, (
        "Levers with no verdict entry and no unregistered_ok reason in "
        ".planning/verdicts.json (record the ruling, or allowlist with a reason): "
        + ", ".join(f"{k} {a} {b}" for k, a, b in gaps)
    )


#: Value levers (a number/dict, not a boolean) that MUST be pinned by value.
REQUIRED_VALUE_LEVERS = {
    ("const", "sleeper_consensus_anchor", "SHIPPED_DEFAULT_CONFIGS"),
    ("const", "dispersion_shrink", "SHRINK_FACTOR"),
    ("const", "dispersion_shrink", "SHRINK_FACTOR_BY_POSITION"),
    ("const", "residual_coverage", "MIN_RATIO"),
    ("const", "projection_engine", "VEGAS_BETA"),
    ("const", "consensus_anchor", "DEFAULT_CONSENSUS_WEIGHTS"),
    ("const", "lineup_setter", "OURS_WEIGHT"),
    ("const", "lineup_setter", "SWAP_P"),
    ("const", "lineup_setter", "LEAN_P"),
    ("const", "set_lineups", "WRITE_P"),
    ("flag", "scripts/set_lineups.py", "--swap-p"),
    ("flag", "scripts/set_lineups.py", "--lean-p"),
    ("flag", "scripts/set_lineups.py", "--write-p"),
    ("flag", "scripts/generate_projections.py", "--dispersion-shrink-k"),
    ("flag", "scripts/generate_projections.py", "--consensus-anchor-src"),
    ("flag", "scripts/generate_projections.py", "--consensus-anchor-extra-weight"),
}


def test_required_value_levers_are_listed_and_pinned_by_value():
    listed = {
        (
            ("flag", x["script"], x["flag"])
            if "flag" in x
            else ("const", x["module"], x["name"])
        )
        for x in REG["value_levers"]
    }
    assert REQUIRED_VALUE_LEVERS <= listed, REQUIRED_VALUE_LEVERS - listed
    assert vr.value_lever_gaps(REG) == []


def test_completeness_discovers_known_levers():
    """The discovery itself must see real levers (guards against a parser that finds none)."""
    levers = set(vr.discover_levers())
    assert (
        "flag",
        "scripts/generate_projections.py",
        "--rb-tail-calibration",
    ) in levers
    assert ("flag", "scripts/generate_predictions.py", "--use-sentiment") in levers
    assert ("flag", "scripts/set_lineups.py", "--espn-write") in levers
    assert ("flag", "scripts/sunday_projection_refresh.py", "--dry-run") in levers
    assert ("const", "projection_engine", "USE_WR_TPRR_COLLAPSE") in levers
    assert len(levers) >= 25


def test_unregistered_ok_entries_are_not_stale():
    live = set(vr.discover_levers())
    stale = []
    for u in REG["unregistered_ok"]:
        ref = (
            ("flag", u["script"], u["flag"])
            if "flag" in u
            else ("const", u["module"], u["name"])
        )
        if ref not in live:
            stale.append(u)
    assert not stale, f"allowlist entries for levers that no longer exist: {stale}"


def test_stale_check_handles_constant_allowlist_entries():
    """Regression: a constant-type entry used to KeyError the stale check."""
    reg = {
        "verdicts": [],
        "unregistered_ok": [{"module": "m", "name": "USE_X", "reason": "r"}],
    }
    ref = ("const", "m", "USE_X")
    assert ref in vr.covered_refs(reg)


# --------------------------------------------------------------------------
# (d) non-vacuity: the checker must be able to fail
# --------------------------------------------------------------------------

V = {"id": "fx", "ruling": "HOLD", "doc": ".planning/X.md", "date": "2026-01-01"}
GP = "scripts/generate_projections.py"


def _wf(tmp_path, body, name="w.yml"):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(textwrap.dedent(body))


def _ban(flag="--hold-me", script=GP):
    return {
        "kind": "workflow_must_not_pass",
        "workflow": "*",
        "script": script,
        "flag": flag,
    }


def _run(cmd_block):
    body = textwrap.indent(textwrap.dedent(cmd_block), " " * 10)
    return f"jobs:\n  j:\n    steps:\n      - run: |\n{body}\n"


def _fails(tmp_path, workflow_text, a=None, name="w.yml"):
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "workflows" / name).write_text(workflow_text)
    return vr.check_assertion(V, a or _ban(), tmp_path).status == "FAIL"


# every evasion from the review, as (id, workflow yaml); all must be caught
EVASIONS = {
    "continuation-line": _run(
        "python scripts/generate_projections.py \\\n  --season 1 \\\n  --hold-me \\\n  --output s3\n"
    ),
    "var-indirection": _run(
        'F=""\nif true; then F="--hold-me"; fi\npython scripts/generate_projections.py --season 1 $F\n'
    ),
    "multi-flag-variable": _run(
        'EXTRA="--hold-me --ml"\npython scripts/generate_projections.py $EXTRA\n'
    ),
    "inputs-expression": _run(
        "python scripts/generate_projections.py ${{ inputs.extra_flags }} --hold-me\n"
    ),
    "env-value": "jobs:\n  j:\n    steps:\n      - env:\n          EXTRA: --hold-me\n        run: python scripts/generate_projections.py $EXTRA\n",
    "bash-array": _run(
        'ARGS=(--season 1 --hold-me)\npython scripts/generate_projections.py "${ARGS[@]}"\n'
    ),
    "cd-then-bare-script": _run(
        "cd scripts && python generate_projections.py --hold-me\n"
    ),
    "python-dash-m": _run("python -m scripts.generate_projections --hold-me\n"),
    "comment-with-shadow-tag": _run(
        "python scripts/generate_projections.py --hold-me # --shadow-tag x\n"
    ),
    "echo-shadow-tag-after-semicolon": _run(
        "python scripts/generate_projections.py --hold-me; echo --shadow-tag x\n"
    ),
    "shadow-tag-no-value": _run(
        'python scripts/generate_projections.py --hold-me --shadow-tag ""\n'
    ),
    "quote-split-flag": _run('python scripts/generate_projections.py --hold-"me"\n'),
    "matrix-value": "jobs:\n  j:\n    strategy:\n      matrix:\n        flag: ['--hold-me']\n    steps:\n      - run: python scripts/generate_projections.py ${{ matrix.flag }}\n",
}


@pytest.mark.parametrize("name", sorted(EVASIONS))
def test_workflow_ban_catches_evasion(tmp_path, name):
    assert _fails(tmp_path, EVASIONS[name]), name


def test_workflow_ban_catches_yaml_extension_and_shell_scripts(tmp_path):
    assert _fails(tmp_path, EVASIONS["continuation-line"], name="w.yaml")
    (tmp_path / ".github" / "workflows" / "w.yaml").unlink()
    (tmp_path / "run_weekly.sh").write_text(
        "#!/bin/bash\npython scripts/generate_projections.py --hold-me\n"
    )
    _wf(tmp_path, _run("bash run_weekly.sh\n"))
    assert vr.check_assertion(V, _ban(), tmp_path).status == "FAIL"
    (tmp_path / "run_weekly.sh").write_text(
        "#!/bin/bash\n# python scripts/generate_projections.py --hold-me\n"
    )
    assert vr.check_assertion(V, _ban(), tmp_path).status == "PASS"


def test_workflow_ban_exempts_only_a_real_shadow_command_and_passes_clean(tmp_path):
    _wf(
        tmp_path,
        """\
        jobs:
          j:
            steps:
              - run: |
                  python scripts/generate_projections.py \\
                    --hold-me \\
                    --shadow-tag t \\
                  || echo "shadow failed"
              - run: python scripts/generate_projections.py --season 1  # --hold-me is off
        """,
    )
    assert vr.check_assertion(V, _ban(), tmp_path).status == "PASS"
    # a '#' inside quotes is not a comment
    _wf(tmp_path, _run('python scripts/generate_projections.py --x "#" --hold-me\n'))
    assert vr.check_assertion(V, _ban(), tmp_path).status == "FAIL"
    # --flag-suffix is a different flag
    _wf(tmp_path, _run("python scripts/generate_projections.py --hold-me-not\n"))
    assert vr.check_assertion(V, _ban(), tmp_path).status == "PASS"


def test_shell_comment_stripper():
    s = vr.strip_shell_comments
    assert s("a # b\nc").split("\n") == ["a ", "c"]
    assert s('echo "a # b"') == 'echo "a # b"'
    assert s("echo 'x # y' # z") == "echo 'x # y' "
    assert s("echo ${#v} $#") == "echo ${#v} $#"
    assert s("# only\n--hold-me").strip() == "--hold-me"


def test_workflow_must_pass_needs_a_real_invocation(tmp_path):
    a = dict(_ban("--ml"), kind="workflow_must_pass", workflow="w.yml")
    _wf(tmp_path, _run("python scripts/generate_projections.py --season 1\n"))
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"  # flag absent
    _wf(tmp_path, _run('echo "python scripts/generate_projections.py --ml"\n'))
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"  # echo line
    _wf(tmp_path, _run("# python scripts/generate_projections.py --ml\ntrue\n"))
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"  # comment
    _wf(tmp_path, _run("python scripts/generate_projections.py --ml --shadow-tag t\n"))
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"  # shadow never publishes
    _wf(
        tmp_path,
        _run("python scripts/generate_projections.py \\\n  --season 1 \\\n  --ml\n"),
    )
    assert vr.check_assertion(V, a, tmp_path).status == "PASS"


PASSTHROUGH = {
    "kind": "workflow_no_flag_passthrough",
    "workflow": "*",
    "scripts": [GP],
    "allow_vars": [{"name": "SEASON", "reason": "r"}],
    "allow_expressions": [
        {"workflow": "w.yml", "expression": "inputs.season || '1'", "reason": "r"}
    ],
}


def test_passthrough_flags_unreviewed_expansions_and_honours_allowlist(tmp_path):
    for body in (
        "python scripts/generate_projections.py ${{ inputs.extra_flags }}\n",
        "python scripts/generate_projections.py ${{ github.event.inputs.x }}\n",
        "python scripts/generate_projections.py ${{ vars.EXTRA }}\n",
        "python scripts/generate_projections.py $EXTRA\n",
        'python scripts/generate_projections.py "${EXTRA}"\n',
        "python scripts/generate_projections.py ${{ inputs.week || '3' }}\n",
    ):
        _wf(tmp_path, _run(body))
        assert vr.check_assertion(V, PASSTHROUGH, tmp_path).status == "FAIL", body
    _wf(
        tmp_path,
        _run(
            "python scripts/generate_projections.py --season \"$SEASON\" ${{ inputs.season || '1' }}\n"
        ),
    )
    assert vr.check_assertion(V, PASSTHROUGH, tmp_path).status == "PASS"
    # same expression in another workflow file is NOT covered by the allowlist
    _wf(
        tmp_path,
        _run("python scripts/generate_projections.py ${{ inputs.season || '1' }}\n"),
        name="other.yml",
    )
    assert vr.check_assertion(V, PASSTHROUGH, tmp_path).status == "FAIL"


def test_workflow_ban_on_value_carrying_override_flags(tmp_path):
    for flag in (
        "--consensus-anchor-src",
        "--dispersion-shrink-k",
        "--consensus-anchor-extra-weight",
    ):
        _wf(tmp_path, _run(f"python scripts/generate_projections.py {flag} 1.0\n"))
        assert vr.check_assertion(V, _ban(flag), tmp_path).status == "FAIL", flag
        _wf(tmp_path, _run(f"python scripts/generate_projections.py {flag}=1.0\n"))
        assert vr.check_assertion(V, _ban(flag), tmp_path).status == "FAIL", flag


def test_registry_bans_every_value_override_flag_of_generate_projections():
    """Each value-taking flag of the publisher that changes a shipped default is banned."""
    banned = {a["flag"] for _, a in ASSERTIONS if a["kind"] == "workflow_must_not_pass"}
    for flag in (
        "--consensus-anchor-src",
        "--consensus-anchor-position",
        "--consensus-anchor-mode",
        "--consensus-anchor-weight",
        "--consensus-anchor-extra-position",
        "--consensus-anchor-extra-mode",
        "--consensus-anchor-extra-weight",
        "--dispersion-shrink-k",
        "--early-season-prior-weight",
        "--adp-prior-weight",
        "--qb-starter-floor-haircut",
        "--rb-tail-low-weight",
        "--rb-tail-high-shrink",
        "--ecr-anchor-mode",
        "--ecr-anchor-weight",
        "--wind-adjust-shrink",
    ):
        assert flag in banned, flag
    # every value-taking flag of the script is either banned or known-benign
    benign = {
        "--season",
        "--week",
        "--scoring",
        "--output",
        "--output-dir",
        "--depth-chart-as-of",
        "--shadow-tag",
    }
    for flag, meta in vr.argparse_flags(GP).items():
        if meta["action"] not in vr._BOOL_ACTIONS and flag not in benign:
            assert (
                flag in banned
            ), f"value flag {flag} is neither banned nor listed benign"


# --- module constants: values, extra assignment sites -----------------------


def _mod(tmp_path, body, name="fakemod"):
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / f"{name}.py").write_text(textwrap.dedent(body))


def _const(name, expected, module="fakemod"):
    return {
        "kind": "module_constant",
        "module": module,
        "name": name,
        "expected": expected,
    }


def test_module_constant_checker_catches_flipped_constant(tmp_path):
    _mod(tmp_path, "USE_THING: bool = True\n")
    r = vr.check_assertion(V, _const("USE_THING", False), tmp_path)
    assert r.status == "FAIL" and "True" in r.detail
    _mod(tmp_path, "USE_THING: bool = False\n")
    assert vr.check_assertion(V, _const("USE_THING", False), tmp_path).status == "PASS"


def test_module_constant_missing_is_a_failure_not_a_pass(tmp_path):
    (tmp_path / "src").mkdir()
    assert vr.check_assertion(V, _const("X", False, "nope"), tmp_path).status == "FAIL"


def test_value_pins_catch_neutralised_values(tmp_path):
    _mod(
        tmp_path,
        """\
        BASE = 0.8
        SHRINK = 1.0
        BY_POS = {"QB": BASE, "WR": 1.0}
        BETA = {"QB": 0.25, "RB": 0.0}
        CFG = ({"position": "WR", "weight": 0.5},)
        MIN_RATIO = 0.0
        FLAG_AS_INT = 1
        """,
    )
    chk = lambda n, e: vr.check_assertion(
        V, _const(n, e), tmp_path
    ).status  # noqa: E731
    assert chk("SHRINK", 0.8) == "FAIL" and chk("SHRINK", 1.0) == "PASS"
    assert chk("MIN_RATIO", 0.70) == "FAIL"
    assert chk("BY_POS", {"QB": 0.8, "WR": 1.0}) == "PASS"  # names resolved statically
    assert chk("BY_POS", {"QB": 0.8, "WR": 0.9}) == "FAIL"
    assert chk("BETA", {"QB": 0.25, "RB": 0.1}) == "FAIL"
    assert chk("BETA", {"QB": 0.25, "RB": 0.0, "WR": 0.0}) == "FAIL"  # extra key
    assert chk("CFG", [{"position": "WR", "weight": 0.5}]) == "PASS"
    assert chk("CFG", [{"position": "WR", "weight": 0.51}]) == "FAIL"
    assert (
        chk(
            "CFG",
            [{"position": "WR", "weight": 0.5}, {"position": "QB", "weight": 0.5}],
        )
        == "FAIL"
    )
    assert chk("SHRINK", 1.0 + 1e-12) == "PASS"  # float tolerance
    assert chk("FLAG_AS_INT", True) == "FAIL"  # 1 is not True


def test_module_constant_fails_on_any_extra_assignment_site(tmp_path):
    cases = {
        "appended": "USE_X = False\nUSE_X = True\n",
        "inside-if": "USE_X = False\nif True:\n    USE_X = True\n",
        "inside-try": "USE_X = False\ntry:\n    USE_X = True\nexcept Exception:\n    pass\n",
        "augmented": "USE_X = False\nUSE_X |= True\n",
        "globals-const-key": "USE_X = False\nglobals()['USE_X'] = True\n",
        "globals-dynamic-key": "USE_X = False\nk = 'USE_X'\nglobals()[k] = True\n",
        "globals-update": "USE_X = False\nglobals().update(USE_X=True)\n",
        "global-in-function": "USE_X = False\ndef f():\n    global USE_X\n    USE_X = True\n",
        "import-rebind": "USE_X = False\nfrom other import USE_X\n",
        "tuple-rebind": "USE_X = False\nUSE_X, y = True, 1\n",
    }
    for label, body in cases.items():
        _mod(tmp_path, body)
        r = vr.check_assertion(V, _const("USE_X", False), tmp_path)
        assert r.status == "FAIL", label
        assert "fakemod.py:" in r.detail, label  # reports the sites
    _mod(tmp_path, "USE_X = False\n")
    assert vr.check_assertion(V, _const("USE_X", False), tmp_path).status == "PASS"
    _mod(tmp_path, "SWAP_P, LEAN_P = 0.52, 0.52\n")
    assert vr.check_assertion(V, _const("LEAN_P", 0.52), tmp_path).status == "PASS"


def test_constant_contains_is_by_value(tmp_path):
    _mod(tmp_path, "CFG = ({'position': 'WR', 'weight': 0.5},)\n")
    a = {
        "kind": "module_constant_contains",
        "module": "fakemod",
        "name": "CFG",
        "item": {"position": "WR", "weight": 0.9},
    }
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"
    assert (
        vr.check_assertion(
            V, dict(a, item={"position": "WR", "weight": 0.5}), tmp_path
        ).status
        == "PASS"
    )


def test_cross_module_lever_write_is_caught(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts" / "experiments").mkdir(parents=True)
    (tmp_path / "src" / "a.py").write_text("import b\nb.USE_THING = True\n")
    assert vr.attribute_write_violations({}, tmp_path)
    (tmp_path / "src" / "a.py").write_text("import b\nsetattr(b, 'ENABLE_Y', 1)\n")
    assert vr.attribute_write_violations({}, tmp_path)
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "scripts" / "experiments" / "e.py").write_text(
        "import b\nb.USE_THING = True\n"
    )
    assert vr.attribute_write_violations({}, tmp_path) == []  # experiments excluded
    (tmp_path / "scripts" / "s.py").write_text("import b\nb.USE_THING = True\n")
    hits = vr.attribute_write_violations({}, tmp_path)
    assert hits
    allow = {
        "attribute_write_allowlist": [
            {"file": "scripts/s.py", "target": "b.USE_THING", "reason": "r"}
        ]
    }
    assert vr.attribute_write_violations(allow, tmp_path) == []


# --- data files --------------------------------------------------------------


def _board(tmp_path, name, vals):
    d = tmp_path / "data" / "gold" / "predictions" / "season=2026" / "week=11"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ou_pick": vals}).to_parquet(d / name)


_COL = {
    "kind": "data_column_blank",
    "column": "ou_pick",
    "enforced_since": "2026-11-18T02:15:35Z",
    "glob": "data/gold/predictions/season=2026/week=*/predictions_*.parquet",
}


def test_data_column_checker_catches_nonblank_after_enforcement(tmp_path):
    _board(tmp_path, "predictions_20261120_090000.parquet", ["Over", None])
    r = vr.check_assertion(V, _COL, tmp_path)
    assert r.status == "FAIL" and "ou_pick" in r.detail


def test_data_column_checker_checks_same_day_files_after_the_timestamp(tmp_path):
    """A date-only '>' compare skipped same-day files; the full timestamp uses >=."""
    _board(
        tmp_path, "predictions_20261118_090000.parquet", ["Over", "Under"]
    )  # same day, after 02:15:35Z
    assert vr.check_assertion(V, _COL, tmp_path).status == "FAIL"
    day = dict(_COL, enforced_since="2026-11-18")  # date-only means midnight UTC
    assert vr.check_assertion(V, day, tmp_path).status == "FAIL"
    exact = dict(_COL, enforced_since="2026-11-18T09:00:00Z")
    assert (
        vr.check_assertion(V, exact, tmp_path).status == "FAIL"
    )  # >=, boundary file is checked
    off = dict(
        _COL, enforced_since="2026-11-18T04:00:01-05:00"
    )  # = 09:00:01Z, offset converted
    assert vr.check_assertion(V, off, tmp_path).status == "SKIP"


def test_data_column_checker_skips_before_enforcement_and_passes_blank(tmp_path):
    _board(tmp_path, "predictions_20261117_092007.parquet", ["Over", "Under"])
    r = vr.check_assertion(V, _COL, tmp_path)
    assert r.status == "SKIP" and "2026-11-18T02:15:35Z" in r.detail
    _board(tmp_path, "predictions_20261124_090000.parquet", ["", None])
    assert vr.check_assertion(V, _COL, tmp_path).status == "PASS"


def test_registry_totals_entry_is_enforced_from_the_merge_instant():
    v = next(x for x in REG["verdicts"] if x["id"] == "totals-ou-pick")
    col = next(a for a in v["enforcement"] if a["kind"] == "data_column_blank")
    assert vr._ts_key(col["enforced_since"]) == "20261118_021535"  # PR #161 merge, UTC
    assert "20261117_092007" < vr._ts_key(col["enforced_since"])  # pre-merge cron board


# --- source scans -------------------------------------------------------------


def test_source_checker_catches_banned_phrase(tmp_path):
    (tmp_path / "page.tsx").write_text("We beat the consensus every week")
    a = {
        "kind": "source_must_not_contain",
        "file": "page.tsx",
        "pattern": "(?i)we beat the consensus",
    }
    assert vr.check_assertion(V, a, tmp_path).status == "FAIL"
    assert (
        vr.check_assertion(V, dict(a, file="missing.tsx"), tmp_path).status == "FAIL"
    )  # no vacuous pass


def _claim(vid):
    v = next(x for x in REG["verdicts"] if x["id"] == vid)
    return v, v["enforcement"][0]


@pytest.mark.parametrize(
    "vid,rel,text,fails",
    [
        ("claim-ats-53", "web/frontend/src/lib/a.ts", "Our model hits 53.0% ATS", True),
        ("claim-ats-53", "web/frontend/src/a.md", "53% ATS this season", True),
        ("claim-ats-53", "README.MD", "53.0% against the spread", True),
        ("claim-ats-53", "README.MD", "53.0% ATS on the sealed 2024 holdout", False),
        (
            "claim-clv",
            "web/frontend/src/lib/a.json",
            '{"t": "positive closing-line value"}',
            True,
        ),
        ("claim-clv", "README.MD", "we track CLV every week", True),
        ("claim-clv", "README.MD", "no CLV evidence (retracted)", False),
        (
            "claim-beat-consensus",
            "web/frontend/src/lib/a.ts",
            "export const t = 'GIQ beats Sleeper'",
            True,
        ),
        (
            "claim-beat-consensus",
            "web/frontend/src/a.md",
            "Our projections outperform the consensus",
            True,
        ),
        ("claim-beat-consensus", "README.MD", "we beat the consensus", True),
        (
            "claim-beat-consensus",
            "README.MD",
            "we beat Sleeper in the 2022-24 backtest",
            False,
        ),
    ],
)
def test_claim_bans_catch_rewordings_in_all_scoped_files(
    tmp_path, vid, rel, text, fails
):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text + "\n")
    v, a = _claim(vid)
    assert (vr.check_assertion(v, a, tmp_path).status == "FAIL") is fails


# --- argparse -------------------------------------------------------------------

_INLINE = """\
import argparse
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hold-me", action="store_true")
    p.add_argument("--no-thing", action="store_true", default=True)
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--opt", action=argparse.BooleanOptionalAction, default=False)
"""


def _script(tmp_path, body, name="s.py"):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / name).write_text(textwrap.dedent(body))


def _ad(flag, expected, script="scripts/s.py"):
    return {
        "kind": "argparse_default",
        "script": script,
        "flag": flag,
        "expected": expected,
    }


def test_argparse_checker_inline_shape(tmp_path):
    _script(tmp_path, _INLINE)
    assert vr.check_assertion(V, _ad("--hold-me", False), tmp_path).status == "PASS"
    assert vr.check_assertion(V, _ad("--no-thing", False), tmp_path).status == "FAIL"
    assert vr.check_assertion(V, _ad("--ghost", False), tmp_path).status == "FAIL"
    assert vr.check_assertion(V, _ad("--n", 3), tmp_path).status == "PASS"
    assert vr.check_assertion(V, _ad("--n", 4), tmp_path).status == "FAIL"


def test_argparse_default_resolves_names_and_catches_a_changed_value(tmp_path):
    _script(
        tmp_path,
        "import argparse\nSWAP_P = 0.52\ndef main():\n    p = argparse.ArgumentParser()\n    p.add_argument('--swap-p', type=float, default=SWAP_P)\n",
    )
    assert vr.check_assertion(V, _ad("--swap-p", 0.52), tmp_path).status == "PASS"
    assert vr.check_assertion(V, _ad("--swap-p", 0.6), tmp_path).status == "FAIL"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "consts.py").write_text("SWAP_P = 0.9\n")
    _script(
        tmp_path,
        "import argparse\nfrom src.consts import (\n    SWAP_P,\n)\ndef main():\n    p = argparse.ArgumentParser()\n    p.add_argument('--swap-p', default=SWAP_P)\n",
    )
    assert vr.check_assertion(V, _ad("--swap-p", 0.52), tmp_path).status == "FAIL"
    assert vr.check_assertion(V, _ad("--swap-p", 0.9), tmp_path).status == "PASS"


def test_argparse_default_fails_when_overwritten_after_parsing(tmp_path):
    for label, extra in {
        "set_defaults": "    p.set_defaults(hold_me=True)\n",
        "set_defaults-splat": "    p.set_defaults(**{'hold_me': True})\n",
        "args-assign": "    args = p.parse_args()\n    args.hold_me = True\n",
        "setattr": "    setattr(args, 'hold_me', True)\n",
        "vars": "    vars(args)['hold_me'] = True\n",
    }.items():
        _script(tmp_path, _INLINE + extra)
        r = vr.check_assertion(V, _ad("--hold-me", False), tmp_path)
        assert r.status == "FAIL" and "overwritten" in r.detail, label
    _script(tmp_path, _INLINE + "    args = p.parse_args()\n    args.other = True\n")
    assert vr.check_assertion(V, _ad("--hold-me", False), tmp_path).status == "PASS"


def test_argparse_checker_build_parser_in_script(tmp_path):
    _script(
        tmp_path,
        "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--hold-me', action='store_true')\n    return p\n"
        "def main():\n    build_parser().parse_args()\n",
    )
    assert "--hold-me" in vr.argparse_flags("scripts/s.py", tmp_path)


def test_argparse_checker_build_parser_extracted_to_other_module(tmp_path):
    """Refactor shape: the script imports build_parser from a sibling module."""
    _script(
        tmp_path,
        "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--hold-me', action='store_true')\n"
        "    p.add_argument('--no-x', action='store_false')\n    return p\n",
        name="vr_cli_helper.py",
    )
    _script(
        tmp_path,
        "from vr_cli_helper import build_parser\ndef main():\n    build_parser().parse_args()\n",
    )
    flags = vr.argparse_flags("scripts/s.py", tmp_path)
    assert flags["--hold-me"] == {"action": "store_true", "default": False}
    assert flags["--no-x"]["default"] is True
    sys.modules.pop("vr_cli_helper", None)


# --- completeness -------------------------------------------------------------


def test_completeness_flags_an_unregistered_lever(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "web" / "api").mkdir(parents=True)
    for s in vr.COMPLETENESS_SCRIPTS:
        _script(tmp_path, _INLINE, name=Path(s).name)
    (tmp_path / "src" / "m.py").write_text(
        "USE_NEW_LEVER = True\nENABLE_X: bool = False\nUSE_N = 3\n"
        "ALLOW_Y = True\nAPPLY_Z = 1\nDISABLE_W = 0\nSKIP_V = False\nOTHER_FLAG = True\n"
    )
    (tmp_path / "scripts" / "k.py").write_text("USE_IN_SCRIPTS = True\n")
    (tmp_path / "web" / "api" / "w.py").write_text("ENABLE_IN_API = False\n")
    reg = {"verdicts": [], "unregistered_ok": []}
    gaps = vr.completeness_gaps(reg, tmp_path)
    for name in (
        "USE_NEW_LEVER",
        "ENABLE_X",
        "ALLOW_Y",
        "APPLY_Z",
        "DISABLE_W",
        "SKIP_V",
    ):
        assert ("const", "m", name) in gaps, name
    assert ("const", "k", "USE_IN_SCRIPTS") in gaps
    assert ("const", "web.api.w", "ENABLE_IN_API") in gaps
    assert ("const", "m", "USE_N") not in gaps and (
        "const",
        "m",
        "OTHER_FLAG",
    ) not in gaps
    assert ("flag", "scripts/generate_projections.py", "--hold-me") in gaps
    # BooleanOptionalAction as an attribute (not a string literal) is a lever
    assert ("flag", "scripts/set_lineups.py", "--opt") in gaps
    assert ("flag", "scripts/sunday_projection_refresh.py", "--hold-me") in gaps
    assert ("flag", "scripts/generate_projections.py", "--n") not in gaps
    reg["unregistered_ok"] = [
        {"kind": "module_constant", "module": "m", "name": "ENABLE_X", "reason": "r"}
    ]
    assert ("const", "m", "ENABLE_X") not in vr.completeness_gaps(reg, tmp_path)


def test_value_lever_without_a_value_pin_is_a_gap():
    pinned = {
        "verdicts": [
            {"id": "a", "enforcement": [_const("MIN_RATIO", 0.7, "residual_coverage")]}
        ],
        "value_levers": [
            {"module": "residual_coverage", "name": "MIN_RATIO"},
            {"module": "residual_coverage", "name": "OTHER"},
        ],
        "unregistered_ok": [
            {"module": "residual_coverage", "name": "OTHER", "reason": "r"}
        ],
    }
    # an allowlist entry does NOT satisfy a value lever
    assert vr.value_lever_gaps(pinned) == [("const", "residual_coverage", "OTHER")]


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
                "enforcement": [{"kind": "module_constant", "module": "m"}],
            }
        ],
        "unregistered_ok": [{"kind": "x", "flag": "--f"}],
    }
    errs = " | ".join(vr.schema_errors(bad, tmp_path))
    assert "MAYBE" in errs and "unparseable date" in errs and "does not exist" in errs
    assert "missing 'name'" in errs and "missing 'expected'" in errs
    assert "missing reason" in errs
    cols = {
        "verdicts": [
            dict(
                V,
                subject="s",
                note="n",
                doc="d.md",
                enforcement=[
                    {
                        "kind": "data_column_blank",
                        "glob": "g",
                        "column": "c",
                        "enforced_since": "yesterday",
                    }
                ],
            )
        ]
    }
    (tmp_path / "d.md").write_text("x")
    assert "enforced_since" in " ".join(vr.schema_errors(cols, tmp_path))


def test_shape_errors_catch_a_cron_flag_with_no_workflow_assertion():
    base = dict(V, subject="s", note="n", doc="d")
    unpaired = {
        "verdicts": [
            dict(base, ruling="HOLD", enforcement=[_ad("--hold-me", False, GP)])
        ]
    }
    assert any("no workflow_must" in e for e in vr.shape_errors(unpaired))
    paired = {
        "verdicts": [
            dict(base, ruling="HOLD", enforcement=[_ad("--hold-me", False, GP), _ban()])
        ]
    }
    assert vr.shape_errors(paired) == []
    must = {
        "verdicts": [
            dict(
                base,
                ruling="HOLD",
                enforcement=[dict(_ban(), kind="workflow_must_pass")],
            )
        ]
    }
    assert any("must not require" in e for e in vr.shape_errors(must))
    empty = {"verdicts": [dict(base, ruling="KILL")]}
    assert vr.shape_errors(empty)
