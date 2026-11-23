"""Executable verdict registry: tie .planning rulings (SHIP/HOLD/KILL) to code.

``.planning/verdicts.json`` records one entry per model decision plus
machine-checkable assertions about the repo (CLI defaults, module constants and
their VALUES, what the production cron passes, whether a killed output column
is blank, public-copy retractions).  ``check_assertion`` evaluates one
assertion and returns a ``Result``; ``completeness_gaps`` finds levers
(argparse booleans, ``USE_*``-style constants) that no entry covers.

Everything is read statically (``ast``, YAML, regex) -- no pipeline is run and
no module is imported (the one exception is the legacy ``build_parser()``
fallback in ``_flags_from_import``).  The workflow checks are deliberately
conservative: a false positive is loud and cheap, a false negative is a
silently neutralised ruling.  See docs/VERDICT_REGISTRY.md.
"""

from __future__ import annotations

import ast
import datetime as _dt
import importlib.util
import json
import math
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
    "workflow_no_flag_passthrough",
    "data_column_blank",
    "source_must_not_contain",
    "source_must_contain",
)
#: Required keys per assertion kind (a typo is a schema error, not a KeyError).
KIND_KEYS = {
    "argparse_default": ("script", "flag", "expected"),
    "module_constant": ("module", "name", "expected"),
    "module_constant_contains": ("module", "name", "item"),
    "workflow_must_not_pass": ("workflow", "script", "flag"),
    "workflow_must_pass": ("workflow", "script", "flag"),
    "workflow_no_flag_passthrough": ("workflow", "scripts"),
    "data_column_blank": ("glob", "column", "enforced_since"),
    "source_must_not_contain": ("file", "pattern"),
    "source_must_contain": ("file", "pattern"),
}
#: Every CLI that publishes a board or sets a lineup.  sunday_projection_refresh is
#: a second production publisher (sunday-refresh.yml).
COMPLETENESS_SCRIPTS = (
    "scripts/generate_projections.py",
    "scripts/generate_predictions.py",
    "scripts/set_lineups.py",
    "scripts/sunday_projection_refresh.py",
)
#: Scripts the production crons run: argparse_default there must be paired with a
#: workflow assertion (see ``shape_errors``).
CRON_SCRIPTS = ("scripts/generate_projections.py", "scripts/generate_predictions.py")
_BOOL_ACTIONS = ("store_true", "store_false", "BooleanOptionalAction")
_PARSER_BUILDERS = ("build_parser", "_build_parser", "get_parser", "make_parser")
LEVER_CONST_RX = re.compile(r"^(USE|ENABLE|ALLOW|APPLY|DISABLE|SKIP)_[A-Z0-9_]+$")
_SKIP_DIRS = {".git", "node_modules", ".next", "venv", ".venv", "__pycache__"}


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
        or str(a.get("pattern", ""))[:24]
        or ""
    )
    where = (
        a.get("script")
        or a.get("module")
        or a.get("workflow")
        or (a.get("file") if isinstance(a.get("file"), str) else "")
        or ""
    )
    return f"{v['id']}::{a['kind']}::{where}::{tail}"


def _label(v: Dict[str, Any]) -> str:
    doc = Path(v["doc"]).name
    return f"{v['ruling']} '{v['id']}' ({doc}, {v['date']})"


def _as_list(x: Any) -> List[Any]:
    return list(x) if isinstance(x, (list, tuple)) else [x]


# --------------------------------------------------------------------------
# exact-case file access (a case mismatch must fail on macOS too)
# --------------------------------------------------------------------------


def _exact_file(root: Path, rel: str) -> Optional[Path]:
    """``root/rel`` if it exists with EXACTLY this case (listdir names are real)."""
    cur = root
    for part in Path(rel).parts:
        try:
            names = os.listdir(cur)
        except OSError:
            return None
        if part not in names:
            return None
        cur = cur / part
    return cur if cur.is_file() else None


def _glob_regex(pat: str) -> "re.Pattern[str]":
    out, i = [], 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif pat[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pat[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile("".join(out))


def _walk_files(base: Path, root: Path) -> Iterable[Path]:
    for dp, dns, fns in os.walk(base):
        dns[:] = [
            d
            for d in dns
            if d not in _SKIP_DIRS
            and (Path(dp) / d).relative_to(root).as_posix() != ".claude/worktrees"
        ]
        for fn in fns:
            yield Path(dp) / fn


def expand(root: Path, pattern: str) -> List[Path]:
    """Files matching ``pattern`` (``*``, ``**``, ``?``), case-SENSITIVE on any OS."""
    pat = pattern.replace("\\", "/")
    if not re.search(r"[*?]", pat):
        f = _exact_file(root, pat)
        return [f] if f else []
    lit: List[str] = []
    for part in pat.split("/")[:-1]:
        if re.search(r"[*?]", part):
            break
        lit.append(part)
    base = root.joinpath(*lit)
    if not base.is_dir():
        return []
    rx = _glob_regex(pat)
    return sorted(
        f
        for f in _walk_files(base, root)
        if rx.fullmatch(f.relative_to(root).as_posix())
    )


def git_tracked(root: Path = ROOT) -> Optional[List[str]]:
    """``git ls-files`` of ``root`` when ``root`` is itself a git toplevel, else None."""
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if top.returncode or Path(top.stdout.strip()).resolve() != root.resolve():
            return None
        ls = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if ls.returncode:
            return None
        return [x for x in ls.stdout.split("\0") if x]
    except (OSError, subprocess.SubprocessError):
        return None


def match_tracked(pattern: str, tracked: Iterable[str]) -> List[str]:
    """Tracked names matching a literal path or glob, exact case."""
    pat = pattern.replace("\\", "/")
    if not re.search(r"[*?]", pat):
        return [t for t in tracked if t == pat]
    rx = _glob_regex(pat)
    return [t for t in tracked if rx.fullmatch(t)]


# --------------------------------------------------------------------------
# static python reading: assignments (every site), literal evaluation
# --------------------------------------------------------------------------


@dataclass
class Site:
    name: str
    value: Optional[ast.AST]  # None = not a plain literal-bindable assignment
    line: int
    how: str


def _sub_bodies(n: ast.AST) -> List[List[ast.stmt]]:
    if isinstance(n, ast.If):
        return [n.body, n.orelse]
    if isinstance(n, ast.Try):
        return [n.body, n.orelse, n.finalbody] + [h.body for h in n.handlers]
    if isinstance(n, (ast.With, ast.For, ast.While)):
        return [n.body, getattr(n, "orelse", [])]
    return []


def _iter_module_stmts(body: Sequence[ast.stmt]) -> Iterable[ast.stmt]:
    """Module-level statements, including those nested in top-level if/try/with/for."""
    for n in body:
        yield n
        for sub in _sub_bodies(n):
            yield from _iter_module_stmts(sub)


def _is_globals_call(n: ast.AST) -> bool:
    return (
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in ("globals", "vars")
        and not n.args
    )


def module_sites(tree: ast.Module) -> List[Site]:
    """Every place a module-level name is (re)bound, including dynamic rebinding."""
    sites: List[Site] = []

    def target(t: ast.AST, value: Optional[ast.AST], line: int, how: str) -> None:
        if isinstance(t, ast.Name):
            sites.append(Site(t.id, value, line, how))
        elif isinstance(t, (ast.Tuple, ast.List)):
            vals = (
                value.elts
                if isinstance(value, (ast.Tuple, ast.List))
                and len(value.elts) == len(t.elts)
                else [None] * len(t.elts)
            )
            for sub_t, sub_v in zip(t.elts, vals):
                target(sub_t, sub_v, line, how)
        elif isinstance(t, ast.Subscript) and _is_globals_call(t.value):
            key = t.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                sites.append(Site(key.value, None, line, "globals()[...] assignment"))
            else:
                sites.append(Site("<dynamic>", None, line, "globals()[<dynamic>]"))

    for n in _iter_module_stmts(tree.body):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                target(t, n.value, n.lineno, "assignment")
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            target(n.target, n.value, n.lineno, "assignment")
        elif isinstance(n, ast.AugAssign):
            target(n.target, None, n.lineno, "augmented assignment")
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                nm = al.asname or al.name.split(".")[0]
                sites.append(Site(nm, None, n.lineno, "import rebinding"))
        elif (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and _is_globals_call(n.value.func.value)
            and n.value.func.attr in ("update", "setdefault", "__setitem__")
        ):
            sites.append(Site("<dynamic>", None, n.lineno, "globals().update(...)"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Global):
            for nm in n.names:
                sites.append(
                    Site(nm, None, n.lineno, "'global' declaration in function")
                )
    return sites


def _static_eval(node: ast.AST, env: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise ValueError(f"unresolvable name {node.id}")
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_static_eval(e, env) for e in node.elts]
    if isinstance(node, ast.Set):
        return sorted(_static_eval(e, env) for e in node.elts)
    if isinstance(node, ast.Dict):
        if any(k is None for k in node.keys):
            raise ValueError("dict unpacking")
        return {
            _static_eval(k, env): _static_eval(v, env)  # type: ignore[arg-type]
            for k, v in zip(node.keys, node.values)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _static_eval(node.operand, env)
        return -v if isinstance(node.op, ast.USub) else +v
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
    ):
        a, b = _static_eval(node.left, env), _static_eval(node.right, env)
        return (
            {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b}.get(type(node.op), None)
            if not isinstance(node.op, ast.Div)
            else a / b
        )
    raise ValueError(f"non-literal {type(node).__name__}")


def _module_env(tree: ast.Module) -> Dict[str, Any]:
    """Literal values of module names bound exactly once (resolved in source order)."""
    sites = module_sites(tree)
    counts: Dict[str, int] = {}
    for s in sites:
        counts[s.name] = counts.get(s.name, 0) + 1
    env: Dict[str, Any] = {}
    for s in sites:
        if counts[s.name] == 1 and s.value is not None:
            try:
                env[s.name] = _static_eval(s.value, env)
            except Exception:
                pass
    return env


def _values_equal(a: Any, b: Any) -> bool:
    """Compare by value: bools strictly, numbers with a small tolerance, containers deep."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_values_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_values_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _norm(x: Any) -> Any:
    if isinstance(x, (tuple, list)):
        return [_norm(i) for i in x]
    if isinstance(x, set):
        return sorted(_norm(i) for i in x)
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    return x


def _module_file(module: str, root: Path) -> Optional[Path]:
    if "." in module:  # dotted repo path, e.g. web.api.routers.predictions
        return _exact_file(root, module.replace(".", "/") + ".py")
    for d in ("src", "scripts"):
        p = _exact_file(root, f"{d}/{module}.py")
        if p:
            return p
    return None


def module_constant(module: str, name: str, root: Path = ROOT) -> Tuple[bool, Any]:
    """Statically read ``module.name``; FAIL if it is bound anywhere more than once."""
    f = _module_file(module, root)
    if f is None:
        return False, f"module '{module}' not found under src/, scripts/ or web/api/"
    rel = f.relative_to(root).as_posix()
    tree = ast.parse(f.read_text())
    sites = [s for s in module_sites(tree) if s.name in (name, "<dynamic>")]
    if not sites:
        return False, f"{module}.{name} not defined"
    if len(sites) > 1 or sites[0].name == "<dynamic>":
        where = "; ".join(f"{rel}:{s.line} ({s.how})" for s in sites)
        return False, (
            f"{module}.{name} is rebound or dynamically assignable "
            f"({len(sites)} site(s)): {where}"
        )
    s = sites[0]
    if s.value is None:
        return (
            False,
            f"{module}.{name} is not a plain literal ({rel}:{s.line}, {s.how})",
        )
    try:
        return True, _norm(_static_eval(s.value, _module_env(tree)))
    except Exception:
        return False, f"{module}.{name} is not a literal ({rel}:{s.line})"


def _assigned_levers(tree: ast.Module) -> List[str]:
    """Module-level names matching the lever pattern bound to a bool or 0/1 literal."""
    out = []
    for s in module_sites(tree):
        v = s.value
        if (
            LEVER_CONST_RX.match(s.name)
            and isinstance(v, ast.Constant)
            and (isinstance(v.value, bool) or v.value in (0, 1))
            and not isinstance(v.value, str)
        ):
            out.append(s.name)
    return out


def _py_files(root: Path, sub: str) -> List[Path]:
    d = root / sub
    return (
        sorted(p for p in _walk_files(d, root) if p.suffix == ".py")
        if d.is_dir()
        else []
    )


def _module_name(f: Path, root: Path) -> str:
    rel = f.relative_to(root).as_posix()
    if rel.startswith(("src/", "scripts/")) and rel.count("/") == 1:
        return f.stem
    return rel[: -len(".py")].replace("/", ".")


def bool_constants(root: Path = ROOT) -> List[Tuple[str, str]]:
    """Every ``USE|ENABLE|ALLOW|APPLY|DISABLE|SKIP_*`` bool/0-1 constant in src/, scripts/, web/api."""
    found = []
    for sub in ("src", "scripts", "web/api"):
        for f in _py_files(root, sub):
            for nm in _assigned_levers(ast.parse(f.read_text())):
                found.append((_module_name(f, root), nm))
    return found


# --------------------------------------------------------------------------
# argparse (static): both inline-in-main() and build_parser() shapes
# --------------------------------------------------------------------------


def _lit(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return "<non-literal>"


def _action_name(node: ast.AST) -> Any:
    """``'store_true'`` or ``argparse.BooleanOptionalAction`` (attribute/name) -> a string."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
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
        kws = {k.arg: k.value for k in n.keywords if k.arg}
        action = _action_name(kws["action"]) if "action" in kws else None
        ref = None
        if "default" in kws:
            default = _lit(kws["default"])
            if isinstance(kws["default"], ast.Name):
                ref = kws["default"].id
        elif action == "store_true":
            default = False
        elif action == "store_false":
            default = True
        else:
            default = None
        dest = (
            _lit(kws["dest"])
            if "dest" in kws
            else names[0].lstrip("-").replace("-", "_")
        )
        out[names[0]] = {
            "action": action,
            "default": default,
            "default_ref": ref,
            "dest": dest,
        }
    return out


def _flags_from_import(script: Path, root: Path = ROOT) -> Dict[str, Dict[str, Any]]:
    """Fallback for a parser extracted into a ``build_parser()`` elsewhere."""
    spec = importlib.util.spec_from_file_location(f"_vr_{script.stem}", script)
    if spec is None or spec.loader is None:
        return {}
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script.parent))
    sys.path.insert(0, str(root))
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
    p = _exact_file(root, script)
    if p is None:
        raise FileNotFoundError(f"script {script} not found (exact case)")
    flags = _flags_from_ast(ast.parse(p.read_text()))
    if not flags:
        flags = _flags_from_import(p, root)
    return flags


def argparse_mutations(script: str, dest: str, root: Path = ROOT) -> List[str]:
    """Sites that overwrite a parsed default: ``set_defaults(dest=..)``, ``x.dest = ..``."""
    p = _exact_file(root, script)
    if p is None:
        return []
    hits = []
    for n in ast.walk(ast.parse(p.read_text())):
        if isinstance(n, ast.Call):
            fn = n.func
            if isinstance(fn, ast.Attribute) and fn.attr == "set_defaults":
                if any(k.arg in (dest, None) for k in n.keywords) or n.args:
                    hits.append(f"{script}:{n.lineno} set_defaults(...)")
            if (
                isinstance(fn, ast.Name)
                and fn.id == "setattr"
                and len(n.args) >= 2
                and isinstance(n.args[1], ast.Constant)
                and n.args[1].value == dest
            ):
                hits.append(f"{script}:{n.lineno} setattr(..., {dest!r}, ...)")
        targets: List[ast.AST] = []
        if isinstance(n, ast.Assign):
            targets = list(n.targets)
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
            targets = [n.target]
        while targets:
            t = targets.pop()
            if isinstance(t, (ast.Tuple, ast.List)):
                targets.extend(t.elts)
            elif isinstance(t, ast.Attribute) and t.attr == dest:
                hits.append(f"{script}:{n.lineno} {ast.unparse(t)} = ...")
            elif (
                isinstance(t, ast.Subscript)
                and isinstance(t.slice, ast.Constant)
                and t.slice.value == dest
                and (
                    (
                        isinstance(t.value, ast.Call)
                        and getattr(t.value.func, "id", "") == "vars"
                    )
                    or (
                        isinstance(t.value, ast.Attribute)
                        and t.value.attr == "__dict__"
                    )
                )
            ):
                hits.append(f"{script}:{n.lineno} vars(...)[{dest!r}] = ...")
    return hits


def _resolve_name(rel: str, name: str, root: Path, depth: int = 0) -> Tuple[bool, Any]:
    """Value of ``name`` as seen from file ``rel``: local literal, else via ``from X import``."""
    f = _exact_file(root, rel)
    if f is None or depth > 5:
        return False, f"cannot resolve {name} from {rel}"
    tree = ast.parse(f.read_text())
    local = [
        s for s in module_sites(tree) if s.name == name and s.how != "import rebinding"
    ]
    if len(local) == 1 and local[0].value is not None:
        try:
            return True, _norm(_static_eval(local[0].value, _module_env(tree)))
        except Exception:
            return False, f"{name} in {rel} is not a literal"
    if len(local) > 1:
        return False, f"{name} bound {len(local)} times in {rel}"
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            if any(al.name == name and al.asname is None for al in n.names):
                nxt = n.module.replace(".", "/") + ".py"
                if _exact_file(root, nxt) is None:
                    nxt = "scripts/" + nxt
                return _resolve_name(nxt, name, root, depth + 1)
    return False, f"{name} not defined or imported in {rel}"


# --------------------------------------------------------------------------
# workflows + shell: conservative token scan
# --------------------------------------------------------------------------


def strip_shell_comments(text: str) -> str:
    """Remove ``# ...`` comments (a ``#`` starts one only at a word start, outside quotes)."""
    out: List[str] = []
    i, n, sq, dq = 0, len(text), False, False
    while i < n:
        c = text[i]
        if sq:
            out.append(c)
            sq = c != "'"
            i += 1
            continue
        if dq:
            if c == "\\" and i + 1 < n:
                out.append(text[i : i + 2])
                i += 2
                continue
            out.append(c)
            dq = c != '"'
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(text[i : i + 2])
            i += 2
            continue
        if c == "'":
            sq = True
        elif c == '"':
            dq = True
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;|&("):
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def simple_commands(text: str) -> List[str]:
    """Split on unquoted ``; & && | || newline`` after joining ``\\`` continuations.

    ``${{ ... }}`` expressions are opaque (they contain ``||`` / ``&&``).
    """
    text = re.sub(r"\\\n[ \t]*", " ", text)
    cmds: List[str] = []
    cur: List[str] = []
    i, n, sq, dq = 0, len(text), False, False

    def flush() -> None:
        s = "".join(cur).strip()
        if s:
            cmds.append(s)
        cur.clear()

    while i < n:
        c = text[i]
        if text.startswith("${{", i):
            j = text.find("}}", i)
            j = n if j < 0 else j + 2
            cur.append(text[i:j])
            i = j
            continue
        if sq:
            cur.append(c)
            sq = c != "'"
        elif dq:
            if c == "\\" and i + 1 < n:
                cur.append(text[i : i + 2])
                i += 2
                continue
            cur.append(c)
            dq = c != '"'
        elif c == "\\" and i + 1 < n:
            cur.append(text[i : i + 2])
            i += 2
            continue
        elif c == "'":
            sq = True
            cur.append(c)
        elif c == '"':
            dq = True
            cur.append(c)
        elif c in ";\n":
            flush()
        elif c in "&|":
            while i + 1 < n and text[i + 1] == c:
                i += 1
            flush()
        else:
            cur.append(c)
        i += 1
    flush()
    return cmds


def _unquoted(cmd: str) -> str:
    return cmd.replace('"', "").replace("'", "")


def _has_flag(cmd: str, flag: str) -> bool:
    return bool(re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", _unquoted(cmd)))


def _shadow_exempt(cmd: str, script_stem: str) -> bool:
    """The ONE exemption: this very command invokes the script AND carries a real
    ``--shadow-tag <value>`` argument (a shadow run never publishes)."""
    if script_stem not in cmd:
        return False
    return bool(re.search(r"(?<![\w-])--shadow-tag(?:=|\s+)[^\s\-]", _unquoted(cmd)))


def _tokens(cmd: str) -> List[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


_WRAPPERS = {
    "time",
    "nohup",
    "exec",
    "env",
    "command",
    "sudo",
    "uv",
    "run",
    "poetry",
    "pipenv",
}


def _invocation(cmd: str, stem: str) -> Optional[List[str]]:
    """Tokens of ``cmd`` if it genuinely runs ``stem`` (python <script>, ./script, -m mod)."""
    toks = _tokens(cmd)
    while toks and (re.fullmatch(r"[A-Za-z_]\w*=.*", toks[0]) or toks[0] in _WRAPPERS):
        toks.pop(0)
    if not toks:
        return None
    script_rx = re.compile(rf"(?:^|[/.]){re.escape(stem)}(?:\.py)?$")
    head = os.path.basename(toks[0])
    if script_rx.search(toks[0]):
        return toks
    if re.fullmatch(r"python[\d.]*|py", head) and any(
        script_rx.search(t) for t in toks[1:8]
    ):
        return toks
    return None


def _flags_of(toks: List[str]) -> List[str]:
    return [t.split("=", 1)[0] for t in toks if t.startswith("--")]


def _tok_shadow(toks: List[str]) -> bool:
    for i, t in enumerate(toks):
        if t == "--shadow-tag" and i + 1 < len(toks):
            return bool(toks[i + 1]) and not toks[i + 1].startswith("-")
        if t.startswith("--shadow-tag=") and len(t) > len("--shadow-tag="):
            return True
    return False


def _yaml_texts(text: str) -> List[Tuple[str, bool]]:
    """Every executable-ish scalar of a workflow: ``(text, is_shell)``; ``run`` bodies are shell."""
    out: List[Tuple[str, bool]] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            stepish = any(k in o for k in ("run", "uses", "steps", "runs-on"))
            for k, v in o.items():
                if k == "run" and isinstance(v, str):
                    out.append((v, True))
                elif k in ("name", "description") and stepish:
                    continue
                else:
                    walk(v)
        elif isinstance(o, list):
            for i in o:
                walk(i)
        elif isinstance(o, str):
            out.append((o, False))

    for doc in yaml.safe_load_all(text):
        walk(doc)
    return out


def _workflow_files(workflow: str, root: Path) -> List[Path]:
    d = root / ".github" / "workflows"
    if workflow == "*":
        if not d.is_dir():
            return []
        return sorted(p for p in d.iterdir() if p.suffix.lower() in (".yml", ".yaml"))
    f = _exact_file(root, f".github/workflows/{workflow}")
    if f is None:
        raise FileNotFoundError(f"workflow {workflow} not found (exact case)")
    return [f]


def shell_files(root: Path = ROOT) -> List[Path]:
    """Tracked shell scripts (``git ls-files``), else a filesystem walk."""
    tracked = git_tracked(root)
    exts = (".sh", ".bash", ".zsh")
    if tracked is not None:
        return [root / t for t in tracked if t.endswith(exts) and (root / t).is_file()]
    return sorted(f for f in _walk_files(root, root) if f.name.endswith(exts))


def _texts_of(path: Path) -> List[Tuple[str, bool]]:
    txt = path.read_text(errors="ignore")
    if path.suffix.lower() in (".yml", ".yaml"):
        return _yaml_texts(txt)
    return [(txt, True)]


def _executable_commands(files: Iterable[Path]) -> Iterable[Tuple[str, str, bool]]:
    """``(file name, simple command, is_run_body)`` for every executable text."""
    for f in files:
        for text, is_shell in _texts_of(f):
            body = strip_shell_comments(text) if is_shell else text
            for cmd in simple_commands(body):
                yield f.name, cmd, is_shell


def _scan_files(workflow: str, root: Path, with_shell: bool) -> List[Path]:
    files = _workflow_files(workflow, root)
    if with_shell and workflow == "*":
        files = files + shell_files(root)
    return files


def workflow_ban_hits(a: Dict[str, Any], root: Path) -> Tuple[List[str], int]:
    """(``file: command`` for each offending command, files scanned)."""
    stem, flag = Path(a["script"]).stem, a["flag"]
    files = _scan_files(a["workflow"], root, True)
    hits = []
    for name, cmd, _ in _executable_commands(files):
        if _has_flag(cmd, flag) and not _shadow_exempt(cmd, stem):
            hits.append(f"{name}: {cmd[:110]}")
    return hits, len(files)


def workflow_pass_hits(a: Dict[str, Any], root: Path) -> List[str]:
    """Files with a real, non-shadow invocation of the script passing the flag."""
    stem, flag = Path(a["script"]).stem, a["flag"]
    hits = []
    for name, cmd, is_shell in _executable_commands(
        _workflow_files(a["workflow"], root)
    ):
        if not is_shell:
            continue
        toks = _invocation(cmd, stem)
        if toks and flag in _flags_of(toks) and not _tok_shadow(toks):
            hits.append(name)
    return hits


_EXPR_RX = re.compile(r"\$\{\{(.*?)\}\}", re.S)
_RISKY_EXPR = re.compile(
    r"(?<![\w.])(?:inputs|vars|matrix|steps|needs|env)\.|github\.event\.inputs\."
)


def passthrough_violations(a: Dict[str, Any], root: Path) -> List[str]:
    """Unreviewable flag passthrough on a publisher command line.

    A ``${{ inputs.* / vars.* / ... }}`` expression or a shell variable on a command
    that names one of ``a['scripts']`` can smuggle any flag past the token scan, so each
    must be allowlisted (with a reason) in the registry.
    """
    stems = [Path(s).stem for s in a["scripts"]]
    ok_expr = {
        (e["workflow"], " ".join(e["expression"].split()))
        for e in a.get("allow_expressions", [])
    }
    ok_vars = {v["name"] for v in a.get("allow_vars", [])}
    hits = []
    for name, cmd, is_shell in _executable_commands(
        _workflow_files(a["workflow"], root)
    ):
        if not is_shell or not any(s in cmd for s in stems):
            continue
        for m in _EXPR_RX.finditer(cmd):
            expr = " ".join(m.group(1).split())
            if _RISKY_EXPR.search(expr) and (name, expr) not in ok_expr:
                hits.append(f"{name}: expression ${{{{ {expr} }}}} on `{cmd[:80]}`")
        bare = _EXPR_RX.sub("", cmd)
        for m in re.finditer(r"\$\{?([A-Za-z_]\w*)", bare):
            if m.group(1) not in ok_vars:
                hits.append(f"{name}: variable ${m.group(1)} on `{cmd[:80]}`")
    return hits


# --------------------------------------------------------------------------
# data files
# --------------------------------------------------------------------------


def _ts_key(s: str) -> str:
    """``YYYYMMDD_HHMMSS`` (UTC) of a date or ISO timestamp (``Z``/offset aware)."""
    d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is not None:
        d = d.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y%m%d_%H%M%S")


def _filename_key(name: str) -> Optional[str]:
    m = re.search(r"(\d{8})_(\d{6})", name)
    return f"{m.group(1)}_{m.group(2)}" if m else None


def _is_blank(series: Any) -> bool:
    return bool(
        series.map(
            lambda x: x is None or x != x or (isinstance(x, str) and not x.strip())
        ).all()
    )


# --------------------------------------------------------------------------
# the checker
# --------------------------------------------------------------------------


def _source_hits(a: Dict[str, Any], files: List[Path], root: Path) -> List[str]:
    rx = re.compile(a["pattern"])
    unless = re.compile(a["unless"]) if a.get("unless") else None
    hits = []
    for f in files:
        text = f.read_text(errors="ignore")
        rel = f.relative_to(root).as_posix()
        if unless is not None:
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line) and not unless.search(line):
                    hits.append(f"{rel}:{i}: {line.strip()[:100]}")
        else:
            m = rx.search(text)
            if m:
                hits.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}")
    return hits


def check_assertion(v: Dict[str, Any], a: Dict[str, Any], root: Path = ROOT) -> Result:
    kind = a["kind"]
    lab = _label(v)
    try:
        if kind == "argparse_default":
            flags = argparse_flags(a["script"], root)
            if a["flag"] not in flags:
                return Result("FAIL", f"{lab}: {a['flag']} not found in {a['script']}")
            meta = flags[a["flag"]]
            got = meta["default"]
            if got == "<non-literal>" and meta.get("default_ref"):
                ok, got = _resolve_name(a["script"], meta["default_ref"], root)
                if not ok:
                    return Result("FAIL", f"{lab}: {got}")
            muts = (
                argparse_mutations(a["script"], meta.get("dest") or "", root)
                if meta.get("dest")
                else []
            )
            if muts:
                return Result(
                    "FAIL",
                    f"{lab}: {a['flag']} default is overwritten after parsing: {'; '.join(muts)}",
                )
            if not _values_equal(got, a["expected"]):
                return Result(
                    "FAIL",
                    f"{lab}: {a['script']} {a['flag']} default is {got!r}, expected {a['expected']!r}",
                )
            return Result("PASS", f"default={got!r}")

        if kind == "module_constant":
            ok, got = module_constant(a["module"], a["name"], root)
            if not ok:
                return Result("FAIL", f"{lab}: {got}")
            if not _values_equal(got, _norm(a["expected"])):
                return Result(
                    "FAIL",
                    f"{lab}: {a['module']}.{a['name']} is {got!r}, expected {a['expected']!r}",
                )
            return Result("PASS", f"{a['name']}={got!r}")

        if kind == "module_constant_contains":
            ok, got = module_constant(a["module"], a["name"], root)
            if not ok:
                return Result("FAIL", f"{lab}: {got}")
            if not any(_values_equal(g, _norm(a["item"])) for g in got):
                return Result(
                    "FAIL",
                    f"{lab}: {a['module']}.{a['name']} lacks {a['item']!r} (has {got!r})",
                )
            return Result("PASS", f"{a['name']} contains {a['item']!r}")

        if kind == "workflow_must_not_pass":
            hits, nfiles = workflow_ban_hits(a, root)
            if hits:
                return Result(
                    "FAIL",
                    f"{lab}: {a['flag']} appears in executable workflow/shell text "
                    f"(only a --shadow-tag run of {a['script']} may carry it): "
                    + " | ".join(hits[:4]),
                )
            return Result("PASS", f"not present in {nfiles} workflow/shell file(s)")

        if kind == "workflow_must_pass":
            hits = workflow_pass_hits(a, root)
            if not hits:
                return Result(
                    "FAIL",
                    f"{lab}: {a['flag']} is NOT passed to {a['script']} by a real "
                    f"invocation in {a['workflow']}",
                )
            return Result("PASS", f"passed in {hits[0]}")

        if kind == "workflow_no_flag_passthrough":
            hits = passthrough_violations(a, root)
            if hits:
                return Result(
                    "FAIL",
                    f"{lab}: unreviewable flag passthrough on a publisher command "
                    f"(allowlist it in the registry with a reason): "
                    + " | ".join(hits[:4]),
                )
            return Result(
                "PASS", "no unallowlisted expansion on publisher command lines"
            )

        if kind == "data_column_blank":
            import pandas as pd

            since = a["enforced_since"]
            since_key = _ts_key(since)
            files = sorted(
                f
                for f in expand(root, a["glob"])
                if (_filename_key(f.name) or "") >= since_key
            )
            if not files:
                return Result(
                    "SKIP",
                    f"no file matching {a['glob']} has a filename timestamp at/after {since} "
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
                        f"{lab}: column '{a['column']}' has {n} non-blank value(s) in {f.name} (written at/after {since})",
                    )
            return Result("PASS", f"{len(files)} file(s) at/after {since} blank")

        if kind in ("source_must_not_contain", "source_must_contain"):
            patterns = _as_list(a["file"])
            missing = [
                p for p in patterns if not re.search(r"[*?]", p) and not expand(root, p)
            ]
            if missing:  # a literal path (e.g. README.MD) must exist, exact case
                return Result("FAIL", f"{lab}: literal file(s) not found: {missing}")
            files = sorted({f for p in patterns for f in expand(root, p)})
            if not files:
                return Result("FAIL", f"{lab}: no file matches {patterns}")
            hits = _source_hits(a, files, root)
            if kind == "source_must_not_contain":
                if hits:
                    return Result(
                        "FAIL",
                        f"{lab}: /{a['pattern']}/ found: " + " | ".join(hits[:5]),
                    )
                return Result(
                    "PASS", f"/{a['pattern']}/ absent from {len(files)} file(s)"
                )
            if not hits:
                return Result(
                    "FAIL", f"{lab}: /{a['pattern']}/ not found in {patterns}"
                )
            return Result("PASS", "pattern present")
    except Exception as e:  # a checker error must never read as PASS
        return Result("FAIL", f"{lab}: checker error {type(e).__name__}: {e}")
    return Result("FAIL", f"{lab}: unknown assertion kind {kind!r}")


# --------------------------------------------------------------------------
# schema, shape, completeness
# --------------------------------------------------------------------------

REQUIRED = ("id", "subject", "ruling", "date", "doc", "note")


def schema_errors(reg: Dict[str, Any], root: Path = ROOT) -> List[str]:
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
            _dt.date.fromisoformat(v.get("date", ""))
        except ValueError:
            errs.append(f"{vid}: unparseable date {v.get('date')!r}")
        if v.get("doc") and not _exact_file(root, v["doc"]):
            errs.append(f"{vid}: doc {v['doc']} does not exist (exact case)")
        if not v.get("enforcement") and not v.get("enforcement_gap"):
            errs.append(f"{vid}: needs 'enforcement' or an 'enforcement_gap' reason")
        for a in v.get("enforcement", []):
            if a.get("kind") not in KINDS:
                errs.append(f"{vid}: unknown assertion kind {a.get('kind')!r}")
                continue
            for k in KIND_KEYS[a["kind"]]:
                if k not in a:
                    errs.append(f"{vid}: {a['kind']} assertion missing '{k}'")
            for lst, key in (
                ("allow_expressions", "expression"),
                ("allow_vars", "name"),
            ):
                for e in a.get(lst, []):
                    if not e.get("reason") or not e.get(key):
                        errs.append(
                            f"{vid}: {lst} entry needs '{key}' and a reason: {e}"
                        )
            if a["kind"] == "data_column_blank":
                try:
                    _ts_key(a["enforced_since"])
                except (ValueError, KeyError):
                    errs.append(
                        f"{vid}: unparseable enforced_since {a.get('enforced_since')!r}"
                    )
    for u in reg.get("unregistered_ok", []):
        if not u.get("reason"):
            errs.append(f"unregistered_ok {u}: missing reason")
        if not (("script" in u and "flag" in u) or ("module" in u and "name" in u)):
            errs.append(f"unregistered_ok {u}: needs script+flag or module+name")
    for lv in reg.get("value_levers", []):
        if not (("script" in lv and "flag" in lv) or ("module" in lv and "name" in lv)):
            errs.append(f"value_levers {lv}: needs script+flag or module+name")
    for w in reg.get("attribute_write_allowlist", []):
        if not (w.get("file") and w.get("target") and w.get("reason")):
            errs.append(f"attribute_write_allowlist {w}: needs file, target, reason")
    return errs


def shape_errors(reg: Dict[str, Any]) -> List[str]:
    """Ruling-specific structure: what makes each ruling a decision rather than a comment."""
    errs = []
    for v in reg["verdicts"]:
        vid, ruling = v.get("id", "?"), v.get("ruling")
        asserts = v.get("enforcement", [])
        if ruling in ("KILL", "DEAD", "HOLD", "SHIP", "SHIP_OPT_IN") and not asserts:
            if not v.get("enforcement_gap"):
                errs.append(
                    f"{vid}: {ruling} has neither enforcement nor enforcement_gap"
                )
        have_wf = {
            (a.get("script"), a.get("flag"))
            for a in asserts
            if a["kind"] in ("workflow_must_pass", "workflow_must_not_pass")
        }
        for a in asserts:
            if a["kind"] == "argparse_default" and a["script"] in CRON_SCRIPTS:
                if (a["script"], a["flag"]) not in have_wf:
                    errs.append(
                        f"{vid}: argparse_default {a['flag']} has no workflow_must_pass/"
                        f"workflow_must_not_pass for the same flag (the cron could override it)"
                    )
        if ruling in ("HOLD", "SHIP_OPT_IN"):
            for a in asserts:
                if a["kind"] == "workflow_must_pass":
                    errs.append(
                        f"{vid}: {ruling} must not require the cron to pass {a['flag']}"
                    )
        if (
            ruling in ("KILL", "DEAD")
            and not any(a["kind"] != "workflow_must_pass" for a in asserts)
            and not v.get("enforcement_gap")
        ):
            errs.append(f"{vid}: {ruling} needs a negative assertion")
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


def pinned_refs(reg: Dict[str, Any]) -> set:
    """Refs pinned by a VALUE assertion (an allowlist entry does not pin anything)."""
    refs = set()
    for _, a in iter_assertions(reg):
        if a["kind"] == "argparse_default":
            refs.add(("flag", a["script"], a["flag"]))
        if a["kind"] == "module_constant":
            refs.add(("const", a["module"], a["name"]))
    return refs


def value_lever_gaps(reg: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    pinned = pinned_refs(reg)
    gaps = []
    for lv in reg.get("value_levers", []):
        ref = (
            ("flag", lv["script"], lv["flag"])
            if "flag" in lv
            else ("const", lv["module"], lv["name"])
        )
        if ref not in pinned:
            gaps.append(ref)
    return gaps


def discover_levers(root: Path = ROOT) -> List[Tuple[str, str, str]]:
    levers = []
    for s in COMPLETENESS_SCRIPTS:
        if _exact_file(root, s) is None:
            continue
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


def attribute_write_violations(reg: Dict[str, Any], root: Path = ROOT) -> List[str]:
    """``othermodule.USE_X = ...`` / ``setattr(m, 'USE_X', ...)`` anywhere in src/, scripts/, web/api."""
    allow = {(w["file"], w["target"]) for w in reg.get("attribute_write_allowlist", [])}
    rx = re.compile(r"^(USE|ENABLE)_[A-Z0-9_]+$")
    hits = []
    for sub in ("src", "scripts", "web/api"):
        for f in _py_files(root, sub):
            rel = f.relative_to(root).as_posix()
            if rel.startswith("scripts/experiments/") or (
                rel.startswith("scripts/") and f.name.startswith("experiment")
            ):
                continue
            for n in ast.walk(ast.parse(f.read_text())):
                targets: List[ast.AST] = []
                if isinstance(n, ast.Assign):
                    targets = list(n.targets)
                elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
                    targets = [n.target]
                while targets:
                    t = targets.pop()
                    if isinstance(t, (ast.Tuple, ast.List)):
                        targets.extend(t.elts)
                    elif isinstance(t, ast.Attribute) and rx.match(t.attr):
                        if (rel, ast.unparse(t)) not in allow:
                            hits.append(f"{rel}:{n.lineno} {ast.unparse(t)} = ...")
                if (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name)
                    and n.func.id == "setattr"
                    and len(n.args) >= 2
                    and isinstance(n.args[1], ast.Constant)
                    and isinstance(n.args[1].value, str)
                    and rx.match(n.args[1].value)
                ):
                    tgt = f"setattr(..., {n.args[1].value!r})"
                    if (rel, tgt) not in allow:
                        hits.append(f"{rel}:{n.lineno} {tgt}")
    return hits


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
                or str(a.get("pattern", ""))[:30]
            )
            print(f"{v['ruling']:<12} {v['id']:<34} {r.status:<5} {a['kind']}: {what}")
            if r.status != "PASS":
                print(f"{'':<54}-> {r.detail}")
    for e in schema_errors(reg) + shape_errors(reg):
        bad += 1
        print(f"SCHEMA FAIL: {e}")
    for lv in completeness_gaps(reg):
        bad += 1
        print(f"UNREGISTERED LEVER: {lv[0]} {lv[1]} {lv[2]}")
    for lv in value_lever_gaps(reg):
        bad += 1
        print(f"VALUE LEVER WITH NO PINNING ASSERTION: {lv[0]} {lv[1]} {lv[2]}")
    for h in attribute_write_violations(reg):
        bad += 1
        print(f"CROSS-MODULE LEVER WRITE: {h}")
    print(f"\n{bad} failure(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
