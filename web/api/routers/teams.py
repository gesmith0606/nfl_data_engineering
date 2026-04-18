"""
/api/teams endpoints — schedule-aware current week + real-roster lookups.

Implements MTCH-02 (defensive rosters with real NFL data), MTCH-04 (schedule-aware
current week), and the OL portion of MTCH-01 (offense roster with depth chart).

See ``.planning/phases/64-matchup-view-completion/API-CONTRACT.md`` for the
authoritative response shapes.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import CurrentWeekResponse, TeamRosterResponse
from ..services import team_roster_service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/current-week", response_model=CurrentWeekResponse)
def current_week() -> CurrentWeekResponse:
    """Return the current NFL (season, week) pair from today's calendar date.

    ``source == "schedule"`` when today falls inside a real gameday window,
    ``source == "fallback"`` during the offseason or when data lag prevents a
    match (returns max (season, week) from the latest schedule parquet).
    """
    try:
        return team_roster_service.get_current_week()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/{team}/roster", response_model=TeamRosterResponse)
def team_roster(
    team: str,
    season: int = Query(..., ge=2016, le=2030, description="NFL season"),
    week: int = Query(
        ..., ge=1, le=22, description="Week number (1-22 incl. postseason)"
    ),
    side: Literal["offense", "defense", "all"] = Query(
        "all", description="Roster side to return"
    ),
) -> TeamRosterResponse:
    """Return the roster for a team-week with snap-pct joins and slot hints.

    Falls back to the most recent available season when the requested season's
    roster parquet is absent (flagged via ``fallback`` / ``fallback_season``).
    """
    try:
        return team_roster_service.load_team_roster(team, season, week, side)
    except ValueError as exc:
        # Unknown team code -> 404 (distinct from 422 validation)
        raise HTTPException(status_code=404, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
