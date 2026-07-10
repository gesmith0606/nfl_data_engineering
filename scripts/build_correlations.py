#!/usr/bin/env python3
"""Build the player correlation network (UC3) and save to Gold.

Computes stability-gated CORRELATES edges from Bronze weekly fantasy
points (2016-2025 pooled) and writes them to
data/gold/correlations/correlations_TIMESTAMP.parquet, where the API
(/api/players/{id}/correlations) and the lineup builder read them.

Usage:
    python scripts/build_correlations.py
    python scripts/build_correlations.py --scoring ppr
"""

import argparse
import datetime
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_correlation import GOLD_CORRELATIONS_DIR, build_correlation_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build stability-gated player correlation edges (UC3)"
    )
    parser.add_argument("--scoring", default="half_ppr")
    args = parser.parse_args()

    edges = build_correlation_data(scoring_format=args.scoring)
    if edges.empty:
        logger.error("No edges computed — check Bronze weekly data availability")
        sys.exit(1)

    os.makedirs(GOLD_CORRELATIONS_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(GOLD_CORRELATIONS_DIR, f"correlations_{ts}.parquet")
    edges.to_parquet(path, index=False)

    pairs = edges[edges["level"] == "pair"]
    priors = edges[edges["level"] == "relation"]
    logger.info(
        "Saved %d stable pair edges + %d relation priors -> %s",
        len(pairs),
        len(priors),
        path,
    )
    for _, row in priors.iterrows():
        logger.info(
            "  prior %-16s rho=%+.3f (train %+.3f / holdout %+.3f, n=%d)",
            row["relation"],
            row["rho"],
            row["rho_train"],
            row["rho_holdout"],
            row["n_games"],
        )


if __name__ == "__main__":
    main()
