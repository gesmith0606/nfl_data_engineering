#!/usr/bin/env python3
"""ONE sealed-2025 confirmation read per position for the consolidation task.

Evaluates a small, explicit list of (position, model_dir) candidates against
the sealed-2025 matched population (weeks 3-18), reusing the exact same
population-assembly recipe as scripts/span_recency_gate.py so numbers are
directly comparable to the sealed reads already recorded in
.planning/holdout_ledger.json. Read-only; touches 2025 exactly once per
position for exactly the candidates listed below (the walk-forward winners).
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import HOLDOUT_SEASON, PLAYER_DATA_SEASONS  # noqa: E402
from hybrid_projection import apply_residual_correction  # noqa: E402
from player_feature_engineering import assemble_multiyear_player_features  # noqa: E402
from unified_evaluation import (  # noqa: E402
    build_defensive_strength_table,
    compute_actual_fantasy_points,
    compute_production_heuristic,
)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

# (position, label, model_dir)
CANDIDATES = [
    ("QB", "shipped", "models/residual"),
    ("QB", "winner", None),  # filled in by caller via --qb-winner
    ("RB", "shipped", "models/residual"),
    ("RB", "winner", None),  # filled in by caller via --rb-winner
]


def load_bronze_weekly(seasons):
    dfs = []
    for s in seasons:
        pattern = os.path.join(
            BASE_DIR, "data", "bronze", "players", "weekly", f"season={s}", "*.parquet"
        )
        files = sorted(glob.glob(pattern))
        if files:
            dfs.append(pd.read_parquet(files[-1]))
    return pd.concat(dfs, ignore_index=True) if dfs else None


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--qb-winner", required=True)
    ap.add_argument("--rb-winner", required=True)
    args = ap.parse_args()

    cands = [
        ("QB", "shipped", "models/residual"),
        ("QB", "winner", args.qb_winner),
        ("RB", "shipped", "models/residual"),
        ("RB", "winner", args.rb_winner),
    ]

    print("Assembling sealed-2025 eval population (2016-2025, weeks 3-18)...")
    all_data = assemble_multiyear_player_features(list(range(2016, HOLDOUT_SEASON + 1)))
    opp_rankings = build_defensive_strength_table(PLAYER_DATA_SEASONS)
    weekly_df = load_bronze_weekly(PLAYER_DATA_SEASONS)

    eval_rows = {}
    for position in ["QB", "RB"]:
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] == HOLDOUT_SEASON].copy()
        heur = compute_production_heuristic(
            pos_data, position, opp_rankings, "half_ppr", weekly_df=weekly_df
        )
        actual = compute_actual_fantasy_points(pos_data, "half_ppr")
        week_mask = pos_data["week"].between(3, 18)
        valid = week_mask & heur.notna() & actual.notna()
        matched = pos_data[valid].copy()
        matched["_heuristic_pts"] = heur[valid]
        matched["_actual_pts"] = actual[valid]
        eval_rows[position] = matched
        print(f"  {position}: {len(matched)} matched sealed-2025 rows")

    results = {}
    for position, label, model_dir in cands:
        matched = eval_rows[position]
        heuristic_df = pd.DataFrame(
            {
                "player_id": matched["player_id"].values,
                "projected_points": matched["_heuristic_pts"].values,
            },
            index=matched.index,
        )
        corrected = apply_residual_correction(
            heuristic_df, matched, position, model_dir=model_dir
        )
        pred = corrected["projected_points"].values
        actual = matched["_actual_pts"].values
        err = pred - actual
        mae = float(np.mean(np.abs(err)))
        bias = float(np.mean(err))
        results[f"{position}_{label}"] = {
            "model_dir": model_dir,
            "mae": mae,
            "bias": bias,
            "n": len(matched),
        }
        print(f"  {position}/{label} ({model_dir}): MAE={mae:.4f} bias={bias:+.3f} n={len(matched)}")

    with open("scratch_sealed_gate_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
