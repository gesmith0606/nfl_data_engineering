#!/usr/bin/env python3
"""Train ensemble prediction models (XGBoost + LightGBM + CatBoost + Ridge).

Trains stacking ensemble for both spread and total targets using walk-forward
CV with out-of-fold predictions. Supports optional Optuna hyperparameter
tuning per model type.

Usage:
    python scripts/train_ensemble.py
    python scripts/train_ensemble.py --tune --trials 50
    python scripts/train_ensemble.py --ensemble-dir models/ensemble_v2
"""

import argparse
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import (
    CB_CONSERVATIVE_PARAMS,
    CONSERVATIVE_PARAMS,
    ENSEMBLE_DIR,
    HOLDOUT_SEASON,
    LGB_CONSERVATIVE_PARAMS,
    SELECTED_FEATURES,
)
from ensemble_training import (
    _cb_fit_kwargs,
    _lgb_fit_kwargs,
    _xgb_fit_kwargs,
    make_cb_model,
    make_lgb_model,
    make_xgb_model,
    train_ensemble,
    walk_forward_cv_with_oof,
)
from feature_engineering import assemble_multiyear_features, get_feature_columns
from feature_selector import select_features_for_fold


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Train ensemble prediction models (XGB+LGB+CB+Ridge) "
            "with optional Optuna hyperparameter tuning."
        ),
    )
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Run Optuna hyperparameter tuning (default: use conservative defaults).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=50,
        help="Number of Optuna trials per model per target (default: 50).",
    )
    parser.add_argument(
        "--ensemble-dir",
        type=str,
        default=None,
        help=f"Output directory for ensemble artifacts (default: {ENSEMBLE_DIR}).",
    )
    parser.add_argument(
        "--features-from",
        type=str,
        default=None,
        help=(
            "Path to an existing ensemble metadata.json whose selected_features "
            "list should be reused (e.g. models/ensemble/metadata.json)."
        ),
    )
    parser.add_argument(
        "--include-player-features",
        action="store_true",
        help=(
            "Assemble players/usage + players/advanced team-aggregate candidate "
            "features (opt-in; default off leaves the shipped 120-feature path "
            "byte-for-byte unchanged -- see .planning/ENSEMBLE_PLAYER_FEATURES_"
            "2026_08_16.md). Appends the new candidates to the --features-from "
            "pool (or the full candidate pool if --features-from is omitted) and "
            "re-runs the standard SHAP + correlation selection "
            "(feature_selector.select_features_for_fold) at the same target "
            "count, rather than hand-picking which new features to keep."
        ),
    )
    parser.add_argument(
        "--include-ep-features",
        action="store_true",
        help=(
            "Assemble ffopportunity expected-points team-aggregate candidate "
            "features (opt-in; default off leaves the shipped 120-feature path "
            "byte-for-byte unchanged -- see .planning/ENSEMBLE_EP_FEATURES_"
            "GATE.md). Composable with --include-player-features. Appends the "
            "new candidates to the --features-from pool (or the full candidate "
            "pool if --features-from is omitted) and re-runs the standard SHAP "
            "+ correlation selection (feature_selector.select_features_for_fold) "
            "at the same target count."
        ),
    )
    return parser


def _run_optuna_tuning(
    all_data,
    feature_cols: list,
    n_trials: int,
) -> dict:
    """Run Optuna tuning for all three model types on both targets.

    Args:
        all_data: Full training DataFrame with features and targets.
        feature_cols: Feature column names.
        n_trials: Number of trials per model per target.

    Returns:
        Dict with keys 'xgb_params', 'lgb_params', 'cb_params' containing
        the best hyperparameters found.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    targets = {"spread": "actual_margin", "total": "actual_total"}

    # Accumulate best params across targets (use spread params as final)
    best_xgb: Optional[dict] = None
    best_lgb: Optional[dict] = None
    best_cb: Optional[dict] = None

    for target_name, target_col in targets.items():
        print(f"\n--- Tuning for {target_name} ({target_col}) ---")

        # XGBoost tuning
        print(f"  XGBoost: {n_trials} trials...")

        def xgb_objective(trial: optuna.Trial) -> float:
            params = {
                "max_depth": trial.suggest_int("max_depth", 2, 6),
                "learning_rate": trial.suggest_float(
                    "learning_rate", 0.01, 0.15, log=True
                ),
                "min_child_weight": trial.suggest_int("min_child_weight", 3, 20),
                "subsample": trial.suggest_float("subsample", 0.6, 0.9),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 0.8),
                "reg_alpha": trial.suggest_float("reg_alpha", 0.1, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
                "n_estimators": 500,
                "early_stopping_rounds": 50,
                "objective": "reg:squarederror",
                "random_state": 42,
                "verbosity": 0,
            }
            result, _ = walk_forward_cv_with_oof(
                all_data,
                feature_cols,
                target_col,
                model_factory=lambda p=params: make_xgb_model(p),
                fit_kwargs_fn=_xgb_fit_kwargs,
            )
            return result.mean_mae

        study = optuna.create_study(
            direction="minimize", study_name=f"xgb_{target_name}"
        )
        study.optimize(xgb_objective, n_trials=n_trials)
        print(f"  XGBoost best MAE: {study.best_trial.value:.4f}")
        print(f"  XGBoost best params: {study.best_params}")
        xgb_params = study.best_params.copy()
        xgb_params.update({
            "n_estimators": 500,
            "early_stopping_rounds": 50,
            "objective": "reg:squarederror",
            "random_state": 42,
            "verbosity": 0,
        })
        best_xgb = xgb_params

        # LightGBM tuning
        print(f"  LightGBM: {n_trials} trials...")

        def lgb_objective(trial: optuna.Trial) -> float:
            params = {
                "max_depth": trial.suggest_int("max_depth", 2, 6),
                "learning_rate": trial.suggest_float(
                    "learning_rate", 0.01, 0.15, log=True
                ),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
                "subsample": trial.suggest_float("subsample", 0.6, 0.9),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 0.8),
                "reg_alpha": trial.suggest_float("reg_alpha", 0.1, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
                "n_estimators": 500,
                "objective": "regression",
                "random_state": 42,
                "verbose": -1,
                "force_col_wise": True,
            }
            result, _ = walk_forward_cv_with_oof(
                all_data,
                feature_cols,
                target_col,
                model_factory=lambda p=params: make_lgb_model(p),
                fit_kwargs_fn=_lgb_fit_kwargs,
            )
            return result.mean_mae

        study = optuna.create_study(
            direction="minimize", study_name=f"lgb_{target_name}"
        )
        study.optimize(lgb_objective, n_trials=n_trials)
        print(f"  LightGBM best MAE: {study.best_trial.value:.4f}")
        print(f"  LightGBM best params: {study.best_params}")
        lgb_params = study.best_params.copy()
        lgb_params.update({
            "n_estimators": 500,
            "objective": "regression",
            "random_state": 42,
            "verbose": -1,
            "force_col_wise": True,
        })
        best_lgb = lgb_params

        # CatBoost tuning
        print(f"  CatBoost: {n_trials} trials...")

        def cb_objective(trial: optuna.Trial) -> float:
            params = {
                "depth": trial.suggest_int("depth", 2, 6),
                "learning_rate": trial.suggest_float(
                    "learning_rate", 0.01, 0.15, log=True
                ),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 20.0, log=True),
                "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 10, 50),
                "subsample": trial.suggest_float("subsample", 0.6, 0.9),
                "rsm": trial.suggest_float("rsm", 0.5, 0.8),
                "iterations": 500,
                "loss_function": "RMSE",
                "bootstrap_type": "Bernoulli",
                "random_seed": 42,
                "verbose": 0,
                "early_stopping_rounds": 50,
                "allow_writing_files": False,
            }
            result, _ = walk_forward_cv_with_oof(
                all_data,
                feature_cols,
                target_col,
                model_factory=lambda p=params: make_cb_model(p),
                fit_kwargs_fn=_cb_fit_kwargs,
            )
            return result.mean_mae

        study = optuna.create_study(
            direction="minimize", study_name=f"cb_{target_name}"
        )
        study.optimize(cb_objective, n_trials=n_trials)
        print(f"  CatBoost best MAE: {study.best_trial.value:.4f}")
        print(f"  CatBoost best params: {study.best_params}")
        cb_params = study.best_params.copy()
        cb_params.update({
            "iterations": 500,
            "loss_function": "RMSE",
            "bootstrap_type": "Bernoulli",
            "random_seed": 42,
            "verbose": 0,
            "early_stopping_rounds": 50,
            "allow_writing_files": False,
        })
        best_cb = cb_params

    return {
        "xgb_params": best_xgb,
        "lgb_params": best_lgb,
        "cb_params": best_cb,
    }


def main(argv: list = None) -> int:
    """Main entry point for the ensemble training CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    ensemble_dir = args.ensemble_dir or ENSEMBLE_DIR
    start_time = time.time()

    print("\nEnsemble Training Pipeline (XGB + LGB + CB + Ridge)")
    print("=" * 60)

    # Step 1: Assemble features
    print("Assembling game features...")
    try:
        all_data = assemble_multiyear_features(
            include_player_features=args.include_player_features,
            include_ep_features=args.include_ep_features,
        )
    except Exception as e:
        print(f"ERROR: Failed to assemble features: {e}")
        return 1

    if all_data.empty:
        print("ERROR: No game data assembled. Check Silver/Bronze data.")
        return 1

    # Step 2: Determine feature columns
    if args.features_from:
        import json

        with open(args.features_from) as fh:
            prior_meta = json.load(fh)
        prior_features = prior_meta.get("selected_features") or []
        feature_cols = [c for c in prior_features if c in all_data.columns]
        missing = sorted(set(prior_features) - set(feature_cols))
        print(
            f"Using {len(feature_cols)} features from {args.features_from}"
            + (f" ({len(missing)} missing in current data)" if missing else "")
        )
    elif SELECTED_FEATURES is not None:
        feature_cols = [c for c in SELECTED_FEATURES if c in all_data.columns]
        print(f"Using {len(feature_cols)} selected features from config")
    else:
        feature_cols = get_feature_columns(all_data)
        print(
            f"WARNING: SELECTED_FEATURES is None, "
            f"using all {len(feature_cols)} features"
        )

    # Step 2b: Append player-aggregate candidates and re-run the standard
    # SHAP + correlation selection (mirrors run_final_selection() in
    # scripts/run_feature_selection.py) at the same target count, rather
    # than hand-picking which new features to keep.
    if args.include_player_features or args.include_ep_features:
        prior_pool = feature_cols
        full_pool = get_feature_columns(all_data)
        candidate_pool = sorted(set(prior_pool) | set(full_pool))
        target_count = len(prior_pool) if prior_pool else len(full_pool)
        train_data = all_data[all_data["season"] < HOLDOUT_SEASON]
        print(
            f"\nRe-running SHAP feature selection: {len(candidate_pool)} candidates "
            f"({len(prior_pool)} prior + {len(candidate_pool) - len(prior_pool)} "
            f"new-or-unselected) -> target_count={target_count}"
        )
        selection = select_features_for_fold(
            train_data,
            candidate_pool,
            target_col="actual_margin",
            target_count=target_count,
            correlation_threshold=0.90,
            params=CONSERVATIVE_PARAMS.copy(),
        )
        feature_cols = selection.selected_features
        n_new_selected = len([f for f in feature_cols if f not in prior_pool])
        print(
            f"Selected {len(feature_cols)} features "
            f"({n_new_selected} newly selected, not in the prior pool)"
        )

    print(f"{len(all_data)} games, {len(feature_cols)} features")

    # Step 3: Determine hyperparameters
    xgb_params = None
    lgb_params = None
    cb_params = None

    if args.tune:
        print(f"\nRunning Optuna tuning ({args.trials} trials per model per target)...")
        try:
            tuned = _run_optuna_tuning(all_data, feature_cols, args.trials)
            xgb_params = tuned["xgb_params"]
            lgb_params = tuned["lgb_params"]
            cb_params = tuned["cb_params"]
        except Exception as e:
            print(f"ERROR: Optuna tuning failed: {e}")
            return 1
    else:
        print("\nUsing conservative default hyperparameters (pass --tune to optimize)")

    # Step 4: Train ensemble
    print("\nTraining ensemble (spread + total)...")
    try:
        metadata = train_ensemble(
            all_data,
            feature_cols,
            xgb_params=xgb_params,
            lgb_params=lgb_params,
            cb_params=cb_params,
            ensemble_dir=ensemble_dir,
        )
    except Exception as e:
        print(f"ERROR: Ensemble training failed: {e}")
        return 1

    # Step 5: Print summary
    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"ENSEMBLE TRAINING COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Output:     {ensemble_dir}")
    print(f"  Features:   {metadata['n_features']}")
    print(f"  Duration:   {elapsed:.1f}s")

    for target_name in ("spread", "total"):
        target_meta = metadata[target_name]
        print(f"\n  {target_name.upper()}:")
        print(f"    XGB CV MAE:  {target_meta['xgb_cv_mae']:.4f}")
        print(f"    LGB CV MAE:  {target_meta['lgb_cv_mae']:.4f}")
        print(f"    CB  CV MAE:  {target_meta['cb_cv_mae']:.4f}")
        print(f"    Ridge alpha: {target_meta['ridge_alpha']}")
        coefs = target_meta["ridge_coefficients"]
        print(f"    Ridge coefs: XGB={coefs[0]:.4f}, LGB={coefs[1]:.4f}, CB={coefs[2]:.4f}")

    print(f"\n{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
