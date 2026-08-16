#!/usr/bin/env python3
"""Walk-forward (never-sealed) candidate ranking for QB/RB consolidation.

Reuses the existing walk-forward CV primitive `train_residual_model`
(expanding-window, val_seasons=[2022,2023,2024], RidgeCV proxy) as a FAST,
model-type-agnostic way to rank span/recency/feature-pool candidates BEFORE
spending a sealed-2025 touch. Each candidate reuses the feature list already
SHAP-selected by its real (LGB, matching shipped hyperparams) training run
saved under models/span_experiments_2026_08_16/ or
models/pbp_feature_experiments_2026_08_16/ -- no re-selection here, this is
purely a walk-forward comparison of "given this candidate's own chosen
features and data span/weighting, how does it do out-of-sample on
2022/2023/2024 in turn." Never reads 2025.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hybrid_projection import train_residual_model  # noqa: E402
from player_feature_engineering import assemble_multiyear_player_features  # noqa: E402

REF_SEASON = 2024
MAX_DUP = 12


def recency_dup(df, half_life):
    age = (REF_SEASON - df["season"]).clip(lower=0)
    weight = 0.5 ** (age / half_life)
    counts = np.round(weight / weight.min()).astype(int).clip(1, MAX_DUP)
    return df.loc[df.index.repeat(counts.values)].reset_index(drop=True)


def load_features(meta_path):
    return json.load(open(meta_path))["features"]


def main():
    print("Assembling 2012-2024 superset once (never touches 2025)...")
    all_data = assemble_multiyear_player_features(list(range(2012, 2025)))

    specs = {
        "QB": {
            "zone_more_years": (
                "models/span_experiments_2026_08_16/more_years/qb_residual_meta.json",
                2012,
                None,
            ),
            "zone_recency_hl3": (
                "models/span_experiments_2026_08_16/recency_hl3/qb_residual_meta.json",
                2016,
                3.0,
            ),
            "zone_more_years_recency_hl3": (
                "models/span_experiments_2026_08_16/combo/qb_residual_meta.json",
                2012,
                3.0,
            ),
        },
        "RB": {
            "zone_alone": (
                "models/pbp_feature_experiments_2026_08_16/pbp_ftn/rb_residual_meta.json",
                2016,
                None,
            ),
            "zone_more_years": (
                "models/span_experiments_2026_08_16/more_years/rb_residual_meta.json",
                2012,
                None,
            ),
            "zone_recency_hl3": (
                "models/span_experiments_2026_08_16/recency_hl3/rb_residual_meta.json",
                2016,
                3.0,
            ),
            "zone_more_years_recency_hl3": (
                "models/span_experiments_2026_08_16/combo/rb_residual_meta.json",
                2012,
                3.0,
            ),
        },
    }

    results = {}
    for position, cands in specs.items():
        pos_all = all_data[all_data["position"] == position].copy()
        results[position] = {}
        for name, (meta_path, min_season, hl) in cands.items():
            if not os.path.exists(meta_path):
                print(f"  SKIP {position}/{name}: {meta_path} not found")
                continue
            feats = load_features(meta_path)
            df = pos_all[pos_all["season"] >= min_season].copy()
            if hl:
                df = recency_dup(df, hl)
            res, _ = train_residual_model(
                df, position, feats, val_seasons=[2022, 2023, 2024]
            )
            results[position][name] = res
            print(
                f"  {position}/{name}: mean_mae={res['mean_mae']:.4f} "
                f"folds={[(f['val_season'], round(f['mae'],4)) for f in res['fold_details']]}"
            )

    print("\n" + "=" * 90)
    print("WALK-FORWARD SUMMARY (2022/2023/2024 expanding-window CV, RidgeCV proxy on "
          "each candidate's own SHAP-selected features; sealed 2025 untouched)")
    print("=" * 90)
    for position, cands in results.items():
        print(f"\n{position}:")
        for name, res in sorted(cands.items(), key=lambda kv: kv[1]["mean_mae"]):
            print(f"  {name:<32} mean_mae={res['mean_mae']:.4f}")

    with open("scratch_wf_gate_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
