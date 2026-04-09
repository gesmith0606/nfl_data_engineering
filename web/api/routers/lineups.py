"""
/api/lineups endpoints -- team starting lineup identification.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import LineupPlayer, LineupResponse, TeamLineup

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
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=22, description="Week number"),
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

    When ``team`` is provided, projections are included if available.
    """
    from lineup_builder import (
        get_team_lineup_with_projections,
        get_team_starters,
    )

    if team:
        df = get_team_lineup_with_projections(
            season=season, week=week, team=team.upper(), scoring_format=scoring
        )
    else:
        df = get_team_starters(season=season, week=week)

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No lineup data for season={season} week={week}"
            + (f" team={team}" if team else ""),
        )

    lineups: List[TeamLineup] = []
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

    return LineupResponse(
        season=season,
        week=week,
        lineups=lineups,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
