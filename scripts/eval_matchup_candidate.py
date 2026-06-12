#!/usr/bin/env python3
"""Evaluate WR/TE candidate residual models (ELITE-2.3) vs production baseline.

Applies both production and candidate residual models to 2022-2024 WR/TE
player-weeks (weeks 3-18, consensus_proj >= 5 pts) and compares:
  - Heuristic baseline MAE / Spearman
  - Production residual MAE / Spearman (models/residual/)
  - Candidate residual MAE / Spearman (models/residual_matchup_candidate/)

Gates:
  - SHIP if TE 2022-24 MAE gap <= -0.46 (current prod gap = -0.428)
  - SHIP if WR gap improves >= 0.03 MAE points vs heuristic with no TE regression

Safety:
  - Production models are NEVER modified by this script
  - Candidate models come from models/residual_matchup_candidate/ only

Usage:
    python scripts/eval_matchup_candidate.py
    python scripts/eval_matchup_candidate.py --seasons 2022 2023 2024
"""

import argparse
import glob
import logging
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTION_MODEL_DIR = os.path.join(BASE_DIR, "models", "residual")
CANDIDATE_MODEL_DIR = os.path.join(BASE_DIR, "models", "residual_matchup_candidate")
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")
SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")

EVAL_WEEKS_MIN = 3
EVAL_WEEKS_MAX = 18
CONSENSUS_MIN_PTS = 5.0

# Gate thresholds (from spec)
GATE_TE_GAP_THRESHOLD = -0.46   # TE gap must be <= this (more negative = better)
GATE_WR_IMPROVEMENT = 0.03      # WR must improve by >= this many MAE points


def _load_bronze_latest(subdir: str, seasons: list) -> pd.DataFrame:
    """Load latest parquet for each season from bronze subdirectory."""
    dfs = []
    for s in seasons:
        pattern = os.path.join(BRONZE_DIR, subdir, f"season={s}", "*.parquet")
        fs = sorted(glob.glob(pattern))
        if fs:
            dfs.append(pd.read_parquet(fs[-1]))
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _load_silver_latest(subdir: str, seasons: list) -> pd.DataFrame:
    """Load latest parquet for each season from silver subdirectory."""
    dfs = []
    for s in seasons:
        pattern = os.path.join(SILVER_DIR, subdir, f"season={s}", "*.parquet")
        fs = sorted(glob.glob(pattern))
        if fs:
            dfs.append(pd.read_parquet(fs[-1]))
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _compute_half_ppr(pw: pd.DataFrame) -> pd.Series:
    """Compute half-PPR fantasy points from player-weekly dataframe."""
    if "fantasy_points_ppr" in pw.columns and "fantasy_points" in pw.columns:
        return (pw["fantasy_points"] + pw["fantasy_points_ppr"]) / 2
    if "fantasy_points" in pw.columns:
        return pw["fantasy_points"]
    return pd.Series(np.nan, index=pw.index)


def _mean_spearman(df: pd.DataFrame, pred_col: str, actual_col: str) -> float:
    """Compute mean within-position-week Spearman rank correlation."""
    corrs = []
    for _, grp in df.groupby(["season", "week"]):
        valid = grp[[pred_col, actual_col]].dropna()
        if len(valid) < 4:
            continue
        r, _ = stats.spearmanr(valid[pred_col], valid[actual_col])
        if not np.isnan(r):
            corrs.append(r)
    return float(np.mean(corrs)) if corrs else np.nan


def run_evaluation(seasons: list) -> None:
    """Run candidate vs production evaluation and print results.

    Args:
        seasons: List of seasons to evaluate over (e.g. [2022, 2023, 2024]).
    """
    from hybrid_projection import apply_residual_correction
    from player_feature_engineering import assemble_multiyear_player_features
    from unified_evaluation import (
        build_defensive_strength_table,
        compute_production_heuristic,
    )

    logger.info("Loading Bronze player-weekly for seasons: %s", seasons)
    pw = _load_bronze_latest("players/weekly", seasons)
    if pw.empty:
        logger.error("No player-weekly data found. Exiting.")
        return

    pw["actual_half_ppr"] = _compute_half_ppr(pw)
    pw = pw[(pw["week"] >= EVAL_WEEKS_MIN) & (pw["week"] <= EVAL_WEEKS_MAX)].copy()

    # Load feature data (includes ELITE-2.3 trailing features via _join_def_trailing_features)
    logger.info("Assembling player features for seasons: %s", seasons)
    feature_data = assemble_multiyear_player_features(seasons)
    if feature_data.empty:
        logger.error("No feature data assembled. Exiting.")
        return
    logger.info("Feature data: %d rows, %d columns", len(feature_data), len(feature_data.columns))

    # Check new trailing features are present
    trail_cols = [
        "wr_def_trail_yds_per_tgt", "wr_def_trail_yds_per_tgt_slot",
        "te_def_trail_td_rate", "te_def_trail_lb_coverage_share",
    ]
    found_trail = [c for c in trail_cols if c in feature_data.columns]
    logger.info("Defense trailing features in feature_data: %d/%d", len(found_trail), len(trail_cols))
    if not found_trail:
        logger.warning(
            "NONE of the new trailing features found in assembled data. "
            "Check that _join_def_trailing_features ran and Silver parquets exist."
        )

    # Build defensive strength table
    logger.info("Building defensive strength table...")
    opp_rankings = build_defensive_strength_table(seasons)

    results_rows = []

    for position in ["WR", "TE"]:
        logger.info("\n--- Evaluating %s ---", position)

        # Filter to position player-weeks
        pw_pos = pw[pw["position"] == position].copy()
        pw_pos["player_id"] = pw_pos["player_id"].astype(str)

        feat_pos = feature_data[feature_data["position"] == position].copy()
        feat_pos["player_id"] = feat_pos["player_id"].astype(str)

        if pw_pos.empty or feat_pos.empty:
            logger.warning("No %s data in eval window", position)
            continue

        # Compute heuristic projections row by row
        logger.info("Computing heuristic projections for %s (%d rows)...", position, len(feat_pos))
        heuristic_series = compute_production_heuristic(
            feat_pos,
            position=position,
            opp_rankings=opp_rankings,
            scoring_format="half_ppr",
        )
        feat_pos["heuristic_pts"] = heuristic_series.values

        # Join actuals
        feat_pos = feat_pos.merge(
            pw_pos[["player_id", "season", "week", "actual_half_ppr"]],
            on=["player_id", "season", "week"],
            how="inner",
        )

        # Load external consensus (optional, for reference)
        feat_pos_consensus = feat_pos.copy()
        for sdir in ["external_projections/sleeper"]:
            ext = _load_silver_latest(sdir, seasons)
            if not ext.empty:
                ext["player_id"] = ext["player_id"].astype(str)
                if "projected_points" in ext.columns:
                    ext = ext.rename(columns={"projected_points": "consensus_proj"})
                elif "consensus_proj" not in ext.columns:
                    ext = pd.DataFrame()
                if not ext.empty and "consensus_proj" in ext.columns:
                    feat_pos_consensus = feat_pos_consensus.merge(
                        ext[["player_id", "season", "week", "consensus_proj"]],
                        on=["player_id", "season", "week"],
                        how="left",
                    )

        eval_df = feat_pos.copy()
        if "consensus_proj" not in eval_df.columns:
            eval_df["consensus_proj"] = np.nan

        # Apply consensus minimum filter: at least 5 pts consensus or, if
        # consensus unavailable, filter by heuristic >= 5
        has_consensus = eval_df["consensus_proj"].notna().sum() > 0
        if has_consensus:
            eval_df = eval_df[eval_df["consensus_proj"] >= CONSENSUS_MIN_PTS].copy()
        else:
            eval_df = eval_df[eval_df["heuristic_pts"].fillna(0) >= CONSENSUS_MIN_PTS].copy()

        if eval_df.empty:
            logger.warning("No %s rows after consensus filter", position)
            continue

        logger.info("%s eval rows: %d (has_consensus: %s)", position, len(eval_df), has_consensus)

        # Heuristic MAE
        heuristic_mae = (eval_df["heuristic_pts"] - eval_df["actual_half_ppr"]).abs().mean()
        heuristic_spearman = _mean_spearman(eval_df, "heuristic_pts", "actual_half_ppr")

        # Apply production residual
        heur_df_for_residual = eval_df[["player_id", "season", "week"]].copy()
        heur_df_for_residual["projected_points"] = eval_df["heuristic_pts"].values

        prod_corrected = apply_residual_correction(
            heur_df_for_residual.copy(),
            eval_df,
            position,
            model_dir=PRODUCTION_MODEL_DIR,
        )
        prod_pts = prod_corrected["projected_points"].values
        prod_mae = np.abs(prod_pts - eval_df["actual_half_ppr"].values).mean()
        eval_df["prod_pts"] = prod_pts
        prod_spearman = _mean_spearman(eval_df, "prod_pts", "actual_half_ppr")

        # Apply candidate residual
        cand_corrected = apply_residual_correction(
            heur_df_for_residual.copy(),
            eval_df,
            position,
            model_dir=CANDIDATE_MODEL_DIR,
        )
        cand_pts = cand_corrected["projected_points"].values
        cand_mae = np.abs(cand_pts - eval_df["actual_half_ppr"].values).mean()
        eval_df["cand_pts"] = cand_pts
        cand_spearman = _mean_spearman(eval_df, "cand_pts", "actual_half_ppr")

        prod_gap = prod_mae - heuristic_mae
        cand_gap = cand_mae - heuristic_mae

        results_rows.append({
            "position": position,
            "n_obs": len(eval_df),
            "heuristic_mae": heuristic_mae,
            "prod_mae": prod_mae,
            "prod_gap": prod_gap,
            "prod_spearman": prod_spearman,
            "cand_mae": cand_mae,
            "cand_gap": cand_gap,
            "cand_spearman": cand_spearman,
            "cand_vs_prod_mae_delta": cand_mae - prod_mae,
        })

        logger.info(
            "%s | heuristic_mae=%.3f | prod_mae=%.3f (gap=%.3f) | "
            "cand_mae=%.3f (gap=%.3f) | cand_vs_prod_delta=%.3f",
            position, heuristic_mae,
            prod_mae, prod_gap,
            cand_mae, cand_gap,
            cand_mae - prod_mae,
        )

    if not results_rows:
        print("\nERROR: No evaluation results generated.")
        return

    # Print results table
    print(f"\n{'=' * 75}")
    print("  ELITE-2.3 CANDIDATE EVALUATION RESULTS")
    print(f"  Seasons: {seasons} | Weeks: {EVAL_WEEKS_MIN}-{EVAL_WEEKS_MAX}")
    print(f"{'=' * 75}")
    print(
        f"\n  {'Pos':<5} {'N':>6} {'Heur MAE':>9} {'Prod MAE':>9} {'Prod Gap':>9} "
        f"{'Cand MAE':>9} {'Cand Gap':>9} {'Delta':>8}"
    )
    print(f"  {'-'*65}")

    te_row = None
    wr_row = None
    for r in results_rows:
        delta_sign = "+" if r["cand_vs_prod_mae_delta"] > 0 else ""
        print(
            f"  {r['position']:<5} {r['n_obs']:>6} {r['heuristic_mae']:>9.3f} "
            f"{r['prod_mae']:>9.3f} {r['prod_gap']:>+9.3f} "
            f"{r['cand_mae']:>9.3f} {r['cand_gap']:>+9.3f} "
            f"{delta_sign}{r['cand_vs_prod_mae_delta']:>7.3f}"
        )
        if r["position"] == "TE":
            te_row = r
        if r["position"] == "WR":
            wr_row = r

    # Spearman table
    print(f"\n  {'Pos':<5} {'Prod SpearR':>12} {'Cand SpearR':>12}")
    print(f"  {'-'*35}")
    for r in results_rows:
        print(
            f"  {r['position']:<5} {r['prod_spearman']:>12.4f} {r['cand_spearman']:>12.4f}"
        )

    # Gate evaluation
    print(f"\n{'=' * 75}")
    print("  GATE EVALUATION")
    print(f"{'=' * 75}")
    print(f"  Reference baselines (from plan): TE prod_gap = -0.428, WR prod_gap = -0.075")
    print(f"  Gate 1: TE cand_gap <= {GATE_TE_GAP_THRESHOLD} (more negative = better)")
    print(f"  Gate 2: WR improvement >= {GATE_WR_IMPROVEMENT} MAE points vs heuristic (no TE regression)")

    te_gate_pass = False
    wr_gate_pass = False

    if te_row:
        te_gate_pass = te_row["cand_gap"] <= GATE_TE_GAP_THRESHOLD
        te_status = "PASS" if te_gate_pass else "FAIL"
        print(f"\n  Gate 1 (TE gap <= {GATE_TE_GAP_THRESHOLD}): {te_status}")
        print(f"    TE cand_gap = {te_row['cand_gap']:+.3f}  (prod_gap = {te_row['prod_gap']:+.3f})")

    if wr_row and te_row:
        wr_improvement = te_row["prod_gap"] - wr_row["cand_gap"] if te_row else 0
        # WR gate: improvement >= 0.03 with no TE regression
        # "improvement" = prod_gap - cand_gap (negative means cand is closer to 0 = better)
        # Actually WR improvement = cand is LOWER MAE, so: heuristic_mae - cand_mae >= 0.03
        # Wait — gap = cand_mae - heuristic_mae; lower (more negative) is better
        # "improves >= 0.03" means cand_gap <= prod_gap - 0.03
        wr_improvement_val = wr_row["prod_gap"] - wr_row["cand_gap"]
        # And no TE regression = TE cand_gap <= TE prod_gap
        no_te_regression = te_row["cand_gap"] <= te_row["prod_gap"]
        wr_gate_pass = wr_improvement_val >= GATE_WR_IMPROVEMENT and no_te_regression
        wr_status = "PASS" if wr_gate_pass else "FAIL"
        print(f"\n  Gate 2 (WR improvement >= {GATE_WR_IMPROVEMENT}, no TE regression): {wr_status}")
        print(f"    WR improvement = {wr_improvement_val:+.3f}  (cand_gap {wr_row['cand_gap']:+.3f} vs prod_gap {wr_row['prod_gap']:+.3f})")
        if not no_te_regression:
            print(f"    [BLOCKED] TE regression: cand_gap {te_row['cand_gap']:+.3f} > prod_gap {te_row['prod_gap']:+.3f}")

    overall = te_gate_pass or wr_gate_pass
    verdict = "SHIP" if overall else "KILL"
    print(f"\n  OVERALL VERDICT: {verdict}")
    if overall:
        print(
            "  -> SHIP: Candidate models cleared the gate. "
            "Promote models/residual_matchup_candidate/ to production."
        )
    else:
        print(
            "  -> KILL: Gates not cleared. "
            "Restore production models from models/residual/_matchup_backup/."
        )

    print(f"\n{'=' * 75}\n")


def main() -> int:
    """Entry point for candidate evaluation CLI.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        description="Evaluate ELITE-2.3 candidate WR/TE models vs production baseline."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2022, 2023, 2024],
        help="Seasons to evaluate (default: 2022 2023 2024)",
    )
    args = parser.parse_args()

    # Verify backups exist
    backup_dir = os.path.join(BASE_DIR, "models", "residual", "_matchup_backup")
    if not os.path.exists(backup_dir):
        logger.error(
            "Backup directory %s not found. Run backup step first.", backup_dir
        )
        return 1

    if not os.path.exists(CANDIDATE_MODEL_DIR) or not any(
        f.endswith(".joblib") for f in os.listdir(CANDIDATE_MODEL_DIR)
    ):
        logger.error(
            "No candidate models found in %s. Run train_matchup_candidate_models.py first.",
            CANDIDATE_MODEL_DIR,
        )
        return 1

    run_evaluation(args.seasons)
    return 0


if __name__ == "__main__":
    sys.exit(main())
