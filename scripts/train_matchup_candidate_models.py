#!/usr/bin/env python3
"""Train WR and TE residual candidate models with ELITE-2.3 defense-side trailing features.

Outputs ONLY to models/residual_matchup_candidate/ — NEVER touches the production
models in models/residual/.

Safety:
    - Production models were backed up to models/residual/_matchup_backup/ before
      this script runs.
    - This script CANNOT modify production artifacts; it only reads from them and
      writes to the candidate directory.

Usage:
    python scripts/train_matchup_candidate_models.py
    python scripts/train_matchup_candidate_models.py --shap-features 60
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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATE_DIR = os.path.join(BASE_DIR, "models", "residual_matchup_candidate")
PRODUCTION_DIR = os.path.join(BASE_DIR, "models", "residual")


def main() -> int:
    """Train WR/TE candidate residual models with defense trailing features.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Train WR/TE residual candidates with ELITE-2.3 defense-side trailing "
            "features. Saves to models/residual_matchup_candidate/ ONLY."
        )
    )
    parser.add_argument(
        "--shap-features",
        type=int,
        default=60,
        help="Number of SHAP-selected features (default: 60)",
    )
    parser.add_argument(
        "--training-seasons",
        type=int,
        nargs="+",
        default=None,
        metavar="YEAR",
        help="Override training seasons (default: PLAYER_DATA_SEASONS 2016-2024)",
    )
    args = parser.parse_args()

    os.makedirs(CANDIDATE_DIR, exist_ok=True)

    print("\nTraining WR/TE Residual Candidate Models (ELITE-2.3)")
    print(f"Candidate output: {CANDIDATE_DIR}")
    print(f"Production models (READ-ONLY): {PRODUCTION_DIR}")
    print(f"SHAP feature count: {args.shap_features}")
    print("=" * 65)

    seasons_label = ""
    if args.training_seasons:
        seasons_label = f" | Seasons: {args.training_seasons[0]}-{args.training_seasons[-1]}"
    print(f"Positions: WR, TE | Scoring: HALF_PPR{seasons_label}")
    print("=" * 65)

    results = train_and_save_residual_models(
        positions=["WR", "TE"],
        scoring_format="half_ppr",
        output_dir=CANDIDATE_DIR,
        use_graph_features=True,
        model_type="ridge",
        shap_feature_count=args.shap_features,
        training_seasons=args.training_seasons,
    )

    if not results:
        logger.error("No candidate models trained.")
        return 1

    print(f"\n{'=' * 65}")
    print("CANDIDATE TRAINING RESULTS")
    print(f"{'=' * 65}")
    for pos, info in results.items():
        mtype = info.get("model_type", "ridge")
        n_feats = info.get("n_features", len(info.get("features", [])))
        graph_added = info.get("graph_features_added", 0)
        if mtype == "lgb":
            print(
                f"  {pos}: type={mtype}, n_train={info['n_train']}, "
                f"features={n_feats}, train_mae={info['mae']:.3f}, "
                f"graph_added={graph_added}"
            )
        else:
            print(
                f"  {pos}: type={mtype}, "
                f"ridge_alpha={info.get('ridge_alpha', 0):.3f}, "
                f"n_train={info['n_train']}, features={n_feats}, "
                f"graph_added={graph_added}"
            )

    print(f"\nCandidate models saved to: {CANDIDATE_DIR}")
    print("\nNEXT STEP: Run backtest_projections.py with --candidate-model-dir")
    print("  to compare candidate vs production performance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
