"""Map Sleeper player_ids onto our projection player keys (Phase 85, SLPR-03).

Sleeper identifies players by an opaque ``player_id``; our projections key on
``player_name`` + ``position`` + ``team``. The Sleeper ``/v1/players/nfl``
registry is the bridge, but it is ~5MB, so it is cached on disk and only
refetched when stale.

Public API
----------
``normalize_name(name) -> str``
``load_sleeper_players(force_refresh=False, max_age_days=7) -> dict``
``build_player_index(registry) -> dict``
``map_picks_to_projections(picks, projections_df) -> (matched, unmatched)``
``mapping_coverage(matched, unmatched, positions=...) -> float``

Fail-open: a registry fetch failure falls back to any existing cache, and only
returns ``{}`` when neither network nor cache is available. Unmatched picks are
always returned (never silently dropped) so callers can surface them.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import pandas as pd

from src import sleeper_http
from src.config import SENTIMENT_CONFIG
from src.sleeper_draft import PickEvent

logger = logging.getLogger(__name__)

_CACHE_PATH: str = os.path.join("data", "bronze", "players", "sleeper_players.json")
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, and drop generational suffixes.

    ``"Marvin Harrison Jr."`` and ``"marvin harrison"`` both normalize to
    ``"marvin harrison"`` so registry and projection names align.
    """
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9\s]", "", str(name).lower())
    tokens = [t for t in cleaned.split() if t and t not in _SUFFIXES]
    return " ".join(tokens)


def load_sleeper_players(
    force_refresh: bool = False,
    max_age_days: int = 7,
    cache_path: str = _CACHE_PATH,
) -> Dict[str, Any]:
    """Return the Sleeper player registry, cached on disk.

    On a fresh cache (younger than ``max_age_days``) and not ``force_refresh``,
    reads the cache. Otherwise GETs ``/v1/players/nfl`` and rewrites the cache.
    If the fetch fails, falls back to an existing cache; returns ``{}`` only when
    neither network nor cache yields data.
    """
    cache_fresh = False
    if os.path.exists(cache_path):
        age_s = time.time() - os.path.getmtime(cache_path)
        cache_fresh = age_s < max_age_days * 86400

    if cache_fresh and not force_refresh:
        cached = _read_cache(cache_path)
        if cached:
            return cached

    registry = sleeper_http.fetch_sleeper_json(SENTIMENT_CONFIG["sleeper_players_url"])
    if isinstance(registry, dict) and registry:
        _write_cache(cache_path, registry)
        return registry

    # Fetch failed — fall back to any existing cache (even if stale).
    cached = _read_cache(cache_path)
    if cached:
        logger.warning(
            "Sleeper players fetch failed — using stale cache at %s", cache_path
        )
        return cached

    logger.warning("Sleeper players unavailable (no network, no cache)")
    return {}


def _read_cache(cache_path: str) -> Dict[str, Any]:
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Sleeper players cache %s: %s", cache_path, exc)
        return {}


def _write_cache(cache_path: str, registry: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(registry, fh)
    except OSError as exc:
        logger.warning("Could not write Sleeper players cache %s: %s", cache_path, exc)


def build_player_index(registry: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Normalize the raw registry to ``sleeper_player_id -> identity`` records.

    Each value is ``{full_name, position, team, normalized_name}``.
    """
    index: Dict[str, Dict[str, str]] = {}
    for pid, entry in (registry or {}).items():
        if not isinstance(entry, dict):
            continue
        full = str(entry.get("full_name") or "").strip()
        if not full:
            first = str(entry.get("first_name") or "")
            last = str(entry.get("last_name") or "")
            full = f"{first} {last}".strip()
        index[str(pid)] = {
            "full_name": full,
            "position": str(entry.get("position") or "").upper(),
            "team": str(entry.get("team") or "").upper(),
            "normalized_name": normalize_name(full),
        }
    return index


def _pick_identity(pick: PickEvent, index: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """Resolve a pick's (normalized_name, position, team), preferring the
    registry record and falling back to the pick's own embedded metadata."""
    rec = index.get(pick.sleeper_player_id) if index else None
    if rec and rec.get("normalized_name"):
        return rec
    return {
        "full_name": pick.full_name,
        "position": pick.position,
        "team": pick.team,
        "normalized_name": normalize_name(pick.full_name),
    }


def map_picks_to_projections(
    picks: Iterable[PickEvent],
    projections_df: pd.DataFrame,
    player_index: Dict[str, Dict[str, str]] | None = None,
) -> Tuple[List[Dict[str, Any]], List[PickEvent]]:
    """Match each pick to a projection row.

    Match key: ``normalized_name`` + ``position``, with ``team`` as a tiebreaker
    when multiple projection rows share name+position. DST/K and obscure rookies
    that have no projection row are returned in the ``unmatched`` list — never
    silently dropped.

    Returns:
        ``(matched, unmatched)`` where ``matched`` rows include the projection's
        ``player_id`` / ``player_name`` plus the originating ``pick_no``.
    """
    index = player_index if player_index is not None else {}
    matched: List[Dict[str, Any]] = []
    unmatched: List[PickEvent] = []

    if projections_df is None or projections_df.empty:
        return matched, list(picks)

    proj = projections_df.copy()
    name_col = "player_name" if "player_name" in proj.columns else None
    if name_col is None:
        return matched, list(picks)
    proj["_norm"] = proj[name_col].map(normalize_name)
    proj["_pos"] = (
        proj.get("position", pd.Series([""] * len(proj))).astype(str).str.upper()
    )
    proj["_team"] = (
        proj.get("team", pd.Series([""] * len(proj))).astype(str).str.upper()
    )

    for pick in picks:
        identity = _pick_identity(pick, index)
        norm = identity["normalized_name"]
        pos = identity["position"]
        cand = proj[(proj["_norm"] == norm) & (proj["_pos"] == pos)]
        if len(cand) > 1 and identity["team"]:
            team_cand = cand[cand["_team"] == identity["team"]]
            if not team_cand.empty:
                cand = team_cand
        if cand.empty:
            unmatched.append(pick)
            continue
        row = cand.iloc[0].to_dict()
        row["pick_no"] = pick.pick_no
        row["sleeper_player_id"] = pick.sleeper_player_id
        matched.append(row)

    if unmatched:
        by_pos: Dict[str, int] = {}
        for p in unmatched:
            by_pos[p.position or "?"] = by_pos.get(p.position or "?", 0) + 1
        logger.warning(
            "map_picks_to_projections: %d/%d picks matched; unmatched by position: %s",
            len(matched),
            len(matched) + len(unmatched),
            by_pos,
        )
    return matched, unmatched


def mapping_coverage(
    matched: Sequence[Dict[str, Any]],
    unmatched: Sequence[PickEvent],
    positions: Sequence[str] = _SKILL_POSITIONS,
) -> float:
    """Fraction of picks at ``positions`` that matched a projection (0.0–1.0).

    Returns 1.0 when there are no picks at the requested positions (vacuously
    complete).
    """
    wanted = {p.upper() for p in positions}
    matched_n = sum(
        1
        for m in matched
        if str(m.get("_pos", m.get("position", ""))).upper() in wanted
    )
    unmatched_n = sum(1 for p in unmatched if (p.position or "").upper() in wanted)
    total = matched_n + unmatched_n
    if total == 0:
        return 1.0
    return matched_n / total
