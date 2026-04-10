"""
/api/projections endpoints -- fantasy player projections.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import VALID_POSITIONS, VALID_SCORING_FORMATS
from ..models.schemas import PlayerProjection, ProjectionResponse
from ..services import projection_service

router = APIRouter(prefix="/projections", tags=["projections"])


def _df_to_projection_list(df, scoring_format: str) -> list:
    """Convert a projection DataFrame to a list of PlayerProjection dicts."""
    records = []
    for _, row in df.iterrows():
        records.append(
            PlayerProjection(
                player_id=str(row.get("player_id", "")),
                player_name=str(row.get("player_name", "")),
                team=str(row.get("team", "")),
                position=str(row.get("position", "")),
                projected_points=float(row.get("projected_points", 0)),
                projected_floor=float(row.get("projected_floor", 0)),
                projected_ceiling=float(row.get("projected_ceiling", 0)),
                proj_pass_yards=_safe_float(row.get("proj_pass_yards")),
                proj_pass_tds=_safe_float(row.get("proj_pass_tds")),
                proj_rush_yards=_safe_float(row.get("proj_rush_yards")),
                proj_rush_tds=_safe_float(row.get("proj_rush_tds")),
                proj_rec=_safe_float(row.get("proj_rec")),
                proj_rec_yards=_safe_float(row.get("proj_rec_yards")),
                proj_rec_tds=_safe_float(row.get("proj_rec_tds")),
                proj_fg_makes=_safe_float(row.get("proj_fg_makes")),
                proj_xp_makes=_safe_float(row.get("proj_xp_makes")),
                scoring_format=scoring_format,
                season=_safe_int(row.get("season", 0)) or 0,
                week=_safe_int(row.get("week", 0)) or 0,
                position_rank=_safe_int(row.get("position_rank")),
                injury_status=_safe_str(row.get("injury_status")),
            )
        )
    return records


def _safe_float(val) -> Optional[float]:
    """Convert to float, returning None for NaN / missing."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:
            return None
        return int(f)
    except (ValueError, TypeError):
        return None


def _safe_str(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val)
    if s.lower() in ("nan", "none", ""):
        return None
    return s


@router.get("", response_model=ProjectionResponse)
def list_projections(
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=18, description="Week number"),
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
    position: Optional[str] = Query(None, description="QB / RB / WR / TE / K"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    limit: int = Query(200, ge=1, le=1000, description="Max results"),
) -> ProjectionResponse:
    """Return player projections for the given season, week, and scoring format."""
    if scoring not in VALID_SCORING_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scoring format. Choose from: {sorted(VALID_SCORING_FORMATS)}",
        )
    if position and position.upper() not in VALID_POSITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid position. Choose from: {sorted(VALID_POSITIONS)}",
        )

    try:
        df = projection_service.get_projections(
            season=season,
            week=week,
            scoring_format=scoring,
            position=position,
            team=team,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    projections = _df_to_projection_list(df, scoring)
    return ProjectionResponse(
        season=season,
        week=week,
        scoring_format=scoring,
        projections=projections,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/top", response_model=ProjectionResponse)
def top_projections(
    season: int = Query(..., ge=1999, le=2030),
    week: int = Query(..., ge=1, le=18),
    scoring: str = Query("half_ppr"),
    position: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> ProjectionResponse:
    """Convenience endpoint: top N projected players (shorthand for limit)."""
    return list_projections(
        season=season,
        week=week,
        scoring=scoring,
        position=position,
        team=None,
        limit=limit,
    )
