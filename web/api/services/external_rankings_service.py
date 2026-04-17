"""
Service layer for fetching, caching, and comparing external fantasy rankings.

Supported sources:
  - Sleeper ADP (reliable, free API)
  - FantasyPros ECR (may be rate-limited or blocked)
  - ESPN Rankings (may be rate-limited or blocked)

Cache strategy: read from data/external/*.json first; fall back to live fetch.
Cached files are considered fresh for 24 hours.
"""

import json
import logging
import os
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

# User-Agent to avoid basic bot detection
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
# Hardcoded consensus fallback (from sanity_check_projections.py)
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
    """Normalize player name for fuzzy matching."""
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
# Cache helpers
# ---------------------------------------------------------------------------
def _cache_path(source: str) -> Path:
    """Return the cache file path for a given source."""
    return EXTERNAL_DIR / f"{source}_rankings.json"


def _cache_is_fresh(source: str) -> bool:
    """Return True if the cached file exists and is less than 24 hours old."""
    path = _cache_path(source)
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < CACHE_MAX_AGE_SECONDS


def _read_cache(source: str) -> Optional[List[Dict[str, Any]]]:
    """Read cached rankings, returning None if stale or missing."""
    if not _cache_is_fresh(source):
        return None
    try:
        with open(_cache_path(source), "r") as f:
            data = json.load(f)
        logger.info("Loaded %d cached rankings for %s", len(data), source)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read cache for %s: %s", source, exc)
        return None


def _write_cache(source: str, data: List[Dict[str, Any]]) -> None:
    """Write rankings data to cache file."""
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(source)
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Cached %d rankings for %s -> %s", len(data), source, path)
    except OSError as exc:
        logger.warning("Failed to write cache for %s: %s", source, exc)


# ---------------------------------------------------------------------------
# Sleeper rankings
# ---------------------------------------------------------------------------
def _fetch_sleeper_live(limit: int = 200) -> List[Dict[str, Any]]:
    """Fetch Sleeper player database and extract ADP-style rankings."""
    resp = requests.get(SLEEPER_PLAYERS_URL, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    players = resp.json()

    rows: List[Dict[str, Any]] = []
    for player_id, info in players.items():
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
                "team": info.get("team", ""),
                "external_rank": search_rank,
                "sleeper_id": player_id,
            }
        )

    rows.sort(key=lambda r: r["external_rank"])
    # Re-rank sequentially
    for i, row in enumerate(rows[:limit], 1):
        row["rank"] = i
    return rows[:limit]


def _fetch_sleeper_from_adp_csv() -> Optional[List[Dict[str, Any]]]:
    """Fall back to data/adp_latest.csv if it exists."""
    csv_path = DATA_DIR / "adp_latest.csv"
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path)
        rows: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "rank": int(r.get("adp_rank", 0)),
                    "player_name": str(r.get("player_name", "")),
                    "position": str(r.get("position", "")),
                    "team": str(r.get("team", "")),
                    "external_rank": int(r.get("adp_rank", 0)),
                    "sleeper_id": str(r.get("sleeper_id", "")),
                }
            )
        logger.info("Loaded %d players from adp_latest.csv fallback", len(rows))
        return rows
    except Exception as exc:
        logger.warning("Failed to read adp_latest.csv: %s", exc)
        return None


def get_sleeper_rankings(limit: int = 200) -> List[Dict[str, Any]]:
    """Get Sleeper rankings: cache -> live API -> adp_latest.csv fallback."""
    cached = _read_cache("sleeper")
    if cached is not None:
        return cached[:limit]

    try:
        data = _fetch_sleeper_live(limit=limit)
        if data:
            _write_cache("sleeper", data)
            return data
    except Exception as exc:
        logger.warning("Sleeper live fetch failed: %s", exc)

    # Fall back to ADP CSV
    csv_data = _fetch_sleeper_from_adp_csv()
    if csv_data:
        return csv_data[:limit]

    # Final fallback: consensus
    logger.warning("All Sleeper sources failed; using hardcoded consensus")
    return _consensus_as_rankings()[:limit]


# ---------------------------------------------------------------------------
# FantasyPros ECR
# ---------------------------------------------------------------------------
def _fetch_fantasypros_live(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 200
) -> List[Dict[str, Any]]:
    """Attempt to fetch FantasyPros consensus rankings via their public API."""
    scoring_type = _FP_SCORING_MAP.get(scoring, "half-ppr")
    url = FANTASYPROS_ECR_URL.format(season=season, scoring_type=scoring_type)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    data = resp.json()

    players_raw = data.get("players", [])
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
                "team": p.get("player_team_id", p.get("team", "")),
                "external_rank": int(p.get("rank_ecr", i)),
            }
        )
    return rows[:limit]


def get_fantasypros_rankings(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 200
) -> List[Dict[str, Any]]:
    """Get FantasyPros rankings: cache -> live API -> consensus fallback."""
    cached = _read_cache("fantasypros")
    if cached is not None:
        return cached[:limit]

    try:
        data = _fetch_fantasypros_live(season=season, scoring=scoring, limit=limit)
        if data:
            _write_cache("fantasypros", data)
            return data
    except Exception as exc:
        logger.warning("FantasyPros live fetch failed: %s", exc)

    logger.warning("FantasyPros unavailable; using hardcoded consensus")
    return _consensus_as_rankings()[:limit]


# ---------------------------------------------------------------------------
# ESPN Rankings
# ---------------------------------------------------------------------------
def _fetch_espn_live(season: int = 2026, limit: int = 200) -> List[Dict[str, Any]]:
    """Attempt to fetch ESPN fantasy rankings via their API."""
    url = ESPN_API_URL.format(season=season)
    headers = {**_HEADERS, "x-fantasy-filter": json.dumps({
        "players": {
            "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
            "limit": limit,
            "offset": 0,
            "filterSlotIds": {"value": [0, 2, 4, 6, 23]},  # QB, RB, WR, TE, K
        }
    })}
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    # ESPN slot ID -> position mapping
    slot_to_pos = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "K"}

    players_raw = data.get("players", [])
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

        # ESPN team ID -> abbreviation (simplified mapping)
        team = str(p.get("proTeamId", ""))

        rows.append(
            {
                "rank": i,
                "player_name": full_name,
                "position": pos,
                "team": team,
                "external_rank": i,
            }
        )
    return rows[:limit]


def get_espn_rankings(
    season: int = 2026, limit: int = 200
) -> List[Dict[str, Any]]:
    """Get ESPN rankings: cache -> live API -> consensus fallback."""
    cached = _read_cache("espn")
    if cached is not None:
        return cached[:limit]

    try:
        data = _fetch_espn_live(season=season, limit=limit)
        if data:
            _write_cache("espn", data)
            return data
    except Exception as exc:
        logger.warning("ESPN live fetch failed: %s", exc)

    logger.warning("ESPN unavailable; using hardcoded consensus")
    return _consensus_as_rankings()[:limit]


# ---------------------------------------------------------------------------
# Consensus fallback
# ---------------------------------------------------------------------------
def _consensus_as_rankings() -> List[Dict[str, Any]]:
    """Convert the hardcoded CONSENSUS_TOP_50 to ranking format."""
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
# Unified getter
# ---------------------------------------------------------------------------
def get_external_rankings(
    source: str = "sleeper",
    scoring: str = "half_ppr",
    position: Optional[str] = None,
    limit: int = 50,
    season: int = 2026,
) -> List[Dict[str, Any]]:
    """Fetch external rankings from the specified source.

    Args:
        source: One of sleeper, fantasypros, espn, consensus.
        scoring: Scoring format (ppr / half_ppr / standard).
        position: Optional position filter (QB / RB / WR / TE / K).
        limit: Maximum number of players to return.
        season: NFL season year.

    Returns:
        List of ranking dicts with rank, player_name, position, team, external_rank.
    """
    if source == "sleeper":
        data = get_sleeper_rankings(limit=max(limit * 3, 200))
    elif source == "fantasypros":
        data = get_fantasypros_rankings(season=season, scoring=scoring, limit=max(limit * 3, 200))
    elif source == "espn":
        data = get_espn_rankings(season=season, limit=max(limit * 3, 200))
    elif source == "consensus":
        data = _consensus_as_rankings()
    else:
        data = get_sleeper_rankings(limit=max(limit * 3, 200))

    # Position filter
    if position:
        pos_upper = position.upper()
        data = [r for r in data if r.get("position", "").upper() == pos_upper]

    # Re-rank after filtering
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
# Comparison engine
# ---------------------------------------------------------------------------
def compare_rankings(
    source: str = "sleeper",
    scoring: str = "half_ppr",
    position: Optional[str] = None,
    limit: int = 20,
    season: int = 2026,
) -> Dict[str, Any]:
    """Compare external rankings against our projections.

    Args:
        source: External source (sleeper / fantasypros / espn / consensus).
        scoring: Scoring format.
        position: Optional position filter.
        limit: Max players to compare.
        season: NFL season year.

    Returns:
        Dict with source, players (list of comparison dicts), and metadata.
    """
    external = get_external_rankings(
        source=source, scoring=scoring, position=position,
        limit=limit * 2, season=season,
    )
    our_df = _load_our_projections(season=season, scoring=scoring)

    if our_df.empty:
        # No projections available -- return external only
        return {
            "source": source,
            "scoring_format": scoring,
            "position_filter": position,
            "our_projections_available": False,
            "players": [
                {
                    "rank": r["rank"],
                    "player_name": r["player_name"],
                    "position": r["position"],
                    "team": r.get("team", ""),
                    "external_rank": r["external_rank"],
                    "our_rank": None,
                    "rank_diff": None,
                    "our_projected_points": None,
                }
                for r in external[:limit]
            ],
            "compared_at": datetime.now(timezone.utc).isoformat(),
        }

    # Build lookup for our projections by normalized name
    our_lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in our_df.iterrows():
        name_key = _normalize_name(str(row.get("player_name", "")))
        our_lookup[name_key] = {
            "our_rank": int(row["our_rank"]),
            "projected_points": float(row.get("projected_points", 0)),
            "position": str(row.get("position", "")),
            "team": str(row.get("team", "")),
        }

    compared: List[Dict[str, Any]] = []
    for ext in external:
        ext_name_key = _normalize_name(ext["player_name"])
        match = our_lookup.get(ext_name_key)

        our_rank = match["our_rank"] if match else None
        our_pts = match["projected_points"] if match else None
        rank_diff = (ext["external_rank"] - our_rank) if (our_rank is not None) else None

        compared.append(
            {
                "rank": ext["rank"],
                "player_name": ext["player_name"],
                "position": ext["position"],
                "team": ext.get("team", match["team"] if match else ""),
                "external_rank": ext["external_rank"],
                "our_rank": our_rank,
                "rank_diff": rank_diff,
                "our_projected_points": round(our_pts, 1) if our_pts else None,
            }
        )

    # Sort by external rank, limit
    compared.sort(key=lambda r: r["external_rank"])
    compared = compared[:limit]
    for i, row in enumerate(compared, 1):
        row["rank"] = i

    return {
        "source": source,
        "scoring_format": scoring,
        "position_filter": position,
        "our_projections_available": True,
        "players": compared,
        "compared_at": datetime.now(timezone.utc).isoformat(),
    }
