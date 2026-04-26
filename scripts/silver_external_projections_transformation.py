#!/usr/bin/env python3
"""Silver consolidation CLI for external projections (Phase 73-02)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.external_projections import SilverConsolidator  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("silver_external_projections")


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate external projections to Silver.")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--scoring", choices=["ppr", "half_ppr", "standard"], default="half_ppr")
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze/external_projections"))
    parser.add_argument("--gold-root", type=Path, default=Path("data/gold/projections"))
    parser.add_argument("--silver-root", type=Path, default=Path("data/silver/external_projections"))
    args = parser.parse_args()

    consolidator = SilverConsolidator(
        season=args.season,
        week=args.week,
        scoring_format=args.scoring,
        bronze_root=args.bronze_root,
        gold_root=args.gold_root,
    )
    df = consolidator.consolidate()
    consolidator.write_silver(df, silver_root=args.silver_root)
    logger.info("Silver consolidation complete: %d rows", len(df))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
