#!/usr/bin/env python3
"""Train per-position player stat models and run ship gate evaluation.

Trains XGBoost models for each stat in POSITION_STAT_PROFILE per position,
runs SHAP-based feature selection, generates heuristic baseline predictions
on identical rows, and produces a ship gate report with SHIP/SKIP verdicts.

Usage:
    python scripts/train_player_models.py
    python scripts/train_player_models.py --positions QB WR
    python scripts/train_player_models.py --holdout-eval --scoring half_ppr
    python scripts/train_player_models.py --dry-run
    python scripts/train_player_models.py --skip-feature-selection
"""

import argparse
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS, PLAYER_LABEL_COLUMNS
from player_feature_engineering import (
    assemble_multiyear_player_features,
    detect_leakage,
    get_player_feature_columns,
)
from player_model_training import (
    STAT_TYPE_GROUPS,
    build_ship_gate_report,
    compute_position_mae,
    generate_heuristic_predictions,
    predict_player_stats,
    print_ship_gate_table,
    run_player_feature_selection,
    ship_gate_verdict,
    train_position_models,
)
from projection_engine import POSITION_STAT_PROFILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = "models/player"


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Train per-position player stat models and run ship gate evaluation. "
            "Trains XGBoost models for each stat per position, compares to "
            "heuristic baseline, and produces SHIP/SKIP verdicts."
        ),
    )
    parser.add_argument(
        "--positions",
        nargs="+",
        default=["QB", "RB", "WR", "TE"],
        help="Positions to train (default: QB RB WR TE).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run feature selection only, skip model training.",
    )
    parser.add_argument(
        "--skip-feature-selection",
        action="store_true",
        help="Reuse saved feature selections from models/player/feature_selection/.",
    )
    parser.add_argument(
        "--holdout-eval",
        action="store_true",
        help=f"Evaluate on {HOLDOUT_SEASON} holdout after training (default: OOF only).",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format for ship gate evaluation (default: half_ppr).",
    )
    return parser


def load_saved_features(output_dir: str = OUTPUT_DIR) -> dict:
    """Load previously saved feature selection results.

    Args:
        output_dir: Base model output directory.

    Returns:
        Dict mapping group name to list of feature names.
    """
    fs_dir = os.path.join(output_dir, "feature_selection")
    result = {}
    for group_name in STAT_TYPE_GROUPS.keys():
        path = os.path.join(fs_dir, f"{group_name}_features.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            result[group_name] = data.get("features", [])
            logger.info(
                "Loaded %d saved features for '%s'",
                len(result[group_name]),
                group_name,
            )
        else:
            logger.warning("No saved features found at %s", path)
    return result


def compute_per_stat_mae(
    predictions_df,
    position: str,
    stats: list,
) -> list:
    """Compute per-stat MAE for ML vs actual for safety floor checks.

    Args:
        predictions_df: DataFrame with pred_{stat} and actual stat columns.
        position: Position code.
        stats: List of stat names to evaluate.

    Returns:
        List of dicts with stat, ml_mae keys.
    """
    from sklearn.metrics import mean_absolute_error as sklearn_mae

    results = []
    df = predictions_df.copy()
    if "week" in df.columns:
        df = df[(df["week"] >= 3) & (df["week"] <= 18)]

    for stat in stats:
        pred_col = f"pred_{stat}"
        if pred_col not in df.columns or stat not in df.columns:
            continue
        valid = df[[pred_col, stat]].dropna()
        if valid.empty:
            continue
        mae = float(sklearn_mae(valid[stat], valid[pred_col]))
        results.append({"stat": stat, "ml_mae": mae})
    return results


def compute_heuristic_per_stat_mae(
    heuristic_df,
    position: str,
    stats: list,
) -> dict:
    """Compute per-stat MAE for heuristic predictions.

    Args:
        heuristic_df: DataFrame with pred_{stat} and actual stat columns.
        position: Position code.
        stats: List of stat names.

    Returns:
        Dict mapping stat -> heuristic MAE.
    """
    from sklearn.metrics import mean_absolute_error as sklearn_mae

    result = {}
    df = heuristic_df.copy()
    if "week" in df.columns:
        df = df[(df["week"] >= 3) & (df["week"] <= 18)]

    for stat in stats:
        pred_col = f"pred_{stat}"
        if pred_col not in df.columns or stat not in df.columns:
            continue
        valid = df[[pred_col, stat]].dropna()
        if valid.empty:
            continue
        result[stat] = float(sklearn_mae(valid[stat], valid[pred_col]))
    return result


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    start_time = time.time()
    positions = args.positions
    scoring = args.scoring

    # -----------------------------------------------------------------------
    # Step A: Load data
    # -----------------------------------------------------------------------
    logger.info("Loading player feature data for seasons %s...", PLAYER_DATA_SEASONS)
    try:
        all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    except Exception as e:
        logger.error("Failed to assemble player features: %s", e)
        sys.exit(1)

    if all_data.empty:
        logger.error("No player data assembled. Exiting.")
        sys.exit(1)

    n_seasons = all_data["season"].nunique()
    logger.info("Loaded %d player-weeks across %d seasons", len(all_data), n_seasons)

    # -----------------------------------------------------------------------
    # Step B: Get feature columns
    # -----------------------------------------------------------------------
    feature_cols = get_player_feature_columns(all_data)
    logger.info("Found %d candidate feature columns", len(feature_cols))

    # -----------------------------------------------------------------------
    # Step C: Leakage check
    # -----------------------------------------------------------------------
    leakage_warnings = detect_leakage(all_data, feature_cols, PLAYER_LABEL_COLUMNS)
    if leakage_warnings:
        logger.warning("Leakage detected in %d feature-target pairs:", len(leakage_warnings))
        for feat, target, r in leakage_warnings[:10]:
            logger.warning("  %s <-> %s: r=%.3f", feat, target, r)
    else:
        logger.info("No leakage detected")

    # -----------------------------------------------------------------------
    # Step D: Feature selection
    # -----------------------------------------------------------------------
    if args.skip_feature_selection:
        logger.info("Skipping feature selection, loading saved features...")
        feature_cols_by_group = load_saved_features(OUTPUT_DIR)
        if not feature_cols_by_group:
            logger.error("No saved features found. Run without --skip-feature-selection first.")
            sys.exit(1)
    else:
        logger.info("Running SHAP-based feature selection per stat-type group...")
        feature_cols_by_group = run_player_feature_selection(
            all_data, feature_cols, positions, output_dir=OUTPUT_DIR
        )
        for group, feats in feature_cols_by_group.items():
            logger.info("Selected %d features for %s group", len(feats), group)

    if args.dry_run:
        logger.info("Dry run complete. Feature selection done, skipping training.")
        elapsed = time.time() - start_time
        logger.info("Elapsed: %.1f seconds", elapsed)
        return

    # -----------------------------------------------------------------------
    # Step E: Train and evaluate per position
    # -----------------------------------------------------------------------
    position_results = []

    for position in positions:
        logger.info("=" * 60)
        logger.info("Training position: %s", position)
        logger.info("=" * 60)

        stats = POSITION_STAT_PROFILE.get(position, [])
        if not stats:
            logger.warning("No stats defined for position %s, skipping", position)
            continue

        # Filter to position data
        pos_data = all_data[all_data["position"] == position].copy()
        if pos_data.empty:
            logger.warning("No data for position %s", position)
            continue

        logger.info("Position %s: %d player-weeks", position, len(pos_data))

        # Train all stat models
        try:
            model_results = train_position_models(
                pos_data, position, feature_cols_by_group, output_dir=OUTPUT_DIR
            )
        except Exception as e:
            logger.error("Training failed for %s: %s", position, e)
            position_results.append(
                ship_gate_verdict(position, 0.0, 0.0, 0.0, 0.0, [])
            )
            continue

        if not model_results:
            logger.warning("No models trained for %s", position)
            position_results.append(
                ship_gate_verdict(position, 0.0, 0.0, 0.0, 0.0, [])
            )
            continue

        # Generate OOF ML predictions
        # Reconstruct OOF data by combining per-stat OOF predictions
        oof_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

        # For OOF ML: use the walk-forward OOF predictions stored in model_results
        # Each stat has its own oof_df with idx, oof_prediction columns
        for stat, stat_info in model_results.items():
            oof_df = stat_info.get("oof_df")
            if oof_df is not None and not oof_df.empty:
                # Map OOF predictions back to the position data by index
                pred_map = dict(zip(oof_df["idx"], oof_df["oof_prediction"]))
                oof_data[f"pred_{stat}"] = oof_data.index.map(
                    lambda x, pm=pred_map: pm.get(x, float("nan"))
                )
            else:
                oof_data[f"pred_{stat}"] = float("nan")

        # Generate OOF heuristic predictions on same rows
        heuristic_oof = generate_heuristic_predictions(oof_data, position)

        # Compute OOF MAEs
        oof_ml_mae = compute_position_mae(oof_data, position, scoring_format=scoring)
        oof_heuristic_mae = compute_position_mae(
            heuristic_oof, position, scoring_format=scoring
        )

        logger.info(
            "OOF MAE -- %s: ML=%.3f, Heuristic=%.3f",
            position, oof_ml_mae, oof_heuristic_mae,
        )

        # Per-stat MAE for safety floor (OOF)
        ml_per_stat = compute_per_stat_mae(oof_data, position, stats)
        heuristic_per_stat_maes = compute_heuristic_per_stat_mae(
            heuristic_oof, position, stats
        )

        # Merge per-stat results
        per_stat_results = []
        for sr in ml_per_stat:
            heur_mae = heuristic_per_stat_maes.get(sr["stat"], 0.0)
            per_stat_results.append({
                "stat": sr["stat"],
                "ml_mae": sr["ml_mae"],
                "heuristic_mae": heur_mae,
            })

        # Holdout evaluation
        if args.holdout_eval:
            holdout_data = pos_data[pos_data["season"] == HOLDOUT_SEASON].copy()
            if holdout_data.empty:
                logger.warning(
                    "No holdout data (season=%d) for %s. Using OOF-only verdict.",
                    HOLDOUT_SEASON, position,
                )
                holdout_ml_mae = oof_ml_mae
                holdout_heuristic_mae = oof_heuristic_mae
            else:
                # ML predictions on holdout
                holdout_ml = predict_player_stats(
                    model_results, holdout_data, position, feature_cols_by_group
                )
                holdout_heuristic = generate_heuristic_predictions(
                    holdout_data, position
                )
                holdout_ml_mae = compute_position_mae(
                    holdout_ml, position, scoring_format=scoring
                )
                holdout_heuristic_mae = compute_position_mae(
                    holdout_heuristic, position, scoring_format=scoring
                )
                logger.info(
                    "Holdout MAE -- %s: ML=%.3f, Heuristic=%.3f",
                    position, holdout_ml_mae, holdout_heuristic_mae,
                )
        else:
            # Use OOF as proxy for holdout
            holdout_ml_mae = oof_ml_mae
            holdout_heuristic_mae = oof_heuristic_mae

        # Ship gate verdict
        verdict = ship_gate_verdict(
            position=position,
            ml_mae=holdout_ml_mae,
            heuristic_mae=holdout_heuristic_mae,
            oof_ml_mae=oof_ml_mae,
            oof_heuristic_mae=oof_heuristic_mae,
            per_stat_results=per_stat_results,
        )
        position_results.append(verdict)

        logger.info(
            "Position %s: %s (ML MAE: %.3f, Heuristic MAE: %.3f, Delta: %.1f%%)",
            position,
            verdict["verdict"],
            verdict["ml_mae"],
            verdict["heuristic_mae"],
            verdict["holdout_improvement_pct"],
        )

    # -----------------------------------------------------------------------
    # Step F: Build and print report
    # -----------------------------------------------------------------------
    if position_results:
        report = build_ship_gate_report(position_results, output_dir=OUTPUT_DIR)
        print_ship_gate_table(report)
    else:
        logger.warning("No position results to report")

    elapsed = time.time() - start_time
    logger.info("Total elapsed: %.1f seconds", elapsed)


if __name__ == "__main__":
    main()
