"""
Service layer for reading and filtering player projections.

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

from ..config import GOLD_PROJECTIONS_DIR
from ..db import get_connection, is_db_enabled

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectionMetaInfo:
    """Upstream metadata for a projection read.

    ``data_as_of`` is the ISO 8601 UTC mtime of the most recent parquet for
    the requested ``(season, week)``. ``source_path`` is the project-relative
    path to that parquet. Both are ``None`` when the PostgreSQL backend
    served the query (no filesystem origin).
    """

    season: int
    week: int
    data_as_of: Optional[str]
    source_path: Optional[str]


# ---------------------------------------------------------------------------
# Parquet helpers (development fallback)
# ---------------------------------------------------------------------------


def _latest_parquet(directory: Path) -> Optional[Path]:
    """Return the most-recently modified Parquet file in *directory*."""
    parquets = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    return parquets[-1] if parquets else None


def _project_relative(path: Path) -> str:
    """Return *path* relative to the project root when possible, else absolute."""
    try:
        root = GOLD_PROJECTIONS_DIR.resolve().parents[1].parent  # .../<project>/
        return str(path.resolve().relative_to(root))
    except (ValueError, IndexError):
        return str(path)


def _iso_utc(mtime: float) -> str:
    """Convert a POSIX mtime to an ISO 8601 UTC timestamp."""
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def get_projection_meta(season: int, week: int) -> ProjectionMetaInfo:
    """Return source-parquet metadata for a given season/week.

    Never raises: when no data exists, returns a ``ProjectionMetaInfo`` with
    ``data_as_of=None`` and ``source_path=None`` so the caller can still echo
    the requested slice in the response envelope.
    """
    if is_db_enabled():
        # Postgres backend — no filesystem origin.
        return ProjectionMetaInfo(
            season=season, week=week, data_as_of=None, source_path=None
        )

    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    if not week_dir.exists():
        return ProjectionMetaInfo(
            season=season, week=week, data_as_of=None, source_path=None
        )

    parquet_path = _latest_parquet(week_dir)
    if parquet_path is None:
        return ProjectionMetaInfo(
            season=season, week=week, data_as_of=None, source_path=None
        )

    mtime = parquet_path.stat().st_mtime
    return ProjectionMetaInfo(
        season=season,
        week=week,
        data_as_of=_iso_utc(mtime),
        source_path=_project_relative(parquet_path),
    )


def get_latest_week(season: int) -> ProjectionMetaInfo:
    """Scan ``data/gold/projections/season=<season>/week=*/`` and return the
    highest week number that has at least one parquet file.

    Returns ``ProjectionMetaInfo(week=None, data_as_of=None, source_path=None)``
    when no data exists for the requested season. Never raises — callers
    always receive a typed response even during the offseason.
    """
    season_dir = GOLD_PROJECTIONS_DIR / f"season={season}"
    if not season_dir.exists():
        return ProjectionMetaInfo(
            season=season, week=None, data_as_of=None, source_path=None  # type: ignore[arg-type]
        )

    best_week: Optional[int] = None
    best_path: Optional[Path] = None
    best_mtime: float = -1.0
    for week_dir in season_dir.glob("week=*"):
        try:
            week_num = int(week_dir.name.split("=", 1)[1])
        except (IndexError, ValueError):
            continue
        parquet_path = _latest_parquet(week_dir)
        if parquet_path is None:
            continue
        if best_week is None or week_num > best_week:
            best_week = week_num
            best_path = parquet_path
            best_mtime = parquet_path.stat().st_mtime

    if best_week is None or best_path is None:
        return ProjectionMetaInfo(
            season=season, week=None, data_as_of=None, source_path=None  # type: ignore[arg-type]
        )

    return ProjectionMetaInfo(
        season=season,
        week=best_week,
        data_as_of=_iso_utc(best_mtime),
        source_path=_project_relative(best_path),
    )


def _get_projections_parquet(
    season: int,
    week: int,
    scoring_format: str,
    position: Optional[str] = None,
    team: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Read projections from local Parquet files."""
    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    if not week_dir.exists():
        raise FileNotFoundError(f"No projection data for season={season} week={week}")

    parquet_path = _latest_parquet(week_dir)
    if parquet_path is None:
        raise FileNotFoundError(f"No parquet files in {week_dir}")

    logger.info("Reading projections from %s", parquet_path)
    df = pd.read_parquet(parquet_path)

    rename_map = {
        "recent_team": "team",
        # Parquet stat columns are unprefixed; map to the proj_ names the router expects
        "passing_yards": "proj_pass_yards",
        "passing_tds": "proj_pass_tds",
        "rushing_yards": "proj_rush_yards",
        "rushing_tds": "proj_rush_tds",
        "receptions": "proj_rec",
        "receiving_yards": "proj_rec_yards",
        "receiving_tds": "proj_rec_tds",
        "interceptions": "proj_interceptions",
        "targets": "proj_targets",
        "carries": "proj_carries",
        # Preseason uses projected_season_points; normalize to projected_points
        "projected_season_points": "projected_points",
        "proj_season": "season",
        "proj_week": "week",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["scoring_format"] = scoring_format

    if position:
        df = df[df["position"].str.upper() == position.upper()]
    if team:
        df = df[df["team"].str.upper() == team.upper()]

    df = df.sort_values("projected_points", ascending=False).head(limit)
    return df


def _search_players_parquet(
    query: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Search players from local Parquet files."""
    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    if not week_dir.exists():
        raise FileNotFoundError(f"No projection data for season={season} week={week}")

    parquet_path = _latest_parquet(week_dir)
    if parquet_path is None:
        raise FileNotFoundError(f"No parquet files in {week_dir}")

    df = pd.read_parquet(parquet_path)
    df = df.rename(columns={"recent_team": "team"})

    mask = df["player_name"].str.lower().str.contains(query.lower(), na=False)
    results = df.loc[mask, ["player_id", "player_name", "team", "position"]]
    return results.drop_duplicates().head(50)


# ---------------------------------------------------------------------------
# PostgreSQL helpers (production)
# ---------------------------------------------------------------------------


def _get_projections_db(
    season: int,
    week: int,
    scoring_format: str,
    position: Optional[str] = None,
    team: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Read projections from PostgreSQL."""
    conditions = [
        "season = %s",
        "week = %s",
        "scoring_format = %s",
    ]
    params: list = [season, week, scoring_format]

    if position:
        conditions.append("UPPER(position) = UPPER(%s)")
        params.append(position)
    if team:
        conditions.append("UPPER(team) = UPPER(%s)")
        params.append(team)

    where = " AND ".join(conditions)
    params.append(limit)

    sql = (
        f"SELECT * FROM projections WHERE {where} "
        f"ORDER BY projected_points DESC LIMIT %s"
    )

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    return df


def _search_players_db(
    query: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Search players from PostgreSQL."""
    sql = (
        "SELECT DISTINCT player_id, player_name, team, position "
        "FROM projections "
        "WHERE season = %s AND week = %s "
        "  AND LOWER(player_name) LIKE LOWER(%s) "
        "LIMIT 50"
    )
    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=[season, week, f"%{query}%"])
    return df


# ---------------------------------------------------------------------------
# Public API (auto-selects backend)
# ---------------------------------------------------------------------------


def get_projections(
    season: int,
    week: int,
    scoring_format: str,
    position: Optional[str] = None,
    team: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Load cached projections and return a filtered DataFrame.

    Tries PostgreSQL when DATABASE_URL is set; falls back to Parquet on any
    DB error (covers bad credentials, network failures, or stale pool state
    across worker processes).

    Args:
        season: NFL season year.
        week: Week number (1-18).
        scoring_format: One of ppr / half_ppr / standard.
        position: Optional position filter (QB/RB/WR/TE/K).
        team: Optional team abbreviation filter.
        limit: Maximum rows to return (default 200).

    Returns:
        DataFrame with projection data, sorted by projected_points desc.

    Raises:
        FileNotFoundError: If no data exists for the given season/week.
    """
    if is_db_enabled():
        try:
            logger.debug("Using PostgreSQL backend for projections")
            return _get_projections_db(
                season, week, scoring_format, position, team, limit
            )
        except Exception as exc:
            logger.warning("PostgreSQL read failed (%s); falling back to Parquet", exc)
    logger.debug("Using Parquet backend for projections")
    return _get_projections_parquet(season, week, scoring_format, position, team, limit)


def search_players(
    query: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Search for players whose name matches *query* (case-insensitive).

    Tries PostgreSQL first; falls back to Parquet on any DB error.

    Args:
        query: Partial player name to search for.
        season: NFL season year.
        week: Week number.

    Returns:
        DataFrame of matching players (player_id, player_name, team, position).

    Raises:
        FileNotFoundError: If no data exists.
    """
    if is_db_enabled():
        try:
            return _search_players_db(query, season, week)
        except Exception as exc:
            logger.warning(
                "PostgreSQL search failed (%s); falling back to Parquet", exc
            )
    return _search_players_parquet(query, season, week)
