"""Read our Yahoo team's roster and the lineup actually set on the site.

Yahoo enabled read-only Fantasy Sports access (``fspt-r``) for this app on
2026-10-28. Until then Yahoo "published no roster we could read without a
login", so :mod:`scripts.set_lineups` fell back to a pasted ``--roster-file``
and could only ever print a recommendation.

That fallback rotted silently. On 2026-10-28 the committed Feetball file was
three weeks old and missing four rostered players -- a starting QB (Jordan
Love), a WR1 (Justin Jefferson), the kicker and the defense -- so the week-8
board started a quarterback who was on IR and left K and DEF unfillable.
A live read is the fix: a lineup built for a team you no longer have is wrong
in a way no optimizer can recover from.

Writes stay unavailable: the Yahoo Fantasy API team confirmed on 2026-10-26
that setting lineups, add/drop and waiver claims "isn't available at this
time", and that it is not a tier we can apply for. This module therefore
reads only, and Feetball's SLOT column stays a recommendation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

from src.yahoo_draft import _iter_collection, _merge_fragments, fetch_yahoo_json
from src.yahoo_oauth import YahooOAuth

logger = logging.getLogger(__name__)

#: Yahoo's multi-position slot labels mapped onto the Sleeper-style labels the
#: rest of the lineup code speaks (``slots_from_shape`` in set_lineups).
YAHOO_SLOT_MAP: Dict[str, str] = {
    "W/R": "FLEX",
    "W/T": "FLEX",
    "W/R/T": "FLEX",
    "Q/W/R/T": "SUPER_FLEX",
    "D": "DEF",
    "DST": "DEF",
}

#: Yahoo position strings that mean "team defense".
_DEF_POSITIONS = {"DEF", "D", "DST", "D/ST"}


def normalize_slot(slot: str) -> str:
    """Map a Yahoo ``selected_position`` onto our slot vocabulary."""
    raw = str(slot or "").strip().upper()
    return YAHOO_SLOT_MAP.get(raw, raw)


def normalize_position(position: str) -> str:
    """Map a Yahoo ``display_position`` onto our position vocabulary."""
    raw = str(position or "").strip().upper()
    return "DEF" if raw in _DEF_POSITIONS else raw


def parse_team_roster(node: Any) -> List[Dict[str, str]]:
    """Flatten a Yahoo team ``roster`` payload into per-player records.

    Pure: takes the already-parsed JSON so it can be exercised without a
    network call or a token.

    Args:
        node: The parsed JSON from ``/team/<team_key>/roster``.

    Returns:
        One dict per player with ``player_key``, ``name``, ``position``,
        ``team`` and ``slot`` (the slot the player currently occupies, e.g.
        ``QB``/``FLEX``/``BN``/``IR``). Empty when the payload has no players.
    """
    players_node = _find_players_node(node)
    if players_node is None:
        logger.warning("parse_team_roster: no players collection in payload")
        return []

    out: List[Dict[str, str]] = []
    for member in _iter_collection(players_node):
        record = member.get("player") if isinstance(member, dict) else member
        flat = _merge_fragments(record)
        player_key = str(flat.get("player_key") or "")
        if not player_key:
            continue
        name_obj = flat.get("name")
        name = ""
        if isinstance(name_obj, dict):
            name = str(name_obj.get("full") or "").strip()
        selected = _merge_fragments(flat.get("selected_position"))
        out.append(
            {
                "player_key": player_key,
                "name": name,
                "position": normalize_position(
                    flat.get("display_position") or flat.get("primary_position") or ""
                ),
                "team": str(flat.get("editorial_team_abbr") or "").upper(),
                "slot": normalize_slot(selected.get("position", "")),
            }
        )
    return out


def _find_players_node(node: Any) -> Optional[Any]:
    """Locate the ``players`` collection inside a roster payload."""
    found: List[Any] = []

    def walk(obj: Any) -> None:
        if found:
            return
        if isinstance(obj, dict):
            if "players" in obj:
                found.append(obj["players"])
                return
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(node)
    return found[0] if found else None


def team_key(league_id: str, team_id: str, game: str = "nfl") -> str:
    """Build a Yahoo team key, e.g. ``nfl.l.658684.t.10``.

    ``nfl`` is Yahoo's alias for the current season's game, so this resolves to
    the league's current year without pinning a game id that goes stale.
    """
    return f"{game}.l.{league_id}.t.{team_id}"


def fetch_team_roster(
    league_id: str,
    team_id: str,
    oauth: Optional[YahooOAuth] = None,
) -> List[Dict[str, str]]:
    """Read our roster and current lineup slots from Yahoo.

    Fail-open (D-06): returns ``[]`` when credentials, the grant or the network
    are unavailable, so the caller can fall back to a pasted roster file rather
    than crash.
    """
    manager = oauth or YahooOAuth()
    if not manager.has_credentials():
        logger.warning("fetch_team_roster: no Yahoo credentials — returning []")
        return []
    node = fetch_yahoo_json(f"/team/{team_key(league_id, team_id)}/roster", manager)
    if not node:
        return []
    return parse_team_roster(node)


def starters_by_slot(
    roster: List[Mapping[str, str]],
    labels: List[str],
) -> Dict[str, List[str]]:
    """Group the rostered player names by the slot each currently occupies.

    Args:
        roster: Records from :func:`parse_team_roster`.
        labels: The league's starter slot labels, in board order.

    Returns:
        ``label -> [name, ...]``. A label with no occupant maps to an empty
        list, which is how an unfilled slot (scoring zero) becomes visible.
    """
    grouped: Dict[str, List[str]] = {label: [] for label in labels}
    for player in roster:
        slot = str(player.get("slot") or "")
        if slot in grouped:
            grouped[slot].append(str(player.get("name") or ""))
    return grouped
