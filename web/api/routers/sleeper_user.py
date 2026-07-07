"""Phase 74: Sleeper user / league / roster endpoints.

All Sleeper public-API HTTP traffic flows through ``src/sleeper_http.py``
per CONTEXT D-01 (LOCKED in Phase 73).

Plan-3 League Sync: adds ``league_router`` (prefix ``/league``) with three
read-only endpoints backed by live Sleeper API calls, 15-minute TTL cache,
and projection re-scoring via ``src/league_scoring.py``.
"""

from __future__ import annotations

import glob
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response

from src.config import SENTIMENT_CONFIG
from src.draft_models import PickEvent
from src.league_scoring import score_with_settings, unmodeled_offense_keys
from src.roster_optimizer import drop_candidates, optimal_lineup
from src.sleeper_http import fetch_sleeper_json, get_league, get_league_rosters
from src.sleeper_player_map import (
    build_player_index,
    load_sleeper_players,
    map_picks_to_projections,
    normalize_name,
)

from ..models.schemas import (
    LeagueOverviewResponse,
    LeagueRosterPlayer,
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


def _latest_preseason_parquet(season: int) -> Optional[pd.DataFrame]:
    """Load the newest committed preseason projections parquet for ``season``.

    Uses the same glob pattern as ``scripts/draft_live.py`` so the API always
    serves the same Gold artifact that the CLI draft co-pilot uses.

    Returns:
        DataFrame if found, else ``None``.
    """
    pattern = os.path.join(
        "data", "gold", "projections", "preseason", f"season={season}", "*.parquet"
    )
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    try:
        df = pd.read_parquet(files[-1])
        # Alias recent_team → team so downstream functions have a consistent
        # ``team`` column for tiebreaking during name matching.
        if "recent_team" in df.columns and "team" not in df.columns:
            df = df.rename(columns={"recent_team": "team"})
        return df
    except Exception as exc:
        logger.warning("Could not read preseason parquet %s: %s", files[-1], exc)
        return None


def _load_projections(season: int) -> Optional[pd.DataFrame]:
    """Load season projections, trying preseason parquet first.

    Mirrors the priority in ``scripts/draft_live.py::load_projections`` so the
    web API returns the same values as the CLI tool for the same inputs.

    Returns:
        DataFrame (never empty) or ``None`` when no source is available.
    """
    df = _latest_preseason_parquet(season)
    if df is not None and not df.empty:
        return df
    logger.warning("No preseason parquet for season=%d; projections unavailable", season)
    return None


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
                settings=item.get("settings")
                if isinstance(item.get("settings"), dict)
                else None,
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
        registry_payload = fetch_sleeper_json(SENTIMENT_CONFIG["sleeper_players_url"])
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
# Plan-3 League Sync endpoints
# ---------------------------------------------------------------------------


@league_router.get("/{league_id}/overview", response_model=LeagueOverviewResponse)
def league_overview(
    league_id: str,
    user_id: Optional[str] = Query(None, description="Sleeper user_id to load roster"),
    season: Optional[int] = Query(None, description="Season year (defaults to current)"),
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
    _validate_numeric_league_id(league_id)
    league = _require_league(league_id)

    use_season = season if season is not None else _current_year()
    scoring_settings: Dict[str, Any] = league.get("scoring_settings") or {}
    roster_positions: List[str] = league.get("roster_positions") or []
    scoring_label = _scoring_format_label(scoring_settings)
    deltas = _scoring_delta_badges(scoring_settings)
    unmodeled = unmodeled_offense_keys(scoring_settings)

    user_roster_rows: List[LeagueRosterPlayer] = []
    if user_id:
        cache_key = f"rosters:{league_id}"
        rosters = _cache_get(cache_key)
        if rosters is None:
            rosters = get_league_rosters(league_id, timeout=_SLEEPER_TIMEOUT_S)
            _cache_set(cache_key, rosters)

        try:
            _, player_ids = _require_user_roster(rosters, user_id, league_id)
        except HTTPException:
            player_ids = []

        if player_ids:
            projections = _load_projections(use_season)
            if projections is not None and not projections.empty:
                rescored = score_with_settings(projections, scoring_settings)
                player_index = build_player_index(load_sleeper_players())
                matched, _ = _map_roster_to_projections(
                    player_ids, rescored, player_index
                )
                for row in matched:
                    user_roster_rows.append(
                        LeagueRosterPlayer(
                            sleeper_player_id=str(
                                row.get("sleeper_player_id") or ""
                            ),
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
        league_name=str(league.get("name") or ""),
        season=str(league.get("season") or use_season),
        status=league.get("status"),
        total_rosters=league.get("total_rosters"),
        roster_positions=roster_positions,
        scoring_format_label=scoring_label,
        scoring_deltas=deltas,
        unmodeled_keys=unmodeled,
        user_roster=user_roster_rows,
    )


@league_router.get("/{league_id}/roster-report", response_model=RosterReportResponse)
def league_roster_report(
    league_id: str,
    user_id: str = Query(..., description="Sleeper user_id"),
    season: Optional[int] = Query(None, description="Season year (defaults to current)"),
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
    _validate_numeric_league_id(league_id)
    league = _require_league(league_id)
    use_season = season if season is not None else _current_year()

    # --- projections ---------------------------------------------------------
    projections = _load_projections(use_season)
    if projections is None or projections.empty:
        raise HTTPException(
            status_code=503,
            detail=(
                "Projections unavailable — preseason parquet not found. "
                "Run `generate_projections.py --preseason` first."
            ),
        )

    # --- league settings + re-score -----------------------------------------
    scoring_settings: Dict[str, Any] = league.get("scoring_settings") or {}
    roster_positions: List[str] = league.get("roster_positions") or []
    if scoring_settings:
        projections = score_with_settings(projections, scoring_settings)

    roster_format = (
        "superflex"
        if "SUPER_FLEX" in roster_positions or "SUPERFLEX" in roster_positions
        else "standard"
    )

    # --- user's roster -------------------------------------------------------
    cache_key = f"rosters:{league_id}"
    rosters = _cache_get(cache_key)
    if rosters is None:
        rosters = get_league_rosters(league_id, timeout=_SLEEPER_TIMEOUT_S)
        _cache_set(cache_key, rosters)

    _, player_ids = _require_user_roster(rosters, user_id, league_id)

    # --- map player_ids → projection rows ------------------------------------
    player_index = build_player_index(load_sleeper_players())
    matched, unmatched_ids = _map_roster_to_projections(
        player_ids, projections, player_index
    )

    if not matched:
        return RosterReportResponse(
            league_id=league_id,
            user_id=user_id,
            roster_size=0,
            roster_format=roster_format,
            unmatched_player_ids=unmatched_ids,
        )

    # --- optimal lineup + drop candidates ------------------------------------
    lineup = optimal_lineup(
        matched, roster_format, roster_positions=roster_positions or None
    )
    drops = drop_candidates(
        matched, roster_format, top_n=5, roster_positions=roster_positions or None
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
        roster_format=roster_format,
        starters=starters,
        bench=bench_rows,
        drop_candidates=drop_rows,
        unmatched_player_ids=unmatched_ids,
    )


@league_router.get("/{league_id}/waivers", response_model=WaiversResponse)
def league_waivers(
    league_id: str,
    user_id: str = Query(..., description="Sleeper user_id"),
    season: Optional[int] = Query(None, description="Season year (defaults to current)"),
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
    _validate_numeric_league_id(league_id)
    league = _require_league(league_id)
    use_season = season if season is not None else _current_year()

    projections = _load_projections(use_season)
    if projections is None or projections.empty:
        raise HTTPException(
            status_code=503,
            detail=(
                "Projections unavailable — preseason parquet not found. "
                "Run `generate_projections.py --preseason` first."
            ),
        )

    scoring_settings: Dict[str, Any] = league.get("scoring_settings") or {}
    roster_positions: List[str] = league.get("roster_positions") or []
    if scoring_settings:
        projections = score_with_settings(projections, scoring_settings)

    roster_format = (
        "superflex"
        if "SUPER_FLEX" in roster_positions or "SUPERFLEX" in roster_positions
        else "standard"
    )

    # --- all rostered players across entire league ---------------------------
    cache_key = f"rosters:{league_id}"
    rosters = _cache_get(cache_key)
    if rosters is None:
        rosters = get_league_rosters(league_id, timeout=_SLEEPER_TIMEOUT_S)
        _cache_set(cache_key, rosters)

    all_rostered_ids: set = set()
    user_player_ids: List[str] = []
    for r in rosters:
        if not isinstance(r, dict):
            continue
        pids = [str(p) for p in (r.get("players") or []) if p]
        all_rostered_ids.update(pids)
        if str(r.get("owner_id") or "") == user_id:
            user_player_ids = pids

    if not user_player_ids:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} not found in league {league_id}.",
        )

    # --- build Sleeper player_id → projections mapping -----------------------
    player_index = build_player_index(load_sleeper_players())

    # Map all registry entries to projection rows to find free agents.
    # Build a fast lookup: normalized_name + position → projection row.
    proj_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, row in projections.iterrows():
        name_key = normalize_name(str(row.get("player_name") or ""))
        pos_key = str(row.get("position") or "").upper()
        if name_key and pos_key:
            proj_lookup[(name_key, pos_key)] = row.to_dict()

    # Identify free agents: skill-position players in Sleeper registry that
    # are not rostered in the league and have a projection row.
    free_agent_rows: List[Dict[str, Any]] = []
    for pid, meta in player_index.items():
        if str(pid) in all_rostered_ids:
            continue
        pos = str(meta.get("position") or "").upper()
        if pos not in _SKILL_POSITIONS:
            continue
        norm = meta.get("normalized_name") or normalize_name(
            str(meta.get("full_name") or "")
        )
        row = proj_lookup.get((norm, pos))
        if row is None:
            continue
        row = dict(row)
        row["sleeper_player_id"] = str(pid)
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
    user_lineup = optimal_lineup(
        user_matched, roster_format, roster_positions=roster_positions or None
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
        roster_positions=roster_positions,
        targets=targets,
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
