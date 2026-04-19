"""
/api/players endpoints -- search and player detail.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import VALID_SCORING_FORMATS
from ..models.schemas import PlayerProjection, PlayerSearchResult
from ..services import projection_service

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/search", response_model=List[PlayerSearchResult])
def search_players(
    q: str = Query(..., min_length=2, description="Player name search query"),
    season: int = Query(2024, ge=1999, le=2030),
    week: int = Query(17, ge=1, le=18),
) -> List[PlayerSearchResult]:
    """Search for players by name (case-insensitive partial match)."""
    try:
        df = projection_service.search_players(query=q, season=season, week=week)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return [
        PlayerSearchResult(
            player_id=str(row["player_id"]),
            player_name=str(row["player_name"]),
            team=str(row["team"]),
            position=str(row["position"]),
        )
        for _, row in df.iterrows()
    ]


@router.get("/{player_id}", response_model=PlayerProjection)
def get_player_detail(
    player_id: str,
    season: int = Query(2024, ge=1999, le=2030),
    week: int = Query(17, ge=1, le=18),
    scoring: str = Query("half_ppr"),
) -> PlayerProjection:
    """Return detailed projection for a single player."""
    if scoring not in VALID_SCORING_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scoring format. Choose from: {sorted(VALID_SCORING_FORMATS)}",
        )

    try:
        df = projection_service.get_projections(
            season=season, week=week, scoring_format=scoring, limit=1000
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    match = df[df["player_id"] == player_id]
    if match.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Player {player_id} not found in season={season} week={week}",
        )

    row = match.iloc[0]

    def _scalar(val):
        """Coerce pandas Series (from duplicate column names) to its first element."""
        if hasattr(val, "iloc") and not hasattr(val, "lower"):
            return val.iloc[0] if len(val) > 0 else None
        return val

    def _sf(val) -> Optional[float]:
        val = _scalar(val)
        if val is None:
            return None
        try:
            f = float(val)
            return None if f != f else f
        except (ValueError, TypeError):
            return None

    def _ss(val) -> Optional[str]:
        val = _scalar(val)
        if val is None:
            return None
        s = str(val)
        return None if s.lower() in ("nan", "none", "") else s

    def _si(val, default: int = 0) -> int:
        v = _scalar(val)
        if v is None:
            return default
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    def _sstr(val, default: str = "") -> str:
        v = _scalar(val)
        return default if v is None else str(v)

    return PlayerProjection(
        player_id=_sstr(row.get("player_id")),
        player_name=_sstr(row.get("player_name")),
        team=_sstr(row.get("team")),
        position=_sstr(row.get("position")),
        projected_points=_sf(row.get("projected_points")) or 0.0,
        projected_floor=_sf(row.get("projected_floor")) or 0.0,
        projected_ceiling=_sf(row.get("projected_ceiling")) or 0.0,
        proj_pass_yards=_sf(row.get("proj_pass_yards")),
        proj_pass_tds=_sf(row.get("proj_pass_tds")),
        proj_rush_yards=_sf(row.get("proj_rush_yards")),
        proj_rush_tds=_sf(row.get("proj_rush_tds")),
        proj_rec=_sf(row.get("proj_rec")),
        proj_rec_yards=_sf(row.get("proj_rec_yards")),
        proj_rec_tds=_sf(row.get("proj_rec_tds")),
        proj_fg_makes=_sf(row.get("proj_fg_makes")),
        proj_xp_makes=_sf(row.get("proj_xp_makes")),
        scoring_format=scoring,
        season=season,
        week=week,
        position_rank=(
            _si(row.get("position_rank"))
            if _scalar(row.get("position_rank")) is not None
            else None
        ),
        injury_status=_ss(row.get("injury_status")),
    )
