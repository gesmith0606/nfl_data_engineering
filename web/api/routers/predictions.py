"""
/api/predictions endpoints -- game spread / total predictions.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import GamePrediction, PredictionResponse
from ..services import prediction_service

router = APIRouter(prefix="/predictions", tags=["predictions"])

# The O/U betting surface is retired: .planning/TOTALS_VERDICT.md (2026-06-10,
# VERDICT: KILL) says to "remove the game-totals betting surface from
# production [and] keep predicted_total as website content labeled market
# tracking (useful context; not a bet recommendation)".
#
# Blanked HERE, at the serving boundary, and not only in the generator,
# because the boards on disk were written over the four months the verdict
# went unenforced and still carry a real side; the API reads those parquets
# directly. predicted_total / vegas_total / total_edge keep flowing as market
# tracking. See scripts/generate_predictions.py::OU_PICK_RETIRED for the
# evidence, and web/frontend/.../prediction-cards.tsx for the presentation.
OU_PICK_RETIRED = ""

# -110 break-even. NOT applied: whether to publish only picks that clear it is
# the product owner's call (4 of 14 picked sides clear it on the served 2026
# wk7 board). Documented here so the number sits beside the pick it would gate,
# and gated for real by generate_predictions.ATS_PUBLISH_MIN_PROB if ever
# switched on.
ATS_BREAKEVEN_PROB = 0.5238


def _row_to_prediction(row) -> GamePrediction:
    """Convert a DataFrame row/Series to a GamePrediction.

    ``ats_pick`` is re-derived from ``home_cover_prob`` when the row carries
    one, so the pick served can never contradict the calibrated probability
    behind it — including for boards generated before the generator was fixed
    (they picked on the raw edge sign and disagreed on 1 of 14 wk7 games).
    This mirrors ``generate_predictions.picks_home_side``; keep the two in step.
    """

    def _sf(val) -> Optional[float]:
        if val is None:
            return None
        try:
            f = float(val)
            return None if f != f else f
        except (ValueError, TypeError):
            return None

    home_team = str(row.get("home_team", ""))
    away_team = str(row.get("away_team", ""))
    cover_prob = _sf(row.get("home_cover_prob"))
    if cover_prob is None:
        ats_pick = str(row.get("ats_pick", ""))
    else:
        ats_pick = home_team if cover_prob >= 0.50 else away_team

    return GamePrediction(
        game_id=str(row.get("game_id", "")),
        season=int(row.get("season", 0)),
        week=int(row.get("week", 0)),
        home_team=home_team,
        away_team=away_team,
        predicted_spread=float(row.get("predicted_spread", 0)),
        predicted_total=float(row.get("predicted_total", 0)),
        vegas_spread=_sf(row.get("vegas_spread")),
        vegas_total=_sf(row.get("vegas_total")),
        spread_edge=_sf(row.get("spread_edge")),
        total_edge=_sf(row.get("total_edge")),
        confidence_tier=str(row.get("confidence_tier", "low")),
        ats_pick=ats_pick,
        ou_pick=OU_PICK_RETIRED,
    )


@router.get("", response_model=PredictionResponse)
def list_predictions(
    season: Optional[int] = Query(
        None, ge=1999, le=2030, description="NFL season (defaults to latest-played)"
    ),
    week: Optional[int] = Query(
        None, ge=1, le=18, description="Week number (defaults to latest-played)"
    ),
) -> PredictionResponse:
    """Return game predictions for the given season and week.

    When ``season`` and/or ``week`` are omitted the service resolves them to
    the latest-played slice in Gold storage (phase 66 / v7.0 graceful
    defaulting). ``defaulted=True`` signals the defaulting occurred and
    ``data_as_of`` carries the underlying parquet mtime so the frontend
    surfaces freshness without a second request.

    Returns an empty envelope (HTTP 200) when no predictions exist for the
    requested slice (preseason / offseason). This preserves the advisor
    tool contract which expects ``{"predictions": []}`` rather than a 404.
    """
    import logging

    logger = logging.getLogger(__name__)

    defaulted = season is None or week is None
    data_as_of: Optional[str] = None
    if defaulted:
        meta = prediction_service.get_latest_week(season=season)
        # Preserve any caller-supplied value; only fill in the missing ones.
        resolved_season = season if season is not None else meta.season
        resolved_week = week if week is not None else meta.week
        data_as_of = meta.data_as_of
        if resolved_week is None:
            # No data anywhere — return empty, typed envelope.
            return PredictionResponse(
                season=resolved_season or 0,
                week=0,
                predictions=[],
                generated_at=datetime.now(timezone.utc).isoformat(),
                data_as_of=None,
                defaulted=True,
            )
        season = resolved_season
        week = resolved_week

    assert season is not None and week is not None  # narrowed by logic above

    try:
        df = prediction_service.get_predictions(season=season, week=week)
    except FileNotFoundError as exc:
        logger.warning(
            "No prediction data for season=%d week=%d: %s", season, week, exc
        )
        return PredictionResponse(
            season=season,
            week=week,
            predictions=[],
            generated_at=datetime.now(timezone.utc).isoformat(),
            data_as_of=data_as_of,
            defaulted=defaulted,
        )

    predictions = [_row_to_prediction(row) for _, row in df.iterrows()]
    return PredictionResponse(
        season=season,
        week=week,
        predictions=predictions,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_as_of=data_as_of,
        defaulted=defaulted,
    )


@router.get("/latest-week")
def latest_predictions_week(
    season: Optional[int] = Query(
        None, ge=1999, le=2030,
        description="NFL season to scan (omit to scan all seasons)",
    ),
) -> dict:
    """Return the latest (season, week) that has game-prediction data.

    Mirrors `/api/projections/latest-week` but anchored to predictions.
    The frontend's predictions page uses this to resolve a sensible default
    week instead of borrowing from projections — the two layers can be out
    of sync (e.g. preseason projections exist for 2026 but no game
    predictions yet because the season hasn't started).

    Returns ``week=null`` when no predictions are available anywhere.
    """
    meta = prediction_service.get_latest_week(season=season)
    return {
        "season": meta.season,
        "week": meta.week,
        "data_as_of": meta.data_as_of,
    }


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
