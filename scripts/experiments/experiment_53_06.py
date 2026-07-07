#!/usr/bin/env python3
"""Phase 53-06 Experiment: Three paths to improve fantasy projection MAE.

Path 1: Full-feature residual (466 features) vs basic Silver (42 features)
Path 2: Residual correction for QB and RB (same approach as WR/TE)
Path 3: Heuristic weight grid search (RECENCY_WEIGHTS tuning)

Baseline: Overall MAE 4.79 (QB 6.58, RB 5.06, WR 4.63, TE 3.58)

Usage:
    python scripts/experiment_53_06.py
    python scripts/experiment_53_06.py --path 1
    python scripts/experiment_53_06.py --path 2
    python scripts/experiment_53_06.py --path 3
"""

import argparse
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS
from player_feature_engineering import (
    assemble_multiyear_player_features,
    get_player_feature_columns,
)
from projection_engine import (
    POSITION_STAT_PROFILE,
    PROJECTION_CEILING_SHRINKAGE,
    RECENCY_WEIGHTS,
    _matchup_factor,
    _usage_multiplier,
    _weighted_baseline,
)
from scoring_calculator import calculate_fantasy_points_df

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def load_data_and_rankings():
    """Load full feature data and opponent rankings."""
    logger.info("Loading player feature data...")
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        logger.error("No data assembled. Exiting.")
        sys.exit(1)

    logger.info(
        "Loaded %d player-weeks, %d columns", len(all_data), len(all_data.columns)
    )

    feature_cols = get_player_feature_columns(all_data)
    logger.info("Found %d candidate feature columns", len(feature_cols))

    # Build opponent rankings
    from run_production_residual_experiment import build_opp_rankings_from_features

    opp_rankings = build_opp_rankings_from_features(all_data)

    return all_data, feature_cols, opp_rankings


def compute_production_heuristic(
    pos_data: pd.DataFrame,
    position: str,
    opp_rankings: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.Series:
    """Reproduce the production heuristic pipeline."""
    stat_cols = POSITION_STAT_PROFILE.get(position, [])
    if not stat_cols:
        return pd.Series(np.nan, index=pos_data.index)

    work = pos_data.copy()
    work = work.drop(columns=["opp_rank"], errors="ignore")

    usage_mult = _usage_multiplier(work, position)
    matchup = _matchup_factor(work, opp_rankings, position)

    rename_map = {}
    proj_cols = {}
    for stat in stat_cols:
        baseline = _weighted_baseline(work, stat)
        proj_val = (baseline * usage_mult * matchup).round(2)
        proj_col = f"proj_{stat}"
        proj_cols[proj_col] = proj_val
        rename_map[proj_col] = stat

    work = work.assign(**proj_cols)
    orig_cols = [v for v in rename_map.values() if v in work.columns]
    scoring_input = work.drop(columns=orig_cols, errors="ignore")
    scoring_input = scoring_input.rename(columns=rename_map).reset_index(drop=True)
    scoring_input = calculate_fantasy_points_df(
        scoring_input, scoring_format=scoring_format, output_col="projected_points"
    )

    pts = scoring_input["projected_points"]
    shrink = pd.Series(1.0, index=scoring_input.index)
    for threshold in sorted(PROJECTION_CEILING_SHRINKAGE.keys()):
        factor = PROJECTION_CEILING_SHRINKAGE[threshold]
        shrink = shrink.where(pts < threshold, factor)
    scoring_input["projected_points"] = (pts * shrink).round(2)

    result = scoring_input["projected_points"]
    result.index = pos_data.index
    return result


def compute_actual_points(
    df: pd.DataFrame, scoring_format: str = "half_ppr"
) -> pd.Series:
    """Compute actual fantasy points."""
    work = calculate_fantasy_points_df(
        df.copy(), scoring_format=scoring_format, output_col="actual_pts"
    )
    return work["actual_pts"]


def compute_custom_heuristic(
    pos_data: pd.DataFrame,
    position: str,
    opp_rankings: pd.DataFrame,
    scoring_format: str,
    roll3_w: float,
    roll6_w: float,
    std_w: float,
) -> pd.Series:
    """Heuristic with custom recency weights."""
    stat_cols = POSITION_STAT_PROFILE.get(position, [])
    if not stat_cols:
        return pd.Series(np.nan, index=pos_data.index)

    work = pos_data.copy()
    work = work.drop(columns=["opp_rank"], errors="ignore")

    usage_mult = _usage_multiplier(work, position)
    matchup = _matchup_factor(work, opp_rankings, position)

    weights = {"roll3": roll3_w, "roll6": roll6_w, "std": std_w}

    rename_map = {}
    proj_cols = {}
    for stat in stat_cols:
        result = pd.Series(0.0, index=work.index)
        total_weight = 0.0
        for suffix, weight in weights.items():
            col = f"{stat}_{suffix}"
            if col in work.columns:
                result += work[col].fillna(0) * weight
                total_weight += weight
        if total_weight > 0:
            result /= total_weight

        proj_val = (result * usage_mult * matchup).round(2)
        proj_col = f"proj_{stat}"
        proj_cols[proj_col] = proj_val
        rename_map[proj_col] = stat

    work = work.assign(**proj_cols)
    orig_cols = [v for v in rename_map.values() if v in work.columns]
    scoring_input = work.drop(columns=orig_cols, errors="ignore")
    scoring_input = scoring_input.rename(columns=rename_map).reset_index(drop=True)
    scoring_input = calculate_fantasy_points_df(
        scoring_input, scoring_format=scoring_format, output_col="projected_points"
    )

    pts = scoring_input["projected_points"]
    shrink = pd.Series(1.0, index=scoring_input.index)
    for threshold in sorted(PROJECTION_CEILING_SHRINKAGE.keys()):
        factor = PROJECTION_CEILING_SHRINKAGE[threshold]
        shrink = shrink.where(pts < threshold, factor)
    scoring_input["projected_points"] = (pts * shrink).round(2)

    result_pts = scoring_input["projected_points"]
    result_pts.index = pos_data.index
    return result_pts


# ---------------------------------------------------------------------------
# Path 1: Full-feature residual in backtest
# ---------------------------------------------------------------------------


def run_path1(all_data, feature_cols, opp_rankings, scoring="half_ppr"):
    """Test full features vs basic Silver features for residual correction."""
    print("\n" + "=" * 70)
    print("  PATH 1: FULL-FEATURE RESIDUAL vs BASIC SILVER")
    print("=" * 70)

    val_seasons = [2022, 2023, 2024]

    # Identify basic Silver features (the ~42 from usage/rolling)
    basic_features = [
        f
        for f in feature_cols
        if any(
            f.endswith(s)
            for s in ["_roll3", "_roll6", "_std"]
        )
        and not any(
            f.startswith(p)
            for p in [
                "ngs_",
                "pfr_",
                "qbr_",
                "def_",
                "off_",
                "draft",
                "cb_",
                "te_",
                "wr_",
                "rb_",
                "ol_",
                "qb_",
            ]
        )
    ]
    basic_features = [f for f in basic_features if f in all_data.columns]

    logger.info("Basic Silver features: %d", len(basic_features))
    logger.info("Full features: %d", len(feature_cols))

    results = []
    for position in ["WR", "TE"]:
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

        prod_pts = compute_production_heuristic(pos_data, position, opp_rankings, scoring)
        actual_pts = compute_actual_points(pos_data, scoring)

        for label, features in [
            ("basic_42", basic_features),
            ("full_466", feature_cols),
        ]:
            available = [f for f in features if f in pos_data.columns]
            fold_maes_heur = []
            fold_maes_hybrid = []

            for val_season in val_seasons:
                week_mask = pos_data["week"].between(3, 18)
                train_mask = (pos_data["season"] < val_season) & week_mask
                val_mask = (pos_data["season"] == val_season) & week_mask

                train_idx = pos_data.index[train_mask]
                val_idx = pos_data.index[val_mask]

                if len(train_idx) < 50 or len(val_idx) < 10:
                    continue

                train_residual = actual_pts.loc[train_idx] - prod_pts.loc[train_idx]
                train_valid = train_residual.notna()
                val_valid = prod_pts.loc[val_idx].notna() & actual_pts.loc[val_idx].notna()

                train_idx_v = train_idx[train_valid.loc[train_idx].values]
                val_idx_v = val_idx[val_valid.loc[val_idx].values]

                if len(train_idx_v) < 50 or len(val_idx_v) < 10:
                    continue

                X_train = pos_data.loc[train_idx_v, available]
                y_train = train_residual.loc[train_idx_v]
                X_val = pos_data.loc[val_idx_v, available]

                model = Pipeline([
                    ("imputer", SimpleImputer(strategy="median")),
                    ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
                ])
                model.fit(X_train, y_train)

                residual_pred = model.predict(X_val)
                hybrid_pts = prod_pts.loc[val_idx_v].values + residual_pred
                actual_val = actual_pts.loc[val_idx_v].values
                heur_val = prod_pts.loc[val_idx_v].values

                fold_maes_heur.append(mean_absolute_error(actual_val, heur_val))
                fold_maes_hybrid.append(mean_absolute_error(actual_val, hybrid_pts))

            mean_heur = np.mean(fold_maes_heur) if fold_maes_heur else 0
            mean_hybrid = np.mean(fold_maes_hybrid) if fold_maes_hybrid else 0
            improvement = (mean_heur - mean_hybrid) / mean_heur * 100 if mean_heur > 0 else 0

            results.append({
                "position": position,
                "feature_set": label,
                "n_features": len(available),
                "heur_mae": mean_heur,
                "hybrid_mae": mean_hybrid,
                "improvement_pct": improvement,
            })

            print(
                f"  {position} {label:>10}: {len(available):>3} features | "
                f"Heur MAE={mean_heur:.3f} | Hybrid MAE={mean_hybrid:.3f} | "
                f"Improvement={improvement:+.1f}%"
            )

    return results


# ---------------------------------------------------------------------------
# Path 2: Residual correction for QB and RB
# ---------------------------------------------------------------------------


def run_path2(all_data, feature_cols, opp_rankings, scoring="half_ppr"):
    """Test residual correction for QB and RB."""
    print("\n" + "=" * 70)
    print("  PATH 2: RESIDUAL CORRECTION FOR QB AND RB")
    print("=" * 70)

    val_seasons = [2022, 2023, 2024]
    available_features = [f for f in feature_cols if f in all_data.columns]

    results = []
    for position in ["QB", "RB", "WR", "TE"]:
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

        if pos_data.empty:
            continue

        prod_pts = compute_production_heuristic(pos_data, position, opp_rankings, scoring)
        actual_pts = compute_actual_points(pos_data, scoring)

        fold_maes_heur = []
        fold_maes_hybrid = []
        fold_details = []

        for val_season in val_seasons:
            week_mask = pos_data["week"].between(3, 18)
            train_mask = (pos_data["season"] < val_season) & week_mask
            val_mask = (pos_data["season"] == val_season) & week_mask

            train_idx = pos_data.index[train_mask]
            val_idx = pos_data.index[val_mask]

            if len(train_idx) < 50 or len(val_idx) < 10:
                continue

            train_residual = actual_pts.loc[train_idx] - prod_pts.loc[train_idx]
            train_valid = train_residual.notna()
            val_valid = prod_pts.loc[val_idx].notna() & actual_pts.loc[val_idx].notna()

            train_idx_v = train_idx[train_valid.loc[train_idx].values]
            val_idx_v = val_idx[val_valid.loc[val_idx].values]

            if len(train_idx_v) < 50 or len(val_idx_v) < 10:
                continue

            X_train = pos_data.loc[train_idx_v, available_features]
            y_train = train_residual.loc[train_idx_v]
            X_val = pos_data.loc[val_idx_v, available_features]

            model = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
            ])
            model.fit(X_train, y_train)

            residual_pred = model.predict(X_val)
            hybrid_pts = prod_pts.loc[val_idx_v].values + residual_pred
            actual_val = actual_pts.loc[val_idx_v].values
            heur_val = prod_pts.loc[val_idx_v].values

            h_mae = float(mean_absolute_error(actual_val, heur_val))
            hy_mae = float(mean_absolute_error(actual_val, hybrid_pts))
            fold_maes_heur.append(h_mae)
            fold_maes_hybrid.append(hy_mae)
            fold_details.append({
                "val_season": val_season,
                "heur_mae": h_mae,
                "hybrid_mae": hy_mae,
                "ridge_alpha": float(model.named_steps["model"].alpha_),
                "mean_correction": float(np.mean(residual_pred)),
                "n": len(val_idx_v),
            })

        mean_heur = np.mean(fold_maes_heur) if fold_maes_heur else 0
        mean_hybrid = np.mean(fold_maes_hybrid) if fold_maes_hybrid else 0
        improvement = (mean_heur - mean_hybrid) / mean_heur * 100 if mean_heur > 0 else 0
        decision = "SHIP" if improvement > 0 else "SKIP"

        results.append({
            "position": position,
            "heur_mae": mean_heur,
            "hybrid_mae": mean_hybrid,
            "improvement_pct": improvement,
            "decision": decision,
            "fold_details": fold_details,
        })

        print(f"\n  {position}: Heur MAE={mean_heur:.3f} | Hybrid MAE={mean_hybrid:.3f} | "
              f"Improvement={improvement:+.1f}% -> {decision}")
        for fd in fold_details:
            print(f"    {fd['val_season']}: Heur={fd['heur_mae']:.3f} Hybrid={fd['hybrid_mae']:.3f} "
                  f"alpha={fd['ridge_alpha']:.3f} mean_corr={fd['mean_correction']:+.3f} n={fd['n']}")

    return results


# ---------------------------------------------------------------------------
# Path 3: Heuristic weight grid search
# ---------------------------------------------------------------------------


def run_path3(all_data, feature_cols, opp_rankings, scoring="half_ppr"):
    """Grid search on RECENCY_WEIGHTS."""
    print("\n" + "=" * 70)
    print("  PATH 3: HEURISTIC WEIGHT GRID SEARCH")
    print("=" * 70)

    val_seasons = [2022, 2023, 2024]

    # Current baseline
    current_roll3 = RECENCY_WEIGHTS["roll3"]
    current_roll6 = RECENCY_WEIGHTS["roll6"]
    current_std = RECENCY_WEIGHTS["std"]
    print(f"  Current weights: roll3={current_roll3}, roll6={current_roll6}, std={current_std}")

    # Grid
    roll3_values = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    roll6_values = [0.20, 0.25, 0.30, 0.35]

    positions = ["QB", "RB", "WR", "TE"]

    # Pre-compute actual points per position once
    pos_actual = {}
    pos_data_dict = {}
    for position in positions:
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()
        pos_data_dict[position] = pos_data
        pos_actual[position] = compute_actual_points(pos_data, scoring)

    grid_results = []
    best_overall_mae = float("inf")
    best_config = None

    for roll3_w in roll3_values:
        for roll6_w in roll6_values:
            std_w = 1.0 - roll3_w - roll6_w
            if std_w < 0.05 or std_w > 0.45:
                continue

            total_weighted_mae = 0.0
            total_n = 0
            pos_maes = {}

            for position in positions:
                pos_data = pos_data_dict[position]
                actual_pts = pos_actual[position]

                proj_pts = compute_custom_heuristic(
                    pos_data, position, opp_rankings, scoring,
                    roll3_w, roll6_w, std_w,
                )

                # Evaluate on val_seasons, weeks 3-18
                eval_mask = (
                    pos_data["season"].isin(val_seasons)
                    & pos_data["week"].between(3, 18)
                    & proj_pts.notna()
                    & actual_pts.notna()
                )
                n_eval = int(eval_mask.sum())

                if n_eval > 0:
                    mae = float(
                        np.mean(
                            np.abs(
                                proj_pts[eval_mask].values
                                - actual_pts[eval_mask].values
                            )
                        )
                    )
                    pos_maes[position] = mae
                    total_weighted_mae += mae * n_eval
                    total_n += n_eval

            overall_mae = total_weighted_mae / total_n if total_n > 0 else float("inf")

            grid_results.append({
                "roll3": roll3_w,
                "roll6": roll6_w,
                "std": std_w,
                "overall_mae": overall_mae,
                **{f"{p}_mae": pos_maes.get(p, float("nan")) for p in positions},
            })

            if overall_mae < best_overall_mae:
                best_overall_mae = overall_mae
                best_config = (roll3_w, roll6_w, std_w)

    # Print top 10 configurations
    grid_results.sort(key=lambda x: x["overall_mae"])
    print(f"\n  Top 10 configurations:")
    print(f"  {'roll3':>5} {'roll6':>5} {'std':>5} | {'Overall':>8} {'QB':>8} {'RB':>8} {'WR':>8} {'TE':>8}")
    print(f"  {'-' * 65}")
    for r in grid_results[:10]:
        current_marker = " <-- current" if (
            abs(r["roll3"] - current_roll3) < 0.01
            and abs(r["roll6"] - current_roll6) < 0.01
        ) else ""
        print(
            f"  {r['roll3']:>5.2f} {r['roll6']:>5.2f} {r['std']:>5.2f} | "
            f"{r['overall_mae']:>8.3f} {r.get('QB_mae', 0):>8.3f} "
            f"{r.get('RB_mae', 0):>8.3f} {r.get('WR_mae', 0):>8.3f} "
            f"{r.get('TE_mae', 0):>8.3f}{current_marker}"
        )

    # Compute current baseline MAE for comparison
    current_result = [
        r for r in grid_results
        if abs(r["roll3"] - current_roll3) < 0.01 and abs(r["roll6"] - current_roll6) < 0.01
    ]
    if current_result:
        current_mae = current_result[0]["overall_mae"]
        print(f"\n  Current config MAE: {current_mae:.4f}")
        print(f"  Best config MAE:    {best_overall_mae:.4f}")
        if best_config:
            print(f"  Best config: roll3={best_config[0]}, roll6={best_config[1]}, std={best_config[2]:.2f}")
            delta = current_mae - best_overall_mae
            print(f"  Improvement: {delta:+.4f} ({delta/current_mae*100:+.2f}%)")

    return grid_results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Phase 53-06 Experiment")
    parser.add_argument(
        "--path",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Run a specific path (1, 2, or 3). Default: run all.",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format (default: half_ppr).",
    )
    args = parser.parse_args()

    start_time = time.time()

    all_data, feature_cols, opp_rankings = load_data_and_rankings()

    paths_to_run = [args.path] if args.path else [1, 2, 3]

    path1_results = None
    path2_results = None
    path3_results = None

    if 1 in paths_to_run:
        path1_results = run_path1(all_data, feature_cols, opp_rankings, args.scoring)
    if 2 in paths_to_run:
        path2_results = run_path2(all_data, feature_cols, opp_rankings, args.scoring)
    if 3 in paths_to_run:
        path3_results = run_path3(all_data, feature_cols, opp_rankings, args.scoring)

    elapsed = time.time() - start_time
    print(f"\n\nTotal elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
