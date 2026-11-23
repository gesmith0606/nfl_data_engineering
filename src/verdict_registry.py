"""Executable verdict registry: tie .planning rulings (SHIP/HOLD/KILL) to code.

``.planning/verdicts.json`` records one entry per model decision plus
machine-checkable assertions about the repo (CLI defaults, module constants,
what the production cron passes, whether a killed output column is blank,
public-copy retractions).  ``check_assertion`` evaluates one assertion and
returns a ``Result``; ``completeness_gaps`` finds levers (argparse booleans,
``USE_*``/``ENABLE_*`` constants) that no entry covers.

Everything is read statically (``ast``, YAML, regex) -- no pipeline is run.
See docs/VERDICT_REGISTRY.md.
"""

from __future__ import annotations

import ast
import glob as _glob
import importlib.util
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / ".planning" / "verdicts.json"
RULINGS = ("SHIP", "SHIP_OPT_IN", "HOLD", "KILL", "DEAD")
KINDS = (
    "argparse_default",
    "module_constant",
    "module_constant_contains",
    "workflow_must_not_pass",
    "workflow_must_pass",
    "data_column_blank",
    "source_must_not_contain",
    "source_must_contain",
)
COMPLETENESS_SCRIPTS = (
    "scripts/generate_projections.py",
    "scripts/generate_predictions.py",
)
_BOOL_ACTIONS = ("store_true", "store_false", "BooleanOptionalAction")
_PARSER_BUILDERS = ("build_parser", "_build_parser", "get_parser", "make_parser")


@dataclass
class Result:
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


def load_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    return json.loads((path or REGISTRY_PATH).read_text())


def iter_assertions(
    reg: Dict[str, Any],
) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
    for v in reg["verdicts"]:
        for a in v.get("enforcement", []):
            yield v, a


def assertion_id(v: Dict[str, Any], a: Dict[str, Any]) -> str:
    tail = (
        a.get("flag")
        or a.get("name")
        or a.get("column")
        or a.get("pattern", "")[:24]
        or ""
    )
    return f"{v['id']}::{a['kind']}::{a.get('script') or a.get('module') or a.get('workflow') or a.get('file') or ''}::{tail}"


def _label(v: Dict[str, Any]) -> str:
    doc = Path(v["doc"]).name
    return f"{v['ruling']} '{v['id']}' ({doc}, {v['date']})"


# --------------------------------------------------------------------------
# argparse (static): both inline-in-main() and build_parser() shapes
# --------------------------------------------------------------------------


def _lit(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return "<non-literal>"


def _flags_from_ast(tree: ast.AST) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for n in ast.walk(tree):
        if not (
            isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_argument"
        ):
            continue
        names = [
            a.value
            for a in n.args
            if isinstance(a, ast.Constant)
            and isinstance(a.value, str)
            and a.value.startswith("--")
        ]
        if not names:
            continue
        kw = {k.arg: _lit(k.value) for k in n.keywords if k.arg}
        action = kw.get("action")
        if "default" in kw:
            default = kw["default"]
        elif action == "store_true":
            default = False
        elif action == "store_false":
            default = True
        else:
            default = None
        out[names[0]] = {"action": action, "default": default}
    return out


def _flags_from_import(script: Path) -> Dict[str, Dict[str, Any]]:
    """Fallback for a parser extracted into a ``build_parser()`` elsewhere."""
    spec = importlib.util.spec_from_file_location(f"_vr_{script.stem}", script)
    if spec is None or spec.loader is None:
        return {}
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script.parent))
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
        sys.path.pop(0)
    for name in _PARSER_BUILDERS:
        fn = getattr(mod, name, None)
        if callable(fn):
            parser = fn()
            out = {}
            for act in parser._actions:
                flags = [s for s in act.option_strings if s.startswith("--")]
                if flags and act.dest != "help":
                    kind = type(act).__name__
                    action = {
                        "_StoreTrueAction": "store_true",
                        "_StoreFalseAction": "store_false",
                        "BooleanOptionalAction": "BooleanOptionalAction",
                    }.get(kind, "store")
                    out[flags[0]] = {"action": action, "default": act.default}
            return out
    return {}


def argparse_flags(script: str, root: Path = ROOT) -> Dict[str, Dict[str, Any]]:
    p = root / script
    flags = _flags_from_ast(ast.parse(p.read_text()))
    if not flags:
        flags = _flags_from_import(p)
    return flags


# --------------------------------------------------------------------------
# module constants (static)
# --------------------------------------------------------------------------


def _module_file(module: str, root: Path) -> Optional[Path]:
    if (
        "." in module
    ):  # dotted path from the repo root, e.g. web.api.routers.predictions
        p = root / (module.replace(".", "/") + ".py")
        return p if p.exists() else None
    for d in ("src", "scripts"):
        p = root / d / f"{module}.py"
        if p.exists():
            return p
    return None


def _norm(x: Any) -> Any:
    if isinstance(x, (tuple, list)):
        return [_norm(i) for i in x]
    if isinstance(x, set):
        return sorted(_norm(i) for i in x)
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    return x


def module_constant(module: str, name: str, root: Path = ROOT) -> Tuple[bool, Any]:
    f = _module_file(module, root)
    if f is None:
        return False, f"module '{module}' not found under src/, scripts/ or web/api/"
    for n in ast.parse(f.read_text()).body:
        if isinstance(n, ast.Assign):
            targets = [t.id for t in n.targets if isinstance(t, ast.Name)]
            val = n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            targets, val = [n.target.id], n.value
        else:
            continue
        if name in targets and val is not None:
            try:
                return True, _norm(ast.literal_eval(val))
            except Exception:
                return False, f"{module}.{name} is not a literal"
    return False, f"{module}.{name} not defined"


def bool_constants(root: Path = ROOT) -> List[Tuple[str, str]]:
    """Every module-level ``USE_*`` / ``ENABLE_*`` boolean in src/."""
    found = []
    for f in sorted((root / "src").rglob("*.py")):
        for n in ast.parse(f.read_text()).body:
            if isinstance(n, ast.Assign):
                names = [t.id for t in n.targets if isinstance(t, ast.Name)]
                val = n.value
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                names, val = [n.target.id], n.value
            else:
                continue
            for nm in names:
                if (
                    re.match(r"(USE|ENABLE)_", nm)
                    and isinstance(val, ast.Constant)
                    and isinstance(val.value, bool)
                ):
                    found.append((f.stem, nm))
    return found


# --------------------------------------------------------------------------
# workflows
# --------------------------------------------------------------------------


def _run_blocks(text: str) -> List[str]:
    doc = yaml.safe_load(text) or {}
    blocks = []
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                blocks.append(step["run"])
    return blocks


def workflow_commands(text: str, script: str) -> List[List[str]]:
    """Flag lists of every command line invoking ``scripts/<script>.py``.

    Handles ``\\`` continuations and ``VAR="--flag"`` indirection
    (``$VAR`` / ``${VAR}`` in a command expands to the assigned flag).
    """
    cmds = []
    for block in _run_blocks(text):
        assigns: Dict[str, List[str]] = {}
        for m in re.finditer(r"\b([A-Za-z_]\w*)=\"(--[\w-]+)\"", block):
            assigns.setdefault(m.group(1), []).append(m.group(2))
        joined = re.sub(r"\\\s*\n\s*", " ", block)
        for line in joined.splitlines():
            if line.lstrip().startswith("#") or f"scripts/{script}.py" not in line:
                continue
            try:
                toks = shlex.split(line)
            except ValueError:
                toks = line.split()
            flags = []
            for t in toks:
                if t.startswith("--"):
                    flags.append(t.split("=", 1)[0])
                m = re.fullmatch(r"\$\{?(\w+)\}?", t)
                if m:
                    flags.extend(assigns.get(m.group(1), []))
            cmds.append(flags)
    return cmds


def _workflow_files(workflow: str, root: Path) -> List[Path]:
    d = root / ".github" / "workflows"
    if workflow == "*":
        return sorted(d.glob("*.yml"))
    return [d / workflow]


def _workflow_hits(a: Dict[str, Any], root: Path) -> Tuple[List[str], List[str]]:
    """(files where a non-shadow command passes the flag, files read)."""
    ignore = a.get("ignore_if_has_flag", "--shadow-tag")
    script, flag = Path(a["script"]).stem, a["flag"]
    hits, read = [], []
    for f in _workflow_files(a["workflow"], root):
        if not f.exists():
            raise FileNotFoundError(f"workflow {f.name} not found")
        read.append(f.name)
        for flags in workflow_commands(f.read_text(), script):
            if ignore and ignore in flags:
                continue
            if flag in flags:
                hits.append(f.name)
                break
    return hits, read


# --------------------------------------------------------------------------
# data files
# --------------------------------------------------------------------------


def _filename_date(name: str) -> Optional[str]:
    m = re.search(r"(\d{4})(\d{2})(\d{2})_\d{6}", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _is_blank(series: Any) -> bool:
    return bool(
        series.map(
            lambda x: x is None or x != x or (isinstance(x, str) and not x.strip())
        ).all()
    )


# --------------------------------------------------------------------------
# the checker
# --------------------------------------------------------------------------


def check_assertion(v: Dict[str, Any], a: Dict[str, Any], root: Path = ROOT) -> Result:
    kind = a["kind"]
    lab = _label(v)
    try:
        if kind == "argparse_default":
            flags = argparse_flags(a["script"], root)
            if a["flag"] not in flags:
                return Result("FAIL", f"{lab}: {a['flag']} not found in {a['script']}")
            got = flags[a["flag"]]["default"]
            if got != a["expected"]:
                return Result(
                    "FAIL",
                    f"{lab}: {a['script']} {a['flag']} default is {got!r}, expected {a['expected']!r}",
                )
            return Result("PASS", f"default={got!r}")

        if kind == "module_constant":
            ok, got = module_constant(a["module"], a["name"], root)
            if not ok:
                return Result("FAIL", f"{lab}: {got}")
            if got != _norm(a["expected"]):
                return Result(
                    "FAIL",
                    f"{lab}: {a['module']}.{a['name']} is {got!r}, expected {a['expected']!r}",
                )
            return Result("PASS", f"{a['name']}={got!r}")

        if kind == "module_constant_contains":
            ok, got = module_constant(a["module"], a["name"], root)
            if not ok:
                return Result("FAIL", f"{lab}: {got}")
            if _norm(a["item"]) not in got:
                return Result(
                    "FAIL",
                    f"{lab}: {a['module']}.{a['name']} lacks {a['item']!r} (has {got!r})",
                )
            return Result("PASS", f"{a['name']} contains {a['item']!r}")

        if kind in ("workflow_must_not_pass", "workflow_must_pass"):
            hits, read = _workflow_hits(a, root)
            if kind == "workflow_must_not_pass":
                if hits:
                    return Result(
                        "FAIL",
                        f"{lab}: {a['flag']} is passed to {a['script']} by {', '.join(sorted(set(hits)))}",
                    )
                return Result("PASS", f"not passed in {len(read)} workflow(s)")
            if not hits:
                return Result(
                    "FAIL",
                    f"{lab}: {a['flag']} is NOT passed to {a['script']} by {a['workflow']}",
                )
            return Result("PASS", f"passed in {hits[0]}")

        if kind == "data_column_blank":
            import pandas as pd

            since = a["enforced_since"]
            files = sorted(
                f
                for f in _glob.glob(str(root / a["glob"]))
                if (_filename_date(Path(f).name) or "") > since
            )
            if not files:
                return Result(
                    "SKIP",
                    f"no file matching {a['glob']} has a filename timestamp after {since} "
                    "(enforcement not yet observable in tracked data)",
                )
            for f in files:
                df = pd.read_parquet(f)
                if a["column"] not in df.columns:
                    continue  # column dropped entirely is also not serving a value
                if not _is_blank(df[a["column"]]):
                    n = int(df[a["column"]].notna().sum())
                    return Result(
                        "FAIL",
                        f"{lab}: column '{a['column']}' has {n} non-blank value(s) in {Path(f).name} (written after {since})",
                    )
            return Result("PASS", f"{len(files)} file(s) after {since} blank")

        if kind in ("source_must_not_contain", "source_must_contain"):
            files = sorted(_glob.glob(str(root / a["file"]), recursive=True))
            if not files:
                return Result("FAIL", f"{lab}: no file matches {a['file']}")
            rx = re.compile(a["pattern"])
            matched = [
                f
                for f in files
                if Path(f).is_file() and rx.search(Path(f).read_text(errors="ignore"))
            ]
            if kind == "source_must_not_contain":
                if matched:
                    rel = Path(matched[0]).relative_to(root)
                    return Result("FAIL", f"{lab}: /{a['pattern']}/ found in {rel}")
                return Result(
                    "PASS", f"/{a['pattern']}/ absent from {len(files)} file(s)"
                )
            if not matched:
                return Result(
                    "FAIL", f"{lab}: /{a['pattern']}/ not found in {a['file']}"
                )
            return Result("PASS", "pattern present")
    except Exception as e:  # a checker error must never read as PASS
        return Result("FAIL", f"{lab}: checker error {type(e).__name__}: {e}")
    return Result("FAIL", f"{lab}: unknown assertion kind {kind!r}")


# --------------------------------------------------------------------------
# schema + completeness
# --------------------------------------------------------------------------

REQUIRED = ("id", "subject", "ruling", "date", "doc", "note")


def schema_errors(reg: Dict[str, Any], root: Path = ROOT) -> List[str]:
    import datetime as dt

    errs, seen = [], set()
    for v in reg["verdicts"]:
        vid = v.get("id", "?")
        for k in REQUIRED:
            if not v.get(k):
                errs.append(f"{vid}: missing '{k}'")
        if v.get("id") in seen:
            errs.append(f"{vid}: duplicate id")
        seen.add(v.get("id"))
        if v.get("ruling") not in RULINGS:
            errs.append(f"{vid}: ruling {v.get('ruling')!r} not in {RULINGS}")
        try:
            dt.date.fromisoformat(v.get("date", ""))
        except ValueError:
            errs.append(f"{vid}: unparseable date {v.get('date')!r}")
        if v.get("doc") and not (root / v["doc"]).exists():
            errs.append(f"{vid}: doc {v['doc']} does not exist")
        if not v.get("enforcement") and not v.get("enforcement_gap"):
            errs.append(f"{vid}: needs 'enforcement' or an 'enforcement_gap' reason")
        for a in v.get("enforcement", []):
            if a.get("kind") not in KINDS:
                errs.append(f"{vid}: unknown assertion kind {a.get('kind')!r}")
    for u in reg.get("unregistered_ok", []):
        if not u.get("reason"):
            errs.append(f"unregistered_ok {u}: missing reason")
    return errs


def covered_refs(reg: Dict[str, Any]) -> set:
    refs = set()
    for _, a in iter_assertions(reg):
        if "script" in a and "flag" in a:
            refs.add(("flag", a["script"], a["flag"]))
        if "module" in a and "name" in a:
            refs.add(("const", a["module"], a["name"]))
    for u in reg.get("unregistered_ok", []):
        if "flag" in u:
            refs.add(("flag", u["script"], u["flag"]))
        if "name" in u:
            refs.add(("const", u["module"], u["name"]))
    return refs


def discover_levers(root: Path = ROOT) -> List[Tuple[str, str, str]]:
    levers = []
    for s in COMPLETENESS_SCRIPTS:
        for flag, meta in argparse_flags(s, root).items():
            if meta["action"] in _BOOL_ACTIONS:
                levers.append(("flag", s, flag))
    for mod, name in bool_constants(root):
        levers.append(("const", mod, name))
    return levers


def completeness_gaps(
    reg: Dict[str, Any], root: Path = ROOT
) -> List[Tuple[str, str, str]]:
    cov = covered_refs(reg)
    return [lv for lv in discover_levers(root) if lv not in cov]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    reg = load_registry()
    bad = 0
    print(f"{'RULING':<12} {'VERDICT':<34} {'RESULT':<5} ASSERTION")
    for v in reg["verdicts"]:
        if not v.get("enforcement"):
            print(
                f"{v['ruling']:<12} {v['id']:<34} {'GAP':<5} {v.get('enforcement_gap', '')[:70]}"
            )
        for a in v.get("enforcement", []):
            r = check_assertion(v, a)
            bad += r.status == "FAIL"
            what = (
                a.get("flag")
                or a.get("name")
                or a.get("column")
                or a.get("pattern", "")[:30]
            )
            print(f"{v['ruling']:<12} {v['id']:<34} {r.status:<5} {a['kind']}: {what}")
            if r.status != "PASS":
                print(f"{'':<54}-> {r.detail}")
    for e in schema_errors(reg):
        bad += 1
        print(f"SCHEMA FAIL: {e}")
    for lv in completeness_gaps(reg):
        bad += 1
        print(f"UNREGISTERED LEVER: {lv[0]} {lv[1]} {lv[2]}")
    print(f"\n{bad} failure(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
