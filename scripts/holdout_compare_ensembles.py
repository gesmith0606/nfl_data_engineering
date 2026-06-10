#!/usr/bin/env python3
"""One-shot sealed-holdout comparison between two ensemble directories.

Evaluates spread + total predictions on the sealed holdout season for the
production ensemble and a candidate ensemble. Intended to be run AT MOST
ONCE per candidate decision — repeated runs invalidate the holdout.

Usage:
    python scripts/holdout_compare_ensembles.py \
        --baseline models/ensemble --candidate models/ensemble_v3
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import HOLDOUT_SEASON
from ensemble_training import load_ensemble, predict_ensemble
from feature_engineering import assemble_multiyear_features
from prediction_backtester import compute_profit, evaluate_ats, evaluate_ou


def evaluate_dir(ensemble_dir: str, holdout: pd.DataFrame) -> dict:
    """Evaluate one ensemble dir on the holdout frame."""
    spread_models, total_models, metadata = load_ensemble(ensemble_dir)
    feats = metadata["selected_features"]
    X = holdout[[c for c in feats if c in holdout.columns]]
    missing = [c for c in feats if c not in holdout.columns]
    for c in missing:
        X = X.assign(**{c: np.nan})
    X = X[feats]

    df = holdout.copy()
    df["predicted_margin"] = predict_ensemble(X, spread_models)
    df["predicted_total"] = predict_ensemble(X, total_models)

    df = evaluate_ats(df)
    df = evaluate_ou(df)

    spread_mae = float((df["predicted_margin"] - df["actual_margin"]).abs().mean())
    total_mae = float((df["predicted_total"] - df["actual_total"]).abs().mean())

    ats = df.dropna(subset=["ats_correct"])
    profit = compute_profit(ats)

    out = {
        "dir": ensemble_dir,
        "n_games": len(df),
        "spread_mae": spread_mae,
        "total_mae": total_mae,
        "ats_accuracy": float(ats["ats_correct"].mean()),
        "ats_profit": profit["profit"],
        "ats_roi": profit["roi"],
        "ou_accuracy": float(df["ou_correct"].dropna().mean()),
    }

    # High-edge subset (>= 3 pts vs the line)
    edge = df["predicted_margin"] - df["spread_line"]
    he = ats[edge.abs().reindex(ats.index) >= 3.0]
    if len(he):
        out["ats_accuracy_edge3"] = float(he["ats_correct"].mean())
        out["n_edge3"] = len(he)

    # Calibrated probabilities sanity (candidate only has calibrators)
    calib = spread_models.get("calibrator")
    if calib is not None:
        p = calib.predict_proba(edge.values.reshape(-1, 1))[:, 1]
        out["calib_prob_range"] = (float(np.min(p)), float(np.max(p)))

    return out


def compare_metas_on_holdout(ensemble_dir: str, holdout: pd.DataFrame) -> None:
    """Compare legacy RidgeCV meta vs shipped meta on shared base models.

    The production dir (models/ensemble) is missing LGB/CB artifacts, so the
    baseline meta is reconstructed the way train_ensemble used to build it:
    RidgeCV fit on the full OOF matrix (saved in the candidate dir).
    """
    from ensemble_training import train_ridge_meta

    spread_models, total_models, metadata = load_ensemble(ensemble_dir)
    feats = metadata["selected_features"]
    X = holdout[[c for c in feats if c in holdout.columns]]

    for target, models, target_col, line_col in (
        ("spread", spread_models, "actual_margin", "spread_line"),
        ("total", total_models, "actual_total", "total_line"),
    ):
        oof = pd.read_parquet(os.path.join(ensemble_dir, f"oof_{target}.parquet"))
        legacy_meta = train_ridge_meta(oof)

        base = np.column_stack(
            [
                models["xgb"].predict(X),
                models["lgb"].predict(X),
                models["cb"].predict(X),
            ]
        )
        actual = holdout[target_col].values
        line = holdout[line_col].values

        print(f"\n--- {target.upper()} (n={len(holdout)}) ---")
        for name, pred in (
            ("legacy ridge_cv", legacy_meta.predict(base)),
            ("shipped (mean)", models["ridge"].predict(base)),
        ):
            mae = float(np.abs(pred - actual).mean())
            push = actual == line
            win = (pred > line) == (actual > line)
            valid = ~push & (pred != line)
            acc = float(win[valid].mean())
            n = int(valid.sum())
            wins = int(win[valid].sum())
            profit = wins * (100 / 110) - (n - wins)
            edge = np.abs(pred - line) >= 3.0
            he = valid & edge
            acc3 = float(win[he].mean()) if he.sum() else float("nan")
            print(
                f"  {name:<18} MAE {mae:.3f} | acc {acc:.4f} (n={n}) "
                f"| profit {profit:+.1f}u | edge>=3 acc {acc3:.4f} (n={int(he.sum())})"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="models/ensemble")
    parser.add_argument("--candidate", default="models/ensemble_v3")
    parser.add_argument(
        "--meta-only",
        action="store_true",
        help="Compare meta-learners on the candidate's shared base models.",
    )
    args = parser.parse_args()

    print(f"SEALED HOLDOUT comparison on season {HOLDOUT_SEASON} — single use!")
    all_data = assemble_multiyear_features()
    holdout = all_data[all_data["season"] == HOLDOUT_SEASON].dropna(
        subset=["actual_margin", "actual_total", "spread_line", "total_line"]
    )
    print(f"Holdout games: {len(holdout)}")

    if args.meta_only:
        compare_metas_on_holdout(args.candidate, holdout)
        return 0

    for d in (args.baseline, args.candidate):
        r = evaluate_dir(d, holdout)
        print(f"\n=== {d} ===")
        for k, v in r.items():
            print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
