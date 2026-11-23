#!/usr/bin/env python3
"""Derive the ppr / standard weekly boards from the published half_ppr board.

Writes ``projections_ppr_<ts>.parquet`` and ``projections_standard_<ts>.parquet``
beside the newest ``projections_half_ppr_<ts>.parquet`` of each week, reusing
its timestamp. See ``src/scoring_derivation.py`` for the math.

Usage:
    python scripts/derive_scoring_boards.py --season 2026 --week 11
    python scripts/derive_scoring_boards.py --season 2026 --all-weeks   # backfill
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path  # noqa: E402

from scoring_derivation import derive_season  # noqa: E402

GOLD_DIR = Path(__file__).resolve().parent.parent / "data" / "gold"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--season", type=int, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int)
    g.add_argument("--all-weeks", action="store_true")
    p.add_argument("--gold-dir", type=Path, default=GOLD_DIR)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    done = derive_season(
        args.gold_dir, args.season, None if args.all_weeks else args.week
    )
    if not done:
        print(f"No half_ppr board found for season={args.season} — nothing derived.")
        return 1
    for wk, paths in sorted(done.items()):
        print(f"week {wk}: " + ", ".join(x.name for x in paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
