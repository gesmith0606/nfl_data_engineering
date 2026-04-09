#!/usr/bin/env python3
"""Train and evaluate Bayesian hierarchical residual models.

Walk-forward CV evaluation + optional production model training.

Usage:
    # Walk-forward CV evaluation (compare to heuristic/Ridge/LGB)
    python scripts/train_bayesian_models.py --evaluate

    # Train and save production models
    python scripts/train_bayesian_models.py

    # Specific positions
    python scripts/train_bayesian_models.py --positions WR TE --evaluate

    # With graph features
    python scripts/train_bayesian_models.py --use-graph-features --evaluate
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bayesian_projection import (
    train_and_save_bayesian_models,
    train_bayesian_residual,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_evaluation(
    positions: list,
    scoring_format: str,
    use_graph_features: bool,
    shap_features: int,
) -> dict:
    """Run walk-forward CV evaluation for Bayesian models.

    Args:
        positions: List of position codes.
        scoring_format: Scoring format string.
        use_graph_features: Whether to include graph features.
        shap_features: Number of SHAP features to select.

    Returns:
        Dict mapping position -> evaluation results.
    """
    from config import PLAYER_DATA_SEASONS
    from hybrid_projection import GRAPH_FEATURE_SET, load_graph_features
    from player_feature_engineering import (
        assemble_multiyear_player_features,
        get_player_feature_columns,
    )

    logger.info("Loading player feature data for evaluation...")
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        logger.error("No data assembled")
        return {}

    if use_graph_features:
        logger.info("Loading graph features...")
        graph_df = load_graph_features(PLAYER_DATA_SEASONS)
        if not graph_df.empty:
            join_keys = ["player_id", "season", "week"]
            existing_cols = set(all_data.columns)
            new_cols = [
                c
                for c in graph_df.columns
                if c not in join_keys and c not in existing_cols
            ]
            if new_cols:
                all_data = all_data.merge(
                    graph_df[join_keys + new_cols], on=join_keys, how="left"
                )

    feature_cols = get_player_feature_columns(all_data)
    logger.info("Found %d candidate features", len(feature_cols))

    results = {}
    for position in positions:
        logger.info("Evaluating Bayesian model for %s...", position)
        pos_data = all_data[all_data["position"] == position].copy()

        if pos_data.empty:
            logger.warning("No data for %s", position)
            continue

        eval_results, oof_df = train_bayesian_residual(
            pos_data=pos_data,
            position=position,
            feature_cols=feature_cols,
            scoring_format=scoring_format,
            val_seasons=[2022, 2023, 2024],
            shap_feature_count=shap_features,
        )

        results[position] = {
            "eval": eval_results,
            "oof_size": len(oof_df),
        }

        # Also compute heuristic-only MAE for comparison
        if not oof_df.empty:
            from sklearn.metrics import mean_absolute_error

            heur_mae = float(
                mean_absolute_error(oof_df["actual_pts"], oof_df["heuristic_pts"])
            )
            results[position]["heuristic_mae"] = heur_mae

    return results


def main() -> int:
    """Entry point for Bayesian model training/evaluation CLI.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        description="Train/evaluate Bayesian hierarchical residual models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Walk-forward CV evaluation
  python scripts/train_bayesian_models.py --evaluate

  # Train production models
  python scripts/train_bayesian_models.py

  # Both evaluation and training
  python scripts/train_bayesian_models.py --evaluate --train
        """,
    )
    parser.add_argument(
        "--positions",
        nargs="+",
        default=["QB", "RB", "WR", "TE"],
        help="Positions to train/evaluate (default: QB RB WR TE)",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        default=False,
        help="Run walk-forward CV evaluation",
    )
    parser.add_argument(
        "--train",
        action="store_true",
        default=False,
        help="Train and save production models",
    )
    parser.add_argument(
        "--shap-features",
        type=int,
        default=60,
        help="Number of SHAP-selected features (default: 60)",
    )
    parser.add_argument(
        "--use-graph-features",
        action="store_true",
        default=False,
        help="Include graph features in training data",
    )
    args = parser.parse_args()

    positions = [p.upper() for p in args.positions]

    # If neither --evaluate nor --train, default to --train
    if not args.evaluate and not args.train:
        args.train = True

    graph_label = " + graph features" if args.use_graph_features else ""

    print(f"\nBayesian Hierarchical Residual Models")
    print(f"Positions: {positions} | Scoring: {args.scoring.upper()}{graph_label}")
    print(f"SHAP feature count: {args.shap_features}")
    print("=" * 60)

    if args.evaluate:
        print("\n--- Walk-Forward CV Evaluation ---\n")
        eval_results = run_evaluation(
            positions=positions,
            scoring_format=args.scoring,
            use_graph_features=args.use_graph_features,
            shap_features=args.shap_features,
        )

        if eval_results:
            print(f"\n{'=' * 70}")
            print("EVALUATION RESULTS (Walk-Forward CV, Weeks 3-18)")
            print(f"{'=' * 70}")
            print(
                f"{'Pos':<5} {'Bayes MAE':>10} {'Heur MAE':>10} "
                f"{'Improve':>10} {'Calib 80%':>10} {'Width':>8}"
            )
            print("-" * 55)

            for pos in positions:
                if pos not in eval_results:
                    continue
                info = eval_results[pos]
                ev = info["eval"]
                bayes_mae = ev.get("mean_mae", 0.0)
                heur_mae = info.get("heuristic_mae", 0.0)
                improvement = (
                    (heur_mae - bayes_mae) / heur_mae * 100
                    if heur_mae > 0
                    else 0.0
                )
                calibration = ev.get("mean_calibration_80", 0.0)
                mean_width = (
                    float(
                        sum(f["mean_interval_width"] for f in ev["fold_details"])
                        / len(ev["fold_details"])
                    )
                    if ev["fold_details"]
                    else 0.0
                )

                print(
                    f"{pos:<5} {bayes_mae:>10.3f} {heur_mae:>10.3f} "
                    f"{improvement:>9.1f}% {calibration * 100:>9.1f}% {mean_width:>8.2f}"
                )

                # Per-fold details
                for fd in ev.get("fold_details", []):
                    print(
                        f"  fold {fd['val_season']}: MAE={fd['mae']:.3f}, "
                        f"calib={fd['calibration_80'] * 100:.1f}%, "
                        f"width={fd['mean_interval_width']:.2f}, "
                        f"sigma={fd['noise_sigma']:.3f}"
                    )

            print(f"\n{'=' * 70}")

    if args.train:
        print("\n--- Training Production Models ---\n")
        train_results = train_and_save_bayesian_models(
            positions=positions,
            scoring_format=args.scoring,
            use_graph_features=args.use_graph_features,
            shap_feature_count=args.shap_features,
        )

        if train_results:
            print(f"\n{'=' * 60}")
            print("TRAINING RESULTS")
            print(f"{'=' * 60}")
            for pos, info in train_results.items():
                print(
                    f"  {pos}: MAE={info['mae']:.3f}, "
                    f"features={info['n_features']}, "
                    f"n_train={info['n_train']}, "
                    f"sigma={info['noise_sigma']:.3f}"
                )
            print(f"\nModels saved to models/bayesian/")
        else:
            print("\nERROR: No models trained.")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
