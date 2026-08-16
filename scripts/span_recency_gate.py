#!/usr/bin/env python3
"""Sealed-2025 gate for the span/recency residual experiments.

Assembles the sealed-2025 eval population ONCE (same vintage, same session,
matched rows across every variant compared) and evaluates each trained
variant in models/span_experiments_2026_08_16/<variant>/ against it, plus a
2024-season-only slice diagnostic (the "thinning margin" question from
.planning/OPPORTUNITY_SCAN_2026_08_16.md).

Gate (pre-registered per task brief):
    Adopt-recommend a variant only if it improves sealed-2025 matched MAE at
    >=1 position by >=0.03 with NO other position worsening by >0.02,
    relative to the SAME-SESSION baseline (models/span_experiments_2026_08_16/baseline/).

Does not modify src/hybrid_projection.py, src/player_feature_engineering.py,
or src/unified_evaluation.py -- read-only calls only.
"""

import argparse
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
OUT_ROOT = os.path.join("models", "span_experiments_2026_08_16")
POSITIONS = ["QB", "RB", "WR", "TE"]


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["more_years", "recency_hl3", "recency_hl6"],
        help="Variant subdirs under models/span_experiments_2026_08_16/ to gate "
        "against 'baseline'.",
    )
    parser.add_argument("--scoring", default="half_ppr")
    args = parser.parse_args()

    print("Assembling sealed-2025 eval population (2016-2025, weeks 3-18)...")
    all_data = assemble_multiyear_player_features(list(range(2016, HOLDOUT_SEASON + 1)))
    opp_rankings = build_defensive_strength_table(PLAYER_DATA_SEASONS)
    weekly_df = load_bronze_weekly(PLAYER_DATA_SEASONS)

    eval_rows = {}  # position -> matched eval DataFrame (features + heuristic + actual)
    for position in POSITIONS:
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] == HOLDOUT_SEASON].copy()
        if pos_data.empty:
            print(f"  {position}: no sealed-2025 rows, skipping")
            continue

        heur = compute_production_heuristic(
            pos_data, position, opp_rankings, args.scoring, weekly_df=weekly_df
        )
        actual = compute_actual_fantasy_points(pos_data, args.scoring)
        week_mask = pos_data["week"].between(3, 18)
        valid = week_mask & heur.notna() & actual.notna()

        matched = pos_data[valid].copy()
        matched["_heuristic_pts"] = heur[valid]
        matched["_actual_pts"] = actual[valid]
        eval_rows[position] = matched
        print(f"  {position}: {len(matched)} matched sealed-2025 rows (weeks 3-18)")

    def mae_for(variant: str, position: str, matched: pd.DataFrame):
        """Apply variant's saved residual model, return (mae, bias, n)."""
        model_dir = os.path.join(OUT_ROOT, variant)
        heuristic_df = pd.DataFrame(
            {
                "player_id": matched["player_id"].values,
                "projected_points": matched["_heuristic_pts"].values,
            },
            index=matched.index,
        )
        try:
            corrected = apply_residual_correction(
                heuristic_df, matched, position, model_dir=model_dir
            )
        except Exception as exc:
            print(f"    WARN: {variant}/{position} apply failed: {exc}")
            return None
        pred = corrected["projected_points"].values
        actual = matched["_actual_pts"].values
        err = pred - actual
        mae = float(np.mean(np.abs(err)))
        bias = float(np.mean(err))
        return mae, bias, len(matched)

    # -------------------------------------------------------------------
    # Full sealed-2025 gate table
    # -------------------------------------------------------------------
    print(f"\n{'=' * 100}")
    print("SEALED-2025 GATE (weeks 3-18, matched rows)")
    print(f"{'=' * 100}")
    header = f"{'Position':<9}{'n':>6}{'baseline MAE (bias)':>24}"
    for v in args.variants:
        header += f"{v + ' MAE (bias)':>26}{'delta vs baseline':>16}"
    print(header)

    gate_results = {}  # variant -> position -> delta (baseline_mae - variant_mae; positive=improve)
    for v in args.variants:
        gate_results[v] = {}

    for position, matched in eval_rows.items():
        base = mae_for("baseline", position, matched)
        if base is None:
            continue
        base_mae, base_bias, n = base
        row = f"{position:<9}{n:>6}{base_mae:>18.3f} ({base_bias:+.2f})"
        for v in args.variants:
            res = mae_for(v, position, matched)
            if res is None:
                row += f"{'FAILED':>26}{'':>16}"
                continue
            v_mae, v_bias, _ = res
            delta = base_mae - v_mae  # positive = variant improves
            gate_results[v][position] = delta
            row += f"{v_mae:>20.3f} ({v_bias:+.2f})" + f"{delta:>+16.3f}"
        print(row)

    # -------------------------------------------------------------------
    # 2024-season-only slice diagnostic (opportunity-scan motivating question)
    # NOTE: 2024 is in the training window (2016-2024), so this is an
    # in-sample slice, not a sealed holdout -- reported as a diagnostic only,
    # per the task brief ("report whether weighting specifically closes the
    # 2024-season slice gap"). The real gate is the sealed-2025 table above.
    # -------------------------------------------------------------------
    print(f"\n{'=' * 100}")
    print("2024-SEASON TRAIN-WINDOW SLICE DIAGNOSTIC (in-sample; NOT the gate)")
    print(f"{'=' * 100}")
    all_2024 = {}
    for position in POSITIONS:
        pos_data = all_data[all_data["position"] == position].copy()
        pos_data = pos_data[pos_data["season"] == 2024].copy()
        if pos_data.empty:
            continue
        heur = compute_production_heuristic(
            pos_data, position, opp_rankings, args.scoring, weekly_df=weekly_df
        )
        actual = compute_actual_fantasy_points(pos_data, args.scoring)
        week_mask = pos_data["week"].between(3, 18)
        valid = week_mask & heur.notna() & actual.notna()
        matched = pos_data[valid].copy()
        matched["_heuristic_pts"] = heur[valid]
        matched["_actual_pts"] = actual[valid]
        all_2024[position] = matched

    header2 = f"{'Position':<9}{'n':>6}{'baseline MAE':>16}"
    for v in args.variants:
        header2 += f"{v + ' MAE':>18}{'delta':>10}"
    print(header2)
    for position, matched in all_2024.items():
        base = mae_for("baseline", position, matched)
        if base is None:
            continue
        base_mae, _, n = base
        row = f"{position:<9}{n:>6}{base_mae:>16.3f}"
        for v in args.variants:
            res = mae_for(v, position, matched)
            if res is None:
                row += f"{'FAILED':>18}{'':>10}"
                continue
            v_mae, _, _ = res
            row += f"{v_mae:>18.3f}{base_mae - v_mae:>+10.3f}"
        print(row)

    # -------------------------------------------------------------------
    # Verdicts
    # -------------------------------------------------------------------
    print(f"\n{'=' * 100}")
    print("VERDICTS (gate: >=1 position improves >=0.03, no position worsens >0.02)")
    print(f"{'=' * 100}")
    for v in args.variants:
        deltas = gate_results[v]
        if not deltas:
            print(f"  {v}: NO DATA")
            continue
        best_improve = max(deltas.values())
        worst = min(deltas.values())  # most negative = worst regression
        worst_regression = -worst if worst < 0 else 0.0
        ship = best_improve >= 0.03 and worst_regression <= 0.02
        verdict = "SHIP (recommend)" if ship else "HOLD"
        detail = ", ".join(f"{p}={d:+.3f}" for p, d in deltas.items())
        print(f"  {v}: {verdict}  [{detail}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
