"""
/api/players endpoints -- search and player detail.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..config import VALID_SCORING_FORMATS
from ..models.schemas import (
    PlayerCorrelation,
    PlayerCorrelationsResponse,
    PlayerProjection,
    PlayerSearchResult,
)
from ..services import projection_service

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/{player_id}/correlations", response_model=PlayerCorrelationsResponse)
def get_player_correlations(
    player_id: str,
    min_rho: float = Query(
        0.1, ge=0.0, le=1.0, description="Minimum |rho| for an edge to be returned"
    ),
    limit: int = Query(20, ge=1, le=100),
) -> PlayerCorrelationsResponse:
    """Stability-gated correlation edges for one player (UC3).

    Edges come from the Gold correlations parquet built by
    ``scripts/build_correlations.py``. Positive rho = the pair's big games
    coincide (stack); negative = they trade off. Returns an empty list
    (HTTP 200) when no correlation data has been built — the surface is
    additive and must not break player pages.
    """
    logger = logging.getLogger(__name__)

    # Guarded like lineups.py: any import/load failure serves an empty
    # list instead of a 500 — this surface must never break player pages.
    try:
        from graph_correlation import load_latest_correlations

        edges = load_latest_correlations()
    except Exception:
        logger.exception("Correlation edges unavailable — serving empty list")
        edges = pd.DataFrame()

    correlations = []
    if not edges.empty:
        pairs = edges[edges["level"] == "pair"]
        mine = pairs[
            ((pairs["player_id_a"] == player_id) | (pairs["player_id_b"] == player_id))
            & (pairs["rho"].abs() >= min_rho)
        ].copy()
        mine["abs_rho"] = mine["rho"].abs()
        mine = mine.sort_values("abs_rho", ascending=False).head(limit)
        for _, row in mine.iterrows():
            is_a = row["player_id_a"] == player_id
            correlations.append(
                PlayerCorrelation(
                    other_player_id=str(
                        row["player_id_b"] if is_a else row["player_id_a"]
                    ),
                    other_player_name=str(
                        row["player_name_b"] if is_a else row["player_name_a"]
                    ),
                    relation=str(row["relation"]),
                    rho=float(row["rho"]),
                    n_games=int(row["n_games"]),
                )
            )

    return PlayerCorrelationsResponse(
        player_id=player_id,
        correlations=correlations,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


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
        import pandas as _pd

        if isinstance(val, _pd.Series):
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
