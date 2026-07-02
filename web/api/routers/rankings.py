"""
/api/rankings endpoints -- external fantasy rankings comparison.

Compare our projections against Sleeper ADP, FantasyPros ECR, and ESPN rankings.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import VALID_POSITIONS, VALID_SCORING_FORMATS
from ..services import external_rankings_service

router = APIRouter(prefix="/rankings", tags=["rankings"])

VALID_SOURCES = {
    "sleeper",
    "fantasypros",
    "espn",
    "consensus",
    "draftsharks",
    "ftn",
}


@router.get("/external")
def get_external_rankings(
    source: str = Query(
        "sleeper",
        description="sleeper / fantasypros / espn / consensus / draftsharks / ftn",
    ),
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
    position: Optional[str] = Query(None, description="QB / RB / WR / TE / K"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    season: int = Query(2026, ge=2020, le=2030, description="NFL season"),
) -> dict:
    """Return external fantasy rankings from the specified source.

    Sources:
    - **sleeper**: Sleeper API search_rank (most reliable)
    - **fantasypros**: FantasyPros ECR consensus
    - **espn**: ESPN fantasy rankings
    - **draftsharks**: Draft Sharks board (2024 FP draft-accuracy #1+#2 site)
    - **ftn**: Jeff Ratcliffe / FTN (#1 multi-year FP draft accuracy)
    - **consensus**: Hardcoded expert consensus top-50
    """
    if source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Choose from: {sorted(VALID_SOURCES)}",
        )
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

    # External-source failure is NOT a caller error — the service returns an
    # empty list rather than raising. Never surface 502 here.
    data = external_rankings_service.get_external_rankings(
        source=source,
        scoring=scoring,
        position=position.upper() if position else None,
        limit=limit,
        season=season,
    )

    return {
        "source": source,
        "scoring_format": scoring,
        "position_filter": position,
        "count": len(data),
        "players": data,
    }


@router.get("/compare")
def compare_rankings(
    source: str = Query(
        "sleeper",
        description="sleeper / fantasypros / espn / consensus / draftsharks / ftn",
    ),
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
    position: Optional[str] = Query(None, description="QB / RB / WR / TE / K"),
    limit: int = Query(20, ge=1, le=200, description="Max results"),
    season: int = Query(2026, ge=2020, le=2030, description="NFL season"),
) -> dict:
    """Compare our projections against external rankings side by side.

    Returns each player with both external_rank and our_rank, plus rank_diff
    (positive = we rank them higher than the source, negative = lower).
    """
    if source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Choose from: {sorted(VALID_SOURCES)}",
        )
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

    # External-source failure is NOT a caller error — the service always returns
    # a well-formed envelope with `stale` metadata. Never surface 502 here.
    result = external_rankings_service.compare_rankings(
        source=source,
        scoring=scoring,
        position=position.upper() if position else None,
        limit=limit,
        season=season,
    )
    return result


_VALID_MULTI_SOURCES = {"sleeper", "espn", "yahoo", "draftsharks", "ftn"}
_VALID_SORT_BY = {
    "consensus",
    "ours",
    "sleeper",
    "espn",
    "yahoo",
    "draftsharks",
    "ftn",
}


@router.get("/multi-compare")
def multi_compare_rankings(
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
    position: Optional[str] = Query(None, description="QB / RB / WR / TE / K"),
    limit: int = Query(50, ge=1, le=300, description="Max rows returned"),
    season: int = Query(2026, ge=2020, le=2030, description="NFL season"),
    sources: str = Query(
        "sleeper,espn,yahoo,draftsharks,ftn",
        description=(
            "Comma-separated subset of sleeper / espn / yahoo / draftsharks / ftn"
        ),
    ),
    sort_by: str = Query(
        "consensus",
        description=(
            "consensus (mean external rank) / ours / sleeper / espn / yahoo "
            "/ draftsharks / ftn"
        ),
    ),
) -> dict:
    """Side-by-side ranking table across our projections + 1..N external sources.

    Returns one row per player with a column per requested source plus
    ``our_rank`` and ``our_projected_points``. Players are joined on a
    normalized name key. ``yahoo`` is served via FantasyPros consensus
    (provenance preserved in ``source_labels``).

    Sign convention: ``rank_diff_vs_<source> = external_rank - our_rank``.
    Positive => the source ranks the player lower than we do.
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

    requested = tuple(s.strip().lower() for s in sources.split(",") if s.strip())
    if not requested:
        raise HTTPException(
            status_code=400,
            detail="At least one source is required.",
        )
    invalid = [s for s in requested if s not in _VALID_MULTI_SOURCES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid source(s) {invalid}. "
                f"Choose from: {sorted(_VALID_MULTI_SOURCES)}"
            ),
        )
    if sort_by not in _VALID_SORT_BY:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by. Choose from: {sorted(_VALID_SORT_BY)}",
        )
    if sort_by != "consensus" and sort_by != "ours" and sort_by not in requested:
        raise HTTPException(
            status_code=400,
            detail=(
                f"sort_by={sort_by!r} requires that source in `sources`. "
                f"Got sources={list(requested)}."
            ),
        )

    # External-source failure is NOT a caller error — the service returns a
    # well-formed envelope with `stale` per source. Never surface 502 here.
    return external_rankings_service.multi_compare_rankings(
        scoring=scoring,
        position=position.upper() if position else None,
        limit=limit,
        season=season,
        sources=requested,
        sort_by=sort_by,
    )


@router.get("/sources")
def list_sources() -> dict:
    """List available external ranking sources and their status."""
    sources = []
    for src in sorted(VALID_SOURCES):
        cache_fresh = external_rankings_service._cache_is_fresh(src)
        sources.append(
            {
                "source": src,
                "cache_fresh": cache_fresh,
                "description": {
                    "sleeper": "Sleeper API ADP/search rankings (free, reliable)",
                    "fantasypros": "FantasyPros ECR consensus (may be rate-limited)",
                    "espn": "ESPN fantasy rankings (may be rate-limited)",
                    "draftsharks": (
                        "Draft Sharks board — analysts took #1 and #2 of 225 "
                        "in the 2024 FantasyPros draft-accuracy contest"
                    ),
                    "ftn": (
                        "Jeff Ratcliffe (FTN) — #1 on FantasyPros' 2022-2024 "
                        "multi-year draft-accuracy leaderboard; empty until he "
                        "submits ranks for the season (typically Jul-Aug)"
                    ),
                    "consensus": "Hardcoded expert consensus top-50 (always available)",
                }.get(src, ""),
            }
        )
    return {"sources": sources}
