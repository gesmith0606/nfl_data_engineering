"""Real Average Draft Position (ADP) fetchers — FFC + ESPN + MFL (fail-open).

``data/adp_latest.csv`` historically stored Sleeper's ``search_rank`` — a
popularity index, NOT actual draft position. This module fetches *real* ADP
from free, unauthenticated sources:

* :func:`fetch_ffc_adp` — Fantasy Football Calculator's public REST API.
  NOTE (verified 2026-08): the ``teams`` query param is silently IGNORED by
  the FFC servers — 8/10/12/14-team requests for the same year return
  identical results — as are ``date``/``days``/``position``. The scoring
  format (``ppr``/``half-ppr``/``standard``) is the only param that actually
  changes the response.
* :func:`fetch_espn_adp` — ESPN's undocumented ``leaguedefaults`` endpoint,
  which carries ``ownership.averageDraftPosition`` per player.
* :func:`fetch_mfl_adp` — MyFantasyLeague's public ``export?TYPE=adp``
  endpoint. Not scoring-format-aware (unlike FFC); ``PERIOD=ALL`` aggregates
  the whole draft season for a year, which is noisier than FFC's tight
  late-Aug/early-Sept closed-season window — treat MFL as a historical
  cross-check, not a primary source.
* :func:`fetch_sleeper_adp` — despite the name, every entry in this feed
  carries ``"company": "rotowire"``. This is RotoWire's composite ADP
  re-served through Sleeper's (undocumented) season-projections API, NOT
  ADP derived from actual Sleeper draft rooms. See the function docstring.

Both fetchers follow the project-wide D-06 fail-open contract established by
``src/sleeper_http.py``: any network, HTTP, or JSON-parse error is logged at
WARNING and an empty (but correctly-columned) DataFrame is returned rather
than raising. Callers should treat an empty return as "skip this source".

Public API
----------
``fetch_ffc_adp(scoring, year, teams=12) -> pd.DataFrame``
``fetch_espn_adp(year) -> pd.DataFrame``
``fetch_mfl_adp(year, scoring=...) -> pd.DataFrame``
``fetch_sleeper_adp(scoring, year) -> pd.DataFrame``

All return a DataFrame with columns ``[player_name, position, team, adp,
high, low, stdev, times_drafted, source, scoring_format, fetched_at,
name_key]``. Any field not exposed by a given source (e.g. ``high``/``low``
for ESPN/Sleeper, ``stdev`` for MFL) is ``NaN``. ``name_key`` is the
``sleeper_player_map.normalize_name`` join key used to line ADP rows up
against our projections.
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
    "high",
    "low",
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
        teams:   League size — accepted for API-shape compatibility, but
                 NOTE (verified 2026-08) FFC silently ignores this param:
                 8/10/12/14-team requests for the same year/scoring return
                 identical results. Kept for readability/future-proofing,
                 not because it currently changes the response.

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
                "high": _to_float(p.get("high")),
                "low": _to_float(p.get("low")),
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

    df = pd.DataFrame(rows, columns=ADP_COLUMNS)
    # Stash the aggregation-window meta (start_date/end_date/etc.) as a
    # DataFrame attr rather than a new column — callers that need the true
    # "ADP at draft time" snapshot date (e.g. scripts/ingest_adp_history.py)
    # can read df.attrs["ffc_meta"]["end_date"] without a second network
    # call; every other caller can ignore it (attrs don't affect columns/
    # to_csv output).
    df.attrs["ffc_meta"] = payload.get("meta") if isinstance(payload, dict) else None
    return df


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


# ---------------------------------------------------------------------------
# Sleeper — actually RotoWire's composite ADP, re-served via Sleeper's feed
# ---------------------------------------------------------------------------

_SLEEPER_ADP_FIELD: Dict[str, str] = {
    "ppr": "adp_ppr",
    "half_ppr": "adp_half_ppr",
    "standard": "adp_std",
}

_SLEEPER_ADP_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


def fetch_sleeper_adp(scoring: str, year: int) -> pd.DataFrame:
    """Fetch ADP from Sleeper's season projections feed.

    CORRECTED PROVENANCE (verified 2026-08): despite the function name and
    this feed living on Sleeper's API, every entry in the payload carries
    ``"company": "rotowire"``. This is RotoWire's composite ADP re-served
    through Sleeper's (undocumented) season-projections endpoint
    (``stats.adp_half_ppr`` etc.) — it is NOT ADP derived from actual
    Sleeper draft rooms, despite the ``source`` label below still reading
    ``"sleeper"`` (kept as-is: the CLI ``--source sleeper`` flag, the
    ``adp_sleeper_{scoring}.csv`` filename convention, the web API's
    ``?source=sleeper`` query param, and the frontend's ``adp_source:
    'sleeper'`` config are all keyed on this exact string — relabeling the
    per-row value would desync the CSV's own "source" column from the
    filename/URL that selects it). It IS still real ADP (not the legacy
    ``search_rank`` popularity index the ``sleeper_rank`` source uses) —
    just sourced from RotoWire's panel, not Sleeper drafts.

    Args:
        scoring: One of ``"ppr"``, ``"half_ppr"``, ``"standard"``.
        year:    Draft season year.

    Returns:
        Normalized ADP DataFrame (see module docstring); ``stdev``/
        ``times_drafted`` are ``NaN`` (not exposed). Empty on any error.
    """
    field = _SLEEPER_ADP_FIELD.get(scoring)
    if field is None:
        logger.warning(
            "fetch_sleeper_adp: unknown scoring format '%s' — fail-open", scoring
        )
        return _empty_adp_df()

    pos_params = "&".join(f"position[]={p}" for p in _SLEEPER_ADP_POSITIONS)
    url = (
        f"https://api.sleeper.app/projections/nfl/{year}"
        f"?season_type=regular&{pos_params}&order_by={field}"
    )
    payload = _fetch_json(url, headers={"User-Agent": _USER_AGENT})
    if not isinstance(payload, list) or not payload:
        logger.warning("fetch_sleeper_adp: no rows from %s — fail-open", url)
        return _empty_adp_df()

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        stats = entry.get("stats") or {}
        player = entry.get("player") or {}
        adp = _to_float(stats.get(field)) if isinstance(stats, dict) else None
        if adp is None or adp <= 0:
            continue
        first = str(player.get("first_name") or "").strip()
        last = str(player.get("last_name") or "").strip()
        name = f"{first} {last}".strip()
        if not name:
            continue
        rows.append(
            {
                "player_name": name,
                "position": _normalize_position(player.get("position")),
                "team": str(entry.get("team") or player.get("team") or "").upper(),
                "adp": adp,
                "stdev": None,
                "times_drafted": None,
                # NOT real Sleeper draft-room data — see the RotoWire
                # provenance note in this function's docstring. Value kept
                # as "sleeper" because the CLI/API/filename layers are all
                # keyed on this exact string (see docstring).
                "source": "sleeper",
                "scoring_format": scoring,
                "fetched_at": fetched_at,
                "name_key": normalize_name(name),
            }
        )

    if not rows:
        logger.warning("fetch_sleeper_adp: %s had no usable rows — fail-open", url)
        return _empty_adp_df()

    df = pd.DataFrame(rows, columns=ADP_COLUMNS)
    return df.sort_values("adp").reset_index(drop=True)


# ---------------------------------------------------------------------------
# MyFantasyLeague (MFL)
# ---------------------------------------------------------------------------

# Per-process memoized id -> {name, position, team} crosswalk, keyed by year.
# MFL's ADP export only carries player ids; names/positions/teams require a
# separate TYPE=players call. Memoized so a multi-format/multi-year history
# backfill (see scripts/ingest_adp_history.py) doesn't refetch the ~2600-
# player crosswalk once per (year, scoring) combo.
_MFL_PLAYERS_CACHE: Dict[int, Dict[str, Dict[str, str]]] = {}


def _fetch_mfl_players(year: int) -> Dict[str, Dict[str, str]]:
    """Fetch (and memoize) the MFL id -> {name, position, team} crosswalk.

    Fail-open: any network/HTTP/JSON error returns ``{}`` (logged at
    WARNING by ``_fetch_json``), which makes ``fetch_mfl_adp`` skip every
    row for that year rather than raising.
    """
    if year in _MFL_PLAYERS_CACHE:
        return _MFL_PLAYERS_CACHE[year]

    url = f"https://api.myfantasyleague.com/{year}/export?TYPE=players&JSON=1"
    payload = _fetch_json(url, headers={"User-Agent": _USER_AGENT})
    players_obj = payload.get("players") if isinstance(payload, dict) else None
    raw_list = players_obj.get("player") if isinstance(players_obj, dict) else None

    crosswalk: Dict[str, Dict[str, str]] = {}
    if isinstance(raw_list, list):
        for p in raw_list:
            if isinstance(p, dict) and p.get("id"):
                crosswalk[str(p["id"])] = {
                    "name": str(p.get("name") or ""),
                    "position": str(p.get("position") or ""),
                    "team": str(p.get("team") or ""),
                }

    _MFL_PLAYERS_CACHE[year] = crosswalk
    return crosswalk


def _flip_mfl_name(raw: str) -> str:
    """MFL names are ``"Last, First"`` (also true for DST rows, e.g.
    ``"Bills, Buffalo"``) — flip to ``"First Last"`` to match every other
    source. Names without a comma are returned unchanged."""
    raw = str(raw or "").strip()
    if "," not in raw:
        return raw
    last, _, first = raw.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def fetch_mfl_adp(year: int, scoring: str = "half_ppr") -> pd.DataFrame:
    """Fetch real ADP from MyFantasyLeague's public ``export?TYPE=adp`` API.

    Uses ``PERIOD=ALL`` (verified 2026-08: ``PERIOD=RECENT`` returns
    ``totalDrafts=0`` for closed seasons — only ``ALL`` works for
    2021-2025). Unlike FFC, MFL's ADP is NOT scoring-format-aware — there is
    no validated per-format query param, so ``PERIOD=ALL`` aggregates every
    draft for the year regardless of scoring. ``scoring`` is accepted only
    for output-schema parity with the other fetchers (populates
    ``scoring_format``); it has no effect on the request.

    ``PERIOD=ALL`` also aggregates across the *entire* draft season, which
    is noisier than FFC's tight late-Aug/early-Sept closed-season window —
    treat MFL as a historical cross-check, not a primary ADP source. Current
    in-progress-season (e.g. 2026) data is thin and contaminated with
    dynasty drafts.

    Team codes are MFL's own convention (e.g. ``"SFO"``, ``"NOS"``), not
    normalized to the nflverse abbreviations used elsewhere in this repo.

    Args:
        year:    Draft season year.
        scoring: One of ``"ppr"``, ``"half_ppr"``, ``"standard"`` — labeling
            only (see above); defaults to ``"half_ppr"``.

    Returns:
        Normalized ADP DataFrame (see module docstring); ``stdev`` is always
        ``NaN`` (not exposed by this endpoint). Empty on any error, an
        unrecognized ``scoring`` value, or an empty/unfetchable crosswalk.
    """
    if scoring not in _FFC_SCORING_MAP:
        logger.warning(
            "fetch_mfl_adp: unknown scoring format '%s' — fail-open returning empty",
            scoring,
        )
        return _empty_adp_df()

    url = f"https://api.myfantasyleague.com/{year}/export?TYPE=adp&PERIOD=ALL&JSON=1"
    payload = _fetch_json(url, headers={"User-Agent": _USER_AGENT})
    adp_obj = payload.get("adp") if isinstance(payload, dict) else None
    entries = adp_obj.get("player") if isinstance(adp_obj, dict) else None
    if not isinstance(entries, list) or not entries:
        logger.warning("fetch_mfl_adp: no players returned from %s — fail-open", url)
        return _empty_adp_df()

    crosswalk = _fetch_mfl_players(year)
    if not crosswalk:
        logger.warning(
            "fetch_mfl_adp: players crosswalk unavailable for year %d — fail-open",
            year,
        )
        return _empty_adp_df()

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        player_id = str(entry.get("id") or "")
        info = crosswalk.get(player_id)
        if info is None:
            continue
        name = _flip_mfl_name(info["name"])
        if not name:
            continue
        rows.append(
            {
                "player_name": name,
                "position": _normalize_position(info["position"]),
                "team": info["team"].upper(),
                "adp": _to_float(entry.get("averagePick")),
                "high": _to_float(entry.get("minPick")),
                "low": _to_float(entry.get("maxPick")),
                "stdev": None,
                "times_drafted": _to_float(entry.get("draftsSelectedIn")),
                "source": "mfl",
                "scoring_format": scoring,
                "fetched_at": fetched_at,
                "name_key": normalize_name(name),
            }
        )

    if not rows:
        logger.warning("fetch_mfl_adp: %s had no usable player rows — fail-open", url)
        return _empty_adp_df()

    df = pd.DataFrame(rows, columns=ADP_COLUMNS)
    return df.sort_values("adp").reset_index(drop=True)
