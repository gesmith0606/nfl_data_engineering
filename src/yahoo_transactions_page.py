"""Pure parsers for Yahoo's league pages (transactions, rosters, player list).

Yahoo's Fantasy API is approval-gated and returns ``401
additional_authorization_required`` for read scope, and new apps cannot get
write scope at all, so the site's own pages are the only source. This module
holds no IO: it turns the Transactions page's ``body.innerText`` into rows,
the same way :mod:`src.espn_draft_page` splits parsing from the browser.

That matters because the waiver bid model prices a claim off what the room
has already paid for a player. Without this reader Feetball had only the
league-wide median to go on — the statistic that produced three overbids in
one session.

A record on that page reads::

    Evan McPherson Cin - K        <- the player added
    $1 Waiver                     <- the winning bid ("Free Agent" when none)
    Cam Little Jax - K            <- the player dropped (optional)
    To Waivers
    Teez Nutz                     <- the fantasy team
    Oct 21, 4:52 am               <- terminates the record
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

#: ``Name Tm - POS`` with an optional status suffix (``NA``, ``IR``, ``IR-R``).
PLAYER_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<team>[A-Za-z]{2,3})\s*-\s*"
    r"(?P<pos>QB|RB|WR|TE|K|DEF)(?:\s+[A-Z-]+)?$"
)
BID_RE = re.compile(r"^\$(?P<bid>\d+)\s+Waiver$")
DATE_RE = re.compile(r"^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{1,2}:\d{2}\s*(?:am|pm)$", re.I)
#: Lines that describe how a move happened rather than who moved.
METHOD_LINES = {"free agent", "to waivers", "to free agent", "waiver"}


def parse_yahoo_transactions(text: str) -> List[Dict[str, Any]]:
    """Parse one Transactions page into add/drop records.

    Args:
        text: ``document.body.innerText`` of ``/f1/<id>/transactions``.

    Returns:
        One dict per record, oldest last (page order is newest first), with
        ``add``/``drop`` as ``{"name", "team", "pos"}`` or None, ``bid`` as an
        int or None, ``team`` the fantasy team, and ``when`` the raw date.
        Malformed records are skipped rather than raising — a partial history
        still prices most claims.
    """
    records: List[Dict[str, Any]] = []
    pending: List[Any] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if DATE_RE.match(line):
            rec = _close(pending, line)
            if rec:
                records.append(rec)
            pending = []
            continue
        pending.append(line)
        if len(pending) > 12:  # never let a malformed page grow unbounded
            pending = pending[-12:]
    return records


def _player(line: str) -> Optional[Dict[str, str]]:
    m = PLAYER_RE.match(line)
    if not m:
        return None
    return {
        "name": m.group("name").strip(),
        "team": m.group("team").upper(),
        "pos": m.group("pos"),
    }


def _close(pending: List[str], when: str) -> Optional[Dict[str, Any]]:
    """Turn the lines gathered before a date line into one record."""
    add = drop = None
    bid: Optional[int] = None
    fantasy_team = None
    i = 0
    while i < len(pending):
        who = _player(pending[i])
        if who is None:
            # The last non-player, non-method line before the date is the team.
            if pending[i].lower() not in METHOD_LINES:
                fantasy_team = pending[i]
            i += 1
            continue
        nxt = pending[i + 1].strip() if i + 1 < len(pending) else ""
        low = nxt.lower()
        if low.startswith("to "):
            drop = who
        else:
            add = who
            m = BID_RE.match(nxt)
            if m:
                bid = int(m.group("bid"))
        i += 2 if nxt else 1
    if add is None and drop is None:
        return None
    return {
        "add": add,
        "drop": drop,
        "bid": bid,
        "team": fantasy_team,
        "when": when,
    }


#: Yahoo glues annotations and a status onto the name in ``innerText``:
#: ``Ladd McConkeyQVideo ForecastPlayer Note``.
_ANNOTATIONS = (
    "Video Forecast",
    "New Player Note",
    "Player Note",
    "No new player Notes",
)
#: Status tokens Yahoo appends directly to a surname.
_STATUS_SUFFIXES = ("IR-R", "IR", "SUSP", "NA", "PUP", "Q", "O", "D", "P")
#: ``Tm - POS`` on the line after the name.
TEAM_POS_RE = re.compile(r"^(?P<team>[A-Za-z]{2,3})\s*-\s*(?P<pos>QB|RB|WR|TE|K|DEF)$")


def clean_player_name(raw: str) -> str:
    """Strip Yahoo's glued-on annotations and status from a name.

    ``"Ladd McConkeyQVideo ForecastPlayer Note"`` -> ``"Ladd McConkey"``.
    """
    name = raw.strip()
    for note in _ANNOTATIONS:
        name = name.replace(note, "")
    name = name.strip()
    for suffix in _STATUS_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            trimmed = name[: -len(suffix)].rstrip()
            # Only a glued status, never a real last letter: the character
            # before it must end a word (lower-case or '.').
            if trimmed and (trimmed[-1].islower() or trimmed[-1] == "."):
                name = trimmed
                break
    return name.strip()


def parse_yahoo_player_names(text: str) -> List[str]:
    """Player names from a Yahoo roster or player-list page.

    Every row renders the name on one line and ``Tm - POS`` on the next, which
    is the only stable anchor in ``innerText``. Yahoo's API has no read scope,
    so this is how a Yahoo league gets the live roster and free-agent pool the
    Sleeper and ESPN paths read directly.

    Args:
        text: ``document.body.innerText`` of a roster or players page.

    Returns:
        Names in page order, de-duplicated, annotations and status stripped.
    """
    lines = [ln.strip() for ln in text.splitlines()]
    seen: Dict[str, None] = {}
    for i, line in enumerate(lines):
        if i == 0 or not TEAM_POS_RE.match(line):
            continue
        prev = next((lines[j] for j in range(i - 1, -1, -1) if lines[j]), "")
        name = clean_player_name(prev)
        if name and not TEAM_POS_RE.match(name):
            seen.setdefault(name, None)
    return list(seen)
