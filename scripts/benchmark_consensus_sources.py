#!/usr/bin/env python3
"""Benchmark our projections against multiple external sources.

Reuses the projections + actuals from an existing ``backtest_projections.py``
run (the canonical v4.3 production backtest CSV) and joins each requested
external source's Silver projections onto the SAME rows, so every source is
compared under identical conditions: same our-projections, same actuals, same
matched-population rules (weeks 3-18, QB/RB/WR/TE, consensus >= 5 pts) as the
published Sleeper benchmark.

Usage::

    python scripts/benchmark_consensus_sources.py \\
        --backtest-csv output/backtest/backtest_half_ppr_ml_fullfeatures_consensus_20260612_141246.csv \\
        --sources espn sleeper --scoring half_ppr \\
        --json-out output/backtest/consensus_benchmark_summary.json

Outputs a per-source head-to-head report, per-source matched CSVs, and a
JSON summary suitable for the website's model-metrics generation.
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict

import numpy as np
import pandas as pd

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPTS_DIR, "..")
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))
sys.path.insert(0, _SCRIPTS_DIR)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from backtest_projections import (  # noqa: E402
    join_consensus,
    load_consensus_for_seasons,
    print_consensus_report,
)
from consensus_metrics import (  # noqa: E402
    CONSENSUS_POSITIONS,
    apply_consensus_filter,
    build_position_table,
)


def _latest_backtest_csv(output_dir: str) -> str:
    """Return the most recent full backtest CSV containing consensus rows."""
    pattern = os.path.join(output_dir, "backtest_*consensus_*.csv")
    files = sorted(globmod.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No backtest CSV matching {pattern}. Run "
            "backtest_projections.py --vs-consensus first."
        )
    return files[-1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Head-to-head benchmark vs multiple external projection sources."
    )
    parser.add_argument(
        "--backtest-csv",
        default=None,
        help=(
            "Existing backtest CSV with projected_points + actual_points "
            "(default: latest backtest_*consensus_*.csv in --output-dir)."
        ),
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["espn"],
        choices=["sleeper", "espn", "yahoo_proxy_fp"],
        help="External sources to benchmark against.",
    )
    parser.add_argument("--scoring", default="half_ppr")
    parser.add_argument(
        "--silver-root",
        default=os.path.join(_PROJECT_ROOT, "data", "silver", "external_projections"),
    )
    parser.add_argument("--output-dir", default="output/backtest")
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path for the JSON summary across sources.",
    )
    args = parser.parse_args()

    csv_path = args.backtest_csv or _latest_backtest_csv(args.output_dir)
    logger.info("Loading backtest results: %s", csv_path)
    results = pd.read_csv(csv_path)
    # Drop any consensus column carried from the original run — each source
    # gets a fresh join below.
    results = results.drop(columns=["consensus_proj"], errors="ignore")

    required = {"player_id", "player_name", "season", "week", "position",
                "projected_points", "actual_points"}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"Backtest CSV missing columns: {sorted(missing)}")

    seasons = sorted(int(s) for s in results["season"].unique())
    results_filtered = results[
        (results["week"] >= 3)
        & (results["week"] <= 18)
        & (results["position"].isin(CONSENSUS_POSITIONS))
    ].copy()
    logger.info(
        "Backtest rows: %d total, %d in eval window (seasons %s)",
        len(results),
        len(results_filtered),
        seasons,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary: Dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backtest_csv": os.path.basename(csv_path),
        "scoring": args.scoring,
        "seasons": seasons,
        "population": "weeks 3-18, QB/RB/WR/TE, source projection >= 5 pts, matched player-weeks",
        "sources": {},
    }

    for source in args.sources:
        print(f"\n{'=' * 72}\nBENCHMARK VS: {source.upper()}\n{'=' * 72}")
        consensus_df = load_consensus_for_seasons(
            seasons=seasons,
            weeks=list(range(3, 19)),
            scoring_format=args.scoring,
            silver_root=args.silver_root,
            source=source,
        )
        if consensus_df.empty:
            print(f"WARNING: no Silver rows for source={source} — skipping.")
            continue
        # Rows without a resolved player_id would collide on the empty-string
        # sentinel during the id join; drop them (name-fallback join inside
        # join_consensus only triggers when the id join yields zero matches).
        consensus_df = consensus_df[
            consensus_df["player_id"].astype(str).str.strip() != ""
        ]
        matched = join_consensus(results_filtered, consensus_df)
        if matched.empty:
            print(f"WARNING: 0 matched player-weeks for source={source}.")
            continue

        print_consensus_report(matched, args.scoring, source_label=source.capitalize())

        out_csv = os.path.join(
            args.output_dir, f"consensus_matched_{source}_{args.scoring}_{ts}.csv"
        )
        matched.to_csv(out_csv, index=False)
        print(f"Matched rows saved to: {out_csv}")

        table = build_position_table(apply_consensus_filter(matched))
        summary["sources"][source] = {
            "matched_csv": os.path.basename(out_csv),
            "positions": [
                {k: (None if isinstance(v, float) and np.isnan(v) else v)
                 for k, v in row.items()}
                for row in table
            ],
        }

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(summary, fh, indent=2)
        print(f"\nJSON summary written to: {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
