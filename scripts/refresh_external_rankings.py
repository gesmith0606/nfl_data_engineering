#!/usr/bin/env python3
"""
Refresh external fantasy rankings from Sleeper, FantasyPros, ESPN,
Draft Sharks, and FTN (Jeff Ratcliffe).

Fetches rankings from all sources and caches them as JSON files in
data/external/ for the rankings API to consume. Designed to be run daily
alongside the sentiment pipeline.

Note on FTN: Jeff Ratcliffe's board is served via the FantasyPros partners
API expert filter and is empty until he submits ranks for the season
(typically Jul-Aug) — an empty result is normal in the early offseason.

Usage:
    python scripts/refresh_external_rankings.py
    python scripts/refresh_external_rankings.py --season 2026
    python scripts/refresh_external_rankings.py --source sleeper
    python scripts/refresh_external_rankings.py --source draftsharks
    python scripts/refresh_external_rankings.py --source all --limit 300
"""

import argparse
import gzip
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"
ARCHIVE_DIR = EXTERNAL_DIR / "archive"

REQUEST_TIMEOUT = 60
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_FP_SCORING_MAP = {
    "ppr": "ppr",
    "half_ppr": "half-ppr",
    "standard": "standard",
}

# Draft Sharks publishes ppr / half-ppr / superflex boards only — standard
# leagues are served the half-ppr board (closest available).
_DS_SCORING_MAP = {
    "ppr": "ppr",
    "half_ppr": "half-ppr",
    "standard": "half-ppr",
}

# FantasyPros partners API scoring codes (differ from the public v2 API).
_FP_PARTNERS_SCORING_MAP = {
    "ppr": "PPR",
    "half_ppr": "HALF",
    "standard": "STD",
}

# ---------------------------------------------------------------------------
# FantasyPros weekly per-position rankings page slugs (public, no auth).
#
# These are DIFFERENT pages from fetch_fantasypros() above: that function
# always calls the partners consensus-rankings.php with week=0&type=draft
# -- the perpetual overall REDRAFT/draft board. These pages
# (fantasypros.com/nfl/rankings/{slug}.php) are FantasyPros' weekly
# per-position boards -- the same product WR_ECR_ORDINAL_GATE.md's
# historical DynastyProcess archive scraped, re-ranked every week from that
# week's expert consensus. Each page embeds a `var ecrData = {...}` JS
# object carrying the true per-position rank (`pos_rank`, e.g. "WR1"),
# dispersion stats (`rank_ave`/`rank_std`/`rank_min`/`rank_max`), and a
# numeric FantasyPros player id -- richer than the draft-board capture,
# which has none of that (see ECR_ANCHOR_FORWARD_GATE.md #0.2/#0.4).
# QB has no scoring split (passing/rushing points don't depend on
# receptions) -- qb.php is used for every scoring value.
_FP_WEEKLY_PAGE_SLUGS = {
    ("QB", "ppr"): "qb",
    ("QB", "half_ppr"): "qb",
    ("QB", "standard"): "qb",
    ("RB", "ppr"): "ppr-rb",
    ("RB", "half_ppr"): "half-point-ppr-rb",
    ("RB", "standard"): "rb",
    ("WR", "ppr"): "ppr-wr",
    ("WR", "half_ppr"): "half-point-ppr-wr",
    ("WR", "standard"): "wr",
    ("TE", "ppr"): "ppr-te",
    ("TE", "half_ppr"): "half-point-ppr-te",
    ("TE", "standard"): "te",
}
_FP_WEEKLY_POSITIONS = ("QB", "RB", "WR", "TE")

# Jeff Ratcliffe (FTN) — #1 on FantasyPros' 2022-2024 multi-year draft-accuracy
# leaderboard. ID verified against partners expert-groups.php (year=2025).
FTN_RATCLIFFE_EXPERT_ID = 125

# 2025 FantasyPros draft-accuracy podium still submitting draft boards in
# 2026: Seth Miller (Crossroads FF, #1), Guilherme Gianni (Fantasy
# Futebolista, #2), Marc Shannep (Fantasy Knockout, #5). IDs verified
# against partners expert-groups.php (year=2026, type=draft) on 2026-08-27.
SHARPS_EXPERT_IDS = "2743:4179:1080"


# ---------------------------------------------------------------------------
# Sleeper
# ---------------------------------------------------------------------------
def fetch_sleeper(limit: int = 300) -> List[Dict[str, Any]]:
    """Fetch Sleeper player database and extract ADP-style rankings."""
    logger.info("Fetching Sleeper player database...")
    resp = requests.get(
        "https://api.sleeper.app/v1/players/nfl",
        timeout=REQUEST_TIMEOUT,
        headers=_HEADERS,
    )
    resp.raise_for_status()
    players = resp.json()
    logger.info("Received %d player entries from Sleeper", len(players))

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
    for i, row in enumerate(rows[:limit], 1):
        row["rank"] = i
    return rows[:limit]


# ---------------------------------------------------------------------------
# FantasyPros (partners API primary; public v2 legacy fallback)
# ---------------------------------------------------------------------------
def _parse_fp_partners_players(
    data: Dict[str, Any], limit: int
) -> List[Dict[str, Any]]:
    """Shape a FP partners consensus-rankings.php response into ranking rows."""
    players_raw = data.get("players", []) or []
    rows: List[Dict[str, Any]] = []
    for p in players_raw:
        pos = str(p.get("player_position_id", p.get("position", "")) or "").upper()
        if pos not in FANTASY_POSITIONS:
            continue
        name = p.get("player_name", p.get("name", "")) or ""
        if not name:
            continue
        try:
            ext_rank = int(p.get("rank_ecr"))
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "player_name": name,
                "position": pos,
                "team": p.get("player_team_id", p.get("team", "")) or "",
                "external_rank": ext_rank,
            }
        )
    rows.sort(key=lambda r: r["external_rank"])
    rows = rows[:limit]
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def fetch_fantasypros(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 300
) -> List[Dict[str, Any]]:
    """Fetch FantasyPros ECR consensus rankings.

    Primary: the auth-free partners API. Legacy fallback: the public v2 API
    (requires an auth token since ~2026-06, kept in case partners goes away).
    """
    partners_scoring = _FP_PARTNERS_SCORING_MAP.get(scoring, "HALF")
    partners_url = (
        "https://partners.fantasypros.com/api/v1/consensus-rankings.php"
        f"?sport=NFL&year={season}&week=0&position=ALL&type=draft"
        f"&scoring={partners_scoring}"
    )
    logger.info("Fetching FantasyPros ECR (partners): %s", partners_url)
    try:
        resp = requests.get(partners_url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
        resp.raise_for_status()
        rows = _parse_fp_partners_players(resp.json(), limit=limit)
        if rows:
            logger.info("Parsed %d FantasyPros rankings (partners)", len(rows))
            return rows
        logger.warning("FP partners returned no players; trying public v2")
    except requests.RequestException as exc:
        logger.warning("FP partners fetch failed (%s); trying public v2", exc)

    scoring_type = _FP_SCORING_MAP.get(scoring, "half-ppr")
    url = (
        f"https://api.fantasypros.com/public/v2/json/nfl/{season}"
        f"/consensus-rankings.php?type={scoring_type}"
    )
    logger.info("Fetching FantasyPros ECR (public v2): %s", url)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    data = resp.json()

    players_raw = data.get("players", [])
    rows = []
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
    logger.info("Parsed %d FantasyPros rankings (public v2)", len(rows))
    return rows[:limit]


# ---------------------------------------------------------------------------
# FantasyPros weekly per-position ECR (true weekly rankings, not the draft board)
# ---------------------------------------------------------------------------
def _extract_ecr_data_json(html: str) -> Optional[Dict[str, Any]]:
    """Pull the `var ecrData = {...};` JS object literal out of a
    fantasypros.com/nfl/rankings/*.php page and parse it as JSON.

    Uses a brace-balance scan (respecting quoted strings) rather than a
    regex terminated on the first ``};`` -- safer against player note text
    that might itself contain that substring. Returns None if the marker
    isn't found or the extracted text isn't valid JSON (page format changed,
    or FantasyPros served an error page) -- callers treat that as a normal
    fail-open miss, not an exception.
    """
    marker = "var ecrData = "
    start = html.find(marker)
    if start == -1:
        return None
    start += len(marker)
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(html)):
        ch = html[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _parse_fp_weekly_page(
    data: Dict[str, Any], position: str, limit: int
) -> List[Dict[str, Any]]:
    """Shape one weekly-position page's `ecrData` payload into ranking rows.

    Carries FantasyPros' own per-position rank/dispersion/id fields through
    verbatim (``pos_rank``, ``ecr``, ``sd``, ``best``, ``worst``,
    ``fantasypros_id``) -- these map directly onto the historical Silver
    schema's columns of the same meaning, unlike the draft-board capture
    which has to leave them null (see ``bridge_fp_ecr_live.py``).
    """
    players_raw = data.get("players", []) or []
    week_raw = data.get("week")
    try:
        week = int(week_raw) if week_raw is not None else None
    except (TypeError, ValueError):
        week = None

    rows: List[Dict[str, Any]] = []
    for p in players_raw[:limit]:
        name = p.get("player_name") or ""
        if not name:
            continue
        pos_rank_raw = str(p.get("pos_rank") or "")
        digits = re.sub(r"[^0-9]", "", pos_rank_raw)
        pos_rank = int(digits) if digits else None
        try:
            rank_ecr = int(p.get("rank_ecr"))
        except (TypeError, ValueError):
            rank_ecr = None
        rows.append(
            {
                "player_name": name,
                "position": position,
                "team": p.get("player_team_id", "") or "",
                "fantasypros_id": p.get("player_id"),
                "external_rank": rank_ecr,
                "pos_rank": pos_rank,
                "ecr": p.get("rank_ave"),
                "sd": p.get("rank_std"),
                "best": p.get("rank_min"),
                "worst": p.get("rank_max"),
                "week": week,
                "ranking_type": data.get("ranking_type_name"),
            }
        )
    # Fallback: a handful of rows with an unparsable pos_rank (page format
    # drift) shouldn't sink the whole position -- derive from rank_ecr order.
    if any(r["pos_rank"] is None for r in rows):
        rows.sort(key=lambda r: (r["external_rank"] is None, r["external_rank"] or 0))
        for i, r in enumerate(rows, 1):
            if r["pos_rank"] is None:
                r["pos_rank"] = i
    rows.sort(key=lambda r: r["pos_rank"])
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def fetch_fantasypros_weekly(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 300
) -> List[Dict[str, Any]]:
    """Fetch FantasyPros' TRUE weekly per-position ECR (QB/RB/WR/TE).

    Unlike ``fetch_fantasypros`` (the perpetual overall draft board), this
    hits the public weekly-position rankings pages directly -- the same
    product the historical WR_ECR_ORDINAL_GATE.md archive was built from.
    Preseason/off-cadence behavior: FantasyPros may serve a provisional
    "week 1" board (``ranking_type_name == "weekly"``) before kickoff, or
    (rarely) a page with no ``ecrData`` at all if the format changes -- both
    are handled by skipping that position and logging, never raising.
    Fail-open per position: one position 404ing/erroring doesn't stop the
    other three, and an all-positions failure returns ``[]`` (the existing
    ``main()`` loop already treats an empty return as a normal "no data").

    Returns a flat list across QB/RB/WR/TE, each row also carrying its own
    ``week`` and ``ranking_type`` (FantasyPros' self-reported values, not
    derived) so downstream consumers can tell a true "weekly" capture from
    a preseason "draft"-labeled fallback if FantasyPros ever serves one.
    """
    rows: List[Dict[str, Any]] = []
    for position in _FP_WEEKLY_POSITIONS:
        slug = _FP_WEEKLY_PAGE_SLUGS.get((position, scoring))
        if slug is None:
            continue
        url = f"https://www.fantasypros.com/nfl/rankings/{slug}.php"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "FantasyPros weekly %s (%s) fetch failed (%s) -- skipping this position",
                position,
                scoring,
                exc,
            )
            continue
        data = _extract_ecr_data_json(resp.text)
        if not data:
            logger.warning(
                "FantasyPros weekly %s (%s): no ecrData found on %s (page format may "
                "have changed, or the page 404'd/served an error body) -- skipping",
                position,
                scoring,
                url,
            )
            continue
        page_rows = _parse_fp_weekly_page(data, position, limit)
        logger.info(
            "FantasyPros weekly %s (%s): %d players, week=%s, type=%s, experts=%s",
            position,
            scoring,
            len(page_rows),
            data.get("week"),
            data.get("ranking_type_name"),
            data.get("total_experts"),
        )
        rows.extend(page_rows)
    return rows


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------
def fetch_espn(season: int = 2026, limit: int = 300) -> List[Dict[str, Any]]:
    """Fetch ESPN fantasy rankings via their API."""
    url = (
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
        "/segments/0/leaguedefaults/3?view=kona_player_info"
    )
    headers = {
        **_HEADERS,
        "x-fantasy-filter": json.dumps(
            {
                "players": {
                    "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
                    "limit": limit,
                    "offset": 0,
                    "filterSlotIds": {"value": [0, 2, 4, 6, 23]},
                }
            }
        ),
    }
    logger.info("Fetching ESPN rankings for season %d...", season)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
    resp.raise_for_status()
    data = resp.json()

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
        if not pos:
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
    logger.info("Parsed %d ESPN rankings", len(rows))
    return rows[:limit]


# ---------------------------------------------------------------------------
# Draft Sharks
# ---------------------------------------------------------------------------
def fetch_draftsharks(
    scoring: str = "half_ppr", limit: int = 300
) -> List[Dict[str, Any]]:
    """Fetch the Draft Sharks rankings board (free HTML endpoint)."""
    from bs4 import BeautifulSoup

    slug = _DS_SCORING_MAP.get(scoring, "half-ppr")
    url = (
        "https://www.draftsharks.com/rankings/load-rows"
        f"?offset=0&limit={limit}&pprSuperflexSlug={slug}"
    )
    logger.info("Fetching Draft Sharks board: %s", url)
    resp = requests.get(
        url, timeout=REQUEST_TIMEOUT, headers={**_HEADERS, "Accept": "text/html"}
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows: List[Dict[str, Any]] = []
    for tbody in soup.select("tbody[data-player-row]"):
        name = str(tbody.get("data-player-name") or "").strip()
        pos = str(tbody.get("data-fantasy-position") or "").strip().upper()
        if not name or pos not in FANTASY_POSITIONS:
            continue
        team_el = tbody.select_one(".player-details-group__team-name")
        team = team_el.get_text(strip=True) if team_el else ""
        rank_el = tbody.select_one(".rank-index span")
        ds_rank: Optional[int] = None
        if rank_el:
            try:
                ds_rank = int(rank_el.get_text(strip=True))
            except ValueError:
                ds_rank = None
        rows.append(
            {
                "player_name": name,
                "position": pos,
                "team": team,
                "external_rank": ds_rank,
            }
        )

    # Rows with an unparsable rank sink below every parsed rank — guessing
    # their board position from list order can collide with a real rank,
    # because non-fantasy rows (DEF) were filtered out above.
    unranked_offset = max(
        (r["external_rank"] for r in rows if r["external_rank"] is not None),
        default=0,
    )
    for row in rows:
        if row["external_rank"] is None:
            unranked_offset += 1
            row["external_rank"] = unranked_offset
    rows.sort(key=lambda r: r["external_rank"])
    rows = rows[:limit]
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    logger.info("Parsed %d Draft Sharks rankings", len(rows))
    return rows


# ---------------------------------------------------------------------------
# FTN (Jeff Ratcliffe) via FantasyPros partners API
# ---------------------------------------------------------------------------
def _in_season_week(season: int) -> Optional[int]:
    """Current NFL week if today falls inside a real game week of ``season``.

    Mirrors the guard in the web service's ``_fetch_ftn_weekly``: only a
    schedule-window match for the requested season counts — the
    out-of-season fallback would otherwise point at last season's week 18.
    Fail-open (returns None) if the web service stack is unimportable in
    this environment.
    """
    try:
        repo_root = os.path.join(os.path.dirname(__file__), "..")
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from web.api.services.team_roster_service import get_current_week

        cur = get_current_week()
        if cur.source == "schedule" and cur.season == season:
            return int(cur.week)
    except Exception as exc:  # noqa: BLE001 — cache refresh must fail open
        logger.warning("Could not resolve in-season week: %s", exc)
    return None


def fetch_ftn(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 300
) -> List[Dict[str, Any]]:
    """Fetch Jeff Ratcliffe's board via the FP partners expert filter.

    His 2026 DRAFT board is subscriber-only at ftnfantasy.com, so the draft
    fetch stays empty; in-season, this falls back to his FP weekly ranks
    (mirroring the web service) so the committed cache — the website's tier-2
    fallback when a live fetch blips — stays populated during the season.
    """
    scoring_type = _FP_PARTNERS_SCORING_MAP.get(scoring, "HALF")
    url = (
        "https://partners.fantasypros.com/api/v1/consensus-rankings.php"
        f"?sport=NFL&year={season}&week=0&position=ALL&type=draft"
        f"&scoring={scoring_type}&filters={FTN_RATCLIFFE_EXPERT_ID}"
    )
    logger.info("Fetching FTN (Ratcliffe) rankings: %s", url)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    rows = _parse_fp_partners_players(resp.json(), limit=limit)
    if not rows:
        week = _in_season_week(season)
        if week is not None:
            url = (
                "https://partners.fantasypros.com/api/v1/consensus-rankings.php"
                f"?sport=NFL&year={season}&week={week}&position=ALL&type=weekly"
                f"&scoring={scoring_type}&filters={FTN_RATCLIFFE_EXPERT_ID}"
            )
            logger.info("FTN draft board empty — weekly probe: %s", url)
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            rows = _parse_fp_partners_players(resp.json(), limit=limit)
    logger.info("Parsed %d FTN (Ratcliffe) rankings", len(rows))
    return rows


def fetch_sharps(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 300
) -> List[Dict[str, Any]]:
    """Fetch the 2025 draft-accuracy podium consensus via the FP expert filter."""
    scoring_type = _FP_PARTNERS_SCORING_MAP.get(scoring, "HALF")
    url = (
        "https://partners.fantasypros.com/api/v1/consensus-rankings.php"
        f"?sport=NFL&year={season}&week=0&position=ALL&type=draft"
        f"&scoring={scoring_type}&filters={SHARPS_EXPERT_IDS}"
    )
    logger.info("Fetching sharps (2025 accuracy podium) rankings: %s", url)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
    resp.raise_for_status()
    rows = _parse_fp_partners_players(resp.json(), limit=limit)
    logger.info("Parsed %d sharps rankings", len(rows))
    return rows


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
def save_rankings(
    source: str, data: List[Dict[str, Any]], extra: Optional[Dict[str, Any]] = None
) -> Tuple[Path, bool]:
    """Save rankings to data/external/<source>_rankings.json.

    Writes the canonical envelope format the web service reads (source /
    fetched_at / players) so cache staleness is measured from fetched_at
    rather than file mtime. Skips the write when the player content is
    unchanged — the daily workflow commits this directory, and a fetched_at
    -only diff would produce a meaningless commit every day.

    Args:
        source: Cache file basename prefix (``data/external/<source>_rankings.json``).
        data: Player rows.
        extra: Optional additional envelope-level fields (e.g. ``week``,
            ``scoring``) merged in alongside ``source``/``fetched_at``/
            ``players``. Ignored by existing readers of the envelope (they
            only ever look at ``players``), so this is purely additive.

    Returns:
        ``(path, changed)`` — ``changed`` is False when the cache content
        was identical and the write was skipped. Callers use it to decide
        whether a dated archive snapshot is warranted.
    """
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EXTERNAL_DIR / f"{source}_rankings.json"

    if path.exists():
        try:
            existing = json.loads(path.read_text())
            existing_players = (
                existing.get("players")
                if isinstance(existing, dict)
                else existing  # legacy bare-list format
            )
            if existing_players == data:
                logger.info("Rankings unchanged for %s — cache not rewritten", source)
                return path, False
        except (json.JSONDecodeError, OSError):
            pass  # unreadable cache — overwrite it

    envelope = {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
        "players": data,
    }
    # Atomic write: this file is committed to main by the daily workflow, so
    # a reader (or a racing `git add`) must never observe a partial write.
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(envelope, f, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise
    logger.info("Saved %d rankings -> %s", len(data), path)
    return path, True


def archive_rankings_snapshot(sources: List[str]) -> List[Path]:
    """Write dated, gzipped snapshots of the given source caches.

    The live ``data/external/*.json`` caches are overwritten in place on
    every refresh, so no rankings history exists — which made it impossible
    to backtest the preseason consensus-anchor weights (2026-07-08 finding)
    or evaluate anchoring weekly in-season projections. Snapshots land in
    ``data/external/archive/YYYY-MM-DD/<source>_rankings.json.gz`` and are
    committed by the daily cron alongside the live caches.

    Only sources whose content actually changed this run should be passed
    in (a source absent from a date's directory is covered by its most
    recent prior snapshot). Gzip keeps each snapshot to a few KB, so a
    full season of history costs single-digit MB in git.

    Args:
        sources: Source names whose caches changed this run.

    Returns:
        Paths of the snapshot files written.
    """
    written: List[Path] = []
    if not sources:
        return written
    day_dir = ARCHIVE_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        src_path = EXTERNAL_DIR / f"{source}_rankings.json"
        if not src_path.exists():
            continue
        dest = day_dir / f"{source}_rankings.json.gz"
        with gzip.open(dest, "wt", encoding="utf-8") as f:
            f.write(src_path.read_text(encoding="utf-8"))
        written.append(dest)
        logger.info("Archived %s snapshot -> %s", source, dest)
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh external fantasy rankings from Sleeper, FantasyPros, "
            "ESPN, Draft Sharks, and FTN"
        )
    )
    parser.add_argument(
        "--season", type=int, default=2026, help="NFL season (default: 2026)"
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        choices=["ppr", "half_ppr", "standard"],
        help="Scoring format for FantasyPros (default: half_ppr)",
    )
    parser.add_argument(
        "--source",
        default="all",
        choices=[
            "all",
            "sleeper",
            "fantasypros",
            "fantasypros_weekly",
            "espn",
            "draftsharks",
            "ftn",
            "sharps",
        ],
        help="Which source to refresh (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=300,
        help="Max players per source (default: 300)",
    )
    args = parser.parse_args()

    print(f"\nExternal Rankings Refresh")
    print(f"Season: {args.season} | Scoring: {args.scoring} | Limit: {args.limit}")
    print("=" * 60)

    sources_to_fetch = (
        [
            "sleeper",
            "fantasypros",
            "fantasypros_weekly",
            "espn",
            "draftsharks",
            "ftn",
            "sharps",
        ]
        if args.source == "all"
        else [args.source]
    )

    results: Dict[str, str] = {}
    changed_sources: List[str] = []
    for source in sources_to_fetch:
        print(f"\n--- {source.upper()} ---")
        try:
            if source == "sleeper":
                data = fetch_sleeper(limit=args.limit)
            elif source == "fantasypros":
                data = fetch_fantasypros(
                    season=args.season, scoring=args.scoring, limit=args.limit
                )
            elif source == "fantasypros_weekly":
                data = fetch_fantasypros_weekly(
                    season=args.season, scoring=args.scoring, limit=args.limit
                )
            elif source == "espn":
                data = fetch_espn(season=args.season, limit=args.limit)
            elif source == "draftsharks":
                data = fetch_draftsharks(scoring=args.scoring, limit=args.limit)
            elif source == "ftn":
                data = fetch_ftn(
                    season=args.season, scoring=args.scoring, limit=args.limit
                )
            elif source == "sharps":
                data = fetch_sharps(
                    season=args.season, scoring=args.scoring, limit=args.limit
                )
            else:
                continue

            if data:
                path, changed = save_rankings(source, data)
                if changed:
                    changed_sources.append(source)
                results[source] = f"OK ({len(data)} players -> {path})"

                # Show top 10
                print(f"  Top 10:")
                for row in data[:10]:
                    print(
                        f"    {row['rank']:>3}. {row['player_name']:<25} "
                        f"{row['position']:<3} {row.get('team', '')}"
                    )
            else:
                results[source] = "EMPTY (no data returned)"
                print(f"  No data returned")

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            results[source] = f"FAILED (HTTP {status})"
            print(f"  HTTP error: {status} -- {exc}")
        except requests.exceptions.ConnectionError as exc:
            results[source] = "FAILED (connection error)"
            print(f"  Connection error: {exc}")
        except requests.exceptions.Timeout:
            results[source] = "FAILED (timeout)"
            print(f"  Request timed out")
        except Exception as exc:
            results[source] = f"FAILED ({exc})"
            print(f"  Error: {exc}")

        # Brief pause between sources to be polite
        if source != sources_to_fetch[-1]:
            time.sleep(1)

    # Dated snapshot of every cache that actually changed this run —
    # the anchor-weight backtest history (see archive_rankings_snapshot).
    try:
        archived = archive_rankings_snapshot(changed_sources)
    except OSError as exc:
        archived = []
        logger.warning("Rankings snapshot archive failed: %s", exc)

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary:")
    for source, status in results.items():
        print(f"  {source:<15} {status}")
    if archived:
        print(f"  archived {len(archived)} snapshot(s) -> {ARCHIVE_DIR}")

    failed = sum(1 for s in results.values() if s.startswith("FAILED"))
    return 1 if failed == len(results) else 0


if __name__ == "__main__":
    sys.exit(main())
