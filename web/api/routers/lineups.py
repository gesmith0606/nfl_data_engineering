"""
/api/lineups endpoints -- team starting lineup identification.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import (
    FlatLineupPlayer,
    LineupPlayer,
    LineupResponse,
    TeamLineup,
)
from ..services import projection_service

# Ensure src/ is importable for lineup_builder
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

router = APIRouter(prefix="/lineups", tags=["lineups"])


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


def _df_to_lineup_players(df) -> List[LineupPlayer]:
    """Convert a starters DataFrame subset to a list of LineupPlayer models."""
    players = []
    for _, row in df.iterrows():
        players.append(
            LineupPlayer(
                player_id=str(row.get("player_id", "")),
                player_name=str(row.get("player_name", "")),
                position=str(row.get("position", "")),
                position_group=str(row.get("position_group", "")),
                field_position=str(row.get("field_position", "")),
                projected_points=_safe_float(row.get("projected_points")),
                projected_floor=_safe_float(row.get("projected_floor")),
                projected_ceiling=_safe_float(row.get("projected_ceiling")),
                snap_pct=_safe_float(row.get("snap_pct")),
                depth_rank=int(row.get("depth_rank", 1)),
                is_starter=bool(row.get("is_starter", False)),
                starter_confidence=float(row.get("starter_confidence", 0.0)),
            )
        )
    return players


@router.get("", response_model=LineupResponse)
def get_lineups(
    season: Optional[int] = Query(
        None, ge=1999, le=2030, description="NFL season (defaults to latest)"
    ),
    week: Optional[int] = Query(
        None, ge=1, le=22, description="Week number (defaults to latest)"
    ),
    team: Optional[str] = Query(
        None, min_length=2, max_length=3, description="Team abbreviation (e.g. KC)"
    ),
    scoring: str = Query(
        "half_ppr",
        description="Scoring format for projections",
        pattern="^(ppr|half_ppr|standard)$",
    ),
) -> LineupResponse:
    """Get starting lineups for all teams or a specific team.

    When ``team`` is provided, projections are included if available. When
    ``season`` and/or ``week`` are omitted, the service resolves them to the
    latest-available Gold projection slice (phase 66 / v7.0 graceful
    defaulting). ``defaulted=True`` flags the resolution and ``data_as_of``
    carries the underlying parquet mtime.
    """
    from lineup_builder import (
        get_team_lineup_with_projections,
        get_team_starters,
    )

    import logging

    logger = logging.getLogger(__name__)

    defaulted = season is None or week is None
    data_as_of: Optional[str] = None
    if defaulted:
        meta = projection_service.get_latest_slice()
        resolved_season = season if season is not None else meta.season
        resolved_week = week if week is not None else meta.week
        data_as_of = meta.data_as_of
        if resolved_week is None:
            # No Gold projections anywhere — return empty, typed envelope.
            return LineupResponse(
                season=resolved_season or 0,
                week=0,
                lineups=[],
                lineup=[],
                generated_at=datetime.now(timezone.utc).isoformat(),
                data_as_of=None,
                defaulted=True,
            )
        season = resolved_season
        week = resolved_week

    assert season is not None and week is not None  # narrowed by logic above

    if team:
        df = get_team_lineup_with_projections(
            season=season, week=week, team=team.upper(), scoring_format=scoring
        )
    else:
        df = get_team_starters(season=season, week=week)

    if df.empty:
        # Return an empty envelope (HTTP 200) instead of 404 so the advisor
        # tool ``getTeamRoster`` receives ``{"lineup": []}`` during offseason
        # or when the requested team has no depth chart yet.
        logger.warning(
            "No lineup data for season=%d week=%d team=%s — returning empty",
            season,
            week,
            team or "ALL",
        )
        return LineupResponse(
            season=season,
            week=week,
            lineups=[],
            lineup=[],
            generated_at=datetime.now(timezone.utc).isoformat(),
            data_as_of=data_as_of,
            defaulted=defaulted,
        )

    lineups: List[TeamLineup] = []
    flat_lineup: List[FlatLineupPlayer] = []
    for team_code in sorted(df["team"].unique()):
        team_df = df[df["team"] == team_code]
        offense_df = team_df[team_df["side"] == "offense"]
        defense_df = team_df[team_df["side"] == "defense"]

        # Compute team projected total from offense projections
        proj_total = None
        if "projected_points" in team_df.columns:
            off_pts = offense_df["projected_points"].dropna()
            if not off_pts.empty:
                proj_total = round(float(off_pts.sum()), 1)

        lineups.append(
            TeamLineup(
                team=team_code,
                season=season,
                week=week,
                offense=_df_to_lineup_players(offense_df),
                defense=_df_to_lineup_players(defense_df),
                implied_total=None,  # Would come from Vegas data
                team_projected_total=proj_total,
            )
        )

        # Flat lineup entries for the advisor contract.
        for _, row in team_df.iterrows():
            flat_lineup.append(
                FlatLineupPlayer(
                    player_id=str(row.get("player_id", "")),
                    player_name=str(row.get("player_name", "")),
                    team=str(team_code),
                    position=str(row.get("position", "")),
                    projected_points=_safe_float(row.get("projected_points")),
                    projected_floor=_safe_float(row.get("projected_floor")),
                    projected_ceiling=_safe_float(row.get("projected_ceiling")),
                    injury_status=(
                        str(row.get("injury_status"))
                        if row.get("injury_status") is not None
                        and str(row.get("injury_status")) != "nan"
                        else None
                    ),
                    is_starter=bool(row.get("is_starter", False)),
                )
            )

    return LineupResponse(
        season=season,
        week=week,
        lineups=lineups,
        lineup=flat_lineup,
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_as_of=data_as_of,
        defaulted=defaulted,
    )
