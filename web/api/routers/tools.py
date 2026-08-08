"""/api/tools endpoints — in-season decision tools.

Market-gap sprint (2026-08): rest-of-season value, trade analyzer,
start/sit comparator, auction values, league-wide defense-vs-position
SOS, depth charts, and injury report. Every endpoint is a thin surface
over existing Gold/Silver artifacts and src/ modules — no new modeling.
"""

from __future__ import annotations

import glob
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.projection_store import load_latest_preseason
from src.scoring_calculator import calculate_fantasy_points_df

from ..config import DATA_DIR
from ..services import projection_service
from ..services.team_roster_service import get_current_week

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])

_SEASON_WEEKS = 18


# ---------------------------------------------------------------------------
# Schemas (local — only tools endpoints use them)
# ---------------------------------------------------------------------------


class RosPlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    ros_points: float = Field(description="Projected points over remaining weeks")
    projected_season_points: float
    vorp: Optional[float] = None
    position_rank: Optional[int] = None


class RosResponse(BaseModel):
    season: int
    from_week: int
    weeks_remaining: int
    scoring_format: str
    players: List[RosPlayer]


class TradeRequest(BaseModel):
    side_a: List[str] = Field(min_length=1, description="player_ids given away")
    side_b: List[str] = Field(min_length=1, description="player_ids received")
    season: int
    week: Optional[int] = None
    scoring: str = "half_ppr"


class TradeSide(BaseModel):
    players: List[RosPlayer]
    total_ros_points: float
    unmatched_player_ids: List[str] = []


class TradeResponse(BaseModel):
    season: int
    from_week: int
    scoring_format: str
    side_a: TradeSide
    side_b: TradeSide
    delta_ros_points: float = Field(
        description="side_b minus side_a (positive = you win)"
    )
    verdict: str
    fairness_pct: float = Field(description="abs delta as % of larger side total")


class ComparePlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    projected_points: float
    projected_floor: Optional[float] = None
    projected_ceiling: Optional[float] = None
    injury_status: Optional[str] = None
    opp_rank_vs_position: Optional[int] = Field(
        None, description="Opponent defense rank vs this position (1 = toughest)"
    )
    ros_points: Optional[float] = None
    recommended: bool = False


class CompareResponse(BaseModel):
    season: int
    week: int
    scoring_format: str
    players: List[ComparePlayer]
    reason: str


class AuctionPlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    projected_season_points: float
    vorp: Optional[float] = None
    auction_value: int


class AuctionResponse(BaseModel):
    season: int
    n_teams: int
    budget_per_team: int
    scoring_format: str
    players: List[AuctionPlayer]


class SosCell(BaseModel):
    team: str
    position: str
    avg_pts_allowed: float
    rank: int = Field(description="1 = fewest fantasy pts allowed (toughest)")


class SosResponse(BaseModel):
    season: int
    week: int
    cells: List[SosCell]


class DepthChartEntry(BaseModel):
    team: str
    position: str
    player_name: str
    depth_rank: int
    gsis_id: Optional[str] = None


class DepthChartResponse(BaseModel):
    season: int
    as_of: Optional[str] = None
    entries: List[DepthChartEntry]


class InjuryRow(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    injury_status: str
    projected_points: float


class InjuryResponse(BaseModel):
    season: int
    week: int
    players: List[InjuryRow]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_week(season: int, week: Optional[int]) -> int:
    """Resolve the effective from-week: explicit > current schedule week > 1."""
    if week is not None:
        return week
    try:
        cw = get_current_week()
        if int(cw.season) == season and cw.week is not None:
            return int(cw.week)
    except Exception:  # pragma: no cover — schedule parquet missing
        logger.warning("current-week resolution failed", exc_info=True)
    return 1


def _preseason_scored(season: int, scoring: str) -> pd.DataFrame:
    """Preseason projections re-scored to *scoring*, with ROS-ready columns.

    The committed preseason parquet is generated under half_ppr; for other
    formats the season stat columns are re-scored vectorized.
    """
    df = load_latest_preseason(season)
    if df is None or df.empty:
        raise HTTPException(
            status_code=503,
            detail=f"No preseason projections on disk for season {season}.",
        )
    df = df.copy()
    if scoring != "half_ppr":
        df = calculate_fantasy_points_df(
            df, scoring_format=scoring, output_col="projected_season_points"
        )
    return df


def _with_ros(df: pd.DataFrame, from_week: int) -> pd.DataFrame:
    """Add ros_points = season points x remaining-season fraction.

    ponytail: linear proration of the season-long projection; per-week
    re-projection (matchups, injuries) is the upgrade path once weekly
    ROS artifacts exist.
    """
    remaining = max(0, _SEASON_WEEKS - from_week + 1)
    df = df.copy()
    df["ros_points"] = (
        df["projected_season_points"].fillna(0) * remaining / _SEASON_WEEKS
    ).round(1)
    return df


def _to_ros_player(row: Dict[str, Any]) -> RosPlayer:
    vorp = row.get("vorp")
    pos_rank = row.get("position_rank")
    return RosPlayer(
        player_id=str(row.get("player_id") or ""),
        player_name=str(row.get("player_name") or ""),
        team=row.get("team") or row.get("recent_team"),
        position=str(row.get("position") or "").upper(),
        ros_points=float(row.get("ros_points") or 0),
        projected_season_points=float(row.get("projected_season_points") or 0),
        vorp=None if vorp is None or pd.isna(vorp) else float(vorp),
        position_rank=None if pos_rank is None or pd.isna(pos_rank) else int(pos_rank),
    )


def _check_scoring(scoring: str) -> None:
    if scoring not in ("ppr", "half_ppr", "standard"):
        raise HTTPException(status_code=400, detail=f"Invalid scoring: {scoring}")


# ---------------------------------------------------------------------------
# Rest-of-season rankings
# ---------------------------------------------------------------------------


@router.get("/ros", response_model=RosResponse)
def ros_rankings(
    season: int = Query(..., ge=1999, le=2030),
    week: Optional[int] = Query(
        None, ge=1, le=18, description="From-week (default: current)"
    ),
    scoring: str = Query("half_ppr"),
    position: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> RosResponse:
    """Rest-of-season player value rankings (powers trade + waiver decisions)."""
    _check_scoring(scoring)
    from_week = _resolve_week(season, week)
    df = _with_ros(_preseason_scored(season, scoring), from_week)
    if position:
        df = df[df["position"].astype(str).str.upper() == position.upper()]
    df = df.sort_values("ros_points", ascending=False).head(limit)
    return RosResponse(
        season=season,
        from_week=from_week,
        weeks_remaining=max(0, _SEASON_WEEKS - from_week + 1),
        scoring_format=scoring,
        players=[_to_ros_player(r) for r in df.to_dict("records")],
    )


# ---------------------------------------------------------------------------
# Trade analyzer
# ---------------------------------------------------------------------------


def _match_side(df: pd.DataFrame, ids: List[str]) -> TradeSide:
    rows: List[RosPlayer] = []
    unmatched: List[str] = []
    for pid in ids:
        hit = df[df["player_id"].astype(str) == str(pid)]
        if hit.empty:
            unmatched.append(pid)
            continue
        rows.append(_to_ros_player(hit.iloc[0].to_dict()))
    return TradeSide(
        players=rows,
        total_ros_points=round(sum(p.ros_points for p in rows), 1),
        unmatched_player_ids=unmatched,
    )


@router.post("/trade", response_model=TradeResponse)
def evaluate_trade(body: TradeRequest) -> TradeResponse:
    """Evaluate a trade: rest-of-season value of each side + verdict.

    ``side_a`` is what you give away, ``side_b`` what you receive.
    """
    _check_scoring(body.scoring)
    from_week = _resolve_week(body.season, body.week)
    df = _with_ros(_preseason_scored(body.season, body.scoring), from_week)

    side_a = _match_side(df, body.side_a)
    side_b = _match_side(df, body.side_b)
    delta = round(side_b.total_ros_points - side_a.total_ros_points, 1)
    bigger = max(side_a.total_ros_points, side_b.total_ros_points)
    fairness = round(abs(delta) / bigger * 100, 1) if bigger > 0 else 0.0

    if fairness < 5:
        verdict = "Fair trade — near-even rest-of-season value."
    elif delta > 0:
        verdict = (
            f"You win this trade — you gain {delta:+.1f} projected "
            "rest-of-season points."
        )
    else:
        verdict = (
            f"You lose this trade — you give up {abs(delta):.1f} projected "
            "rest-of-season points."
        )
    if side_a.unmatched_player_ids or side_b.unmatched_player_ids:
        verdict += " (Some players had no projection and count as 0.)"

    return TradeResponse(
        season=body.season,
        from_week=from_week,
        scoring_format=body.scoring,
        side_a=side_a,
        side_b=side_b,
        delta_ros_points=delta,
        verdict=verdict,
        fairness_pct=fairness,
    )


# ---------------------------------------------------------------------------
# Start/Sit comparator
# ---------------------------------------------------------------------------


def _opp_rank_lookup(season: int, week: int) -> Dict[tuple, int]:
    """(team, position) → opponent defensive rank for that week's matchup.

    Best-effort: derives each player's opponent from the schedule via the
    lineups service data; returns {} when unavailable.
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
                    / "season=*"
                    / "opp_rankings_*.parquet"
                )
            )
        )
        if not pos_files:
            return {}
        ranks = pd.read_parquet(pos_files[-1])
        ranks = ranks[ranks["week"] <= _SEASON_WEEKS]
        ranks = (
            ranks.sort_values("week")
            .groupby(["team", "position"], as_index=False)
            .last()
        )
        rank_by = {
            (str(r["team"]), str(r["position"]).upper()): int(r["rank"])
            for _, r in ranks.iterrows()
        }
        out: Dict[tuple, int] = {}
        for team, opponent in opp.items():
            for pos in ("QB", "RB", "WR", "TE"):
                if (opponent, pos) in rank_by:
                    out[(team, pos)] = rank_by[(opponent, pos)]
        return out
    except Exception:  # pragma: no cover — any data gap degrades gracefully
        logger.warning("opp-rank lookup failed", exc_info=True)
        return {}


@router.get("/compare", response_model=CompareResponse)
def compare_players(
    ids: str = Query(..., description="Comma-separated player_ids (2-4)"),
    season: int = Query(..., ge=1999, le=2030),
    week: int = Query(..., ge=1, le=18),
    scoring: str = Query("half_ppr"),
) -> CompareResponse:
    """Who-should-I-start: head-to-head weekly comparison of 2-4 players."""
    _check_scoring(scoring)
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if not 2 <= len(id_list) <= 4:
        raise HTTPException(status_code=400, detail="Provide 2-4 player ids.")

    try:
        df = projection_service.get_projections(
            season=season, week=week, scoring_format=scoring, limit=1000
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    ros_df = None
    try:
        ros_df = _with_ros(_preseason_scored(season, scoring), week)
    except HTTPException:
        pass  # ROS is optional context in the weekly comparison

    opp_ranks = _opp_rank_lookup(season, week)

    players: List[ComparePlayer] = []
    for pid in id_list:
        hit = df[df["player_id"].astype(str) == pid]
        if hit.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Player {pid} not found in season={season} week={week}",
            )
        row = hit.iloc[0]
        team = str(row.get("team") or "")
        pos = str(row.get("position") or "").upper()
        ros_pts: Optional[float] = None
        if ros_df is not None:
            ros_hit = ros_df[ros_df["player_id"].astype(str) == pid]
            if not ros_hit.empty:
                ros_pts = float(ros_hit.iloc[0]["ros_points"])
        inj = row.get("injury_status")
        players.append(
            ComparePlayer(
                player_id=pid,
                player_name=str(row.get("player_name") or ""),
                team=team or None,
                position=pos,
                projected_points=float(row.get("projected_points") or 0),
                projected_floor=(
                    float(row["projected_floor"])
                    if pd.notna(row.get("projected_floor"))
                    else None
                ),
                projected_ceiling=(
                    float(row["projected_ceiling"])
                    if pd.notna(row.get("projected_ceiling"))
                    else None
                ),
                injury_status=None if inj is None or pd.isna(inj) else str(inj),
                opp_rank_vs_position=opp_ranks.get((team, pos)),
                ros_points=ros_pts,
            )
        )

    # Recommendation: highest projection; floor breaks near-ties (<0.5 pt).
    best = max(players, key=lambda p: (p.projected_points, p.projected_floor or 0))
    near = [
        p
        for p in players
        if abs(p.projected_points - best.projected_points) < 0.5 and p is not best
    ]
    for p in players:
        p.recommended = p is best
    if near:
        reason = (
            f"Start {best.player_name} — projections are near-even, "
            f"but the floor ({best.projected_floor}) is safer."
        )
    else:
        reason = (
            f"Start {best.player_name} — highest projection "
            f"({best.projected_points:.1f} pts) this week."
        )
    return CompareResponse(
        season=season, week=week, scoring_format=scoring, players=players, reason=reason
    )


# ---------------------------------------------------------------------------
# Auction values
# ---------------------------------------------------------------------------


@router.get("/auction-values", response_model=AuctionResponse)
def auction_values(
    season: int = Query(..., ge=1999, le=2030),
    teams: int = Query(12, ge=4, le=20),
    budget: int = Query(200, ge=50, le=1000),
    scoring: str = Query("half_ppr"),
    limit: int = Query(300, ge=1, le=1000),
) -> AuctionResponse:
    """VORP-proportional auction dollar values for the draft tool.

    Standard method: every rostered player costs $1 minimum; the league's
    discretionary budget is split proportional to positive VORP.
    """
    _check_scoring(scoring)
    df = _preseason_scored(season, scoring)
    if "vorp" not in df.columns:
        raise HTTPException(status_code=503, detail="Preseason parquet lacks vorp.")
    df = df.copy()
    roster_spots = 16  # ponytail: fixed typical roster size; league shape upgrade later
    discretionary = teams * budget - teams * roster_spots
    pos_vorp = df["vorp"].fillna(0).clip(lower=0)
    total_vorp = pos_vorp.sum()
    if total_vorp <= 0:
        raise HTTPException(status_code=503, detail="No positive VORP in projections.")
    df["auction_value"] = (
        (1 + pos_vorp / total_vorp * discretionary).round().astype(int)
    )
    df = df.sort_values("auction_value", ascending=False).head(limit)
    return AuctionResponse(
        season=season,
        n_teams=teams,
        budget_per_team=budget,
        scoring_format=scoring,
        players=[
            AuctionPlayer(
                player_id=str(r.get("player_id") or ""),
                player_name=str(r.get("player_name") or ""),
                team=r.get("team") or r.get("recent_team"),
                position=str(r.get("position") or "").upper(),
                projected_season_points=float(r.get("projected_season_points") or 0),
                vorp=None if pd.isna(r.get("vorp")) else float(r.get("vorp")),
                auction_value=int(r.get("auction_value") or 1),
            )
            for r in df.to_dict("records")
        ],
    )


# ---------------------------------------------------------------------------
# League-wide SOS (defense vs position)
# ---------------------------------------------------------------------------


@router.get("/sos", response_model=SosResponse)
def sos_grid(
    season: Optional[int] = Query(None, ge=1999, le=2030),
) -> SosResponse:
    """All-32-team defense-vs-position grid from the Silver opp_rankings."""
    pattern = str(
        DATA_DIR
        / "silver"
        / "defense"
        / "positional"
        / "season=*"
        / "opp_rankings_*.parquet"
    )
    if season is not None:
        pattern = str(
            DATA_DIR
            / "silver"
            / "defense"
            / "positional"
            / f"season={season}"
            / "opp_rankings_*.parquet"
        )
    files = sorted(glob.glob(pattern))
    if not files:
        raise HTTPException(
            status_code=404, detail="No defense-vs-position data on disk."
        )
    df = pd.read_parquet(files[-1])
    # Regular season only; playoff weeks cover few teams and would shrink the grid.
    df = df[df["week"] <= _SEASON_WEEKS]
    latest_season = int(df["season"].max())
    df = df[df["season"] == latest_season]
    # Latest available row per (team, position) — teams on bye lag a week.
    df = df.sort_values("week").groupby(["team", "position"], as_index=False).last()
    latest_week = int(df["week"].max())
    return SosResponse(
        season=latest_season,
        week=latest_week,
        cells=[
            SosCell(
                team=str(r["team"]),
                position=str(r["position"]).upper(),
                avg_pts_allowed=float(r["avg_pts_allowed"]),
                rank=int(r["rank"]),
            )
            for _, r in df.iterrows()
        ],
    )


# ---------------------------------------------------------------------------
# Depth charts
# ---------------------------------------------------------------------------

_OFFENSE_GROUPS = {"offense"}


@router.get("/depth-charts", response_model=DepthChartResponse)
def depth_charts(
    season: int = Query(..., ge=1999, le=2030),
    team: Optional[str] = Query(None, description="Team abbreviation filter"),
) -> DepthChartResponse:
    """Latest committed depth chart (offense skill positions) per team."""
    files = sorted(
        glob.glob(
            str(DATA_DIR / "bronze" / "depth_charts" / f"season={season}" / "*.parquet")
        )
    )
    if not files:
        raise HTTPException(
            status_code=404, detail=f"No depth charts for season {season}."
        )
    df = pd.read_parquet(files[-1])
    # Parquet accumulates dated snapshots — keep only the newest per team.
    if "dt" in df.columns:
        latest_dt = df.groupby("team")["dt"].transform("max")
        df = df[df["dt"] == latest_dt]
    skill = df[df["pos_abb"].astype(str).str.upper().isin(("QB", "RB", "WR", "TE"))]
    if team:
        skill = skill[skill["team"].astype(str).str.upper() == team.upper()]
    skill = skill.drop_duplicates(subset=["team", "pos_abb", "pos_rank", "player_name"])
    skill = skill.sort_values(["team", "pos_abb", "pos_rank"])
    as_of = str(df["dt"].max()) if "dt" in df.columns and len(df) else None
    return DepthChartResponse(
        season=season,
        as_of=as_of,
        entries=[
            DepthChartEntry(
                team=str(r["team"]),
                position=str(r["pos_abb"]).upper(),
                player_name=str(r["player_name"]),
                depth_rank=int(r["pos_rank"]),
                gsis_id=str(r["gsis_id"]) if pd.notna(r.get("gsis_id")) else None,
            )
            for _, r in skill.iterrows()
        ],
    )


# ---------------------------------------------------------------------------
# Injury report
# ---------------------------------------------------------------------------


@router.get("/injuries", response_model=InjuryResponse)
def injury_report(
    season: int = Query(..., ge=1999, le=2030),
    week: int = Query(..., ge=1, le=18),
    scoring: str = Query("half_ppr"),
) -> InjuryResponse:
    """Fantasy-relevant players carrying an injury designation this week."""
    _check_scoring(scoring)
    try:
        df = projection_service.get_projections(
            season=season, week=week, scoring_format=scoring, limit=1000
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if "injury_status" not in df.columns:
        return InjuryResponse(season=season, week=week, players=[])
    inj = df[df["injury_status"].notna() & (df["injury_status"].astype(str) != "")]
    inj = inj.sort_values("projected_points", ascending=False)
    return InjuryResponse(
        season=season,
        week=week,
        players=[
            InjuryRow(
                player_id=str(r.get("player_id") or ""),
                player_name=str(r.get("player_name") or ""),
                team=r.get("team"),
                position=str(r.get("position") or "").upper(),
                injury_status=str(r.get("injury_status")),
                projected_points=float(r.get("projected_points") or 0),
            )
            for r in inj.to_dict("records")
        ],
    )
