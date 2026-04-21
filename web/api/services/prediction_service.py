"""
Service layer for reading game predictions.

Supports two data backends:
  1. PostgreSQL -- when DATABASE_URL is set (production)
  2. Parquet    -- local file reads (development fallback)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from ..config import GOLD_PREDICTIONS_DIR
from ..db import get_connection, is_db_enabled

logger = logging.getLogger(__name__)


@dataclass
class PredictionMetaInfo:
    """Metadata for the latest-available predictions slice.

    Analogous to ``projection_service.ProjectionMetaInfo``. Used by graceful
    defaulting in ``/api/predictions`` when the caller omits ``season``/``week``.
    """

    season: int
    week: Optional[int]
    data_as_of: Optional[str]
    source_path: Optional[str]


def _iso_utc(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Parquet helpers (development fallback)
# ---------------------------------------------------------------------------


def _latest_parquet(directory: Path) -> Optional[Path]:
    """Return the most-recently modified Parquet file in *directory*."""
    parquets = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    return parquets[-1] if parquets else None


def _get_predictions_parquet(season: int, week: int) -> pd.DataFrame:
    """Read predictions from local Parquet files."""
    # Try both unpadded (week=1) and zero-padded (week=01) directory names
    week_dir = GOLD_PREDICTIONS_DIR / f"season={season}" / f"week={week}"
    if not week_dir.exists():
        week_dir = GOLD_PREDICTIONS_DIR / f"season={season}" / f"week={week:02d}"
    if not week_dir.exists():
        raise FileNotFoundError(f"No prediction data for season={season} week={week}")

    parquet_path = _latest_parquet(week_dir)
    if parquet_path is None:
        raise FileNotFoundError(f"No parquet files in {week_dir}")

    logger.info("Reading predictions from %s", parquet_path)
    return pd.read_parquet(parquet_path)


def _get_prediction_by_game_parquet(
    season: int, week: int, game_id: str
) -> Optional[pd.Series]:
    """Return a single game prediction from Parquet, or None."""
    df = _get_predictions_parquet(season, week)
    if "game_id" not in df.columns:
        return None
    match = df[df["game_id"] == game_id]
    if match.empty:
        return None
    return match.iloc[0]


# ---------------------------------------------------------------------------
# PostgreSQL helpers (production)
# ---------------------------------------------------------------------------


def _get_predictions_db(season: int, week: int) -> pd.DataFrame:
    """Read predictions from PostgreSQL."""
    sql = (
        "SELECT * FROM predictions "
        "WHERE season = %s AND week = %s "
        "ORDER BY game_id"
    )
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=[season, week])


def _get_prediction_by_game_db(
    season: int, week: int, game_id: str
) -> Optional[pd.Series]:
    """Return a single game prediction from PostgreSQL, or None."""
    sql = (
        "SELECT * FROM predictions "
        "WHERE season = %s AND week = %s AND game_id = %s "
        "LIMIT 1"
    )
    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=[season, week, game_id])
    if df.empty:
        return None
    return df.iloc[0]


# ---------------------------------------------------------------------------
# Public API (auto-selects backend)
# ---------------------------------------------------------------------------


def get_predictions(season: int, week: int) -> pd.DataFrame:
    """Load cached game predictions for a given season/week.

    Tries PostgreSQL when DATABASE_URL is set; falls back to Parquet on any
    DB error (covers bad credentials, network failures, or stale pool state
    across worker processes).

    Args:
        season: NFL season year.
        week: Week number (1-18).

    Returns:
        DataFrame with prediction data.

    Raises:
        FileNotFoundError: If no prediction data exists.
    """
    if is_db_enabled():
        try:
            logger.debug("Using PostgreSQL backend for predictions")
            return _get_predictions_db(season, week)
        except Exception as exc:
            logger.warning(
                "PostgreSQL read failed (%s); falling back to Parquet", exc
            )
    logger.debug("Using Parquet backend for predictions")
    return _get_predictions_parquet(season, week)


def get_prediction_by_game(
    season: int,
    week: int,
    game_id: str,
) -> Optional[pd.Series]:
    """Return a single game prediction row, or None if not found.

    Tries PostgreSQL first; falls back to Parquet on any DB error.

    Args:
        season: NFL season year.
        week: Week number.
        game_id: Unique game identifier.

    Returns:
        Series for the matching game, or None.
    """
    if is_db_enabled():
        try:
            return _get_prediction_by_game_db(season, week, game_id)
        except Exception as exc:
            logger.warning(
                "PostgreSQL game lookup failed (%s); falling back to Parquet", exc
            )
    return _get_prediction_by_game_parquet(season, week, game_id)


# ---------------------------------------------------------------------------
# Latest-week resolution (graceful defaulting — phase 66 / v7.0)
# ---------------------------------------------------------------------------


def get_latest_week(season: Optional[int] = None) -> PredictionMetaInfo:
    """Return the latest (season, week) in the Gold predictions layer.

    When ``season`` is None, scans all season directories and returns the
    highest (season, week) pair with at least one parquet file. When
    ``season`` is supplied, scans only that season.

    Returns ``week=None`` (and other fields None) when no prediction data
    exists. Never raises — callers receive a typed response even in the
    offseason or on a fresh install.
    """
    if not GOLD_PREDICTIONS_DIR.exists():
        return PredictionMetaInfo(
            season=season or 0, week=None, data_as_of=None, source_path=None
        )

    if season is not None:
        season_dirs = [GOLD_PREDICTIONS_DIR / f"season={season}"]
    else:
        season_dirs = sorted(
            GOLD_PREDICTIONS_DIR.glob("season=*"),
            key=lambda p: int(p.name.split("=", 1)[1]) if "=" in p.name else 0,
            reverse=True,
        )

    best: Optional[PredictionMetaInfo] = None
    for season_dir in season_dirs:
        if not season_dir.exists():
            continue
        try:
            season_num = int(season_dir.name.split("=", 1)[1])
        except (IndexError, ValueError):
            continue

        for week_dir in season_dir.glob("week=*"):
            try:
                week_num = int(week_dir.name.split("=", 1)[1])
            except (IndexError, ValueError):
                continue
            parquet_path = _latest_parquet(week_dir)
            if parquet_path is None:
                continue
            try:
                mtime = parquet_path.stat().st_mtime
            except OSError:
                continue

            candidate = PredictionMetaInfo(
                season=season_num,
                week=week_num,
                data_as_of=_iso_utc(mtime),
                source_path=_project_relative(parquet_path),
            )
            if best is None or (candidate.season, candidate.week or 0) > (
                best.season,
                best.week or 0,
            ):
                best = candidate

        if best is not None and season is not None:
            # When a season was explicitly requested, stop after scanning it.
            break

    if best is None:
        return PredictionMetaInfo(
            season=season or 0, week=None, data_as_of=None, source_path=None
        )
    return best
