"""Canonical Gold preseason projection loader.

Single source of truth for locating and reading the most recent preseason
projections parquet for a given season.  Used by the live draft CLI
(``scripts/draft_live.py``) and the web API draft + league routers
(``web/api/routers/draft.py``, ``web/api/routers/sleeper_user.py``) so all
consumers always serve the same Gold artifact with identical column
normalisation and one shared read-cache.

The parquet path is anchored at the repository root (derived from this
file's location), so lookups work regardless of the caller's working
directory — scripts in ``scripts/``, pytest, and the FastAPI app all
resolve the same ``data/gold/projections/preseason`` tree.

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
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

#: Repository root — src/projection_store.py lives one level below it.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Glob template for the preseason partition, anchored at the repo root.
_PRESEASON_PATTERN = os.path.join(
    str(_PROJECT_ROOT),
    "data",
    "gold",
    "projections",
    "preseason",
    "season={season}",
    "*.parquet",
)


@lru_cache(maxsize=8)
def _read_preseason_parquet(path: str) -> pd.DataFrame:
    """Read (and cache) a preseason projection parquet by path.

    The web live-draft endpoint polls every ~5s; without this cache each
    poll would re-read the same Gold artifact from disk.  Keyed on the
    resolved file path, so a newer artifact (new timestamp in the filename)
    naturally busts the cache.

    The ``recent_team`` column is aliased to ``team`` when present so
    downstream functions (player-name matching, roster optimizer, waiver
    ranking) have a consistent ``team`` column regardless of which pipeline
    version produced the file.

    Args:
        path: Absolute path to the parquet file.

    Returns:
        The parsed (and column-normalised) DataFrame.  This is a shared
        cached object — callers must NOT mutate it; copy before writing
        (all current consumers — ``compute_value_scores``,
        ``score_with_settings``, ``DraftBoard`` — already copy).
    """
    df = pd.read_parquet(path)
    # Normalise column name: pipeline older than v4.3 uses recent_team.
    if "recent_team" in df.columns and "team" not in df.columns:
        df = df.rename(columns={"recent_team": "team"})
    return df


def load_latest_preseason(season: int) -> Optional[pd.DataFrame]:
    """Load the newest committed preseason projections parquet for *season*.

    The file is the Gold artifact produced by::

        python scripts/generate_projections.py --preseason --season YYYY

    It is committed to git so it survives pre-season API outages and
    upstream 404s that would break a live ``generate_preseason_projections``
    call.

    Args:
        season: NFL season year (e.g. 2026).

    Returns:
        DataFrame on success; ``None`` when no parquet is found on disk or
        the file cannot be parsed.  The frame is a shared, cached read —
        treat it as read-only and copy before mutating.
    """
    pattern = _PRESEASON_PATTERN.format(season=season)
    files = sorted(glob.glob(pattern))
    if not files:
        logger.debug("No preseason parquet for season=%d: %s", season, pattern)
        return None
    path = files[-1]  # alphabetically last = newest YYYYMMDD_HHMMSS timestamp
    try:
        return _read_preseason_parquet(path)
    except Exception as exc:
        logger.warning("Could not read preseason parquet %s: %s", path, exc)
        return None
