"""
/api/games endpoints -- historical game archive with player fantasy stats.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import VALID_POSITIONS, VALID_SCORING_FORMATS
from ..models.schemas import (
    AvailableSeason,
    GameDetail,
    GameDetailResponse,
    GameListResponse,
    GamePlayerStat,
    GameResult,
    PlayerGameLogEntry,
    PlayerGameLogResponse,
    SeasonLeader,
    SeasonLeadersResponse,
    SeasonsResponse,
)
from ..services import game_service

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/seasons", response_model=SeasonsResponse)
def list_seasons() -> SeasonsResponse:
    """List all available seasons with game counts."""
    seasons = game_service.available_seasons()
    return SeasonsResponse(
        seasons=[AvailableSeason(**s) for s in seasons],
    )


@router.get("/leaders", response_model=SeasonLeadersResponse)
def season_leaders(
    season: int = Query(..., ge=2016, le=2030, description="NFL season"),
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
    position: Optional[str] = Query(None, description="QB / RB / WR / TE"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
) -> SeasonLeadersResponse:
    """Get season-long fantasy point leaders."""
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
        leaders = game_service.season_leaders(season, scoring, position, limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return SeasonLeadersResponse(
        season=season,
        scoring_format=scoring,
        position=position,
        leaders=[SeasonLeader(**r) for r in leaders],
    )


@router.get("/player-log/{player_id}", response_model=PlayerGameLogResponse)
def player_game_log(
    player_id: str,
    season: int = Query(..., ge=2016, le=2030, description="NFL season"),
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
) -> PlayerGameLogResponse:
    """Get a player's full game log for a season."""
    if scoring not in VALID_SCORING_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scoring format. Choose from: {sorted(VALID_SCORING_FORMATS)}",
        )

    try:
        log = game_service.player_game_log(player_id, season, scoring)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return PlayerGameLogResponse(
        player_id=player_id,
        season=season,
        scoring_format=scoring,
        game_log=[PlayerGameLogEntry(**entry) for entry in log],
    )


@router.get("/{game_id}", response_model=GameDetailResponse)
def game_detail(
    game_id: str,
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=18, description="Week number"),
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
) -> GameDetailResponse:
    """Get full game detail with both teams' player fantasy stats."""
    if scoring not in VALID_SCORING_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scoring format. Choose from: {sorted(VALID_SCORING_FORMATS)}",
        )

    try:
        detail = game_service.game_detail(season, week, game_id, scoring)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    game_info = GameResult(**detail["game_info"])
    home_players = [GamePlayerStat(**p) for p in detail["home_players"]]
    away_players = [GamePlayerStat(**p) for p in detail["away_players"]]
    top_performers = [GamePlayerStat(**p) for p in detail["top_performers"]]

    return GameDetailResponse(
        game=GameDetail(
            game_info=game_info,
            home_players=home_players,
            away_players=away_players,
            top_performers=top_performers,
        ),
        scoring_format=scoring,
    )


@router.get("", response_model=GameListResponse)
def list_games(
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: Optional[int] = Query(None, ge=1, le=18, description="Week number"),
) -> GameListResponse:
    """List game results for a season (optionally filtered by week)."""
    try:
        games = game_service.list_games(season, week)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return GameListResponse(
        season=season,
        week=week,
        games=[GameResult(**g) for g in games],
        count=len(games),
    )
