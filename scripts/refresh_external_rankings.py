#!/usr/bin/env python3
"""
Refresh external fantasy rankings from Sleeper, FantasyPros, and ESPN.

Fetches rankings from all three sources and caches them as JSON files in
data/external/ for the rankings API to consume. Designed to be run daily
alongside the sentiment pipeline.

Usage:
    python scripts/refresh_external_rankings.py
    python scripts/refresh_external_rankings.py --season 2026
    python scripts/refresh_external_rankings.py --source sleeper
    python scripts/refresh_external_rankings.py --source all --limit 300
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

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
# FantasyPros
# ---------------------------------------------------------------------------
def fetch_fantasypros(
    season: int = 2026, scoring: str = "half_ppr", limit: int = 300
) -> List[Dict[str, Any]]:
    """Fetch FantasyPros ECR consensus rankings."""
    scoring_type = _FP_SCORING_MAP.get(scoring, "half-ppr")
    url = (
        f"https://api.fantasypros.com/public/v2/json/nfl/{season}"
        f"/consensus-rankings.php?type={scoring_type}"
    )
    logger.info("Fetching FantasyPros ECR: %s", url)
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
    logger.info("Parsed %d FantasyPros rankings", len(rows))
    return rows[:limit]


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
# Save
# ---------------------------------------------------------------------------
def save_rankings(source: str, data: List[Dict[str, Any]]) -> Path:
    """Save rankings to data/external/<source>_rankings.json."""
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EXTERNAL_DIR / f"{source}_rankings.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("Saved %d rankings -> %s", len(data), path)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh external fantasy rankings from Sleeper, FantasyPros, ESPN"
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
        choices=["all", "sleeper", "fantasypros", "espn"],
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
        ["sleeper", "fantasypros", "espn"]
        if args.source == "all"
        else [args.source]
    )

    results: Dict[str, str] = {}
    for source in sources_to_fetch:
        print(f"\n--- {source.upper()} ---")
        try:
            if source == "sleeper":
                data = fetch_sleeper(limit=args.limit)
            elif source == "fantasypros":
                data = fetch_fantasypros(
                    season=args.season, scoring=args.scoring, limit=args.limit
                )
            elif source == "espn":
                data = fetch_espn(season=args.season, limit=args.limit)
            else:
                continue

            if data:
                path = save_rankings(source, data)
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

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary:")
    for source, status in results.items():
        print(f"  {source:<15} {status}")

    failed = sum(1 for s in results.values() if s.startswith("FAILED"))
    return 1 if failed == len(results) else 0


if __name__ == "__main__":
    sys.exit(main())
