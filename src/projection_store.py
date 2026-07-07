"""Canonical Gold preseason projection loader.

Single source of truth for locating and reading the most recent preseason
projections parquet for a given season.  Used by both the live draft CLI
(``scripts/draft_live.py``) and the web API league router
(``web/api/routers/sleeper_user.py``) so both always serve the same Gold
artifact with identical column normalisation.

Usage
-----
::

    from src.projection_store import load_latest_preseason

    df = load_latest_preseason(2026)
    if df is None:
        # No preseason parquet on disk — fall back or raise 503.
        ...
"""

from __future__ import annotations

import glob
import logging
import os
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

#: Glob template for the preseason partition.  Relative to the project root
#: so it works whether the caller is a script in ``scripts/`` (which adds
#: the repo root to ``sys.path``) or the FastAPI app (CWD = repo root).
_PRESEASON_PATTERN = os.path.join(
    "data", "gold", "projections", "preseason", "season={season}", "*.parquet"
)


def load_latest_preseason(season: int) -> Optional[pd.DataFrame]:
    """Load the newest committed preseason projections parquet for *season*.

    The file is the Gold artifact produced by::

        python scripts/generate_projections.py --preseason --season YYYY

    It is committed to git so it survives pre-season API outages and
    upstream 404s that would break a live ``generate_preseason_projections``
    call.

    The ``recent_team`` column is aliased to ``team`` when present so
    downstream functions (player-name matching, roster optimizer, waiver
    ranking) have a consistent ``team`` column regardless of which pipeline
    version produced the file.

    Args:
        season: NFL season year (e.g. 2026).

    Returns:
        DataFrame on success; ``None`` when no parquet is found on disk or
        the file cannot be parsed.
    """
    pattern = _PRESEASON_PATTERN.format(season=season)
    files = sorted(glob.glob(pattern))
    if not files:
        logger.debug(
            "No preseason parquet for season=%d (pattern=%s)", season, pattern
        )
        return None
    path = files[-1]  # alphabetically last = newest YYYYMMDD_HHMMSS timestamp
    try:
        df = pd.read_parquet(path)
        # Normalise column name: pipeline older than v4.3 uses recent_team.
        if "recent_team" in df.columns and "team" not in df.columns:
            df = df.rename(columns={"recent_team": "team"})
        return df
    except Exception as exc:
        logger.warning("Could not read preseason parquet %s: %s", path, exc)
        return None
