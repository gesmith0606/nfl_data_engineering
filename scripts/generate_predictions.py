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
from ensemble_training import load_ensemble, predict_ensemble  # noqa: E402
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
    "predicted_spread",
    "predicted_total",
    "vegas_spread",
    "vegas_total",
    "spread_edge",
    "total_edge",
    "confidence_tier",
    "ats_pick",
    # Retired betting surface, kept in the schema. See OU_PICK_RETIRED.
    "ou_pick",
    "home_cover_prob",
    "over_prob",
]


# ---------------------------------------------------------------------------
# Retired betting surface: game totals
# ---------------------------------------------------------------------------
# .planning/TOTALS_VERDICT.md (2026-06-10) reached VERDICT: KILL on the
# game-totals betting surface, with this action: "Remove the game-totals
# betting surface from production. Keep predicted_total as website content
# labeled market tracking (useful context; not a bet recommendation)."
#
# Enforced by never populating a side in ``ou_pick``. The column itself stays
# in OUTPUT_COLUMNS (and in the predictions DDL, the API schema and the
# frontend types) so the served schema and the DB contract are unchanged;
# dropping it would cascade a migration through four consumers to no benefit.
# predicted_total, vegas_total, total_edge and over_prob are all still emitted
# -- those are the market-tracking content the verdict asks us to keep.
#
# Why no side can be emitted: the totals model is near-constant
# (``predicted_total`` std 0.49 against ``vegas_total`` std 4.66 on the served
# 2026 wk7 board), so ``total_edge`` is the Vegas line with its sign flipped
# (corr -0.9944, vs +0.038 against our own prediction) and "over if
# total_edge > 0" reduces to fading every extreme line. Graded model-free
# against the 93 settled 2026 games, that rule goes 41-52-0 (44.1%, ROI
# -15.84%) -- byte-identical to the shipped ensemble O/U record, while the
# market itself was a coin flip (overs 50.5%). The pick also contradicted our
# own calibrated ``over_prob`` on 9 of 14 wk7 games. Full write-up:
# .planning/CLV_PICK_RULE_AUDIT_2026_10_24.md.
OU_PICK_RETIRED = ""


# ---------------------------------------------------------------------------
# ATS pick rule
# ---------------------------------------------------------------------------
# The calibrated cover probability -- not the raw edge sign -- picks the side,
# so ``ats_pick`` and ``home_cover_prob`` can never contradict each other (they
# disagreed on 1 of 14 games on the served 2026 wk7 board). ``>=`` preserves
# the historical tie behaviour: a dead-even game is a home pick.
ATS_PICK_PROB_THRESHOLD = 0.50

# -110 juice breaks even at 52.38%. Gating publication on it is a PRODUCT
# decision, not a modelling one: on the served 2026 wk7 board only 4 of 14
# picked sides clear it (the picked side's probability tops out at 0.5531), so
# switching this on strips most of the board off a monetized site.
# Deliberately left OFF -- ``None`` publishes every pick, which is the existing
# behaviour. Set it to 0.5238 to publish only picks that clear break-even;
# rows below it get an empty ``ats_pick``, the same "no recommendation" shape
# ``ou_pick`` now carries permanently.
#
# Measured on the only two boards carrying a calibrator (2026 wk7 n=14, 2025
# wk18 n=16): 10 of 30 picked sides clear 52.38% (33%). Reading the raw
# ``home_cover_prob`` instead of the picked side's probability gives 1 of 30 --
# that is the "nothing clears it" figure, and it undercounts, because most
# picks are AWAY and the away side's probability is 1 - home_cover_prob.
ATS_PUBLISH_MIN_PROB: Optional[float] = None


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


# Calibrated win probability of the picked side. -110 juice breaks even at
# 52.4%, so "medium" must clear it and "high" needs real margin.
PROB_TIER_HIGH = 0.56
PROB_TIER_MEDIUM = 0.53


def classify_tier_prob(pick_prob: float) -> Optional[str]:
    """Classify by the calibrated probability that the picked side wins.

    Raw edge size is not confidence: on the sealed 2025 season a 3+ point
    edge hit 53% O/U and 57% ATS, while the leak-free OOF calibrator maps a
    5-point total edge to a 49.5% over probability (the totals model is
    near-constant, so big "edges" just mean Vegas posted an extreme line).
    Tiering on the calibrated probability lets a model without skill fall to
    "low" instead of advertising high confidence.

    Args:
        pick_prob: Calibrated probability that the recommended side wins.

    Returns:
        'high', 'medium', 'low', or None if the probability is NaN.
    """
    if pd.isna(pick_prob):
        return None
    if pick_prob >= PROB_TIER_HIGH:
        return "high"
    if pick_prob >= PROB_TIER_MEDIUM:
        return "medium"
    return "low"


def picks_home_side(df: pd.DataFrame) -> pd.Series:
    """Whether the ATS pick takes the home side, per the calibrated probability.

    ``home_cover_prob`` is the leak-free OOF calibrator's probability that the
    home side covers, so picking from it makes the served pick and the served
    probability agree by construction. Rows with no probability -- the single
    XGBoost path trains no calibrator -- fall back to the edge sign, which is
    the pre-2026-10 behaviour (NaN edge picked home, and still does).

    Args:
        df: Frame carrying ``home_cover_prob`` and/or ``spread_edge``.

    Returns:
        Boolean Series aligned to ``df.index``.
    """
    nan_series = pd.Series(np.nan, index=df.index)
    prob = pd.to_numeric(df.get("home_cover_prob", nan_series), errors="coerce")
    edge = pd.to_numeric(df.get("spread_edge", nan_series), errors="coerce")
    return pd.Series(
        np.where(prob.notna(), prob >= ATS_PICK_PROB_THRESHOLD, edge.fillna(0.0) >= 0),
        index=df.index,
    )


def picked_side_prob(df: pd.DataFrame) -> pd.Series:
    """Calibrated probability that the *picked* ATS side covers.

    Args:
        df: Frame carrying ``home_cover_prob`` (and the columns
            :func:`picks_home_side` needs).

    Returns:
        Float Series; NaN wherever no calibrated probability exists.
    """
    nan_series = pd.Series(np.nan, index=df.index)
    prob = pd.to_numeric(df.get("home_cover_prob", nan_series), errors="coerce")
    return prob.where(picks_home_side(df), 1.0 - prob)


def derive_ats_pick(df: pd.DataFrame) -> pd.Series:
    """Resolve the ATS pick to a team abbreviation.

    Args:
        df: Frame with ``home_team``/``away_team`` plus the probability/edge
            columns :func:`picks_home_side` reads.

    Returns:
        Series of team abbreviations. Empty string where ``ATS_PUBLISH_MIN_PROB``
        is set and the picked side's probability does not clear it (that gate is
        off by default, so every row carries a team).
    """
    empty = pd.Series("", index=df.index)
    home = df.get("home_team", empty).fillna("").astype(str)
    away = df.get("away_team", empty).fillna("").astype(str)
    pick = pd.Series(np.where(picks_home_side(df), home, away), index=df.index)

    if ATS_PUBLISH_MIN_PROB is not None:
        pick_prob = picked_side_prob(df)
        pick = pick.where(pick_prob.isna() | (pick_prob >= ATS_PUBLISH_MIN_PROB), "")

    return pick


def _normalize_prediction_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and derive fields for the output schema.

    Maps feature-engineering names (team_home/team_away, model_spread/model_total)
    to the output schema expected by the web API (home_team/away_team,
    predicted_spread/predicted_total, confidence_tier, ats_pick) and blanks the
    retired ``ou_pick`` (see OU_PICK_RETIRED).
    """
    out = df.copy()

    # Rename team columns from feature engineering format
    if "team_home" in out.columns and "home_team" not in out.columns:
        out.rename(columns={"team_home": "home_team", "team_away": "away_team"}, inplace=True)

    # Rename model predictions to predicted_*
    if "model_spread" in out.columns and "predicted_spread" not in out.columns:
        out.rename(columns={"model_spread": "predicted_spread", "model_total": "predicted_total"}, inplace=True)

    # Confidence tier = the SPREAD tier alone. This used to take the better of
    # the spread and total tiers, which let a retired totals edge badge a game
    # "high confidence" beside an ATS pick that had no edge at all. The ATS
    # pick is the only recommendation served, so it is the only thing the tier
    # can describe (TOTALS_VERDICT; see OU_PICK_RETIRED).
    if "spread_confidence_tier" in out.columns and "confidence_tier" not in out.columns:
        tier = out["spread_confidence_tier"]
        out["confidence_tier"] = tier.where(tier.notna(), "low")

    # Calibrated probabilities default to NaN when no calibrator was applied.
    # home_cover_prob drives ats_pick below; over_prob is retained purely as
    # market-tracking content (see OU_PICK_RETIRED). Defaulted before the pick
    # is derived so derive_ats_pick always sees the column.
    for prob_col in ("home_cover_prob", "over_prob"):
        if prob_col not in out.columns:
            out[prob_col] = float("nan")

    # ATS pick follows the calibrated cover probability, falling back to the
    # edge sign when no calibrator ran.
    if "ats_pick" not in out.columns:
        out["ats_pick"] = derive_ats_pick(out)

    # O/U pick retired -- assigned unconditionally, not behind an "if not
    # present" guard: an upstream frame (or a board written before this change)
    # may carry a real side, and this is the single place that can guarantee
    # none ships. See OU_PICK_RETIRED.
    out["ou_pick"] = OU_PICK_RETIRED

    return out


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

    # Classify the confidence tier (apply to raw edge, not abs). Spread only:
    # the O/U pick is retired, so there is no totals tier to compute
    # (TOTALS_VERDICT; see OU_PICK_RETIRED).
    week_df["spread_confidence_tier"] = week_df["spread_edge"].apply(classify_tier)

    # Metadata
    week_df["model_version"] = "v1.4.0"
    week_df["prediction_timestamp"] = datetime.utcnow()

    # Normalize column names for output schema
    week_df = _normalize_prediction_columns(week_df)

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
        tier = row.get("confidence_tier", "-") or "-"

        vegas_sprd = f"{row['vegas_spread']:+.1f}" if pd.notna(row["vegas_spread"]) else "N/A"
        vegas_tot = f"{row['vegas_total']:.1f}" if pd.notna(row["vegas_total"]) else "N/A"
        sprd_edge = f"{row['spread_edge']:+.1f}" if pd.notna(row["spread_edge"]) else "N/A"
        tot_edge = f"{row['total_edge']:+.1f}" if pd.notna(row["total_edge"]) else "N/A"

        print(
            f"{game:<20} {row['predicted_spread']:>+10.1f} {vegas_sprd:>10} {sprd_edge:>10} "
            f"{row['predicted_total']:>9.1f} {vegas_tot:>9} {tot_edge:>9} {tier:>6}"
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
    parser.add_argument(
        "--ensemble",
        action="store_true",
        help="Use stacking ensemble instead of single XGBoost",
    )
    parser.add_argument(
        "--ensemble-dir",
        type=str,
        default=None,
        help="Directory containing ensemble artifacts (default: models/ensemble/)",
    )
    parser.add_argument(
        "--use-sentiment",
        action="store_true",
        help="Apply team sentiment as a post-prediction edge adjustment",
    )
    args = parser.parse_args(argv)

    model_version = "v2.0-ensemble" if args.ensemble else "v1.4.0"
    print(f"\nNFL Game Prediction Pipeline {model_version}")
    print(f"Season: {args.season}, Week: {args.week}")
    if args.ensemble:
        print("Mode: Stacking Ensemble (XGB+LGB+CB+Ridge)")
    print("=" * 60)

    # Assemble features first (needed for both paths)
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

    if args.ensemble:
        # Ensemble path: load ensemble models and generate predictions inline
        print("Loading ensemble models...")
        try:
            spread_models, total_models, ens_metadata = load_ensemble(args.ensemble_dir)
        except FileNotFoundError as e:
            print(f"\nERROR: {e}")
            print("Train the ensemble first: python scripts/train_ensemble.py")
            return 1

        # Get features from ensemble metadata
        ens_feature_cols = ens_metadata.get("selected_features", [])
        ens_available = [c for c in ens_feature_cols if c in game_df.columns]
        if len(ens_available) < len(ens_feature_cols):
            missing = set(ens_feature_cols) - set(ens_available)
            logger.warning(
                "Ensemble: %d/%d features missing: %s",
                len(missing), len(ens_feature_cols), sorted(missing)[:5],
            )

        week_df = game_df[game_df["week"] == args.week].copy()
        if week_df.empty:
            print(f"\nNo games found for week {args.week}.")
            return 0

        features_input = week_df[ens_available].fillna(0.0)
        week_df["model_spread"] = predict_ensemble(features_input, spread_models)
        week_df["model_total"] = predict_ensemble(features_input, total_models)

        # Map Vegas lines and compute edges
        week_df["vegas_spread"] = week_df["spread_line"]
        week_df["vegas_total"] = week_df["total_line"]
        week_df["spread_edge"] = week_df["model_spread"] - week_df["vegas_spread"]
        week_df["total_edge"] = week_df["model_total"] - week_df["vegas_total"]
        week_df["spread_confidence_tier"] = week_df["spread_edge"].apply(classify_tier)

        # Calibrated edge -> probability (trained on leak-free OOF predictions)
        for prob_col, models_dict, edge_col in (
            ("home_cover_prob", spread_models, "spread_edge"),
            ("over_prob", total_models, "total_edge"),
        ):
            calibrator = models_dict.get("calibrator")
            if calibrator is not None:
                edge_vals = week_df[edge_col].fillna(0.0).values.reshape(-1, 1)
                week_df[prob_col] = calibrator.predict_proba(edge_vals)[:, 1].round(4)
            else:
                week_df[prob_col] = float("nan")

        # Tier the ATS pick on the calibrated probability of the side we
        # actually pick (picks_home_side decides it, the same rule
        # derive_ats_pick uses, so tier and pick can never describe different
        # sides). No totals tier: the O/U pick is retired, so there is no
        # picked side to tier (TOTALS_VERDICT; see OU_PICK_RETIRED).
        if week_df["home_cover_prob"].notna().any():
            pick_prob = picked_side_prob(week_df)
            week_df["spread_confidence_tier"] = pick_prob.where(
                week_df["spread_edge"].notna()
            ).apply(classify_tier_prob)

        week_df["model_version"] = model_version
        week_df["prediction_timestamp"] = datetime.utcnow()

        # Normalize column names for output schema
        week_df = _normalize_prediction_columns(week_df)

        # Sort by max edge magnitude
        week_df["_sort_key"] = week_df[["spread_edge", "total_edge"]].abs().max(axis=1)
        week_df = week_df.sort_values("_sort_key", ascending=False, na_position="last")
        predictions = week_df[OUTPUT_COLUMNS].reset_index(drop=True)
    else:
        # Single XGBoost path (unchanged)
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

        # Generate predictions
        predictions = generate_week_predictions(
            game_df, args.week, spread_model, spread_meta, total_model, total_meta
        )

    if predictions.empty:
        print(f"\nNo games found for week {args.week}.")
        return 0

    # Apply team sentiment adjustment if requested
    if args.use_sentiment:
        try:
            from sentiment.aggregation.team_weekly import (
                TeamWeeklyAggregator,
                apply_team_sentiment_adjustment,
            )

            print("\nLoading team sentiment data...")
            team_agg = TeamWeeklyAggregator()
            team_sentiment = team_agg._load_player_sentiment(args.season, args.week)

            if not team_sentiment.empty:
                # Run team aggregation on the fly if needed
                team_df = team_agg.aggregate(
                    season=args.season, week=args.week, dry_run=True
                )
                if not team_df.empty:
                    predictions = apply_team_sentiment_adjustment(
                        predictions, team_df
                    )
                    adj_count = (predictions["sentiment_adjustment"].abs() > 0.001).sum()
                    print(
                        f"  Sentiment adjustment applied to {adj_count}/{len(predictions)} games "
                        f"(max adjustment: {predictions['sentiment_adjustment'].abs().max():.3f} pts)"
                    )
                else:
                    print("  No team sentiment data available -- edges unchanged")
            else:
                print("  No player sentiment data found -- edges unchanged")
        except Exception as exc:
            logger.warning("Sentiment adjustment failed: %s", exc)
            print(f"  WARNING: Sentiment adjustment failed ({exc}) -- edges unchanged")

    # Display results
    _print_predictions_table(predictions)

    # Summary
    n_games = len(predictions)
    high_conf = (predictions["confidence_tier"] == "high").sum()
    print(
        f"\n{n_games} games | {high_conf} high-confidence edges"
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
