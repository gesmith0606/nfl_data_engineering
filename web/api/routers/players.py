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

    def _sf(val) -> Optional[float]:
        if val is None:
            return None
        try:
            f = float(val)
            return None if f != f else f
        except (ValueError, TypeError):
            return None

    def _ss(val) -> Optional[str]:
        if val is None:
            return None
        s = str(val)
        return None if s.lower() in ("nan", "none", "") else s

    return PlayerProjection(
        player_id=str(row.get("player_id", "")),
        player_name=str(row.get("player_name", "")),
        team=str(row.get("team", "")),
        position=str(row.get("position", "")),
        projected_points=float(row.get("projected_points", 0)),
        projected_floor=float(row.get("projected_floor", 0)),
        projected_ceiling=float(row.get("projected_ceiling", 0)),
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
        season=int(row.get("season", 0)),
        week=int(row.get("week", 0)),
        position_rank=(
            int(row.get("position_rank", 0))
            if row.get("position_rank") is not None
            else None
        ),
        injury_status=_ss(row.get("injury_status")),
    )
