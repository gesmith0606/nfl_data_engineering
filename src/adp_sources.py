"""Real Average Draft Position (ADP) fetchers — FFC + ESPN (fail-open).

``data/adp_latest.csv`` historically stored Sleeper's ``search_rank`` — a
popularity index, NOT actual draft position. This module fetches *real* ADP
from two free, unauthenticated sources:

* :func:`fetch_ffc_adp` — Fantasy Football Calculator's public REST API,
  scoring- and league-size-aware.
* :func:`fetch_espn_adp` — ESPN's undocumented ``leaguedefaults`` endpoint,
  which carries ``ownership.averageDraftPosition`` per player.

Both fetchers follow the project-wide D-06 fail-open contract established by
``src/sleeper_http.py``: any network, HTTP, or JSON-parse error is logged at
WARNING and an empty (but correctly-columned) DataFrame is returned rather
than raising. Callers should treat an empty return as "skip this source".

Public API
----------
``fetch_ffc_adp(scoring, year, teams=12) -> pd.DataFrame``
``fetch_espn_adp(year) -> pd.DataFrame``

Both return a DataFrame with columns ``[player_name, position, team, adp,
stdev, times_drafted, source, scoring_format, fetched_at, name_key]``.
``stdev``/``times_drafted`` are ``NaN`` for ESPN (not exposed by that
endpoint). ``name_key`` is the ``sleeper_player_map.normalize_name`` join key
used to line ADP rows up against our projections.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from src.sleeper_player_map import normalize_name

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT_S: int = 15
_USER_AGENT: str = "NFLDataEngineering/1.0 (adp-sources-helper)"
# ESPN's undocumented API 403s on the default urllib UA; a browser-like UA
# is required (matches the pattern already used to reach ESPN elsewhere).
_ESPN_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

ADP_COLUMNS: List[str] = [
    "player_name",
    "position",
    "team",
    "adp",
    "stdev",
    "times_drafted",
    "source",
    "scoring_format",
    "fetched_at",
    "name_key",
]

# FFC's REST path segment per our scoring format key.
_FFC_SCORING_MAP: Dict[str, str] = {
    "ppr": "ppr",
    "half_ppr": "half-ppr",
    "standard": "standard",
}

# FFC exposes DEF/PK; our schema uses DST/K everywhere else.
_POSITION_NORMALIZE: Dict[str, str] = {"DEF": "DST", "PK": "K"}

# ESPN defaultPositionId -> our position code.
_ESPN_POSITION_MAP: Dict[int, str] = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "DST",
}


def _empty_adp_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ADP_COLUMNS)


def _to_float(val: Any) -> Optional[float]:
    """Best-effort float conversion; ``None``/NaN/unparseable -> ``None``."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (TypeError, ValueError):
        return None


def _normalize_position(pos: Any) -> str:
    upper = str(pos or "").upper()
    return _POSITION_NORMALIZE.get(upper, upper)


def _fetch_json(
    url: str, headers: Dict[str, str], timeout: int = _DEFAULT_TIMEOUT_S
) -> Any:
    """GET ``url`` and return parsed JSON. Fail-open to ``{}`` on any error."""
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https URLs)
            raw = resp.read()
    except HTTPError as exc:
        logger.warning(
            "ADP source HTTP %d for %s — fail-open returning {}", exc.code, url
        )
        return {}
    except URLError as exc:
        logger.warning(
            "ADP source network error for %s: %s — fail-open returning {}",
            url,
            exc.reason,
        )
        return {}
    except (TimeoutError, OSError) as exc:
        logger.warning(
            "ADP source transport error for %s: %s — fail-open returning {}",
            url,
            exc,
        )
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "ADP source invalid JSON from %s: %s — fail-open returning {}", url, exc
        )
        return {}


# ---------------------------------------------------------------------------
# Fantasy Football Calculator
# ---------------------------------------------------------------------------


def fetch_ffc_adp(scoring: str, year: int, teams: int = 12) -> pd.DataFrame:
    """Fetch real ADP from the Fantasy Football Calculator public API.

    Args:
        scoring: One of ``"ppr"``, ``"half_ppr"``, ``"standard"``.
        year:    Draft season year.
        teams:   League size (default 12).

    Returns:
        Normalized ADP DataFrame (see module docstring); empty on any error
        or an unrecognized ``scoring`` value.
    """
    fmt = _FFC_SCORING_MAP.get(scoring)
    if fmt is None:
        logger.warning(
            "fetch_ffc_adp: unknown scoring format '%s' — fail-open returning empty",
            scoring,
        )
        return _empty_adp_df()

    url = (
        f"https://fantasyfootballcalculator.com/api/v1/adp/{fmt}"
        f"?teams={teams}&year={year}"
    )
    payload = _fetch_json(url, headers={"User-Agent": _USER_AGENT})
    players = payload.get("players") if isinstance(payload, dict) else None
    if not isinstance(players, list) or not players:
        logger.warning("fetch_ffc_adp: no players returned from %s — fail-open", url)
        return _empty_adp_df()

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for p in players:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "player_name": name,
                "position": _normalize_position(p.get("position")),
                "team": str(p.get("team") or "").upper(),
                "adp": _to_float(p.get("adp")),
                "stdev": _to_float(p.get("stdev")),
                "times_drafted": _to_float(p.get("times_drafted")),
                "source": "ffc",
                "scoring_format": scoring,
                "fetched_at": fetched_at,
                "name_key": normalize_name(name),
            }
        )

    if not rows:
        logger.warning("fetch_ffc_adp: %s had no usable player rows — fail-open", url)
        return _empty_adp_df()

    return pd.DataFrame(rows, columns=ADP_COLUMNS)


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------


def fetch_espn_adp(year: int) -> pd.DataFrame:
    """Fetch real ADP from ESPN's undocumented ``leaguedefaults`` endpoint.

    This endpoint is not versioned or documented by ESPN and may change
    shape without notice — any structural surprise fails open to an empty
    DataFrame rather than raising, per D-06.

    Args:
        year: Draft season year.

    Returns:
        Normalized ADP DataFrame (see module docstring); ``stdev`` and
        ``times_drafted`` are always ``None`` (not exposed by ESPN).
    """
    url = (
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}"
        f"/segments/0/leaguedefaults/3?view=kona_player_info"
    )
    fantasy_filter = json.dumps(
        {
            "players": {
                "limit": 400,
                "sortDraftRanks": {
                    "sortPriority": 100,
                    "sortAsc": True,
                    "value": "STANDARD",
                },
            }
        }
    )
    payload = _fetch_json(
        url,
        headers={
            "User-Agent": _ESPN_USER_AGENT,
            "X-Fantasy-Filter": fantasy_filter,
        },
    )
    players = payload.get("players") if isinstance(payload, dict) else None
    if not isinstance(players, list) or not players:
        logger.warning("fetch_espn_adp: no players returned from %s — fail-open", url)
        return _empty_adp_df()

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for entry in players:
        if not isinstance(entry, dict):
            continue
        player = entry.get("player")
        if not isinstance(player, dict):
            continue
        name = str(player.get("fullName") or "").strip()
        if not name:
            continue
        position = _ESPN_POSITION_MAP.get(player.get("defaultPositionId"), "")
        ownership = player.get("ownership")
        adp = (
            _to_float(ownership.get("averageDraftPosition"))
            if isinstance(ownership, dict)
            else None
        )
        rows.append(
            {
                "player_name": name,
                "position": position,
                # proTeamId -> team abbreviation mapping is not trivial from
                # this payload alone; left blank per spec rather than guessed.
                "team": "",
                "adp": adp,
                "stdev": None,
                "times_drafted": None,
                "source": "espn",
                "scoring_format": "standard",
                "fetched_at": fetched_at,
                "name_key": normalize_name(name),
            }
        )

    if not rows:
        logger.warning("fetch_espn_adp: %s had no usable player rows — fail-open", url)
        return _empty_adp_df()

    return pd.DataFrame(rows, columns=ADP_COLUMNS)
