"""
/api/news endpoints -- player news items and sentiment alerts.

Reads from the Gold/Silver/Bronze sentiment data layers written by the
Phases S1-S3 ingestion and processing pipeline. All endpoints return
empty results gracefully when no sentiment data has been ingested yet.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import Alert, NewsItem, PlayerSentiment
from ..services import news_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/player/{player_id}", response_model=List[NewsItem])
def get_player_news(
    player_id: str,
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=18, description="Week number"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
) -> List[NewsItem]:
    """Return recent news items for a specific player.

    Reads Silver signal records filtered to the requested player.
    Returns an empty list when no news has been ingested yet — this is
    the expected state before the sentiment pipeline has run.

    Args:
        player_id: Canonical player ID (e.g. ``"00-0023459"``).
        season: NFL season year.
        week: NFL week number (1-18).
        limit: Maximum number of news items to return (1-50).

    Returns:
        List of :class:`NewsItem` objects ordered newest first.
    """
    try:
        items = news_service.get_player_news(
            player_id=player_id,
            season=season,
            week=week,
            limit=limit,
        )
    except Exception as exc:
        logger.error(
            "Error fetching news for player=%s season=%d week=%d: %s",
            player_id,
            season,
            week,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to load player news")

    return [NewsItem(**item) for item in items]


@router.get("/alerts", response_model=List[Alert])
def get_active_alerts(
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=18, description="Week number"),
) -> List[Alert]:
    """Return all active alerts for the current week.

    Alerts are triggered when a player is ruled out, inactive, questionable,
    suspended, or has a major positive/negative sentiment shift (multiplier
    outside the 0.85–1.10 neutral band).

    Returns an empty list when Gold sentiment data has not yet been generated.

    Args:
        season: NFL season year.
        week: NFL week number (1-18).

    Returns:
        List of :class:`Alert` objects ordered by severity (ruled_out first).
    """
    try:
        alerts = news_service.get_active_alerts(season=season, week=week)
    except Exception as exc:
        logger.error(
            "Error fetching alerts for season=%d week=%d: %s", season, week, exc
        )
        raise HTTPException(status_code=500, detail="Failed to load alerts")

    return [Alert(**alert) for alert in alerts]


@router.get("/sentiment/{player_id}", response_model=PlayerSentiment)
def get_player_sentiment(
    player_id: str,
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=18, description="Week number"),
) -> PlayerSentiment:
    """Return aggregated weekly sentiment for a single player.

    Reads the Gold sentiment Parquet for the requested season/week and
    returns the pre-computed multiplier and event flags for *player_id*.

    Args:
        player_id: Canonical player ID.
        season: NFL season year.
        week: NFL week number (1-18).

    Returns:
        :class:`PlayerSentiment` with multiplier, doc count, and event flags.

    Raises:
        HTTPException 404: When no Gold sentiment data exists for this player.
    """
    try:
        data = news_service.get_player_sentiment(
            player_id=player_id,
            season=season,
            week=week,
        )
    except Exception as exc:
        logger.error(
            "Error fetching sentiment for player=%s season=%d week=%d: %s",
            player_id,
            season,
            week,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to load player sentiment")

    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No sentiment data for player={player_id} season={season} week={week}",
        )

    return PlayerSentiment(**data)
