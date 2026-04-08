#!/usr/bin/env python3
"""Train and save residual correction models for WR and TE.

Trains Ridge residual models on the production heuristic residuals
and saves them to models/residual/ for use by the ML projection router.

Usage:
    python scripts/train_residual_models.py
    python scripts/train_residual_models.py --positions WR TE
    python scripts/train_residual_models.py --scoring half_ppr
    python scripts/train_residual_models.py --positions wr te --use-graph-features
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hybrid_projection import GRAPH_FEATURE_SET, train_and_save_residual_models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Entry point for residual model training CLI.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        description="Train residual correction models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Baseline training (Silver rolling stats only)
  python scripts/train_residual_models.py --positions WR TE

  # Graph-enhanced training (adds up to 49 graph features per position)
  python scripts/train_residual_models.py --positions WR TE --use-graph-features

  # All positions with graph features
  python scripts/train_residual_models.py --use-graph-features
        """,
    )
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
    parser.add_argument(
        "--use-graph-features",
        action="store_true",
        default=False,
        help=(
            "Explicitly load and merge all Silver graph feature tables "
            f"(up to {len(GRAPH_FEATURE_SET)} features: QB-WR chemistry, "
            "game script, red zone, WR/TE matchup, injury cascade, OL/RB, scheme). "
            "NaN values from missing player-weeks are median-imputed by the pipeline. "
            "When omitted, baseline behavior is preserved."
        ),
    )
    args = parser.parse_args()

    positions = [p.upper() for p in args.positions]
    graph_label = " + graph features" if args.use_graph_features else ""

    print(f"\nTraining Residual Correction Models")
    print(
        f"Positions: {positions} | Scoring: {args.scoring.upper()}{graph_label}"
    )
    if args.use_graph_features:
        print(
            f"Graph features: up to {len(GRAPH_FEATURE_SET)} features from Silver "
            "(QB-WR chemistry, game script, red zone, WR/TE matchup, "
            "injury cascade, OL/RB, scheme)"
        )
    print("=" * 60)

    results = train_and_save_residual_models(
        positions=positions,
        scoring_format=args.scoring,
        use_graph_features=args.use_graph_features,
    )

    if not results:
        print("\nERROR: No models trained.")
        return 1

    print(f"\n{'=' * 60}")
    print("TRAINING RESULTS")
    print(f"{'=' * 60}")
    for pos, info in results.items():
        graph_info = ""
        if args.use_graph_features:
            graph_info = f", graph_features_added={info.get('graph_features_added', 0)}"
        print(
            f"  {pos}: ridge_alpha={info['ridge_alpha']:.3f}, "
            f"n_train={info['n_train']}, features={len(info['features'])}"
            f"{graph_info}"
        )

    print(f"\nModels saved to models/residual/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
