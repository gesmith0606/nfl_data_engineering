"""FastAPI API package.

Package-level bootstrap: put the repo's ``src/`` directory on ``sys.path``
exactly once so API routers/services can import projection and analytics
modules (``lineup_builder``, ``game_archive``, ``draft_optimizer``, ...)
that follow the repo's bare-module import convention. Centralized here so
individual modules don't each mutate ``sys.path``.
"""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
del sys, Path, _SRC
