#!/usr/bin/env python3
"""Train XGBoost game prediction models with walk-forward CV and Optuna tuning.

Usage:
    python scripts/train_prediction_model.py --target spread
    python scripts/train_prediction_model.py --target total --trials 100
    python scripts/train_prediction_model.py --target spread --no-tune
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import xgboost as xgb

from config import CONSERVATIVE_PARAMS, MODEL_DIR, TRAINING_SEASONS
from feature_engineering import assemble_multiyear_features, get_feature_columns
from model_training import train_final_model, walk_forward_cv

# Target column mapping: CLI flag -> DataFrame column name
TARGET_MAP = {
    "spread": "actual_margin",
    "total": "actual_total",
}


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the training CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Train XGBoost game prediction models with walk-forward CV and Optuna tuning.",
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=["spread", "total"],
        help="Prediction target: 'spread' (point margin) or 'total' (over/under).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=50,
        help="Number of Optuna trials for hyperparameter tuning (default: 50).",
    )
    parser.add_argument(
        "--no-tune",
        action="store_true",
        help="Skip Optuna tuning and use conservative default hyperparameters.",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=None,
        help="Override training seasons (default: 2016-2023).",
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Override model output directory (default: models/).",
    )
    return parser


def _run_optuna_tuning(
    all_data: pd.DataFrame,
    feature_cols: list,
    target_col: str,
    n_trials: int,
    target_name: str,
) -> dict:
    """Run Optuna hyperparameter tuning and return best params.

    Args:
        all_data: Full training DataFrame.
        feature_cols: Feature column names.
        target_col: Target column name.
        n_trials: Number of Optuna trials.
        target_name: Study name prefix ('spread' or 'total').

    Returns:
        Best hyperparameters merged with fixed params.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        """Optuna objective: minimize walk-forward CV MAE."""
        params = {
            "max_depth": trial.suggest_int("max_depth", 2, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "min_child_weight": trial.suggest_int("min_child_weight", 3, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 0.9),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 0.8),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.1, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
            # Fixed params
            "n_estimators": 500,
            "early_stopping_rounds": 50,
            "objective": "reg:squarederror",
            "random_state": 42,
            "verbosity": 0,
        }
        result = walk_forward_cv(all_data, feature_cols, target_col, params=params)
        return result.mean_mae

    study = optuna.create_study(
        direction="minimize",
        study_name=f"{target_name}_prediction",
    )
    study.optimize(objective, n_trials=n_trials)

    print(f"\nBest MAE: {study.best_trial.value:.4f}")
    print(f"Best params: {study.best_params}")

    # Merge best params with fixed params
    best_params = study.best_params.copy()
    best_params.update({
        "n_estimators": 500,
        "early_stopping_rounds": 50,
        "objective": "reg:squarederror",
        "random_state": 42,
        "verbosity": 0,
    })

    return best_params


def _write_feature_importance(
    model: xgb.XGBRegressor,
    feature_cols: list,
    output_dir: str,
) -> None:
    """Write feature importance report to console and CSV.

    Args:
        model: Trained XGBRegressor model.
        feature_cols: Feature column names used during training.
        output_dir: Directory to write feature_importance.csv.
    """
    importance_df = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False).reset_index(drop=True)

    # Console report
    print("\n" + "=" * 60)
    print("Top 20 Features by Gain:")
    print("=" * 60)
    for i, row in importance_df.head(20).iterrows():
        print(f"  {i + 1:2d}. {row['feature']:<50s} {row['importance']:.6f}")
    print("=" * 60)

    # CSV output
    csv_path = os.path.join(output_dir, "feature_importance.csv")
    importance_df.to_csv(csv_path, index=False)
    print(f"\nFeature importance saved to {csv_path}")


def main(argv: list = None) -> int:
    """Main entry point for the training CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    target_col = TARGET_MAP[args.target]
    seasons = args.seasons or TRAINING_SEASONS
    model_dir = args.model_dir or MODEL_DIR

    print(f"\nTraining {args.target} prediction model...")
    print(f"Target column: {target_col}")
    print(f"Seasons: {min(seasons)}-{max(seasons)}")

    # Load data
    all_data = assemble_multiyear_features(seasons)
    if all_data.empty:
        print("ERROR: No game data assembled. Check Silver data availability.")
        return 1
    feature_cols = get_feature_columns(all_data)
    if not feature_cols:
        print("ERROR: No feature columns found in assembled data.")
        return 1
    print(
        f"{len(all_data)} games, {len(feature_cols)} features, "
        f"seasons {min(seasons)}-{max(seasons)}"
    )

    pre_cv_result = None
    if args.no_tune:
        # Use conservative defaults
        best_params = CONSERVATIVE_PARAMS.copy()
        print("\nSkipping Optuna tuning, using conservative defaults...")
        pre_cv_result = walk_forward_cv(all_data, feature_cols, target_col, params=best_params)
        print(f"\nWalk-forward CV MAE: {pre_cv_result.mean_mae:.4f}")
        for fold in pre_cv_result.fold_details:
            print(
                f"  Fold {fold['val_season']}: "
                f"train {fold['train_seasons'][0]}-{fold['train_seasons'][-1]} "
                f"({fold['train_size']} games) -> MAE {fold['mae']:.4f}"
            )
    else:
        # Optuna tuning
        print(f"\nRunning Optuna tuning with {args.trials} trials...")
        best_params = _run_optuna_tuning(
            all_data, feature_cols, target_col,
            n_trials=args.trials,
            target_name=args.target,
        )

    # Train final model
    print("\nTraining final model...")
    model, metadata = train_final_model(
        all_data, feature_cols, target_col,
        params=best_params,
        target_name=args.target,
        model_dir=model_dir,
        cv_result=pre_cv_result,
    )

    output_dir = os.path.join(model_dir, args.target)

    # Feature importance report
    _write_feature_importance(model, feature_cols, output_dir)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Model saved to: {os.path.join(output_dir, 'model.json')}")
    print(f"Metadata saved to: {os.path.join(output_dir, 'metadata.json')}")
    print(f"CV MAE: {metadata['cv_scores']['mean_mae']:.4f}")
    print(f"Features: {len(feature_cols)}")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
