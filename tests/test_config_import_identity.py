"""Regression test for the config double-import guard (GH issue #10).

The codebase imports config two ways: ``from src.config import ...``
(scripts/web) and bare ``from config import ...`` (src-internal modules
with src/ on sys.path). The guard at the bottom of src/config.py must make
both forms resolve to the SAME module object so runtime state can never
diverge between them.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")


@pytest.mark.unit
def test_prefixed_then_bare_import_is_same_module() -> None:
    """src.config loaded first (the pytest norm) — bare import must alias it."""
    sys.path.insert(0, SRC_DIR)
    try:
        import src.config as prefixed  # noqa: PLC0415

        import config as bare  # noqa: PLC0415

        assert bare is prefixed
    finally:
        sys.path.remove(SRC_DIR)


@pytest.mark.unit
def test_bare_then_prefixed_import_is_same_module() -> None:
    """Bare `config` loaded first — the src.config form must alias it.

    Runs in a subprocess so this process's already-imported modules can't
    mask a load-order bug.
    """
    code = (
        "import sys, os\n"
        f"sys.path.insert(0, {SRC_DIR!r})\n"
        f"sys.path.insert(0, {PROJECT_ROOT!r})\n"
        "import config as bare\n"
        "import src.config as prefixed\n"
        "assert bare is prefixed, 'config and src.config are distinct objects'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
