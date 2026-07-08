#!/usr/bin/env python3
"""Sleeper External Projections Ingester — Bronze Layer (Phase 73-01 / Phase 1.1).

Fetches weekly fantasy projections from the Sleeper public API and writes a
timestamped Parquet to::

    data/bronze/external_projections/sleeper/season=YYYY/week=WW/sleeper_{ts}.parquet

Per CONTEXT D-01 (LOCKED), this script does NOT call ``requests`` or
``urllib`` directly — all Sleeper HTTP traffic flows through
``src.sleeper_http.fetch_sleeper_json``. A structural test
(``test_sleeper_uses_shared_http_helper_not_requests_directly``) greps this
file's source and asserts no ``import requests`` appears.

Fail-open contract (D-06)
-------------------------
``fetch_sleeper_json`` already returns ``{}`` on any error. ``main()`` checks
for empty payload and exits 0 without writing.

Historical backfill mode (Phase 1.1)
-------------------------------------
Pass ``--historical`` together with ``--season`` and ``--weeks 1-18`` to
backfill a full season.  The endpoint
``https://api.sleeper.app/v1/projections/nfl/regular/{season}/{week}``
serves historical weeks.  A 0.5 s sleep is inserted between calls to be
polite to the Sleeper API.  Weeks that already have a Bronze parquet are
skipped by default (pass ``--overwrite`` to re-fetch).

The ``player_id`` column is populated using a two-step strategy:

1. ``nfl_data_py.import_ids()`` provides a ``sleeper_id -> gsis_id`` map
   covering ~6 000 entries.
2. Any remaining unresolved IDs fall back to a name-fuzzy lookup via
   ``src.player_name_resolver.PlayerNameResolver`` (fail-open; blank on miss).

CLI
---
    # Single-week (original behaviour):
    python scripts/ingest_external_projections_sleeper.py --season 2025 --week 1

    # Historical backfill:
    python scripts/ingest_external_projections_sleeper.py \\
        --historical --season 2023 --weeks 1-18 --scoring half_ppr
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import SENTIMENT_CONFIG  # noqa: E402
from src.sleeper_http import fetch_sleeper_json  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_external_projections_sleeper")

_SOURCE_LABEL: str = "sleeper"
_DEFAULT_OUT_ROOT: Path = _PROJECT_ROOT / "data" / "bronze" / "external_projections"

# How long to sleep between API calls in historical mode (seconds).
_HISTORICAL_SLEEP_S: float = 0.5


# ---------------------------------------------------------------------------
# ID-mapping helpers
# ---------------------------------------------------------------------------


def _build_gsis_map() -> Dict[str, str]:
    """Build a sleeper_id (str) -> gsis_id (str) mapping via nfl_data_py.

    Falls back gracefully if nfl_data_py is unavailable.

    Returns:
        Dict mapping Sleeper player ID string to GSIS player ID string.
    """
    try:
        from src.nfl_data_adapter import NFLDataAdapter

        ids = NFLDataAdapter().fetch_ids()
        if ids.empty:
            raise ValueError("adapter returned no ID crosswalk data")
        # sleeper_id may be float in the DataFrame; convert to int-string.
        clean = ids.dropna(subset=["sleeper_id", "gsis_id"])
        mapping: Dict[str, str] = {}
        for _, row in clean.iterrows():
            try:
                sid = str(int(float(row["sleeper_id"])))
                gsis = str(row["gsis_id"]).strip()
                if sid and gsis:
                    mapping[sid] = gsis
            except (ValueError, TypeError):
                continue
        logger.info("Built sleeper->gsis map with %d entries", len(mapping))
        return mapping
    except Exception as exc:
        logger.warning("Could not build sleeper->gsis map: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Parse / normalise helpers
# ---------------------------------------------------------------------------


def _normalise_to_records(
    raw: Any,
    season: int,
    week: int,
    scoring: str,
    player_registry: Dict[str, Dict[str, Any]],
    gsis_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Normalise the Sleeper projections payload to per-player Bronze rows.

    Sleeper returns a dict keyed by ``player_id`` with each value containing
    a ``stats`` sub-dict. We map ``pts_half_ppr`` / ``pts_ppr`` / ``pts_std``
    based on scoring format.

    Args:
        raw: Sleeper API response (dict[player_id -> {stats, ...}]).
        season: NFL season year.
        week: NFL week number.
        scoring: One of "ppr", "half_ppr", "standard".
        player_registry: Sleeper player registry (id -> {name, team, position}).
        gsis_map: Optional pre-built sleeper_id -> gsis_id lookup.

    Returns:
        List of Bronze record dicts.
    """
    if not isinstance(raw, dict) or not raw:
        return []

    pts_key = {
        "ppr": "pts_ppr",
        "half_ppr": "pts_half_ppr",
        "standard": "pts_std",
    }.get(scoring, "pts_half_ppr")

    if gsis_map is None:
        gsis_map = {}

    records: List[Dict[str, Any]] = []
    projected_at = datetime.now(timezone.utc).isoformat()

    for player_id, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        # Sleeper API may return either {"stats": {...}} (newer) or a flat
        # stats dict directly (older). Handle both.
        if "stats" in payload and isinstance(payload["stats"], dict):
            stats = payload["stats"]
        else:
            stats = payload
        projected_points = stats.get(pts_key)
        if projected_points is None:
            continue

        meta = player_registry.get(player_id) or {}

        # Resolve GSIS player_id from map; fall back to raw Sleeper ID.
        gsis_id: str = gsis_map.get(str(player_id), "")

        records.append(
            {
                "player_name": meta.get("full_name") or meta.get("name"),
                "player_id": gsis_id or str(player_id),
                "sleeper_player_id": str(player_id),
                "team": meta.get("team"),
                "position": meta.get("position"),
                "projected_points": float(projected_points),
                "scoring_format": scoring,
                "source": _SOURCE_LABEL,
                "season": int(season),
                "week": int(week),
                "projected_at": projected_at,
                "raw_payload": json.dumps(payload),
            }
        )
    return records


def _parse_sleeper_response(
    raw: Any,
    season: int,
    week: int,
    scoring: str,
    player_registry: Optional[Dict[str, Dict[str, Any]]] = None,
    gsis_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Parse a Sleeper projections payload and return a Bronze-schema DataFrame.

    This is the public parse entry-point used by tests and the Silver
    consolidation step.  It delegates to ``_normalise_to_records`` and wraps
    the result in a DataFrame.

    Args:
        raw: Sleeper API response dict.
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format ("ppr", "half_ppr", "standard").
        player_registry: Optional player registry dict (id -> meta).
        gsis_map: Optional sleeper_id -> gsis_id map.

    Returns:
        DataFrame with the Bronze Sleeper schema.
    """
    registry = player_registry or {}
    records = _normalise_to_records(raw, season, week, scoring, registry, gsis_map)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Write helper
# ---------------------------------------------------------------------------


def _write_bronze(
    records: List[Dict[str, Any]],
    season: int,
    week: int,
    out_root: Path,
) -> Optional[Path]:
    """Write Bronze Parquet at the canonical season/week path."""
    if not records:
        logger.warning(
            "No Sleeper projections to write for season=%d week=%d (D-06 fail-open)",
            season,
            week,
        )
        return None

    week_dir = out_root / _SOURCE_LABEL / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = week_dir / f"{_SOURCE_LABEL}_{ts}.parquet"

    df = pd.DataFrame(records)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d Sleeper projections to %s", len(records), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Historical backfill helpers
# ---------------------------------------------------------------------------


def _parse_weeks_arg(weeks_str: str) -> List[int]:
    """Parse '1-18' or '1,5,10' week range argument.

    Args:
        weeks_str: Week range string.

    Returns:
        Sorted list of week integers.
    """
    if "-" in weeks_str:
        parts = weeks_str.split("-", 1)
        return list(range(int(parts[0]), int(parts[1]) + 1))
    return sorted(int(w) for w in weeks_str.split(","))


def _week_already_exists(season: int, week: int, out_root: Path) -> bool:
    """Return True if a Bronze parquet already exists for this season/week."""
    week_dir = out_root / _SOURCE_LABEL / f"season={season}" / f"week={week:02d}"
    if not week_dir.exists():
        return False
    return any(week_dir.glob("*.parquet"))


def run_historical_backfill(
    season: int,
    weeks: List[int],
    scoring: str,
    out_root: Path,
    overwrite: bool = False,
    player_registry: Optional[Dict[str, Dict[str, Any]]] = None,
    gsis_map: Optional[Dict[str, str]] = None,
) -> Dict[str, int]:
    """Backfill Sleeper historical projections for a season's weeks.

    Fetches each week from the Sleeper historical projections endpoint,
    normalises the payload, and writes Bronze Parquet.  Sleeps 0.5 s
    between calls to be polite to the API.

    Args:
        season: NFL season year.
        weeks: List of week numbers to backfill.
        scoring: Scoring format.
        out_root: Bronze output root directory.
        overwrite: If False, skip weeks that already have a parquet.
        player_registry: Optional player metadata dict (id -> meta).
        gsis_map: Optional sleeper_id -> gsis_id map.

    Returns:
        Summary dict with keys "written", "skipped", "failed".
    """
    if player_registry is None:
        logger.info("Fetching Sleeper player registry for name resolution…")
        player_registry = fetch_sleeper_json(SENTIMENT_CONFIG["sleeper_players_url"])
        if not isinstance(player_registry, dict):
            player_registry = {}
        logger.info("Registry has %d entries", len(player_registry))

    if gsis_map is None:
        gsis_map = _build_gsis_map()

    summary = {"written": 0, "skipped": 0, "failed": 0}

    for week in weeks:
        if not overwrite and _week_already_exists(season, week, out_root):
            logger.info("Season %d Week %02d — already exists, skipping", season, week)
            summary["skipped"] += 1
            continue

        logger.info("Season %d Week %02d — fetching…", season, week)
        url = SENTIMENT_CONFIG["sleeper_projections_url"].format(
            season=season, week=week
        )
        raw = fetch_sleeper_json(url)
        if not raw:
            logger.warning(
                "Season %d Week %02d — empty response, skipping", season, week
            )
            summary["failed"] += 1
            time.sleep(_HISTORICAL_SLEEP_S)
            continue

        records = _normalise_to_records(
            raw, season, week, scoring, player_registry, gsis_map
        )
        out_path = _write_bronze(records, season, week, out_root)
        if out_path is not None:
            summary["written"] += 1
        else:
            summary["failed"] += 1

        time.sleep(_HISTORICAL_SLEEP_S)

    logger.info(
        "Backfill season=%d complete — written=%d skipped=%d failed=%d",
        season,
        summary["written"],
        summary["skipped"],
        summary["failed"],
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument list (``None`` to use ``sys.argv``).

    Returns:
        Exit code (0 = success).
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])

    # Original single-week mode args.
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="Week number (single-week mode). Not required with --historical.",
    )
    parser.add_argument(
        "--scoring",
        choices=["ppr", "half_ppr", "standard"],
        default="half_ppr",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=_DEFAULT_OUT_ROOT,
    )
    parser.add_argument(
        "--registry-fixture",
        type=Path,
        default=None,
        help=(
            "Optional path to a JSON fixture standing in for the Sleeper "
            "player registry (used by tests; production fetches live)."
        ),
    )
    parser.add_argument(
        "--projections-fixture",
        type=Path,
        default=None,
        help=(
            "Optional path to a JSON fixture standing in for the Sleeper "
            "projections payload (used by tests)."
        ),
    )

    # Historical backfill mode args.
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Run historical backfill for --season / --weeks range.",
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default="1-18",
        help=("Week range for historical mode: '1-18' or '1,5,10'. " "Default: 1-18."),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-fetch weeks that already have a Bronze parquet.",
    )

    args = parser.parse_args(argv)

    # -----------------------------------------------------------------------
    # Historical backfill mode
    # -----------------------------------------------------------------------
    if args.historical:
        weeks = _parse_weeks_arg(args.weeks)
        logger.info(
            "Historical backfill: season=%d weeks=%s scoring=%s",
            args.season,
            weeks,
            args.scoring,
        )
        run_historical_backfill(
            season=args.season,
            weeks=weeks,
            scoring=args.scoring,
            out_root=args.out_root,
            overwrite=args.overwrite,
        )
        return 0

    # -----------------------------------------------------------------------
    # Original single-week mode
    # -----------------------------------------------------------------------
    if args.week is None:
        parser.error("--week is required unless --historical is specified.")

    # Fetch player registry (or load fixture for tests).
    if args.registry_fixture and args.registry_fixture.exists():
        player_registry: Dict[str, Any] = json.loads(
            args.registry_fixture.read_text(encoding="utf-8")
        )
        if not isinstance(player_registry, dict):
            player_registry = {}
    else:
        player_registry = fetch_sleeper_json(SENTIMENT_CONFIG["sleeper_players_url"])
        if not isinstance(player_registry, dict):
            player_registry = {}

    # Fetch projections payload (or load fixture).
    if args.projections_fixture and args.projections_fixture.exists():
        raw: Any = json.loads(args.projections_fixture.read_text(encoding="utf-8"))
    else:
        raw = fetch_sleeper_json(_build_url(args.season, args.week))

    records = _normalise_to_records(
        raw, args.season, args.week, args.scoring, player_registry
    )
    _write_bronze(records, args.season, args.week, args.out_root)
    return 0


def _build_url(season: int, week: int) -> str:
    """Format the Sleeper projections URL for a given season/week."""
    template = SENTIMENT_CONFIG["sleeper_projections_url"]
    return template.format(season=season, week=week)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
