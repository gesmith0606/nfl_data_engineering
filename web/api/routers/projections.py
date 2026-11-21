"""
/api/projections endpoints -- fantasy player projections.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import VALID_POSITIONS, VALID_SCORING_FORMATS
from ..models.schemas import (
    LatestWeekResponse,
    PlayerProjection,
    ProjectionComparison,
    ProjectionComparisonRow,
    ProjectionMeta,
    ProjectionResponse,
)
from ..services import projection_service

router = APIRouter(prefix="/projections", tags=["projections"])

_SEASON_TOTAL_MESSAGE = (
    "Preseason projections: projected_points are full-season TOTALS, "
    "not points for this week."
)


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
                proj_interceptions=_safe_float(row.get("proj_interceptions")),
                proj_rush_yards=_safe_float(row.get("proj_rush_yards")),
                proj_rush_tds=_safe_float(row.get("proj_rush_tds")),
                proj_carries=_safe_float(row.get("proj_carries")),
                proj_rec=_safe_float(row.get("proj_rec")),
                proj_rec_yards=_safe_float(row.get("proj_rec_yards")),
                proj_rec_tds=_safe_float(row.get("proj_rec_tds")),
                proj_targets=_safe_float(row.get("proj_targets")),
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
    limit: int = Query(1000, ge=1, le=1000, description="Max results"),
    board: Optional[str] = Query(
        None,
        description="'preseason' = explicitly request the season-total preseason board",
    ),
) -> ProjectionResponse:
    """Return player projections for the given season, week, and scoring format.

    When the week's board is not published yet (season underway) the response
    is HTTP 200 with ``available=false`` and an empty list -- never season
    totals. Rows that ARE season totals carry ``is_season_total=true``.

    Default ``limit`` is the API ceiling (1000) so unfiltered callers — like
    the matchups page, which builds 32 team rosters from a single fetch —
    always receive the full slate. Truncating to a top-N by projected_points
    silently drops mid-tier RB2/WR3/TE on lower-projected teams (NYJ/CHI/MIN)
    and renders their offensive cards blank.
    """
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

    if board == "preseason":
        try:
            df = projection_service.get_preseason_projections(
                season, scoring, position, team, limit
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return ProjectionResponse(
            season=season,
            week=week,
            scoring_format=scoring,
            projections=_df_to_projection_list(df, scoring),
            generated_at=datetime.now(timezone.utc).isoformat(),
            available=True,
            source="preseason_fallback",
            is_season_total=True,
            message=_SEASON_TOTAL_MESSAGE,
            meta=ProjectionMeta(season=season, week=week, source="preseason_fallback"),
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
    except projection_service.ProjectionsNotPublished as exc:
        # Season is underway but this week's board does not exist: say so
        # explicitly instead of serving season totals as weekly points.
        latest = exc.latest_week
        return ProjectionResponse(
            season=season,
            week=week,
            scoring_format=scoring,
            projections=[],
            generated_at=datetime.now(timezone.utc).isoformat(),
            available=False,
            source="not_published",
            is_season_total=False,
            latest_available_week=latest,
            message=(
                f"Week {week} projections publish Tuesday; latest available is "
                f"week {latest}."
                if latest
                else f"Week {week} projections are not published yet."
            ),
            meta=ProjectionMeta(
                season=season,
                week=week,
                source="not_published",
                latest_available_week=latest,
            ),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    projections = _df_to_projection_list(df, scoring)
    meta_info = projection_service.get_projection_meta(season=season, week=week)
    is_total = meta_info.source == "preseason_fallback"
    return ProjectionResponse(
        season=season,
        week=week,
        scoring_format=scoring,
        projections=projections,
        generated_at=datetime.now(timezone.utc).isoformat(),
        available=True,
        source=meta_info.source,
        is_season_total=is_total,
        latest_available_week=meta_info.latest_available_week,
        message=_SEASON_TOTAL_MESSAGE if is_total else None,
        meta=ProjectionMeta(
            season=meta_info.season,
            week=meta_info.week,
            data_as_of=meta_info.data_as_of,
            source_path=meta_info.source_path,
            source=meta_info.source,
            latest_available_week=meta_info.latest_available_week,
        ),
    )


@router.get("/latest-week", response_model=LatestWeekResponse)
def latest_week(
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
) -> LatestWeekResponse:
    """Return the highest week number in the Gold layer that has a parquet file.

    Used by the AI advisor's ``getPositionRankings`` tool to auto-resolve a
    sensible default week when the user asks "who are the top 10 RBs" without
    specifying one. Returns HTTP 200 with ``week=null`` during the offseason
    instead of a 404 so the advisor can distinguish "no data yet" from
    "backend unreachable".
    """
    info = projection_service.get_latest_week(season=season)
    return LatestWeekResponse(
        season=info.season,
        week=info.week,
        data_as_of=info.data_as_of,
    )


@router.get("/comparison", response_model=ProjectionComparison)
def projections_comparison(
    season: int = Query(..., ge=1999, le=2030),
    week: int = Query(..., ge=1, le=18),
    scoring: str = Query("half_ppr"),
    position: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> ProjectionComparison:
    """Side-by-side projection comparison: ours vs ESPN vs Sleeper vs Yahoo (FP proxy).

    Returns a wide-format comparison with delta_vs_ours computed per player.
    Falls back to an empty `rows` list if Silver hasn't been consolidated yet
    (D-06 fail-open) — frontend renders an EmptyState placeholder.
    """
    if scoring not in VALID_SCORING_FORMATS:
        raise HTTPException(
            status_code=400, detail=f"Invalid scoring format: {scoring}"
        )
    if position and position.upper() not in VALID_POSITIONS:
        raise HTTPException(status_code=400, detail=f"Invalid position: {position}")

    payload = projection_service.get_comparison(
        season=season,
        week=week,
        scoring_format=scoring,
        position=position,
        limit=limit,
    )
    return ProjectionComparison(
        season=payload["season"],
        week=payload["week"],
        scoring_format=payload["scoring_format"],
        rows=[ProjectionComparisonRow(**r) for r in payload["rows"]],
        source_labels=payload["source_labels"],
        data_as_of=payload["data_as_of"],
        fallback=payload.get("fallback", False),
        fallback_season=payload.get("fallback_season"),
        fallback_week=payload.get("fallback_week"),
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
        board=None,
    )
