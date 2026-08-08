"""/api/yahoo endpoints — Yahoo OAuth connect + league import for the web UI.

Wraps the existing v8.0 machinery (``src/yahoo_oauth.YahooOAuth``,
``src/yahoo_draft.fetch_yahoo_json``) in a browser-friendly flow:

1. ``GET /api/yahoo/status``  — credentials/connection state.
2. ``GET /api/yahoo/auth-url`` — authorization URL to open in a new tab.
3. ``GET /api/yahoo/callback`` — Yahoo redirects here with ``?code=``; the
   code is exchanged and tokens persist to ``data/yahoo_tokens.json``.
4. ``GET /api/yahoo/leagues`` — the connected account's NFL leagues.
5. ``GET /api/yahoo/league/{league_key}/teams`` — teams + rosters.

Single-account by design: the token file is server-global, matching the CLI
draft co-pilot this reuses — fine for a personal deployment. The redirect
URI must be registered on the Yahoo app; set ``YAHOO_REDIRECT_URI`` to
``https://<backend-host>/api/yahoo/callback`` (falls back to ``oob``, where
the user pastes the code into ``POST /api/yahoo/connect``).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.yahoo_draft import (
    _iter_collection,
    _merge_fragments,
    _user_league_candidates,
    fetch_yahoo_json,
)
from src.yahoo_oauth import DEFAULT_REDIRECT_URI, YahooAuthError, YahooOAuth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/yahoo", tags=["yahoo"])


def _oauth() -> YahooOAuth:
    """OAuth manager with the web redirect URI (env) or oob fallback."""
    return YahooOAuth(
        redirect_uri=os.environ.get("YAHOO_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class YahooStatus(BaseModel):
    has_credentials: bool
    connected: bool
    redirect_mode: str  # "callback" | "oob"


class YahooAuthUrl(BaseModel):
    url: str
    redirect_mode: str


class YahooConnectRequest(BaseModel):
    code: str


class YahooLeague(BaseModel):
    league_key: str
    league_id: str
    name: str
    draft_status: str


class YahooRosterPlayer(BaseModel):
    player_name: str
    position: str
    team: Optional[str] = None
    selected_position: Optional[str] = None


class YahooTeam(BaseModel):
    team_key: str
    name: str
    is_my_team: bool = False
    roster: List[YahooRosterPlayer] = []


class YahooTeamsResponse(BaseModel):
    league_key: str
    teams: List[YahooTeam]


# ---------------------------------------------------------------------------
# Connection endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=YahooStatus)
def yahoo_status() -> YahooStatus:
    """Credential + connection state for the connect card."""
    oauth = _oauth()
    return YahooStatus(
        has_credentials=oauth.has_credentials(),
        connected=bool(oauth.get_access_token()),
        redirect_mode=(
            "oob" if oauth.redirect_uri == DEFAULT_REDIRECT_URI else "callback"
        ),
    )


@router.get("/auth-url", response_model=YahooAuthUrl)
def yahoo_auth_url() -> YahooAuthUrl:
    """Authorization URL the user opens once to grant access."""
    oauth = _oauth()
    try:
        url = oauth.build_authorization_url()
    except YahooAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return YahooAuthUrl(
        url=url,
        redirect_mode=(
            "oob" if oauth.redirect_uri == DEFAULT_REDIRECT_URI else "callback"
        ),
    )


@router.get("/callback", response_class=HTMLResponse)
def yahoo_callback(code: str = Query("")) -> HTMLResponse:
    """OAuth redirect target — exchanges the code and stores tokens."""
    if not code:
        return HTMLResponse("<h3>Missing ?code — authorization failed.</h3>", 400)
    try:
        tokens = _oauth().exchange_code(code)
    except YahooAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not tokens:
        return HTMLResponse(
            "<h3>Yahoo rejected the code — retry the connect flow.</h3>", 502
        )
    return HTMLResponse(
        "<h3>Yahoo connected ✓</h3><p>You can close this tab and return "
        "to the app.</p>"
    )


@router.post("/connect", response_model=YahooStatus)
def yahoo_connect(body: YahooConnectRequest) -> YahooStatus:
    """oob fallback: user pastes the on-screen code here."""
    try:
        tokens = _oauth().exchange_code(body.code.strip())
    except YahooAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not tokens:
        raise HTTPException(status_code=502, detail="Yahoo rejected the code.")
    return yahoo_status()


# ---------------------------------------------------------------------------
# League endpoints
# ---------------------------------------------------------------------------


def _require_connected() -> YahooOAuth:
    oauth = _oauth()
    if not oauth.get_access_token():
        raise HTTPException(
            status_code=401,
            detail="Yahoo not connected — run the connect flow first.",
        )
    return oauth


@router.get("/leagues", response_model=List[YahooLeague])
def yahoo_leagues(
    season: Optional[int] = Query(None, description="Season (default: current year)"),
) -> List[YahooLeague]:
    """NFL leagues for the connected Yahoo account."""
    from datetime import datetime, timezone

    oauth = _require_connected()
    use_season = season or datetime.now(timezone.utc).year
    candidates = _user_league_candidates(str(use_season), oauth)
    return [
        YahooLeague(
            league_key=c["draft_id"],
            league_id=c["league_id"],
            name=c["name"],
            draft_status=c["status"],
        )
        for c in candidates
    ]


def _parse_team_fragments(team_node: Any) -> Dict[str, Any]:
    """Merge Yahoo's team fragment list into one dict (name, team_key, ...)."""
    merged = _merge_fragments(team_node)
    # Yahoo nests the fragment list one level deeper under "team" sometimes.
    if not merged.get("team_key") and isinstance(team_node, dict):
        merged = _merge_fragments(team_node.get("team"))
    return merged


def _parse_roster_players(team_frag: Dict[str, Any]) -> List[YahooRosterPlayer]:
    """Extract roster players from a merged team fragment with a roster node."""
    players: List[YahooRosterPlayer] = []
    roster = team_frag.get("roster")
    if not isinstance(roster, dict):
        return players
    # roster -> "0" -> players -> {"0": {player: [...]}, ..., count}
    zero = roster.get("0") if "players" not in roster else roster
    node = zero.get("players") if isinstance(zero, dict) else None
    for p in _iter_collection(node):
        frag = _merge_fragments(p.get("player") if isinstance(p, dict) else p)
        name = frag.get("name")
        full = (
            str(name.get("full")) if isinstance(name, dict) and name.get("full") else ""
        )
        if not full:
            continue
        sel = frag.get("selected_position")
        sel_pos = None
        if sel is not None:
            sel_frag = _merge_fragments(sel)
            sel_pos = str(sel_frag.get("position") or "") or None
        players.append(
            YahooRosterPlayer(
                player_name=full,
                position=str(frag.get("display_position") or "?"),
                team=str(frag.get("editorial_team_abbr") or "").upper() or None,
                selected_position=sel_pos,
            )
        )
    return players


@router.get("/league/{league_key}/teams", response_model=YahooTeamsResponse)
def yahoo_league_teams(league_key: str) -> YahooTeamsResponse:
    """All teams in a league with rosters; flags the connected user's team."""
    oauth = _require_connected()
    node = fetch_yahoo_json(f"/league/{league_key}/teams/roster/players", oauth)
    content = node.get("fantasy_content") if isinstance(node, dict) else None
    if not isinstance(content, dict):
        raise HTTPException(
            status_code=502, detail="Yahoo API unavailable — retry shortly."
        )
    league_node = content.get("league")
    teams_out: List[YahooTeam] = []
    frags = league_node if isinstance(league_node, list) else [league_node]
    for frag in frags:
        if not isinstance(frag, dict) or "teams" not in frag:
            continue
        for t in _iter_collection(frag["teams"]):
            team_frag = _parse_team_fragments(t)
            key = str(team_frag.get("team_key") or "")
            if not key:
                continue
            teams_out.append(
                YahooTeam(
                    team_key=key,
                    name=str(team_frag.get("name") or key),
                    is_my_team=bool(team_frag.get("is_owned_by_current_login")),
                    roster=_parse_roster_players(team_frag),
                )
            )
    return YahooTeamsResponse(league_key=league_key, teams=teams_out)
