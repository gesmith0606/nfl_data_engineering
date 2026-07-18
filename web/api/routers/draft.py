"""
/api/draft endpoints -- fantasy draft session management.

Wraps the existing ``src/draft_optimizer.py`` engine (DraftBoard, DraftAdvisor,
MockDraftSimulator, compute_value_scores) in stateful HTTP endpoints using
in-memory session storage keyed by UUID.
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    DraftSyncLogRequest,
    DraftSyncLogResponse,
    LiveDraftKeyMoment,
    LiveDraftRecommendation,
    LiveDraftResponse,
    MockDraftPickRequest,
    MockDraftPickResponse,
    MockDraftStartRequest,
    MockDraftStartResponse,
    PlatformPreset,
    PlatformPresetsResponse,
)

# src/ is importable via the web.api package bootstrap (web/api/__init__.py).
# _PROJECT_ROOT is still used below for data-file paths (ADP csv).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

from draft_optimizer import (  # noqa: E402
    DraftAdvisor,
    DraftBoard,
    MockDraftSimulator,
    compute_value_scores,
)
from draft_availability import prob_gone_before_vectorized  # noqa: E402
from draft_tiers import compute_tiers  # noqa: E402
from nfl_data_integration import NFLDataFetcher  # noqa: E402
from projection_engine import generate_preseason_projections  # noqa: E402

# Canonical preseason loader (src/projection_store.py) — imported via the
# ``src.`` package path so this router shares one module instance (and thus
# one lru read-cache) with the league router and the CLI co-pilot.
from src.projection_store import load_latest_preseason  # noqa: E402

# Platform-faithful draft presets (v8.3 draft-tool upgrade).
from src.config import PLATFORM_PRESETS, ROSTER_CONFIGS  # noqa: E402

# Live-draft co-pilot wiring (v8.0): read a live Sleeper draft and drive our
# roster-aware recommendation engine. Imported lazily-safe at module load so a
# missing optional dep never breaks the mock-draft endpoints above.
from draft_adapter import SleeperAdapter  # noqa: E402
from draft_paste_sync import build_name_lookup, parse_pick_log  # noqa: E402
from live_draft_engine import LiveDraftEngine  # noqa: E402
from sleeper_draft import load_draft_state, resolve_active_draft  # noqa: E402
from yahoo_adapter import YahooAdapter  # noqa: E402
from yahoo_oauth import YahooOAuth  # noqa: E402

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


def _finite_or_zero(val: object) -> float:
    """Like ``_safe_float`` but for summation contexts: NaN/missing -> 0.0.

    Used when aggregating projected points/VORP across a roster that may
    include a DST row (ADP-only, no projection) — treating its unprojected
    contribution as 0 keeps roster totals finite instead of NaN-poisoned.
    """
    f = _safe_float(val)
    return f if f is not None else 0.0


def _safe_round(val: object, ndigits: int = 1) -> Optional[float]:
    """Round a value to *ndigits*, returning ``None`` for NaN/missing.

    Positions our model doesn't project (DST is ADP-only) carry NaN
    projected_points/vorp — this keeps them as JSON ``null`` rather than the
    non-standard ``NaN`` token or a fabricated ``0.0``.
    """
    f = _safe_float(val)
    return round(f, ndigits) if f is not None else None


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


def _safe_tier(val: object) -> Optional[int]:
    """Convert a tier value to int, returning None for NaN / missing.

    Distinct from :func:`_safe_int` (which has a numeric default) because a
    missing tier is a meaningful ``None`` (e.g. DST has no points to tier),
    not a sentinel default.
    """
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return int(f)
    except (ValueError, TypeError):
        return None


def _load_cached_projections(scoring: str, season: int) -> Optional[pd.DataFrame]:
    """Attempt to load cached Gold preseason projections from local Parquet files.

    Thin wrapper over :func:`src.projection_store.load_latest_preseason` —
    the canonical loader shared with the league router and the CLI draft
    co-pilot.  The loader lru-caches the parquet read keyed on file path
    (the live-draft endpoint polls every ~5s), so a newer artifact with a
    fresh filename timestamp naturally busts the cache.

    Args:
        scoring: Scoring format key (unused; cached files are format-agnostic
                 since points are already computed — kept for signature
                 stability with callers and tests).
        season:  NFL season year.

    Returns:
        DataFrame of cached projections, or ``None`` if no cache is available.
        The frame is a shared, cached read — treat it as read-only.
    """
    return load_latest_preseason(season)


def _load_draft_data(scoring: str, season: int) -> pd.DataFrame:
    """Load projections, load ADP (if available), and compute value scores.

    Prefers the cached Gold preseason artifact so the web API serves the same
    consensus-anchored projections (with full player names, which the ADP merge
    depends on) as the CLI draft co-pilot.  Falls back to a live fetch +
    on-the-fly projection generation only when no cached artifact exists.

    ``compute_value_scores`` is always applied afterwards: the Gold artifact
    carries raw projections only (no vorp/model_rank/adp_rank columns), and
    merging ADP at request time keeps value tiers fresh with ``adp_latest.csv``.

    Args:
        scoring: Scoring format key (e.g. ``"half_ppr"``).
        season:  NFL season year.

    Returns:
        Enriched projection DataFrame ready for ``DraftBoard``.
    """
    # --- Strategy 1: cached Gold preseason projections ---
    projections: Optional[pd.DataFrame] = _load_cached_projections(scoring, season)

    # --- Strategy 2: live fetch + projection generation ---
    if projections is None or projections.empty:
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
            logger.warning("Live projection generation failed: %s", exc)
            projections = None

    if projections is None or projections.empty:
        raise ValueError(
            f"No projection data available for {season}. "
            "NFL data API may be offline and no cached projections exist. "
            "Run 'python scripts/generate_projections.py --preseason "
            f"--season {season}' when the API is reachable to populate the cache."
        )

    enriched = compute_value_scores(projections, _load_adp_df())
    # Positional tiers computed once on the full pre-draft pool so tier
    # numbers stay stable as players come off the board (recomputing per
    # available-only slice would renumber tiers mid-draft).
    enriched["tier"] = compute_tiers(enriched)
    return enriched


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
        projected_points=_safe_round(row.get(pts_col)),
        model_rank=_safe_int(row.get("model_rank"), 999),
        adp_rank=_safe_float(row.get("adp_rank")),
        adp_diff=_safe_float(row.get("adp_diff")),
        adp_stdev=_safe_float(row.get("adp_stdev")),
        value_tier=str(row.get("value_tier", "fair_value")),
        vorp=_safe_round(row.get("vorp")),
        tier=_safe_tier(row.get("tier")),
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
        projected_points=_safe_round(row.get(pts_col)),
        adp=_safe_float(row.get("adp_rank")),
        adp_stdev=_safe_float(row.get("adp_stdev")),
        vorp=_safe_round(row.get("vorp")),
        value_tier=str(row.get("value_tier", "fair_value")),
        bye_week=bye_week,
        tier=_safe_tier(row.get("tier")),
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
        projected_points=_safe_round(d.get(pts_col)),
        model_rank=_safe_int(d.get("model_rank"), 999),
        adp_rank=_safe_float(d.get("adp_rank")),
        adp_diff=_safe_float(d.get("adp_diff")),
        adp_stdev=_safe_float(d.get("adp_stdev")),
        value_tier=str(d.get("value_tier", "fair_value")),
        vorp=_safe_round(d.get("vorp")),
        tier=_safe_tier(d.get("tier")),
    )


def _user_next_pick_number(
    session: Dict, board: DraftBoard, user_pick: Optional[int]
) -> Optional[int]:
    """Overall pick number of the user's next pick, via snake/linear math.

    Prefers the session's own mock-draft ``user_pick`` (set by
    ``/draft/mock/start``) so gone-probability works for a mock draft in
    progress without any extra query params; falls back to an explicit
    ``user_pick`` query param for plain board sessions that have no
    simulator. Returns ``None`` (caller degrades to no gone_probability)
    when neither is available.
    """
    slot = session.get("user_pick") or user_pick
    if not slot:
        return None
    simulator: Optional[MockDraftSimulator] = session.get("simulator")
    draft_type = getattr(simulator, "draft_type", "snake") if simulator else "snake"
    n_teams = board.n_teams
    if n_teams <= 0:
        return None
    start_pick = board.picks_taken() + 1
    for pick_no in range(start_pick, start_pick + n_teams * 2 + 1):
        pick_in_round = (pick_no - 1) % n_teams + 1
        if draft_type == "linear":
            slot_on_clock = pick_in_round
        else:
            round_number = (pick_no - 1) // n_teams + 1
            slot_on_clock = (
                pick_in_round if round_number % 2 == 1 else n_teams - pick_in_round + 1
            )
        if slot_on_clock == slot:
            return pick_no
    return None


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
    scoring: Optional[str] = Query(
        None,
        description="Scoring format; defaults from platform preset, else half_ppr",
        pattern="^(ppr|half_ppr|standard)$",
    ),
    roster_format: Optional[str] = Query(
        None,
        description="Roster format; defaults from platform preset, else standard",
        pattern="^(standard|superflex|2qb|espn_default|sleeper_default|yahoo_default)$",
    ),
    n_teams: int = Query(12, ge=4, le=20, description="Number of teams"),
    season: int = Query(2026, ge=2020, le=2030, description="NFL season"),
    session_id: Optional[str] = Query(None, description="Reuse an existing session"),
    platform: Optional[str] = Query(
        None,
        description=(
            "Platform preset (espn/sleeper/yahoo/custom, see GET /draft/"
            "platforms) — fills in scoring/roster_format when omitted"
        ),
        pattern="^(espn|sleeper|yahoo|custom)$",
    ),
) -> DraftBoardResponse:
    """Return the current draft board.

    If ``session_id`` is provided and valid, the existing session is returned.
    Otherwise a new session is created with fresh projections. When
    ``platform`` is given, any of ``scoring``/``roster_format`` left unset
    default from that platform's preset (``PLATFORM_PRESETS`` in
    ``src/config.py``); an explicit value always wins over the preset.
    """
    if session_id and session_id in _sessions:
        return _board_to_response(session_id, _sessions[session_id])

    preset = PLATFORM_PRESETS.get(platform) if platform else None
    resolved_scoring = scoring or (preset or {}).get("scoring_format") or "half_ppr"
    resolved_roster_format = (
        roster_format or (preset or {}).get("roster") or "standard"
    )

    # Create a new session
    _evict_oldest()
    try:
        players_df = _load_draft_data(resolved_scoring, season)
    except Exception as exc:
        logger.exception("Failed to generate draft data")
        raise HTTPException(
            status_code=500, detail=f"Draft data generation failed: {exc}"
        ) from exc

    board = DraftBoard(players_df, roster_format=resolved_roster_format, n_teams=n_teams)
    board.scoring_format = resolved_scoring
    advisor = DraftAdvisor(board, scoring_format=resolved_scoring)

    new_id = uuid.uuid4().hex
    _sessions[new_id] = {
        "board": board,
        "advisor": advisor,
        "simulator": None,
        "scoring_format": resolved_scoring,
        "roster_format": resolved_roster_format,
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
    user_pick: Optional[int] = Query(
        None,
        ge=1,
        le=20,
        description=(
            "Your draft slot, used to compute gone_probability at your next "
            "pick. Not needed for a mock-draft session (uses the slot set at "
            "/draft/mock/start); required for a plain board session."
        ),
    ),
) -> DraftRecommendationsResponse:
    """Return ranked pick recommendations for the current board state."""
    session = _get_session(session_id)
    advisor: DraftAdvisor = session["advisor"]
    board: DraftBoard = session["board"]

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

    # gone_probability: chance each candidate is drafted before the user's
    # next pick. Computed once, vectorized, over the whole recs frame.
    gone_prob: Optional[pd.Series] = None
    next_pick_no = _user_next_pick_number(session, board, user_pick)
    if next_pick_no is not None and not recs_df.empty and "adp_rank" in recs_df.columns:
        gone_prob = prob_gone_before_vectorized(recs_df, next_pick_no)

    recommendations: List[DraftRecommendation] = []
    for _, row in recs_df.iterrows():
        gp = None
        if gone_prob is not None:
            gp_val = gone_prob.get(row.name)
            gp = float(gp_val) if gp_val is not None and pd.notna(gp_val) else None
        recommendations.append(
            DraftRecommendation(
                player_id=str(row.get("player_id", "")),
                player_name=str(row.get("player_name", "")),
                position=str(row.get("position", "")),
                team=str(row.get("recent_team", row.get("team", ""))) or None,
                projected_points=_safe_round(row.get(pts_col)),
                model_rank=_safe_int(row.get("model_rank"), 999),
                vorp=_safe_round(row.get("vorp")),
                recommendation_score=round(
                    _finite_or_zero(row.get("recommendation_score", row.get(pts_col))),
                    1,
                ),
                gone_probability=round(gp, 3) if gp is not None else None,
            )
        )

    return DraftRecommendationsResponse(
        recommendations=recommendations,
        reasoning=reasoning,
        remaining_needs=board.remaining_needs(),
    )


@router.post("/mock/start", response_model=MockDraftStartResponse)
def start_mock_draft(req: MockDraftStartRequest) -> MockDraftStartResponse:
    """Initialize a new mock draft simulation session.

    When ``req.platform`` is set, any of ``scoring``/``roster_format`` left
    unset (``None``) default from that platform's preset
    (``PLATFORM_PRESETS`` in ``src/config.py``).
    """
    if req.user_pick < 1 or req.user_pick > req.n_teams:
        raise HTTPException(
            status_code=400,
            detail=f"user_pick must be between 1 and {req.n_teams}",
        )

    preset = PLATFORM_PRESETS.get(req.platform) if req.platform else None
    scoring = req.scoring or (preset or {}).get("scoring_format") or "half_ppr"
    roster_format = req.roster_format or (preset or {}).get("roster") or "standard"

    _evict_oldest()
    try:
        players_df = _load_draft_data(scoring, req.season)
    except Exception as exc:
        logger.exception("Failed to generate mock draft data")
        raise HTTPException(
            status_code=500, detail=f"Draft data generation failed: {exc}"
        ) from exc

    board = DraftBoard(players_df, roster_format=roster_format, n_teams=req.n_teams)
    board.scoring_format = scoring
    advisor = DraftAdvisor(board, scoring_format=scoring)
    simulator = MockDraftSimulator(
        board=board, user_pick=req.user_pick, n_teams=req.n_teams
    )

    new_id = uuid.uuid4().hex
    _sessions[new_id] = {
        "board": board,
        "advisor": advisor,
        "simulator": simulator,
        "scoring_format": scoring,
        "roster_format": roster_format,
        "pick_number": 0,
        "user_pick": req.user_pick,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return MockDraftStartResponse(
        session_id=new_id,
        message=f"Mock draft started: {req.n_teams} teams, pick #{req.user_pick}, {scoring}",
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
        total_pts = sum(_finite_or_zero(p.get(pts_col)) for p in board.my_roster)
        total_vorp = sum(_finite_or_zero(p.get("vorp")) for p in board.my_roster)
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
                simulator.record_pick(position)  # keep positional-run tracking in sync
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
            sum(_finite_or_zero(p.get(pts_col)) for p in board.my_roster), 1
        )
        total_vorp = round(
            sum(_finite_or_zero(p.get("vorp")) for p in board.my_roster), 1
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
def get_adp(
    source: Optional[str] = Query(
        None,
        pattern="^(ffc|espn|sleeper)$",
        description=(
            "Real-ADP source (ffc/espn) or the legacy sleeper_rank path; "
            "reads data/adp/adp_{source}_{scoring}.csv, falling back to "
            "data/adp_latest.csv when that file doesn't exist. Omit for the "
            "legacy data/adp_latest.csv pointer directly."
        ),
    ),
    scoring: str = Query(
        "half_ppr",
        pattern="^(ppr|half_ppr|standard)$",
        description="Scoring format; only used to locate the per-source file",
    ),
) -> AdpResponse:
    """Return ADP data, optionally from a specific real-ADP source.

    Returns 404 if no ADP file could be found (neither the per-source file
    nor the ``adp_latest.csv`` fallback exists).
    """
    adp_path = None
    if source:
        candidate = _PROJECT_ROOT / "data" / "adp" / f"adp_{source}_{scoring}.csv"
        if candidate.exists():
            adp_path = candidate
    if adp_path is None:
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
    stdev_col = next((c for c in df.columns if c.lower() == "stdev"), None)

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
                stdev=(
                    float(row[stdev_col])
                    if stdev_col and pd.notna(row[stdev_col])
                    else None
                ),
            )
        )

    # Try to get file modification time for updated_at
    import os

    stat = os.stat(str(adp_path))
    updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

    return AdpResponse(
        players=players,
        source=adp_path.name,
        updated_at=updated_at,
    )


@router.get("/platforms", response_model=PlatformPresetsResponse)
def get_platform_presets() -> PlatformPresetsResponse:
    """Return platform-faithful draft-session presets.

    One entry per ``PLATFORM_PRESETS`` key (espn/sleeper/yahoo/custom, see
    ``src/config.py``), with ``roster_format`` resolved to its
    ``ROSTER_CONFIGS`` slot-count dict as ``roster_slots`` so callers don't
    need a second lookup to render a roster grid.
    """
    platforms: Dict[str, PlatformPreset] = {}
    for key, preset in PLATFORM_PRESETS.items():
        roster_key = preset.get("roster")
        roster_slots = ROSTER_CONFIGS.get(roster_key, {}) if roster_key else {}
        platforms[key] = PlatformPreset(
            scoring_format=preset.get("scoring_format"),
            roster_format=roster_key,
            rounds=preset.get("rounds"),
            timer_seconds=preset.get("timer_seconds"),
            adp_source=preset.get("adp_source"),
            roster_slots=dict(roster_slots),
        )
    return PlatformPresetsResponse(platforms=platforms)


# ---------------------------------------------------------------------------
# Live draft sync (v8.0 co-pilot on the web)
# ---------------------------------------------------------------------------


def _load_adp_df() -> Optional[pd.DataFrame]:
    """Load ``data/adp_latest.csv`` as a DataFrame, or None if unavailable."""
    adp_path = _PROJECT_ROOT / "data" / "adp_latest.csv"
    if not adp_path.exists():
        return None
    try:
        return pd.read_csv(str(adp_path))
    except Exception:
        logger.warning("Failed to read ADP file at %s", adp_path)
        return None


@router.get("/live", response_model=LiveDraftResponse)
def live_draft_sync(
    draft_id: Optional[str] = Query(
        None,
        pattern=r"^[A-Za-z0-9.]{1,30}$",
        description=(
            "Sleeper draft_id, or Yahoo league key (nfl.l.<id>) / bare league "
            "id when platform=yahoo"
        ),
    ),
    username: Optional[str] = Query(
        None,
        pattern=r"^[A-Za-z0-9_]{1,40}$",
        description="Sleeper username — resolves the active draft",
    ),
    league_id: Optional[str] = Query(
        None,
        pattern=r"^[A-Za-z0-9.]{1,30}$",
        description="Optional league id to disambiguate the draft",
    ),
    my_slot: Optional[int] = Query(
        None, ge=1, le=20, description="Your draft slot (1-based)"
    ),
    my_user_id: Optional[str] = Query(
        None, description="Your Sleeper user_id (infers slot from draft_order)"
    ),
    season: int = Query(2026, ge=2020, le=2030, description="NFL season"),
    scoring: str = Query(
        "half_ppr", pattern="^(ppr|half_ppr|standard)$", description="Scoring format"
    ),
    top_n: int = Query(5, ge=1, le=15, description="Number of recommendations"),
    platform: str = Query(
        "sleeper",
        pattern="^(sleeper|yahoo)$",
        description="Draft platform (Sleeper public API, or Yahoo via OAuth)",
    ),
) -> LiveDraftResponse:
    """Sync a live draft and return *our* roster-aware recommendation.

    This is the fix for "autopick just uses the platform's board": picks are
    read straight from the live platform draft, and the recommendation for the
    user's next pick comes from :class:`LiveDraftEngine` — VORP + remaining
    positional needs + correlation stacks — not the platform's consensus order.

    Sleeper needs no auth. Yahoo requires server-side OAuth (``YAHOO_CLIENT_ID``
    / ``YAHOO_CLIENT_SECRET`` plus a granted token — seedable headlessly via
    ``YAHOO_REFRESH_TOKEN``); without it this returns 503 and the UI falls back
    to mirror mode. For Yahoo, pass the league id/key as ``draft_id``.

    Provide either ``draft_id`` or ``username`` (optionally with ``league_id``).
    Provide ``my_slot`` or ``my_user_id`` so recommendations are tailored to the
    user's own drafted roster and remaining needs.
    """
    if platform == "yahoo":
        # One shared OAuth instance: the credential check below may rotate the
        # refresh token, and a second instance would re-hit Yahoo's token
        # endpoint (HTTP 999 throttling risk) mid-draft.
        oauth = YahooOAuth()
        if not oauth.has_credentials() or oauth.get_access_token() is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Yahoo live sync is not connected on this server (OAuth "
                    "grant missing). Use mirror mode, or connect Yahoo via "
                    "YAHOO_CLIENT_ID/YAHOO_CLIENT_SECRET/YAHOO_REFRESH_TOKEN."
                ),
            )
        adapter: Any = YahooAdapter(oauth=oauth)
    else:
        adapter = SleeperAdapter()

    # Resolve the draft to poll.
    resolve_failed = False
    if not draft_id and (username or league_id):
        try:
            if platform == "yahoo":
                res = adapter.resolve_draft(
                    username or league_id or "", str(season), league_id=league_id
                )
            else:
                res = resolve_active_draft(
                    username or "", str(season), league_id=league_id
                )
            draft_id = res.get("draft_id") or None
        except Exception as exc:
            resolve_failed = True
            logger.warning(
                "resolve draft failed on %s for %s: %s", platform, username, exc
            )
    if not draft_id:
        if username or league_id:
            detail = (
                f"Could not resolve an active NFL draft on {platform} for "
                f"'{username or league_id}'"
                + (" (platform was unreachable)." if resolve_failed else ".")
            )
        else:
            detail = "Provide a draft_id, or a username with an active NFL draft."
        raise HTTPException(status_code=400, detail=detail)

    # Raw projections (LiveDraftEngine adds VORP/model_rank itself).
    projections = _load_cached_projections(scoring, season)
    if projections is None or projections.empty:
        raise HTTPException(
            status_code=503,
            detail=(
                f"No projections available for {season}. Generate preseason "
                "projections to enable live draft sync."
            ),
        )

    try:
        engine = LiveDraftEngine(
            adapter,
            projections,
            adp_df=_load_adp_df(),
            my_slot=my_slot,
            my_user_id=my_user_id,
        )
        state = (
            adapter.load_state(draft_id)
            if platform == "yahoo"
            else load_draft_state(draft_id)
        )
        result = engine.update(state)
    except Exception as exc:
        logger.exception("Live draft sync failed for %s draft %s", platform, draft_id)
        # Fixed message — exception text could carry platform response bodies
        # (OAuth headers, API payloads); the cause is in the log line above.
        raise HTTPException(
            status_code=502, detail="Live draft sync failed — see server logs."
        ) from exc

    # Our recommendations for the user's next pick.
    recs_df, reasoning = engine.recommendations(top_n)
    pts_col = (
        "projected_season_points"
        if "projected_season_points" in recs_df.columns
        else "projected_points"
    )
    needs = engine.board.remaining_needs() if engine.board else {}
    recommendations: List[LiveDraftRecommendation] = []
    for _, row in recs_df.iterrows():
        pos = str(row.get("position", ""))
        adp_rank = _safe_float(row.get("adp_rank"))
        adp_diff = _safe_float(row.get("adp_diff"))
        recommendations.append(
            LiveDraftRecommendation(
                player_id=str(row.get("player_id", "")),
                player_name=str(row.get("player_name", "")),
                position=pos,
                team=str(row.get("recent_team", row.get("team", ""))) or None,
                projected_points=_safe_round(row.get(pts_col)),
                model_rank=_safe_int(row.get("model_rank"), 999),
                vorp=_safe_round(row.get("vorp")),
                recommendation_score=round(
                    _finite_or_zero(row.get("recommendation_score", row.get(pts_col))),
                    1,
                ),
                fills_need=bool(needs.get(pos, 0) > 0),
                stack_note=str(row.get("stack_note", "") or ""),
                adp_rank=int(adp_rank) if adp_rank is not None else None,
                adp_diff=int(adp_diff) if adp_diff is not None else None,
            )
        )

    # Ticker of noteworthy events (steals, reaches, positional runs). The
    # engine is rebuilt per request, so result.key_moments covers the whole
    # draft so far — keep the most recent few, newest first.
    key_moments = [
        LiveDraftKeyMoment(
            kind=m.kind, pick_no=m.pick_no, player=m.player, detail=m.detail
        )
        for m in reversed(result.key_moments[-8:])
    ]

    # The user's drafted roster so far.
    my_roster: List[DraftPlayer] = [
        _dict_to_draft_player(p) for p in engine.my_full_roster()
    ]

    turn = engine.turn_info()
    picks_until = None
    if turn and turn.my_next_pick_no is not None:
        picks_until = max(0, turn.my_next_pick_no - turn.on_clock_pick_no)

    return LiveDraftResponse(
        draft_id=draft_id,
        status=state.status,
        n_teams=state.n_teams,
        picks_made=len(state.picks),
        my_slot=engine.my_slot,
        on_the_clock_slot=turn.on_clock_slot if turn else None,
        is_my_turn=bool(turn.is_my_turn) if turn else False,
        picks_until_my_turn=picks_until,
        my_next_pick_no=turn.my_next_pick_no if turn else None,
        my_roster=my_roster,
        remaining_needs=needs,
        recommendations=recommendations,
        reasoning=reasoning,
        key_moments=key_moments,
        unmatched_count=len(result.unmatched),
        platform=platform,
    )


# ---------------------------------------------------------------------------
# Paste-sync (ESPN's better-than-mirror-mode path)
# ---------------------------------------------------------------------------


@router.post("/sync-log", response_model=DraftSyncLogResponse)
def sync_pick_log(req: DraftSyncLogRequest) -> DraftSyncLogResponse:
    """Apply a pasted draft-room pick log to a board session in one shot.

    ESPN has no live draft API (Phase 89 NO-GO), but its draft room shows a
    copyable pick-history panel. Paste that text here and every recognized
    player is drafted off the session board in paste order — one paste catches
    the whole room up, instead of one "Taken" click per pick. Re-pasting the
    full history is safe: players already off the board are skipped.

    When ``my_slot`` is given, each newly applied pick's overall number is run
    through snake math so picks landing on the user's slot build their roster.
    """
    session = _get_session(req.session_id)
    board: DraftBoard = session["board"]

    pool = board.all_players
    if "player_name" not in pool.columns or "player_id" not in pool.columns:
        raise HTTPException(
            status_code=500, detail="Session board is missing player columns"
        )
    lookup = build_name_lookup(
        zip(pool["player_name"].astype(str), pool["player_id"].astype(str))
    )
    parsed = parse_pick_log(req.text, lookup)

    available_ids = set(board.available["player_id"].astype(str))
    applied = 0
    my_picks = 0
    already = 0
    for pick in parsed.picks:
        if pick.player_id not in available_ids:
            already += 1
            continue
        pick_no = board.picks_taken() + 1
        by_me = bool(
            req.my_slot is not None
            and LiveDraftEngine._slot_on_clock(pick_no, board.n_teams, "snake")
            == req.my_slot
        )
        result = board.draft_player(pick.player_id, by_me=by_me)
        if result:
            available_ids.discard(pick.player_id)
            applied += 1
            if by_me:
                my_picks += 1

    return DraftSyncLogResponse(
        matched=len(parsed.picks),
        applied=applied,
        already_drafted=already,
        my_picks_applied=my_picks,
        unmatched_lines=parsed.unmatched_lines[:20],
        unmatched_count=len(parsed.unmatched_lines),
        picks_taken=board.picks_taken(),
    )
