"""Phase 74: Sleeper user / league / roster endpoints.

All Sleeper public-API HTTP traffic flows through ``src/sleeper_http.py``
per CONTEXT D-01 (LOCKED in Phase 73).

Plan-3 League Sync: adds ``league_router`` (prefix ``/league``) with three
read-only endpoints backed by live Sleeper API calls, 15-minute TTL cache,
and projection re-scoring via ``src/league_scoring.py``.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, NamedTuple, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response

from src.config import SENTIMENT_CONFIG
from src.draft_models import PickEvent
from src.projection_store import load_latest_preseason
from src.league_scoring import score_with_settings, unmodeled_offense_keys
from src.roster_optimizer import drop_candidates, optimal_lineup
from src.sleeper_http import (
    fetch_sleeper_json,
    get_drafts_for_league,
    get_league,
    get_league_rosters,
    get_league_users,
)
from src.sleeper_player_map import (
    build_player_index,
    build_projection_lookup,
    load_sleeper_players,
    map_picks_to_projections,
    normalize_name,
)

from ..config import GOLD_PROJECTIONS_DIR
from ..models.schemas import (
    BestAvailablePlayer,
    DraftInfo,
    KeeperCandidate,
    LeagueDraftPrepResponse,
    LeagueOverviewResponse,
    LeagueRosterPlayer,
    LineupChanges,
    MyWeekPlayer,
    MyWeekResponse,
    MyWeekSlot,
    MyWeekWaiverTarget,
    RosterReportResponse,
    ScoringDeltaBadge,
    SleeperLeague,
    SleeperRoster,
    SleeperRosterPlayer,
    SleeperUser,
    SleeperUserLoginResponse,
    StarterSlot,
    WaiverTarget,
    WaiversResponse,
)
from ..services.projection_service import _latest_parquet
from ..services.team_roster_service import get_current_week as _get_current_week

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sleeper", tags=["sleeper"])
league_router = APIRouter(prefix="/league", tags=["league_sync"])

_SESSION_COOKIE = "sleeper_user_id"
_SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 7 days
_SLEEPER_TIMEOUT_S: int = 10
_CACHE_TTL_S: float = 15 * 60  # 15 minutes
_SKILL_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})

# ---------------------------------------------------------------------------
# In-process TTL cache
# ---------------------------------------------------------------------------

_CACHE: Dict[str, Tuple[Any, float]] = {}


def _cache_get(key: str) -> Optional[Any]:
    """Return cached value if not expired, else None."""
    entry = _CACHE.get(key)
    if entry and time.monotonic() - entry[1] < _CACHE_TTL_S:
        return entry[0]
    return None


def _cache_set(key: str, value: Any) -> None:
    """Store value in the TTL cache with the current monotonic timestamp."""
    _CACHE[key] = (value, time.monotonic())


# ---------------------------------------------------------------------------
# Projection helpers
# ---------------------------------------------------------------------------


def _load_projections(season: int) -> Optional[pd.DataFrame]:
    """Load season projections from the canonical preseason parquet.

    Delegates to :func:`src.projection_store.load_latest_preseason` so the
    web API always serves the same Gold artifact as the CLI draft co-pilot,
    with identical ``recent_team → team`` column normalisation.

    Returns:
        DataFrame (never empty) or ``None`` when no source is available.
    """
    df = load_latest_preseason(season)
    if df is not None and not df.empty:
        return df
    logger.warning(
        "No preseason parquet for season=%d; projections unavailable", season
    )
    return None


def _cached_player_index() -> Dict[str, Dict[str, str]]:
    """Return the Sleeper player index, TTL-cached in-process.

    The registry is a ~5 MB JSON parse + ~10k-record index build — far too
    expensive to repeat per request. An empty registry (Sleeper outage with a
    cold disk cache) raises 503 rather than silently matching zero players.

    Raises:
        HTTPException 503: Sleeper player registry unavailable.
    """
    cached = _cache_get("player_index")
    if cached is not None:
        return cached
    index = build_player_index(load_sleeper_players())
    if not index:
        raise HTTPException(
            status_code=503,
            detail=(
                "Sleeper player registry unavailable (network fetch failed and "
                "no disk cache) — retry shortly."
            ),
        )
    _cache_set("player_index", index)
    return index


def _cached_raw_registry() -> Dict[str, Any]:
    """Return the raw Sleeper player registry (all fields), TTL-cached in-process.

    Unlike ``_cached_player_index`` (which only keeps name/pos/team), the raw
    registry preserves ``years_exp`` and other per-player attributes needed for
    taxi eligibility and rookie detection.
    """
    cached = _cache_get("raw_registry")
    if cached is not None:
        return cached  # type: ignore[return-value]
    registry = load_sleeper_players()
    if not registry:
        # Same failure mode as _cached_player_index: cold disk cache + Sleeper
        # unreachable. Without this guard every keeper would silently get
        # years_exp=0 (all flagged taxi-eligible) on a 200 response.
        raise HTTPException(
            status_code=503,
            detail=(
                "Sleeper player registry unavailable (network fetch failed and "
                "no disk cache) — retry shortly."
            ),
        )
    _cache_set("raw_registry", registry)
    return registry


def _cached_projections(season: int) -> Optional[pd.DataFrame]:
    """Return the season projections DataFrame, TTL-cached in-process."""
    key = f"projections:{season}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    df = _load_projections(season)
    if df is not None:
        _cache_set(key, df)
    return df


def _league_projections(
    league_id: str, season: int, scoring_settings: Dict[str, Any]
) -> Optional[pd.DataFrame]:
    """Return projections re-scored for a league, TTL-cached per (league, season).

    Drops the ``vorp`` column when custom scoring is applied: VORP is computed
    at generation time under the preset scoring, so it is stale relative to the
    re-scored points — ``roster_optimizer`` then correctly falls back to
    league-accurate ``projected_season_points`` for drop ranking.
    """
    key = f"league_proj:{league_id}:{season}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    projections = _cached_projections(season)
    if projections is None or projections.empty:
        return None
    if scoring_settings:
        projections = score_with_settings(projections, scoring_settings)
        if "vorp" in projections.columns:
            projections = projections.drop(columns=["vorp"])
    _cache_set(key, projections)
    return projections


# ---------------------------------------------------------------------------
# Player-id → projection row mapping
# ---------------------------------------------------------------------------


def _build_pick_events(
    player_ids: List[str], player_index: Dict[str, Dict[str, str]]
) -> Tuple[List[PickEvent], List[str]]:
    """Synthesise ``PickEvent`` objects for a list of Sleeper player_ids.

    Mirrors the ``SleeperAdapter._keeper_pick`` pattern so the same
    ``map_picks_to_projections`` name-normalisation path is reused without
    pulling in the full ``LiveDraftEngine``.

    Returns:
        ``(pick_events, unknown_ids)`` where ``unknown_ids`` are player_ids
        not present in the Sleeper registry (common for practice-squad players).
    """
    events: List[PickEvent] = []
    unknown: List[str] = []
    for i, pid in enumerate(player_ids):
        rec = player_index.get(str(pid), {})
        full = str(rec.get("full_name") or "")
        if not full:
            unknown.append(pid)
            continue
        first, _, last = full.partition(" ")
        events.append(
            PickEvent(
                pick_no=i,
                round=0,
                draft_slot=0,
                roster_id=None,
                picked_by="",
                sleeper_player_id=str(pid),
                first_name=first,
                last_name=last,
                position=str(rec.get("position", "")).upper(),
                team=str(rec.get("team", "")).upper(),
                is_keeper=True,
            )
        )
    return events, unknown


def _map_roster_to_projections(
    player_ids: List[str],
    projections: pd.DataFrame,
    player_index: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Map a list of Sleeper player_ids to their projection rows.

    Returns:
        ``(matched_rows, unmatched_player_ids)``. Each matched row is a plain
        dict from the projection DataFrame, enriched with ``sleeper_player_id``.
    """
    events, unknown_ids = _build_pick_events(player_ids, player_index)
    matched, unmatched_events = map_picks_to_projections(
        events, projections, player_index=player_index
    )
    # Backfill sleeper_player_id onto each matched row.
    for row in matched:
        if "sleeper_player_id" not in row:
            row["sleeper_player_id"] = ""
    unmatched_ids = unknown_ids + [
        p.sleeper_player_id for p in unmatched_events if p.sleeper_player_id
    ]
    return matched, unmatched_ids


# ---------------------------------------------------------------------------
# Scoring label helpers
# ---------------------------------------------------------------------------


def _scoring_format_label(scoring_settings: Dict[str, Any]) -> str:
    """Derive a human-readable scoring label from Sleeper scoring_settings."""
    rec = scoring_settings.get("rec")
    try:
        rec_f = float(rec) if rec is not None else 0.5
    except (TypeError, ValueError):
        rec_f = 0.5
    te_bonus = scoring_settings.get("bonus_rec_te")
    has_te = bool(te_bonus and float(te_bonus) > 0)
    pass_td = scoring_settings.get("pass_td")
    try:
        pass_td_f = float(pass_td) if pass_td is not None else 4.0
    except (TypeError, ValueError):
        pass_td_f = 4.0

    if rec_f >= 1.0:
        base = "Full PPR"
    elif rec_f <= 0.0:
        base = "Standard"
    else:
        base = "Half PPR"
    parts = [base]
    if has_te:
        parts.append("TE premium")
    if pass_td_f >= 6.0:
        parts.append("6pt pass TD")
    return " + ".join(parts) + " (league)"


def _scoring_delta_badges(scoring_settings: Dict[str, Any]) -> List[ScoringDeltaBadge]:
    """Surface the most impactful custom scoring deltas vs standard half-PPR.

    Compares key scoring fields against standard half-PPR defaults
    (rec=0.5, rec_td=6, pass_td=4, pass_yd=0.04, rush_yd=0.1) and emits a
    badge for each non-default value. Only includes fields that meaningfully
    affect ranking decisions.
    """
    _DEFAULTS: Dict[str, float] = {
        "rec": 0.5,
        "rec_td": 6.0,
        "rush_td": 6.0,
        "pass_td": 4.0,
        "pass_yd": 0.04,
        "rush_yd": 0.1,
        "rec_yd": 0.1,
        "pass_int": -2.0,
    }
    badges: List[ScoringDeltaBadge] = []
    te_bonus = scoring_settings.get("bonus_rec_te")
    if te_bonus and float(te_bonus) != 0:
        badges.append(
            ScoringDeltaBadge(
                key="bonus_rec_te",
                label=f"TE +{float(te_bonus):.1f} rec premium",
                value=float(te_bonus),
            )
        )
    for key, default in _DEFAULTS.items():
        raw = scoring_settings.get(key)
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if abs(val - default) > 0.001:
            direction = "+" if val > default else ""
            badges.append(
                ScoringDeltaBadge(
                    key=key,
                    label=f"{key} {direction}{val - default:.2g} vs half-PPR",
                    value=val,
                )
            )
    return badges


# ---------------------------------------------------------------------------
# League_id validation helper
# ---------------------------------------------------------------------------


def _validate_numeric_league_id(league_id: str) -> None:
    """Raise 400 if ``league_id`` is not a numeric string."""
    if not league_id.isdigit():
        raise HTTPException(
            status_code=400,
            detail=(
                f"league_id must be a numeric Sleeper league ID; got '{league_id}'. "
                "Copy the ID from your Sleeper app URL."
            ),
        )


def _require_league(league_id: str) -> Dict[str, Any]:
    """Fetch league metadata; raise 404 if not found or empty."""
    cache_key = f"league:{league_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    league = get_league(league_id, timeout=_SLEEPER_TIMEOUT_S)
    if not league or not league.get("name"):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Sleeper league '{league_id}' not found. "
                "Check the league ID and try again."
            ),
        )
    _cache_set(cache_key, league)
    return league


def _cached_rosters(league_id: str) -> List[Dict[str, Any]]:
    """Return all rosters for a league from Sleeper, TTL-cached in-process.

    Args:
        league_id: Numeric Sleeper league ID.

    Returns:
        Raw roster dicts as returned by the Sleeper API (possibly empty on
        Sleeper outage — D-06 fail-open).
    """
    cache_key = f"rosters:{league_id}"
    rosters = _cache_get(cache_key)
    if rosters is None:
        rosters = get_league_rosters(league_id, timeout=_SLEEPER_TIMEOUT_S)
        _cache_set(cache_key, rosters)
    return rosters


def _user_team_name(league_id: str, user_id: str) -> Optional[str]:
    """Return the user's team name in a league, TTL-cached in-process.

    Sleeper keeps team names on the league-users resource under
    ``metadata.team_name``. Fail-open: any Sleeper outage or a user who never
    set a team name yields ``None`` (the frontend falls back to display name).
    """
    cache_key = f"league_users:{league_id}"
    users = _cache_get(cache_key)
    if users is None:
        users = get_league_users(league_id, timeout=_SLEEPER_TIMEOUT_S)
        _cache_set(cache_key, users)
    for u in users:
        if isinstance(u, dict) and str(u.get("user_id") or "") == user_id:
            metadata = u.get("metadata") or {}
            team_name = metadata.get("team_name") if isinstance(metadata, dict) else None
            return str(team_name) if team_name else None
    return None


def _require_league_projections(
    league_id: str, season: int, scoring_settings: Dict[str, Any]
) -> pd.DataFrame:
    """Return league-re-scored projections, raising 503 when unavailable.

    Args:
        league_id: Numeric Sleeper league ID (cache key component).
        season: NFL season year.
        scoring_settings: Sleeper ``scoring_settings`` dict for re-scoring.

    Returns:
        Non-empty projections DataFrame re-scored for the league.

    Raises:
        HTTPException 503: no preseason parquet is available on disk.
    """
    projections = _league_projections(league_id, season, scoring_settings)
    if projections is None or projections.empty:
        raise HTTPException(
            status_code=503,
            detail=(
                "Projections unavailable — preseason parquet not found. "
                "Run `generate_projections.py --preseason` first."
            ),
        )
    return projections


def _require_user_roster(
    rosters: List[Dict[str, Any]], user_id: str, league_id: str
) -> Tuple[Dict[str, Any], List[str]]:
    """Find the user's roster in a league roster list.

    Returns:
        ``(roster_dict, player_ids)`` for the roster owned by ``user_id``.

    Raises:
        HTTPException 404 if no roster matches.
    """
    for r in rosters:
        if str(r.get("owner_id") or "") == user_id:
            return r, [str(p) for p in (r.get("players") or []) if p]
    raise HTTPException(
        status_code=404,
        detail=(
            f"User {user_id} is not a member of league {league_id}. "
            "Check your user_id parameter."
        ),
    )


# ---------------------------------------------------------------------------
# Original Phase 74 endpoints (unchanged)
# ---------------------------------------------------------------------------


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _to_user(payload: Any) -> Optional[SleeperUser]:
    if not isinstance(payload, dict) or not payload.get("user_id"):
        return None
    return SleeperUser(
        user_id=str(payload["user_id"]),
        username=str(payload.get("username") or ""),
        display_name=payload.get("display_name"),
        avatar=payload.get("avatar"),
    )


def _to_leagues(payload: Any) -> List[SleeperLeague]:
    if not isinstance(payload, list):
        return []
    out: List[SleeperLeague] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("league_id"):
            continue
        out.append(
            SleeperLeague(
                league_id=str(item["league_id"]),
                name=str(item.get("name") or ""),
                season=str(item.get("season") or ""),
                total_rosters=item.get("total_rosters"),
                sport=item.get("sport") or "nfl",
                status=item.get("status"),
                settings=(
                    item.get("settings")
                    if isinstance(item.get("settings"), dict)
                    else None
                ),
            )
        )
    return out


def _resolve_player_meta(
    player_id: str, registry: Dict[str, Dict[str, Any]]
) -> Dict[str, Optional[str]]:
    meta = registry.get(player_id) or {}
    return {
        "player_name": meta.get("full_name") or meta.get("name"),
        "position": meta.get("position"),
        "team": meta.get("team"),
    }


@router.post("/user/login", response_model=SleeperUserLoginResponse)
def sleeper_user_login(
    payload: dict,
    response: Response,
    season: Optional[int] = Query(
        None, description="NFL season for league lookup (defaults to current year)"
    ),
) -> SleeperUserLoginResponse:
    """Resolve a Sleeper username to user_id + leagues for the requested season.

    Sets an HttpOnly cookie ``sleeper_user_id`` on success (7-day expiry) so
    subsequent requests are user-scoped without re-querying Sleeper.

    D-06 fail-open: Sleeper outage returns 200 with empty leagues list.
    """
    username = (payload or {}).get("username") or ""
    username = str(username).strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")

    user_url = SENTIMENT_CONFIG["sleeper_user_url"].format(username=username)
    user_payload = fetch_sleeper_json(user_url)
    user = _to_user(user_payload)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Could not verify Sleeper user '{username}'. The username "
                "may not exist, or Sleeper may be temporarily unreachable."
            ),
        )

    use_season = season if season is not None else _current_year()
    leagues_url = SENTIMENT_CONFIG["sleeper_leagues_url"].format(
        user_id=user.user_id, season=use_season
    )
    leagues = _to_leagues(fetch_sleeper_json(leagues_url))

    response.set_cookie(
        key=_SESSION_COOKIE,
        value=user.user_id,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )

    return SleeperUserLoginResponse(user=user, leagues=leagues)


@router.get("/leagues/{user_id}", response_model=List[SleeperLeague])
def list_user_leagues(
    user_id: str,
    season: Optional[int] = Query(None),
) -> List[SleeperLeague]:
    """Return leagues the user belongs to for a given season."""
    use_season = season if season is not None else _current_year()
    leagues_url = SENTIMENT_CONFIG["sleeper_leagues_url"].format(
        user_id=user_id, season=use_season
    )
    return _to_leagues(fetch_sleeper_json(leagues_url))


@router.get("/rosters/{league_id}", response_model=List[SleeperRoster])
def list_league_rosters(
    league_id: str,
    user_id: Optional[str] = Query(
        None,
        description="Authenticated user_id; rosters where owner_id matches get is_user_roster=True",
    ),
) -> List[SleeperRoster]:
    """Return all rosters for a league. Marks the user's roster with is_user_roster=True.

    D-06 fail-open: Sleeper outage returns empty list.
    """
    rosters_url = SENTIMENT_CONFIG["sleeper_league_rosters_url"].format(
        league_id=league_id
    )
    raw = fetch_sleeper_json(rosters_url)
    if not isinstance(raw, list):
        return []

    registry: Dict[str, Dict[str, Any]] = {}
    if raw:
        # load_sleeper_players keeps a 7-day disk cache of the ~5 MB registry —
        # never live-fetch it per request.
        registry_payload = load_sleeper_players()
        if isinstance(registry_payload, dict):
            registry = registry_payload

    out: List[SleeperRoster] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        starters_ids = item.get("starters") or []
        all_players = item.get("players") or []
        bench_ids = [p for p in all_players if p not in starters_ids]

        starters = [
            SleeperRosterPlayer(
                player_id=str(pid), **_resolve_player_meta(str(pid), registry)
            )
            for pid in starters_ids
            if pid
        ]
        bench = [
            SleeperRosterPlayer(
                player_id=str(pid), **_resolve_player_meta(str(pid), registry)
            )
            for pid in bench_ids
            if pid
        ]
        owner_id = item.get("owner_id")
        out.append(
            SleeperRoster(
                roster_id=int(item.get("roster_id") or 0),
                league_id=league_id,
                owner_user_id=str(owner_id) if owner_id else None,
                is_user_roster=bool(
                    user_id and owner_id and str(owner_id) == str(user_id)
                ),
                starters=starters,
                bench=bench,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Shared league context helper (plan-3 endpoints)
# ---------------------------------------------------------------------------


class _LeagueContext(NamedTuple):
    """Validated league context shared by all three league_router endpoints."""

    league: Dict[str, Any]
    use_season: int
    scoring_settings: Dict[str, Any]
    roster_positions: List[str]
    roster_format: str


def _build_league_context(league_id: str, season: Optional[int]) -> "_LeagueContext":
    """Validate, fetch, and assemble shared league context.

    Runs the three-step prologue every league endpoint shares: numeric-ID
    guard, Sleeper league fetch (15-min TTL cache), and season/scoring/roster
    extraction.  Raises 400/404 on bad inputs so callers are free of those
    guard clauses.

    Args:
        league_id: Numeric Sleeper league ID string.
        season: Requested NFL season year, or ``None`` to default to current.

    Returns:
        ``_LeagueContext`` with all fields populated.

    Raises:
        HTTPException 400: non-numeric ``league_id``.
        HTTPException 404: league not found on Sleeper.
    """
    _validate_numeric_league_id(league_id)
    league = _require_league(league_id)
    use_season = season if season is not None else _current_year()
    scoring_settings: Dict[str, Any] = league.get("scoring_settings") or {}
    roster_positions: List[str] = league.get("roster_positions") or []
    roster_format = (
        "superflex"
        if "SUPER_FLEX" in roster_positions or "SUPERFLEX" in roster_positions
        else "standard"
    )
    return _LeagueContext(
        league=league,
        use_season=use_season,
        scoring_settings=scoring_settings,
        roster_positions=roster_positions,
        roster_format=roster_format,
    )


# ---------------------------------------------------------------------------
# Plan-3 League Sync endpoints
# ---------------------------------------------------------------------------


@league_router.get("/{league_id}/overview", response_model=LeagueOverviewResponse)
def league_overview(
    league_id: str,
    user_id: Optional[str] = Query(None, description="Sleeper user_id to load roster"),
    season: Optional[int] = Query(
        None, description="Season year (defaults to current)"
    ),
) -> LeagueOverviewResponse:
    """Return league settings + scoring summary + user's re-scored roster.

    Projections are re-scored under the league's exact ``scoring_settings`` so
    ``projected_season_points`` values reflect real league value rather than the
    generic half-PPR preset. A 15-minute TTL cache covers the Sleeper API calls.

    Args:
        league_id: Numeric Sleeper league ID.
        user_id: Sleeper user_id; when provided the response includes the user's
            roster with league-re-scored projections.
        season: NFL season year (default: current UTC year).

    Returns:
        League name, roster positions, scoring deltas vs half-PPR, and (when
        ``user_id`` is given) the user's roster rows with custom-scored points.

    Raises:
        HTTPException 400: non-numeric league_id.
        HTTPException 404: league not found on Sleeper.
    """
    ctx = _build_league_context(league_id, season)
    scoring_label = _scoring_format_label(ctx.scoring_settings)
    deltas = _scoring_delta_badges(ctx.scoring_settings)
    unmodeled = unmodeled_offense_keys(ctx.scoring_settings)

    user_roster_rows: List[LeagueRosterPlayer] = []
    team_name: Optional[str] = None
    if user_id:
        team_name = _user_team_name(league_id, user_id)
        rosters = _cached_rosters(league_id)
        try:
            _, player_ids = _require_user_roster(rosters, user_id, league_id)
        except HTTPException:
            player_ids = []

        if player_ids:
            rescored = _league_projections(
                league_id, ctx.use_season, ctx.scoring_settings
            )
            if rescored is not None and not rescored.empty:
                player_index = _cached_player_index()
                matched, _ = _map_roster_to_projections(
                    player_ids, rescored, player_index
                )
                for row in matched:
                    user_roster_rows.append(
                        LeagueRosterPlayer(
                            sleeper_player_id=str(row.get("sleeper_player_id") or ""),
                            player_name=row.get("player_name"),
                            position=str(row.get("position") or "").upper() or None,
                            team=row.get("team") or row.get("recent_team"),
                            projected_season_points=_safe_float(
                                row.get("projected_season_points")
                            ),
                            vorp=_safe_float(row.get("vorp")),
                        )
                    )

    return LeagueOverviewResponse(
        league_id=league_id,
        league_name=str(ctx.league.get("name") or ""),
        season=str(ctx.league.get("season") or ctx.use_season),
        status=ctx.league.get("status"),
        total_rosters=ctx.league.get("total_rosters"),
        roster_positions=ctx.roster_positions,
        scoring_format_label=scoring_label,
        scoring_deltas=deltas,
        unmodeled_keys=unmodeled,
        user_roster=user_roster_rows,
        team_name=team_name,
    )


@league_router.get("/{league_id}/roster-report", response_model=RosterReportResponse)
def league_roster_report(
    league_id: str,
    user_id: str = Query(..., description="Sleeper user_id"),
    season: Optional[int] = Query(
        None, description="Season year (defaults to current)"
    ),
) -> RosterReportResponse:
    """Return optimal starting lineup, bench, and drop candidates for the user's roster.

    Mirrors the output of ``scripts/draft_live.py --roster-report`` for the same
    league and user: projects are re-scored under the league's exact
    ``scoring_settings``, and ``optimal_lineup`` / ``drop_candidates`` from
    ``src/roster_optimizer`` are applied with the league's real ``roster_positions``.

    The player set in ``starters`` is guaranteed to match the CLI tool's output
    when the same preseason projections parquet is active (±floating-point
    rounding at the 0.1 pt level).

    Args:
        league_id: Numeric Sleeper league ID.
        user_id: Sleeper user_id (required — this is a personalized endpoint).
        season: NFL season year (default: current UTC year).

    Returns:
        ``starters``, ``bench``, ``drop_candidates``, and ``unmatched_player_ids``.

    Raises:
        HTTPException 400: non-numeric league_id.
        HTTPException 404: league not found or user not in league.
        HTTPException 503: projections unavailable (no preseason parquet on disk).
    """
    ctx = _build_league_context(league_id, season)

    # --- re-scored projections (cached) --------------------------------------
    projections = _require_league_projections(
        league_id, ctx.use_season, ctx.scoring_settings
    )

    # --- user's roster -------------------------------------------------------
    rosters = _cached_rosters(league_id)
    _, player_ids = _require_user_roster(rosters, user_id, league_id)

    # --- map player_ids → projection rows ------------------------------------
    player_index = _cached_player_index()
    matched, unmatched_ids = _map_roster_to_projections(
        player_ids, projections, player_index
    )

    if not matched:
        return RosterReportResponse(
            league_id=league_id,
            user_id=user_id,
            roster_size=0,
            roster_format=ctx.roster_format,
            unmatched_player_ids=unmatched_ids,
        )

    # --- optimal lineup + drop candidates ------------------------------------
    lineup = optimal_lineup(
        matched, ctx.roster_format, roster_positions=ctx.roster_positions or None
    )
    drops = drop_candidates(
        matched,
        ctx.roster_format,
        top_n=5,
        roster_positions=ctx.roster_positions or None,
    )

    starters: List[StarterSlot] = []
    for slot, players in lineup["starters"].items():
        for p in players:
            starters.append(
                StarterSlot(
                    slot=slot,
                    player_name=p.get("player_name"),
                    position=str(p.get("position") or "").upper() or None,
                    team=p.get("team") or p.get("recent_team"),
                    projected_season_points=_safe_float(
                        p.get("projected_season_points")
                    ),
                )
            )

    bench_rows: List[LeagueRosterPlayer] = [
        LeagueRosterPlayer(
            sleeper_player_id=str(p.get("sleeper_player_id") or ""),
            player_name=p.get("player_name"),
            position=str(p.get("position") or "").upper() or None,
            team=p.get("team") or p.get("recent_team"),
            projected_season_points=_safe_float(p.get("projected_season_points")),
            vorp=_safe_float(p.get("vorp")),
        )
        for p in lineup["bench"]
    ]

    drop_rows = [
        {
            "player_name": d["player"].get("player_name"),
            "position": str(d["player"].get("position") or "").upper() or None,
            "value": d["value"],
            "reason": d["reason"],
        }
        for d in drops
    ]

    return RosterReportResponse(
        league_id=league_id,
        user_id=user_id,
        roster_size=len(matched),
        roster_format=ctx.roster_format,
        starters=starters,
        bench=bench_rows,
        drop_candidates=drop_rows,
        unmatched_player_ids=unmatched_ids,
    )


@league_router.get("/{league_id}/waivers", response_model=WaiversResponse)
def league_waivers(
    league_id: str,
    user_id: str = Query(..., description="Sleeper user_id"),
    season: Optional[int] = Query(
        None, description="Season year (defaults to current)"
    ),
) -> WaiversResponse:
    """Return top-20 unrostered free agents ranked by league-scored season projection.

    Each target is annotated with the weakest starter they would displace at
    their position on the user's roster, or ``upgrades_over=None`` when they
    add depth only (user has no starter weaker than the candidate at that slot).

    All rostered players across **all** league rosters are excluded — not just
    the requesting user's roster — so truly available free agents are shown.

    Args:
        league_id: Numeric Sleeper league ID.
        user_id: Sleeper user_id (required for upgrade analysis).
        season: NFL season year (default: current UTC year).

    Returns:
        Up to 20 waiver targets with upgrade annotations.

    Raises:
        HTTPException 400: non-numeric league_id.
        HTTPException 404: league not found or user not in league.
        HTTPException 503: projections unavailable.
    """
    ctx = _build_league_context(league_id, season)
    projections = _require_league_projections(
        league_id, ctx.use_season, ctx.scoring_settings
    )

    # --- all rostered players across entire league ---------------------------
    rosters = _cached_rosters(league_id)

    all_rostered_ids: set = set()
    user_player_ids: List[str] = []
    user_found = False
    for r in rosters:
        if not isinstance(r, dict):
            continue
        pids = [str(p) for p in (r.get("players") or []) if p]
        all_rostered_ids.update(pids)
        if str(r.get("owner_id") or "") == user_id:
            user_found = True
            user_player_ids = pids

    # An empty roster (pre-draft league) is legitimate — only 404 when the
    # user genuinely isn't a member.
    if not user_found:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} not found in league {league_id}.",
        )

    # --- vectorized projection lookup (no iterrows) --------------------------
    # build_projection_lookup vectorizes normalize_name via map() and stores
    # _team on every row so we can apply team-aware tiebreaks below.
    player_index = _cached_player_index()
    proj_lookup = build_projection_lookup(projections)
    adp_lookup = _cached_adp()

    # Identify free agents: skill-position players in Sleeper registry that
    # are not rostered in the league and have a matching projection row.
    free_agent_rows: List[Dict[str, Any]] = []
    for pid, meta, base_row in _iter_projected_free_agents(
        player_index, proj_lookup, all_rostered_ids, adp_lookup
    ):
        # Team-aware tiebreak: if both player and stored row have known teams
        # and they differ, the lookup hit belongs to a same-name player on a
        # different team — skip to avoid mis-attribution.
        player_team = str(meta.get("team") or "").upper()
        stored_team = base_row.get("_team", "")
        if player_team and stored_team and player_team != stored_team:
            continue
        row = dict(base_row)
        row["sleeper_player_id"] = pid
        free_agent_rows.append(row)

    # Sort by projected_season_points descending.
    free_agent_rows.sort(
        key=lambda r: _safe_float(r.get("projected_season_points")) or 0,
        reverse=True,
    )
    top_20 = free_agent_rows[:20]

    # --- user's optimal lineup for upgrade analysis --------------------------
    user_matched, _ = _map_roster_to_projections(
        user_player_ids, projections, player_index
    )
    user_lineup = (
        optimal_lineup(
            user_matched,
            ctx.roster_format,
            roster_positions=ctx.roster_positions or None,
        )
        if user_matched
        else {"starters": {}, "bench": []}
    )

    # Weakest starter points per position.
    weakest_starter: Dict[str, Tuple[float, str, str]] = {}  # pos → (pts, name, slot)
    for slot, players in user_lineup["starters"].items():
        for p in players:
            pos = str(p.get("position") or "").upper()
            pts = _safe_float(p.get("projected_season_points")) or 0
            if pos not in weakest_starter or pts < weakest_starter[pos][0]:
                weakest_starter[pos] = (
                    pts,
                    str(p.get("player_name") or ""),
                    slot,
                )

    targets: List[WaiverTarget] = []
    for row in top_20:
        pos = str(row.get("position") or "").upper()
        pts = _safe_float(row.get("projected_season_points")) or 0
        upgrades_over: Optional[str] = None
        upgrade_slot: Optional[str] = None
        if pos in weakest_starter:
            starter_pts, starter_name, slot = weakest_starter[pos]
            if pts > starter_pts:
                upgrades_over = starter_name
                upgrade_slot = slot
        targets.append(
            WaiverTarget(
                sleeper_player_id=str(row.get("sleeper_player_id") or ""),
                player_name=row.get("player_name"),
                position=pos or None,
                team=row.get("team") or row.get("recent_team"),
                projected_season_points=_safe_float(row.get("projected_season_points")),
                vorp=_safe_float(row.get("vorp")),
                upgrades_over=upgrades_over,
                upgrade_slot=upgrade_slot,
            )
        )

    return WaiversResponse(
        league_id=league_id,
        user_id=user_id,
        roster_positions=ctx.roster_positions,
        targets=targets,
    )


# ---------------------------------------------------------------------------
# My Week — weekly league command center
# ---------------------------------------------------------------------------

#: Weekly Gold parquets prefix per-stat columns with ``proj_``; league_scoring
#: expects the unprefixed names, so strip the prefix on load.
_WEEKLY_STAT_RENAMES: Dict[str, str] = {
    f"proj_{col}": col
    for col in (
        "passing_yards",
        "passing_tds",
        "interceptions",
        "rushing_yards",
        "rushing_tds",
        "receptions",
        "receiving_yards",
        "receiving_tds",
    )
}

#: Injury designations that mean the player cannot play this week.
_OUT_STATUSES = frozenset({"OUT", "IR", "PUP", "NFI", "SUSPENDED"})


def _load_weekly_projections(season: int, week: int) -> Optional[pd.DataFrame]:
    """Load the weekly Gold projections parquet for ``(season, week)``.

    Reads ``data/gold/projections/season=S/week=W/`` directly (same Gold
    artifact ``/api/projections`` serves in its Parquet path), preferring the
    half-PPR file — the per-stat columns are format-independent and points are
    re-scored under league settings anyway. Deliberately does NOT apply the
    preseason fallback ``projection_service`` uses: a season-long projection
    rebadged as a week would make start/sit deltas meaningless, so the caller
    surfaces an explicit preseason mode instead.

    Returns:
        DataFrame with unprefixed stat columns and a ``team`` column, or
        ``None`` when no weekly parquet exists for the slice.
    """
    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    if not week_dir.exists():
        return None
    parquet_path = _latest_parquet(
        week_dir, "projections_half_ppr_*.parquet"
    ) or _latest_parquet(week_dir)
    if parquet_path is None:
        return None
    df = pd.read_parquet(parquet_path)
    df = df.rename(
        columns={k: v for k, v in _WEEKLY_STAT_RENAMES.items() if k in df.columns}
    )
    if "recent_team" in df.columns and "team" not in df.columns:
        df = df.rename(columns={"recent_team": "team"})
    return df


def _league_weekly_projections(
    league_id: str, season: int, week: int, scoring_settings: Dict[str, Any]
) -> Optional[pd.DataFrame]:
    """Return weekly projections re-scored for a league, TTL-cached.

    Re-scores ``projected_points`` under the league's ``scoring_settings`` and
    scales ``projected_floor`` / ``projected_ceiling`` by the same per-player
    ratio so the bands stay consistent with the re-scored point estimate.
    K/DST rows (no modeled stat columns) keep their preset points rather than
    being zeroed by the re-score.
    """
    key = f"league_weekly:{league_id}:{season}:{week}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    df = _load_weekly_projections(season, week)
    if df is None or df.empty:
        return None
    if scoring_settings and "projected_points" in df.columns:
        base = df["projected_points"].astype(float).copy()
        df = score_with_settings(df, scoring_settings)
        if "position" in df.columns:
            unmodeled = df["position"].astype(str).str.upper().isin(("K", "DST", "DEF"))
            df.loc[unmodeled, "projected_points"] = base[unmodeled]
        rescored = df["projected_points"].astype(float)
        ratio = pd.Series(1.0, index=df.index)
        nonzero = base > 0
        ratio[nonzero] = rescored[nonzero] / base[nonzero]
        for col in ("projected_floor", "projected_ceiling"):
            if col in df.columns:
                df[col] = (df[col].astype(float) * ratio).round(1)
    _cache_set(key, df)
    return df


def _abbrev_name_key(full_name: str) -> str:
    """Collapse a registry full name to the weekly-Gold abbreviated form.

    Registry ``"Josh Allen"`` → ``"jallen"``; multi-token surnames also
    collapse: ``"Amon-Ra St. Brown"`` → ``"astbrown"``. The weekly-side key
    (see :func:`_weekly_abbrev_key`) collapses ``"J.Allen"`` / ``"A.St.
    Brown"`` to the same strings.
    """
    tokens = normalize_name(full_name).split()
    if len(tokens) >= 2:
        return tokens[0][0] + "".join(tokens[1:])
    return tokens[0] if tokens else ""


def _weekly_abbrev_key(weekly_name: str) -> str:
    """Collapse a weekly-Gold short name (``"A.St. Brown"``) to its join key."""
    return normalize_name(weekly_name).replace(" ", "")


def _weekly_row_lookups(
    weekly: pd.DataFrame,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, str], Dict[str, Any]]]:
    """Build ``gsis_id → row`` and ``(abbrev_key, position) → row`` lookups.

    Weekly Gold rows key on GSIS ``player_id`` and abbreviated names, so the
    full-name join used for preseason data cannot work here. The primary join
    is Sleeper's ``gsis_id`` (present for effectively all fantasy-relevant
    players); the abbreviated-name key is the fallback.
    """
    by_gsis: Dict[str, Dict[str, Any]] = {}
    by_abbrev: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in weekly.to_dict("records"):
        gsis = str(row.get("player_id") or "").strip()
        if gsis:
            by_gsis.setdefault(gsis, row)
        key = _weekly_abbrev_key(str(row.get("player_name") or ""))
        pos = str(row.get("position") or "").upper()
        if key and pos:
            by_abbrev.setdefault((key, pos), row)
    return by_gsis, by_abbrev


def _find_weekly_row(
    pid: str,
    meta: Dict[str, Any],
    raw_registry: Dict[str, Any],
    by_gsis: Dict[str, Dict[str, Any]],
    by_abbrev: Dict[Tuple[str, str], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Resolve a Sleeper player_id to its weekly projection row (or None)."""
    raw = raw_registry.get(pid) or {}
    gsis = str(raw.get("gsis_id") or "").strip()
    if gsis:
        row = by_gsis.get(gsis)
        if row is not None:
            return row
    pos = str(meta.get("position") or "").upper()
    key = _abbrev_name_key(str(meta.get("full_name") or ""))
    if key and pos:
        return by_abbrev.get((key, pos))
    return None


def _to_my_week_player(row: Dict[str, Any]) -> MyWeekPlayer:
    """Convert a weekly projection row dict to a ``MyWeekPlayer``."""
    status = row.get("injury_status")
    status_str = str(status) if status is not None and not pd.isna(status) else None
    is_bye = bool(row.get("is_bye_week") or False)
    return MyWeekPlayer(
        sleeper_player_id=str(row.get("sleeper_player_id") or ""),
        player_name=row.get("player_name"),
        position=str(row.get("position") or "").upper() or None,
        team=row.get("team") or row.get("recent_team"),
        projected_points=_safe_float(row.get("projected_points")),
        floor=_safe_float(row.get("projected_floor")),
        ceiling=_safe_float(row.get("projected_ceiling")),
        injury_status=status_str,
        is_bye_week=is_bye,
        is_out=bool(status_str and status_str.upper() in _OUT_STATUSES),
    )


def _weekly_points(row: Dict[str, Any]) -> float:
    """League-scored weekly points for a row, 0.0 when missing."""
    return _safe_float(row.get("projected_points")) or 0.0


def _preseason_my_week(
    league_id: str,
    user_id: str,
    ctx: "_LeagueContext",
    week: Optional[int],
) -> MyWeekResponse:
    """Empty-payload preseason response with an explicit explanation."""
    return MyWeekResponse(
        league_id=league_id,
        user_id=user_id,
        season=ctx.use_season,
        week=week,
        mode="preseason",
        message=(
            f"Weekly projections for the {ctx.use_season} season aren't "
            "published yet — My Week goes live once the regular season starts. "
            "Until then, use the Roster Report for season-long lineup advice."
        ),
        scoring_format_label=_scoring_format_label(ctx.scoring_settings),
        roster_positions=ctx.roster_positions,
    )


@league_router.get("/{league_id}/my-week", response_model=MyWeekResponse)
def league_my_week(
    league_id: str,
    user_id: str = Query(..., description="Sleeper user_id"),
    season: Optional[int] = Query(
        None, description="Season year (defaults to current)"
    ),
    week: Optional[int] = Query(
        None, ge=1, le=18, description="NFL week (defaults to current week)"
    ),
) -> MyWeekResponse:
    """Return the weekly command center for the user's roster in a league.

    Loads the WEEKLY Gold projections for the resolved (season, week) —
    the same artifact ``/api/projections`` serves — re-scored under the
    league's exact ``scoring_settings``, then computes:

    - the optimal weekly lineup for the league's real ``roster_positions``
      (with floor/ceiling bands and injury/bye flags per player),
    - start/sit deltas vs the lineup currently set in Sleeper (players to
      start, players to bench, net projected gain),
    - the bench with weekly points,
    - the top-10 unrostered free agents by league-scored WEEKLY projection,
      annotated with the starter they would upgrade over.

    When ``week`` is omitted the current NFL week is resolved from the
    schedule; if it doesn't fall inside the requested season (offseason), or
    no weekly parquet exists for the slice, the endpoint returns 200 with
    ``mode="preseason"``, a human-readable ``message``, and empty lists —
    it never silently substitutes season-long numbers for weekly ones.

    Raises:
        HTTPException 400: non-numeric league_id.
        HTTPException 404: league not found or user not in league.
    """
    ctx = _build_league_context(league_id, season)

    # --- resolve week --------------------------------------------------------
    resolved_week = week
    if resolved_week is None:
        try:
            cw = _get_current_week()
            if int(cw.season) == ctx.use_season and cw.week is not None:
                resolved_week = int(cw.week)
        except Exception:  # pragma: no cover — schedule data unavailable
            logger.warning("Current-week resolution failed", exc_info=True)

    if resolved_week is None:
        return _preseason_my_week(league_id, user_id, ctx, None)

    # --- weekly projections re-scored for the league -------------------------
    weekly = _league_weekly_projections(
        league_id, ctx.use_season, resolved_week, ctx.scoring_settings
    )
    if weekly is None or weekly.empty:
        return _preseason_my_week(league_id, user_id, ctx, resolved_week)

    # --- user roster + current starters --------------------------------------
    rosters = _cached_rosters(league_id)
    roster, player_ids = _require_user_roster(rosters, user_id, league_id)
    current_starter_ids = [
        str(p) for p in (roster.get("starters") or []) if p and str(p) != "0"
    ]

    player_index = _cached_player_index()
    raw_registry = _cached_raw_registry()
    by_gsis, by_abbrev = _weekly_row_lookups(weekly)

    matched: List[Dict[str, Any]] = []
    unmatched_ids: List[str] = []
    for pid in player_ids:
        meta = player_index.get(pid) or {}
        row = _find_weekly_row(pid, meta, raw_registry, by_gsis, by_abbrev)
        if row is None:
            unmatched_ids.append(pid)
            continue
        enriched = dict(row)
        enriched["sleeper_player_id"] = pid
        # Weekly Gold names are abbreviated ("J.Allen") — display the
        # registry full name instead.
        if meta.get("full_name"):
            enriched["player_name"] = meta["full_name"]
        matched.append(enriched)

    # --- optimal lineup + deltas ---------------------------------------------
    lineup = optimal_lineup(
        matched, ctx.roster_format, roster_positions=ctx.roster_positions or None
    )

    optimal_starters: List[MyWeekSlot] = []
    optimal_ids: set = set()
    slot_by_id: Dict[str, str] = {}
    for slot, players in lineup["starters"].items():
        for p in players:
            pid = str(p.get("sleeper_player_id") or "")
            optimal_ids.add(pid)
            slot_by_id[pid] = slot
            optimal_starters.append(
                MyWeekSlot(slot=slot, **_to_my_week_player(p).model_dump())
            )

    matched_by_id = {str(p.get("sleeper_player_id") or ""): p for p in matched}
    optimal_points = sum(
        _weekly_points(p)
        for p in matched
        if str(p.get("sleeper_player_id") or "") in optimal_ids
    )
    current_points = sum(
        _weekly_points(matched_by_id[pid])
        for pid in current_starter_ids
        if pid in matched_by_id
    )

    to_start = [
        MyWeekSlot(
            slot=slot_by_id.get(pid, ""),
            **_to_my_week_player(matched_by_id[pid]).model_dump(),
        )
        for pid in sorted(
            optimal_ids - set(current_starter_ids),
            key=lambda i: -_weekly_points(matched_by_id.get(i, {})),
        )
        if pid in matched_by_id
    ]
    to_bench = [
        _to_my_week_player(matched_by_id[pid])
        for pid in current_starter_ids
        if pid not in optimal_ids and pid in matched_by_id
    ]
    changes = LineupChanges(
        to_start=to_start,
        to_bench=to_bench,
        current_points=round(current_points, 1),
        optimal_points=round(optimal_points, 1),
        net_gain=round(optimal_points - current_points, 1),
    )

    bench_players = [_to_my_week_player(p) for p in lineup["bench"]]

    # --- weekly waiver targets ------------------------------------------------
    all_rostered_ids: set = set()
    for r in rosters:
        if isinstance(r, dict):
            all_rostered_ids.update(str(p) for p in (r.get("players") or []) if p)

    adp_lookup = _cached_adp()
    fa_rows: List[Dict[str, Any]] = []
    for pid, meta in player_index.items():
        if str(pid) in all_rostered_ids:
            continue
        pos = str(meta.get("position") or "").upper()
        if pos not in _SKILL_POSITIONS:
            continue
        norm = meta.get("normalized_name") or normalize_name(
            str(meta.get("full_name") or "")
        )
        if not norm or not _is_relevant_free_agent(meta, norm, adp_lookup):
            continue
        row = _find_weekly_row(str(pid), meta, raw_registry, by_gsis, by_abbrev)
        if row is None:
            continue
        # Team-aware tiebreak — same-name/same-position collisions on other teams.
        player_team = str(meta.get("team") or "").upper()
        row_team = str(row.get("team") or "").upper()
        if player_team and row_team and player_team != row_team:
            continue
        enriched = dict(row)
        enriched["sleeper_player_id"] = str(pid)
        if meta.get("full_name"):
            enriched["player_name"] = meta["full_name"]
        fa_rows.append(enriched)

    fa_rows.sort(key=_weekly_points, reverse=True)

    # Weakest optimal starter per position for upgrade annotations.
    weakest_starter: Dict[str, Tuple[float, str, str]] = {}
    for slot, players in lineup["starters"].items():
        for p in players:
            pos = str(p.get("position") or "").upper()
            pts = _weekly_points(p)
            if pos not in weakest_starter or pts < weakest_starter[pos][0]:
                weakest_starter[pos] = (pts, str(p.get("player_name") or ""), slot)

    waiver_targets: List[MyWeekWaiverTarget] = []
    for row in fa_rows[:10]:
        pos = str(row.get("position") or "").upper()
        pts = _weekly_points(row)
        upgrades_over: Optional[str] = None
        upgrade_slot: Optional[str] = None
        if pos in weakest_starter:
            starter_pts, starter_name, slot = weakest_starter[pos]
            if pts > starter_pts:
                upgrades_over = starter_name
                upgrade_slot = slot
        waiver_targets.append(
            MyWeekWaiverTarget(
                upgrades_over=upgrades_over,
                upgrade_slot=upgrade_slot,
                **_to_my_week_player(row).model_dump(),
            )
        )

    return MyWeekResponse(
        league_id=league_id,
        user_id=user_id,
        season=ctx.use_season,
        week=resolved_week,
        mode="weekly",
        scoring_format_label=_scoring_format_label(ctx.scoring_settings),
        roster_positions=ctx.roster_positions,
        optimal_starters=optimal_starters,
        bench=bench_players,
        changes=changes,
        waiver_targets=waiver_targets,
        unmatched_player_ids=unmatched_ids,
    )


# ---------------------------------------------------------------------------
# Draft-prep helpers
# ---------------------------------------------------------------------------


def _load_adp() -> Dict[str, int]:
    """Load ADP data from the committed CSV, keyed by normalized player name.

    Returns:
        Mapping of ``normalize_name(player_name)`` → ``adp_rank`` (int).
        Empty dict when the file is absent or unreadable.
    """
    adp_path = os.path.join("data", "adp_latest.csv")
    if not os.path.exists(adp_path):
        logger.debug("ADP file not found at %s — adp_rank will be None", adp_path)
        return {}
    try:
        df = pd.read_csv(adp_path, usecols=["player_name", "adp_rank"])
        result: Dict[str, int] = {}
        for _, row in df.iterrows():
            key = normalize_name(str(row["player_name"]))
            if key:
                result[key] = int(row["adp_rank"])
        return result
    except Exception as exc:
        logger.warning("Could not load ADP from %s: %s", adp_path, exc)
        return {}


def _cached_adp() -> Dict[str, int]:
    """Return ADP lookup, TTL-cached in-process."""
    cached = _cache_get("adp_lookup")
    if cached is not None:
        return cached  # type: ignore[return-value]
    adp = _load_adp()
    _cache_set("adp_lookup", adp)
    return adp


_FA_MAX_ADP_RANK = 300  # market-relevance ceiling for surfacing free agents


def _is_relevant_free_agent(
    meta: Dict[str, Any], norm: str, adp_lookup: Dict[str, int]
) -> bool:
    """Filter for surfacing a free agent as a waiver/draft target.

    The Sleeper registry marks long-retired players as ``Active`` (Philip
    Rivers included), and the projection engine can emit phantom points from
    stale seasonal rows. Two guards keep the lists trustworthy:

    - the player must be on an NFL roster (retired/unsigned → ``team`` empty),
    - when ADP data is loaded, the market must rank them inside the top
      ``_FA_MAX_ADP_RANK`` — nobody actionable in a fantasy league sits
      outside it, but stale-projection artifacts (e.g. a QB the market ranks
      ~494) do.
    """
    if not str(meta.get("team") or "").strip():
        return False
    if adp_lookup:
        rank = adp_lookup.get(norm)
        if rank is None or rank > _FA_MAX_ADP_RANK:
            return False
    return True


def _iter_projected_free_agents(
    player_index: Dict[str, Dict[str, str]],
    proj_lookup: Dict[Tuple[str, str], Dict[str, Any]],
    all_rostered_ids: set,
    adp_lookup: Dict[str, int],
) -> Iterator[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """Yield ``(player_id, registry_meta, projection_row)`` for matchable free agents.

    Shared registry scan behind ``league_waivers`` and ``league_draft_prep``:
    iterates the Sleeper player registry and yields unrostered skill-position
    players that pass the market-relevance filter and have a projection row
    keyed by ``(normalized_name, position)``.  Callers apply endpoint-specific
    enrichment (team-aware tiebreak, ``years_exp``) on the yielded rows.

    This intentionally does NOT reuse ``map_picks_to_projections``: that path
    fuzzy-resolves a short, known pick list into projections, while this scans
    the full ~10k-player registry against a vectorized ``(norm, pos)`` lookup.
    Funnelling the registry through synthesized ``PickEvent`` objects would be
    far slower and would change match semantics (fuzzy fallbacks vs exact
    normalized keys).

    Args:
        player_index: Sleeper player_id → name/pos/team index.
        proj_lookup: ``(normalized_name, POSITION)`` → projection-row dict.
        all_rostered_ids: Sleeper player_ids rostered anywhere in the league.
        adp_lookup: normalized name → ADP rank (market-relevance filter).

    Yields:
        ``(player_id, meta, projection_row)`` tuples; ``projection_row`` is the
        shared lookup dict — callers must copy before mutating.
    """
    for pid, meta in player_index.items():
        if str(pid) in all_rostered_ids:
            continue
        pos = str(meta.get("position") or "").upper()
        if pos not in _SKILL_POSITIONS:
            continue
        norm = meta.get("normalized_name") or normalize_name(
            str(meta.get("full_name") or "")
        )
        if not norm or not _is_relevant_free_agent(meta, norm, adp_lookup):
            continue
        base_row = proj_lookup.get((norm, pos))
        if base_row is None:
            continue
        yield str(pid), meta, base_row


def _build_draft_info(league_id: str, user_id: Optional[str]) -> Optional[DraftInfo]:
    """Fetch the first upcoming/active draft for a league and return a DraftInfo.

    Calls ``GET /v1/league/{league_id}/drafts`` via ``get_drafts_for_league``.

    Args:
        league_id: Sleeper league ID.
        user_id: Calling user's ID; used to look up their slot in ``draft_order``.

    Returns:
        ``DraftInfo`` for the first non-complete draft found, or ``None`` when
        no draft exists or the Sleeper call fails.
    """
    cache_key = f"drafts:{league_id}"
    drafts = _cache_get(cache_key)
    if drafts is None:
        drafts = get_drafts_for_league(league_id, timeout=_SLEEPER_TIMEOUT_S)
        _cache_set(cache_key, drafts)

    if not drafts:
        return None

    # Prefer the first non-complete draft; fall back to the first one.
    target = next(
        (d for d in drafts if isinstance(d, dict) and d.get("status") != "complete"),
        drafts[0] if isinstance(drafts[0], dict) else None,
    )
    if not target:
        return None

    settings = target.get("settings") or {}
    rounds = int(settings.get("rounds") or settings.get("draft_rounds") or 0) or None

    # draft_order maps user_id → slot (1-based) when set by commissioner.
    draft_order = target.get("draft_order") or {}
    user_slot: Optional[int] = None
    if user_id and isinstance(draft_order, dict):
        raw_slot = draft_order.get(user_id) or draft_order.get(str(user_id))
        if raw_slot is not None:
            try:
                user_slot = int(raw_slot)
            except (TypeError, ValueError):
                pass

    return DraftInfo(
        draft_id=str(target.get("draft_id") or ""),
        status=str(target.get("status") or "pre_draft"),
        type=str(target.get("type") or "snake"),
        rounds=rounds if rounds and rounds > 0 else 1,
        user_slot=user_slot,
    )


@league_router.get("/{league_id}/draft-prep", response_model=LeagueDraftPrepResponse)
def league_draft_prep(
    league_id: str,
    user_id: Optional[str] = Query(None, description="Sleeper user_id"),
    season: Optional[int] = Query(
        None, description="Season year (defaults to current)"
    ),
) -> LeagueDraftPrepResponse:
    """Return pre-draft analysis for a league: keeper candidates, draft info, best available, and rookies.

    Designed for the flagship pre-season view shown when a connected league has
    ``status='pre_draft'`` or an empty roster. Four sections are returned:

    1. **keeper_candidates** — user's current roster (if any) sorted by
       league-scored ``projected_season_points`` descending, with a
       ``taxi_eligible`` flag derived from ``league.settings.taxi_years``.
    2. **draft_info** — draft type, rounds, and the user's draft slot when set.
    3. **best_available** — top-30 unrostered skill-position players by
       league-scored projection, each annotated with ``adp_rank`` (from
       ``data/adp_latest.csv``) and ``value = adp_rank - projection_rank``.
    4. **rookies** — subset of best_available where ``years_exp == 0``,
       re-sorted by ``adp_rank`` ascending since our rookie projections are
       conservative positional fallbacks.

    Args:
        league_id: Numeric Sleeper league ID.
        user_id: Sleeper user_id (optional; keeper_candidates empty when absent).
        season: NFL season year (default: current UTC year).

    Returns:
        ``LeagueDraftPrepResponse`` with all four sections populated.

    Raises:
        HTTPException 400: non-numeric league_id.
        HTTPException 404: league not found on Sleeper.
    """
    ctx = _build_league_context(league_id, season)
    league = ctx.league
    use_season = ctx.use_season
    scoring_settings = ctx.scoring_settings
    league_settings: Dict[str, Any] = league.get("settings") or {}

    # Sleeper's taxi_years counts eligible SEASONS: taxi_years=2 → players with
    # years_exp <= 1 (rookies + second-years) may occupy taxi slots; taxi_years=1
    # → rookies only. (Matches Sleeper app behavior; verified against a live
    # taxi_years=2 / taxi_allow_vets=0 league.)
    taxi_years_raw = league_settings.get("taxi_years")
    try:
        taxi_years = int(taxi_years_raw) if taxi_years_raw is not None else 0
    except (TypeError, ValueError):
        taxi_years = 0
    taxi_threshold = max(0, taxi_years - 1) if taxi_years > 0 else -1

    # --- load projections, registry, ADP (all TTL-cached) -------------------
    projections = _league_projections(league_id, use_season, scoring_settings)
    player_index = _cached_player_index()
    raw_registry = _cached_raw_registry()
    adp_lookup = _cached_adp()

    # --- rosters: all league members + user's own players -------------------
    rosters = _cached_rosters(league_id)

    all_rostered_ids: set = set()
    user_player_ids: List[str] = []
    for r in rosters:
        if not isinstance(r, dict):
            continue
        pids = [str(p) for p in (r.get("players") or []) if p]
        all_rostered_ids.update(pids)
        if user_id and str(r.get("owner_id") or "") == user_id:
            user_player_ids = pids

    # --- draft info ----------------------------------------------------------
    draft_info = _build_draft_info(league_id, user_id)

    # --- keeper candidates ---------------------------------------------------
    keeper_candidates: List[KeeperCandidate] = []
    if user_player_ids and projections is not None and not projections.empty:
        matched, _ = _map_roster_to_projections(
            user_player_ids, projections, player_index
        )
        # Sort descending by projected_season_points.
        matched.sort(
            key=lambda r: _safe_float(r.get("projected_season_points")) or 0,
            reverse=True,
        )
        for row in matched:
            pid = str(row.get("sleeper_player_id") or "")
            # Use raw_registry (not the processed player_index) to preserve years_exp.
            raw_rec = raw_registry.get(pid, {})
            try:
                yrs = int(raw_rec.get("years_exp") or 0)
            except (TypeError, ValueError):
                yrs = 0
            taxi_eligible = (taxi_threshold >= 0) and (yrs <= taxi_threshold)
            keeper_candidates.append(
                KeeperCandidate(
                    sleeper_player_id=pid,
                    player_name=row.get("player_name"),
                    position=str(row.get("position") or "").upper() or None,
                    team=row.get("team") or row.get("recent_team"),
                    projected_season_points=_safe_float(
                        row.get("projected_season_points")
                    ),
                    taxi_eligible=taxi_eligible,
                )
            )

    # --- best available ------------------------------------------------------
    # Build a projection lookup keyed by (normalized_name, position).
    best_available: List[BestAvailablePlayer] = []
    rookies: List[BestAvailablePlayer] = []

    if projections is not None and not projections.empty:
        # Same vectorized (norm, pos) → row lookup league_waivers uses —
        # includes the _team tiebreak for same-name/same-position collisions.
        proj_lookup = build_projection_lookup(projections)

        # Scan registry for unrostered skill-position players with projections.
        free_agent_rows: List[Dict[str, Any]] = []
        for pid, _meta, proj_row in _iter_projected_free_agents(
            player_index, proj_lookup, all_rostered_ids, adp_lookup
        ):
            enriched = dict(proj_row)
            enriched["sleeper_player_id"] = pid
            # Use raw_registry to get years_exp (build_player_index strips it).
            raw_rec = raw_registry.get(pid, {})
            try:
                enriched["years_exp"] = int(raw_rec.get("years_exp") or 0)
            except (TypeError, ValueError):
                enriched["years_exp"] = 0
            free_agent_rows.append(enriched)

        # Sort by projected_season_points descending; take top 30.
        free_agent_rows.sort(
            key=lambda r: _safe_float(r.get("projected_season_points")) or 0,
            reverse=True,
        )
        top_30 = free_agent_rows[:30]

        for proj_rank, row in enumerate(top_30, start=1):
            norm_name = normalize_name(str(row.get("player_name") or ""))
            adp_rank_val = adp_lookup.get(norm_name)
            value: Optional[int] = None
            if adp_rank_val is not None:
                value = adp_rank_val - proj_rank
            entry = BestAvailablePlayer(
                sleeper_player_id=str(row.get("sleeper_player_id") or ""),
                player_name=row.get("player_name"),
                position=str(row.get("position") or "").upper() or None,
                team=row.get("team") or row.get("recent_team"),
                projected_season_points=_safe_float(row.get("projected_season_points")),
                adp_rank=adp_rank_val,
                projection_rank=proj_rank,
                value=value,
                years_exp=row.get("years_exp"),
            )
            best_available.append(entry)

        # Rookies: years_exp==0, sorted by adp_rank ascending (None → end).
        rookies = sorted(
            [p for p in best_available if p.years_exp == 0],
            key=lambda p: (p.adp_rank is None, p.adp_rank or 9999),
        )

    return LeagueDraftPrepResponse(
        league_id=league_id,
        user_id=user_id or "",
        draft_info=draft_info,
        keeper_candidates=keeper_candidates,
        best_available=best_available,
        rookies=rookies,
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _safe_float(val: Any) -> Optional[float]:
    """Convert a value to float, returning None for NaN or non-numeric values."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else round(f, 1)
    except (TypeError, ValueError):
        return None
