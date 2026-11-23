"""Module discovery for the editable/installed package.

Everything else lives in pyproject.toml. src/*.py are importable as top-level
modules (``import projection_engine``) as well as ``src.projection_engine``;
setuptools has no static glob for ``py-modules``, so they are listed here.
"""

from pathlib import Path

from setuptools import setup

setup(
    py_modules=sorted(
        p.stem
        for p in (Path(__file__).parent / "src").glob("*.py")
        if p.stem != "__init__"
    )
)
