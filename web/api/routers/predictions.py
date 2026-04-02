"""
/api/predictions endpoints -- game spread / total predictions.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import GamePrediction, PredictionResponse
from ..services import prediction_service

router = APIRouter(prefix="/predictions", tags=["predictions"])


def _row_to_prediction(row) -> GamePrediction:
    """Convert a DataFrame row/Series to a GamePrediction."""

    def _sf(val) -> Optional[float]:
        if val is None:
            return None
        try:
            f = float(val)
            return None if f != f else f
        except (ValueError, TypeError):
            return None

    return GamePrediction(
        game_id=str(row.get("game_id", "")),
        season=int(row.get("season", 0)),
        week=int(row.get("week", 0)),
        home_team=str(row.get("home_team", "")),
        away_team=str(row.get("away_team", "")),
        predicted_spread=float(row.get("predicted_spread", 0)),
        predicted_total=float(row.get("predicted_total", 0)),
        vegas_spread=_sf(row.get("vegas_spread")),
        vegas_total=_sf(row.get("vegas_total")),
        spread_edge=_sf(row.get("spread_edge")),
        total_edge=_sf(row.get("total_edge")),
        confidence_tier=str(row.get("confidence_tier", "low")),
        ats_pick=str(row.get("ats_pick", "")),
        ou_pick=str(row.get("ou_pick", "")),
    )


@router.get("", response_model=PredictionResponse)
def list_predictions(
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=18, description="Week number"),
) -> PredictionResponse:
    """Return game predictions for the given season and week."""
    try:
        df = prediction_service.get_predictions(season=season, week=week)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    predictions = [_row_to_prediction(row) for _, row in df.iterrows()]
    return PredictionResponse(
        season=season,
        week=week,
        predictions=predictions,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{game_id}", response_model=GamePrediction)
def get_prediction(
    game_id: str,
    season: int = Query(..., ge=1999, le=2030),
    week: int = Query(..., ge=1, le=18),
) -> GamePrediction:
    """Return a single game prediction by game_id."""
    try:
        row = prediction_service.get_prediction_by_game(
            season=season, week=week, game_id=game_id
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if row is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    return _row_to_prediction(row)
