"""/api/espn endpoints — ESPN league import for the web UI.

Thin surface over ``src/espn_league.py`` (Phase 89 import machinery).
Public leagues need no cookies; private leagues pass espn_s2/SWID
per-request — cookies are used for the one ESPN call and never stored
or logged. Live-draft capture remains NO-GO (no ESPN API).
"""

from __future__ import annotations

import logging
from typing import List, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.espn_league import (
    extract_league_info,
    extract_rosters,
    extract_teams,
    fetch_league,
    find_my_team_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/espn", tags=["espn"])


class EspnImportRequest(BaseModel):
    league_id: int
    season: int
    espn_s2: Optional[str] = Field(
        None, description="Private-league cookie (not stored)"
    )
    swid: Optional[str] = Field(None, description="Private-league cookie (not stored)")


class EspnRosterPlayer(BaseModel):
    player_name: str
    position: str
    pro_team: Optional[str] = None
    lineup_slot: Optional[str] = None
    is_starter: bool = False
    injury_status: Optional[str] = None


class EspnTeam(BaseModel):
    team_id: int
    team_name: str
    abbrev: Optional[str] = None
    owner_name: Optional[str] = None
    wins: int = 0
    losses: int = 0
    is_my_team: bool = False
    roster: List[EspnRosterPlayer] = []


class EspnImportResponse(BaseModel):
    league_id: int
    season: int
    league_name: Optional[str] = None
    team_count: Optional[int] = None
    scoring_type: Optional[str] = None
    teams: List[EspnTeam]


@router.post("/import", response_model=EspnImportResponse)
def import_league(body: EspnImportRequest) -> EspnImportResponse:
    """Import an ESPN league: settings, teams, and full rosters."""
    cookies = {}
    if body.espn_s2:
        cookies["espn_s2"] = body.espn_s2.strip()
    if body.swid:
        swid = body.swid.strip()
        if not swid.startswith("{"):
            swid = "{" + swid.strip("{}") + "}"
        cookies["SWID"] = swid

    try:
        payload = fetch_league(body.league_id, body.season, cookies=cookies or None)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except requests.RequestException:
        logger.warning("ESPN fetch failed", exc_info=True)
        raise HTTPException(
            status_code=502, detail="ESPN API unreachable — retry shortly."
        )

    info = extract_league_info(payload)
    teams_df = extract_teams(payload)
    rosters_df = extract_rosters(payload)
    my_team_id = (
        find_my_team_id(payload, cookies.get("SWID", ""))
        if cookies.get("SWID")
        else None
    )

    rosters_by_team: dict = {}
    if not rosters_df.empty:
        for r in rosters_df.to_dict("records"):
            rosters_by_team.setdefault(r["team_id"], []).append(
                EspnRosterPlayer(
                    player_name=str(r.get("player_name") or ""),
                    position=str(r.get("position") or "?"),
                    pro_team=r.get("pro_team"),
                    lineup_slot=r.get("lineup_slot"),
                    is_starter=bool(r.get("is_starter")),
                    injury_status=str(r.get("injury_status") or "") or None,
                )
            )

    teams: List[EspnTeam] = []
    for t in teams_df.to_dict("records"):
        tid = int(t.get("team_id") or 0)
        teams.append(
            EspnTeam(
                team_id=tid,
                team_name=str(t.get("team_name") or f"Team {tid}"),
                abbrev=t.get("abbrev") or None,
                owner_name=t.get("owner_name") or None,
                wins=int(t.get("wins") or 0),
                losses=int(t.get("losses") or 0),
                is_my_team=bool(my_team_id is not None and tid == my_team_id),
                roster=rosters_by_team.get(tid, []),
            )
        )

    return EspnImportResponse(
        league_id=body.league_id,
        season=body.season,
        league_name=info.get("name"),
        team_count=info.get("size"),
        scoring_type=str(info.get("scoring_type") or "") or None,
        teams=teams,
    )
