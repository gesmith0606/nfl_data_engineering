"""/api/report endpoints -- auto-generated, league-agnostic weekly digest.

Deterministic composition over existing Gold/Silver artifacts (projections +
schedule + defense-vs-position ranks). No LLM calls, no new modeling --
every section is a filter/sort/join over data other endpoints already serve.
"""

from __future__ import annotations

import glob
import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import DATA_DIR, GOLD_PROJECTIONS_DIR
from ..services import projection_service
from ..services.team_roster_service import get_current_week

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report"])

_SKILL_POSITIONS: Tuple[str, ...] = ("QB", "RB", "WR", "TE")
_BOOM_BUST_MIN_PROJECTION = 8.0


# ---------------------------------------------------------------------------
# Schemas (local -- only the weekly report endpoint uses them)
# ---------------------------------------------------------------------------


class Headline(BaseModel):
    season: int
    week: Optional[int] = None
    generated_from: Optional[str] = Field(
        None,
        description="Project-relative path of the Gold parquet this report was built from",
    )


class TopProjectedPlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    projected_points: float
    projected_floor: Optional[float] = None
    projected_ceiling: Optional[float] = None


class InjuryWatchPlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    injury_status: str
    projected_points: float


class MatchupCell(BaseModel):
    team: str
    position: str
    opponent: str
    opp_rank: int = Field(
        description="Opponent defense rank vs this position (1 = toughest, 32 = easiest)"
    )


class MatchupSpotlight(BaseModel):
    best: List[MatchupCell] = Field(default_factory=list)
    worst: List[MatchupCell] = Field(default_factory=list)


class BoomBustPlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    projected_points: float
    projected_floor: Optional[float] = None
    projected_ceiling: Optional[float] = None
    ceiling_minus_floor: Optional[float] = None
    floor_ratio: Optional[float] = Field(
        None, description="projected_floor / projected_points -- higher is safer"
    )


class BoomBust(BaseModel):
    upside: List[BoomBustPlayer] = Field(default_factory=list)
    safe: List[BoomBustPlayer] = Field(default_factory=list)


class WeeklyReportResponse(BaseModel):
    headline: Headline
    mode: str = Field("weekly", description="'weekly' or 'preseason'")
    message: Optional[str] = None
    top_projected: Dict[str, List[TopProjectedPlayer]] = Field(default_factory=dict)
    injury_watch: List[InjuryWatchPlayer] = Field(default_factory=list)
    matchup_spotlight: MatchupSpotlight = Field(default_factory=MatchupSpotlight)
    boom_bust: BoomBust = Field(default_factory=BoomBust)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _check_scoring(scoring: str) -> Optional[str]:
    if scoring not in ("ppr", "half_ppr", "standard"):
        return f"Invalid scoring: {scoring}"
    return None


def _opt_float(val) -> Optional[float]:
    return None if val is None or pd.isna(val) else float(val)


def _resolve_week(season: int, week: Optional[int]) -> Optional[int]:
    """Resolve the effective week: explicit > current schedule week > None.

    Returns None (rather than defaulting to week 1) so the caller can render
    preseason mode honestly instead of pretending week 1 data exists.
    """
    if week is not None:
        return week
    try:
        cw = get_current_week()
        if int(cw.season) == season and cw.week is not None:
            return int(cw.week)
    except Exception:  # pragma: no cover -- schedule parquet missing
        logger.warning("current-week resolution failed", exc_info=True)
    return None


def _preseason_response(season: int, week: Optional[int]) -> WeeklyReportResponse:
    """Empty-payload preseason response with an explicit explanation.

    Mirrors the /api/league/{league_id}/my-week preseason pattern: 200 OK,
    mode='preseason', empty sections, human-readable message -- never a 500
    or a silent substitution of season-long numbers for weekly ones.
    """
    return WeeklyReportResponse(
        headline=Headline(season=season, week=week, generated_from=None),
        mode="preseason",
        message=(
            f"Weekly projections for the {season} season aren't published yet "
            "-- the Weekly Report goes live once game-week data is available."
        ),
    )


def _has_weekly_parquet(season: int, week: int) -> bool:
    """True when a weekly Gold projections parquet exists for (season, week).

    Checked directly against disk (not via projection_service.get_projections,
    which auto-falls-back to preseason data for current/future seasons) so a
    genuinely missing weekly slice is reported as preseason mode rather than
    silently rebadging season-long projections as this week's report.
    """
    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    return week_dir.exists() and any(week_dir.glob("*.parquet"))


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _to_top_player(row: Dict) -> TopProjectedPlayer:
    return TopProjectedPlayer(
        player_id=str(row.get("player_id") or ""),
        player_name=str(row.get("player_name") or ""),
        team=row.get("team") or row.get("recent_team"),
        position=str(row.get("position") or "").upper(),
        projected_points=float(row.get("projected_points") or 0),
        projected_floor=_opt_float(row.get("projected_floor")),
        projected_ceiling=_opt_float(row.get("projected_ceiling")),
    )


def _build_top_projected(df: pd.DataFrame) -> Dict[str, List[TopProjectedPlayer]]:
    """Top 5 per position (QB/RB/WR/TE) by projected_points, floor/ceiling attached."""
    out: Dict[str, List[TopProjectedPlayer]] = {}
    for pos in _SKILL_POSITIONS:
        sub = df[df["position"].astype(str).str.upper() == pos]
        sub = sub.sort_values("projected_points", ascending=False).head(5)
        out[pos] = [_to_top_player(r) for r in sub.to_dict("records")]
    return out


def _build_injury_watch(df: pd.DataFrame) -> List[InjuryWatchPlayer]:
    """Top-10 projected players (any skill position) carrying an injury_status."""
    if "injury_status" not in df.columns:
        return []
    inj = df[df["injury_status"].notna() & (df["injury_status"].astype(str) != "")]
    inj = inj.sort_values("projected_points", ascending=False).head(10)
    return [
        InjuryWatchPlayer(
            player_id=str(r.get("player_id") or ""),
            player_name=str(r.get("player_name") or ""),
            team=r.get("team") or r.get("recent_team"),
            position=str(r.get("position") or "").upper(),
            injury_status=str(r.get("injury_status")),
            projected_points=float(r.get("projected_points") or 0),
        )
        for r in inj.to_dict("records")
    ]


def _matchup_opp_ranks(
    season: int, week: int
) -> Dict[Tuple[str, str], Tuple[str, int]]:
    """(team, position) -> (opponent, opp_rank) for this week's matchups.

    Joins the week's schedule (home/away) against the latest defense-vs-
    position ranks known at or before this week. Best-effort: returns {} on
    any data gap so matchup_spotlight degrades to empty lists instead of a
    500 (fail-open, same convention as tools.py's _opp_rank_lookup).
    """
    try:
        sched_files = sorted(
            glob.glob(
                str(
                    DATA_DIR
                    / "bronze"
                    / "schedules"
                    / f"season={season}"
                    / "**"
                    / "*.parquet"
                ),
                recursive=True,
            )
        )
        if not sched_files:
            return {}
        sched = pd.read_parquet(sched_files[-1])
        sched = sched[sched["week"] == week]
        if sched.empty:
            return {}
        opp: Dict[str, str] = {}
        for _, g in sched.iterrows():
            home, away = str(g.get("home_team")), str(g.get("away_team"))
            opp[home] = away
            opp[away] = home

        pos_files = sorted(
            glob.glob(
                str(
                    DATA_DIR
                    / "silver"
                    / "defense"
                    / "positional"
                    / f"season={season}"
                    / "opp_rankings_*.parquet"
                )
            )
        )
        if not pos_files:
            return {}
        ranks = pd.read_parquet(pos_files[-1])
        known = ranks[ranks["week"] <= week]
        if known.empty:
            # Early season: no ranks reported yet at/before this week --
            # fall back to whatever the parquet has rather than an empty grid.
            known = ranks
        known = (
            known.sort_values("week")
            .groupby(["team", "position"], as_index=False)
            .last()
        )
        rank_by = {
            (str(r["team"]), str(r["position"]).upper()): int(r["rank"])
            for _, r in known.iterrows()
        }

        out: Dict[Tuple[str, str], Tuple[str, int]] = {}
        for team, opponent in opp.items():
            for pos in _SKILL_POSITIONS:
                if (opponent, pos) in rank_by:
                    out[(team, pos)] = (opponent, rank_by[(opponent, pos)])
        return out
    except Exception:  # pragma: no cover -- any data gap degrades gracefully
        logger.warning("matchup opp-rank lookup failed", exc_info=True)
        return {}


def _build_matchup_spotlight(season: int, week: int) -> MatchupSpotlight:
    """5 best + 5 worst (team, position) matchups by opponent defense rank.

    Best = opponent rank near 32 (defense allows the most fantasy points to
    that position); worst = opponent rank near 1 (toughest defense).
    """
    opp_ranks = _matchup_opp_ranks(season, week)
    if not opp_ranks:
        return MatchupSpotlight()
    cells = [
        MatchupCell(team=team, position=pos, opponent=opponent, opp_rank=rank)
        for (team, pos), (opponent, rank) in opp_ranks.items()
    ]
    best = sorted(cells, key=lambda c: c.opp_rank, reverse=True)[:5]
    worst = sorted(cells, key=lambda c: c.opp_rank)[:5]
    return MatchupSpotlight(best=best, worst=worst)


def _to_boom_bust_player(row: Dict) -> BoomBustPlayer:
    points = float(row.get("projected_points") or 0)
    floor = _opt_float(row.get("projected_floor"))
    ceiling = _opt_float(row.get("projected_ceiling"))
    return BoomBustPlayer(
        player_id=str(row.get("player_id") or ""),
        player_name=str(row.get("player_name") or ""),
        team=row.get("team") or row.get("recent_team"),
        position=str(row.get("position") or "").upper(),
        projected_points=points,
        projected_floor=floor,
        projected_ceiling=ceiling,
        ceiling_minus_floor=(
            round(ceiling - floor, 2)
            if ceiling is not None and floor is not None
            else None
        ),
        floor_ratio=(
            round(floor / points, 3) if floor is not None and points > 0 else None
        ),
    )


def _build_boom_bust(df: pd.DataFrame) -> BoomBust:
    """Upside (widest ceiling-floor spread) and safe (highest floor/proj ratio) plays.

    Both pools are restricted to players with projected_points >= 8 -- below
    that, floor/ceiling bands are too noisy to call either "boom" or "safe".
    """
    pool = df[df["projected_points"].fillna(0) >= _BOOM_BUST_MIN_PROJECTION].copy()
    if (
        pool.empty
        or "projected_floor" not in pool.columns
        or "projected_ceiling" not in pool.columns
    ):
        return BoomBust()

    pool["_range"] = pool["projected_ceiling"].fillna(pool["projected_points"]) - pool[
        "projected_floor"
    ].fillna(pool["projected_points"])
    upside_df = pool.sort_values("_range", ascending=False).head(5)

    pool["_floor_ratio"] = pool["projected_floor"].fillna(0) / pool[
        "projected_points"
    ].replace(0, pd.NA)
    safe_df = pool.sort_values("_floor_ratio", ascending=False).head(5)

    return BoomBust(
        upside=[_to_boom_bust_player(r) for r in upside_df.to_dict("records")],
        safe=[_to_boom_bust_player(r) for r in safe_df.to_dict("records")],
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/weekly", response_model=WeeklyReportResponse)
def weekly_report(
    season: int = Query(..., ge=1999, le=2030),
    week: Optional[int] = Query(
        None, ge=1, le=18, description="Defaults to current week"
    ),
    scoring: str = Query("half_ppr"),
) -> WeeklyReportResponse:
    """Auto-generated weekly digest -- deterministic composition, no LLM calls.

    Sections: headline, top_projected (top 5 per QB/RB/WR/TE), injury_watch
    (top-10 projected players with an injury designation), matchup_spotlight
    (5 best/5 worst team-position matchups by opponent defense rank), and
    boom_bust (5 widest ceiling-floor spreads, 5 highest floor/projection
    ratios, min 8 projected points).

    When ``week`` is omitted the current NFL week is resolved from the
    schedule. If no weekly Gold parquet exists for the resolved (season,
    week) -- e.g. during the preseason -- returns 200 with ``mode:
    'preseason'``, empty sections, and a human-readable ``message``. Never
    500s on missing data.
    """
    scoring_error = _check_scoring(scoring)
    if scoring_error:
        raise HTTPException(status_code=400, detail=scoring_error)

    resolved_week = _resolve_week(season, week)
    if resolved_week is None or not _has_weekly_parquet(season, resolved_week):
        return _preseason_response(season, resolved_week)

    try:
        df = projection_service.get_projections(
            season=season, week=resolved_week, scoring_format=scoring, limit=1000
        )
    except FileNotFoundError:
        return _preseason_response(season, resolved_week)

    if df is None or df.empty:
        return _preseason_response(season, resolved_week)

    # projection_service's rename map collides "proj_season"/"proj_week" onto
    # already-present "season"/"week" columns; drop the dupes so
    # DataFrame.to_dict("records") below doesn't silently pick an arbitrary
    # one (harmless here since we never read those two fields, but noisy).
    df = df.loc[:, ~df.columns.duplicated()].copy()

    meta = projection_service.get_projection_meta(season, resolved_week)
    generated_from = meta.source_path

    return WeeklyReportResponse(
        headline=Headline(
            season=season, week=resolved_week, generated_from=generated_from
        ),
        mode="weekly",
        message=None,
        top_projected=_build_top_projected(df),
        injury_watch=_build_injury_watch(df),
        matchup_spotlight=_build_matchup_spotlight(season, resolved_week),
        boom_bust=_build_boom_bust(df),
    )
