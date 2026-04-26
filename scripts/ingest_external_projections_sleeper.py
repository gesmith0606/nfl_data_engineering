#!/usr/bin/env python3
"""Sleeper External Projections Ingester — Bronze Layer (Phase 73-01).

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

CLI
---
    python scripts/ingest_external_projections_sleeper.py --season 2025 --week 1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
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
_DEFAULT_OUT_ROOT: Path = (
    _PROJECT_ROOT / "data" / "bronze" / "external_projections"
)


def _build_url(season: int, week: int) -> str:
    """Format the Sleeper projections URL for a given season/week."""
    template = SENTIMENT_CONFIG["sleeper_projections_url"]
    return template.format(season=season, week=week)


def _normalise_to_records(
    raw: Any,
    season: int,
    week: int,
    scoring: str,
    player_registry: Dict[str, Dict[str, Any]],
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
        records.append(
            {
                "player_name": meta.get("full_name") or meta.get("name"),
                "player_id": str(player_id),
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

    week_dir = (
        out_root / _SOURCE_LABEL / f"season={season}" / f"week={week:02d}"
    )
    week_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = week_dir / f"{_SOURCE_LABEL}_{ts}.parquet"

    df = pd.DataFrame(records)
    df.to_parquet(out_path, index=False)
    logger.info(
        "Wrote %d Sleeper projections to %s", len(records), out_path
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
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
    args = parser.parse_args()

    # Fetch player registry (or load fixture for tests).
    if args.registry_fixture and args.registry_fixture.exists():
        player_registry = json.loads(args.registry_fixture.read_text(encoding="utf-8"))
        if not isinstance(player_registry, dict):
            player_registry = {}
    else:
        player_registry = fetch_sleeper_json(SENTIMENT_CONFIG["sleeper_players_url"])
        if not isinstance(player_registry, dict):
            player_registry = {}

    # Fetch projections payload (or load fixture).
    if args.projections_fixture and args.projections_fixture.exists():
        raw = json.loads(args.projections_fixture.read_text(encoding="utf-8"))
    else:
        raw = fetch_sleeper_json(_build_url(args.season, args.week))

    records = _normalise_to_records(
        raw, args.season, args.week, args.scoring, player_registry
    )
    _write_bronze(records, args.season, args.week, args.out_root)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
