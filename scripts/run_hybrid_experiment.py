#!/usr/bin/env python3
"""Hybrid projection experiment: blend and residual approaches.

Runs two experiments:
1. Simple Blend: alpha * heuristic + (1-alpha) * ML OOF, grid-search alpha per position
2. Residual Model: Ridge trained on (actual - heuristic), walk-forward CV

Reports MAE comparison table for all approaches.

Usage:
    python scripts/run_hybrid_experiment.py
    python scripts/run_hybrid_experiment.py --scoring half_ppr
    python scripts/run_hybrid_experiment.py --positions QB RB WR TE
"""

import argparse
import logging
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS, PLAYER_LABEL_COLUMNS
from hybrid_projection import (
    compute_actual_fantasy_points,
    compute_fantasy_points_from_preds,
    evaluate_blend,
    train_residual_model,
)
from player_feature_engineering import (
    assemble_multiyear_player_features,
    get_player_feature_columns,
)
from player_model_training import (
    PLAYER_VALIDATION_SEASONS,
    generate_heuristic_predictions,
    get_lgb_params_for_stat,
    get_player_model_params,
    get_stat_type,
    make_lgb_model,
    make_xgb_model,
    player_walk_forward_cv,
    _player_lgb_fit_kwargs,
    _player_xgb_fit_kwargs,
)
from projection_engine import POSITION_STAT_PROFILE
from scoring_calculator import calculate_fantasy_points_df

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Import model factories from ensemble_training
from ensemble_training import make_lgb_model, make_xgb_model


def load_feature_selections(output_dir: str = "models/player") -> dict:
    """Load saved SHAP feature selections per stat-type group."""
    import json

    from player_model_training import STAT_TYPE_GROUPS

    fs_dir = os.path.join(output_dir, "feature_selection")
    result = {}
    for group_name in STAT_TYPE_GROUPS.keys():
        path = os.path.join(fs_dir, f"{group_name}_features.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            result[group_name] = data.get("features", [])
    return result


def run_ml_oof_predictions(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols_by_group: dict,
    scoring_format: str = "half_ppr",
    val_seasons: list = None,
) -> pd.DataFrame:
    """Run walk-forward CV for all stats and convert OOF to fantasy points.

    Returns DataFrame with columns:
        idx, season, week, ml_fantasy_pts
    aligned to pos_data rows that appeared in OOF.
    """
    if val_seasons is None:
        val_seasons = [2022, 2023, 2024]

    stats = POSITION_STAT_PROFILE.get(position, [])
    stat_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

    # Week 3-18 filter for evaluation
    stat_data_eval = stat_data[stat_data["week"].between(3, 18)].copy()

    # Collect OOF predictions per stat
    oof_by_stat = {}

    for stat in stats:
        stat_type = get_stat_type(stat)
        feat_cols = feature_cols_by_group.get(stat_type, [])
        available = [f for f in feat_cols if f in stat_data.columns]

        if not available:
            logger.warning("No features for %s/%s", position, stat)
            continue

        clean = stat_data.dropna(subset=[stat]).copy()
        if clean.empty:
            continue

        # XGB walk-forward CV
        xgb_params = get_player_model_params(stat)
        try:
            xgb_wf, xgb_oof = player_walk_forward_cv(
                clean,
                available,
                stat,
                lambda p=xgb_params: make_xgb_model(p),
                fit_kwargs_fn=_player_xgb_fit_kwargs,
                val_seasons=val_seasons,
            )
            logger.info(
                "  %s/%s XGB OOF MAE: %.3f (%d rows)",
                position,
                stat,
                xgb_wf.mean_mae,
                len(xgb_oof),
            )
        except Exception as e:
            logger.warning("XGB CV failed for %s/%s: %s", position, stat, e)
            continue

        if not xgb_oof.empty:
            # Map OOF predictions back by index
            pred_map = dict(zip(xgb_oof["idx"], xgb_oof["oof_prediction"]))
            oof_by_stat[stat] = pred_map

    if not oof_by_stat:
        return pd.DataFrame()

    # Build ML prediction DataFrame for OOF rows
    # Find rows that have predictions for ALL stats
    all_oof_indices = None
    for stat, pred_map in oof_by_stat.items():
        idx_set = set(pred_map.keys())
        if all_oof_indices is None:
            all_oof_indices = idx_set
        else:
            all_oof_indices = all_oof_indices & idx_set

    if not all_oof_indices:
        return pd.DataFrame()

    # Build pred_{stat} columns
    ml_df = stat_data.loc[list(all_oof_indices)].copy()
    for stat, pred_map in oof_by_stat.items():
        ml_df[f"pred_{stat}"] = ml_df.index.map(
            lambda x, pm=pred_map: pm.get(x, np.nan)
        )

    # Convert to fantasy points
    ml_pts = compute_fantasy_points_from_preds(
        ml_df, position, scoring_format, output_col="ml_fantasy_pts"
    )

    result = pd.DataFrame(
        {
            "idx": ml_df.index,
            "season": ml_df["season"].values,
            "week": ml_df["week"].values,
            "ml_fantasy_pts": ml_pts.values,
        }
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="Hybrid projection experiment")
    parser.add_argument(
        "--positions",
        nargs="+",
        default=["QB", "RB", "WR", "TE"],
        help="Positions to evaluate.",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format (default: half_ppr).",
    )
    parser.add_argument(
        "--skip-blend",
        action="store_true",
        help="Skip Approach 1 (simple blend).",
    )
    parser.add_argument(
        "--skip-residual",
        action="store_true",
        help="Skip Approach 2 (residual model).",
    )
    args = parser.parse_args()

    start_time = time.time()
    positions = args.positions
    scoring = args.scoring

    # ------------------------------------------------------------------
    # Step 1: Load data
    # ------------------------------------------------------------------
    logger.info("Loading player feature data...")
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        logger.error("No data assembled. Exiting.")
        sys.exit(1)

    logger.info(
        "Loaded %d player-weeks across %d seasons",
        len(all_data),
        all_data["season"].nunique(),
    )

    feature_cols = get_player_feature_columns(all_data)
    logger.info("Found %d candidate feature columns", len(feature_cols))

    # Load saved feature selections
    feature_cols_by_group = load_feature_selections()
    if not feature_cols_by_group:
        logger.error(
            "No saved feature selections found in models/player/feature_selection/. "
            "Run train_player_models.py first."
        )
        sys.exit(1)

    # Validation seasons for backtest window (2022-2024, matching heuristic backtest)
    val_seasons = [2022, 2023, 2024]

    # ------------------------------------------------------------------
    # Results collection
    # ------------------------------------------------------------------
    results_table = []

    for position in positions:
        print(f"\n{'=' * 60}")
        print(f"  Position: {position}")
        print(f"{'=' * 60}")

        pos_data = all_data[all_data["position"] == position].copy()
        if pos_data.empty:
            logger.warning("No data for %s", position)
            continue

        # Exclude holdout season
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()
        logger.info("%s: %d player-weeks (excl. holdout)", position, len(pos_data))

        # ------------------------------------------------------------------
        # Heuristic baseline (on weeks 3-18 of val seasons)
        # ------------------------------------------------------------------
        heur_df = generate_heuristic_predictions(pos_data, position)
        heur_pts = compute_fantasy_points_from_preds(
            heur_df, position, scoring, output_col="heuristic_pts"
        )
        actual_pts = compute_actual_fantasy_points(
            pos_data, scoring, output_col="actual_pts"
        )

        # Filter to val seasons, weeks 3-18
        eval_mask = pos_data["season"].isin(val_seasons) & pos_data["week"].between(
            3, 18
        )
        valid_mask = eval_mask & heur_pts.notna() & actual_pts.notna()

        heur_mae = float(
            np.mean(np.abs(heur_pts[valid_mask].values - actual_pts[valid_mask].values))
        )
        n_eval = int(valid_mask.sum())
        print(f"  Heuristic MAE: {heur_mae:.3f} ({n_eval} player-weeks)")

        pos_result = {
            "position": position,
            "n_eval": n_eval,
            "heuristic_mae": heur_mae,
            "blend_best_alpha": None,
            "blend_mae": None,
            "residual_mae": None,
            "ml_mae": None,
        }

        # ------------------------------------------------------------------
        # Approach 1: Simple Blend
        # ------------------------------------------------------------------
        if not args.skip_blend:
            print(f"\n  --- Approach 1: Simple Blend ---")
            ml_oof = run_ml_oof_predictions(
                pos_data, position, feature_cols_by_group, scoring, val_seasons
            )

            if ml_oof.empty:
                print("  No ML OOF predictions available. Skipping blend.")
            else:
                # Filter ML OOF to evaluation window
                ml_oof_eval = ml_oof[
                    ml_oof["season"].isin(val_seasons) & ml_oof["week"].between(3, 18)
                ]

                # Align heuristic and actuals to ML OOF indices
                ml_indices = ml_oof_eval["idx"].values
                h_aligned = heur_pts.loc[ml_indices]
                a_aligned = actual_pts.loc[ml_indices]
                m_aligned = ml_oof_eval.set_index("idx")["ml_fantasy_pts"]

                valid = h_aligned.notna() & m_aligned.notna() & a_aligned.notna()
                h_valid = h_aligned[valid]
                m_valid = m_aligned[valid]
                a_valid = a_aligned[valid]

                # ML standalone MAE
                ml_standalone_mae = float(
                    np.mean(np.abs(m_valid.values - a_valid.values))
                )
                print(
                    f"  ML standalone MAE: {ml_standalone_mae:.3f} ({len(h_valid)} rows)"
                )
                pos_result["ml_mae"] = ml_standalone_mae

                # Heuristic MAE on same rows (for fair comparison)
                heur_same_rows_mae = float(
                    np.mean(np.abs(h_valid.values - a_valid.values))
                )
                print(f"  Heuristic MAE (same rows): {heur_same_rows_mae:.3f}")

                # Blend search
                alphas = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
                best_alpha, best_mae, alpha_results = evaluate_blend(
                    h_valid, m_valid, a_valid, alphas
                )

                print(f"  Best blend alpha: {best_alpha:.1f} (MAE: {best_mae:.3f})")
                print(f"  Alpha sweep:")
                for alpha, mae in sorted(alpha_results.items()):
                    marker = " <-- best" if alpha == best_alpha else ""
                    print(f"    alpha={alpha:.1f}: MAE={mae:.3f}{marker}")

                pos_result["blend_best_alpha"] = best_alpha
                pos_result["blend_mae"] = best_mae

        # ------------------------------------------------------------------
        # Approach 2: Residual Model
        # ------------------------------------------------------------------
        if not args.skip_residual:
            print(f"\n  --- Approach 2: Residual Model ---")

            residual_result, residual_oof = train_residual_model(
                pos_data, position, feature_cols, scoring, val_seasons
            )

            if residual_oof.empty:
                print("  Residual model training failed. Skipping.")
            else:
                # Filter to eval window
                residual_eval = residual_oof[
                    residual_oof["season"].isin(val_seasons)
                    & residual_oof["week"].between(3, 18)
                ]

                if residual_eval.empty:
                    print("  No residual OOF in eval window.")
                else:
                    residual_mae = float(
                        np.mean(
                            np.abs(
                                residual_eval["hybrid_pts"].values
                                - residual_eval["actual_pts"].values
                            )
                        )
                    )
                    heur_on_same = float(
                        np.mean(
                            np.abs(
                                residual_eval["heuristic_pts"].values
                                - residual_eval["actual_pts"].values
                            )
                        )
                    )
                    n_residual = len(residual_eval)

                    print(
                        f"  Residual model MAE: {residual_mae:.3f} ({n_residual} rows)"
                    )
                    print(f"  Heuristic MAE (same rows): {heur_on_same:.3f}")
                    improvement = (heur_on_same - residual_mae) / heur_on_same * 100
                    print(f"  Improvement: {improvement:+.1f}%")

                    for fd in residual_result["fold_details"]:
                        print(
                            f"    Season {fd['val_season']}: MAE={fd['mae']:.3f}, "
                            f"Ridge alpha={fd['ridge_alpha']:.3f}, "
                            f"n={fd['val_size']}"
                        )

                    # Mean residual prediction (should be near 0 if well-calibrated)
                    mean_residual = residual_eval["residual_pred"].mean()
                    print(f"  Mean residual prediction: {mean_residual:+.3f}")

                    pos_result["residual_mae"] = residual_mae

        results_table.append(pos_result)

    # ------------------------------------------------------------------
    # Summary Table
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time

    print(f"\n\n{'=' * 80}")
    print(f"  HYBRID PROJECTION EXPERIMENT RESULTS ({scoring.upper()})")
    print(f"{'=' * 80}")
    print(
        f"  {'APPROACH':<16} {'QB MAE':>8} {'RB MAE':>8} {'WR MAE':>8} "
        f"{'TE MAE':>8} {'OVERALL':>8}"
    )
    print(f"  {'-' * 72}")

    # Collect per-position values for each approach
    approaches = {
        "Heuristic": "heuristic_mae",
        "ML Standalone": "ml_mae",
        "Blend (opt)": "blend_mae",
        "Residual": "residual_mae",
    }

    for approach_name, key in approaches.items():
        vals = {}
        weights = {}
        for r in results_table:
            v = r.get(key)
            if v is not None:
                vals[r["position"]] = v
                weights[r["position"]] = r["n_eval"]

        if not vals:
            continue

        # Weighted overall MAE
        total_weight = sum(weights.get(p, 0) for p in vals)
        if total_weight > 0:
            overall = sum(vals[p] * weights.get(p, 0) for p in vals) / total_weight
        else:
            overall = 0.0

        row_parts = [f"  {approach_name:<16}"]
        for pos in ["QB", "RB", "WR", "TE"]:
            if pos in vals:
                row_parts.append(f"{vals[pos]:>8.3f}")
            else:
                row_parts.append(f"{'---':>8}")
        row_parts.append(f"{overall:>8.3f}")
        print(" ".join(row_parts))

    # Print blend alphas
    print(f"\n  Optimal blend alphas:")
    for r in results_table:
        if r.get("blend_best_alpha") is not None:
            print(f"    {r['position']}: alpha={r['blend_best_alpha']:.1f}")

    print(f"\n  Elapsed: {elapsed:.1f}s")
    print(f"{'=' * 80}")

    return results_table


if __name__ == "__main__":
    main()
