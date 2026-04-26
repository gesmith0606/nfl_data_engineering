"""Phase 74: Sleeper user / league / roster endpoints.

All Sleeper public-API HTTP traffic flows through ``src/sleeper_http.py``
per CONTEXT D-01 (LOCKED in Phase 73).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response

from src.config import SENTIMENT_CONFIG
from src.sleeper_http import fetch_sleeper_json

from ..models.schemas import (
    SleeperLeague,
    SleeperRoster,
    SleeperRosterPlayer,
    SleeperUser,
    SleeperUserLoginResponse,
)

router = APIRouter(prefix="/sleeper", tags=["sleeper"])

_SESSION_COOKIE = "sleeper_user_id"
_SESSION_MAX_AGE = 7 * 24 * 60 * 60  # 7 days


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
                settings=item.get("settings") if isinstance(item.get("settings"), dict) else None,
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
        raise HTTPException(status_code=404, detail=f"Sleeper user '{username}' not found")

    use_season = season if season is not None else _current_year()
    leagues_url = SENTIMENT_CONFIG["sleeper_leagues_url"].format(
        user_id=user.user_id, season=use_season
    )
    leagues = _to_leagues(fetch_sleeper_json(leagues_url))

    # Set HttpOnly cookie for subsequent requests
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

    # Lazy load player registry only if there are rosters.
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
            SleeperRosterPlayer(player_id=str(pid), **_resolve_player_meta(str(pid), registry))
            for pid in starters_ids
            if pid
        ]
        bench = [
            SleeperRosterPlayer(player_id=str(pid), **_resolve_player_meta(str(pid), registry))
            for pid in bench_ids
            if pid
        ]
        owner_id = item.get("owner_id")
        out.append(
            SleeperRoster(
                roster_id=int(item.get("roster_id") or 0),
                league_id=league_id,
                owner_user_id=str(owner_id) if owner_id else None,
                is_user_roster=bool(user_id and owner_id and str(owner_id) == str(user_id)),
                starters=starters,
                bench=bench,
            )
        )
    return out
