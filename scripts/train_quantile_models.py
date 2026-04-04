#!/usr/bin/env python3
"""Train quantile regression models for calibrated floor/ceiling predictions.

Trains LightGBM quantile models (10th, 50th, 90th percentile) per position
using the 42-column Silver feature set. Reports OOF calibration and MAE
vs the heuristic baseline.

Usage:
    python scripts/train_quantile_models.py --scoring half_ppr
    python scripts/train_quantile_models.py --scoring ppr --positions QB WR
"""

import argparse
import logging
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import PLAYER_DATA_SEASONS, PLAYER_LABEL_COLUMNS, SCORING_CONFIGS
from player_feature_engineering import (
    assemble_multiyear_player_features,
    get_player_feature_columns,
)
from quantile_models import (
    compute_calibration,
    save_quantile_models,
    train_quantile_models,
)
from scoring_calculator import calculate_fantasy_points_df

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Heuristic baseline MAE from backtest (half_ppr, 2022-2024 W3-18)
HEURISTIC_MAE = {
    "QB": 6.58,
    "RB": 5.00,
    "WR": 4.78,
    "TE": 3.74,
}


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Train quantile regression models for floor/ceiling predictions.",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        choices=list(SCORING_CONFIGS.keys()),
        help="Scoring format (default: half_ppr).",
    )
    parser.add_argument(
        "--positions",
        nargs="+",
        default=["QB", "RB", "WR", "TE"],
        help="Positions to train (default: QB RB WR TE).",
    )
    parser.add_argument(
        "--output-dir",
        default="models/quantile",
        help="Directory to save models (default: models/quantile).",
    )
    return parser


def compute_fantasy_target(
    df: pd.DataFrame,
    scoring_format: str,
) -> pd.DataFrame:
    """Compute fantasy points target column from raw stat labels.

    Args:
        df: Player-week DataFrame with raw stat columns.
        scoring_format: Scoring format key (ppr, half_ppr, standard).

    Returns:
        DataFrame with fantasy_points_target column added.
    """
    scoring = SCORING_CONFIGS[scoring_format]

    # Map raw stat columns to scoring components
    pts = pd.Series(0.0, index=df.index)

    stat_map = {
        "passing_yards": "pass_yd",
        "passing_tds": "pass_td",
        "interceptions": "interception",
        "rushing_yards": "rush_yd",
        "rushing_tds": "rush_td",
        "receiving_yards": "rec_yd",
        "receiving_tds": "rec_td",
        "receptions": "reception",
    }

    for stat_col, scoring_key in stat_map.items():
        if stat_col in df.columns and scoring_key in scoring:
            pts = pts + df[stat_col].fillna(0) * scoring[scoring_key]

    return pts


def main() -> None:
    """Main entry point for quantile model training."""
    parser = build_parser()
    args = parser.parse_args()

    t0 = time.time()

    # 1. Load multi-year player features
    logger.info("Assembling player features for seasons %s", PLAYER_DATA_SEASONS)
    features_df = assemble_multiyear_player_features()

    if features_df.empty:
        logger.error("No player features assembled. Check data/silver/ directory.")
        sys.exit(1)

    logger.info(
        "Assembled %d rows, %d columns across %d seasons",
        len(features_df),
        len(features_df.columns),
        features_df["season"].nunique(),
    )

    # 2. Compute fantasy points target
    target_col = "fantasy_points_target"
    features_df[target_col] = compute_fantasy_target(features_df, args.scoring)

    # Drop rows with NaN target
    before = len(features_df)
    features_df = features_df.dropna(subset=[target_col])
    logger.info(
        "Target column computed: %d rows (dropped %d with NaN target)",
        len(features_df),
        before - len(features_df),
    )

    # 3. Train quantile models
    logger.info("Training quantile models for positions: %s", args.positions)
    result = train_quantile_models(
        features_df=features_df,
        target_col=target_col,
        positions=args.positions,
    )

    # 4. Save models
    save_path = save_quantile_models(result, path=args.output_dir)
    logger.info("Models saved to %s", save_path)

    # 5. Report calibration
    oof_df = result["oof_predictions"]
    if oof_df.empty:
        logger.warning("No OOF predictions generated. Cannot evaluate calibration.")
        return

    cal_df = compute_calibration(oof_df)

    print("\n" + "=" * 80)
    print("QUANTILE REGRESSION RESULTS")
    print("=" * 80)
    print(f"Scoring format: {args.scoring}")
    print(f"Training time: {time.time() - t0:.1f}s")
    print(f"OOF rows: {len(oof_df)}")
    print()

    header = (
        f"{'POSITION':<10} {'HEURISTIC MAE':>14} {'Q50 MAE':>10} "
        f"{'COVERAGE (10-90)':>18} {'AVG WIDTH':>12} {'N':>8}"
    )
    print(header)
    print("-" * len(header))

    for _, row in cal_df.iterrows():
        pos = row["position"]
        h_mae = HEURISTIC_MAE.get(pos, float("nan"))
        print(
            f"{pos:<10} {h_mae:>14.2f} {row['q50_mae']:>10.2f} "
            f"{row['coverage_80']:>17.1%} {row['mean_interval_width']:>12.1f} pts"
            f"{row['n_rows']:>8d}"
        )

    print()
    print("Tail calibration (target: ~10% each):")
    print(f"{'POSITION':<10} {'P(actual < q10)':>18} {'P(actual > q90)':>18}")
    print("-" * 48)
    for _, row in cal_df.iterrows():
        print(
            f"{row['position']:<10} {row['lower_tail_10']:>17.1%} "
            f"{row['upper_tail_10']:>17.1%}"
        )

    print()
    elapsed = time.time() - t0
    print(f"Total time: {elapsed:.1f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
