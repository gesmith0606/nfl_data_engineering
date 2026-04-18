"""
/api/draft endpoints -- fantasy draft session management.

Wraps the existing ``src/draft_optimizer.py`` engine (DraftBoard, DraftAdvisor,
MockDraftSimulator, compute_value_scores) in stateful HTTP endpoints using
in-memory session storage keyed by UUID.
"""

import glob
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import (
    AdpPlayer,
    AdpResponse,
    DraftBoardEntry,
    DraftBoardResponse,
    DraftPickRequest,
    DraftPickResponse,
    DraftPlayer,
    DraftRecommendation,
    DraftRecommendationsResponse,
    MockDraftPickRequest,
    MockDraftPickResponse,
    MockDraftStartRequest,
    MockDraftStartResponse,
)

# ---------------------------------------------------------------------------
# Path setup -- same pattern as lineups.py
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from draft_optimizer import (  # noqa: E402
    DraftAdvisor,
    DraftBoard,
    MockDraftSimulator,
    compute_value_scores,
)
from nfl_data_integration import NFLDataFetcher  # noqa: E402
from projection_engine import generate_preseason_projections  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/draft", tags=["draft"])

# ---------------------------------------------------------------------------
# Session storage  (in-memory, keyed by UUID hex string)
# ---------------------------------------------------------------------------
# Threat T-W9-02: cap concurrent sessions to prevent DoS via expensive
# projection generation.
_MAX_SESSIONS = 100

_sessions: Dict[str, Dict] = {}


def _evict_oldest() -> None:
    """Remove the oldest session when the cap is reached."""
    if len(_sessions) < _MAX_SESSIONS:
        return
    oldest_key = min(_sessions, key=lambda k: _sessions[k].get("created_at", ""))
    del _sessions[oldest_key]
    logger.info("Evicted oldest draft session %s (cap=%d)", oldest_key, _MAX_SESSIONS)


def _get_session(session_id: str) -> Dict:
    """Retrieve a session or raise 404."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _safe_float(val: object) -> Optional[float]:
    """Convert a value to float, returning None for NaN / missing."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_int(val: object, default: int = 0) -> int:
    """Convert a value to int, returning *default* for NaN / missing."""
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:
            return default
        return int(f)
    except (ValueError, TypeError):
        return default


def _load_cached_projections(scoring: str, season: int) -> Optional[pd.DataFrame]:
    """Attempt to load cached Gold preseason projections from local Parquet files.

    Args:
        scoring: Scoring format key (used for logging only; cached files are
                 format-agnostic since points are already computed).
        season:  NFL season year.

    Returns:
        DataFrame of cached projections, or ``None`` if no cache is available.
    """
    cache_dir = (
        _PROJECT_ROOT
        / "data"
        / "gold"
        / "projections"
        / "preseason"
        / f"season={season}"
    )
    pattern = str(cache_dir / "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    try:
        df = pd.read_parquet(files[-1])  # latest by filename timestamp
        logger.info(
            "Loaded %d cached preseason projections from %s", len(df), files[-1]
        )
        return df
    except Exception:
        logger.warning("Failed to read cached projection file %s", files[-1])
        return None


def _load_draft_data(scoring: str, season: int) -> pd.DataFrame:
    """Generate projections, load ADP (if available), and compute value scores.

    Attempts live data fetch first.  When the upstream NFL data API is
    unavailable (common during the offseason), falls back to cached Gold
    preseason projections stored as local Parquet files.

    Args:
        scoring: Scoring format key (e.g. ``"half_ppr"``).
        season:  NFL season year.

    Returns:
        Enriched projection DataFrame ready for ``DraftBoard``.
    """
    projections: Optional[pd.DataFrame] = None

    # --- Strategy 1: live fetch + projection generation ---
    try:
        fetcher = NFLDataFetcher()
        past_seasons = [season - 2, season - 1]
        seasonal_df = fetcher.fetch_player_seasonal(past_seasons)
        projections = generate_preseason_projections(
            seasonal_df, scoring_format=scoring, target_season=season
        )
        if projections.empty:
            projections = None
    except Exception as exc:
        logger.warning("Live data fetch failed, will try cached projections: %s", exc)

    # --- Strategy 2: cached Gold preseason projections ---
    if projections is None:
        projections = _load_cached_projections(scoring, season)

    if projections is None or projections.empty:
        raise ValueError(
            f"No projection data available for {season}. "
            "NFL data API may be offline and no cached projections exist. "
            "Run 'python scripts/generate_projections.py --preseason "
            f"--season {season}' when the API is reachable to populate the cache."
        )

    # Try loading ADP data
    adp_path = _PROJECT_ROOT / "data" / "adp_latest.csv"
    adp_df: Optional[pd.DataFrame] = None
    if adp_path.exists():
        try:
            adp_df = pd.read_csv(str(adp_path))
        except Exception:
            logger.warning("Failed to read ADP file at %s", adp_path)

    return compute_value_scores(projections, adp_df)


def _df_row_to_draft_player(row: pd.Series) -> DraftPlayer:
    """Convert a single DataFrame row to a ``DraftPlayer`` schema."""
    pts_col = (
        "projected_season_points"
        if "projected_season_points" in row.index
        else "projected_points"
    )
    return DraftPlayer(
        player_id=str(row.get("player_id", "")),
        player_name=str(row.get("player_name", "")),
        position=str(row.get("position", "")),
        team=str(row.get("recent_team", row.get("team", ""))) or None,
        projected_points=round(float(row.get(pts_col, 0) or 0), 1),
        model_rank=_safe_int(row.get("model_rank"), 999),
        adp_rank=_safe_float(row.get("adp_rank")),
        adp_diff=_safe_float(row.get("adp_diff")),
        value_tier=str(row.get("value_tier", "fair_value")),
        vorp=round(float(row.get("vorp", 0) or 0), 1),
    )


def _df_row_to_board_entry(row: pd.Series) -> DraftBoardEntry:
    """Convert a DataFrame row to an advisor-facing ``DraftBoardEntry``.

    The advisor schema (``getDraftBoard`` in ``chat/route.ts``) expects the
    friendlier ``adp`` / ``bye_week`` field names instead of ``adp_rank``.
    ``bye_week`` is passed through when the projection DataFrame carries it
    (it comes from ``generate_preseason_projections``); otherwise ``None``.
    """
    pts_col = (
        "projected_season_points"
        if "projected_season_points" in row.index
        else "projected_points"
    )
    bye_week_raw = row.get("bye_week") if "bye_week" in row.index else None
    bye_week = _safe_int(bye_week_raw, default=0) if bye_week_raw is not None else None
    if bye_week == 0 and bye_week_raw in (None, ""):
        bye_week = None
    return DraftBoardEntry(
        player_id=str(row.get("player_id", "")),
        player_name=str(row.get("player_name", "")),
        position=str(row.get("position", "")),
        team=str(row.get("recent_team", row.get("team", ""))) or None,
        projected_points=round(float(row.get(pts_col, 0) or 0), 1),
        adp=_safe_float(row.get("adp_rank")),
        vorp=round(float(row.get("vorp", 0) or 0), 1),
        value_tier=str(row.get("value_tier", "fair_value")),
        bye_week=bye_week,
    )


def _dict_to_draft_player(d: Dict) -> DraftPlayer:
    """Convert a player dict (from ``board.my_roster``) to ``DraftPlayer``."""
    pts_col = (
        "projected_season_points"
        if "projected_season_points" in d
        else "projected_points"
    )
    return DraftPlayer(
        player_id=str(d.get("player_id", "")),
        player_name=str(d.get("player_name", "")),
        position=str(d.get("position", "")),
        team=str(d.get("recent_team", d.get("team", ""))) or None,
        projected_points=round(float(d.get(pts_col, 0) or 0), 1),
        model_rank=_safe_int(d.get("model_rank"), 999),
        adp_rank=_safe_float(d.get("adp_rank")),
        adp_diff=_safe_float(d.get("adp_diff")),
        value_tier=str(d.get("value_tier", "fair_value")),
        vorp=round(float(d.get("vorp", 0) or 0), 1),
    )


def _board_to_response(session_id: str, session: Dict) -> DraftBoardResponse:
    """Build a ``DraftBoardResponse`` from a session dict.

    Populates two parallel views of the available player set:

    * ``players`` — full :class:`DraftPlayer` schema (model_rank, adp_rank,
      adp_diff) consumed by the draft page.
    * ``board`` — advisor-facing :class:`DraftBoardEntry` (adp, bye_week)
      consumed by the AI chat tool.
    """
    board: DraftBoard = session["board"]

    available_players: List[DraftPlayer] = []
    board_entries: List[DraftBoardEntry] = []
    for _, row in board.available.iterrows():
        available_players.append(_df_row_to_draft_player(row))
        board_entries.append(_df_row_to_board_entry(row))

    my_roster: List[DraftPlayer] = [_dict_to_draft_player(p) for p in board.my_roster]

    return DraftBoardResponse(
        session_id=session_id,
        players=available_players,
        board=board_entries,
        my_roster=my_roster,
        picks_taken=board.picks_taken(),
        my_pick_count=board.my_pick_count(),
        remaining_needs=board.remaining_needs(),
        scoring_format=session.get("scoring_format", "half_ppr"),
        roster_format=session.get("roster_format", "standard"),
        n_teams=board.n_teams,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/board", response_model=DraftBoardResponse)
def get_draft_board(
    scoring: str = Query(
        "half_ppr",
        description="Scoring format",
        pattern="^(ppr|half_ppr|standard)$",
    ),
    roster_format: str = Query(
        "standard",
        description="Roster format",
        pattern="^(standard|superflex|2qb)$",
    ),
    n_teams: int = Query(12, ge=4, le=20, description="Number of teams"),
    season: int = Query(2026, ge=2020, le=2030, description="NFL season"),
    session_id: Optional[str] = Query(None, description="Reuse an existing session"),
) -> DraftBoardResponse:
    """Return the current draft board.

    If ``session_id`` is provided and valid, the existing session is returned.
    Otherwise a new session is created with fresh projections.
    """
    if session_id and session_id in _sessions:
        return _board_to_response(session_id, _sessions[session_id])

    # Create a new session
    _evict_oldest()
    try:
        players_df = _load_draft_data(scoring, season)
    except Exception as exc:
        logger.exception("Failed to generate draft data")
        raise HTTPException(
            status_code=500, detail=f"Draft data generation failed: {exc}"
        ) from exc

    board = DraftBoard(players_df, roster_format=roster_format, n_teams=n_teams)
    board.scoring_format = scoring
    advisor = DraftAdvisor(board, scoring_format=scoring)

    new_id = uuid.uuid4().hex
    _sessions[new_id] = {
        "board": board,
        "advisor": advisor,
        "simulator": None,
        "scoring_format": scoring,
        "roster_format": roster_format,
        "pick_number": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return _board_to_response(new_id, _sessions[new_id])


@router.post("/pick", response_model=DraftPickResponse)
def record_pick(req: DraftPickRequest) -> DraftPickResponse:
    """Record a draft pick for the given session.

    ``player_id`` must match a player still on the available board.
    """
    session = _get_session(req.session_id)
    board: DraftBoard = session["board"]

    try:
        result = board.draft_player(req.player_id, by_me=req.by_me)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result:
        raise HTTPException(
            status_code=400,
            detail=f"Player '{req.player_id}' not found in available pool",
        )

    return DraftPickResponse(
        success=True,
        player=_dict_to_draft_player(result),
        message=f"Drafted {result.get('player_name', req.player_id)}",
    )


@router.get("/recommendations", response_model=DraftRecommendationsResponse)
def get_recommendations(
    session_id: str = Query(..., description="Draft session ID"),
    top_n: int = Query(5, ge=1, le=25, description="Number of recommendations"),
    position: Optional[str] = Query(
        None, description="Filter by position (QB/RB/WR/TE)"
    ),
) -> DraftRecommendationsResponse:
    """Return ranked pick recommendations for the current board state."""
    session = _get_session(session_id)
    advisor: DraftAdvisor = session["advisor"]

    if position:
        positions = [position.upper()]
        recs_df = advisor.best_available(positions=positions, top_n=top_n)
        reasoning = f"Best available {position.upper()} players"
    else:
        recs_df, reasoning = advisor.recommend(top_n=top_n)

    pts_col = (
        "projected_season_points"
        if "projected_season_points" in recs_df.columns
        else "projected_points"
    )

    recommendations: List[DraftRecommendation] = []
    for _, row in recs_df.iterrows():
        recommendations.append(
            DraftRecommendation(
                player_id=str(row.get("player_id", "")),
                player_name=str(row.get("player_name", "")),
                position=str(row.get("position", "")),
                team=str(row.get("recent_team", row.get("team", ""))) or None,
                projected_points=round(float(row.get(pts_col, 0) or 0), 1),
                model_rank=_safe_int(row.get("model_rank"), 999),
                vorp=round(float(row.get("vorp", 0) or 0), 1),
                recommendation_score=round(
                    float(row.get("recommendation_score", row.get(pts_col, 0)) or 0), 1
                ),
            )
        )

    board: DraftBoard = session["board"]
    return DraftRecommendationsResponse(
        recommendations=recommendations,
        reasoning=reasoning,
        remaining_needs=board.remaining_needs(),
    )


@router.post("/mock/start", response_model=MockDraftStartResponse)
def start_mock_draft(req: MockDraftStartRequest) -> MockDraftStartResponse:
    """Initialize a new mock draft simulation session."""
    if req.user_pick < 1 or req.user_pick > req.n_teams:
        raise HTTPException(
            status_code=400,
            detail=f"user_pick must be between 1 and {req.n_teams}",
        )

    _evict_oldest()
    try:
        players_df = _load_draft_data(req.scoring, req.season)
    except Exception as exc:
        logger.exception("Failed to generate mock draft data")
        raise HTTPException(
            status_code=500, detail=f"Draft data generation failed: {exc}"
        ) from exc

    board = DraftBoard(players_df, roster_format=req.roster_format, n_teams=req.n_teams)
    board.scoring_format = req.scoring
    advisor = DraftAdvisor(board, scoring_format=req.scoring)
    simulator = MockDraftSimulator(
        board=board, user_pick=req.user_pick, n_teams=req.n_teams
    )

    new_id = uuid.uuid4().hex
    _sessions[new_id] = {
        "board": board,
        "advisor": advisor,
        "simulator": simulator,
        "scoring_format": req.scoring,
        "roster_format": req.roster_format,
        "pick_number": 0,
        "user_pick": req.user_pick,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return MockDraftStartResponse(
        session_id=new_id,
        message=f"Mock draft started: {req.n_teams} teams, pick #{req.user_pick}, {req.scoring}",
    )


@router.post("/mock/pick", response_model=MockDraftPickResponse)
def advance_mock_pick(req: MockDraftPickRequest) -> MockDraftPickResponse:
    """Advance one pick in a mock draft simulation.

    On the user's turn the advisor's top recommendation is auto-drafted.
    On opponent turns an ADP-based pick with randomness is simulated.
    """
    session = _get_session(req.session_id)
    simulator: Optional[MockDraftSimulator] = session.get("simulator")
    if simulator is None:
        raise HTTPException(
            status_code=400, detail="Session has no mock draft simulator"
        )

    board: DraftBoard = session["board"]
    advisor: DraftAdvisor = session["advisor"]

    # Total picks in the draft
    total_picks = board.n_teams * sum(board.roster_config.values())
    pick_number = session.get("pick_number", 0) + 1

    if pick_number > total_picks or board.available.empty:
        # Draft is complete -- compute final results
        pts_col = (
            "projected_season_points"
            if "projected_season_points" in board.all_players.columns
            else "projected_points"
        )
        total_pts = sum(float(p.get(pts_col, 0) or 0) for p in board.my_roster)
        total_vorp = sum(float(p.get("vorp", 0) or 0) for p in board.my_roster)
        return MockDraftPickResponse(
            pick_number=pick_number - 1,
            round_number=(pick_number - 2) // board.n_teams + 1,
            is_user_turn=False,
            is_complete=True,
            draft_grade="B",
            total_pts=round(total_pts, 1),
            total_vorp=round(total_vorp, 1),
        )

    session["pick_number"] = pick_number
    round_number = (pick_number - 1) // board.n_teams + 1
    is_user_turn = simulator._is_user_turn(pick_number)

    player_name: Optional[str] = None
    position: Optional[str] = None
    team: Optional[str] = None

    if is_user_turn:
        recs, _ = advisor.recommend(top_n=1)
        if not recs.empty:
            top = recs.iloc[0]
            pid = str(top.get("player_id", top.get("player_name", "")))
            result = board.draft_player(pid, by_me=True)
            if result:
                player_name = result.get("player_name")
                position = result.get("position")
                team = result.get("recent_team", result.get("team"))
    else:
        player_name = simulator.simulate_opponent_pick(pick_number)
        if player_name and "player_name" in board.all_players.columns:
            match = board.all_players[board.all_players["player_name"] == player_name]
            if not match.empty:
                position = str(match.iloc[0].get("position", ""))
                team = str(
                    match.iloc[0].get("recent_team", match.iloc[0].get("team", ""))
                )

    # Check if draft is now complete
    next_pick = pick_number + 1
    is_complete = next_pick > total_picks or board.available.empty

    draft_grade: Optional[str] = None
    total_pts: Optional[float] = None
    total_vorp: Optional[float] = None
    if is_complete:
        pts_col = (
            "projected_season_points"
            if "projected_season_points" in board.all_players.columns
            else "projected_points"
        )
        total_pts = round(
            sum(float(p.get(pts_col, 0) or 0) for p in board.my_roster), 1
        )
        total_vorp = round(
            sum(float(p.get("vorp", 0) or 0) for p in board.my_roster), 1
        )
        expected_vorp = simulator._estimate_expected_vorp(total_picks)
        from draft_optimizer import _pick_grade

        draft_grade = _pick_grade(total_vorp, expected_vorp)

    return MockDraftPickResponse(
        pick_number=pick_number,
        round_number=round_number,
        is_user_turn=is_user_turn,
        player_name=player_name,
        position=position,
        team=str(team) if team else None,
        is_complete=is_complete,
        draft_grade=draft_grade,
        total_pts=total_pts,
        total_vorp=total_vorp,
    )


@router.get("/adp", response_model=AdpResponse)
def get_adp() -> AdpResponse:
    """Return the latest ADP data from ``data/adp_latest.csv``.

    Returns 404 if the ADP file does not exist.
    """
    adp_path = _PROJECT_ROOT / "data" / "adp_latest.csv"
    if not adp_path.exists():
        raise HTTPException(status_code=404, detail="ADP data file not found")

    try:
        df = pd.read_csv(str(adp_path))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to read ADP file: {exc}"
        ) from exc

    # Normalise column names
    name_col = next(
        (c for c in df.columns if c.lower() in ("player_name", "name", "player")),
        df.columns[0],
    )
    pos_col = next(
        (c for c in df.columns if c.lower() in ("position", "pos")),
        None,
    )
    team_col = next(
        (c for c in df.columns if c.lower() in ("team", "recent_team")),
        None,
    )
    rank_col = next(
        (c for c in df.columns if c.lower() in ("adp_rank", "adp", "rank")),
        None,
    )

    players: List[AdpPlayer] = []
    for _, row in df.iterrows():
        players.append(
            AdpPlayer(
                player_name=str(row[name_col]),
                position=str(row[pos_col]) if pos_col else "UNK",
                team=(
                    str(row[team_col]) if team_col and pd.notna(row[team_col]) else None
                ),
                adp_rank=(
                    float(row[rank_col])
                    if rank_col and pd.notna(row[rank_col])
                    else 0.0
                ),
            )
        )

    # Try to get file modification time for updated_at
    import os

    stat = os.stat(str(adp_path))
    updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

    return AdpResponse(
        players=players,
        source="adp_latest.csv",
        updated_at=updated_at,
    )
