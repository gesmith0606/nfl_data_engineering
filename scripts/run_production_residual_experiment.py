#!/usr/bin/env python3
"""Production residual experiment: residual correction on PRODUCTION heuristic.

Tests whether a Ridge residual model can improve on the production heuristic
(which includes ceiling shrinkage, matchup factor, usage multiplier).
The previous experiment (53-03) tested against a simplified heuristic that
was much weaker, inflating apparent improvements.

Approach:
    1. Load multiyear player features (same as ML training data)
    2. For each position, run the PRODUCTION heuristic (project_position)
       on each player-week to get production_projected_points
    3. Compute actual fantasy points from raw stats
    4. residual = actual - production_heuristic
    5. Train RidgeCV on features -> residual, walk-forward CV
    6. final = production_heuristic + ridge.predict(features)
    7. Compare MAE: production vs production + residual

Usage:
    python scripts/run_production_residual_experiment.py
    python scripts/run_production_residual_experiment.py --positions WR TE
    python scripts/run_production_residual_experiment.py --scoring half_ppr
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
    _matchup_factor,
    _usage_multiplier,
    _weighted_baseline,
    PROJECTION_CEILING_SHRINKAGE,
)
from scoring_calculator import calculate_fantasy_points_df

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Production heuristic reproduction on feature DataFrame
# ---------------------------------------------------------------------------


def compute_production_heuristic_points(
    pos_data: pd.DataFrame,
    position: str,
    opp_rankings: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.Series:
    """Reproduce the production heuristic on the feature DataFrame.

    Applies the full production pipeline:
    1. _weighted_baseline (roll3/roll6/std blending)
    2. _usage_multiplier [0.80, 1.15]
    3. _matchup_factor [0.75, 1.25]
    4. Scoring calculation
    5. PROJECTION_CEILING_SHRINKAGE (15/20/25 pt thresholds)

    Does NOT include Vegas multiplier (not available in backtest feature data)
    or bye week zeroing (not applicable to training data).

    Args:
        pos_data: Position-filtered feature DataFrame with rolling columns.
        position: Position code.
        opp_rankings: Opponent rankings DataFrame.
        scoring_format: Scoring format string.

    Returns:
        Series of production heuristic fantasy points aligned to pos_data.index.
    """
    stat_cols = POSITION_STAT_PROFILE.get(position, [])
    if not stat_cols:
        return pd.Series(np.nan, index=pos_data.index)

    work = pos_data.copy()

    # Drop opp_rank if present in feature data to avoid merge conflict
    # (_matchup_factor does its own merge and creates opp_rank)
    work = work.drop(columns=["opp_rank"], errors="ignore")

    # Step 1-3: baseline * usage * matchup
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

    # Step 4: Calculate fantasy points
    # Drop original stat columns that conflict with projected names
    orig_cols = [v for v in rename_map.values() if v in work.columns]
    scoring_input = work.drop(columns=orig_cols, errors="ignore")
    scoring_input = scoring_input.rename(columns=rename_map).reset_index(drop=True)
    scoring_input = calculate_fantasy_points_df(
        scoring_input, scoring_format=scoring_format, output_col="projected_points"
    )

    # Step 5: Ceiling shrinkage
    pts = scoring_input["projected_points"]
    shrink = pd.Series(1.0, index=scoring_input.index)
    for threshold in sorted(PROJECTION_CEILING_SHRINKAGE.keys()):
        factor = PROJECTION_CEILING_SHRINKAGE[threshold]
        shrink = shrink.where(pts < threshold, factor)
    scoring_input["projected_points"] = (pts * shrink).round(2)

    # Align index back to pos_data
    result = scoring_input["projected_points"]
    result.index = pos_data.index
    return result


def compute_actual_points(
    df: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.Series:
    """Compute actual fantasy points from raw stat columns.

    Args:
        df: DataFrame with actual stat columns.
        scoring_format: Scoring format string.

    Returns:
        Series of actual fantasy points aligned to df.index.
    """
    work = calculate_fantasy_points_df(
        df.copy(), scoring_format=scoring_format, output_col="actual_pts"
    )
    return work["actual_pts"]


# ---------------------------------------------------------------------------
# Walk-forward residual model
# ---------------------------------------------------------------------------


def train_production_residual(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols: List[str],
    opp_rankings: pd.DataFrame,
    scoring_format: str = "half_ppr",
    val_seasons: Optional[List[int]] = None,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Train residual correction on PRODUCTION heuristic with walk-forward CV.

    For each validation season:
    1. Compute production heuristic points for all rows
    2. Compute actual fantasy points
    3. residual = actual - production_heuristic
    4. Train Ridge on features -> residual (train seasons < val)
    5. Predict residual on val
    6. final = production_heuristic + predicted_residual

    Args:
        pos_data: Position-filtered DataFrame with features and actual stats.
        position: Position code.
        feature_cols: Feature column names.
        opp_rankings: Opponent rankings for matchup factor.
        scoring_format: Scoring format.
        val_seasons: Validation seasons. Default [2022, 2023, 2024].

    Returns:
        Tuple of:
        - results dict with per-fold details
        - oof DataFrame with columns for analysis
    """
    if val_seasons is None:
        val_seasons = [2022, 2023, 2024]

    available_features = [f for f in feature_cols if f in pos_data.columns]
    if not available_features:
        logger.warning("No features available for %s", position)
        return {"fold_details": []}, pd.DataFrame()

    # Pre-compute production heuristic and actual points for ALL rows
    logger.info(
        "Computing production heuristic for %s (%d rows)...", position, len(pos_data)
    )
    prod_pts = compute_production_heuristic_points(
        pos_data, position, opp_rankings, scoring_format
    )
    actual_pts = compute_actual_points(pos_data, scoring_format)

    # Week 3-18 filter
    week_mask = pos_data["week"].between(3, 18)

    fold_details: List[Dict[str, Any]] = []
    oof_records: List[pd.DataFrame] = []

    for val_season in val_seasons:
        train_mask = (pos_data["season"] < val_season) & week_mask
        val_mask = (pos_data["season"] == val_season) & week_mask

        train_idx = pos_data.index[train_mask]
        val_idx = pos_data.index[val_mask]

        if len(train_idx) < 50 or len(val_idx) < 10:
            logger.info(
                "Skipping fold %d: train=%d, val=%d",
                val_season,
                len(train_idx),
                len(val_idx),
            )
            continue

        # Residual = actual - production_heuristic
        train_residual = actual_pts.loc[train_idx] - prod_pts.loc[train_idx]
        val_heur = prod_pts.loc[val_idx]
        val_actual = actual_pts.loc[val_idx]

        # Drop NaN residuals
        train_valid = train_residual.notna()
        val_valid = val_heur.notna() & val_actual.notna()

        train_idx_valid = train_idx[train_valid.loc[train_idx].values]
        val_idx_valid = val_idx[val_valid.loc[val_idx].values]

        if len(train_idx_valid) < 50 or len(val_idx_valid) < 10:
            logger.info(
                "Skipping fold %d after NaN filter: train=%d, val=%d",
                val_season,
                len(train_idx_valid),
                len(val_idx_valid),
            )
            continue

        X_train = pos_data.loc[train_idx_valid, available_features]
        y_train = train_residual.loc[train_idx_valid]
        X_val = pos_data.loc[val_idx_valid, available_features]

        # Train Ridge residual model
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("model", RidgeCV(alphas=np.logspace(-3, 3, 50))),
            ]
        )
        model.fit(X_train, y_train)

        # Predict residual correction
        residual_pred = model.predict(X_val)

        # Hybrid = production_heuristic + predicted_residual
        hybrid_pts = val_heur.loc[val_idx_valid].values + residual_pred
        actual_val = val_actual.loc[val_idx_valid].values
        heur_val = val_heur.loc[val_idx_valid].values

        # MAE for this fold
        hybrid_mae = float(mean_absolute_error(actual_val, hybrid_pts))
        heur_mae = float(mean_absolute_error(actual_val, heur_val))

        fold_details.append(
            {
                "val_season": val_season,
                "train_size": len(train_idx_valid),
                "val_size": len(val_idx_valid),
                "heur_mae": heur_mae,
                "hybrid_mae": hybrid_mae,
                "improvement_pct": (heur_mae - hybrid_mae) / heur_mae * 100,
                "ridge_alpha": float(model.named_steps["model"].alpha_),
                "mean_residual_pred": float(np.mean(residual_pred)),
            }
        )

        oof_fold = pd.DataFrame(
            {
                "idx": val_idx_valid,
                "season": pos_data.loc[val_idx_valid, "season"].values,
                "week": pos_data.loc[val_idx_valid, "week"].values,
                "player_name": (
                    pos_data.loc[val_idx_valid, "player_name"].values
                    if "player_name" in pos_data.columns
                    else "unknown"
                ),
                "production_pts": heur_val,
                "residual_pred": residual_pred,
                "hybrid_pts": hybrid_pts,
                "actual_pts": actual_val,
            }
        )
        oof_records.append(oof_fold)

    oof_df = (
        pd.concat(oof_records, ignore_index=True) if oof_records else pd.DataFrame()
    )

    return {"fold_details": fold_details}, oof_df


# ---------------------------------------------------------------------------
# Build opponent rankings from the feature data
# ---------------------------------------------------------------------------


def build_opp_rankings_from_features(all_data: pd.DataFrame) -> pd.DataFrame:
    """Build a simple opponent ranking proxy from the feature data.

    Uses opp_rank columns if present in the feature data, otherwise returns
    empty DataFrame (matchup factor will default to 1.0).

    Args:
        all_data: Multiyear feature DataFrame.

    Returns:
        Opponent rankings DataFrame compatible with _matchup_factor.
    """
    # Check if we have pre-computed opponent rank columns
    rank_cols = [c for c in all_data.columns if "opp_rank" in c.lower()]
    if rank_cols:
        logger.info("Found opponent rank columns: %s", rank_cols[:5])

    # Build from Bronze weekly data (same approach as backtest script)
    try:
        project_root = os.path.join(os.path.dirname(__file__), "..")
        bronze_dir = os.path.join(project_root, "data", "bronze")

        import glob as globmod

        # Load weekly data
        dfs = []
        for season in PLAYER_DATA_SEASONS:
            files = sorted(
                globmod.glob(
                    os.path.join(
                        bronze_dir, f"players/weekly/season={season}/*.parquet"
                    )
                )
            )
            if files:
                dfs.append(pd.read_parquet(files[-1]))

        if not dfs:
            logger.warning("No Bronze weekly data for opponent rankings")
            return pd.DataFrame()

        weekly_df = pd.concat(dfs, ignore_index=True)
        if (
            "air_yards" not in weekly_df.columns
            and "receiving_air_yards" in weekly_df.columns
        ):
            weekly_df["air_yards"] = weekly_df["receiving_air_yards"].fillna(0)

        # Load schedules
        sched_dfs = []
        for season in PLAYER_DATA_SEASONS:
            for pattern in [
                f"games/season={season}/*.parquet",
                f"schedules/season={season}/*.parquet",
            ]:
                files = sorted(globmod.glob(os.path.join(bronze_dir, pattern)))
                if files:
                    sdf = pd.read_parquet(files[-1])
                    if "season" not in sdf.columns:
                        sdf["season"] = season
                    sched_dfs.append(sdf)
                    break

        schedules_df = (
            pd.concat(sched_dfs, ignore_index=True) if sched_dfs else pd.DataFrame()
        )

        from player_analytics import compute_opponent_rankings

        opp_rankings = compute_opponent_rankings(weekly_df, schedules_df)
        logger.info("Built opponent rankings: %d rows", len(opp_rankings))
        return opp_rankings

    except Exception as e:
        logger.warning("Failed to build opponent rankings: %s", e)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Production residual experiment")
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

    # ------------------------------------------------------------------
    # Step 2: Build opponent rankings for matchup factor
    # ------------------------------------------------------------------
    logger.info("Building opponent rankings...")
    opp_rankings = build_opp_rankings_from_features(all_data)

    # Validation seasons matching the heuristic backtest (2022-2024, weeks 3-18)
    val_seasons = [2022, 2023, 2024]

    # ------------------------------------------------------------------
    # Step 3: Run per-position experiments
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
        # Production heuristic baseline (full pipeline)
        # ------------------------------------------------------------------
        prod_pts = compute_production_heuristic_points(
            pos_data, position, opp_rankings, scoring
        )
        actual_pts = compute_actual_points(pos_data, scoring)

        # Evaluate on val seasons, weeks 3-18
        eval_mask = pos_data["season"].isin(val_seasons) & pos_data["week"].between(
            3, 18
        )
        valid_mask = eval_mask & prod_pts.notna() & actual_pts.notna()
        n_eval = int(valid_mask.sum())

        prod_mae = float(
            np.mean(np.abs(prod_pts[valid_mask].values - actual_pts[valid_mask].values))
        )
        print(f"  Production heuristic MAE: {prod_mae:.3f} ({n_eval} player-weeks)")

        # ------------------------------------------------------------------
        # Residual model on production heuristic
        # ------------------------------------------------------------------
        print(f"\n  --- Residual Correction on Production Heuristic ---")

        residual_result, residual_oof = train_production_residual(
            pos_data, position, feature_cols, opp_rankings, scoring, val_seasons
        )

        pos_result = {
            "position": position,
            "n_eval": n_eval,
            "production_mae": prod_mae,
            "hybrid_mae": None,
            "improvement_pct": None,
        }

        if residual_oof.empty:
            print("  Residual model training failed.")
        else:
            # Evaluate on val seasons, weeks 3-18
            residual_eval = residual_oof[
                residual_oof["season"].isin(val_seasons)
                & residual_oof["week"].between(3, 18)
            ]

            if residual_eval.empty:
                print("  No residual OOF in eval window.")
            else:
                hybrid_mae = float(
                    np.mean(
                        np.abs(
                            residual_eval["hybrid_pts"].values
                            - residual_eval["actual_pts"].values
                        )
                    )
                )
                prod_on_same = float(
                    np.mean(
                        np.abs(
                            residual_eval["production_pts"].values
                            - residual_eval["actual_pts"].values
                        )
                    )
                )
                n_residual = len(residual_eval)
                improvement = (prod_on_same - hybrid_mae) / prod_on_same * 100

                print(f"  Production heuristic MAE (same rows): {prod_on_same:.3f}")
                print(
                    f"  Production + Residual MAE: {hybrid_mae:.3f} ({n_residual} rows)"
                )
                print(f"  Improvement: {improvement:+.1f}%")

                # Per-fold details
                for fd in residual_result["fold_details"]:
                    print(
                        f"    Season {fd['val_season']}: "
                        f"Heur MAE={fd['heur_mae']:.3f}, "
                        f"Hybrid MAE={fd['hybrid_mae']:.3f}, "
                        f"Improvement={fd['improvement_pct']:+.1f}%, "
                        f"Ridge alpha={fd['ridge_alpha']:.3f}, "
                        f"Mean residual={fd['mean_residual_pred']:+.3f}, "
                        f"n={fd['val_size']}"
                    )

                # Error distribution analysis
                prod_errors = np.abs(
                    residual_eval["production_pts"].values
                    - residual_eval["actual_pts"].values
                )
                hybrid_errors = np.abs(
                    residual_eval["hybrid_pts"].values
                    - residual_eval["actual_pts"].values
                )
                print(f"\n  Error distribution:")
                for pct in [50, 75, 90, 95]:
                    print(
                        f"    P{pct}: Prod={np.percentile(prod_errors, pct):.2f}, "
                        f"Hybrid={np.percentile(hybrid_errors, pct):.2f}"
                    )

                pos_result["hybrid_mae"] = hybrid_mae
                pos_result["improvement_pct"] = improvement

        results_table.append(pos_result)

    # ------------------------------------------------------------------
    # Summary Table
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time

    print(f"\n\n{'=' * 90}")
    print(f"  PRODUCTION RESIDUAL EXPERIMENT RESULTS ({scoring.upper()})")
    print(f"{'=' * 90}")
    print(
        f"  {'POSITION':<10} {'PROD HEUR MAE':>14} {'PROD+RESID MAE':>15} "
        f"{'IMPROVEMENT':>12} {'DECISION':>10}"
    )
    print(f"  {'-' * 70}")

    total_prod_weighted = 0.0
    total_hybrid_weighted = 0.0
    total_weight = 0.0

    for r in results_table:
        pos = r["position"]
        prod_mae = r["production_mae"]
        hybrid_mae = r.get("hybrid_mae")
        improvement = r.get("improvement_pct")
        n = r["n_eval"]

        if hybrid_mae is not None and improvement is not None:
            # SHIP if improvement > 0% (strictly better)
            decision = "SHIP" if improvement > 0 else "SKIP"
            print(
                f"  {pos:<10} {prod_mae:>14.3f} {hybrid_mae:>15.3f} "
                f"{improvement:>+11.1f}% {decision:>10}"
            )
            total_prod_weighted += prod_mae * n
            total_hybrid_weighted += hybrid_mae * n
            total_weight += n
        else:
            print(
                f"  {pos:<10} {prod_mae:>14.3f} {'N/A':>15} "
                f"{'N/A':>12} {'SKIP':>10}"
            )

    if total_weight > 0:
        overall_prod = total_prod_weighted / total_weight
        overall_hybrid = total_hybrid_weighted / total_weight
        overall_improvement = (overall_prod - overall_hybrid) / overall_prod * 100
        overall_decision = "SHIP" if overall_improvement > 0 else "SKIP"
        print(f"  {'-' * 70}")
        print(
            f"  {'Overall':<10} {overall_prod:>14.3f} {overall_hybrid:>15.3f} "
            f"{overall_improvement:>+11.1f}% {overall_decision:>10}"
        )

    print(f"\n  Elapsed: {elapsed:.1f}s")
    print(f"{'=' * 90}")

    return results_table


if __name__ == "__main__":
    main()
