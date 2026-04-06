"""
Service layer for the Game Archive API.

Wraps ``src/game_archive`` functions and converts DataFrames to dicts
suitable for Pydantic response models.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# Ensure project src/ is importable
_SRC = str(Path(__file__).resolve().parent.parent.parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from game_archive import (
    get_available_seasons,
    get_game_detail,
    get_game_player_stats,
    get_game_results,
    get_player_game_log,
    get_season_leaders,
)

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


def list_games(season: int, week: Optional[int] = None) -> List[Dict]:
    """Return game results as a list of dicts."""
    df = get_game_results(season, week)
    records = []
    for _, row in df.iterrows():
        records.append(_clean_dict(row.to_dict()))
    return records


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
