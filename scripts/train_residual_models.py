#!/usr/bin/env python3
"""Train and save residual correction models for WR and TE.

Trains Ridge residual models on the production heuristic residuals
and saves them to models/residual/ for use by the ML projection router.

Usage:
    python scripts/train_residual_models.py
    python scripts/train_residual_models.py --positions WR TE
    python scripts/train_residual_models.py --scoring half_ppr
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hybrid_projection import train_and_save_residual_models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Train residual correction models")
    parser.add_argument(
        "--positions",
        nargs="+",
        default=["QB", "RB", "WR", "TE"],
        help="Positions to train (default: QB RB WR TE)",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    args = parser.parse_args()

    print(f"\nTraining Residual Correction Models")
    print(f"Positions: {args.positions} | Scoring: {args.scoring.upper()}")
    print("=" * 60)

    results = train_and_save_residual_models(
        positions=args.positions,
        scoring_format=args.scoring,
    )

    if not results:
        print("\nERROR: No models trained.")
        return 1

    print(f"\n{'=' * 60}")
    print("TRAINING RESULTS")
    print(f"{'=' * 60}")
    for pos, info in results.items():
        print(
            f"  {pos}: ridge_alpha={info['ridge_alpha']:.3f}, "
            f"n_train={info['n_train']}, features={len(info['features'])}"
        )

    print(f"\nModels saved to models/residual/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
