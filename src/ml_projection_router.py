"""ML Projection Router: routes per-position predictions to ML or heuristic.

Reads the ship gate report to determine which positions use ML models
(verdict=SHIP) and which fall back to the heuristic projection engine
(verdict=SKIP). For WR/TE, applies hybrid residual correction on top of
heuristic projections. Provides MAPIE confidence intervals for ML positions
and team-total coherence checks.

Routing (v3):
    QB -> Heuristic + Residual correction (HYBRID, v2 pruned LGB)
    RB -> Heuristic + Residual correction (HYBRID, v2 pruned LGB)
    WR -> Heuristic + Residual correction (HYBRID)
    TE -> Heuristic + Residual correction (HYBRID)

Exports:
    generate_ml_projections: Main entry point for mixed ML/heuristic projections.
    check_team_total_coherence: Warn when team fantasy totals exceed implied total.
    compute_mapie_intervals: MAPIE-based prediction intervals (optional dependency).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from projection_engine import (
    POSITION_STAT_PROFILE,
    add_floor_ceiling,
    apply_team_constraints,
    generate_weekly_projections,
)
from player_model_training import (
    get_stat_type,
    load_player_model,
    predict_player_stats,
)
from scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)

# Positions using hybrid residual correction (heuristic + LightGBM residual).
# Phase 55: LGB residual with SHAP-60 features improves WR/TE over heuristic.
#
# v4.1 Phase 1 INVESTIGATION: RB and QB routing attempted but both reverted.
#   RB: 2025 holdout degraded MAE 5.39 -> 5.98 (upward bias from full feature set).
#   QB: 2025 holdout catastrophically degraded MAE 8.64 -> 16.15 (unstable extrapolation
#       on travel_miles, temperature features + duplicate-row bug in merge path).
#
# v4.1 Phase 2 PARTIAL SHIP:
#   RB v2: 5.39 -> 5.42 MAE (deduplicated 2025 backtest), Bias=+0.06 — SHIP
#     (training holdout 2.44 MAE reflects a narrower eval slice; production
#     result is approximately parity with heuristic, bias near-zero — acceptable)
#   QB v2: 2025 full-season backtest shows Bias=+11.33 (mean correction +11.82).
#     Model massively over-corrects every QB despite top-20 pruning. Root cause:
#     QB residuals are non-stationary across seasons; pruned features still drive
#     unstable extrapolation. QB stays on heuristic until bias is corrected.
# Models: models/residual/rb_residual_{lgb,imputer}_v2.pkl (promoted to production)
#         models/residual/qb_residual_{lgb,imputer}_v2.pkl (saved, not activated)
HYBRID_POSITIONS = {"WR", "TE"}  # v4.1-p3: RB reverted from v2 pending bisect on MAE regression

# ---------------------------------------------------------------------------
# MAPIE optional import
# ---------------------------------------------------------------------------
try:
    from mapie.regression import MapieRegressor  # type: ignore[import-untyped]

    HAS_MAPIE = True
except ImportError:
    HAS_MAPIE = False


# ---------------------------------------------------------------------------
# Ship gate loading
# ---------------------------------------------------------------------------


def _load_ship_gate(model_dir: str = "models/player") -> Dict[str, str]:
    """Read ship_gate_report.json and return per-position verdicts.

    If QB is absent from the report but QB model files exist on disk,
    QB is inferred as SHIP (models were trained successfully in Phase 41
    but QB was excluded from the ship gate evaluation pipeline).

    Args:
        model_dir: Base directory containing ship_gate_report.json and
            position subdirectories with model files.

    Returns:
        Dict mapping position code to verdict string ('SHIP' or 'SKIP').
        Empty dict if report file is missing.
    """
    report_path = os.path.join(model_dir, "ship_gate_report.json")

    if not os.path.exists(report_path):
        logger.warning(
            "Ship gate report not found at %s; falling back to full heuristic",
            report_path,
        )
        return {}

    with open(report_path, "r") as f:
        report = json.load(f)

    verdicts: Dict[str, str] = {}
    for entry in report.get("positions", []):
        verdicts[entry["position"]] = entry["verdict"]

    # Infer QB SHIP if models exist on disk but QB not in report
    if "QB" not in verdicts:
        qb_model_path = os.path.join(model_dir, "qb", "passing_yards.json")
        if os.path.exists(qb_model_path):
            verdicts["QB"] = "SHIP"
            logger.info("QB models found on disk; inferring SHIP verdict")
        else:
            logger.info("No QB models found; QB will use heuristic")

    # NOTE: RB SHIP override disabled (Exp 4b — 2026-04-13).
    # Production 2022-2024 backtest shows RB XGBoost (5.25 MAE) is worse than
    # heuristic-only (5.00 MAE). The "3.27 vs 5.06" experiment result was from
    # an earlier, stale ship gate and does not reflect current production.
    # RB now respects the ship gate SKIP verdict (pure heuristic).
    # if verdicts.get("RB") == "SKIP":
    #     rb_model_path = os.path.join(model_dir, "rb", "rushing_yards.json")
    #     if os.path.exists(rb_model_path):
    #         verdicts["RB"] = "SHIP"
    #         logger.info("RB promoted to SHIP (XGB MAE < heuristic MAE)")

    # NOTE: WR/TE HYBRID override disabled (Exp 4 — 2026-04-13).
    # Production evaluation showed the Ridge residual correction degrades MAE
    # by +0.44 pts overall vs heuristic-only (WR: +0.58, TE: +0.43) because
    # the models systematically over-correct: mean correction +0.80 vs actual
    # heuristic bias of only -0.38. The ship gate's SKIP verdict is correct.
    # WR/TE now follow the ship gate (SKIP → pure heuristic).
    # Preserved in HYBRID_POSITIONS constant for future experimentation.

    return verdicts


# ---------------------------------------------------------------------------
# Fallback player detection
# ---------------------------------------------------------------------------


def _is_fallback_player(row: pd.Series, min_games: int = 3) -> bool:
    """Determine if a player should fall back to heuristic projections.

    A player is a fallback candidate if:
    (a) All rolling feature columns (roll3/roll6) are NaN -- indicates a rookie
        or player with no recent history.
    (b) The player has fewer than min_games games played.

    Args:
        row: A single player row from Silver-layer DataFrame.
        min_games: Minimum games played to trust ML predictions. Default 3.

    Returns:
        True if player should use heuristic fallback.
    """
    # Check rolling columns
    rolling_cols = [c for c in row.index if "roll3" in c or "roll6" in c]
    if rolling_cols:
        rolling_values = row[rolling_cols]
        if rolling_values.isna().all():
            return True

    # Check games played threshold
    games_col = None
    for candidate in ["games_played", "game_count", "n_games"]:
        if candidate in row.index:
            games_col = candidate
            break

    if games_col is not None:
        games = row[games_col]
        if pd.notna(games) and games < min_games:
            return True

    return False


# ---------------------------------------------------------------------------
# MAPIE confidence intervals
# ---------------------------------------------------------------------------


def compute_mapie_intervals(
    model: Any,
    X_train: Any,
    y_train: Any,
    X_predict: Any,
    alpha: float = 0.20,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Compute MAPIE prediction intervals for a pre-fit model.

    Uses MapieRegressor with method='plus' and cv='prefit' to wrap an
    already-trained model. The calibration step uses X_train/y_train
    residuals to estimate prediction intervals without retraining.

    Args:
        model: Pre-fitted sklearn-compatible estimator.
        X_train: Training features for calibration (residual estimation).
        y_train: Training targets for calibration.
        X_predict: Features to generate intervals for.
        alpha: Significance level. 0.20 gives 80% prediction interval.

    Returns:
        Tuple of (point_predictions, lower_bounds, upper_bounds) as numpy
        arrays, or None if MAPIE is not available or an error occurs.
    """
    if not HAS_MAPIE:
        return None

    try:
        mapie = MapieRegressor(estimator=model, method="plus", cv="prefit")
        mapie.fit(X_train, y_train)
        preds, intervals = mapie.predict(X_predict, alpha=alpha)
        lower = intervals[:, 0, 0]
        upper = intervals[:, 1, 0]
        return preds, lower, upper
    except Exception as e:
        logger.warning("MAPIE interval computation failed: %s; using heuristic", e)
        return None


# ---------------------------------------------------------------------------
# Fantasy interval computation from stat-level intervals
# ---------------------------------------------------------------------------


def compute_fantasy_intervals(
    stat_intervals: Dict[str, Tuple[float, float, float]],
    scoring_format: str = "half_ppr",
) -> Tuple[float, float, float]:
    """Compute floor/ceiling fantasy points from per-stat intervals.

    Floor uses lower bounds for positive stats and upper bound for
    interceptions (worst case). Ceiling uses upper bounds for positive
    stats and lower bound for interceptions (best case).

    Args:
        stat_intervals: Dict mapping stat name to (point, lower, upper).
        scoring_format: Fantasy scoring format for point calculation.

    Returns:
        Tuple of (projected_points, projected_floor, projected_ceiling).
    """
    negative_stats = {"interceptions", "fumbles_lost"}

    floor_stats = {}
    ceiling_stats = {}
    point_stats = {}

    for stat, (point, lower, upper) in stat_intervals.items():
        point_stats[stat] = point
        if stat in negative_stats:
            # For negative stats: floor uses upper (more INTs), ceiling uses lower
            floor_stats[stat] = upper
            ceiling_stats[stat] = lower
        else:
            floor_stats[stat] = max(0.0, lower)
            ceiling_stats[stat] = upper

    # Convert to DataFrames for calculate_fantasy_points_df
    point_df = pd.DataFrame([point_stats])
    floor_df = pd.DataFrame([floor_stats])
    ceiling_df = pd.DataFrame([ceiling_stats])

    pts = calculate_fantasy_points_df(point_df, scoring_format, output_col="pts")[
        "pts"
    ].iloc[0]
    floor_pts = calculate_fantasy_points_df(floor_df, scoring_format, output_col="pts")[
        "pts"
    ].iloc[0]
    ceiling_pts = calculate_fantasy_points_df(
        ceiling_df, scoring_format, output_col="pts"
    )["pts"].iloc[0]

    return float(pts), float(floor_pts), float(ceiling_pts)


# ---------------------------------------------------------------------------
# Feature column loading
# ---------------------------------------------------------------------------


def _load_feature_cols(model_dir: str) -> Dict[str, List[str]]:
    """Load feature columns per stat-type group from feature_selection directory.

    Args:
        model_dir: Base model directory containing feature_selection/ subdir.

    Returns:
        Dict mapping stat-type group name to list of feature column names.
    """
    fs_dir = os.path.join(model_dir, "feature_selection")
    result: Dict[str, List[str]] = {}

    for group in ["yardage", "td", "volume", "turnover"]:
        path = os.path.join(fs_dir, f"{group}_features.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            # Feature files may be either a bare list or {"group": ..., "features": [...]}.
            if isinstance(data, dict) and "features" in data:
                result[group] = list(data["features"])
            elif isinstance(data, list):
                result[group] = list(data)
            else:
                logger.warning(
                    "Unexpected feature file format at %s; treating as empty", path
                )
                result[group] = []
        else:
            logger.warning("Feature file not found: %s", path)
            result[group] = []

    return result


# ---------------------------------------------------------------------------
# Team-total coherence check
# ---------------------------------------------------------------------------


def check_team_total_coherence(
    projections: pd.DataFrame,
    implied_totals: Optional[Dict[str, float]],
    threshold: float = 1.10,
) -> List[str]:
    """Check if projected fantasy points exceed implied team totals.

    For each team in implied_totals, sums projected_points of all team
    players. If the sum exceeds implied_total * threshold, a warning
    string is appended. No adjustments are made to projections.

    Args:
        projections: DataFrame with 'recent_team' and 'projected_points'.
        implied_totals: Dict of {team_abbr: implied_points}. If None,
            returns empty list.
        threshold: Multiplier threshold (default 1.10 = 110%).

    Returns:
        List of warning strings for teams exceeding threshold.
    """
    if implied_totals is None or projections.empty:
        return []

    if (
        "recent_team" not in projections.columns
        or "projected_points" not in projections.columns
    ):
        return []

    warnings: List[str] = []
    team_sums = projections.groupby("recent_team")["projected_points"].sum()

    for team, implied in implied_totals.items():
        if team in team_sums.index:
            total = team_sums[team]
            limit = implied * threshold
            if total > limit:
                warnings.append(
                    f"Team {team}: projected {total:.1f} fantasy pts exceeds "
                    f"{threshold:.0%} of implied total {implied:.1f} "
                    f"(limit {limit:.1f})"
                )

    return warnings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_ml_projections(
    silver_df: pd.DataFrame,
    opp_rankings: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
    schedules_df: Optional[pd.DataFrame] = None,
    implied_totals: Optional[Dict[str, float]] = None,
    model_dir: str = "models/player",
    apply_constraints: bool = False,
    feature_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Generate projections routing each position to ML or heuristic.

    Reads the ship gate report to determine routing. Positions with
    verdict=SHIP use ML models; verdict=SKIP use the heuristic engine.
    Individual players within SHIP positions may still fall back to
    heuristic if they lack sufficient data (rookies, <3 games).

    Output schema matches generate_weekly_projections() with an
    additional 'projection_source' column ('ml' or 'heuristic').

    Args:
        silver_df: Silver-layer DataFrame (all positions, rolling features).
        opp_rankings: Opponent positional rankings (Silver layer).
        season: NFL season year.
        week: NFL week number (the week being projected).
        scoring_format: Fantasy scoring format.
        schedules_df: Optional game schedule DataFrame for bye detection.
        implied_totals: Optional dict of {team: implied_points}.
        model_dir: Base directory for models and ship gate report.
        apply_constraints: If True and implied_totals is provided, apply
            team-level constraints via ``apply_team_constraints()``
            after all projections are merged. Default False.
        feature_df: Optional full-feature DataFrame from
            ``assemble_multiyear_player_features()``. When provided,
            HYBRID positions use this richer feature set for residual
            correction instead of the basic silver_df features.

    Returns:
        Combined projections DataFrame sorted by projected_points desc,
        with projection_source column indicating 'ml', 'hybrid', or 'heuristic'.
    """
    verdicts = _load_ship_gate(model_dir)

    # If no ship gate report, fall back to full heuristic
    if not verdicts:
        logger.warning("No ship gate verdicts; using full heuristic projections")
        result = generate_weekly_projections(
            silver_df,
            opp_rankings,
            season,
            week,
            scoring_format,
            schedules_df,
            implied_totals,
        )
        result = add_floor_ceiling(result)
        result["projection_source"] = "heuristic"
        return result

    # Separate positions by verdict
    ship_positions = [p for p, v in verdicts.items() if v == "SHIP"]
    skip_positions = [p for p, v in verdicts.items() if v == "SKIP"]
    hybrid_positions = [p for p, v in verdicts.items() if v == "HYBRID"]

    # Also include any position not in verdicts as skip (defensive)
    all_positions = list(POSITION_STAT_PROFILE.keys())
    for pos in all_positions:
        if pos not in verdicts:
            skip_positions.append(pos)

    all_projections: List[pd.DataFrame] = []

    # ---- Generate heuristic projections once (needed for SKIP + HYBRID) ----
    need_heuristic = bool(skip_positions or hybrid_positions)
    heuristic_all = pd.DataFrame()
    if need_heuristic:
        heuristic_all = generate_weekly_projections(
            silver_df,
            opp_rankings,
            season,
            week,
            scoring_format,
            schedules_df,
            implied_totals,
        )
        heuristic_all = add_floor_ceiling(heuristic_all)

    # ---- Heuristic positions (SKIP) ----
    if skip_positions and not heuristic_all.empty:
        heuristic_result = heuristic_all[
            heuristic_all["position"].isin(skip_positions)
        ].copy()
        heuristic_result["projection_source"] = "heuristic"
        if not heuristic_result.empty:
            all_projections.append(heuristic_result)

    # ---- Hybrid positions (heuristic + residual correction) ----
    if hybrid_positions and not heuristic_all.empty:
        from hybrid_projection import apply_residual_correction

        for position in hybrid_positions:
            hybrid_result = heuristic_all[heuristic_all["position"] == position].copy()
            if hybrid_result.empty:
                continue

            # Get feature data for these players — prefer full feature_df
            feat_source = feature_df if feature_df is not None else silver_df
            target_df = feat_source[
                (feat_source["season"] == season)
                & (feat_source["week"] == week - 1)
                & (feat_source["position"] == position)
            ]
            if target_df.empty:
                latest = feat_source[
                    (feat_source["season"] == season)
                    & (feat_source["position"] == position)
                ]["week"].max()
                if pd.notna(latest):
                    target_df = feat_source[
                        (feat_source["season"] == season)
                        & (feat_source["week"] == latest)
                        & (feat_source["position"] == position)
                    ]

            if not target_df.empty:
                # Determine residual model directory
                residual_dir = os.path.join(
                    os.path.dirname(model_dir) if "player" in model_dir else model_dir,
                    "residual",
                )
                hybrid_result = apply_residual_correction(
                    hybrid_result, target_df, position, model_dir=residual_dir
                )

            # Recalculate floor/ceiling after correction
            hybrid_result = add_floor_ceiling(hybrid_result)
            hybrid_result["projection_source"] = "hybrid"
            all_projections.append(hybrid_result)

    # ---- ML positions (SHIP) ----
    # XGBoost SHIP models expect the full assembled feature vector (80+ columns
    # including QBR fields). feature_df, when provided by the caller via
    # assemble_player_features(), contains all required columns. Without it,
    # models would receive only silver_df columns and throw a feature_names
    # mismatch error. The feature_df is filtered inside _generate_ml_for_position
    # to week-1 (prior week) to maintain temporal integrity.
    for position in ship_positions:
        ml_result = _generate_ml_for_position(
            silver_df=silver_df,
            opp_rankings=opp_rankings,
            season=season,
            week=week,
            position=position,
            scoring_format=scoring_format,
            schedules_df=schedules_df,
            implied_totals=implied_totals,
            model_dir=model_dir,
            feature_df=feature_df,
        )
        if ml_result is not None and not ml_result.empty:
            all_projections.append(ml_result)

    if not all_projections:
        logger.warning("No projections generated from any source")
        return pd.DataFrame()

    combined = pd.concat(all_projections, ignore_index=True)

    # Ensure standard output columns exist
    for col in ["projected_floor", "projected_ceiling"]:
        if col not in combined.columns:
            combined[col] = np.nan

    # Sort and rank
    combined = combined.sort_values("projected_points", ascending=False).reset_index(
        drop=True
    )
    if "position_rank" not in combined.columns:
        combined["position_rank"] = (
            combined.groupby("position")["projected_points"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
    combined["overall_rank"] = range(1, len(combined) + 1)

    # Team constraints (opt-in)
    if apply_constraints and implied_totals is not None:
        combined = apply_team_constraints(
            combined,
            implied_totals,
            scoring_format=scoring_format,
        )
        logger.info("Team constraints applied to ML projections")

    # Team-total coherence check
    warnings = check_team_total_coherence(combined, implied_totals)
    for w in warnings:
        logger.warning(w)

    return combined


# ---------------------------------------------------------------------------
# Per-position ML projection
# ---------------------------------------------------------------------------


def _generate_ml_for_position(
    silver_df: pd.DataFrame,
    opp_rankings: pd.DataFrame,
    season: int,
    week: int,
    position: str,
    scoring_format: str = "half_ppr",
    schedules_df: Optional[pd.DataFrame] = None,
    implied_totals: Optional[Dict[str, float]] = None,
    model_dir: str = "models/player",
    feature_df: Optional[pd.DataFrame] = None,
) -> Optional[pd.DataFrame]:
    """Generate ML projections for a single SHIP position.

    Players who are fallback candidates (rookies, <3 games) are routed
    to the heuristic engine instead.

    Args:
        silver_df: Silver-layer DataFrame (used for heuristic fallback and
            player identification when feature_df is not provided).
        opp_rankings: Opponent rankings.
        season: Season year.
        week: Projection week.
        position: Position code (e.g., 'QB').
        scoring_format: Scoring format.
        schedules_df: Schedule for bye detection.
        implied_totals: Team implied totals.
        model_dir: Model directory.
        feature_df: Optional full assembled feature DataFrame from
            ``assemble_player_features()``. When provided, used as the ML
            feature source instead of silver_df. This is required for
            positions (e.g., QB) whose models expect QBR columns that are
            absent from silver_df but present in the assembled feature vector.
            silver_df is still used for heuristic fallback routing.

    Returns:
        DataFrame with projections, or None on failure.
    """
    try:
        # Select the feature source: prefer assembled feature_df when available,
        # fall back to silver_df. Both are filtered to week-1 (prior week) to
        # prevent same-week leakage.
        feat_source = feature_df if feature_df is not None else silver_df

        # Filter to position, use week-1 as feature source
        target_df = feat_source[
            (feat_source["season"] == season)
            & (feat_source["week"] == week - 1)
            & (feat_source["position"] == position)
        ].copy()

        if target_df.empty:
            # Fallback: most recent week
            latest = feat_source[
                (feat_source["season"] == season) & (feat_source["position"] == position)
            ]["week"].max()
            if pd.notna(latest):
                target_df = feat_source[
                    (feat_source["season"] == season)
                    & (feat_source["week"] == latest)
                    & (feat_source["position"] == position)
                ].copy()

        if target_df.empty:
            logger.warning("No data for %s in season %d; skipping ML", position, season)
            return None

        # Identify fallback players
        fallback_mask = target_df.apply(_is_fallback_player, axis=1)
        ml_players = target_df[~fallback_mask].copy()
        fallback_players = target_df[fallback_mask].copy()

        results: List[pd.DataFrame] = []

        # ---- ML predictions for eligible players ----
        if not ml_players.empty:
            feature_cols = _load_feature_cols(model_dir)
            stats = POSITION_STAT_PROFILE.get(position, [])

            # Load models
            model_dict: Dict[str, Dict[str, Any]] = {}
            for stat in stats:
                try:
                    model = load_player_model(position, stat, model_dir)
                    model_dict[stat] = {"model": model}
                except Exception as e:
                    logger.warning("Could not load %s/%s model: %s", position, stat, e)

            if not model_dict:
                logger.warning("No models loaded for %s; using heuristic", position)
                # Fall through to heuristic for all players
                fallback_players = target_df.copy()
            else:
                # Predict
                pred_df = predict_player_stats(
                    model_dict, ml_players, position, feature_cols
                )

                # Rename pred_{stat} to proj_{stat} for output consistency
                rename_map = {}
                for stat in stats:
                    pred_col = f"pred_{stat}"
                    proj_col = f"proj_{stat}"
                    if pred_col in pred_df.columns:
                        rename_map[pred_col] = proj_col
                pred_df = pred_df.rename(columns=rename_map)

                # Calculate fantasy points from predicted stats.
                # Build a clean scoring frame from ONLY the proj_{stat} columns —
                # renaming in-place would collide with raw {stat} columns already
                # present in pred_df (merged from silver_df), yielding duplicate
                # column names that break calculate_fantasy_points_df with
                # "'<' not supported between str and int" via pandas index join.
                scoring_data = {}
                for s in stats:
                    proj_col = f"proj_{s}"
                    if proj_col in pred_df.columns:
                        scoring_data[s] = pred_df[proj_col].values
                scoring_input = pd.DataFrame(scoring_data, index=pred_df.index)
                scoring_input = calculate_fantasy_points_df(
                    scoring_input,
                    scoring_format=scoring_format,
                    output_col="projected_points",
                )

                # Build output
                ml_out = pd.DataFrame()
                for col in ["player_id", "player_name", "position", "recent_team"]:
                    if col in pred_df.columns:
                        ml_out[col] = pred_df[col].values

                for stat in stats:
                    proj_col = f"proj_{stat}"
                    if proj_col in pred_df.columns:
                        ml_out[proj_col] = pred_df[proj_col].values

                ml_out["projected_points"] = scoring_input["projected_points"].values

                # MAPIE intervals or heuristic floor/ceiling
                if HAS_MAPIE:
                    # Attempt MAPIE intervals per stat
                    _apply_mapie_intervals(
                        ml_out,
                        model_dict,
                        ml_players,
                        feature_cols,
                        position,
                        scoring_format,
                    )
                else:
                    ml_out = add_floor_ceiling(ml_out)

                ml_out["projection_source"] = "ml"
                results.append(ml_out)

        # ---- Heuristic fallback for rookies/thin-data ----
        if not fallback_players.empty:
            heuristic_all = generate_weekly_projections(
                silver_df,
                opp_rankings,
                season,
                week,
                scoring_format,
                schedules_df,
                implied_totals,
            )
            heuristic_all = add_floor_ceiling(heuristic_all)
            fallback_ids = set(fallback_players["player_id"].values)
            heuristic_pos = heuristic_all[
                (heuristic_all["position"] == position)
                & (heuristic_all["player_id"].isin(fallback_ids))
            ].copy()
            heuristic_pos["projection_source"] = "heuristic"
            if not heuristic_pos.empty:
                results.append(heuristic_pos)

        if not results:
            return None

        return pd.concat(results, ignore_index=True)

    except Exception as e:
        logger.error(
            "ML projection failed for %s: %s; falling back to heuristic", position, e
        )
        # Full heuristic fallback on error
        heuristic = generate_weekly_projections(
            silver_df,
            opp_rankings,
            season,
            week,
            scoring_format,
            schedules_df,
            implied_totals,
        )
        heuristic = add_floor_ceiling(heuristic)
        heuristic = heuristic[heuristic["position"] == position].copy()
        heuristic["projection_source"] = "heuristic"
        return heuristic


def _apply_mapie_intervals(
    ml_out: pd.DataFrame,
    model_dict: Dict[str, Dict[str, Any]],
    ml_players: pd.DataFrame,
    feature_cols: Dict[str, List[str]],
    position: str,
    scoring_format: str,
) -> None:
    """Apply MAPIE intervals to ML output in-place, falling back to heuristic.

    Attempts to compute per-stat MAPIE intervals and derive fantasy point
    floor/ceiling. If MAPIE fails for any reason, falls back to
    add_floor_ceiling heuristic.

    Args:
        ml_out: ML output DataFrame (modified in-place).
        model_dict: Dict of stat -> {model: ...}.
        ml_players: Player feature DataFrame.
        feature_cols: Feature columns per stat-type group.
        position: Position code.
        scoring_format: Scoring format for fantasy point calc.
    """
    # For now, use heuristic floor/ceiling as MAPIE calibration requires
    # training data which may not be available at inference time.
    # The compute_mapie_intervals function is available for callers who
    # have training data.
    temp = add_floor_ceiling(ml_out)
    ml_out["projected_floor"] = temp["projected_floor"]
    ml_out["projected_ceiling"] = temp["projected_ceiling"]
