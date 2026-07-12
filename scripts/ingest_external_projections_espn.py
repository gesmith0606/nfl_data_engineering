#!/usr/bin/env python3
"""ESPN External Projections Ingester — Bronze Layer (Phase 73-01).

Fetches weekly fantasy projections from ESPN's public fantasy API
(no auth required for `league=0` projections) and writes a timestamped
Parquet to::

    data/bronze/external_projections/espn/season=YYYY/week=WW/espn_{ts}.parquet

The Parquet schema mirrors the other Phase 73 Bronze ingesters
(Sleeper, FantasyPros) so that the Wave 2 Silver consolidator can stack
all sources with a single ``pd.concat``::

    player_name, player_id, team, position, projected_points,
    scoring_format, source, season, week, projected_at, raw_payload

Fail-open contract (D-06)
-------------------------
Any ``requests.RequestException``, ``KeyError``, ``ValueError``, or
``json.JSONDecodeError`` raised in ``main()`` is logged at WARNING level and
the process exits 0 with no Parquet written.  This guarantees the daily cron
never breaks because of an upstream outage.

CLI
---
    python scripts/ingest_external_projections_espn.py --season 2025 --week 1
    python scripts/ingest_external_projections_espn.py --season 2025 --week 1 \\
        --scoring ppr --out-root data/bronze/external_projections

Historical backfill
-------------------
ESPN's ``league=0`` endpoint only serves the current season, but the
league-less ``/seasons/{season}/players`` collection endpoint archives the
raw per-week PROJECTED stat lines (statSourceId=1) for past seasons. Those
raw stats carry no league scoring (``appliedTotal`` is 0), so this mode
scores them with our own ``SCORING_CONFIGS`` via ``calculate_fantasy_points``
— which also makes the consensus comparison scoring-identical on both sides.

    python scripts/ingest_external_projections_espn.py --historical \\
        --season 2023 --weeks 1-18 --scoring half_ppr
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Bootstrap project root on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.player_name_resolver import PlayerNameResolver  # noqa: E402
from src.scoring_calculator import calculate_fantasy_points  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_external_projections_espn")

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_SOURCE_LABEL: str = "espn"
_REQUEST_TIMEOUT_S: int = 15
_USER_AGENT: str = "nfl-data-engineering/0.1 (external-projections-espn)"

# ESPN endpoint — public league=0 projections, no auth required.
_ESPN_URL_TEMPLATE: str = (
    "https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/"
    "leagues/0?view=mPlayer&view=kona_player_info"
)

# ESPN scoring period uses an integer week number; this filter is applied via
# the X-Fantasy-Filter header so we only get the requested week's projection.
_ESPN_FILTER_HEADER_TEMPLATE: str = (
    '{{"players":{{"limit":600,"sortPercOwned":{{"sortAsc":false,'
    '"sortPriority":1}},"filterStatsForSourceIds":{{"value":[1]}},'
    '"filterStatsForSplitTypeIds":{{"value":[1]}},'
    '"filterStatsForCurrentSeasonScoringPeriodId":{{"value":[{week}]}}}}}}'
)

# ESPN numeric position id → standardised abbreviation.
_POSITION_ID_TO_ABBR: Dict[int, str] = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "DST",
}

# ESPN numeric pro-team id → nflverse team abbreviation.  Compiled from the
# public ESPN proTeams reference (id 0 = free agent, ids 1-34 are franchises;
# 33/34 historically map to BAL/HOU on the ESPN side).
_TEAM_ID_TO_ABBR: Dict[int, str] = {
    0: "FA",
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WAS",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}

_VALID_SCORINGS: List[str] = ["ppr", "half_ppr", "standard"]


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def fetch_espn_projections(
    season: int, week: int, scoring: str = "half_ppr"
) -> pd.DataFrame:
    """Fetch and parse ESPN projections for a single (season, week).

    Args:
        season: Four-digit NFL season year (e.g. 2025).
        week: Regular-season week number (1-18).
        scoring: One of "ppr", "half_ppr", "standard".  ESPN's default
            league=0 scoring is half-PPR-like; this argument is recorded as a
            provenance column and used for downstream consolidation, but does
            not change the upstream URL (ESPN exposes only one league=0
            scoring view per call).

    Returns:
        Bronze-schema DataFrame.  Empty DataFrame is returned on any HTTP or
        JSON error so the caller can fail-open per D-06.
    """
    url = _ESPN_URL_TEMPLATE.format(season=season)
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "X-Fantasy-Filter": _ESPN_FILTER_HEADER_TEMPLATE.format(week=week),
        "X-Fantasy-Source": "kona",
        "X-Fantasy-Platform": "kona-PROD",
    }
    logger.info("Fetching ESPN projections: season=%d week=%d", season, week)
    resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    payload = resp.json()
    return _parse_espn_response(payload, season=season, week=week, scoring=scoring)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_espn_response(
    payload: dict, season: int, week: int, scoring: str
) -> pd.DataFrame:
    """Convert ESPN's raw JSON into a Bronze-schema DataFrame.

    The shape of the response is::

        {
          "players": [
            {"player": {"fullName": ..., "defaultPositionId": int,
                        "proTeamId": int,
                        "stats": [{"scoringPeriodId": int,
                                   "appliedTotal": float, ...}, ...]}},
            ...
          ]
        }

    Args:
        payload: Parsed JSON response from the ESPN endpoint.
        season: Four-digit season year (recorded in output rows).
        week: Week number (used to filter the matching ``stats`` entry).
        scoring: Scoring format recorded as a provenance column.

    Returns:
        DataFrame with the canonical Bronze schema; one row per player.
        Players whose ``stats`` list does not contain a row for ``week`` are
        omitted with a DEBUG log.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"ESPN payload not a dict: {type(payload)}")

    players = payload.get("players", [])
    if not isinstance(players, list):
        raise ValueError("ESPN payload.players is not a list")

    projected_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, object]] = []

    for entry in players:
        if not isinstance(entry, dict):
            continue
        player = entry.get("player", {})
        if not isinstance(player, dict):
            continue

        full_name = str(player.get("fullName", "")).strip()
        if not full_name:
            continue

        pos_id = player.get("defaultPositionId")
        team_id = player.get("proTeamId")
        position = _POSITION_ID_TO_ABBR.get(int(pos_id), "") if pos_id is not None else ""
        team = _TEAM_ID_TO_ABBR.get(int(team_id), "") if team_id is not None else ""

        # Find the stats entry that matches this week (scoringPeriodId).
        proj_points: Optional[float] = None
        for stat in player.get("stats", []) or []:
            if not isinstance(stat, dict):
                continue
            if int(stat.get("scoringPeriodId", -1)) != int(week):
                continue
            try:
                proj_points = float(stat.get("appliedTotal", 0.0))
            except (TypeError, ValueError):
                proj_points = None
            break

        if proj_points is None:
            logger.debug("No matching week=%d stats for %s — skipping", week, full_name)
            continue

        # Clamp negatives to zero per the projected-points invariant.
        if proj_points < 0:
            proj_points = 0.0

        rows.append(
            {
                "player_name": full_name,
                "player_id": "",  # filled in by _resolve_player_ids
                "team": team or None,
                "position": position or None,
                "projected_points": proj_points,
                "scoring_format": scoring,
                "source": _SOURCE_LABEL,
                "season": int(season),
                "week": int(week),
                "projected_at": projected_at,
                "raw_payload": json.dumps(player, ensure_ascii=False),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        logger.warning("ESPN parser produced 0 rows for season=%d week=%d", season, week)
    else:
        logger.info("ESPN parsed %d player rows for season=%d week=%d", len(df), season, week)
    return df


# ---------------------------------------------------------------------------
# Player ID resolution
# ---------------------------------------------------------------------------


def _resolve_player_ids(
    df: pd.DataFrame, resolver: PlayerNameResolver
) -> pd.DataFrame:
    """Populate the ``player_id`` column via PlayerNameResolver.

    Args:
        df: DataFrame from ``_parse_espn_response``.
        resolver: Pre-built PlayerNameResolver.

    Returns:
        DataFrame with ``player_id`` populated where resolution succeeded;
        unresolved rows keep the empty-string sentinel and are logged at
        WARNING level (Silver Wave 2 attempts a second-pass match).
    """
    if df.empty:
        return df

    resolved: List[str] = []
    unresolved: int = 0
    for _, row in df.iterrows():
        pid = resolver.resolve(
            row["player_name"],
            team=row.get("team") or None,
            position=row.get("position") or None,
        )
        if pid:
            resolved.append(pid)
        else:
            resolved.append("")
            unresolved += 1
    df = df.copy()
    df["player_id"] = resolved
    if unresolved:
        logger.warning(
            "PlayerNameResolver could not match %d/%d ESPN players "
            "(Silver consolidator will retry).",
            unresolved,
            len(df),
        )
    return df


# ---------------------------------------------------------------------------
# Bronze write
# ---------------------------------------------------------------------------


def _write_bronze(
    df: pd.DataFrame, out_root: Path, season: int, week: int
) -> Path:
    """Write the Bronze Parquet to the canonical partitioned path.

    Args:
        df: Resolved Bronze-schema DataFrame.
        out_root: Root directory for the external-projections Bronze layer.
        season: Four-digit season year (becomes ``season=YYYY`` partition).
        week: Week number (becomes ``week=WW`` partition).

    Returns:
        Path to the written Parquet file.
    """
    # Zero-padded week to match the Silver consolidator's read path
    # (week={week:02d}) — Sleeper/Yahoo ingesters already pad.
    partition = out_root / _SOURCE_LABEL / f"season={season}" / f"week={week:02d}"
    partition.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = partition / f"{_SOURCE_LABEL}_{timestamp}.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows → %s", len(df), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Historical backfill (league-less players endpoint, raw projected stats)
# ---------------------------------------------------------------------------

# Past seasons 404 on the league=0 endpoint; the players collection endpoint
# archives per-week projected stat lines (statSourceId=1) back to ~2018.
_ESPN_PLAYERS_URL_TEMPLATE: str = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/"
    "players?view=kona_player_info&scoringPeriodId={week}"
)

_ESPN_HIST_FILTER_TEMPLATE: str = (
    '{{"filterStatsForSourceIds":{{"value":[1]}},'
    '"filterStatsForSplitTypeIds":{{"value":[1]}},'
    '"filterStatsForCurrentSeasonScoringPeriodId":{{"value":[{week}]}},'
    '"limit":1500,"sortPercOwned":{{"sortAsc":false,"sortPriority":1}}}}'
)

# ESPN raw stat id → canonical stat key accepted by calculate_fantasy_points.
# Community-documented ids, spot-verified against 2022-2024 archived weeks.
_ESPN_STAT_ID_MAP: Dict[str, str] = {
    "3": "passing_yards",
    "4": "passing_tds",
    "20": "interceptions",
    "24": "rushing_yards",
    "25": "rushing_tds",
    "42": "receiving_yards",
    "43": "receiving_tds",
    "53": "receptions",
    "72": "fumbles_lost",
}
# 2-pt conversions are split across pass/rush/rec ids; summed into one key.
_ESPN_TWO_PT_IDS = ("19", "26", "44")


def fetch_espn_projections_historical(
    season: int, week: int, scoring: str = "half_ppr"
) -> pd.DataFrame:
    """Fetch archived ESPN projections for a past (season, week).

    The archived stat lines carry raw stat quantities only (appliedTotal is
    zero without a league context), so fantasy points are computed here with
    OUR scoring config — identical scoring on both sides of the comparison.

    Args:
        season: Past NFL season year (e.g. 2023).
        week: Regular-season week number (1-18).
        scoring: One of "ppr", "half_ppr", "standard".

    Returns:
        Bronze-schema DataFrame (same columns as the live-path parser).
        Empty DataFrame on any HTTP/JSON error (D-06 fail-open at callers).
    """
    url = _ESPN_PLAYERS_URL_TEMPLATE.format(season=season, week=week)
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "X-Fantasy-Filter": _ESPN_HIST_FILTER_TEMPLATE.format(week=week),
        "X-Fantasy-Source": "kona",
        "X-Fantasy-Platform": "kona-PROD",
    }
    logger.info("Fetching ESPN HISTORICAL projections: season=%d week=%d", season, week)
    resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    return _parse_historical_payload(resp.json(), season=season, week=week, scoring=scoring)


def _parse_historical_payload(
    payload: object, season: int, week: int, scoring: str
) -> pd.DataFrame:
    """Convert the players-endpoint JSON into a Bronze-schema DataFrame.

    Pure function (no I/O) so the stat-id mapping and our-scoring conversion
    are unit-testable against synthetic payloads.
    """
    entries = payload if isinstance(payload, list) else payload.get("players", [])
    projected_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, object]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        player = entry.get("player", entry)
        if not isinstance(player, dict):
            continue
        full_name = str(player.get("fullName", "")).strip()
        if not full_name:
            continue

        pos_id = player.get("defaultPositionId")
        team_id = player.get("proTeamId")
        position = _POSITION_ID_TO_ABBR.get(int(pos_id), "") if pos_id is not None else ""
        team = _TEAM_ID_TO_ABBR.get(int(team_id), "") if team_id is not None else ""
        if not position:
            continue  # D/ST and unmapped slots are out of eval scope

        raw_stats: Optional[Dict[str, float]] = None
        for stat in player.get("stats", []) or []:
            if not isinstance(stat, dict):
                continue
            if (
                stat.get("statSourceId") == 1
                and int(stat.get("scoringPeriodId", -1)) == int(week)
                and stat.get("statSplitTypeId") == 1
            ):
                raw_stats = stat.get("stats") or {}
                break
        if not raw_stats:
            continue

        stat_line: Dict[str, float] = {}
        for espn_id, key in _ESPN_STAT_ID_MAP.items():
            val = raw_stats.get(espn_id)
            if val is not None:
                stat_line[key] = float(val)
        two_pt = sum(float(raw_stats.get(i, 0.0) or 0.0) for i in _ESPN_TWO_PT_IDS)
        if two_pt:
            stat_line["two_pt_conversions"] = two_pt
        if not stat_line:
            continue

        proj_points = calculate_fantasy_points(stat_line, scoring_format=scoring)
        if proj_points < 0:
            proj_points = 0.0

        rows.append(
            {
                "player_name": full_name,
                "player_id": "",  # filled in by _resolve_player_ids
                "team": team or None,
                "position": position or None,
                "projected_points": round(float(proj_points), 2),
                "scoring_format": scoring,
                "source": _SOURCE_LABEL,
                "season": int(season),
                "week": int(week),
                "projected_at": projected_at,
                "raw_payload": json.dumps(
                    {"espnPlayerId": player.get("id"), "stats": raw_stats},
                    ensure_ascii=False,
                ),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        logger.warning(
            "ESPN historical parser produced 0 rows for season=%d week=%d",
            season,
            week,
        )
    else:
        logger.info(
            "ESPN historical parsed %d player rows for season=%d week=%d",
            len(df),
            season,
            week,
        )
    return df


def _parse_weeks_arg(weeks_arg: str) -> List[int]:
    """Parse a weeks CLI value like ``1-18`` or ``3,5,7`` into a sorted list."""
    weeks: set = set()
    for part in weeks_arg.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            weeks.update(range(int(lo), int(hi) + 1))
        elif part:
            weeks.add(int(part))
    return sorted(w for w in weeks if 1 <= w <= 18)


def run_historical_backfill(args: argparse.Namespace) -> int:
    """Backfill archived ESPN projections for one season across many weeks.

    Skips weeks whose Bronze partition already has an espn parquet unless
    ``--overwrite`` is passed. Sleeps between calls out of politeness.

    Returns:
        Process exit code (0 under the D-06 fail-open contract).
    """
    import time as _time

    weeks = _parse_weeks_arg(args.weeks)
    if not weeks:
        logger.warning("No valid weeks parsed from %r — nothing to do.", args.weeks)
        return 0

    resolver = PlayerNameResolver(bronze_root=_PROJECT_ROOT / "data/bronze")
    written = 0
    for week in weeks:
        partition = (
            args.out_root / _SOURCE_LABEL / f"season={args.season}" / f"week={week:02d}"
        )
        if not args.overwrite and partition.is_dir() and any(partition.glob("*.parquet")):
            logger.info("season=%d week=%d already ingested — skipping", args.season, week)
            continue
        try:
            df = fetch_espn_projections_historical(
                season=args.season, week=week, scoring=args.scoring
            )
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning(
                "[%s] historical fetch failed for week %d (fail-open): %s",
                _SOURCE_LABEL,
                week,
                exc,
            )
            continue
        if df.empty:
            continue
        df = _resolve_player_ids(df, resolver)
        _write_bronze(df, out_root=args.out_root, season=args.season, week=week)
        written += 1
        _time.sleep(0.6)

    logger.info(
        "Historical backfill complete: season=%d, %d/%d weeks written.",
        args.season,
        written,
        len(weeks),
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bronze ingester for ESPN public fantasy projections (Phase 73-01).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--season", type=int, required=True, help="NFL season (e.g. 2025).")
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="Regular-season week (1-18). Required unless --historical.",
    )
    parser.add_argument(
        "--historical",
        action="store_true",
        help=(
            "Backfill a PAST season from ESPN's archived per-week projected "
            "stat lines (league-less players endpoint), scoring them with our "
            "own SCORING_CONFIGS. Use with --weeks."
        ),
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default="1-18",
        help="Weeks to backfill in --historical mode (e.g. '1-18' or '3,5,7').",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-fetch weeks whose Bronze partition already exists (--historical).",
    )
    parser.add_argument(
        "--scoring",
        choices=_VALID_SCORINGS,
        default="half_ppr",
        help="Scoring format label recorded in the Bronze rows.",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("data/bronze/external_projections"),
        help="Root output directory for the external_projections Bronze layer.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point — fetch → parse → resolve → write.

    Returns:
        Process exit code.  Always 0 under the D-06 fail-open contract;
        even on exceptions, only a WARNING is emitted.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.historical:
        return run_historical_backfill(args)

    if args.week is None:
        parser.error("--week is required unless --historical is passed")

    try:
        df = fetch_espn_projections(
            season=args.season, week=args.week, scoring=args.scoring
        )
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning(
            "[%s] fetch failed (D-06 fail-open): %s",
            _SOURCE_LABEL,
            exc,
        )
        return 0

    if df.empty:
        logger.warning(
            "[%s] no rows parsed for season=%d week=%d — nothing written.",
            _SOURCE_LABEL,
            args.season,
            args.week,
        )
        return 0

    try:
        resolver = PlayerNameResolver(bronze_root=_PROJECT_ROOT / "data/bronze")
        df = _resolve_player_ids(df, resolver)
        _write_bronze(df, args.out_root, season=args.season, week=args.week)
    except Exception as exc:  # noqa: BLE001 — D-06 fail-open guard
        logger.warning(
            "[%s] resolve/write failed (D-06 fail-open): %s",
            _SOURCE_LABEL,
            exc,
        )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
