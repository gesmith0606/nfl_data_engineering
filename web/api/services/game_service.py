"""
Service layer for the Game Archive API.

Wraps ``src/game_archive`` functions and converts DataFrames to dicts
suitable for Pydantic response models.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# src/ is importable via the web.api package bootstrap (web/api/__init__.py)
from game_archive import (
    get_available_seasons,
    get_game_detail,
    get_game_player_stats,
    get_game_results,
    get_player_game_log,
    get_season_leaders,
)

from ..db import get_connection, is_db_enabled

logger = logging.getLogger(__name__)


def _nan_to_none(val):
    """Convert NaN/NaT to None for JSON serialisation."""
    if val is None:
        return None
    try:
        if val != val:  # NaN check
            return None
    except (TypeError, ValueError):
        pass
    return val


def _clean_dict(d: Dict) -> Dict:
    """Replace NaN values with None in a dict."""
    return {k: _nan_to_none(v) for k, v in d.items()}


def _get_game_results_db(season: int, week: Optional[int] = None) -> pd.DataFrame:
    """Read game results from PostgreSQL.

    No ``games`` table exists yet in scripts/sync_gold_to_db.py (only
    ``projections``/``predictions`` are synced there today) -- this mirrors
    the DB-first-with-Parquet-fallback convention used by
    projection_service.py / prediction_service.py so game_service is ready
    the moment one ships, and so a ``games`` table that's reachable but not
    yet backfilled for a season degrades to Parquet instead of a false
    "not found".
    """
    conditions = ["season = %s"]
    params: list = [season]
    if week is not None:
        conditions.append("week = %s")
        params.append(week)
    where = " AND ".join(conditions)
    sql = f"SELECT * FROM games WHERE {where} ORDER BY week, game_id"
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def list_games(season: int, week: Optional[int] = None) -> Tuple[List[Dict], str]:
    """Return game results as a list of dicts, plus a data-source label.

    Tries PostgreSQL when DATABASE_URL is set; falls back to Parquet on any
    DB error AND when the DB query succeeds but returns zero rows -- the
    latter covers a ``games`` table that exists but hasn't been backfilled
    for the requested season/week, which would otherwise silently serve an
    empty/wrong result instead of the Parquet data that actually has it.

    Returns:
        Tuple of (records, source) where source is one of "postgres",
        "parquet" (DB never attempted), or "parquet_fallback" (DB attempted
        but errored or was empty).
    """
    df: Optional[pd.DataFrame] = None
    source = "parquet"

    if is_db_enabled():
        try:
            logger.debug("Using PostgreSQL backend for game results")
            db_df = _get_game_results_db(season, week)
            if not db_df.empty:
                df = db_df
                source = "postgres"
            else:
                logger.info(
                    "PostgreSQL returned no rows for season=%s week=%s; "
                    "falling back to Parquet",
                    season,
                    week,
                )
                source = "parquet_fallback"
        except Exception as exc:
            logger.warning(
                "PostgreSQL read failed (%s); falling back to Parquet", exc
            )
            source = "parquet_fallback"

    if df is None:
        logger.debug("Using Parquet backend for game results")
        df = get_game_results(season, week)

    records = [_clean_dict(row.to_dict()) for _, row in df.iterrows()]
    return records, source


def game_detail(
    season: int,
    week: int,
    game_id: str,
    scoring_format: str = "half_ppr",
) -> Dict:
    """Return full game detail as a dict tree."""
    detail = get_game_detail(season, week, game_id, scoring_format)
    detail["game_info"] = _clean_dict(detail["game_info"])
    detail["home_players"] = [_clean_dict(p) for p in detail["home_players"]]
    detail["away_players"] = [_clean_dict(p) for p in detail["away_players"]]
    detail["top_performers"] = [_clean_dict(p) for p in detail["top_performers"]]
    return detail


def season_leaders(
    season: int,
    scoring_format: str = "half_ppr",
    position: Optional[str] = None,
    limit: int = 50,
) -> List[Dict]:
    """Return season leaders as a list of dicts."""
    df = get_season_leaders(season, scoring_format, position, limit)
    records = []
    for _, row in df.iterrows():
        records.append(_clean_dict(row.to_dict()))
    return records


def player_game_log(
    player_id: str,
    season: int,
    scoring_format: str = "half_ppr",
) -> List[Dict]:
    """Return a player's game log as a list of dicts."""
    df = get_player_game_log(player_id, season, scoring_format)
    records = []
    for _, row in df.iterrows():
        records.append(_clean_dict(row.to_dict()))
    return records


def available_seasons() -> List[Dict]:
    """Return list of available seasons."""
    return get_available_seasons()
