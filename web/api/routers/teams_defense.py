"""
/api/teams/{team}/defense-metrics — real defensive matchup metrics.

Implements MTCH-03 (matchup advantage indicators calculated from real team
defensive metrics, not hardcoded). The response surfaces per-position
defensive ranks (vs QB/RB/WR/TE) from ``data/silver/defense/positional`` and
team-level SOS (``def_sos_rank``, ``adj_def_epa``) from
``data/silver/teams/sos``.

Kept in a separate module from ``teams.py`` so plan 64-02 and plan 64-03 don't
overlap on the same file. The router shares the ``/teams`` prefix — FastAPI
allows multiple routers on the same prefix as long as paths don't collide, and
``/defense-metrics`` does not collide with ``/current-week`` or
``/{team}/roster``.

See ``.planning/phases/64-matchup-view-completion/API-CONTRACT.md`` for the
authoritative response shape and fallback matrix.
"""

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import TeamDefenseMetricsResponse
from ..services import team_defense_service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/{team}/defense-metrics", response_model=TeamDefenseMetricsResponse)
def team_defense_metrics(
    team: str,
    season: int = Query(..., ge=2016, le=2030, description="NFL season"),
    week: int = Query(
        ..., ge=1, le=22, description="Week number (1-22 incl. postseason)"
    ),
) -> TeamDefenseMetricsResponse:
    """Return per-team defensive metrics for *season* / *week*.

    Response contract:

    * ``positional`` — always 4 entries (QB/RB/WR/TE) with ``avg_pts_allowed``,
      positional ``rank`` (1-32), and a display ``rating`` (50-99).
    * ``overall_def_rating`` — derived from ``def_sos_rank`` via the same
      rank-to-rating mapping.
    * ``fallback`` / ``fallback_season`` — set when the requested season's
      silver data is absent and the service walked back (e.g., 2026 → 2025).
    * ``source_week`` — actual week whose silver row was used (may differ
      from ``requested_week`` when the requested week has no data).

    Error modes:

    * Unknown team → ``404`` (``ValueError`` from service).
    * No positional parquet for any season → ``404``
      (``FileNotFoundError`` from service).
    * Out-of-range season/week → ``422`` (FastAPI ``Query`` validator).
    """
    try:
        payload = team_defense_service.load_defense_metrics(team, season, week)
    except ValueError as exc:
        # Unknown team → 404 (distinct from 422 validation)
        raise HTTPException(status_code=404, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return TeamDefenseMetricsResponse(**payload)
