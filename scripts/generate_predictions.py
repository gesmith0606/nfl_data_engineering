#!/usr/bin/env python3
"""Generate weekly NFL game predictions with edge detection vs Vegas lines.

Loads trained XGBoost spread and total models, generates predictions for a
requested season/week, computes edges against Vegas closing lines, and
classifies confidence tiers.

Edge convention:
  spread_edge = model_spread - vegas_spread
    Positive = model sees MORE home advantage than Vegas
  total_edge = model_total - vegas_total
    Positive = model expects HIGHER scoring than Vegas

Confidence tiers:
  High:   |edge| >= 3.0 points
  Medium: 1.5 <= |edge| < 3.0 points
  Low:    |edge| < 1.5 points

Usage:
    python scripts/generate_predictions.py --season 2025 --week 10
    python scripts/generate_predictions.py --season 2025 --week 10 --model-dir models/
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feature_engineering import assemble_game_features, get_feature_columns  # noqa: E402
from model_training import load_model  # noqa: E402
from config import MODEL_DIR  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")

# Output columns for the predictions DataFrame
OUTPUT_COLUMNS = [
    "game_id",
    "season",
    "week",
    "home_team",
    "away_team",
    "model_spread",
    "model_total",
    "vegas_spread",
    "vegas_total",
    "spread_edge",
    "total_edge",
    "spread_confidence_tier",
    "total_confidence_tier",
    "model_version",
    "prediction_timestamp",
]


def classify_tier(edge_value: float) -> Optional[str]:
    """Classify a prediction edge into a confidence tier.

    Args:
        edge_value: The absolute edge value (model - Vegas).

    Returns:
        'high', 'medium', 'low', or None if edge is NaN.
    """
    if pd.isna(edge_value):
        return None
    abs_edge = abs(edge_value)
    if abs_edge >= 3.0:
        return "high"
    if abs_edge >= 1.5:
        return "medium"
    return "low"


def generate_week_predictions(
    game_df: pd.DataFrame,
    week: int,
    spread_model: Any,
    spread_meta: Dict[str, Any],
    total_model: Any,
    total_meta: Dict[str, Any],
) -> pd.DataFrame:
    """Generate predictions for all games in a given week.

    Args:
        game_df: Full season game features from assemble_game_features().
        week: NFL week number to predict.
        spread_model: Trained spread prediction model with .predict() method.
        spread_meta: Spread model metadata with 'feature_names' key.
        total_model: Trained total prediction model with .predict() method.
        total_meta: Total model metadata with 'feature_names' key.

    Returns:
        DataFrame with predictions, edges, and confidence tiers sorted by
        max edge magnitude (strongest plays first, NaN edges last).
    """
    week_df = game_df[game_df["week"] == week].copy()
    if week_df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # Align features to what each model expects
    spread_features = spread_meta.get("feature_names", [])
    available_spread = [c for c in spread_features if c in week_df.columns]
    if len(available_spread) < len(spread_features):
        missing = set(spread_features) - set(available_spread)
        logger.warning(
            "Spread model: %d/%d features missing: %s",
            len(missing),
            len(spread_features),
            sorted(missing)[:5],
        )

    total_features = total_meta.get("feature_names", [])
    available_total = [c for c in total_features if c in week_df.columns]
    if len(available_total) < len(total_features):
        missing = set(total_features) - set(available_total)
        logger.warning(
            "Total model: %d/%d features missing: %s",
            len(missing),
            len(total_features),
            sorted(missing)[:5],
        )

    # Fill NaN features with 0.0 (early season handling)
    spread_input = week_df[available_spread].fillna(0.0)
    total_input = week_df[available_total].fillna(0.0)

    # Generate predictions
    week_df["model_spread"] = spread_model.predict(spread_input)
    week_df["model_total"] = total_model.predict(total_input)

    # Map Vegas lines
    week_df["vegas_spread"] = week_df["spread_line"]
    week_df["vegas_total"] = week_df["total_line"]

    # Compute edges
    week_df["spread_edge"] = week_df["model_spread"] - week_df["vegas_spread"]
    week_df["total_edge"] = week_df["model_total"] - week_df["vegas_total"]

    # Classify confidence tiers (apply to raw edge, not abs)
    week_df["spread_confidence_tier"] = week_df["spread_edge"].apply(classify_tier)
    week_df["total_confidence_tier"] = week_df["total_edge"].apply(classify_tier)

    # Metadata
    week_df["model_version"] = "v1.4.0"
    week_df["prediction_timestamp"] = datetime.utcnow()

    # Sort by max edge magnitude (strongest plays first, NaN last)
    week_df["_sort_key"] = week_df[["spread_edge", "total_edge"]].abs().max(axis=1)
    week_df = week_df.sort_values("_sort_key", ascending=False, na_position="last")

    # Select output columns
    output = week_df[OUTPUT_COLUMNS].reset_index(drop=True)
    return output


def _print_predictions_table(predictions: pd.DataFrame) -> None:
    """Print a formatted console table of predictions.

    Args:
        predictions: Output from generate_week_predictions().
    """
    print(f"\n{'=' * 90}")
    print(
        f"{'Game':<20} {'Model Sprd':>10} {'Vegas Sprd':>10} {'Sprd Edge':>10} "
        f"{'Model Tot':>9} {'Vegas Tot':>9} {'Tot Edge':>9} {'Tier':>6}"
    )
    print(f"{'-' * 90}")

    for _, row in predictions.iterrows():
        game = f"{row['away_team']}@{row['home_team']}"
        sprd_tier = row["spread_confidence_tier"] or "-"
        tot_tier = row["total_confidence_tier"] or "-"
        tier_display = f"{sprd_tier[0].upper()}/{tot_tier[0].upper()}" if sprd_tier != "-" and tot_tier != "-" else "-"

        vegas_sprd = f"{row['vegas_spread']:+.1f}" if pd.notna(row["vegas_spread"]) else "N/A"
        vegas_tot = f"{row['vegas_total']:.1f}" if pd.notna(row["vegas_total"]) else "N/A"
        sprd_edge = f"{row['spread_edge']:+.1f}" if pd.notna(row["spread_edge"]) else "N/A"
        tot_edge = f"{row['total_edge']:+.1f}" if pd.notna(row["total_edge"]) else "N/A"

        print(
            f"{game:<20} {row['model_spread']:>+10.1f} {vegas_sprd:>10} {sprd_edge:>10} "
            f"{row['model_total']:>9.1f} {vegas_tot:>9} {tot_edge:>9} {tier_display:>6}"
        )

    print(f"{'=' * 90}")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for weekly game predictions.

    Args:
        argv: Command-line arguments. None uses sys.argv.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="Generate weekly NFL game predictions with edge detection"
    )
    parser.add_argument(
        "--season", type=int, required=True, help="NFL season year"
    )
    parser.add_argument(
        "--week", type=int, required=True, help="NFL week number (1-18)"
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Directory containing trained models (default: models/)",
    )
    args = parser.parse_args(argv)

    print(f"\nNFL Game Prediction Pipeline v1.4")
    print(f"Season: {args.season}, Week: {args.week}")
    print("=" * 60)

    # Load models
    model_dir = args.model_dir
    try:
        print("Loading spread model...")
        spread_model, spread_meta = load_model("spread", model_dir=model_dir)
        print("Loading total model...")
        total_model, total_meta = load_model("total", model_dir=model_dir)
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        print("Train models first: python scripts/train_models.py --target both")
        return 1

    # Assemble features
    print("Assembling game features...")
    try:
        game_df = assemble_game_features(args.season)
    except Exception as e:
        print(f"\nERROR: Failed to assemble features: {e}")
        logger.exception("Feature assembly failed")
        return 1

    if game_df.empty:
        print("ERROR: No game data found for this season. Check Silver/Bronze data.")
        return 1

    print(f"  {len(game_df)} games in season {args.season}")

    # Generate predictions
    predictions = generate_week_predictions(
        game_df, args.week, spread_model, spread_meta, total_model, total_meta
    )

    if predictions.empty:
        print(f"\nNo games found for week {args.week}.")
        return 0

    # Display results
    _print_predictions_table(predictions)

    # Summary
    n_games = len(predictions)
    high_spread = (predictions["spread_confidence_tier"] == "high").sum()
    high_total = (predictions["total_confidence_tier"] == "high").sum()
    print(
        f"\n{n_games} games | {high_spread} high-confidence spread edges | "
        f"{high_total} high-confidence total edges"
    )

    # Save Gold Parquet
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    s3_key = (
        f"predictions/season={args.season}/week={args.week:02d}/"
        f"predictions_{timestamp}.parquet"
    )
    gold_path = os.path.join(GOLD_DIR, s3_key)
    os.makedirs(os.path.dirname(gold_path), exist_ok=True)
    predictions.to_parquet(gold_path, index=False)
    print(f"\nSaved: {gold_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
