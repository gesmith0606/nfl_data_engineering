#!/usr/bin/env python3
"""Train WR and RB blend-consistent residual models for the WR/RB hybrid retry.

This script is part of the WR_RB_HYBRID_RETRY experiment. It trains Ridge
residual models for WR and RB using the SAME architecture as the TE model
that shipped (blend-consistent, v4.2+blend heuristic_version, ridge type,
60 SHAP-selected features).

Key protocol:
- Training seasons: 2016-2021 ONLY (no peeking at 2022-24 eval window)
- Blend-consistent: weekly_df is loaded and passed to compute_production_heuristic
  so training residuals are computed against the same blended baseline as production
- Same architecture: Ridge, 60 features (same as TE)
- Output dir: worktree-local models/residual/ (does NOT touch main repo)

Usage (from main repo root, with data available):
    python .claude/worktrees/agent-a991417434c43b521/scripts/train_wr_rb_blend_consistent.py
"""

import logging
import os
import sys

# Run from the main repo root so data/ is accessible
_MAIN_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "..")
)
# Resolve to the main repo root
_WORKTREE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# The src/ in the worktree (same code as main repo since worktrees share tracked files)
sys.path.insert(0, os.path.join(_WORKTREE_ROOT, "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Training window: 2016-2021 only (2022-24 is the eval window — no peeking)
TRAINING_SEASONS = [2016, 2017, 2018, 2019, 2020, 2021]

# Output directory: worktree-local to avoid contaminating main repo
OUTPUT_DIR = os.path.join(_WORKTREE_ROOT, "models", "residual")


def main() -> int:
    """Train WR and RB blend-consistent Ridge residual models.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    from hybrid_projection import train_and_save_residual_models

    logger.info("=" * 60)
    logger.info("WR/RB BLEND-CONSISTENT RESIDUAL TRAINING")
    logger.info("Training seasons: %s", TRAINING_SEASONS)
    logger.info("Output dir: %s", OUTPUT_DIR)
    logger.info("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = train_and_save_residual_models(
        positions=["WR", "RB"],
        scoring_format="half_ppr",
        output_dir=OUTPUT_DIR,
        use_graph_features=False,  # Same as TE: graph features NOT explicitly added
        model_type="ridge",        # Same architecture as TE
        shap_feature_count=60,     # Same feature count as TE
        training_seasons=TRAINING_SEASONS,
    )

    if not results:
        logger.error("No models trained — check data availability")
        return 1

    logger.info("=" * 60)
    logger.info("TRAINING RESULTS")
    logger.info("=" * 60)
    for pos, info in results.items():
        logger.info(
            "%s: type=%s, ridge_alpha=%.4f, n_train=%d, features=%d, "
            "heuristic_version=blend-consistent",
            pos,
            info.get("model_type", "ridge"),
            info.get("ridge_alpha", 0.0),
            info.get("n_train", 0),
            info.get("n_features", len(info.get("features", []))),
        )

    logger.info("Models saved to %s", OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
