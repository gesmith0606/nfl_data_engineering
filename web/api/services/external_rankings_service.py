"""Service layer for fetching, caching, and comparing external fantasy rankings.

Supported sources:
  - Sleeper ADP (reliable, free API)
  - FantasyPros ECR (may be rate-limited or blocked)
  - ESPN Rankings (may be rate-limited or blocked)
  - consensus (average of the above three, skipping sources that returned nothing)

Cache-first fallback chain (ADVR-03 contract):
  1. Always attempt a live fetch via ``_fetch_live(source)``. On success, write
     the cache and return ``stale=False, cache_age_hours=None``.
  2. On any transport failure / non-2xx / parse error, fall back to
     ``data/external/{source}_rankings.json``. Return ``stale=True`` and
     populate ``cache_age_hours`` from the cache file's fetched_at timestamp.
  3. When neither live nor cache yields data, return ``players=[]`` with
     ``stale=True, cache_age_hours=None``. Never raise HTTPException.

Cache file format (canonical envelope written by ``_save_cache``)::

    {
      "source": "sleeper",
      "fetched_at": "2026-04-18T00:00:00+00:00",
      "players": [ { player_name, position, team, external_rank, rank, ... }, ... ]
    }

Older bare-list format is tolerated on read (legacy files) so in-flight caches
are not invalidated on upgrade.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from ..config import DATA_DIR, GOLD_PROJECTIONS_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EXTERNAL_DIR = DATA_DIR / "external"
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
FANTASYPROS_ECR_URL = (
    "https://api.fantasypros.com/public/v2/json/nfl/{season}"
    "/consensus-rankings.php?type={scoring_type}"
)
ESPN_API_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leaguedefaults/3?view=kona_player_info"
)

FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}
REQUEST_TIMEOUT = 30
VALID_SOURCES = {"sleeper", "fantasypros", "espn", "consensus"}

# User-Agent to avoid basic bot detection. Never includes API keys.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Scoring format mapping for FantasyPros
_FP_SCORING_MAP = {
    "ppr": "ppr",
    "half_ppr": "half-ppr",
    "standard": "standard",
}


# ---------------------------------------------------------------------------
# Hardcoded consensus fallback (last-resort when no cache AND all three live
# sources fail simultaneously).
# ---------------------------------------------------------------------------
CONSENSUS_TOP_50: List[Tuple[int, str, str, str]] = [
    # QBs
    (1, "Josh Allen", "QB", "BUF"),
    (3, "Lamar Jackson", "QB", "BAL"),
    (5, "Jalen Hurts", "QB", "PHI"),
    (8, "Patrick Mahomes", "QB", "KC"),
    (14, "Joe Burrow", "QB", "CIN"),
    (22, "C.J. Stroud", "QB", "HOU"),
    (30, "Jayden Daniels", "QB", "WAS"),
    (38, "Kyler Murray", "QB", "ARI"),
    # RBs
    (2, "Saquon Barkley", "RB", "PHI"),
    (4, "Jahmyr Gibbs", "RB", "DET"),
    (6, "Bijan Robinson", "RB", "ATL"),
    (7, "Derrick Henry", "RB", "BAL"),
    (10, "Breece Hall", "RB", "NYJ"),
    (13, "Josh Jacobs", "RB", "GB"),
    (15, "De'Von Achane", "RB", "MIA"),
    (18, "Jonathan Taylor", "RB", "IND"),
    (21, "Joe Mixon", "RB", "HOU"),
    (25, "James Cook", "RB", "BUF"),
    (28, "Alvin Kamara", "RB", "NO"),
    (33, "Kenneth Walker III", "RB", "SEA"),
    (36, "David Montgomery", "RB", "DET"),
    (40, "Isiah Pacheco", "RB", "KC"),
    (42, "Aaron Jones", "RB", "MIN"),
    (47, "Travis Etienne", "RB", "JAX"),
    # WRs
    (9, "Ja'Marr Chase", "WR", "CIN"),
    (11, "CeeDee Lamb", "WR", "DAL"),
    (12, "Amon-Ra St. Brown", "WR", "DET"),
    (16, "Tyreek Hill", "WR", "MIA"),
    (17, "Justin Jefferson", "WR", "MIN"),
    (19, "Puka Nacua", "WR", "LAR"),
    (20, "Malik Nabers", "WR", "NYG"),
    (23, "Nico Collins", "WR", "HOU"),
    (24, "Drake London", "WR", "ATL"),
    (26, "A.J. Brown", "WR", "PHI"),
    (27, "Garrett Wilson", "WR", "NYJ"),
    (29, "Davante Adams", "WR", "NYJ"),
    (31, "Marvin Harrison Jr.", "WR", "ARI"),
    (34, "DK Metcalf", "WR", "SEA"),
    (37, "Chris Olave", "WR", "NO"),
    (39, "Brian Thomas Jr.", "WR", "JAX"),
    (41, "Tee Higgins", "WR", "CIN"),
    (43, "Terry McLaurin", "WR", "WAS"),
    (45, "DeVonta Smith", "WR", "PHI"),
    (48, "Jaylen Waddle", "WR", "MIA"),
    # TEs
    (32, "Travis Kelce", "TE", "KC"),
    (35, "Brock Bowers", "TE", "LV"),
    (44, "Sam LaPorta", "TE", "DET"),
    (46, "Mark Andrews", "TE", "BAL"),
    (49, "George Kittle", "TE", "SF"),
    (50, "Trey McBride", "TE", "ARI"),
]


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------
def _normalize_name(name: str) -> str:
    """Normalize player name for fuzzy matching across sources."""
    n = name.lower().strip()
    for suffix in [" jr.", " jr", " iii", " ii", " iv", " sr.", " sr"]:
        n = n.replace(suffix, "")
    mappings = {
        "amon-ra st. brown": "amon-ra st brown",
        "amon ra st. brown": "amon-ra st brown",
        "de'von achane": "devon achane",
        "kenneth walker": "kenneth walker",
    }
    return mappings.get(n, n)


# ---------------------------------------------------------------------------
# Cache helpers (canonical envelope + legacy-tolerant read)
# ---------------------------------------------------------------------------
def _cache_path(source: str) -> Path:
    """Return the cache file path for a given source."""
    return EXTERNAL_DIR / f"{source}_rankings.json"


def _cache_is_fresh(source: str) -> bool:
    """Return True if the cache file exists and is less than 24 hours old.

    Kept for the /api/rankings/sources status endpoint. Not used to short-circuit
    the live fetch — we always try live so staleness is never hidden from the
    advisor tool.
    """
    path = _cache_path(source)
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < CACHE_MAX_AGE_SECONDS


def _load_cache(source: str) -> Optional[Tuple[List[Dict[str, Any]], datetime]]:
    """Read cached rankings from disk.

    Returns a tuple (players, fetched_at) on success, or None if the file is
    missing or unparseable. Tolerates both the canonical envelope format
    (dict with ``players`` key) and the legacy bare-list format.
    """
    path = _cache_path(source)
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read cache for %s: %s", source, exc)
        return None

    if isinstance(raw, dict) and "players" in raw:
        players = raw.get("players") or []
        fetched_at_str = raw.get("fetched_at")
        fetched_at: datetime
        if fetched_at_str:
            try:
                fetched_at = datetime.fromisoformat(
                    str(fetched_at_str).replace("Z", "+00:00")
                )
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            except ValueError:
                fetched_at = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                )
        else:
            fetched_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return (list(players), fetched_at)

    if isinstance(raw, list):
        fetched_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return (list(raw), fetched_at)

    logger.warning("Unrecognized cache format for %s (type=%s)", source, type(raw))
    return None


def _save_cache(source: str, data: List[Dict[str, Any]]) -> None:
    """Write rankings to the cache file in canonical envelope format."""
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    envelope = {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players": data,
    }
    path = _cache_path(source)
    try:
        path.write_text(json.dumps(envelope, indent=2))
        logger.info("Cached %d rankings for %s -> %s", len(data), source, path)
    except OSError as exc:
        logger.warning("Failed to write cache for %s: %s", source, exc)


# ---------------------------------------------------------------------------
# Live fetchers (pure functions — never raise; return None on failure)
# ---------------------------------------------------------------------------
def _parse_sleeper_payload(payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    """Shape Sleeper's /v1/players/nfl dict into our ranking rows."""
    rows: List[Dict[str, Any]] = []
    for player_id, info in payload.items():
        if not isinstance(info, dict):
            continue
        pos = info.get("position")
        if pos not in FANTASY_POSITIONS:
            continue
        search_rank = info.get("search_rank")
        if search_rank is None or search_rank > 9999:
            continue
        full_name = info.get("full_name") or (
            f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
        )
        if not full_name:
            continue
        status = info.get("status", "")
        if status and status.lower() not in ("active", "active_reserve", ""):
            continue
        rows.append(
            {
                "player_name": full_name,
                "position": pos,
                "team": info.get("team", "") or "",
                "external_rank": int(search_rank),
                "sleeper_id": player_id,
            }
        )
    rows.sort(key=lambda r: r["external_rank"])
    for i, row in enumerate(rows[:limit], 1):
        row["rank"] = i
    return rows[:limit]


def _parse_fantasypros_payload(
    payload: Dict[str, Any], limit: int
) -> List[Dict[str, Any]]:
    players_raw = payload.get("players", []) or []
    rows: List[Dict[str, Any]] = []
    for i, p in enumerate(players_raw[:limit], 1):
        pos = p.get("position", p.get("sport_position", ""))
        if pos not in FANTASY_POSITIONS:
            continue
        rows.append(
            {
                "rank": i,
                "player_name": p.get("player_name", p.get("name", "")),
                "position": pos,
                "team": p.get("player_team_id", p.get("team", "")) or "",
                "external_rank": int(p.get("rank_ecr", i)),
            }
        )
    return rows[:limit]


def _parse_espn_payload(payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    slot_to_pos = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "K"}
    players_raw = payload.get("players", []) or []
    rows: List[Dict[str, Any]] = []
    for i, entry in enumerate(players_raw[:limit], 1):
        p = entry.get("player", entry)
        full_name = p.get("fullName", "")
        if not full_name:
            first = p.get("firstName", "")
            last = p.get("lastName", "")
            full_name = f"{first} {last}".strip()
        slot_id = p.get("defaultPositionId", -1)
        pos = slot_to_pos.get(slot_id, "")
        if not pos or pos not in FANTASY_POSITIONS:
            continue
        rows.append(
            {
                "rank": i,
                "player_name": full_name,
                "position": pos,
                "team": str(p.get("proTeamId", "")),
                "external_rank": i,
            }
        )
    return rows[:limit]


def _fetch_live(
    source: str,
    season: int = 2026,
    scoring: str = "half_ppr",
    limit: int = 300,
) -> Optional[List[Dict[str, Any]]]:
    """Fetch rankings from the live external source.

    Returns a list of ranking dicts on success, or None on any failure
    (transport error, HTTP 4xx/5xx, parse error). Never raises.
    """
    try:
        if source == "sleeper":
            resp = requests.get(
                SLEEPER_PLAYERS_URL,
                timeout=REQUEST_TIMEOUT,
                headers=_HEADERS,
            )
            resp.raise_for_status()
            return _parse_sleeper_payload(resp.json(), limit=limit)

        if source == "fantasypros":
            scoring_type = _FP_SCORING_MAP.get(scoring, "half-ppr")
            url = FANTASYPROS_ECR_URL.format(season=season, scoring_type=scoring_type)
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            return _parse_fantasypros_payload(resp.json(), limit=limit)

        if source == "espn":
            url = ESPN_API_URL.format(season=season)
            headers = {
                **_HEADERS,
                "x-fantasy-filter": json.dumps(
                    {
                        "players": {
                            "sortPercOwned": {
                                "sortAsc": False,
                                "sortPriority": 1,
                            },
                            "limit": limit,
                            "offset": 0,
                            "filterSlotIds": {"value": [0, 2, 4, 6, 23]},
                        }
                    }
                ),
            }
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
            resp.raise_for_status()
            return _parse_espn_payload(resp.json(), limit=limit)
    except Exception as exc:  # noqa: BLE001 — intentionally broad; never raise
        logger.warning("Live fetch failed for %s: %s", source, exc)
        return None

    return None


# ---------------------------------------------------------------------------
# Consensus fallback (hardcoded)
# ---------------------------------------------------------------------------
def _consensus_as_rankings() -> List[Dict[str, Any]]:
    """Convert the hardcoded CONSENSUS_TOP_50 list to ranking dicts."""
    rows: List[Dict[str, Any]] = []
    for rank, name, pos, team in sorted(CONSENSUS_TOP_50, key=lambda t: t[0]):
        rows.append(
            {
                "rank": rank,
                "player_name": name,
                "position": pos,
                "team": team,
                "external_rank": rank,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Source resolver (live -> cache -> empty) with staleness metadata
# ---------------------------------------------------------------------------
def _resolve_source(
    source: str,
    season: int = 2026,
    scoring: str = "half_ppr",
    limit: int = 300,
) -> Tuple[List[Dict[str, Any]], bool, Optional[float], str]:
    """Resolve rankings for one source using the cache-first fallback chain.

    Returns ``(players, stale, cache_age_hours, last_updated_iso)``.

    - ``stale=False, cache_age_hours=None`` when live fetch succeeded.
    - ``stale=True, cache_age_hours>=0`` when serving from cache.
    - ``stale=True, cache_age_hours=None, players=[]`` when neither live nor
      cache worked. No exception is raised.
    """
    now = datetime.now(timezone.utc)

    # Always try live first — short-circuiting on a fresh cache would hide
    # external degradations from the advisor. ``_fetch_live`` returns None on
    # any failure (never raises).
    live = _fetch_live(source, season=season, scoring=scoring, limit=limit)
    if live:
        _save_cache(source, live)
        return (live[:limit], False, None, now.isoformat())

    cached = _load_cache(source)
    if cached is not None and cached[0]:
        players, fetched_at = cached
        age_seconds = max(0.0, (now - fetched_at).total_seconds())
        age_hours = round(age_seconds / 3600.0, 2)
        logger.warning("Serving stale cache for %s (age=%.2fh)", source, age_hours)
        return (list(players)[:limit], True, age_hours, fetched_at.isoformat())

    logger.warning(
        "No live data and no cache for %s — returning empty envelope", source
    )
    return ([], True, None, now.isoformat())


def _resolve_consensus(
    season: int, scoring: str, limit: int
) -> Tuple[List[Dict[str, Any]], bool, Optional[float], str]:
    """Merge Sleeper + FantasyPros + ESPN into an averaged-rank list.

    Sources that fail to yield data are skipped. ``stale`` is True when any of
    the three underlying sources was served from cache; ``cache_age_hours``
    reflects the oldest cache used.
    """
    now = datetime.now(timezone.utc)

    per_source_data: Dict[str, List[Dict[str, Any]]] = {}
    any_stale = False
    max_age_hours: Optional[float] = None
    newest_last_updated: Optional[str] = None

    for sub in ("sleeper", "fantasypros", "espn"):
        players, stale, age_hours, last_updated = _resolve_source(
            sub, season=season, scoring=scoring, limit=limit
        )
        if not players:
            continue
        per_source_data[sub] = players
        if stale:
            any_stale = True
            if age_hours is not None:
                max_age_hours = (
                    age_hours
                    if max_age_hours is None
                    else max(max_age_hours, age_hours)
                )
        if newest_last_updated is None or last_updated > newest_last_updated:
            newest_last_updated = last_updated

    if not per_source_data:
        logger.warning(
            "All consensus sub-sources empty; "
            "falling back to hardcoded CONSENSUS_TOP_50"
        )
        return (_consensus_as_rankings()[:limit], True, None, now.isoformat())

    merged: Dict[str, Dict[str, Any]] = {}
    for _sub_source, rows in per_source_data.items():
        for r in rows:
            key = _normalize_name(str(r.get("player_name", "")))
            if not key:
                continue
            entry = merged.setdefault(
                key,
                {
                    "player_name": r.get("player_name", ""),
                    "position": r.get("position", ""),
                    "team": r.get("team", ""),
                    "_ranks": [],
                },
            )
            entry["_ranks"].append(float(r.get("external_rank", r.get("rank", 0))))
            if not entry.get("team") and r.get("team"):
                entry["team"] = r["team"]
            if not entry.get("position") and r.get("position"):
                entry["position"] = r["position"]

    consensus_rows: List[Dict[str, Any]] = []
    for entry in merged.values():
        ranks = entry.pop("_ranks")
        if not ranks:
            continue
        avg_rank = sum(ranks) / len(ranks)
        entry["external_rank"] = round(avg_rank, 2)
        entry["rank"] = avg_rank
        consensus_rows.append(entry)

    consensus_rows.sort(key=lambda r: r["external_rank"])
    for i, row in enumerate(consensus_rows[:limit], 1):
        row["rank"] = i

    return (
        consensus_rows[:limit],
        any_stale,
        max_age_hours,
        newest_last_updated or now.isoformat(),
    )


# ---------------------------------------------------------------------------
# Public getters (preserve the pre-existing signatures used by the router)
# ---------------------------------------------------------------------------
def get_sleeper_rankings(limit: int = 200) -> List[Dict[str, Any]]:
    """Back-compat wrapper — returns players only (drops staleness metadata)."""
    players, _, _, _ = _resolve_source("sleeper", limit=limit)
    return players[:limit]


def get_fantasypros_rankings(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 200
) -> List[Dict[str, Any]]:
    """Back-compat wrapper for FantasyPros rankings."""
    players, _, _, _ = _resolve_source(
        "fantasypros", season=season, scoring=scoring, limit=limit
    )
    return players[:limit]


def get_espn_rankings(season: int = 2026, limit: int = 200) -> List[Dict[str, Any]]:
    """Back-compat wrapper for ESPN rankings."""
    players, _, _, _ = _resolve_source("espn", season=season, limit=limit)
    return players[:limit]


def get_external_rankings(
    source: str = "sleeper",
    scoring: str = "half_ppr",
    position: Optional[str] = None,
    limit: int = 50,
    season: int = 2026,
) -> List[Dict[str, Any]]:
    """Fetch external rankings from the specified source (players-only view).

    This is the legacy signature used by ``/api/rankings/external``. Staleness
    information is surfaced only via :func:`compare_rankings`.
    """
    if source not in VALID_SOURCES:
        source = "sleeper"

    internal_limit = max(limit * 3, 200)
    if source == "consensus":
        data, _, _, _ = _resolve_consensus(
            season=season, scoring=scoring, limit=internal_limit
        )
    else:
        data, _, _, _ = _resolve_source(
            source, season=season, scoring=scoring, limit=internal_limit
        )

    if position:
        pos_upper = position.upper()
        data = [r for r in data if str(r.get("position", "")).upper() == pos_upper]

    for i, row in enumerate(data[:limit], 1):
        row["rank"] = i

    return data[:limit]


# ---------------------------------------------------------------------------
# Projection loader (reads our Gold data)
# ---------------------------------------------------------------------------
def _latest_parquet(directory: Path) -> Optional[Path]:
    """Return the most-recently modified Parquet file in *directory*."""
    parquets = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    return parquets[-1] if parquets else None


def _load_our_projections(
    season: int = 2026, scoring: str = "half_ppr"
) -> pd.DataFrame:
    """Load our preseason projections from Gold parquet.

    Tries week=0 first (preseason), then week=1.
    """
    for week in [0, 1]:
        week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
        if not week_dir.exists():
            continue
        parquet_path = _latest_parquet(week_dir)
        if parquet_path is None:
            continue
        df = pd.read_parquet(parquet_path)
        rename_map = {
            "recent_team": "team",
            "projected_season_points": "projected_points",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        if "projected_points" not in df.columns:
            continue
        df = df.sort_values("projected_points", ascending=False).reset_index(drop=True)
        df["our_rank"] = range(1, len(df) + 1)
        return df

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Comparison engine — always returns the full envelope (stale /
# cache_age_hours / last_updated). Never raises on external-source failure.
# ---------------------------------------------------------------------------
def compare_rankings(
    source: str = "sleeper",
    scoring: str = "half_ppr",
    position: Optional[str] = None,
    limit: int = 20,
    season: int = 2026,
) -> Dict[str, Any]:
    """Compare external rankings against our projections.

    Sign convention: ``rank_diff = external_rank - our_rank``.

    - Positive => external source ranks the player lower (higher number) than we do.
    - Negative => external source ranks the player higher than we do.
    - None iff ``our_rank`` is None (the player is not in our projections).

    Returns:
        A dict with keys: ``source``, ``scoring_format``, ``position_filter``,
        ``our_projections_available``, ``players``, ``stale``,
        ``cache_age_hours``, ``last_updated``, ``compared_at``.
    """
    if source not in VALID_SOURCES:
        source = "sleeper"

    internal_limit = max(limit * 3, 200)
    if source == "consensus":
        external, stale, cache_age_hours, last_updated = _resolve_consensus(
            season=season, scoring=scoring, limit=internal_limit
        )
    else:
        external, stale, cache_age_hours, last_updated = _resolve_source(
            source, season=season, scoring=scoring, limit=internal_limit
        )

    if position:
        pos_upper = position.upper()
        external = [
            r for r in external if str(r.get("position", "")).upper() == pos_upper
        ]

    compared_at = datetime.now(timezone.utc).isoformat()

    if not external:
        return {
            "source": source,
            "scoring_format": scoring,
            "position_filter": position,
            "our_projections_available": False,
            "players": [],
            "stale": stale,
            "cache_age_hours": cache_age_hours,
            "last_updated": last_updated,
            "compared_at": compared_at,
        }

    our_df = _load_our_projections(season=season, scoring=scoring)

    if our_df.empty:
        players: List[Dict[str, Any]] = []
        for i, r in enumerate(external[:limit], 1):
            players.append(
                {
                    "rank": i,
                    "player_name": r.get("player_name", ""),
                    "position": r.get("position", ""),
                    "team": r.get("team", ""),
                    "external_rank": r.get("external_rank", i),
                    "our_rank": None,
                    "rank_diff": None,
                    "our_projected_points": None,
                }
            )
        return {
            "source": source,
            "scoring_format": scoring,
            "position_filter": position,
            "our_projections_available": False,
            "players": players,
            "stale": stale,
            "cache_age_hours": cache_age_hours,
            "last_updated": last_updated,
            "compared_at": compared_at,
        }

    our_lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in our_df.iterrows():
        name_key = _normalize_name(str(row.get("player_name", "")))
        if not name_key:
            continue
        our_lookup.setdefault(
            name_key,
            {
                "our_rank": int(row["our_rank"]),
                "projected_points": float(row.get("projected_points", 0) or 0),
                "position": str(row.get("position", "")),
                "team": str(row.get("team", "")),
            },
        )

    compared: List[Dict[str, Any]] = []
    for ext in external:
        ext_name_key = _normalize_name(str(ext.get("player_name", "")))
        match = our_lookup.get(ext_name_key)

        our_rank = match["our_rank"] if match else None
        our_pts = match["projected_points"] if match else None
        ext_rank = ext.get("external_rank", ext.get("rank"))
        rank_diff: Optional[float] = None
        if our_rank is not None and ext_rank is not None:
            rank_diff = float(ext_rank) - float(our_rank)

        compared.append(
            {
                "rank": ext.get("rank"),
                "player_name": ext.get("player_name", ""),
                "position": ext.get("position", ""),
                "team": ext.get("team") or (match["team"] if match else ""),
                "external_rank": ext_rank,
                "our_rank": our_rank,
                "rank_diff": rank_diff,
                "our_projected_points": round(our_pts, 1) if our_pts else None,
            }
        )

    compared.sort(
        key=lambda r: (
            float(r["external_rank"])
            if r.get("external_rank") is not None
            else float("inf")
        )
    )
    compared = compared[:limit]
    for i, row in enumerate(compared, 1):
        row["rank"] = i

    return {
        "source": source,
        "scoring_format": scoring,
        "position_filter": position,
        "our_projections_available": True,
        "players": compared,
        "stale": stale,
        "cache_age_hours": cache_age_hours,
        "last_updated": last_updated,
        "compared_at": compared_at,
    }
