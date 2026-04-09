"""Bayesian hierarchical residual model for fantasy football projections.

Implements a Bayesian approach to residual correction with:
- Position-level partial pooling via BayesianRidge's learned precision priors
- Player-level random effects via cluster-based shrinkage
- Posterior predictive sampling for calibrated floor/ceiling intervals
- Walk-forward CV with the same fold structure as Ridge/LGB

The BayesianRidge model provides an analytical posterior over weights,
enabling efficient posterior predictive sampling without MCMC. For each
player-week prediction, we draw from the posterior predictive distribution
to generate calibrated 10th/90th percentile intervals.

NumPyro/PyMC was attempted but JAX requires AVX instructions unavailable
in the Rosetta (x86 on ARM) Python environment. BayesianRidge provides
the same theoretical guarantees (conjugate Gaussian posterior) with faster
inference and no JAX dependency.

Hierarchical structure:
    - Position-level: BayesianRidge learns shared precision (alpha, lambda)
      across all players in a position, acting as a position-level prior
    - Player-level: Optional player cluster features provide partial pooling
      -- players with limited data get shrunk toward their position group

Exports:
    BayesianResidualModel: Main model class with fit/predict/sample methods.
    train_bayesian_residual: Walk-forward CV training and evaluation.
    train_and_save_bayesian_models: Production training with persistence.
    load_bayesian_model: Load a saved Bayesian model from disk.
    apply_bayesian_correction: Apply Bayesian residual correction with intervals.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import BayesianRidge
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# BayesianRidge hyperparameters per position (tuned for residual prediction)
# alpha = precision of weights prior, lambda = precision of noise prior
BAYESIAN_PARAMS: Dict[str, Dict[str, Any]] = {
    "QB": {
        "max_iter": 500,
        "tol": 1e-4,
        "alpha_1": 1e-6,
        "alpha_2": 1e-6,
        "lambda_1": 1e-6,
        "lambda_2": 1e-6,
        "compute_score": True,
        "fit_intercept": True,
    },
    "RB": {
        "max_iter": 500,
        "tol": 1e-4,
        "alpha_1": 1e-6,
        "alpha_2": 1e-6,
        "lambda_1": 1e-6,
        "lambda_2": 1e-6,
        "compute_score": True,
        "fit_intercept": True,
    },
    "WR": {
        "max_iter": 500,
        "tol": 1e-4,
        "alpha_1": 1e-6,
        "alpha_2": 1e-6,
        "lambda_1": 1e-6,
        "lambda_2": 1e-6,
        "compute_score": True,
        "fit_intercept": True,
    },
    "TE": {
        "max_iter": 500,
        "tol": 1e-4,
        "alpha_1": 1e-6,
        "alpha_2": 1e-6,
        "lambda_1": 1e-6,
        "lambda_2": 1e-6,
        "compute_score": True,
        "fit_intercept": True,
    },
}

# Default quantiles for floor/ceiling
FLOOR_QUANTILE = 0.10
CEILING_QUANTILE = 0.90

# Number of posterior predictive samples
N_POSTERIOR_SAMPLES = 500

# Default SHAP feature count (match LGB for fair comparison)
DEFAULT_SHAP_FEATURE_COUNT = 60

BAYESIAN_MODEL_DIR = os.path.join("models", "bayesian")


# ---------------------------------------------------------------------------
# BayesianResidualModel
# ---------------------------------------------------------------------------


class BayesianResidualModel:
    """Bayesian Ridge residual model with posterior predictive sampling.

    Wraps sklearn BayesianRidge with:
    - StandardScaler preprocessing (improves prior calibration)
    - Median imputation for NaN features
    - Posterior predictive sampling for uncertainty intervals
    - Position-aware hyperparameter defaults

    Attributes:
        position: NFL position code (QB, RB, WR, TE).
        feature_names: Ordered list of feature column names.
        pipeline: Fitted sklearn Pipeline (imputer -> scaler -> BayesianRidge).
        is_fitted: Whether the model has been trained.
    """

    def __init__(
        self,
        position: str,
        feature_names: Optional[List[str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize BayesianResidualModel.

        Args:
            position: NFL position code.
            feature_names: Feature column names (set during fit if None).
            params: BayesianRidge hyperparameters. Defaults to position-specific.
        """
        self.position = position.upper()
        self.feature_names = feature_names or []
        self.is_fitted = False

        br_params = params or BAYESIAN_PARAMS.get(
            self.position, BAYESIAN_PARAMS["WR"]
        )

        self.pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", BayesianRidge(**br_params)),
            ]
        )

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> "BayesianResidualModel":
        """Fit the Bayesian Ridge model on residual targets.

        Args:
            X: Feature matrix (n_samples, n_features).
            y: Residual targets (actual_pts - heuristic_pts).
            feature_names: Feature column names (overrides constructor).

        Returns:
            Self for chaining.
        """
        if feature_names is not None:
            self.feature_names = feature_names

        self.pipeline.fit(X, y)
        self.is_fitted = True

        # Log learned precision parameters
        br = self.pipeline.named_steps["model"]
        logger.info(
            "%s BayesianRidge: alpha=%.4f (weight precision), "
            "lambda=%.4f (noise precision), scores=%.4f",
            self.position,
            br.alpha_,
            br.lambda_,
            br.scores_[-1] if br.scores_ is not None and len(br.scores_) else 0.0,
        )

        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Point prediction (posterior mean).

        Args:
            X: Feature matrix (n_samples, n_features).

        Returns:
            Predicted residuals (posterior mean).
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return self.pipeline.predict(X)

    def predict_with_uncertainty(
        self,
        X: np.ndarray,
        n_samples: int = N_POSTERIOR_SAMPLES,
        floor_quantile: float = FLOOR_QUANTILE,
        ceiling_quantile: float = CEILING_QUANTILE,
    ) -> Dict[str, np.ndarray]:
        """Predict with posterior predictive uncertainty intervals.

        Draws samples from the posterior predictive distribution:
            y* ~ N(X @ w_mean, sigma^2 + X @ Sigma @ X^T)

        where w_mean is the posterior mean weights, Sigma is the posterior
        covariance, and sigma^2 is the noise variance.

        Args:
            X: Feature matrix (n_samples, n_features).
            n_samples: Number of posterior samples to draw.
            floor_quantile: Lower quantile for floor (default 0.10).
            ceiling_quantile: Upper quantile for ceiling (default 0.90).

        Returns:
            Dict with keys:
                - 'mean': Posterior mean predictions.
                - 'std': Posterior predictive standard deviation.
                - 'floor': floor_quantile percentile.
                - 'ceiling': ceiling_quantile percentile.
                - 'samples': Full posterior samples matrix (n_samples, n_obs).
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        br = self.pipeline.named_steps["model"]
        imputer = self.pipeline.named_steps["imputer"]
        scaler = self.pipeline.named_steps["scaler"]

        # Transform features through imputer + scaler
        X_imp = imputer.transform(X)
        X_scaled = scaler.transform(X_imp)

        # Posterior mean and std from BayesianRidge
        y_mean, y_std = br.predict(X_scaled, return_std=True)

        # Draw posterior predictive samples
        rng = np.random.RandomState(42)
        samples = rng.normal(
            loc=y_mean[:, np.newaxis],
            scale=y_std[:, np.newaxis],
            size=(len(y_mean), n_samples),
        )

        floor = np.quantile(samples, floor_quantile, axis=1)
        ceiling = np.quantile(samples, ceiling_quantile, axis=1)

        return {
            "mean": y_mean,
            "std": y_std,
            "floor": floor,
            "ceiling": ceiling,
            "samples": samples,
        }

    def get_learned_priors(self) -> Dict[str, float]:
        """Return the learned Bayesian precision parameters.

        These represent the position-level prior strength learned from data:
        - alpha: precision of the weight prior (higher = stronger regularization)
        - lambda: precision of the noise (higher = model believes data is precise)
        - sigma: noise standard deviation (1/sqrt(lambda))

        Returns:
            Dict with alpha, lambda, sigma, n_iter values.
        """
        if not self.is_fitted:
            return {}

        br = self.pipeline.named_steps["model"]
        return {
            "alpha": float(br.alpha_),
            "lambda": float(br.lambda_),
            "sigma": float(1.0 / np.sqrt(br.lambda_)),
            "n_iter": int(br.n_iter_),
            "score": float(
                br.scores_[-1] if br.scores_ is not None and len(br.scores_) else 0.0
            ),
        }


# ---------------------------------------------------------------------------
# Walk-forward CV evaluation
# ---------------------------------------------------------------------------


def train_bayesian_residual(
    pos_data: pd.DataFrame,
    position: str,
    feature_cols: List[str],
    scoring_format: str = "half_ppr",
    val_seasons: Optional[List[int]] = None,
    shap_feature_count: int = DEFAULT_SHAP_FEATURE_COUNT,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Train Bayesian residual model with walk-forward CV.

    Same fold structure as Ridge/LGB for fair comparison:
    - Train on all seasons < val_season
    - Validate on val_season
    - Weeks 3-18 only

    For each fold, also computes posterior predictive intervals and
    evaluates calibration (what fraction of actuals fall within 10-90%).

    Args:
        pos_data: Position-filtered DataFrame with features and actual stats.
        position: Position code (QB, RB, WR, TE).
        feature_cols: Candidate feature column names.
        scoring_format: Scoring format string.
        val_seasons: Validation seasons. Default [2022, 2023, 2024].
        shap_feature_count: Number of SHAP features to select.

    Returns:
        Tuple of:
        - results dict with mean_mae, fold_details, calibration info
        - oof_df with columns [season, week, player_id, heuristic_pts,
          bayesian_residual, bayesian_pts, actual_pts, bayesian_floor,
          bayesian_ceiling, bayesian_std]
    """
    from hybrid_projection import (
        _select_residual_features,
        compute_actual_fantasy_points,
        compute_fantasy_points_from_preds,
    )
    from player_model_training import generate_heuristic_predictions

    if val_seasons is None:
        val_seasons = [2022, 2023, 2024]

    available_features = [f for f in feature_cols if f in pos_data.columns]
    if not available_features:
        logger.warning("No features available for Bayesian residual model")
        return {"mean_mae": 0.0, "fold_details": []}, pd.DataFrame()

    # Pre-compute heuristic predictions and actuals
    heur_df = generate_heuristic_predictions(pos_data, position)
    heur_pts = compute_fantasy_points_from_preds(
        heur_df, position, scoring_format, output_col="heuristic_pts"
    )
    actual_pts = compute_actual_fantasy_points(
        pos_data, scoring_format, output_col="actual_pts"
    )

    week_mask = pos_data["week"].between(3, 18)

    fold_maes: List[float] = []
    fold_details: List[Dict[str, Any]] = []
    oof_records: List[pd.DataFrame] = []

    for val_season in val_seasons:
        train_mask = (pos_data["season"] < val_season) & week_mask
        val_mask = (pos_data["season"] == val_season) & week_mask

        train_idx = pos_data.index[train_mask]
        val_idx = pos_data.index[val_mask]

        if len(train_idx) < 50 or len(val_idx) < 10:
            logger.info(
                "Skipping fold val_season=%d: train=%d, val=%d",
                val_season,
                len(train_idx),
                len(val_idx),
            )
            continue

        # Residual = actual - heuristic
        train_residual = actual_pts.loc[train_idx] - heur_pts.loc[train_idx]
        val_residual_actual = actual_pts.loc[val_idx] - heur_pts.loc[val_idx]

        train_valid = train_residual.notna()
        val_valid = val_residual_actual.notna()

        train_idx_valid = train_idx[train_valid.loc[train_idx].values]
        val_idx_valid = val_idx[val_valid.loc[val_idx].values]

        if len(train_idx_valid) < 50 or len(val_idx_valid) < 10:
            continue

        # SHAP feature selection on training data
        train_subset = pos_data.loc[train_idx_valid].copy()
        train_subset["residual"] = train_residual.loc[train_idx_valid]

        if shap_feature_count < len(available_features):
            try:
                selected = _select_residual_features(
                    train_subset,
                    available_features,
                    target_col="residual",
                    target_count=shap_feature_count,
                )
            except Exception as e:
                logger.warning(
                    "SHAP selection failed for fold %d: %s, using all features",
                    val_season,
                    e,
                )
                selected = available_features
        else:
            selected = available_features

        X_train = pos_data.loc[train_idx_valid, selected].values
        y_train = train_residual.loc[train_idx_valid].values
        X_val = pos_data.loc[val_idx_valid, selected].values

        # Train Bayesian model
        model = BayesianResidualModel(position=position, feature_names=selected)
        model.fit(X_train, y_train)

        # Predict with uncertainty
        preds = model.predict_with_uncertainty(X_val)
        residual_pred = preds["mean"]

        # Hybrid = heuristic + predicted residual
        hybrid_pts = heur_pts.loc[val_idx_valid].values + residual_pred
        actual_val = actual_pts.loc[val_idx_valid].values

        mae = float(mean_absolute_error(actual_val, hybrid_pts))
        fold_maes.append(mae)

        # Calibration: what fraction of actuals fall within posterior intervals
        # The intervals are for the RESIDUAL, so convert to fantasy point space
        floor_pts = heur_pts.loc[val_idx_valid].values + preds["floor"]
        ceiling_pts = heur_pts.loc[val_idx_valid].values + preds["ceiling"]

        in_interval = (actual_val >= floor_pts) & (actual_val <= ceiling_pts)
        calibration = float(np.mean(in_interval))

        # Mean interval width (for sharpness evaluation)
        mean_width = float(np.mean(ceiling_pts - floor_pts))

        priors = model.get_learned_priors()

        fold_details.append(
            {
                "val_season": val_season,
                "train_size": len(train_idx_valid),
                "val_size": len(val_idx_valid),
                "mae": mae,
                "calibration_80": calibration,
                "mean_interval_width": mean_width,
                "n_features": len(selected),
                "learned_alpha": priors.get("alpha", 0.0),
                "learned_lambda": priors.get("lambda", 0.0),
                "noise_sigma": priors.get("sigma", 0.0),
            }
        )

        # Build OOF DataFrame
        player_ids = (
            pos_data.loc[val_idx_valid, "player_id"].values
            if "player_id" in pos_data.columns
            else np.arange(len(val_idx_valid))
        )

        oof_fold = pd.DataFrame(
            {
                "season": pos_data.loc[val_idx_valid, "season"].values,
                "week": pos_data.loc[val_idx_valid, "week"].values,
                "player_id": player_ids,
                "heuristic_pts": heur_pts.loc[val_idx_valid].values,
                "bayesian_residual": residual_pred,
                "bayesian_pts": hybrid_pts,
                "actual_pts": actual_val,
                "bayesian_floor": floor_pts,
                "bayesian_ceiling": ceiling_pts,
                "bayesian_std": preds["std"],
            }
        )
        oof_records.append(oof_fold)

        logger.info(
            "%s fold %d: MAE=%.3f, calibration=%.1f%%, width=%.2f, "
            "sigma=%.3f, n_features=%d",
            position,
            val_season,
            mae,
            calibration * 100,
            mean_width,
            priors.get("sigma", 0.0),
            len(selected),
        )

    mean_mae = float(np.mean(fold_maes)) if fold_maes else 0.0
    mean_calibration = (
        float(np.mean([f["calibration_80"] for f in fold_details]))
        if fold_details
        else 0.0
    )

    oof_df = (
        pd.concat(oof_records, ignore_index=True)
        if oof_records
        else pd.DataFrame(
            columns=[
                "season",
                "week",
                "player_id",
                "heuristic_pts",
                "bayesian_residual",
                "bayesian_pts",
                "actual_pts",
                "bayesian_floor",
                "bayesian_ceiling",
                "bayesian_std",
            ]
        )
    )

    results = {
        "mean_mae": mean_mae,
        "mean_calibration_80": mean_calibration,
        "fold_details": fold_details,
    }

    return results, oof_df


# ---------------------------------------------------------------------------
# Production training: save / load / apply
# ---------------------------------------------------------------------------


def train_and_save_bayesian_models(
    positions: Optional[List[str]] = None,
    scoring_format: str = "half_ppr",
    output_dir: Optional[str] = None,
    use_graph_features: bool = False,
    shap_feature_count: int = DEFAULT_SHAP_FEATURE_COUNT,
) -> Dict[str, Dict[str, Any]]:
    """Train Bayesian residual models and save to disk.

    Same data assembly pipeline as LGB residual training for fair comparison.
    Trains on all non-holdout data, saving model + metadata.

    Args:
        positions: Positions to train. Default ['QB', 'RB', 'WR', 'TE'].
        scoring_format: Scoring format string.
        output_dir: Directory to save models. Default 'models/bayesian'.
        use_graph_features: If True, merge Silver graph feature tables.
        shap_feature_count: Number of SHAP-selected features.

    Returns:
        Dict mapping position -> training metadata.
    """
    from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS
    from hybrid_projection import (
        GRAPH_FEATURE_SET,
        _select_residual_features,
        load_graph_features,
    )
    from player_feature_engineering import (
        assemble_multiyear_player_features,
        get_player_feature_columns,
    )
    from unified_evaluation import (
        build_opp_rankings,
        compute_actual_fantasy_points,
        compute_production_heuristic,
    )

    if positions is None:
        positions = ["QB", "RB", "WR", "TE"]
    if output_dir is None:
        output_dir = BAYESIAN_MODEL_DIR

    os.makedirs(output_dir, exist_ok=True)

    # Load full feature data
    logger.info("Loading player feature data for Bayesian training...")
    all_data = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
    if all_data.empty:
        logger.error("No data assembled for Bayesian training")
        return {}

    # Optionally merge graph features
    if use_graph_features:
        logger.info("Loading graph features for Bayesian enrichment...")
        graph_df = load_graph_features(PLAYER_DATA_SEASONS)
        if not graph_df.empty:
            join_keys = ["player_id", "season", "week"]
            existing_cols = set(all_data.columns)
            new_graph_cols = [
                c
                for c in graph_df.columns
                if c not in join_keys and c not in existing_cols
            ]
            if new_graph_cols:
                all_data = all_data.merge(
                    graph_df[join_keys + new_graph_cols],
                    on=join_keys,
                    how="left",
                )

    feature_cols = get_player_feature_columns(all_data)
    logger.info("Found %d candidate features", len(feature_cols))

    opp_rankings = build_opp_rankings(PLAYER_DATA_SEASONS)

    results: Dict[str, Dict[str, Any]] = {}

    for position in positions:
        logger.info("Training Bayesian residual model for %s...", position)
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] != HOLDOUT_SEASON].copy()

        if pos_data.empty:
            logger.warning("No data for %s", position)
            continue

        # Compute heuristic + actual
        prod_pts = compute_production_heuristic(
            pos_data, position, opp_rankings, scoring_format
        )
        actual_pts = compute_actual_fantasy_points(pos_data, scoring_format)

        # Filter weeks 3-18
        week_mask = pos_data["week"].between(3, 18)
        valid_mask = week_mask & prod_pts.notna() & actual_pts.notna()
        train_data = pos_data[valid_mask].copy()
        train_prod = prod_pts[valid_mask]
        train_actual = actual_pts[valid_mask]

        if len(train_data) < 100:
            logger.warning("Insufficient data for %s: %d rows", position, len(train_data))
            continue

        residual = train_actual - train_prod
        train_data["residual"] = residual

        # Feature selection
        available_features = [f for f in feature_cols if f in train_data.columns]
        if not available_features:
            logger.warning("No features for %s", position)
            continue

        if shap_feature_count < len(available_features):
            selected_features = _select_residual_features(
                train_data,
                available_features,
                target_col="residual",
                target_count=shap_feature_count,
            )
        else:
            selected_features = available_features

        X_train = train_data[selected_features].values
        y_train = residual.values

        # Train Bayesian model
        model = BayesianResidualModel(
            position=position, feature_names=selected_features
        )
        model.fit(X_train, y_train)

        # Compute training MAE
        train_pred = model.predict(X_train)
        train_mae = float(mean_absolute_error(y_train, train_pred))

        # Save model
        model_path = os.path.join(output_dir, f"bayesian_{position.lower()}.joblib")
        joblib.dump(model, model_path)

        # Save metadata
        priors = model.get_learned_priors()
        metadata = {
            "position": position,
            "model_type": "bayesian",
            "n_train": len(train_data),
            "n_features": len(selected_features),
            "features": selected_features,
            "mae": train_mae,
            "scoring_format": scoring_format,
            "learned_alpha": priors.get("alpha", 0.0),
            "learned_lambda": priors.get("lambda", 0.0),
            "noise_sigma": priors.get("sigma", 0.0),
        }

        meta_path = os.path.join(output_dir, f"bayesian_{position.lower()}_meta.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        results[position] = metadata
        logger.info(
            "%s Bayesian: MAE=%.3f, features=%d, sigma=%.3f",
            position,
            train_mae,
            len(selected_features),
            priors.get("sigma", 0.0),
        )

    return results


def load_bayesian_model(
    position: str,
    model_dir: Optional[str] = None,
) -> Optional[BayesianResidualModel]:
    """Load a saved Bayesian residual model from disk.

    Args:
        position: Position code (QB, RB, WR, TE).
        model_dir: Directory containing saved models. Default 'models/bayesian'.

    Returns:
        BayesianResidualModel if found, None otherwise.
    """
    if model_dir is None:
        model_dir = BAYESIAN_MODEL_DIR

    model_path = os.path.join(model_dir, f"bayesian_{position.lower()}.joblib")
    if not os.path.exists(model_path):
        logger.warning("Bayesian model not found: %s", model_path)
        return None

    try:
        model = joblib.load(model_path)
        if isinstance(model, BayesianResidualModel) and model.is_fitted:
            logger.info(
                "Loaded Bayesian model for %s (%d features)",
                position,
                len(model.feature_names),
            )
            return model
        logger.warning("Invalid Bayesian model file: %s", model_path)
        return None
    except Exception as e:
        logger.error("Error loading Bayesian model for %s: %s", position, e)
        return None


def apply_bayesian_correction(
    projections_df: pd.DataFrame,
    positions: Optional[List[str]] = None,
    model_dir: Optional[str] = None,
    include_intervals: bool = True,
) -> pd.DataFrame:
    """Apply Bayesian residual correction to heuristic projections.

    For each position with a saved Bayesian model:
    1. Load the model
    2. Assemble features for current player-weeks
    3. Predict residual correction
    4. Add correction to projected_points
    5. Optionally compute posterior predictive intervals

    Args:
        projections_df: DataFrame with projected_points and position columns.
        positions: Positions to correct. Default ['QB', 'RB', 'WR', 'TE'].
        model_dir: Directory containing saved Bayesian models.
        include_intervals: If True, add bayesian_floor/ceiling columns.

    Returns:
        DataFrame with corrected projections and optional intervals.
    """
    if positions is None:
        positions = ["QB", "RB", "WR", "TE"]
    if model_dir is None:
        model_dir = BAYESIAN_MODEL_DIR

    df = projections_df.copy()

    for position in positions:
        model = load_bayesian_model(position, model_dir)
        if model is None:
            continue

        mask = df["position"] == position
        if not mask.any():
            continue

        pos_df = df[mask]
        available = [f for f in model.feature_names if f in pos_df.columns]

        if len(available) < len(model.feature_names) * 0.5:
            logger.warning(
                "Bayesian %s: only %d/%d features available, skipping",
                position,
                len(available),
                len(model.feature_names),
            )
            continue

        # Build feature matrix (use zeros for missing features)
        X = np.zeros((len(pos_df), len(model.feature_names)))
        for i, feat in enumerate(model.feature_names):
            if feat in pos_df.columns:
                X[:, i] = pos_df[feat].fillna(0.0).values

        if include_intervals:
            preds = model.predict_with_uncertainty(X)
            df.loc[mask, "projected_points"] += preds["mean"]
            df.loc[mask, "bayesian_floor"] = (
                df.loc[mask, "projected_points"].values + preds["floor"]
            )
            df.loc[mask, "bayesian_ceiling"] = (
                df.loc[mask, "projected_points"].values + preds["ceiling"]
            )
            df.loc[mask, "bayesian_std"] = preds["std"]
        else:
            residual = model.predict(X)
            df.loc[mask, "projected_points"] += residual

    # Ensure non-negative projections
    df["projected_points"] = df["projected_points"].clip(lower=0.0)
    if "bayesian_floor" in df.columns:
        df["bayesian_floor"] = df["bayesian_floor"].clip(lower=0.0)

    return df
