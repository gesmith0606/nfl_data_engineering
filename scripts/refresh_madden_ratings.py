#!/usr/bin/env python3
"""
Refresh live EA Madden player ratings into Bronze.

EA publishes the ratings that power https://www.ea.com/games/madden-nfl/ratings
through Next.js data routes — one JSON page per position, no auth required.
The ratings are LIVE: EA re-rates players every week during the season
(iterations '1-base' → '2-week-1' → ... → '23-super-bowl'), and each page
serves the newest iteration.

Flow:
  1. GET the ratings page HTML → extract the current Next.js buildId
     (changes on every ea.com deploy, so it is scraped fresh each run).
  2. GET /_next/data/{buildId}/en/games/madden-nfl/ratings.json →
     the list of position filters (id + label).
  3. GET one positions-ratings page per position → player items.
  4. Normalize → data/bronze/madden_ratings/madden_ratings_{ts}.parquet

Usage:
    python scripts/refresh_madden_ratings.py
"""

import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("refresh_madden_ratings")

RATINGS_PAGE = "https://www.ea.com/games/madden-nfl/ratings"
NEXT_DATA_BASE = "https://www.ea.com/_next/data/{build_id}/en/games/madden-nfl"
OUT_DIR = _PROJECT_ROOT / "data" / "bronze" / "madden_ratings"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html",
}

# EA team label → nflverse abbreviation.
TEAM_LABEL_TO_ABBR = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


def _get(url: str, retries: int = 3) -> bytes:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 — retry any transport error
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_exc}")


def fetch_build_id() -> str:
    """Scrape the current Next.js buildId from the ratings page HTML."""
    html = _get(RATINGS_PAGE).decode("utf-8", errors="replace")
    match = re.search(r'"buildId":"([^"]+)"', html)
    if not match:
        raise RuntimeError("buildId not found in ratings page HTML")
    return match.group(1)


def _slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def fetch_positions(build_id: str) -> List[Tuple[str, str]]:
    """Return [(slug, position_id)] from the main ratings page filters."""
    url = f"{NEXT_DATA_BASE.format(build_id=build_id)}/ratings.json?franchiseSlug=madden-nfl"
    data = json.loads(_get(url))
    positions = data["pageProps"]["ratingsFilters"]["positions"]
    return [(_slugify(p["label"]), p["id"]) for p in positions]


def fetch_position_items(build_id: str, slug: str, pos_id: str) -> List[dict]:
    url = (
        f"{NEXT_DATA_BASE.format(build_id=build_id)}/ratings/positions-ratings/"
        f"{slug}/{pos_id}.json?franchiseSlug=madden-nfl"
        f"&pageType=positions-ratings&slug1={slug}&slug2={pos_id}"
    )
    data = json.loads(_get(url))
    return data["pageProps"].get("ratingsEntries", {}).get("items", [])


def normalize_items(items: List[dict]) -> List[Dict]:
    rows = []
    for it in items:
        team = it.get("team") or {}
        position = it.get("position") or {}
        iteration = it.get("iteration") or {}
        team_label = team.get("label") or ""
        rows.append(
            {
                "madden_id": it.get("id"),
                "player_name": f"{it.get('firstName', '')} {it.get('lastName', '')}".strip(),
                "team_label": team_label,
                "team": TEAM_LABEL_TO_ABBR.get(team_label, "FA"),
                "position": position.get("id"),
                "position_type": (position.get("positionType") or {}).get("id"),
                "overall_rating": it.get("overallRating"),
                "iteration_id": iteration.get("id"),
                "iteration_label": iteration.get("label"),
                "age": it.get("age"),
                "years_pro": it.get("yearsPro"),
                "jersey_num": it.get("jerseyNum"),
                "archetype": (it.get("archetype") or {}).get("label")
                if isinstance(it.get("archetype"), dict)
                else it.get("archetype"),
            }
        )
    return rows


def main() -> int:
    build_id = fetch_build_id()
    logger.info("buildId: %s", build_id)

    positions = fetch_positions(build_id)
    logger.info("positions: %s", [p[1] for p in positions])

    all_rows: List[Dict] = []
    for slug, pos_id in positions:
        try:
            items = fetch_position_items(build_id, slug, pos_id)
        except RuntimeError as exc:
            logger.warning("position %s failed: %s", pos_id, exc)
            continue
        rows = normalize_items(items)
        # The next-data route serves at most 100 players per position (top
        # OVR first; offset is ignored server-side). That covers every
        # starter; deeper bench players fall back to PFR-derived ratings.
        truncated = " (capped at 100 — bench tail omitted)" if len(rows) == 100 else ""
        logger.info("  %-4s %d players%s", pos_id, len(rows), truncated)
        all_rows.extend(rows)
        time.sleep(0.3)  # be polite

    if not all_rows:
        logger.error("No ratings fetched — aborting without writing")
        return 1

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["madden_id"])
    df["fetched_at"] = datetime.now().isoformat()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"madden_ratings_{ts}.parquet"
    df.to_parquet(out_path, index=False)
    iteration = df["iteration_id"].mode().iloc[0] if not df.empty else "?"
    logger.info(
        "Wrote %d players (%d teams, iteration=%s) -> %s",
        len(df),
        df["team"].nunique(),
        iteration,
        out_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
