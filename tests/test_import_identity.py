"""Duplicate-module hazard: src modules are imported BOTH as top-level
(``import projection_engine``, src/ on sys.path) and as ``src.<module>``
(repo root on sys.path).  Python executes the file twice and keeps two module
objects unless something aliases them.  Only ``src/config.py`` has such an
alias guard, so a flag flipped through one import path is invisible through
the other for every other module.  These tests measure that.
"""

import importlib
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_DUP = (
    "two module objects: only config.py has the sys.modules alias guard, so "
    "`import X` and `import src.X` execute the file twice"
)


def _both(name):
    return importlib.import_module(name), importlib.import_module(f"src.{name}")


@pytest.mark.parametrize(
    "name",
    [
        "config",
        pytest.param("projection_engine", marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=_DUP)),
        pytest.param("ranking_score", marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=_DUP)),
        pytest.param("scoring_calculator", marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=_DUP)),
        pytest.param("utils", marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=_DUP)),
    ],
)
def test_same_module_object_both_ways(name):
    flat, pkg = _both(name)
    assert flat is pkg


def test_config_state_is_shared():
    flat, pkg = _both("config")
    assert flat.SCORING_CONFIGS is pkg.SCORING_CONFIGS


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=_DUP + " -- a USE_* flag flipped on one is not seen by the other")
@pytest.mark.parametrize(
    "name,flag",
    [
        ("projection_engine", "USE_RB_SNAP_COLLAPSE"),
        ("ranking_score", "USE_RANKING_SCORE"),
    ],
)
def test_flag_flip_visible_through_both_paths(name, flag, monkeypatch):
    flat, pkg = _both(name)
    monkeypatch.setattr(flat, flag, not getattr(flat, flag))
    assert getattr(pkg, flag) == getattr(flat, flag)


def test_setup_py_discovers_every_src_module():
    """setup.py globs src/*.py, so a new module is packaged without an edit."""
    text = (ROOT / "setup.py").read_text()
    assert '.glob("*.py")' in text and "py_modules" in text
    assert "py-modules = [" not in (ROOT / "pyproject.toml").read_text()

