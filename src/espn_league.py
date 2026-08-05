"""ESPN league import via session cookies (the Fantasy Footballers pattern).

ESPN has no official fantasy API, but its own web app runs on a stable
private JSON API (``lm-api-reads.fantasy.espn.com/apis/v3``) that accepts the
user's browser session cookies — ``SWID`` + ``espn_s2``. This is exactly how
the Fantasy Footballers Chrome extension does "full team import": the
extension reads those two cookies and their backend calls this API.

We skip the extension. The user copies the cookies out of DevTools once per
season (``espn_s2`` lives ~1 year) into ``.env``:

    ESPN_S2=AEB...   (long URL-encoded token)
    ESPN_SWID={XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}

Scope (deliberate): **post-draft league/team import** — league settings,
teams, rosters, members, and completed draft results. The live-draft NO-GO
in :mod:`src.espn_adapter` stands: these cookies do not unlock ESPN's
realtime draft backend (Phase 89 spike, ESPN-01). Public leagues work
without cookies; private leagues require both.

How to find your cookies (Chrome): fantasy.espn.com while logged in →
DevTools → Application → Cookies → https://fantasy.espn.com → copy the
``espn_s2`` value and the ``SWID`` value (braces included).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

try:
    from src.draft_models import PickEvent
except ImportError:  # pragma: no cover - direct-script import path
    from draft_models import PickEvent

logger = logging.getLogger(__name__)

ESPN_API_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

#: Views covering settings + teams + rosters + members + completed draft.
DEFAULT_VIEWS = ("mSettings", "mTeam", "mRoster", "mDraftDetail")

#: ESPN defaultPositionId -> fantasy position.
POSITION_ID_MAP: Dict[int, str] = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "DST",
}

#: ESPN lineupSlotId -> slot label (starters vs bench/IR).
LINEUP_SLOT_MAP: Dict[int, str] = {
    0: "QB",
    2: "RB",
    3: "RB/WR",
    4: "WR",
    5: "WR/TE",
    6: "TE",
    7: "OP",
    16: "DST",
    17: "K",
    20: "BN",
    21: "IR",
    23: "FLEX",
}

#: ESPN proTeamId -> nflverse team abbreviation.
PRO_TEAM_MAP: Dict[int, str] = {
    0: "FA",
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LA",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WAS",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}


def cookies_from_env() -> Dict[str, str]:
    """Build the ESPN auth cookie dict from ``ESPN_S2`` / ``ESPN_SWID`` env vars.

    The SWID is normalised to ESPN's braced GUID form (``{...}``) — DevTools
    shows it braced but users often paste it bare.

    Returns:
        Dict with ``espn_s2`` and ``SWID`` keys; empty dict when neither env
        var is set (public-league mode).
    """
    espn_s2 = os.environ.get("ESPN_S2", "").strip()
    swid = os.environ.get("ESPN_SWID", "").strip()
    if not espn_s2 and not swid:
        return {}
    if swid and not swid.startswith("{"):
        swid = "{" + swid.strip("{}") + "}"
    cookies = {}
    if espn_s2:
        cookies["espn_s2"] = espn_s2
    if swid:
        cookies["SWID"] = swid
    return cookies


def fetch_league(
    league_id: int,
    season: int,
    views: Optional[List[str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Fetch a league payload from ESPN's v3 fantasy API.

    Args:
        league_id: ESPN league id (the number in the league URL).
        season:    NFL season year.
        views:     API views to request (default ``DEFAULT_VIEWS``).
        cookies:   Auth cookies (default: :func:`cookies_from_env`). Public
                   leagues work with none.
        timeout:   Request timeout in seconds.

    Returns:
        Parsed league JSON dict.

    Raises:
        PermissionError: 401 — league is private and cookies are missing,
            expired, or belong to a non-member account.
        LookupError: 404 — no such league for that season.
        requests.RequestException: Other network/HTTP failures.
    """
    if cookies is None:
        cookies = cookies_from_env()
    url = f"{ESPN_API_BASE}/seasons/{season}/segments/0/leagues/{league_id}"
    params = [("view", v) for v in (views or list(DEFAULT_VIEWS))]
    response = requests.get(
        url,
        params=params,
        cookies=cookies,
        headers={"Accept": "application/json"},
        timeout=timeout,
    )
    if response.status_code == 401:
        raise PermissionError(
            "ESPN returned 401 — private league. Set ESPN_S2 + ESPN_SWID in "
            ".env (DevTools > Application > Cookies > fantasy.espn.com) with "
            "an account that is a member of this league; espn_s2 expires "
            "~yearly."
        )
    if response.status_code == 404:
        raise LookupError(
            f"ESPN returned 404 — no league {league_id} in season {season}."
        )
    response.raise_for_status()
    return response.json()


def _team_display_name(team: Dict[str, Any]) -> str:
    """Return a team's display name across ESPN payload vintages."""
    name = (team.get("name") or "").strip()
    if name:
        return name
    combined = f"{team.get('location', '')} {team.get('nickname', '')}".strip()
    return combined or f"Team {team.get('id', '?')}"


def extract_league_info(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Summarise league-level settings from an ``mSettings`` payload.

    Args:
        payload: League JSON (must include the ``mSettings`` view).

    Returns:
        Dict with league name, size, scoring type, roster info and the
        current scoring period.
    """
    settings = payload.get("settings", {})
    scoring = settings.get("scoringSettings", {})
    receptions = None
    for item in scoring.get("scoringItems", []):
        if item.get("statId") == 53:  # receptions
            receptions = item.get("points") or (
                item.get("pointsOverrides", {}) or {}
            ).get("16")
    return {
        "league_id": payload.get("id"),
        "season": payload.get("seasonId"),
        "name": settings.get("name", ""),
        "size": settings.get("size"),
        "scoring_type": scoring.get("scoringType"),
        "points_per_reception": receptions,
        "current_scoring_period": payload.get("scoringPeriodId"),
        "draft_complete": payload.get("draftDetail", {}).get("drafted"),
    }


def extract_teams(payload: Dict[str, Any]) -> pd.DataFrame:
    """Extract the team table from an ``mTeam`` payload.

    Args:
        payload: League JSON (must include the ``mTeam`` view).

    Returns:
        DataFrame: one row per team — id, name, abbrev, owner GUIDs, owner
        display name, record.
    """
    member_names = {
        m.get("id"): m.get("displayName", "") for m in payload.get("members", [])
    }
    rows = []
    for team in payload.get("teams", []):
        owners = team.get("owners", [])
        record = (team.get("record", {}) or {}).get("overall", {}) or {}
        rows.append(
            {
                "team_id": team.get("id"),
                "team_name": _team_display_name(team),
                "abbrev": team.get("abbrev", ""),
                "owner_ids": owners,
                "owner_name": member_names.get(owners[0], "") if owners else "",
                "wins": record.get("wins", 0),
                "losses": record.get("losses", 0),
            }
        )
    return pd.DataFrame(rows)


def extract_rosters(payload: Dict[str, Any]) -> pd.DataFrame:
    """Extract every team's roster from an ``mRoster`` payload.

    Args:
        payload: League JSON (must include the ``mRoster`` view).

    Returns:
        DataFrame: one row per rostered player — team_id, team_name,
        player_id, player_name, position, pro_team, lineup_slot,
        is_starter, injury_status.
    """
    rows = []
    for team in payload.get("teams", []):
        team_name = _team_display_name(team)
        entries = (team.get("roster", {}) or {}).get("entries", [])
        for entry in entries:
            player = (entry.get("playerPoolEntry", {}) or {}).get("player", {})
            slot_id = entry.get("lineupSlotId")
            slot = LINEUP_SLOT_MAP.get(slot_id, str(slot_id))
            rows.append(
                {
                    "team_id": team.get("id"),
                    "team_name": team_name,
                    "player_id": player.get("id"),
                    "player_name": player.get("fullName", ""),
                    "position": POSITION_ID_MAP.get(
                        player.get("defaultPositionId"), "?"
                    ),
                    "pro_team": PRO_TEAM_MAP.get(player.get("proTeamId"), "?"),
                    "lineup_slot": slot,
                    "is_starter": slot not in ("BN", "IR"),
                    "injury_status": player.get("injuryStatus", ""),
                }
            )
    return pd.DataFrame(rows)


def find_my_team_id(payload: Dict[str, Any], swid: str) -> Optional[int]:
    """Find the team owned by the SWID's account.

    Args:
        payload: League JSON (``mTeam`` view).
        swid: The user's SWID GUID (with or without braces).

    Returns:
        The team id, or None when the SWID owns no team in this league.
    """
    if not swid:
        return None
    target = "{" + swid.strip("{}").upper() + "}"
    for team in payload.get("teams", []):
        owners = [str(o).upper() for o in team.get("owners", [])]
        if target in owners:
            return team.get("id")
    return None


def extract_draft_picks(payload: Dict[str, Any]) -> List[PickEvent]:
    """Convert a completed draft (``mDraftDetail``) into neutral PickEvents.

    ESPN's draft detail carries only player ids; names/positions resolve
    through the rosters in the same payload (drafted-then-dropped players
    keep the raw id as their name — never silently dropped).

    Args:
        payload: League JSON (``mDraftDetail`` + ``mRoster`` views).

    Returns:
        List of :class:`PickEvent`, empty when the draft has not completed.
    """
    detail = payload.get("draftDetail", {}) or {}
    if not detail.get("drafted"):
        return []

    players: Dict[int, Dict[str, Any]] = {}
    for team in payload.get("teams", []):
        for entry in (team.get("roster", {}) or {}).get("entries", []):
            player = (entry.get("playerPoolEntry", {}) or {}).get("player", {})
            if player.get("id") is not None:
                players[player["id"]] = player

    picks: List[PickEvent] = []
    for pick in detail.get("picks", []):
        player = players.get(pick.get("playerId"), {})
        full_name = player.get("fullName", "") or str(pick.get("playerId", ""))
        first, _, last = full_name.partition(" ")
        picks.append(
            PickEvent(
                pick_no=pick.get("overallPickNumber", 0),
                round=pick.get("roundId", 0),
                draft_slot=pick.get("roundPickNumber", 0),
                roster_id=pick.get("teamId"),
                picked_by=str(pick.get("teamId", "")),
                sleeper_player_id=str(pick.get("playerId", "")),
                first_name=first,
                last_name=last,
                position=POSITION_ID_MAP.get(player.get("defaultPositionId"), "?"),
                team=PRO_TEAM_MAP.get(player.get("proTeamId"), "?"),
                is_keeper=bool(pick.get("keeper", False)),
            )
        )
    picks.sort(key=lambda p: p.pick_no)
    return picks
