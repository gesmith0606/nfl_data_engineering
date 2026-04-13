#!/usr/bin/env python3
"""Train and save residual correction models for all positions.

Supports two model types:
    - lgb (default): LightGBM with SHAP feature selection + early stopping
    - ridge: RidgeCV pipeline (original approach)

Usage:
    python scripts/train_residual_models.py
    python scripts/train_residual_models.py --positions WR TE
    python scripts/train_residual_models.py --model-type ridge
    python scripts/train_residual_models.py --shap-features 80
    python scripts/train_residual_models.py --use-graph-features
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
  # Default: LightGBM with 60 SHAP-selected features
  python scripts/train_residual_models.py

  # Ridge baseline (original approach)
  python scripts/train_residual_models.py --model-type ridge

  # LightGBM with more features
  python scripts/train_residual_models.py --shap-features 80

  # With explicit graph feature merging
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
        "--model-type",
        default="lgb",
        choices=["lgb", "ridge"],
        help="Model type: lgb (LightGBM + SHAP, default) or ridge (RidgeCV)",
    )
    parser.add_argument(
        "--shap-features",
        type=int,
        default=60,
        help="Number of SHAP-selected features for LGB models (default: 60)",
    )
    parser.add_argument(
        "--use-graph-features",
        action="store_true",
        default=False,
        help=(
            "Explicitly load and merge all Silver graph feature tables "
            f"(up to {len(GRAPH_FEATURE_SET)} features). "
            "When omitted, baseline behavior is preserved."
        ),
    )
    parser.add_argument(
        "--training-seasons",
        type=int,
        nargs="+",
        default=None,
        metavar="YEAR",
        help=(
            "Explicit list of seasons to use for training (e.g., 2018 2019 "
            "... 2024). Defaults to PLAYER_DATA_SEASONS (2016-2024). Use to "
            "test restricted windows that drop older, potentially noisy data."
        ),
    )
    args = parser.parse_args()

    positions = [p.upper() for p in args.positions]
    model_label = "LightGBM + SHAP" if args.model_type == "lgb" else "RidgeCV"
    graph_label = " + graph features" if args.use_graph_features else ""
    seasons_label = (
        f" | Seasons: {args.training_seasons[0]}-{args.training_seasons[-1]}"
        if args.training_seasons
        else ""
    )

    print(f"\nTraining Residual Correction Models ({model_label})")
    print(
        f"Positions: {positions} | Scoring: {args.scoring.upper()}"
        f"{graph_label}{seasons_label}"
    )
    if args.model_type == "lgb":
        print(f"SHAP feature count: {args.shap_features}")
    print("=" * 60)

    results = train_and_save_residual_models(
        positions=positions,
        scoring_format=args.scoring,
        use_graph_features=args.use_graph_features,
        model_type=args.model_type,
        shap_feature_count=args.shap_features,
        training_seasons=args.training_seasons,
    )

    if not results:
        print("\nERROR: No models trained.")
        return 1

    print(f"\n{'=' * 60}")
    print("TRAINING RESULTS")
    print(f"{'=' * 60}")
    for pos, info in results.items():
        mtype = info.get("model_type", "ridge")
        n_feats = info.get("n_features", len(info.get("features", [])))
        graph_info = ""
        if args.use_graph_features:
            graph_info = (
                f", graph_added={info.get('graph_features_added', 0)}"
            )
        if mtype == "lgb":
            print(
                f"  {pos}: type={mtype}, n_train={info['n_train']}, "
                f"features={n_feats}, train_mae={info['mae']:.3f}"
                f"{graph_info}"
            )
        else:
            print(
                f"  {pos}: type={mtype}, "
                f"ridge_alpha={info.get('ridge_alpha', 0):.3f}, "
                f"n_train={info['n_train']}, features={n_feats}"
                f"{graph_info}"
            )

    print(f"\nModels saved to models/residual/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
