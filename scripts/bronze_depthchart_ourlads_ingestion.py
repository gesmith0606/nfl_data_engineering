#!/usr/bin/env python3
"""
Bronze OurLads Depth Chart Ingestion — daily same-day starter-identity capture.

Our existing nflverse depth-chart Bronze (``data/bronze/depth_charts/``) lags
real-world role changes by 1-3 weeks — that lag killed the QB-starter-floor
model lever (see ``QB_STARTER_FLOOR_GATE.md``: it needs same-day starter
identity, not a stale snapshot). OurLads publishes a hand-maintained depth
chart per team that reacts same-day to beat-writer/coach reporting, so this
script forward-captures it daily to build up 2026-season starter-identity
history the nflverse lag can't provide. This is a pure ADD — it does not
replace or touch ``data/bronze/depth_charts/`` (nflverse) at all.

Live-verified 2026-08-18: all 32 teams at
``https://www.ourlads.com/nfldepthcharts/depthchart/{CODE}`` serve plain
static HTML (Bootstrap ``table table-bordered``) — no anti-bot, no JS
rendering, plain ``requests`` + BeautifulSoup works. Only OFFENSE skill
positions are captured (QB/RB/FB/WR/TE); OL/defense/special-teams rows in the
same table are parsed but discarded — out of scope for the starter-floor
lever this feeds.

CRITICAL GOTCHA (live-verified): Arizona's OurLads code is ``ARZ``, not
``ARI`` — ``ARI`` returns HTTP 200 with a completely EMPTY offense table
(silent failure, not a 404). :data:`OURLADS_TO_NFLVERSE` hardcodes the
verified 32-code map; :func:`run_depthchart_capture` asserts every team
parses a nonzero row count and exits 1 (loud) if any team comes back empty,
rather than silently shipping a partial/wrong capture.

Each OurLads player cell is ``"Lastname, Firstname <suffix>"`` where suffix
is a draft-class tag (``"24/2"``), UDFA/practice-squad/futures tag
(``"U/LAC"``, ``"CF23"``, ``"SF26"``), or similar — never part of the name.
Some rows render the name ALL CAPS (inconsistent even within one team's
table); :func:`parse_player_cell` title-cases only the ALL-CAPS case so
already-mixed-case names (``"McGovern"``, ``"O'Cyrus"``) are left untouched,
and always emits ``"First Last"`` order to match nflverse naming.

Output path (season-partitioned only, one combined snapshot per run — no
week dimension, mirrors ``bronze_season_props_ingestion.py``):
    data/bronze/depth_charts_ourlads/season=YYYY/ourlads_YYYYMMDD_HHMMSS.parquet

Schema (one row per team x position x depth slot):
    snapshot_ts   — UTC ISO-8601 string when this snapshot was taken
    season        — inferred NFL season year (reuses infer_nfl_season)
    team          — nflverse team abbreviation (e.g. "ARI", "LA")
    position      — QB / RB / FB / WR / TE
    slot          — depth slot within position, e.g. "QB1", "WR3"
    player_name   — "First Last" (suffix stripped, case-normalized)
    raw_cell      — original OurLads cell text, unmodified (audit trail)

WR slot ordering: OurLads lists three separate WR rows (LWR/RWR/SWR, i.e.
left/right/slot receiver). This script concatenates them in that fixed order
(LWR depth 1..N, then RWR, then SWR) and numbers WR1..WRn across the
concatenation — NOT per-row-reset numbering.

Usage:
    python scripts/bronze_depthchart_ourlads_ingestion.py
    python scripts/bronze_depthchart_ourlads_ingestion.py --dry-run
"""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from bronze_odds_api_ingestion import infer_nfl_season  # noqa: E402

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OURLADS_URL_TMPL = "https://www.ourlads.com/nfldepthcharts/depthchart/{code}"

#: OurLads team code -> nflverse team abbreviation. All 32 codes verified
#: live 2026-08-18 by walking the OurLads index page link list. Only two
#: differ from the OurLads code itself:
#:   ARZ (Cardinals) -> ARI  — "ARI" 200s with an EMPTY table, see module doc.
#:   LAR (Rams)       -> LA   — nflverse convention (not "LAR").
OURLADS_TO_NFLVERSE: Dict[str, str] = {
    "BUF": "BUF",
    "MIA": "MIA",
    "NE": "NE",
    "NYJ": "NYJ",
    "BAL": "BAL",
    "CIN": "CIN",
    "CLE": "CLE",
    "PIT": "PIT",
    "HOU": "HOU",
    "IND": "IND",
    "JAX": "JAX",
    "TEN": "TEN",
    "DEN": "DEN",
    "KC": "KC",
    "LV": "LV",
    "LAC": "LAC",
    "DAL": "DAL",
    "NYG": "NYG",
    "PHI": "PHI",
    "WAS": "WAS",
    "CHI": "CHI",
    "DET": "DET",
    "GB": "GB",
    "MIN": "MIN",
    "ATL": "ATL",
    "CAR": "CAR",
    "NO": "NO",
    "TB": "TB",
    "ARZ": "ARI",
    "LAR": "LA",
    "SF": "SF",
    "SEA": "SEA",
}

#: Offense position labels kept from the OurLads offense table.
OFFENSE_POSITIONS = frozenset({"QB", "RB", "FB", "LWR", "RWR", "SWR", "TE"})
#: WR sub-rows, in the fixed concatenation order used for WR1..WRn numbering.
WR_ROW_ORDER = ["LWR", "RWR", "SWR"]
#: Positions that map 1:1 to an output `position` value with no combining.
SIMPLE_POSITIONS = ("QB", "RB", "FB", "TE")

REQUEST_DELAY_S = 1.0

BRONZE_DEPTHCHART_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "bronze",
    "depth_charts_ourlads",
)

DEPTHCHART_SCHEMA_COLS: List[str] = [
    "snapshot_ts",
    "season",
    "team",
    "position",
    "slot",
    "player_name",
    "raw_cell",
]

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def fetch_team_page(ourlads_code: str) -> str:
    """Fetch one team's OurLads depth-chart HTML page.

    Args:
        ourlads_code: OurLads team code (key of :data:`OURLADS_TO_NFLVERSE`).

    Returns:
        Raw HTML response body.

    Raises:
        RuntimeError: On non-200 HTTP status.
    """
    url = OURLADS_URL_TMPL.format(code=ourlads_code)
    response = requests.get(url, headers=_REQUEST_HEADERS, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for {url}")
    return response.text


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


def parse_player_cell(raw_text: str) -> Optional[Dict[str, str]]:
    """Parse one OurLads player cell into a name + audit-trail dict.

    Cell format is ``"Lastname, Firstname <suffix>"`` where suffix is a
    draft-class/UDFA/practice-squad tag (never part of the name) — e.g.
    ``"Allen, Josh 18/1"``, ``"Palmer, Joshua U/LAC"``, ``"Shavers, Tyrell
    CF23"``. Some ROWS render the WHOLE name ALL CAPS (``"ALLEN, JOSH
    18/1"``); this is title-cased back to normal case, but ONLY when BOTH
    the last and first name are upper — genuine two-letter-initialism names
    that are correctly all-caps on their own (``"Moore, DJ"`` -> "DJ Moore",
    not the display-quirk case) are left alone, as are already mixed-case
    names (``"McGovern, Connor"``, ``"Torrence, O'Cyrus"``).

    Args:
        raw_text: Anchor text from one ``Player N`` table cell (already
            comma/whitespace-stripped by the caller is NOT assumed — this
            function does its own ``.strip()``).

    Returns:
        ``{"player_name": "First Last", "raw_cell": raw_text}``, or None for
        an empty/unfilled depth slot.
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return None
    if "," not in raw_text:
        # Unexpected shape — keep the raw text as the name rather than
        # dropping the row (Bronze warn-never-block: never silently lose a
        # player because of a format we didn't anticipate).
        return {"player_name": raw_text, "raw_cell": raw_text}

    last, rest = raw_text.split(",", 1)
    tokens = rest.strip().split()
    if len(tokens) >= 2:
        first = " ".join(tokens[:-1])
    elif tokens:
        first = tokens[0]
    else:
        first = ""

    last = last.strip()
    # Only normalize when the WHOLE name is rendered upper (a display quirk
    # on some rows) -- title-casing a lone-upper first name would mangle
    # genuine initialisms like "DJ" ("Moore, DJ" is correctly "DJ Moore",
    # not "Dj Moore").
    if last.isupper() and first.isupper():
        last = last.title()
        first = first.title()

    player_name = f"{first} {last}".strip()
    return {"player_name": player_name, "raw_cell": raw_text}


def parse_offense_rows(html: str) -> Dict[str, List[Dict[str, str]]]:
    """Parse the OFFENSE table's skill-position rows from a team's HTML page.

    The offense table is always the first ``table.table-bordered`` on the
    page (defense/special-teams/reserves tables follow it). Only rows whose
    ``Pos`` cell is in :data:`OFFENSE_POSITIONS` are kept; empty depth slots
    (unfilled ``Player N`` cells) are skipped.

    Args:
        html: Raw HTML from :func:`fetch_team_page`.

    Returns:
        Dict mapping OurLads position label (``"QB"``, ``"LWR"``, etc.) to
        an ordered list of parsed player dicts (empty list, not a missing
        key, when the position row exists but has zero filled slots — a
        genuinely missing row also yields an empty list via ``.get``).
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="table-bordered")
    if not tables:
        return {}
    tbody = tables[0].find("tbody")
    if tbody is None:
        return {}

    rows_by_pos: Dict[str, List[Dict[str, str]]] = {}
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        pos = cells[0].get_text(strip=True)
        if pos not in OFFENSE_POSITIONS:
            continue
        players: List[Dict[str, str]] = []
        # cells: [Pos, No., Player1, No, Player2, No, Player3, No, Player4, No, Player5]
        for i in range(2, len(cells), 2):
            link = cells[i].find("a")
            text = link.get_text(strip=True) if link else cells[i].get_text(strip=True)
            parsed = parse_player_cell(text)
            if parsed:
                players.append(parsed)
        rows_by_pos[pos] = players
    return rows_by_pos


def build_team_rows(html: str, ourlads_code: str, snapshot_ts: str, season: int) -> List[dict]:
    """Turn one team's parsed offense rows into flat output-schema rows.

    Args:
        html: Raw HTML from :func:`fetch_team_page`.
        ourlads_code: OurLads team code (looked up in
            :data:`OURLADS_TO_NFLVERSE` for the output ``team`` column).
        snapshot_ts: UTC ISO-8601 snapshot timestamp string, shared across
            every row in this run.
        season: Inferred NFL season year, shared across every row.

    Returns:
        List of dicts matching :data:`DEPTHCHART_SCHEMA_COLS`. Empty when
        the team's offense table has zero skill-position rows (caller
        treats this as a per-team failure).
    """
    rows_by_pos = parse_offense_rows(html)
    nflverse_team = OURLADS_TO_NFLVERSE[ourlads_code]
    out: List[dict] = []

    def _emit(position: str, players: List[Dict[str, str]]) -> None:
        for depth, player in enumerate(players, start=1):
            out.append(
                {
                    "snapshot_ts": snapshot_ts,
                    "season": season,
                    "team": nflverse_team,
                    "position": position,
                    "slot": f"{position}{depth}",
                    "player_name": player["player_name"],
                    "raw_cell": player["raw_cell"],
                }
            )

    for pos in SIMPLE_POSITIONS:
        _emit(pos, rows_by_pos.get(pos, []))

    wr_players: List[Dict[str, str]] = []
    for wr_row in WR_ROW_ORDER:
        wr_players.extend(rows_by_pos.get(wr_row, []))
    _emit("WR", wr_players)

    return out


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def write_depthchart_parquet(df: pd.DataFrame, season: int, dry_run: bool = False) -> str:
    """Write the combined 32-team snapshot to Bronze Parquet.

    Args:
        df: Rows matching :data:`DEPTHCHART_SCHEMA_COLS`.
        season: NFL season year (partition directory).
        dry_run: When True, skip all file I/O.

    Returns:
        Absolute output path (whether or not the file was written).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BRONZE_DEPTHCHART_DIR, f"season={season}")
    out_path = os.path.join(out_dir, f"ourlads_{timestamp}.parquet")

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to %s", len(df), out_path)
        return out_path

    os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(df), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_depthchart_capture(dry_run: bool = False) -> int:
    """Fetch, parse, and persist a daily 32-team OurLads offense snapshot.

    Fails loud (exit 1) if ANY team parses zero offense rows — this is the
    repo's zero-row fail-hard contract (see module docstring re: the ARZ/ARI
    silent-empty gotcha) rather than the usual Bronze warn-never-block
    posture. Successfully-parsed teams are still written to Parquet even
    when other teams fail, so one broken team doesn't discard 31 good ones
    — the run just exits 1 so CI/cron surfaces the failure instead of a
    silent partial capture.

    Args:
        dry_run: When True, fetch/parse but do not write Parquet.

    Returns:
        Exit code (0 = all 32 teams parsed nonzero rows; 1 = zero rows
        overall, or any individual team came back empty).
    """
    snapshot_ts = datetime.now(timezone.utc).isoformat()
    season = infer_nfl_season(snapshot_ts)

    codes = sorted(OURLADS_TO_NFLVERSE)
    all_rows: List[dict] = []
    per_team_counts: Dict[str, int] = {}

    for idx, code in enumerate(codes):
        try:
            html = fetch_team_page(code)
            rows = build_team_rows(html, code, snapshot_ts, season)
        except Exception as exc:  # network/HTTP/parse — logged, not fatal per-team
            logger.error("OurLads %s fetch/parse failed: %s", code, exc)
            rows = []

        per_team_counts[code] = len(rows)
        if rows:
            logger.info("OurLads %s (%s): %d offense rows", code, OURLADS_TO_NFLVERSE[code], len(rows))
        else:
            logger.error(
                "OurLads %s (%s): ZERO offense rows — silent-failure signature "
                "(wrong team code? see ARZ/ARI gotcha in module docstring)",
                code,
                OURLADS_TO_NFLVERSE[code],
            )
        all_rows.extend(rows)

        if idx < len(codes) - 1:
            time.sleep(REQUEST_DELAY_S)

    df = pd.DataFrame(all_rows, columns=DEPTHCHART_SCHEMA_COLS)

    if df.empty:
        logger.error("Zero rows captured across ALL 32 teams — exiting 1.")
        return 1

    write_depthchart_parquet(df, season, dry_run=dry_run)

    empty_teams = [code for code, n in per_team_counts.items() if n == 0]
    logger.info(
        "OurLads depth-chart capture complete: %d rows, %d/%d teams nonzero%s",
        len(df),
        len(codes) - len(empty_teams),
        len(codes),
        " — DRY RUN" if dry_run else "",
    )

    if empty_teams:
        logger.error(
            "FAIL: %d/%d teams returned zero rows: %s", len(empty_teams), len(codes), empty_teams
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the Bronze OurLads depth-chart ingestion script."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch all 32 teams' OurLads depth charts and write a combined "
            "same-day offense-skill-position Bronze Parquet snapshot. Exits "
            "1 if any team returns zero rows (fail-hard, not silent-partial)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but do not write Parquet files.",
    )
    args = parser.parse_args()
    sys.exit(run_depthchart_capture(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
